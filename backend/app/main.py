"""AuditLens FastAPI application entry-point and complete REST + SSE API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
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
from app.config import get_settings
from app.costlog import get_audit_cost_summary
from app.db import get_session, init_db
from app.events import event_manager
from app.job_runner import run_audit_job_sync
from app.models import Audit, AuditStatus, Finding, Frame, VoiceNote
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
    template_id: str = "fire_exit_safety",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Launch a demo audit on data/sample_walkthrough.mp4 running the full real pipeline:
    stores the video in the audit folder, executes frame sampling, runs tool-based evaluation,
    generates OpenCV overlays, and streams live SSE timeline events to the processing page.
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown template: '{template_id}'")

    audit = Audit(
        template_id=template_id,
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
            "models": {
                "segmentation": a.model_segmentation,
                "agent": a.model_agent,
                "transcription": a.model_transcription,
            },
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
        ev_ledger = json.loads(getattr(f, "evidence_ledger_json", "[]")) if getattr(f, "evidence_ledger_json", None) else []
        strongest_ev = json.loads(getattr(f, "strongest_evidence_json", "null")) if getattr(f, "strongest_evidence_json", None) else None
        policy = getattr(f, "decision_policy", "default")
        detector_val = getattr(f, "detector", "sam")
        supp_cnt = getattr(f, "support_count", 1)
        stab_val = getattr(f, "stability", 1.0)
        esc_steps = json.loads(getattr(f, "escalation_steps_json", "[]")) if getattr(f, "escalation_steps_json", None) else []
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
                if transcript_text and f"[Auditor Note:" not in f.rationale:
                    f.rationale = f.rationale + f" [Auditor Note: \"{transcript_text}\"]"
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

