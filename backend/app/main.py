"""AuditLens FastAPI application entry-point and complete REST + SSE API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session, desc, select

from app.agent.compare import compare_audits
from app.config import get_settings
from app.costlog import get_audit_cost_summary
from app.db import get_session, init_db
from app.events import event_manager
from app.job_runner import run_audit_job_sync
from app.models import Audit, AuditStatus, Finding, Frame, VoiceNote
from app.storage import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_UPLOAD_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    StorageValidationError,
    get_audio_dir,
    get_audit_dir,
    get_frames_dir,
    get_overlays_dir,
    save_upload_file,
    validate_file_extension,
)
from app.template_loader import get_template, list_templates


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    yield


app = FastAPI(
    title="AuditLens API",
    description="Evidence-backed safety audit from walkthrough videos.",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS configured from environment variable (default: "*")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True if settings.cors_origins_list != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "provider_mode": settings.PROVIDER_MODE}


# ── Templates ─────────────────────────────────────────────────────────────────

@app.get("/api/templates")
async def get_templates_list() -> list[dict[str, Any]]:
    tmpls = list_templates()
    return [t.model_dump() for t in tmpls]


@app.get("/api/templates/{template_id}")
async def get_template_detail(template_id: str) -> dict[str, Any]:
    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    return tmpl.model_dump()


# ── Audits CRUD & Background Execution ────────────────────────────────────────

@app.post("/api/audits/demo", status_code=status.HTTP_201_CREATED)
async def create_demo_audit(
    background_tasks: BackgroundTasks,
    template_id: str = "fire_exit_safety",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Launch an audit on the pre-generated synthetic walkthrough video for zero-upload demo."""
    settings = get_settings()
    sample_path = settings.DATA_DIR / "sample_walkthrough.mp4"
    if not sample_path.exists():
        from scripts.make_sample_video import generate_sample_video
        generate_sample_video(sample_path, duration_s=25)

    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown template: '{template_id}'")

    audit = Audit(
        template_id=template_id,
        status=AuditStatus.QUEUED.value,
        video_path=str(sample_path.resolve()),
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)

    background_tasks.add_task(run_audit_job_sync, audit.id)
    return {"id": audit.id, "status": audit.status}


@app.post("/api/audits/{audit_id}/cancel")
async def cancel_audit(
    audit_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Cancel a queued or processing audit."""
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    if audit.status in (AuditStatus.QUEUED.value, AuditStatus.PROCESSING.value):
        audit.status = AuditStatus.FAILED.value
        audit.error = "Audit was canceled by user request."
        session.add(audit)
        session.commit()
        event_manager.emit({
            "type": "error",
            "ts": "",
            "audit_id": audit_id,
            "payload": {"error": "Audit was canceled by user."},
        })
    return {"id": audit.id, "status": audit.status}


@app.post("/api/audits", status_code=status.HTTP_201_CREATED)
async def create_audit(
    background_tasks: BackgroundTasks,
    video: UploadFile | None = File(default=None),
    images: list[UploadFile] | None = File(default=None),
    template_id: str | None = Form(default=None),
    custom_rules: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Create a new audit, save uploaded walkthrough footage, and dispatch background evaluation.
    """
    if not video and not images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Walkthrough media required: please upload a video or photo set.",
        )

    # Validate template or custom rules
    if not template_id and not custom_rules:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either template_id or custom_rules must be provided.",
        )

    if template_id and not custom_rules:
        tmpl = get_template(template_id)
        if not tmpl:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown template_id: '{template_id}'",
            )

    # Create new audit record
    audit = Audit(
        template_id=template_id or "custom",
        custom_rules_json=custom_rules if custom_rules else None,
        status=AuditStatus.QUEUED.value,
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)

    audit_dir = get_audit_dir(audit.id)
    saved_video_path: Path | None = None

    try:
        # Save video if provided
        if video and video.filename:
            suffix = validate_file_extension(video.filename, ALLOWED_VIDEO_EXTENSIONS)
            dest_video = audit_dir / f"walkthrough{suffix}"
            await save_upload_file(video, dest_video, allowed_extensions=ALLOWED_VIDEO_EXTENSIONS)
            saved_video_path = dest_video
            audit.video_path = str(dest_video)

        # Save photos if provided
        if images:
            for idx, img in enumerate(images):
                if img.filename:
                    suffix = validate_file_extension(img.filename, ALLOWED_IMAGE_EXTENSIONS)
                    dest_img = audit_dir / f"photo_{idx:03d}{suffix}"
                    await save_upload_file(img, dest_img, allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)

        session.add(audit)
        session.commit()

    except StorageValidationError as e:
        session.delete(audit)
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        session.delete(audit)
        session.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {str(e)}")

    # Dispatch background worker job
    background_tasks.add_task(run_audit_job_sync, audit.id)

    return {"id": audit.id, "status": audit.status}


