"""Tests for video storage, HTTP range streaming, and demo audit pipeline execution."""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_engine
from app.main import app
from app.models import Audit, AuditStatus
from app.storage import get_audit_dir, get_audit_video_path


@pytest.fixture
def client_with_demo_video(tmp_path, monkeypatch):
    """Set up a test environment with a synthesized walkthrough video."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine()

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    # Pre-generate sample video covering secondary exit window (>16s)
    from scripts.make_sample_video import generate_sample_video
    sample_path = settings.DATA_DIR / "sample_walkthrough.mp4"
    generate_sample_video(sample_path, duration_s=20, fps=25)

    client = TestClient(app)
    yield client, sample_path

    reset_engine()
    get_settings.cache_clear()


def test_sample_video_endpoint(client_with_demo_video):
    """Verify GET /api/sample-video serves the sample video with HTTP range support."""
    client, sample_path = client_with_demo_video

    # Full request
    resp = client.get("/api/sample-video")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.headers.get("accept-ranges") == "bytes"
    total_len = len(resp.content)
    assert total_len > 0

    # Range request
    range_resp = client.get("/api/sample-video", headers={"Range": "bytes=0-99"})
    assert range_resp.status_code == 206
    assert range_resp.headers.get("content-range") == f"bytes 0-99/{total_len}"
    assert len(range_resp.content) == 100


def test_demo_audit_stores_video_and_produces_unsure(client_with_demo_video):
    """
    Verify POST /api/audits/demo:
    1. Stores a copy of walkthrough.mp4 in the audit's own directory.
    2. Runs the real pipeline and reaches 'completed' status.
    3. Produces at least one finding marked 'unsure' (Needs Review).
    4. Provides a valid video_url in GET /api/audits/{id}.
    5. Serves the stored video with HTTP 206 range-request support.
    """
    client, sample_path = client_with_demo_video

    # 1. Launch Demo Audit
    demo_resp = client.post("/api/audits/demo?template_id=fire_exit_safety")
    assert demo_resp.status_code == 201
    audit_id = demo_resp.json()["id"]
    assert audit_id

    # 2. Confirm video file is physically stored in the audit directory
    audit_dir = get_audit_dir(audit_id)
    stored_video = audit_dir / "walkthrough.mp4"
    assert stored_video.exists(), f"Expected walkthrough.mp4 to be stored at {stored_video}"
    assert stored_video.stat().st_size == sample_path.stat().st_size

    # Check storage helper
    detected_path = get_audit_video_path(audit_id)
    assert detected_path is not None
    assert detected_path.resolve() == stored_video.resolve()

    # 3. GET /api/audits/{id} - Check completion and video_url
    detail_resp = client.get(f"/api/audits/{audit_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["status"] == "completed"
    assert data["video_url"] == f"/api/audits/{audit_id}/video"

    # 4. Check findings: MUST have at least one 'unsure' finding
    findings = data["findings"]
    assert len(findings) == 5

    statuses = [f["status"] for f in findings]
    assert "unsure" in statuses, f"Expected at least one 'unsure' finding in demo audit, got: {statuses}"
    assert "pass" in statuses, f"Expected 'pass' in findings, got: {statuses}"
    assert "fail" in statuses, f"Expected 'fail' in findings, got: {statuses}"

    # Verify summary counts match
    summary = data["summary"]
    assert summary["unsure"] >= 1
    assert summary["pass"] >= 1
    assert summary["fail"] >= 1

    # 5. GET /api/audits/{id}/video - Full response
    vid_resp = client.get(f"/api/audits/{audit_id}/video")
    assert vid_resp.status_code == 200
    assert vid_resp.headers["content-type"] == "video/mp4"
    assert vid_resp.headers.get("accept-ranges") == "bytes"
    total_bytes = len(vid_resp.content)
    assert total_bytes == stored_video.stat().st_size

    # 6. GET /api/audits/{id}/video - Range request (seeking / scrubbing)
    seek_resp = client.get(
        f"/api/audits/{audit_id}/video",
        headers={"Range": "bytes=100-299"},
    )
    assert seek_resp.status_code == 206
    assert seek_resp.headers.get("content-range") == f"bytes 100-299/{total_bytes}"
    assert len(seek_resp.content) == 200


def test_video_endpoint_not_found(client_with_demo_video):
    """Verify GET /api/audits/{id}/video returns 404 for nonexistent audit."""
    client, _ = client_with_demo_video
    resp = client.get("/api/audits/nonexistent_audit_id/video")
    assert resp.status_code == 404
