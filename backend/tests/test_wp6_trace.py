"""Unit tests for WP6 Execution Tracing and Observability Spans."""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from sqlmodel import Session

from app.agent.trace import record_span, get_audit_trace
from app.config import get_settings
from app.db import engine, init_db, reset_engine
from app.main import app
from app.models import Audit, AuditSpan, AuditStatus


@pytest.fixture
def client_with_spans(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    s = get_settings()
    monkeypatch.setattr(s, "DATA_DIR", data_dir)
    reset_engine()
    init_db()

    client = TestClient(app)
    audit_id = "audit_trace_test_01"
    with Session(engine()) as session:
        audit = Audit(
            id=audit_id,
            template_id="fire_exit_safety",
            status=AuditStatus.COMPLETED.value,
            summary_json=json.dumps({
                "frames_considered": 100,
                "frames_analyzed": 12,
                "score": 85,
            }),
        )
        session.add(audit)
        session.commit()

        # Add spans
        record_span(
            session=session,
            audit_id=audit_id,
            stage="keyframe_selection",
            model="opencv",
            latency_ms=30,
            cost_usd=0.0,
            step_reason="Quality filtering: 100 candidate frames -> 12 keyframes",
        )
        record_span(
            session=session,
            audit_id=audit_id,
            stage="segmentation",
            model="SAM 3.1",
            concept="fire extinguisher",
            latency_ms=120,
            cost_usd=0.0025,
            cache_hit=False,
            retries=0,
            step_reason="Evaluated extinguisher visibility",
        )
        record_span(
            session=session,
            audit_id=audit_id,
            stage="segmentation",
            model="SAM 3.1",
            concept="emergency exit sign",
            latency_ms=15,
            cost_usd=0.0,
            cache_hit=True,
            retries=0,
            step_reason="Cached result hit",
        )

    return client, audit_id


def test_get_audit_trace_endpoint(client_with_spans):
    """GET /api/audits/{id}/trace returns spans and aggregated totals."""
    client, audit_id = client_with_spans

    resp = client.get(f"/api/audits/{audit_id}/trace")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["audit_id"] == audit_id
    spans = data["spans"]
    assert len(spans) == 3

    # Check keyframe span
    kf_span = spans[0]
    assert kf_span["stage"] == "keyframe_selection"
    assert kf_span["model"] == "opencv"
    assert kf_span["latency_ms"] == 30

    # Check cached span
    cached_span = spans[2]
    assert cached_span["cache_hit"] is True

    # Check totals
    totals = data["totals"]
    assert totals["total_spans"] == 3
    assert totals["total_latency_ms"] == 165
    assert totals["total_cost_usd"] == 0.0025
    assert totals["calls_saved_by_cache"] == 1
    assert totals["calls_saved_by_keyframes"] == 88  # 100 - 12


def test_trace_endpoint_404_for_missing_audit(client_with_spans):
    """GET /api/audits/{id}/trace returns 404 for nonexistent audit."""
    client, _ = client_with_spans
    resp = client.get("/api/audits/non_existent_audit_id/trace")
    assert resp.status_code == 404


def test_demo_audit_creates_trace_spans(tmp_path, monkeypatch):
    """Launching demo audit creates and populates trace spans."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    s = get_settings()
    monkeypatch.setattr(s, "DATA_DIR", data_dir)
    reset_engine()
    init_db()

    client = TestClient(app)
    demo_resp = client.post("/api/audits/demo?template_id=fire_exit_safety")
    assert demo_resp.status_code == 201
    audit_id = demo_resp.json()["id"]

    trace_resp = client.get(f"/api/audits/{audit_id}/trace")
    assert trace_resp.status_code == 200
    data = trace_resp.json()
    assert data["totals"]["total_spans"] >= 1
    stages = [s["stage"] for s in data["spans"]]
    assert "keyframe_selection" in stages
    assert "segmentation" in stages
