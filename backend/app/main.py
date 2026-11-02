"""AuditLens FastAPI application entry-point and complete REST + SSE API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import logging
from pathlib import Path
import secrets
import shutil
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
from app.agent.rules import compute_summary_score
from app.config import get_settings
from app.costlog import get_audit_cost_summary
from app.db import get_session, init_db
from app.events import event_manager
from app.job_runner import run_audit_job_sync
from app.models import Audit, AuditLog, AuditStatus, Finding, Frame, ShareToken, Site, VoiceNote
from app.providers import get_transcription_provider
from app.storage import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_UPLOAD_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    StorageValidationError,
    get_audio_dir,
    get_audit_dir,
    get_audit_video_path,
    get_frames_dir,
    get_overlays_dir,
    save_upload_file,
    validate_file_extension,
)
from app.template_loader import get_template, list_templates
from app.video_norm import inspect_and_normalize_video


logger = logging.getLogger("auditlens.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    settings.ensure_dirs()
    logger.info("AuditLens starting up. Resolved DATA_DIR: %s", settings.DATA_DIR.resolve())
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
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "Content-Type"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "provider_mode": settings.PROVIDER_MODE,
        "data_dir": str(settings.DATA_DIR.resolve()),
        "demo_replay": bool(settings.DEMO_REPLAY),
        "models": {
            "segmentation": settings.MODEL_ID_SEGMENTATION,
            "agent": settings.MODEL_ID_AGENT,
            "transcription": settings.MODEL_ID_TRANSCRIPTION,
        },
    }


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


class TemplateCompileRequest(BaseModel):
    text: str


@app.post("/api/templates/compile")
async def compile_template_endpoint(
    req: TemplateCompileRequest,
) -> dict[str, Any]:
    """
    Compile natural language checklist text into structured draft template JSON (WP12).
    Validates all concept prompts against SAM 3.1 rules (no conjunctions, negation, spatial words).
    Rejects violations with inline errors.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Checklist text cannot be empty.",
        )

    from app.concept_validation import validate_concept
    from app.providers.mock import MockReasoner

    reasoner = MockReasoner()
    draft = reasoner.compile_template(req.text)

    # Validate each rule's concepts
    errors: list[str] = []
    for rule in draft.get("rules", []):
        r_id = rule.get("id", "rule")
        for prompt in rule.get("sam_prompts", []):
            try:
                validate_concept(prompt, rule_id=r_id)
            except ValueError as ve:
                errors.append(str(ve))

    # Mark custom checklist as experimental and human-reviewed
    draft["status"] = "experimental"
    draft["human_reviewed"] = True

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Concept validation failed: SAM 3.1 prompts must be plain noun phrases only.",
                "errors": errors,
                "draft_template": draft,
            },
        )

    return {
        "template": draft,
        "valid": True,
        "errors": [],
    }


# ── Audits CRUD & Background Execution ────────────────────────────────────────

@app.get("/api/sample-video")
async def get_sample_video():
    """Serve the reference walkthrough video data/sample_walkthrough.mp4 with range-request support."""
    settings = get_settings()
    sample_path = settings.DATA_DIR / "sample_walkthrough.mp4"
    if not sample_path.exists() or sample_path.stat().st_size == 0:
        logger.info("Sample walkthrough video missing at %s; generating synthetic H.264 walkthrough video...", sample_path)
        try:
            from scripts.make_sample_video import generate_sample_video
            generate_sample_video(sample_path, duration_s=25)
        except Exception as exc:
            logger.exception("Failed to generate synthetic walkthrough video: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not generate sample walkthrough video: {str(exc)}",
            )

    return FileResponse(
        path=sample_path,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Type",
        },
    )


