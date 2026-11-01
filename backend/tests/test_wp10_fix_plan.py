"""Tests for WP10: AI Fix Plan Generation Grounded in Findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import get_session, init_db, reset_engine
from app.main import app
from app.models import Audit, Finding
from app.providers.base import Reasoner
from app.providers.mock import MockReasoner
from app.providers.record_replay import RecordReplayReasoner
from app.providers.schemas import FixAction, FixEffort, validate_fix_actions


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    return tmp_path


def test_fix_action_schema_validation():
    # Valid model validation
    action = FixAction(
        finding_id="f_01",
        rule_id="exit_path_not_blocked",
        severity="high",
        effort="s",  # should normalize to S
        suggested_fix="Clear delivery boxes immediately",
        suggested_due_days=2,
    )
    assert action.effort == FixEffort.S
    assert action.severity == "high"
    assert action.suggested_due_days == 2
    assert "MOCK" in action.label

    # Normalization of invalid effort and negative due days
    fallback_action = FixAction(
        finding_id="f_02",
        effort="invalid",
        suggested_due_days=-5,
        suggested_fix="Inspect extinguisher",
    )
    assert fallback_action.effort == FixEffort.M
    assert fallback_action.suggested_due_days == 1

    # validate_fix_actions helper filters ungrounded finding IDs
    valid_raw = [
        {
            "finding_id": "f_01",
            "rule_id": "exit_path_not_blocked",
            "severity": "high",
            "effort": "S",
            "suggested_fix": "Clear boxes",
            "suggested_due_days": 2,
        },
        {
            "finding_id": "hallucinated_id",
            "rule_id": "unknown",
            "severity": "low",
            "effort": "L",
            "suggested_fix": "Ghost fix",
            "suggested_due_days": 30,
        },
    ]
    validated = validate_fix_actions(valid_raw, allowed_finding_ids=["f_01"])
    assert len(validated) == 1
    assert validated[0]["finding_id"] == "f_01"
    assert validated[0]["effort"] == "S"


def test_mock_reasoner_plan_fixes_prioritization():
    reasoner: Reasoner = MockReasoner()
    findings = [
        {
            "id": "f_pass",
            "rule_id": "extinguisher_visible",
            "status": "pass",
            "severity": "high",
            "fix_text": "",
        },
        {
            "id": "f_unsure_high",
            "rule_id": "exit_sign_visible",
            "status": "unsure",
            "severity": "high",
            "fix_text": "Verify illuminated exit sign above door.",
        },
        {
            "id": "f_fail_med",
            "rule_id": "exit_path_not_blocked",
            "status": "fail",
            "severity": "medium",
            "fix_text": "Clear boxes blocking egress corridor.",
        },
        {
            "id": "f_fail_high",
            "rule_id": "extinguisher_accessible",
            "status": "fail",
            "severity": "high",
            "fix_text": "Mount extinguisher unobstructed on corridor wall.",
        },
    ]

    plan = reasoner.plan_fixes(findings)
    assert len(plan) == 3  # pass finding excluded
    # Ordering: fail before unsure; high before medium
    assert plan[0]["finding_id"] == "f_fail_high"
    assert plan[0]["severity"] == "high"
    assert plan[0]["label"] == "AI-suggested (MOCK)"

    assert plan[1]["finding_id"] == "f_fail_med"
    assert plan[1]["severity"] == "medium"
    assert plan[1]["effort"] == "S"  # boxes/clear -> Small effort
    assert plan[1]["suggested_due_days"] <= 3

    assert plan[2]["finding_id"] == "f_unsure_high"
    assert plan[2]["severity"] == "high"


def test_record_replay_reasoner_plan_fixes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.providers.record_replay.get_fixtures_dir", lambda: fixtures_dir)

    inner = MockReasoner()
    record_reasoner = RecordReplayReasoner(inner=inner, mode="record")

    findings = [
        {
            "id": "f_test_1",
            "rule_id": "exit_path_not_blocked",
            "status": "fail",
            "severity": "high",
            "fix_text": "Clear aisle boxes",
        }
    ]

    # In record mode: runs and saves fixture
    plan_recorded = record_reasoner.plan_fixes(findings)
    assert len(plan_recorded) == 1
    assert plan_recorded[0]["finding_id"] == "f_test_1"

    fixture_files = list(fixtures_dir.glob("fixplan_*.json"))
    assert len(fixture_files) == 1

    # In replay mode: served directly from disk without touching inner
    inner_mock = MagicMock()
    replay_reasoner = RecordReplayReasoner(inner=inner_mock, mode="replay")
    plan_replayed = replay_reasoner.plan_fixes(findings)
    assert len(plan_replayed) == 1
    assert plan_replayed[0]["finding_id"] == "f_test_1"
    inner_mock.plan_fixes.assert_not_called()


def test_meta_agent_provider_plan_fixes_without_key():
    from app.providers.meta import MetaAgentProvider

    provider = MetaAgentProvider()
    with pytest.raises(ValueError, match="UNVERIFIED against live API"):
        provider.plan_fixes([{"id": "f1", "status": "fail"}])


def test_get_audit_fix_plan_api_endpoint(clean_db: Path):
    client = TestClient(app)

    # 404 for unknown audit
    resp = client.get("/api/audits/non_existent_id/fix_plan")
    assert resp.status_code == 404

    # Seed an audit with findings
    session = next(get_session())
    audit = Audit(
        id="audit_plan_test_01",
        template_id="campus_fire_exit_core",
        status="completed",
    )
    session.add(audit)
    f1 = Finding(
        id="f_audit_fail",
        audit_id="audit_plan_test_01",
        rule_id="exit_path_not_blocked",
        status="fail",
        confidence=0.92,
        timestamp_s=4.0,
        frame_idx=2,
        severity="high",
        fix_text="Remove large pallet from doorway",
        ai_verdict="fail",
        final_verdict="fail",
    )
    f2 = Finding(
        id="f_audit_pass",
        audit_id="audit_plan_test_01",
        rule_id="extinguisher_visible",
        status="pass",
        confidence=0.95,
        timestamp_s=2.0,
        frame_idx=1,
        severity="high",
        ai_verdict="pass",
        final_verdict="pass",
    )
    session.add(f1)
    session.add(f2)
    session.commit()

    resp = client.get(f"/api/audits/{audit.id}/fix_plan")
    assert resp.status_code == 200
    plan = resp.json()
    assert len(plan) == 1
    assert plan[0]["finding_id"] == "f_audit_fail"
    assert plan[0]["severity"] == "high"
    assert "AI-suggested (MOCK)" in plan[0]["label"]
