"""Tests for WP14: Audit Trace Dashboard, Report Polish, and Shareable Links."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlmodel import select
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import get_session, init_db, reset_engine
from app.main import app
from app.models import Audit, AuditSpan, Finding, ShareToken


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    return tmp_path


def test_create_and_resolve_share_link(clean_db: Path):
    client = TestClient(app)

    # 1. 404 on missing audit
    resp = client.post("/api/audits/non_existent/share")
    assert resp.status_code == 404

    # 2. Seed an audit
    session = next(get_session())
    audit = Audit(
        id="audit_share_01",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 90, "pass": 3, "fail": 0, "unsure": 1}),
    )
    session.add(audit)
    session.commit()

    # 3. Create share link
    resp = client.post(f"/api/audits/{audit.id}/share")
    assert resp.status_code == 200
    data = resp.json()

    raw_token = data["token"]
    assert len(raw_token) >= 20
    assert data["share_url"] == f"/audits/{audit.id}?token={raw_token}"

    # Verify database stores SHA-256 hash only, NEVER plaintext token
    th = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    st_row = session.exec(select(ShareToken).where(ShareToken.token_hash == th)).first()
    assert st_row is not None
    assert st_row.audit_id == audit.id
    assert st_row.access_count == 0

    # 4. Resolve share link via /api/share/{token}
    resp_resolve = client.get(f"/api/share/{raw_token}")
    assert resp_resolve.status_code == 200
    res_data = resp_resolve.json()
    assert res_data["id"] == audit.id
    assert res_data["summary"]["score"] == 90

    # Check access count was incremented
    session.refresh(st_row)
    assert st_row.access_count == 1

    # 5. Invalid token returns 404
    resp_invalid = client.get("/api/share/bogus_token_value")
    assert resp_invalid.status_code == 404


def test_audit_trace_endpoint(clean_db: Path):
    client = TestClient(app)

    session = next(get_session())
    audit = Audit(
        id="audit_trace_test_01",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({
            "score": 88,
            "pass": 2,
            "fail": 1,
            "unsure": 0,
            "frames_considered": 40,
            "frames_analyzed": 10,
        }),
    )
    session.add(audit)

    s1 = AuditSpan(
        audit_id="audit_trace_test_01",
        stage="keyframe_selection",
        model="opencv",
        latency_ms=30,
        cost_usd=0.0,
        cache_hit=False,
        step_reason="Filtered 30 blurry frames",
    )
    s2 = AuditSpan(
        audit_id="audit_trace_test_01",
        stage="segmentation",
        model="sam-3.1",
        concept="fire extinguisher",
        latency_ms=120,
        cost_usd=0.001,
        cache_hit=True,
        step_reason="Found extinguisher on wall",
    )
    session.add(s1)
    session.add(s2)
    session.commit()

    resp = client.get(f"/api/audits/{audit.id}/trace")
    assert resp.status_code == 200
    trace_data = resp.json()

    assert trace_data["audit_id"] == audit.id
    assert len(trace_data["spans"]) == 2
    assert trace_data["totals"]["total_spans"] == 2
    assert trace_data["totals"]["cache_hits"] == 1
    assert trace_data["totals"]["total_cost_usd"] == 0.001
    assert trace_data["totals"]["frames_considered"] == 40
    assert trace_data["totals"]["frames_analyzed"] == 10
    assert trace_data["totals"]["frames_saved_by_selection"] == 30
