"""Unit tests for WP5 Human Review Queue and Append-Only Audit Log."""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, get_session, init_db, reset_engine
from app.main import app
from app.models import Audit, AuditLog, AuditStatus, Finding, FindingStatus


@pytest.fixture
def client_with_audit(tmp_path, monkeypatch):
    """Create a temporary client with an active audit and findings."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    s = get_settings()
    monkeypatch.setattr(s, "DATA_DIR", data_dir)
    reset_engine()
    init_db()

    client = TestClient(app)
    # Create an audit directly in the database
    with Session(engine()) as session:
        audit = Audit(
            id="audit_rev_101",
            template_id="fire_exit_safety",
            status=AuditStatus.COMPLETED.value,
            summary_json=json.dumps({"score": 60, "pass": 1, "fail": 1, "unsure": 1, "total": 3}),
        )
        session.add(audit)

        f1 = Finding(
            id="f_pass_01",
            audit_id="audit_rev_101",
            rule_id="extinguisher_visible",
            status=FindingStatus.PASS.value,
            ai_verdict="pass",
            final_verdict="pass",
            confidence=0.92,
            timestamp_s=1.0,
            frame_idx=1,
            severity="high",
            rationale="Visible extinguisher.",
        )
        f2 = Finding(
            id="f_unsure_02",
            audit_id="audit_rev_101",
            rule_id="exit_sign_visible",
            status=FindingStatus.UNSURE.value,
            ai_verdict="unsure",
            final_verdict="unsure",
            confidence=0.45,
            timestamp_s=2.0,
            frame_idx=2,
            severity="high",
            rationale="Marginal visibility.",
        )
        f3 = Finding(
            id="f_fail_03",
            audit_id="audit_rev_101",
            rule_id="exit_path_not_blocked",
            status=FindingStatus.FAIL.value,
            ai_verdict="fail",
            final_verdict="fail",
            confidence=0.88,
            timestamp_s=3.0,
            frame_idx=3,
            severity="high",
            rationale="Blocked corridor.",
        )
        session.add_all([f1, f2, f3])
        session.commit()

    return client, "audit_rev_101"


def test_review_approve_ai(client_with_audit):
    """Reviewer approves AI verdict with a non-empty note."""
    client, audit_id = client_with_audit

    resp = client.post(
        f"/api/audits/{audit_id}/findings/f_unsure_02/review",
        json={
            "action": "approve_ai",
            "actor_label": "Senior Inspector",
            "note": "Checked high-res photo manually; signs are genuinely unclear.",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["finding_id"] == "f_unsure_02"
    assert data["ai_verdict"] == "unsure"
    assert data["final_verdict"] == "unsure"
    assert data["status"] == "unsure"
    assert data["audit_log"]["action"] == "approve_ai"
    assert data["audit_log"]["actor_label"] == "Senior Inspector"
    assert "signs are genuinely unclear" in data["audit_log"]["note"]


def test_review_override_pass_recalculates_score(client_with_audit):
    """Reviewer overrides an unsure or fail finding to pass, recalculating the safety score."""
    client, audit_id = client_with_audit

    # Override f_unsure_02 to pass
    resp = client.post(
        f"/api/audits/{audit_id}/findings/f_unsure_02/review",
        json={
            "action": "override_pass",
            "actor_label": "Safety Officer",
            "note": "Backup emergency lighting unit satisfies the illumination criterion.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_verdict"] == "unsure"
    assert data["final_verdict"] == "pass"
    assert data["status"] == "pass"

    # Verify audit summary recalculated
    summary = data["summary"]
    assert summary["pass"] == 2
    assert summary["unsure"] == 0
    assert summary["fail"] == 1
    assert summary["score"] > 60


def test_review_override_fail_and_audit_log_chronology(client_with_audit):
    """Perform multiple reviews and verify append-only chronology in GET /api/audits/{id}/audit_log."""
    client, audit_id = client_with_audit

    # 1. Override f_pass_01 to fail
    r1 = client.post(
        f"/api/audits/{audit_id}/findings/f_pass_01/review",
        json={
            "action": "override_fail",
            "actor_label": "Fire Marshal",
            "note": "Inspection tag on extinguisher is expired by 6 months.",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["final_verdict"] == "fail"

    # 2. Approve AI on f_fail_03
    r2 = client.post(
        f"/api/audits/{audit_id}/findings/f_fail_03/review",
        json={
            "action": "approve_ai",
            "actor_label": "Fire Marshal",
            "note": "Severe exit pathway blockage confirmed.",
        },
    )
    assert r2.status_code == 200

    # 3. Fetch audit log
    log_resp = client.get(f"/api/audits/{audit_id}/audit_log")
    assert log_resp.status_code == 200
    logs = log_resp.json()
    assert len(logs) == 2
    assert logs[0]["finding_id"] == "f_pass_01"
    assert logs[0]["action"] == "override_fail"
    assert logs[0]["before"] == "pass"
    assert logs[0]["after"] == "fail"

    assert logs[1]["finding_id"] == "f_fail_03"
    assert logs[1]["action"] == "approve_ai"
    assert logs[1]["before"] == "fail"
    assert logs[1]["after"] == "fail"

    # Verify no DELETE or PUT routes exist (strictly append-only)
    del_resp = client.delete(f"/api/audits/{audit_id}/audit_log")
    assert del_resp.status_code in (404, 405)


def test_review_validation_rejects_empty_note_and_invalid_action(client_with_audit):
    """Validation checks: reject empty notes and unknown action types."""
    client, audit_id = client_with_audit

    # Empty note
    r_empty = client.post(
        f"/api/audits/{audit_id}/findings/f_pass_01/review",
        json={"action": "override_fail", "note": "   "},
    )
    assert r_empty.status_code == 422
    assert "note is required" in r_empty.text.lower()

    # Invalid action
    r_invalid = client.post(
        f"/api/audits/{audit_id}/findings/f_pass_01/review",
        json={"action": "delete_finding", "note": "Valid explanation."},
    )
    assert r_invalid.status_code == 422
    assert "invalid review action" in r_invalid.text.lower()
