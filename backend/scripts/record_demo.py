#!/usr/bin/env python3
"""Record a completed demo audit as a fixture for offline replay testing and offline demos."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import sys
import time

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session, select
from app.config import get_settings
from app.db import engine, init_db
from app.models import Audit, AuditStatus, Finding, Frame
from app.storage import get_audit_dir
from app.template_loader import get_template
from app.frames import sample_frames_from_video
from app.providers import get_segmentation_provider, get_transcription_provider
from app.agent.runner import AgentRunner
from app.costlog import get_audit_cost_summary
from scripts.make_sample_video import generate_sample_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("record_demo")


def record_demo(template_id: str = "fire_exit_safety") -> Path:
    """Execute a full audit run, capturing all timeline events, findings, and costs to a JSON fixture."""
    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    # Ensure synthetic sample video exists
    sample_path = settings.DATA_DIR / "sample_walkthrough.mp4"
    if not sample_path.exists() or sample_path.stat().st_size == 0:
        logger.info("Generating synthetic walkthrough video at %s...", sample_path)
        generate_sample_video(sample_path, duration_s=25)

    eng = engine()
    recorded_events: list[dict] = []

    def capturing_emit(event: dict) -> None:
        recorded_events.append(event)

    audit_id = f"demo_rec_{int(time.time())}"
    logger.info("Starting demo recording run with ID %s...", audit_id)

    with Session(eng) as session:
        audit = Audit(
            id=audit_id,
            template_id=template_id,
            status=AuditStatus.PROCESSING.value,
            provider_mode=settings.PROVIDER_MODE,
            model_segmentation=settings.MODEL_ID_SEGMENTATION,
            model_agent=settings.MODEL_ID_AGENT,
            model_transcription=settings.MODEL_ID_TRANSCRIPTION,
            is_replay=False,
        )
        session.add(audit)
        session.commit()

        audit_dir = get_audit_dir(audit_id)
        dest_video = audit_dir / "walkthrough.mp4"
        shutil.copyfile(sample_path, dest_video)
        audit.video_path = str(dest_video.resolve())
        session.add(audit)
        session.commit()

        # 1. Sample Frames
        frames: list[Frame] = sample_frames_from_video(
            video_path=audit.video_path,
            audit_id=audit_id,
            fps=float(settings.FRAME_FPS),
            session=session,
        )

        frames_dicts = [
            {
                "idx": f.idx,
                "timestamp_s": f.timestamp_s,
                "path": f.path,
                "sha256": f.sha256,
            }
            for f in frames
        ]

        # 2. Rules
        tmpl = get_template(template_id)
        if not tmpl:
            raise ValueError(f"Template {template_id} not found")
        rules = tmpl.rules

        # 3. Runner
        seg_provider = get_segmentation_provider()
        asr_provider = get_transcription_provider()
        runner = AgentRunner(
            segmentation_provider=seg_provider,
            transcription_provider=asr_provider,
        )

        findings_res = runner.run_audit(
            audit_id=audit_id,
            rules=rules,
            frames=frames_dicts,
            emit=capturing_emit,
            session=session,
        )

        findings_rows = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
        cost_summary = get_audit_cost_summary(session, audit_id)

        findings_data = []
        for f in findings_rows:
            findings_data.append({
                "rule_id": f.rule_id,
                "status": f.status,
                "confidence": f.confidence,
                "timestamp_s": f.timestamp_s,
                "frame_idx": f.frame_idx,
                "measurement_json": f.measurement_json,
                "rationale": f.rationale,
                "fix_text": f.fix_text,
                "severity": f.severity,
                "sources_json": f.sources_json,
            })

        session.refresh(audit)
        summary = json.loads(audit.summary_json) if audit.summary_json else {}

    fixture_payload = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "template_id": template_id,
        "duration_s": audit.duration_s or 25.0,
        "summary": summary,
        "events": recorded_events,
        "findings": findings_data,
        "cost_summary": cost_summary,
    }

    # Save to data/fixtures/demo_recording.json and app/fixtures/demo_recording.json
    data_fixtures_dir = settings.DATA_DIR / "fixtures"
    data_fixtures_dir.mkdir(parents=True, exist_ok=True)
    out_fixture_path = data_fixtures_dir / "demo_recording.json"
    with open(out_fixture_path, "w", encoding="utf-8") as fp:
        json.dump(fixture_payload, fp, indent=2)

    app_fixtures_dir = BACKEND_DIR / "app" / "fixtures"
    app_fixtures_dir.mkdir(parents=True, exist_ok=True)
    bundled_fixture_path = app_fixtures_dir / "demo_recording.json"
    with open(bundled_fixture_path, "w", encoding="utf-8") as fp:
        json.dump(fixture_payload, fp, indent=2)

    logger.info("Successfully recorded demo fixtures to %s and %s (%d events, %d findings)",
                out_fixture_path, bundled_fixture_path, len(recorded_events), len(findings_data))
    return out_fixture_path


if __name__ == "__main__":
    out = record_demo()
    print(f"Recorded fixture saved: {out}")
