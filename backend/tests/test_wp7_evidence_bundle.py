"""Unit tests for WP7 Tamper-Evident Evidence Bundle and Verification Script."""

import io
import json
from pathlib import Path
import sys
import zipfile
import pytest
from starlette.testclient import TestClient
from sqlmodel import Session

# Add project root to sys.path so scripts can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.agent.trace import record_span
from app.config import get_settings
from app.db import engine, init_db, reset_engine
from app.main import app
from app.models import Audit, AuditLog, AuditStatus, Finding
from scripts.verify_bundle import verify_bundle


@pytest.fixture
def client_with_audit(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    s = get_settings()
    monkeypatch.setattr(s, "DATA_DIR", data_dir)
    reset_engine()
    init_db()

    client = TestClient(app)
    audit_id = "audit_bundle_test_01"

    # Setup audit directory with frames and overlays
    audit_dir = data_dir / "audits" / audit_id
    frames_dir = audit_dir / "frames"
    overlays_dir = audit_dir / "overlays"
    frames_dir.mkdir(parents=True)
    overlays_dir.mkdir(parents=True)

    # Write dummy frame and overlay
    (frames_dir / "frame_0000.jpg").write_bytes(b"dummy_frame_jpeg_bytes_00")
    (overlays_dir / "overlay_f_123.jpg").write_bytes(b"dummy_overlay_jpeg_bytes_123")

    with Session(engine()) as session:
        audit = Audit(
            id=audit_id,
            template_id="fire_exit_safety",
            status=AuditStatus.COMPLETED.value,
            summary_json=json.dumps({"score": 90, "pass": 1, "fail": 0, "unsure": 0}),
        )
        finding = Finding(
            id="f_123",
            audit_id=audit_id,
            rule_id="extinguisher_visible",
            status="pass",
            confidence=0.95,
            timestamp_s=1.5,
            frame_idx=0,
            severity="high",
            rationale="Extinguisher is clearly mounted.",
        )
        log_entry = AuditLog(
            audit_id=audit_id,
            finding_id="f_123",
            actor_label="Inspector",
            action="approve_ai",
            before="pass",
            after="pass",
            note="Verified via photographic evidence.",
        )
        session.add_all([audit, finding, log_entry])
        session.commit()

        record_span(
            session=session,
            audit_id=audit_id,
            stage="segmentation",
            model="SAM 3.1",
            concept="fire extinguisher",
            latency_ms=45,
            cost_usd=0.002,
        )

    return client, audit_id


def test_create_and_download_evidence_bundle(client_with_audit, tmp_path):
    """Verify GET /api/audits/{id}/bundle generates a cryptographically valid ZIP bundle."""
    client, audit_id = client_with_audit

    resp = client.get(f"/api/audits/{audit_id}/bundle")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"

    zip_bytes = resp.content
    bundle_path = tmp_path / "valid_bundle.zip"
    bundle_path.write_bytes(zip_bytes)

    # Verify using scripts/verify_bundle.py
    valid, message = verify_bundle(bundle_path)
    assert valid is True, f"Expected valid bundle, got: {message}"
    assert "Bundle verified successfully" in message
    assert "Legal Disclaimer" in message

    # Inspect zip contents
    with zipfile.ZipFile(bundle_path, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "report.json" in names
        assert "trace.json" in names
        assert "audit_log.json" in names
        assert "frames/frame_0000.jpg" in names
        assert "overlays/overlay_f_123.jpg" in names


def test_tampered_file_fails_verification(client_with_audit, tmp_path):
    """Tampering with any file in the bundle must cause verify_bundle to fail."""
    client, audit_id = client_with_audit

    resp = client.get(f"/api/audits/{audit_id}/bundle")
    original_zip = resp.content

    # Create a modified zip where report.json is altered
    tampered_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_zip), "r") as zin:
        with zipfile.ZipFile(tampered_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "report.json":
                    # Alter one character
                    data = data.replace(b"extinguisher_visible", b"tampered_rule_id___")
                zout.writestr(item, data)

    tampered_path = tmp_path / "tampered_bundle.zip"
    tampered_path.write_bytes(tampered_buffer.getvalue())

    valid, message = verify_bundle(tampered_path)
    assert valid is False
    assert "Checksum mismatch for 'report.json'" in message


def test_tampered_manifest_fails_verification(client_with_audit, tmp_path):
    """Modifying the manifest without valid root manifest_hash must fail verification."""
    client, audit_id = client_with_audit

    resp = client.get(f"/api/audits/{audit_id}/bundle")
    original_zip = resp.content

    tampered_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_zip), "r") as zin:
        with zipfile.ZipFile(tampered_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "manifest.json":
                    manifest_data = json.loads(data.decode("utf-8"))
                    # Forge a file hash inside manifest
                    manifest_data["files"]["report.json"] = "0" * 64
                    data = json.dumps(manifest_data).encode("utf-8")
                zout.writestr(item, data)

    tampered_manifest_path = tmp_path / "tampered_manifest.zip"
    tampered_manifest_path.write_bytes(tampered_buffer.getvalue())

    valid, message = verify_bundle(tampered_manifest_path)
    assert valid is False
    assert "Tampered manifest detected" in message


def test_bundle_404_for_missing_audit(client_with_audit):
    """GET /api/audits/{id}/bundle returns 404 for missing audit."""
    client, _ = client_with_audit
    resp = client.get("/api/audits/non_existent_audit_id/bundle")
    assert resp.status_code == 404
