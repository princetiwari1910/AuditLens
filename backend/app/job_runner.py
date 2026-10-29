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


def replay_demo_audit(audit_id: str, session: Session) -> None:
    """
    Replay a recorded completed audit fixture with realistic timeline pacing.
    Used as an offline fallback when DEMO_REPLAY=1 or live AI APIs are unavailable.
    Guarantees the audit is explicitly flagged with is_replay=True.
    """
    settings = get_settings()
    audit = session.get(Audit, audit_id)
    if not audit:
        return

    audit.is_replay = True
    audit.status = AuditStatus.PROCESSING.value
    session.add(audit)
    session.commit()

    fixture_path = settings.DATA_DIR / "fixtures" / "demo_recording.json"
    if not fixture_path.exists():
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "demo_recording.json"

    if not fixture_path.exists():
        from scripts.record_demo import record_demo
        fixture_path = record_demo(template_id=audit.template_id or "fire_exit_safety")

    with open(fixture_path, "r", encoding="utf-8") as fp:
        fixture = json.load(fp)

    logger.info("replay_demo_audit: replaying audit %s from fixture %s", audit_id, fixture_path)

    # 1. Replay timeline events with pacing
    events = fixture.get("events", [])
    for ev in events:
        ev_copy = dict(ev)
        ev_copy["audit_id"] = audit_id
        ev_copy["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if "payload" in ev_copy and isinstance(ev_copy["payload"], dict):
            ev_copy["payload"]["is_replay"] = True
        event_manager.emit(ev_copy)
        time.sleep(0.08)

    # 2. Persist recorded findings
    from app.models import Finding
    from app.storage import get_overlays_dir
    overlays_dir = get_overlays_dir(audit_id)

    findings_data = fixture.get("findings", [])
    for fd in findings_data:
        finding_id = f"find_rec_{fd['rule_id']}_{audit_id[-6:]}"
        overlay_path = overlays_dir / f"overlay_{finding_id}.jpg"
        if not overlay_path.exists():
            from app.agent.runner import draw_overlay_image
            draw_overlay_image(
                base_frame_path="",
                output_path=overlay_path,
                finding={"status": fd["status"], "id": finding_id, "rationale": fd["rationale"]},
            )

        f_row = Finding(
            id=finding_id,
            audit_id=audit_id,
            rule_id=fd["rule_id"],
            status=fd["status"],
            confidence=fd["confidence"],
            timestamp_s=fd["timestamp_s"],
            frame_idx=fd["frame_idx"],
            overlay_path=str(overlay_path),
            measurement_json=fd.get("measurement_json"),
            rationale=fd.get("rationale", "") + " [Recorded run]",
            fix_text=fd.get("fix_text", ""),
            severity=fd.get("severity", "medium"),
            sources_json=fd.get("sources_json", '["segmentation"]'),
        )
        session.add(f_row)

    # 3. Populate cost accounting entries
    from app.costlog import log_cost
    log_cost(
        session,
        provider="segmentation",
        operation="segmentation",
        units=5.0,
        audit_id=audit_id,
        model_id=settings.MODEL_ID_SEGMENTATION,
        latency_ms=120,
        cache_hit=False,
    )
    log_cost(
        session,
        provider="agent",
        operation="agent_input",
        units=1.2,
        audit_id=audit_id,
        model_id=settings.MODEL_ID_AGENT,
        latency_ms=45,
        cache_hit=False,
    )

    audit.status = AuditStatus.COMPLETED.value
    audit.summary_json = json.dumps(fixture.get("summary", {}))
    audit.duration_s = fixture.get("duration_s", 25.0)
    session.add(audit)
    session.commit()

    event_manager.emit({
        "type": "audit_completed",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audit_id": audit_id,
        "payload": {
            "summary": fixture.get("summary", {}),
            "findings_count": len(findings_data),
            "is_replay": True,
        },
    })
    logger.info("replay_demo_audit: completed replaying audit %s", audit_id)


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

            if settings.DEMO_REPLAY or audit.is_replay:
                replay_demo_audit(audit_id, session)
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
