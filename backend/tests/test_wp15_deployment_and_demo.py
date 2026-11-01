"""Tests for WP15: Guided Demo and Deployment Readiness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import select
from starlette.testclient import TestClient

from app.config import PROJECT_ROOT, get_settings
from app.db import get_session, init_db, reset_engine
from app.main import app
from app.models import Audit


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    # Ensure sample video exists in tmp_path
    sample_video = tmp_path / "sample_walkthrough.mp4"
    sample_video.write_bytes(b"dummy mp4 video bytes")
    return tmp_path


def test_guided_demo_endpoint_creates_replay_audit(clean_db: Path):
    """Calling POST /api/audits/demo?replay=true stamps audit with is_replay=True and provider_mode='replay'."""
    client = TestClient(app)

    resp = client.post("/api/audits/demo?replay=true&template_id=campus_fire_exit_core")
    assert resp.status_code == 201
    data = resp.json()
    audit_id = data["id"]

    session = next(get_session())
    audit = session.get(Audit, audit_id)
    assert audit is not None
    assert audit.is_replay is True
    assert audit.provider_mode == "replay"
    assert audit.template_id == "campus_fire_exit_core"


def test_standard_demo_endpoint_creates_mock_audit(clean_db: Path):
    """Calling POST /api/audits/demo?replay=false stamps audit with is_replay=False and current PROVIDER_MODE (mock)."""
    client = TestClient(app)

    resp = client.post("/api/audits/demo?replay=false&template_id=campus_fire_exit_core")
    assert resp.status_code == 201
    data = resp.json()
    audit_id = data["id"]

    session = next(get_session())
    audit = session.get(Audit, audit_id)
    assert audit is not None
    assert audit.is_replay is False
    assert audit.provider_mode == "mock"


def test_sse_headers_and_buffering(clean_db: Path):
    """Verify that SSE endpoint serves unbuffered no-cache headers."""
    client = TestClient(app)

    # Seed an audit
    session = next(get_session())
    audit = Audit(
        id="audit_sse_headers_01",
        template_id="campus_fire_exit_core",
        status="completed",
    )
    session.add(audit)
    session.commit()

    # Query events stream (first response headers)
    with client.stream("GET", f"/api/audits/{audit.id}/events") as resp:
        assert resp.status_code == 200
        headers = {k.lower(): v for k, v in resp.headers.items()}
        assert "text/event-stream" in headers.get("content-type", "")
        assert "no-cache" in headers.get("cache-control", "")
        assert headers.get("x-accel-buffering") == "no"


def test_dockerfile_and_compose_configuration():
    """Verify backend Dockerfile and docker-compose.yml configurations."""
    dockerfile_path = PROJECT_ROOT / "backend" / "Dockerfile"
    assert dockerfile_path.exists(), "backend/Dockerfile must exist"
    dockerfile_content = dockerfile_path.read_text()
    assert "python:3.11-slim" in dockerfile_content
    assert "ffmpeg" in dockerfile_content
    assert "8000" in dockerfile_content
    assert "uvicorn" in dockerfile_content

    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"
    compose_content = compose_path.read_text()
    assert "DATA_DIR" in compose_content
    assert "CORS_ORIGINS" in compose_content
    assert "./data:/data" in compose_content
    assert "healthcheck" in compose_content
