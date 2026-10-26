"""Command-line audit runner for AuditLens.

Runs an evidence-backed safety audit end-to-end on local video or photo walkthroughs,
emits real-time agent execution events to stdout, and displays a summary findings table
and estimated cost breakdown.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.config import get_settings
from app.costlog import get_audit_cost_summary
from app.db import engine, init_db
from app.events import event_manager
from app.job_runner import run_audit_job_sync
from app.models import Audit, Finding
from app.template_loader import get_template, list_templates
from scripts.make_sample_video import generate_sample_video


def print_cli_event(event: dict) -> None:
    e_type = event.get("type", "")
    p = event.get("payload", {})
    ts = event.get("ts", "")

    if e_type == "audit_started":
        print(f"\n🚀 [AUDIT STARTED] Rules: {p.get('rule_count')}, Frames: {p.get('frame_count')}")
    elif e_type == "frames_sampled":
        print(f"📸 [FRAMES SAMPLED] {p.get('frame_count')} frames captured at 1 fps")
    elif e_type == "tool_call":
        tool = p.get("tool", "")
        rule = p.get("rule_id", "audit")
        args = json.dumps(p.get("args_summary", {}))
        print(f"  ⚡ Tool Call   -> {tool:<20} (Rule: {rule:<22} Args: {args})")
    elif e_type == "tool_result":
        tool = p.get("tool", "")
        summary = p.get("result_summary", "")
        dur = p.get("duration_ms", 0)
        print(f"  ✅ Tool Result -> {tool:<20} {summary} [{dur}ms]")
    elif e_type == "finding_recorded":
        r_id = p.get("rule_id", "")
        stat = p.get("status", "").upper()
        conf = p.get("confidence", 0.0)
        t_s = p.get("timestamp_s", 0.0)
        badge = "🟢 PASS" if stat == "PASS" else ("🔴 FAIL" if stat == "FAIL" else "🟡 UNSURE")
        print(f"  📌 Finding Recorded: {badge} {r_id:<24} Conf: {conf:.0%} @ {t_s:04.1f}s")
    elif e_type == "audit_completed":
        print(f"\n🎉 [AUDIT COMPLETED] Score: {p.get('summary', {}).get('score', 0)}/100")
    elif e_type == "error":
        print(f"\n❌ [ERROR] {p.get('error')}")


def run_cli_audit(
    video_path: str,
    template_id: str = "fire_exit_safety",
    custom_rules: list[str] | None = None,
) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    v_path = Path(video_path)
    if not v_path.exists():
        if "sample_walkthrough.mp4" in str(video_path):
            print(f"Sample video '{video_path}' not found. Generating now...")
            generate_sample_video(v_path, duration_s=25)
        else:
            print(f"Error: video file '{video_path}' does not exist.")
            sys.exit(1)

    eng = engine()
    with Session(eng) as session:
        audit = Audit(
            template_id=template_id,
            custom_rules_json=json.dumps(custom_rules) if custom_rules else None,
            video_path=str(v_path.resolve()),
            status="queued",
        )
        session.add(audit)
        session.commit()
        session.refresh(audit)
        audit_id = audit.id

    # Subscribe stdout listener to events
    old_emit = event_manager.emit

    def logging_emit(evt: dict) -> None:
        old_emit(evt)
        print_cli_event(evt)

    event_manager.emit = logging_emit

    print("=" * 80)
    print(f"  AuditLens CLI Runner | Audit ID: {audit_id}")
    print(f"  Video: {v_path.name} | Checklist: {template_id}")
    print("=" * 80)

    t0 = time.time()
    run_audit_job_sync(audit_id)
    dur = round(time.time() - t0, 2)

    # Fetch completed audit data
    with Session(eng) as session:
        audit_row = session.get(Audit, audit_id)
        findings = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
        cost_summary = get_audit_cost_summary(session, audit_id)

    summary = json.loads(audit_row.summary_json) if audit_row.summary_json else {}

    # Print Findings Table
    print("\n" + "=" * 90)
    print(f"{'RULE ID':<26} | {'STATUS':<8} | {'CONF':<6} | {'TIME':<6} | {'MEASUREMENT':<16} | {'FIX'}")
    print("-" * 90)

    for f in findings:
        meas_txt = "-"
        if f.measurement_json:
            m = json.loads(f.measurement_json)
            meas_txt = f"{m.get('width_m', 0.0):.2f}m +/- {m.get('uncertainty_m', 0.0):.2f}m"

        fix_snippet = (f.fix_text[:28] + "...") if len(f.fix_text) > 30 else (f.fix_text or "-")
        stat_color = f.status.upper()
        print(f"{f.rule_id:<26} | {stat_color:<8} | {f.confidence:<6.0%} | {f.timestamp_s:<5.1f}s | {meas_txt:<16} | {fix_snippet}")

    print("=" * 90)

    # Print Summary & Cost
    print(f"\n📊 Compliance Summary:")
    print(f"   Safety Score:   {summary.get('score', 0)} / 100")
    print(f"   Pass:           {summary.get('pass', 0)}")
    print(f"   Fail:           {summary.get('fail', 0)}")
    print(f"   Unsure:         {summary.get('unsure', 0)}")
    print(f"   Duration:       {dur}s")

    print(f"\n💰 Estimated Provider Usage & Cost:")
    print(f"   Total Calls:    {cost_summary.get('total_calls', 0)}")
    print(f"   Total USD:      ${cost_summary.get('total_cost_usd', 0.0):.4f}")
    for prov, p_data in cost_summary.get("by_provider", {}).items():
        print(f"   - {prov:<16}: {p_data.get('calls')} calls ({p_data.get('units')} units) -> ${p_data.get('cost_usd', 0.0):.4f}")

    print("\n⚠️ Disclaimer:")
    print("   AuditLens is an assistive pre-audit tool. It does not certify legal compliance.")
    print("   Always verify against local regulations and a qualified inspector.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an AuditLens walkthrough safety audit.")
    parser.add_argument(
        "--video",
        "-v",
        default="./data/sample_walkthrough.mp4",
        help="Path to walkthrough video file",
    )
    parser.add_argument(
        "--template",
        "-t",
        default="fire_exit_safety",
        choices=["fire_exit_safety", "workshop_ppe"],
        help="Template checklist ID",
    )
    args = parser.parse_args()

    run_cli_audit(args.video, template_id=args.template)
