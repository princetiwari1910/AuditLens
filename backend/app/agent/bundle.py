"""Tamper-evident evidence bundle creation and packaging (WP7)."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import time
from typing import Any
import zipfile

from sqlmodel import Session, select

from app.agent.trace import get_audit_trace
from app.config import get_settings
from app.models import Audit, AuditLog, Finding
from app.storage import get_audit_dir, get_frames_dir, get_overlays_dir


DISCLAIMER_TEXT = (
    "AuditLens is an assistive pre-audit inspection tool. This tamper-evident bundle "
    "cryptographically records AI perception, tool outputs, and human reviews. "
    "It does NOT certify legal, statutory, or regulatory compliance."
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_evidence_bundle_zip(session: Session, audit_id: str) -> bytes:
    """
    Create a cryptographically verifiable ZIP archive of the audit:
    - report.json
    - trace.json
    - audit_log.json
    - frames/ (redacted)
    - overlays/
    - manifest.json with SHA-256 digests of all bundled files
    """
    audit = session.get(Audit, audit_id)
    if not audit:
        raise ValueError(f"Audit '{audit_id}' not found")

    # 1. Fetch Findings & Summary
    findings = session.exec(select(Finding).where(Finding.audit_id == audit_id)).all()
    summary = json.loads(audit.summary_json) if audit.summary_json else {}

    findings_data = []
    for f in findings:
        meas = json.loads(f.measurement_json) if f.measurement_json else None
        sources = json.loads(f.sources_json) if f.sources_json else ["segmentation"]
        ev_ledger = json.loads(getattr(f, "evidence_ledger_json", "[]")) if getattr(f, "evidence_ledger_json", None) else []
        strongest_ev = json.loads(getattr(f, "strongest_evidence_json", "null")) if getattr(f, "strongest_evidence_json", None) else None
        esc_steps = json.loads(getattr(f, "escalation_steps_json", "[]")) if getattr(f, "escalation_steps_json", None) else []
        findings_data.append({
            "id": f.id,
            "rule_id": f.rule_id,
            "status": getattr(f, "final_verdict", f.status) or f.status,
            "ai_verdict": getattr(f, "ai_verdict", f.status) or f.status,
            "final_verdict": getattr(f, "final_verdict", f.status) or f.status,
            "confidence": f.confidence,
            "timestamp_s": f.timestamp_s,
            "frame_idx": f.frame_idx,
            "measurement": meas,
            "rationale": f.rationale,
            "fix_text": f.fix_text,
            "severity": f.severity,
            "sources": sources,
            "evidence_ledger": ev_ledger,
            "strongest_evidence": strongest_ev,
            "decision_policy": getattr(f, "decision_policy", "default"),
            "detector": getattr(f, "detector", "sam"),
            "support_count": getattr(f, "support_count", 1),
            "stability": getattr(f, "stability", 1.0),
            "escalation_steps": esc_steps,
        })

    report_payload = {
        "id": audit.id,
        "template_id": audit.template_id,
        "status": audit.status,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
        "duration_s": audit.duration_s,
        "provider_mode": audit.provider_mode,
        "model_segmentation": audit.model_segmentation,
        "model_agent": audit.model_agent,
        "model_transcription": audit.model_transcription,
        "is_replay": audit.is_replay,
        "disclaimer": DISCLAIMER_TEXT,
        "summary": summary,
        "findings": findings_data,
    }

    report_bytes = json.dumps(report_payload, indent=2, sort_keys=True).encode("utf-8")

    # 2. Fetch Trace Spans
    trace_payload = get_audit_trace(session, audit_id, summary=summary)
    trace_bytes = json.dumps(trace_payload, indent=2, sort_keys=True).encode("utf-8")

    # 3. Fetch Audit Log
    logs = session.exec(select(AuditLog).where(AuditLog.audit_id == audit_id).order_by(AuditLog.ts.asc())).all()
    audit_log_payload = [
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
    audit_log_bytes = json.dumps(audit_log_payload, indent=2, sort_keys=True).encode("utf-8")

    # Collect files and calculate hashes
    file_entries: dict[str, bytes] = {
        "report.json": report_bytes,
        "trace.json": trace_bytes,
        "audit_log.json": audit_log_bytes,
    }

    # 4. Collect Frame files
    frames_dir = get_frames_dir(audit_id)
    if frames_dir.exists():
        for frame_file in sorted(frames_dir.glob("*.jpg")):
            file_entries[f"frames/{frame_file.name}"] = frame_file.read_bytes()

    # 5. Collect Overlay files
    overlays_dir = get_overlays_dir(audit_id)
    if overlays_dir.exists():
        for ov_file in sorted(overlays_dir.glob("*.jpg")):
            file_entries[f"overlays/{ov_file.name}"] = ov_file.read_bytes()

    # 6. Build Manifest with SHA-256 for each file
    file_hashes: dict[str, str] = {
        name: _sha256_bytes(content) for name, content in file_entries.items()
    }

    canonical_hashes_str = json.dumps(file_hashes, sort_keys=True)
    manifest_hash = hashlib.sha256(canonical_hashes_str.encode("utf-8")).hexdigest()

    manifest_payload = {
        "audit_id": audit_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "disclaimer": DISCLAIMER_TEXT,
        "manifest_hash": manifest_hash,
        "file_count": len(file_hashes),
        "files": file_hashes,
    }
    manifest_bytes = json.dumps(manifest_payload, indent=2, sort_keys=True).encode("utf-8")
    file_entries["manifest.json"] = manifest_bytes

    # 7. Write in-memory ZIP archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in file_entries.items():
            zf.writestr(filename, data)

    return zip_buffer.getvalue()
