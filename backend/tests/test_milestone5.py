"""Tests for Milestone 5: FastAPI REST API, SSE event stream, uploads, compare, and cost."""

import io
import json
import time
from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session

from app.config import get_settings
from app.db import engine, init_db, reset_engine
from app.job_runner import run_audit_job_sync
from app.main import app
from app.models import Audit, Finding
from scripts.make_sample_video import generate_sample_video


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def test_templates_endpoints():
    """Verify GET /api/templates and GET /api/templates/{id}."""
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 2
    ids = [t["id"] for t in templates]
    assert "fire_exit_safety" in ids

    # Detail
    fire_resp = client.get("/api/templates/fire_exit_safety")
    assert fire_resp.status_code == 200
    assert fire_resp.json()["id"] == "fire_exit_safety"
    assert len(fire_resp.json()["rules"]) == 5

    # 404 for unknown template
    missing_resp = client.get("/api/templates/nonexistent_template")
    assert missing_resp.status_code == 404


def test_audit_upload_validation_bad_type(tmp_path):
    """Verify uploading an unsupported file format is rejected with 400."""
    fake_script = io.BytesIO(b"echo 'malicious script'")
    resp = client.post(
        "/api/audits",
        data={"template_id": "fire_exit_safety"},
        files={"video": ("exploit.sh", fake_script, "text/plain")},
    )
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]


def test_audit_upload_validation_unknown_template():
    """Verify unknown template is rejected with 400."""
    dummy_video = io.BytesIO(b"fake video content")
    resp = client.post(
        "/api/audits",
        data={"template_id": "unknown_template_xyz"},
        files={"video": ("walkthrough.mp4", dummy_video, "video/mp4")},
    )
    assert resp.status_code == 400
    assert "Unknown template_id" in resp.json()["detail"]


def test_audit_lifecycle_end_to_end(tmp_path):
    """
    Test complete lifecycle:
    1. Generate small sample video
    2. POST /api/audits
    3. Run background job
    4. Check status reaches 'completed'
    5. Fetch findings with overlay URLs
    6. Verify cost endpoint
    """
    sample_mp4 = tmp_path / "walkthrough.mp4"
    generate_sample_video(sample_mp4, duration_s=4, fps=25)

    with open(sample_mp4, "rb") as f:
        video_bytes = f.read()

    # 1. POST /api/audits (TestClient executes background_tasks synchronously before returning)
    create_resp = client.post(
        "/api/audits",
        data={"template_id": "fire_exit_safety"},
        files={"video": ("walkthrough.mp4", io.BytesIO(video_bytes), "video/mp4")},
    )
    assert create_resp.status_code == 201
    audit_id = create_resp.json()["id"]
    assert audit_id

    # 2. GET /api/audits/{id}
    detail_resp = client.get(f"/api/audits/{audit_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["status"] == "completed"
    assert data["summary"] is not None
    assert "score" in data["summary"]
    assert len(data["findings"]) == 5

    # Check finding fields
    first_f = data["findings"][0]
    assert "overlay_url" in first_f
    assert first_f["status"] in ("pass", "fail", "unsure")
    assert first_f["confidence"] >= 0.0

    # 4. Verify overlay image endpoint serves a valid JPEG
    overlay_resp = client.get(first_f["overlay_url"])
    assert overlay_resp.status_code == 200
    assert overlay_resp.headers["content-type"] == "image/jpeg"
    assert len(overlay_resp.content) > 0

    # 5. Verify cost endpoint
    cost_resp = client.get(f"/api/audits/{audit_id}/cost")
    assert cost_resp.status_code == 200
    cost_data = cost_resp.json()
    assert cost_data["audit_id"] == audit_id
    assert "total_cost_usd" in cost_data


def test_voice_note_upload(tmp_path):
    """Verify POST /api/audits/{id}/voice-notes uploads audio and saves voice note."""
    sample_mp4 = tmp_path / "walkthrough.mp4"
    generate_sample_video(sample_mp4, duration_s=3, fps=25)

    with open(sample_mp4, "rb") as f:
        v_bytes = f.read()

    create_resp = client.post(
        "/api/audits",
        data={"template_id": "fire_exit_safety"},
        files={"video": ("walkthrough.mp4", io.BytesIO(v_bytes), "video/mp4")},
    )
    audit_id = create_resp.json()["id"]

    audio_bytes = io.BytesIO(b"RIFFdummyWAVaudiodata")
    vn_resp = client.post(
        f"/api/audits/{audit_id}/voice-notes",
        data={"timestamp_s": 2.5},
        files={"audio": ("memo.wav", audio_bytes, "audio/wav")},
    )
    assert vn_resp.status_code == 201
    assert vn_resp.json()["audit_id"] == audit_id
    assert vn_resp.json()["timestamp_s"] == 2.5


def test_compare_endpoint(tmp_path):
    """Verify POST /api/compare returns valid per-rule transition results."""
    eng = engine()
    with Session(eng) as session:
        # Create before audit
        a1 = Audit(id="audit_before", template_id="fire_exit_safety", status="completed")
        session.add(a1)
        f1 = Finding(
            id="f1_before",
            audit_id="audit_before",
            rule_id="extinguisher_visible",
            status="fail",
            confidence=0.8,
            timestamp_s=2.0,
            frame_idx=2,
            rationale="Missing",
            fix_text="Install extinguisher",
            severity="high",
        )
        session.add(f1)

        # Create after audit
        a2 = Audit(id="audit_after", template_id="fire_exit_safety", status="completed")
        session.add(a2)
        f2 = Finding(
            id="f2_after",
            audit_id="audit_after",
            rule_id="extinguisher_visible",
            status="pass",
            confidence=0.92,
            timestamp_s=2.0,
            frame_idx=2,
            rationale="Extinguisher mounted",
            fix_text="",
            severity="high",
        )
        session.add(f2)
        session.commit()

    resp = client.post(
        "/api/compare",
        json={"before_id": "audit_before", "after_id": "audit_after"},
    )
    assert resp.status_code == 200
    comp = resp.json()
    assert comp["summary"]["resolved"] == 1
    assert comp["results"][0]["rule_id"] == "extinguisher_visible"
    assert comp["results"][0]["status"] == "resolved"


def test_sse_event_stream_replay(tmp_path):
    """Verify GET /api/audits/{id}/events returns recorded JSONL events."""
    sample_mp4 = tmp_path / "walkthrough.mp4"
    generate_sample_video(sample_mp4, duration_s=3, fps=25)

    with open(sample_mp4, "rb") as f:
        v_bytes = f.read()

    create_resp = client.post(
        "/api/audits",
        data={"template_id": "fire_exit_safety"},
        files={"video": ("walkthrough.mp4", io.BytesIO(v_bytes), "video/mp4")},
    )
    audit_id = create_resp.json()["id"]

    # Connect to SSE endpoint (TestClient has already executed the background job)
    with client.stream("GET", f"/api/audits/{audit_id}/events") as sse_stream:
        lines = []
        for line in sse_stream.iter_lines():
            if line:
                lines.append(line)
            # Collect first 10 SSE lines
            if len(lines) >= 8:
                break

        # SSE lines format: 'data: {...}'
        data_lines = [l for l in lines if l.startswith("data:")]
        assert len(data_lines) > 0
        parsed_first = json.loads(data_lines[0].replace("data:", "").strip())
        assert "type" in parsed_first
        assert parsed_first["audit_id"] == audit_id
