"""Background audit execution job runner."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
import traceback

from sqlmodel import Session, select

from app.agent.rules import parse_custom_rule
from app.agent.runner import AgentRunner
from app.config import get_settings
from app.db import engine
from app.events import event_manager
from app.frames import sample_frames_from_images, sample_frames_from_video
from app.models import Audit, AuditStatus, Frame, RuleModel
from app.providers import get_segmentation_provider, get_transcription_provider
from app.template_loader import get_template

logger = logging.getLogger("auditlens.job_runner")


def run_audit_job_sync(audit_id: str) -> None:
    """
    Synchronous entrypoint for background audit processing.
    Executes frame sampling, rule evaluation, overlay generation, and DB updates.
    Ensures comprehensive logging and guarantees a final event is emitted even on failure.
    """
    logger.info("run_audit_job_sync: starting background job for audit %s", audit_id)
    eng = engine()
    settings = get_settings()

    try:
        with Session(eng) as session:
            audit = session.get(Audit, audit_id)
            if not audit:
                logger.error("run_audit_job_sync: audit %s not found in database", audit_id)
                event_manager.emit({
                    "type": "error",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "audit_id": audit_id,
                    "payload": {"error": f"Audit {audit_id} not found in database"},
                })
                return

            if audit.status == AuditStatus.COMPLETED.value:
                logger.info("run_audit_job_sync: audit %s already completed; skipping", audit_id)
                return

            audit.status = AuditStatus.PROCESSING.value
            session.add(audit)
            session.commit()

            try:
                # 1. Sample Frames
                frames: list[Frame] = []
                if audit.video_path and Path(audit.video_path).exists():
                    logger.info("run_audit_job_sync: sampling frames from video %s", audit.video_path)
                    frames = sample_frames_from_video(
                        video_path=audit.video_path,
                        audit_id=audit_id,
                        fps=float(settings.FRAME_FPS),
                        session=session,
                    )
                else:
                    # Check for uploaded photos under audit dir
                    audit_dir = settings.DATA_DIR / "audits" / audit_id
                    images = sorted(list(audit_dir.glob("*.jpg")) + list(audit_dir.glob("*.png")))
                    if images:
                        logger.info("run_audit_job_sync: sampling frames from %d photos", len(images))
                        frames = sample_frames_from_images(images, audit_id=audit_id, session=session)

                if not frames:
                    raise ValueError("No video or image frames available to process for this audit.")

                logger.info("run_audit_job_sync: sampled %d frames for audit %s", len(frames), audit_id)

                # Convert frame rows to lightweight dictionary format for runner
                frames_dicts = [
                    {
                        "idx": f.idx,
                        "timestamp_s": f.timestamp_s,
                        "path": f.path,
                        "sha256": f.sha256,
                    }
                    for f in frames
                ]

                # 2. Prepare Rules
                rules: list[RuleModel] = []
                if audit.custom_rules_json:
                    custom_texts = json.loads(audit.custom_rules_json)
                    if isinstance(custom_texts, str):
                        custom_texts = [custom_texts]
                    for idx, text in enumerate(custom_texts, start=1):
                        rules.append(parse_custom_rule(text, rule_idx=idx))
                else:
                    tmpl = get_template(audit.template_id)
                    if not tmpl:
                        raise ValueError(f"Unknown template: '{audit.template_id}'")
                    rules = tmpl.rules

                logger.info("run_audit_job_sync: prepared %d rules for audit %s", len(rules), audit_id)

                # 3. Instantiate Runner and Providers
                seg_provider = get_segmentation_provider()
                asr_provider = get_transcription_provider()
                runner = AgentRunner(
                    segmentation_provider=seg_provider,
                    transcription_provider=asr_provider,
                )

                # 4. Run Audit
                runner.run_audit(
                    audit_id=audit_id,
                    rules=rules,
                    frames=frames_dicts,
                    emit=event_manager.emit,
                    session=session,
                )
                logger.info("run_audit_job_sync: audit %s completed successfully", audit_id)

            except Exception as exc:
                err_msg = str(exc)
                logger.exception("run_audit_job_sync: audit %s failed inside processing pipeline: %s", audit_id, err_msg)
                audit.status = AuditStatus.FAILED.value
                audit.error = err_msg
                session.add(audit)
                session.commit()
                event_manager.emit({
                    "type": "error",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "audit_id": audit_id,
                    "payload": {"error": err_msg, "traceback": traceback.format_exc()},
                })

    except Exception as top_exc:
        logger.exception("run_audit_job_sync: unhandled exception in audit %s: %s", audit_id, top_exc)
        event_manager.emit({
            "type": "error",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "audit_id": audit_id,
            "payload": {"error": str(top_exc), "traceback": traceback.format_exc()},
        })
