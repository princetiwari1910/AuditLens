"""Tests for Public Deployment Safety & Share Token Security."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlmodel import Session, select
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import get_session, init_db, reset_engine
from app.main import app
from app.models import Audit, Finding, ShareToken
from app.providers import (
    get_agent_provider,
    get_reasoner,
    get_segmentation_provider,
    get_transcription_provider,
)
from app.providers.meta import (
    MetaAgentProvider,
    MetaSegmentationProvider,
    MetaTranscriptionProvider,
)
from app.providers.mock import MockAgentProvider


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    return tmp_path


# ── Requirement 4: Replay Mode Refuses Live Calls ────────────────────────────

def test_replay_mode_refuses_live_provider_calls(monkeypatch: pytest.MonkeyPatch):
    """When PROVIDER_MODE is replay, refuse live provider calls even if MODEL_API_KEY is present."""
    settings = get_settings()
    monkeypatch.setattr(settings, "PROVIDER_MODE", "replay")
    monkeypatch.setattr(settings, "MODEL_API_KEY", "meta_live_key_xyz_1234567890")

    # 1. MetaSegmentationProvider refuses client creation
    seg = MetaSegmentationProvider()
    with pytest.raises(RuntimeError, match="Live provider calls are strictly prohibited when PROVIDER_MODE=replay"):
        seg._get_client()

    # 2. MetaAgentProvider refuses client creation
    agent = MetaAgentProvider()
    with pytest.raises(RuntimeError, match="Live provider calls are strictly prohibited when PROVIDER_MODE=replay"):
        agent._get_client()

    # 3. MetaTranscriptionProvider refuses client creation
    trans = MetaTranscriptionProvider()
    with pytest.raises(RuntimeError, match="Live provider calls are strictly prohibited when PROVIDER_MODE=replay"):
        trans._get_client()

    # 4. Standard provider factories in replay mode return Mock or RecordReplay wrapping Mock
    agent_p = get_agent_provider()
    assert isinstance(agent_p, MockAgentProvider), "Agent provider must be Mock in replay mode"


# ── Requirement 5: Share Links Read-Only & Own-Audit Confinement ───────────────

def test_share_token_can_only_read_own_audit(clean_db: Path):
    """Share token can only read its own audit and cannot access another audit."""
    client = TestClient(app)
    session = next(get_session())

    # Create Audit A
    audit_a = Audit(
        id="audit_sec_a_01",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 95, "pass": 4, "fail": 0, "unsure": 0}),
    )
    # Create Audit B
    audit_b = Audit(
        id="audit_sec_b_02",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 60, "pass": 2, "fail": 2, "unsure": 0}),
    )
    session.add(audit_a)
    session.add(audit_b)
    session.commit()

    # Generate share token for Audit A
    resp = client.post(f"/api/audits/{audit_a.id}/share")
    assert resp.status_code == 200
    token_a = resp.json()["token"]

    # 1. Resolve Audit A using share token via /api/share/{token}
    resp_resolve = client.get(f"/api/share/{token_a}")
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["id"] == audit_a.id
    assert resp_resolve.json()["summary"]["score"] == 95

    # 2. Direct read of Audit A with token_a succeeds
    resp_own = client.get(f"/api/audits/{audit_a.id}?token={token_a}")
    assert resp_own.status_code == 200
    assert resp_own.json()["id"] == audit_a.id

    # 3. Direct read of Audit B with token_a is strictly FORBIDDEN (403)
    resp_cross = client.get(f"/api/audits/{audit_b.id}?token={token_a}")
    assert resp_cross.status_code == 403
    assert "not authorized for this audit" in resp_cross.json()["detail"]

    # 4. Unknown/invalid token returns 404
    resp_invalid = client.get(f"/api/audits/{audit_a.id}?token=invalid_token_123456789")
    assert resp_invalid.status_code == 404


def test_share_token_exposes_no_write_or_review_endpoints(clean_db: Path):
    """Share endpoints only allow GET; write, review, and mutations are not exposed."""
    client = TestClient(app)
    session = next(get_session())

    audit = Audit(
        id="audit_no_write_01",
        template_id="campus_fire_exit_core",
        status="completed",
    )
    session.add(audit)
    session.commit()

    resp = client.post(f"/api/audits/{audit.id}/share")
    assert resp.status_code == 200
    token = resp.json()["token"]

    # Attempting POST/PUT/DELETE on /api/share/{token} fails with 405 Method Not Allowed
    post_resp = client.post(f"/api/share/{token}")
    assert post_resp.status_code == 405

    put_resp = client.put(f"/api/share/{token}")
    assert put_resp.status_code == 405

    del_resp = client.delete(f"/api/share/{token}")
    assert del_resp.status_code == 405

    # Non-existent review subpath on share route returns 404
    review_share_resp = client.post(f"/api/share/{token}/review")
    assert review_share_resp.status_code in (404, 405)