@app.post("/api/audits/demo", status_code=status.HTTP_201_CREATED)
async def create_demo_audit(
    background_tasks: BackgroundTasks,
    template_id: str = "campus_fire_exit_core",
    replay: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Launch a demo audit on data/sample_walkthrough.mp4 running the full real pipeline:
    stores the video in the audit folder, executes frame sampling, runs tool-based evaluation,
    generates OpenCV overlays, and streams live SSE timeline events to the processing page.
    If replay=True or DEMO_REPLAY=1, replays recorded fixtures with realistic event timing.
    """
    settings = get_settings()
    sample_path = settings.DATA_DIR / "sample_walkthrough.mp4"
    if not sample_path.exists() or sample_path.stat().st_size == 0:
        logger.info("Sample walkthrough video missing at %s; generating synthetic H.264 walkthrough video...", sample_path)
        try:
            from scripts.make_sample_video import generate_sample_video
            generate_sample_video(sample_path, duration_s=25)
        except Exception as exc:
            logger.exception("Failed to generate synthetic walkthrough video: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not generate sample walkthrough video: {str(exc)}",
            )

    tmpl = get_template(template_id)
    if not tmpl:
        # Fallback to campus_fire_exit_core if old template id passed
        tmpl = get_template("campus_fire_exit_core") or get_template("fire_exit_safety")
        if tmpl:
            template_id = tmpl.id
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown template: '{template_id}'")

    is_replay = bool(replay or settings.DEMO_REPLAY)
    audit = Audit(
        site_id="site_demo_building_a",
        template_id=template_id,
        status=AuditStatus.QUEUED.value,
        provider_mode="replay" if is_replay else settings.PROVIDER_MODE,
        model_segmentation=settings.MODEL_ID_SEGMENTATION,
        model_agent=settings.MODEL_ID_AGENT,
        model_transcription=settings.MODEL_ID_TRANSCRIPTION,
        is_replay=is_replay,
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)

    # Store a physical copy of the walkthrough video in the audit's own directory
    audit_dir = get_audit_dir(audit.id)
    dest_video = audit_dir / "walkthrough.mp4"
    shutil.copyfile(sample_path, dest_video)
    audit.video_path = str(dest_video.resolve())
    session.add(audit)
    session.commit()

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
    site_id: str | None = Form(default=None),
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
        site_id=site_id or "site_demo_building_a",
        template_id=template_id or "custom",
        custom_rules_json=custom_rules if custom_rules else None,
        status=AuditStatus.QUEUED.value,
        provider_mode=settings.PROVIDER_MODE,
        model_segmentation=settings.MODEL_ID_SEGMENTATION,
        model_agent=settings.MODEL_ID_AGENT,
        model_transcription=settings.MODEL_ID_TRANSCRIPTION,
        is_replay=bool(settings.DEMO_REPLAY),
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
            raw_upload_path = audit_dir / f"raw_upload{suffix}"
            await save_upload_file(video, raw_upload_path, allowed_extensions=ALLOWED_VIDEO_EXTENSIONS)

            dest_video = audit_dir / "walkthrough.mp4"
            inspect_and_normalize_video(raw_upload_path, dest_video)
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
            "site_id": a.site_id,
            "status": a.status,
            "template_id": a.template_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "duration_s": a.duration_s,
            "summary": summary,
            "error": a.error,
            "provider_mode": a.provider_mode,
            "model_segmentation": a.model_segmentation,
            "model_agent": a.model_agent,
            "model_transcription": a.model_transcription,
            "is_replay": a.is_replay,
            "source_provider_mode": a.source_provider_mode,
            "models": {
                "segmentation": a.model_segmentation,
                "agent": a.model_agent,
                "transcription": a.model_transcription,
            },
        })
    return results


@app.get("/api/audits/{audit_id}")
async def get_audit(
    audit_id: str,
    token: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    if token:
        th = hashlib.sha256(token.encode("utf-8")).hexdigest()
        st_row = session.exec(
            select(ShareToken).where(ShareToken.token_hash == th)
        ).first()
        if not st_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid share token")
        if st_row.audit_id != audit_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Share token is not authorized for this audit",
            )
        st_row.access_count += 1
        session.add(st_row)
        session.commit()

    findings = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
    summary = json.loads(audit.summary_json) if audit.summary_json else None

    findings_data = []
    for f in findings:
        meas = json.loads(f.measurement_json) if f.measurement_json else None
        sources = json.loads(f.sources_json) if f.sources_json else ["segmentation"]
        ev_ledger = json.loads(getattr(f, "evidence_ledger_json", "[]")) if getattr(f, "evidence_ledger_json", None) else []
        strongest_ev = json.loads(getattr(f, "strongest_evidence_json", "null")) if getattr(f, "strongest_evidence_json", None) else None
        policy = getattr(f, "decision_policy", "default")
        detector_val = getattr(f, "detector", "sam")
        supp_cnt = getattr(f, "support_count", 1)
        stab_val = getattr(f, "stability", 1.0)
        esc_steps = json.loads(getattr(f, "escalation_steps_json", "[]")) if getattr(f, "escalation_steps_json", None) else []
        ai_verd = getattr(f, "ai_verdict", f.status) or f.status
        final_verd = getattr(f, "final_verdict", f.status) or f.status
        findings_data.append({
            "id": f.id,
            "rule_id": f.rule_id,
            "status": final_verd,
            "ai_verdict": ai_verd,
            "final_verdict": final_verd,
            "confidence": f.confidence,
            "timestamp_s": f.timestamp_s,
            "frame_idx": f.frame_idx,
            "overlay_url": f"/api/audits/{audit_id}/overlays/{f.id}",
            "measurement": meas,
            "rationale": f.rationale,
            "fix_text": f.fix_text,
            "severity": f.severity,
            "sources": sources,
            "evidence_ledger": ev_ledger,
            "strongest_evidence": strongest_ev,
            "decision_policy": policy,
            "detector": detector_val,
            "support_count": supp_cnt,
            "stability": stab_val,
            "escalation_steps": esc_steps,
        })

    has_video = bool(
        (audit.video_path and Path(audit.video_path).exists())
        or get_audit_video_path(audit_id)
    )
    video_url = f"/api/audits/{audit.id}/video" if has_video else None

    return {
        "id": audit.id,
        "site_id": audit.site_id,
        "status": audit.status,
        "template_id": audit.template_id,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
        "duration_s": audit.duration_s,
        "video_url": video_url,
        "summary": summary,
        "findings": findings_data,
        "error": audit.error,
        "provider_mode": audit.provider_mode,
        "model_segmentation": audit.model_segmentation,
        "model_agent": audit.model_agent,
        "model_transcription": audit.model_transcription,
        "is_replay": audit.is_replay,
        "source_provider_mode": audit.source_provider_mode,
        "models": {
            "segmentation": audit.model_segmentation,
            "agent": audit.model_agent,
            "transcription": audit.model_transcription,
        },
    }


# ── Server-Sent Events (SSE) ──────────────────────────────────────────────────

@app.get("/api/audits/{audit_id}/events")
async def audit_events_stream(audit_id: str, session: Session = Depends(get_session)):
    """
    Server-Sent Events endpoint streaming real-time agent execution events.
    Replays past events from JSONL, then streams live events until terminal event.
    Supports HTTP keep-alive pings every 12s, proxy unbuffering, and guaranteed final events.
    """
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    async def event_generator():
        async for event in event_manager.subscribe(audit_id, session=session):
            yield {
                "event": "message",
                "data": json.dumps(event),
            }

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        ping=15,
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
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

        # Transcribe audio using Transcriber interface (returns clearly labeled stub in mock mode)
        transcript_text = None
        language = None
        try:
            transcriber = get_transcription_provider()
            trans = transcriber.transcribe(str(dest_audio))
            transcript_text = trans.text
            language = trans.language
        except Exception as exc:
            logger.warning("Voice note transcription failed: %s", exc)

        vn = VoiceNote(
            audit_id=audit_id,
            timestamp_s=timestamp_s,
            audio_path=str(dest_audio),
            transcript=transcript_text,
            language=language,
        )
        session.add(vn)
        session.commit()
        session.refresh(vn)

        # If findings exist, attach transcript to findings near this timestamp (within 5 seconds)
        findings = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
        for f in findings:
            if abs(f.timestamp_s - timestamp_s) <= 5.0:
                sources = json.loads(f.sources_json) if f.sources_json else []
                if "voice_note" not in sources:
                    sources.append("voice_note")
                    f.sources_json = json.dumps(sources)
                if transcript_text and "[Auditor Note:" not in f.rationale:
                    try:
                        from app.providers.mock import MockReasoner
                        structured = MockReasoner().extract_note(transcript_text)
                        tag = f"Auditor Note: ({structured['location']}, {structured['severity_hint']})"
                    except Exception:
                        tag = "Auditor Note:"
                    f.rationale = f.rationale + f" [{tag} \"{transcript_text}\"]"
                session.add(f)
        if findings:
            session.commit()

        return {
            "id": vn.id,
            "audit_id": audit_id,
            "timestamp_s": vn.timestamp_s,
            "audio_path": vn.audio_path,
            "transcript": vn.transcript,
            "language": vn.language,
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


@app.get("/api/audits/{audit_id}/video")
async def get_audit_video(
    audit_id: str,
    session: Session = Depends(get_session),
):
    """
    Serve the audit's walkthrough video with HTTP Range request support (206 Partial Content).
    Enables video player playback, scrubbing, and bounding box synchronization.
    """
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit '{audit_id}' not found",
        )

    video_path: Path | None = None
    if audit.video_path and Path(audit.video_path).exists():
        video_path = Path(audit.video_path)
    else:
        video_path = get_audit_video_path(audit_id)

    if not video_path or not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Walkthrough video for audit '{audit_id}' not found",
        )

    ext = video_path.suffix.lower()
    media_type = "video/mp4"
    if ext == ".webm":
        media_type = "video/webm"
    elif ext == ".mov":
        media_type = "video/quicktime"

    return FileResponse(
        path=video_path,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length, Content-Type",
        },
    )


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


# ── Evaluation Results & Needs Review Calibration ─────────────────────────────

@app.get("/api/eval/latest")
async def get_latest_eval():
    """
    Return the latest benchmark evaluation results, confusion matrices,
    reliability calibration curve, and failure cases.
    """
    import os
    from app.config import PROJECT_ROOT, get_settings

    settings = get_settings()

    # Search candidates: EVAL_OUTPUT_DIR -> settings.DATA_DIR -> PROJECT_ROOT / "eval"
    candidates = []
    eval_out_env = os.environ.get("EVAL_OUTPUT_DIR")
    if eval_out_env:
        candidates.append(Path(eval_out_env) / "latest_eval.json")
    candidates.append(settings.DATA_DIR / "latest_eval.json")
    candidates.append(PROJECT_ROOT / "eval" / "latest_eval.json")

    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)

    # If none exist, auto-generate into isolated non-tracked directory (never tracked repo)
    try:
        from eval.run_eval import run_evaluation
        target_dir = Path(eval_out_env) if eval_out_env else settings.DATA_DIR
        run_evaluation(allow_mock=True, output_dir=target_dir)
        gen_path = target_dir / "latest_eval.json"
        if gen_path.exists():
            with open(gen_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Could not auto-generate evaluation: %s", exc)

    return {
        "status": "empty",
        "message": "No evaluation run recorded yet. Execute 'make eval' to generate benchmark.",
    }


# ── Human Review Queue & Append-Only Audit Log (WP5) ──────────────────────────

class FindingReviewRequest(BaseModel):
    action: str  # "approve_ai" | "override_pass" | "override_fail"
    actor_label: str = "reviewer"
    note: str


@app.post("/api/audits/{audit_id}/findings/{finding_id}/review")
async def review_finding(
    audit_id: str,
    finding_id: str,
    req: FindingReviewRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if req.action not in ("approve_ai", "override_pass", "override_fail"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid review action '{req.action}'. Expected 'approve_ai', 'override_pass', or 'override_fail'."
        )
    if not req.note or not req.note.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A non-empty review note is required."
        )

    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    finding = session.exec(
        select(Finding).where(Finding.id == finding_id, Finding.audit_id == audit_id)
    ).first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Finding '{finding_id}' not found")

    before = getattr(finding, "final_verdict", None) or finding.status
    if req.action == "approve_ai":
        after = getattr(finding, "ai_verdict", None) or finding.status
    elif req.action == "override_pass":
        after = "pass"
    elif req.action == "override_fail":
        after = "fail"
    else:
        after = before

    finding.final_verdict = after
    finding.status = after
    session.add(finding)

    log_entry = AuditLog(
        audit_id=audit_id,
        finding_id=finding_id,
        actor_label=req.actor_label,
        action=req.action,
        before=before,
        after=after,
        note=req.note.strip(),
    )
    session.add(log_entry)

    # Recalculate summary & score with final verdicts
    all_findings = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
    findings_dicts = [
        {
            "id": f.id,
            "rule_id": f.rule_id,
            "status": getattr(f, "final_verdict", f.status) or f.status,
            "severity": f.severity,
            "confidence": f.confidence,
        }
        for f in all_findings
    ]
    new_summary = compute_summary_score(findings_dicts)
    if audit.summary_json:
        try:
            old_summary = json.loads(audit.summary_json)
            new_summary["frames_analyzed"] = old_summary.get("frames_analyzed", 0)
            new_summary["frames_considered"] = old_summary.get("frames_considered", 0)
        except Exception:
            pass
    audit.summary_json = json.dumps(new_summary)
    # Regenerate fix plan with updated verdicts (WP10)
    try:
        from app.providers.mock import MockReasoner
        refreshed_plan = MockReasoner().plan_fixes(findings_dicts)
        audit.fix_plan_json = json.dumps(refreshed_plan)
    except Exception:
        pass

    session.add(audit)
    session.commit()
    session.refresh(finding)
    session.refresh(log_entry)

    return {
        "finding_id": finding.id,
        "ai_verdict": finding.ai_verdict,
        "final_verdict": finding.final_verdict,
        "status": finding.status,
        "audit_log": {
            "id": log_entry.id,
            "audit_id": log_entry.audit_id,
            "finding_id": log_entry.finding_id,
            "actor_label": log_entry.actor_label,
            "action": log_entry.action,
            "before": log_entry.before,
            "after": log_entry.after,
            "note": log_entry.note,
            "ts": log_entry.ts.isoformat(),
        },
        "summary": new_summary,
    }


@app.get("/api/audits/{audit_id}/audit_log")
async def get_audit_log(
    audit_id: str,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")
    logs = session.exec(
        select(AuditLog).where(AuditLog.audit_id == audit_id).order_by(AuditLog.ts.asc())
    ).all()
    return [
        {
            "id": l.id,
            "audit_id": l.audit_id,
            "finding_id": l.finding_id,
            "actor_label": l.actor_label,
            "action": l.action,
            "before": l.before,
            "after": l.after,
            "note": l.note,
            "ts": l.ts.isoformat(),
        }
        for l in logs
    ]


# ── Trace and Observability Spans (WP6) ───────────────────────────────────────

@app.get("/api/audits/{audit_id}/trace")
async def get_audit_trace_endpoint(
    audit_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Retrieve detailed execution trace spans, latency, cost, and tool savings."""
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")
    summary = json.loads(audit.summary_json) if audit.summary_json else {}
    from app.agent.trace import get_audit_trace
    return get_audit_trace(session, audit_id, summary=summary)


# ── Tamper-Evident Evidence Bundle (WP7) ──────────────────────────────────────

@app.get("/api/audits/{audit_id}/bundle")
async def get_audit_evidence_bundle_endpoint(
    audit_id: str,
    session: Session = Depends(get_session),
):
    """Generate and download a cryptographically verifiable ZIP evidence bundle."""
    settings = get_settings()
    if not getattr(settings, "ENABLE_EVIDENCE_BUNDLE", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence bundle export is currently disabled.",
        )

    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    from app.agent.bundle import create_evidence_bundle_zip
    try:
        bundle_bytes = create_evidence_bundle_zip(session, audit_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create bundle: {exc}")

    filename = f"auditlens_{audit_id}_bundle.zip"
    return Response(
        content=bundle_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Fix Plan Generation (WP10) ────────────────────────────────────────────────

@app.get("/api/audits/{audit_id}/fix_plan")
async def get_audit_fix_plan(
    audit_id: str,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Retrieve prioritized corrective action fix plan grounded in audit findings."""
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    if audit.fix_plan_json:
        try:
            return json.loads(audit.fix_plan_json)
        except Exception:
            pass

    # Generate on-demand if not precomputed
    findings_db = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
    findings_dicts = [
        {
            "id": f.id,
            "rule_id": f.rule_id,
            "status": getattr(f, "final_verdict", f.status) or f.status,
            "severity": f.severity,
            "rationale": f.rationale,
            "fix_text": f.fix_text,
        }
        for f in findings_db
    ]

    from app.providers.mock import MockReasoner
    reasoner = MockReasoner()
    fix_plan = reasoner.plan_fixes(findings_dicts)
    audit.fix_plan_json = json.dumps(fix_plan)
    session.add(audit)
    session.commit()
    return fix_plan


# ── Sites and Multi-Audit Trend History (WP11) ────────────────────────────────

@app.get("/api/sites")
async def list_sites(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """List all registered sites with audit counts and latest safety scores."""
    sites = session.exec(select(Site).order_by(Site.name.asc())).all()
    results = []
    for s in sites:
        audits = session.exec(
            select(Audit).where(Audit.site_id == s.id).order_by(desc(Audit.created_at))
        ).all()
        latest_audit = audits[0] if audits else None
        latest_score = None
        if latest_audit and latest_audit.summary_json:
            try:
                latest_score = json.loads(latest_audit.summary_json).get("score")
            except Exception:
                pass
        results.append({
            "id": s.id,
            "name": s.name,
            "location_label": s.location_label,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "audit_count": len(audits),
            "latest_score": latest_score,
            "latest_audit_id": latest_audit.id if latest_audit else None,
        })
    return results


@app.get("/api/sites/{site_id}/audits")
async def list_site_audits(
    site_id: str,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Retrieve all historical audits conducted at a specific site."""
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site '{site_id}' not found")

    audits = session.exec(
        select(Audit).where(Audit.site_id == site_id).order_by(desc(Audit.created_at))
    ).all()
    results = []
    for a in audits:
        summary = json.loads(a.summary_json) if a.summary_json else None
        results.append({
            "id": a.id,
            "site_id": a.site_id,
            "status": a.status,
            "template_id": a.template_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "duration_s": a.duration_s,
            "summary": summary,
            "provider_mode": a.provider_mode,
            "is_replay": a.is_replay,
        })
    return results


@app.get("/api/sites/{site_id}/trends")
async def get_site_trends(
    site_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Retrieve longitudinal multi-audit trends: score progression, open issues, recurring issues, and resolved issues."""
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site '{site_id}' not found")

    # Chronological audits for score trend
    audits = session.exec(
        select(Audit).where(Audit.site_id == site_id)
        .order_by(Audit.created_at.asc())
    ).all()

    score_trend = []
    for a in audits:
        summ = json.loads(a.summary_json) if a.summary_json else {}
        score_trend.append({
            "audit_id": a.id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "score": summ.get("score", 0),
            "pass_count": summ.get("pass_count", 0),
            "fail_count": summ.get("fail_count", 0),
            "unsure_count": summ.get("unsure_count", 0),
        })

    audit_ids = [a.id for a in audits]
    audit_findings: dict[str, list[Finding]] = {}
    if audit_ids:
        all_findings = session.exec(
            select(Finding).where(Finding.audit_id.in_(audit_ids))
        ).all()
        for f in all_findings:
            audit_findings.setdefault(f.audit_id, []).append(f)

    # 1. Open deficiencies: from latest audit where verdict is non-pass ('fail' or 'needs_review' or 'unsure')
    open_issues = []
    latest_audit = audits[-1] if audits else None
    if latest_audit:
        for f in audit_findings.get(latest_audit.id, []):
            st = getattr(f, "final_verdict", f.status) or f.status
            if st != "pass":
                open_issues.append({
                    "finding_id": f.id,
                    "rule_id": f.rule_id,
                    "status": st,
                    "severity": f.severity,
                    "rationale": f.rationale,
                    "fix_text": f.fix_text,
                })

    # 2. Recurring issues: rules that failed across >= 2 separate audits
    fail_counts_by_rule: dict[str, int] = {}
    for a in audits:
        failed_rules_in_audit = set()
        for f in audit_findings.get(a.id, []):
            st = getattr(f, "final_verdict", f.status) or f.status
            if st == "fail":
                failed_rules_in_audit.add(f.rule_id)
        for r_id in failed_rules_in_audit:
            fail_counts_by_rule[r_id] = fail_counts_by_rule.get(r_id, 0) + 1

    recurring_issues = [
        {"rule_id": r_id, "fail_occurrences": cnt}
        for r_id, cnt in fail_counts_by_rule.items()
        if cnt >= 2
    ]

    # 3. Resolved issues: rules that failed in an earlier audit and passed in a subsequent audit
    resolved_issues = []
    all_rules_seen = set()
    for f_list in audit_findings.values():
        for f in f_list:
            all_rules_seen.add(f.rule_id)

    for r_id in all_rules_seen:
        earlier_failed = False
        subsequent_passed = False
        for a in audits:
            r_findings = [f for f in audit_findings.get(a.id, []) if f.rule_id == r_id]
            if not r_findings:
                continue
            st = getattr(r_findings[0], "final_verdict", r_findings[0].status) or r_findings[0].status
            if st == "fail":
                earlier_failed = True
            elif st == "pass" and earlier_failed:
                subsequent_passed = True

        if earlier_failed and subsequent_passed:
            resolved_issues.append({
                "rule_id": r_id,
                "status": "resolved",
                "note": "Previously failed in earlier inspection, passed in subsequent walkthrough.",
            })

    trend_notice = None
    if len(audits) < 2:
        recurring_issues = []
        resolved_issues = []
        trend_notice = "Trends need at least 2 audits"

    return {
        "site": {
            "id": site.id,
            "name": site.name,
            "location_label": site.location_label,
            "created_at": site.created_at.isoformat() if site.created_at else None,
        },
        "score_trend": score_trend,
        "open_issues": open_issues,
        "recurring_issues": recurring_issues,
        "resolved_issues": resolved_issues,
        "trend_notice": trend_notice,
    }


# ── Shareable Read-Only Links (WP14) ──────────────────────────────────────────

@app.post("/api/audits/{audit_id}/share")
async def create_share_link(
    audit_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Generate a cryptographically secure, read-only share token link."""
    audit = session.get(Audit, audit_id)
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit '{audit_id}' not found")

    raw_token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    st = ShareToken(audit_id=audit_id, token_hash=token_hash)
    session.add(st)
    session.commit()
    session.refresh(st)

    return {
        "token": raw_token,
        "share_url": f"/share/{raw_token}",
        "created_at": st.created_at.isoformat(),
    }


@app.get("/api/share/{token}")
async def get_shared_audit(
    token: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Resolve a share token to its audit."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    st = session.exec(select(ShareToken).where(ShareToken.token_hash == token_hash)).first()
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired share token")

    st.access_count += 1
    session.add(st)
    session.commit()

    return await get_audit(st.audit_id, token=None, session=session)