@app.get("/api/audits")
async def list_audits(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    audits = session.exec(select(Audit).order_by(desc(Audit.created_at))).all()
    results = []
    for a in audits:
        summary = json.loads(a.summary_json) if a.summary_json else None
        results.append({
            "id": a.id,
            "status": a.status,
            "template_id": a.template_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "duration_s": a.duration_s,
            "summary": summary,
            "error": a.error,
        })
    return results


@app.get("/api/audits/{audit_id}")
async def get_audit(audit_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    findings = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
    summary = json.loads(audit.summary_json) if audit.summary_json else None

    findings_data = []
    for f in findings:
        meas = json.loads(f.measurement_json) if f.measurement_json else None
        sources = json.loads(f.sources_json) if f.sources_json else ["segmentation"]
        findings_data.append({
            "id": f.id,
            "rule_id": f.rule_id,
            "status": f.status,
            "confidence": f.confidence,
            "timestamp_s": f.timestamp_s,
            "frame_idx": f.frame_idx,
            "overlay_url": f"/api/audits/{audit_id}/overlays/{f.id}",
            "measurement": meas,
            "rationale": f.rationale,
            "fix_text": f.fix_text,
            "severity": f.severity,
            "sources": sources,
        })

    return {
        "id": audit.id,
        "status": audit.status,
        "template_id": audit.template_id,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
        "duration_s": audit.duration_s,
        "summary": summary,
        "findings": findings_data,
        "error": audit.error,
    }


# ── Server-Sent Events (SSE) ──────────────────────────────────────────────────

@app.get("/api/audits/{audit_id}/events")
async def audit_events_stream(audit_id: str, session: Session = Depends(get_session)):
    """
    Server-Sent Events endpoint streaming real-time agent execution events.
    Replays past events from JSONL, then streams live events until terminal event.
    """
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    async def event_generator():
        async for event in event_manager.subscribe(audit_id):
            yield {
                "event": event.get("type", "message"),
                "data": json.dumps(event),
            }

    return EventSourceResponse(
        event_generator(),
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
        },
    )


# ── Voice Notes Upload ────────────────────────────────────────────────────────

@app.post("/api/audits/{audit_id}/voice-notes", status_code=status.HTTP_201_CREATED)
async def upload_voice_note(
    audit_id: str,
    audio: UploadFile = File(...),
    timestamp_s: float = Form(default=0.0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Upload an auditor voice memo and attach it to the audit walkthrough timeline."""
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    try:
        suffix = validate_file_extension(audio.filename or "audio.wav", ALLOWED_AUDIO_EXTENSIONS)
        audio_dir = get_audio_dir(audit_id)
        note_id = f"vn_{Path(audio.filename or 'note').stem}"
        dest_audio = audio_dir / f"{note_id}{suffix}"

        await save_upload_file(audio, dest_audio, allowed_extensions=ALLOWED_AUDIO_EXTENSIONS)

        vn = VoiceNote(
            audit_id=audit_id,
            timestamp_s=timestamp_s,
            audio_path=str(dest_audio),
        )
        session.add(vn)
        session.commit()
        session.refresh(vn)

        return {
            "id": vn.id,
            "audit_id": audit_id,
            "timestamp_s": vn.timestamp_s,
            "audio_path": vn.audio_path,
        }
    except StorageValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Frame and Overlay Media Delivery ──────────────────────────────────────────

@app.get("/api/audits/{audit_id}/frames/{frame_idx}")
async def get_audit_frame(
    audit_id: str,
    frame_idx: int,
    session: Session = Depends(get_session),
):
    frame = session.exec(
        select(Frame).where(Frame.audit_id == audit_id, Frame.idx == frame_idx)
    ).first()

    if not frame or not Path(frame.path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Frame #{frame_idx} for audit '{audit_id}' not found",
        )
    return FileResponse(frame.path, media_type="image/jpeg")


@app.get("/api/audits/{audit_id}/overlays/{finding_id}")
async def get_audit_overlay(
    audit_id: str,
    finding_id: str,
    session: Session = Depends(get_session),
):
    finding = session.get(Finding, finding_id)
    if not finding or not finding.overlay_path or not Path(finding.overlay_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Overlay for finding '{finding_id}' not found",
        )
    return FileResponse(finding.overlay_path, media_type="image/jpeg")


# ── Comparison & Cost ─────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    before_id: str
    after_id: str


@app.post("/api/compare")
async def compare_audits_endpoint(
    req: CompareRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Compare findings between a baseline audit and a remediation audit."""
    b_audit = session.get(Audit, req.before_id)
    if not b_audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Before audit '{req.before_id}' not found")

    a_audit = session.get(Audit, req.after_id)
    if not a_audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"After audit '{req.after_id}' not found")

    b_findings = session.exec(select(Finding).where(Finding.audit_id == req.before_id)).all()
    a_findings = session.exec(select(Finding).where(Finding.audit_id == req.after_id)).all()

    b_data = [{"rule_id": f.rule_id, "status": f.status, "confidence": f.confidence, "rationale": f.rationale, "fix_text": f.fix_text} for f in b_findings]
    a_data = [{"rule_id": f.rule_id, "status": f.status, "confidence": f.confidence, "rationale": f.rationale, "fix_text": f.fix_text} for f in a_findings]

    res = compare_audits(b_data, a_data, before_id=req.before_id, after_id=req.after_id)
    return res


@app.get("/api/audits/{audit_id}/cost")
async def get_audit_cost(
    audit_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return provider call count and estimated USD cost breakdown for an audit."""
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")
    return get_audit_cost_summary(session, audit_id)
