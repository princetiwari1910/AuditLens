"""Tests for Meta tooling evidence, model stamping, cost tracking, and demo replay."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.costlog import get_audit_cost_summary, log_cost
from app.db import engine, get_session, init_db
from app.job_runner import replay_demo_audit, run_audit_job_sync
from app.main import app
from app.models import Audit, AuditStatus, CostLog, Finding
from scripts.record_demo import record_demo


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("DEMO_REPLAY", "0")

    get_settings.cache_clear()
    init_db()

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def test_health_stamps_provider_mode_and_models(client):
    """GET /api/health must stamp provider_mode, models dictionary, and data_dir."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["provider_mode"] == "mock"
    assert "models" in data
    assert data["models"]["segmentation"] == "SAM 3.1"
    assert data["models"]["agent"] == "Muse Spark"
    assert data["models"]["transcription"] == "Muse Voice Transcribe"
    assert "data_dir" in data
    assert "demo_replay" in data


def test_audit_record_stamps_provider_and_models(client):
    """Audit creation stamps provider_mode and model IDs on database record and GET response."""
    # Create demo audit
    resp = client.post("/api/audits/demo?template_id=fire_exit_safety")
    assert resp.status_code == 201
    audit_id = resp.json()["id"]

    detail_resp = client.get(f"/api/audits/{audit_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    assert detail["provider_mode"] == "mock"
    assert detail["model_segmentation"] == "SAM 3.1"
    assert detail["model_agent"] == "Muse Spark"
    assert detail["model_transcription"] == "Muse Voice Transcribe"
    assert detail["is_replay"] is False
    assert detail["models"]["segmentation"] == "SAM 3.1"


def test_cost_summary_includes_models_and_roles(client):
    """Cost log tracks model_id, latency_ms, cache_hit, and formats plain-English roles."""
    eng = engine()
    audit_id = "test_cost_meta_audit"

    with Session(eng) as session:
        # 1. Segmentation call
        log_cost(
            session=session,
            provider="segmentation",
            operation="segmentation",
            units=10.0,
            audit_id=audit_id,
            latency_ms=180,
            cache_hit=False,
        )
        # 2. Segmentation cache hit
        log_cost(
            session=session,
            provider="segmentation",
            operation="segmentation",
            units=0.0,
            audit_id=audit_id,
            latency_ms=2,
            cache_hit=True,
        )
        # 3. Agent reasoning call
        log_cost(
            session=session,
            provider="agent",
            operation="agent_input",
            units=1.5,
            audit_id=audit_id,
            latency_ms=45,
            cache_hit=False,
        )

        summary = get_audit_cost_summary(session, audit_id)

    assert summary["audit_id"] == audit_id
    assert summary["total_calls"] == 3
    assert summary["total_cost_usd"] > 0

    by_prov = summary["by_provider"]
    assert "segmentation" in by_prov
    assert "agent" in by_prov
    assert "transcription" in by_prov

    seg = by_prov["segmentation"]
    assert seg["model_id"] == "SAM 3.1"
    assert seg["calls"] == 2
    assert seg["cache_hits"] == 1
    assert seg["latency_ms"] == 182
    assert "finds and measures items" in seg["role"]
    assert seg["simulated"] is True

    agent = by_prov["agent"]
    assert agent["model_id"] == "Muse Spark"
    assert agent["calls"] == 1
    assert "reasons over rules" in agent["role"]


def test_demo_recording_script_and_replay_flow(tmp_path, monkeypatch):
    """record_demo generates fixture and replay_demo_audit replays events with is_replay=True."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    monkeypatch.setenv("PROVIDER_MODE", "mock")

    get_settings.cache_clear()
    init_db()

    # 1. Record demo
    fixture_path = record_demo(template_id="fire_exit_safety")
    assert fixture_path.exists()
    assert fixture_path.stat().st_size > 0

    with open(fixture_path, "r", encoding="utf-8") as fp:
        fixture_data = json.load(fp)

    assert "events" in fixture_data
    assert len(fixture_data["events"]) > 5
    assert "findings" in fixture_data
    assert len(fixture_data["findings"]) > 0

    # 2. Replay demo into a new audit
    eng = engine()
    replay_audit_id = "audit_replayed_test_123"

    with Session(eng) as session:
        audit = Audit(
            id=replay_audit_id,
            template_id="fire_exit_safety",
            status=AuditStatus.QUEUED.value,
        )
        session.add(audit)
        session.commit()

        # Execute replay
        replay_demo_audit(replay_audit_id, session)

        session.refresh(audit)
        assert audit.status == AuditStatus.COMPLETED.value
        assert audit.is_replay is True
        assert audit.summary_json is not None

        findings = session.exec(select(Finding).where(Finding.audit_id == replay_audit_id)).all()
        assert len(findings) == len(fixture_data["findings"])
        assert any("[Recorded run]" in f.rationale for f in findings)


def test_demo_replay_env_flag_activates_replay(tmp_path, monkeypatch):
    """When DEMO_REPLAY=1, background job runner immediately executes replay path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    monkeypatch.setenv("DEMO_REPLAY", "1")

    get_settings.cache_clear()
    init_db()

    # Ensure fixture exists
    record_demo(template_id="fire_exit_safety")

    with TestClient(app) as client:
        # Launch demo audit with DEMO_REPLAY=1
        resp = client.post("/api/audits/demo?template_id=fire_exit_safety")
        assert resp.status_code == 201
        audit_id = resp.json()["id"]

        detail = client.get(f"/api/audits/{audit_id}").json()
        assert detail["status"] == "completed"
        assert detail["is_replay"] is True
