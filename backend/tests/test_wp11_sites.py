"""Tests for WP11: Sites and Multi-Audit Trend History."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import get_session, init_db, reset_engine
from app.main import app
from app.models import Audit, Finding, Site


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    return tmp_path


def test_default_demo_site_seeded(clean_db: Path):
    client = TestClient(app)
    resp = client.get("/api/sites")
    assert resp.status_code == 200
    sites = resp.json()
    assert len(sites) >= 1
    demo_site = next((s for s in sites if s["id"] == "site_demo_building_a"), None)
    assert demo_site is not None
    assert "Building A" in demo_site["name"]
    assert demo_site["location_label"] != ""


def test_site_audits_endpoint(clean_db: Path):
    client = TestClient(app)

    # 404 on missing site
    resp = client.get("/api/sites/unknown_site_id/audits")
    assert resp.status_code == 404

    session = next(get_session())
    site = Site(id="site_custom_test", name="Warehouse Beta", location_label="East Wing")
    session.add(site)
    audit = Audit(
        id="audit_site_01",
        site_id="site_custom_test",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 85, "pass_count": 3, "fail_count": 1}),
    )
    session.add(audit)
    session.commit()

    resp = client.get("/api/sites/site_custom_test/audits")
    assert resp.status_code == 200
    audits = resp.json()
    assert len(audits) == 1
    assert audits[0]["id"] == "audit_site_01"
    assert audits[0]["site_id"] == "site_custom_test"
    assert audits[0]["summary"]["score"] == 85


def test_site_trends_multi_audit_history(clean_db: Path):
    client = TestClient(app)

    # 404 on missing site
    resp = client.get("/api/sites/unknown_site_id/trends")
    assert resp.status_code == 404

    session = next(get_session())
    site = Site(id="site_trend_facility", name="Research Lab Complex", location_label="Sector 4")
    session.add(site)

    # Audit 1 (Earlier): exit_path_not_blocked failed, extinguisher_visible failed
    a1 = Audit(
        id="audit_seq_1",
        site_id="site_trend_facility",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 50, "pass_count": 1, "fail_count": 2, "unsure_count": 0}),
    )
    session.add(a1)
    f1_a1 = Finding(
        id="f1_a1",
        audit_id="audit_seq_1",
        rule_id="exit_path_not_blocked",
        status="fail",
        confidence=0.9,
        timestamp_s=2.0,
        frame_idx=1,
        severity="high",
        rationale="Cart blocking egress hallway",
        ai_verdict="fail",
        final_verdict="fail",
    )
    f2_a1 = Finding(
        id="f2_a1",
        audit_id="audit_seq_1",
        rule_id="extinguisher_visible",
        status="fail",
        confidence=0.9,
        timestamp_s=4.0,
        frame_idx=2,
        severity="high",
        rationale="Extinguisher missing from designated bracket",
        ai_verdict="fail",
        final_verdict="fail",
    )
    session.add(f1_a1)
    session.add(f2_a1)

    # Audit 2 (Subsequent): exit_path_not_blocked passed (resolved!), extinguisher_visible still failed (recurring!)
    a2 = Audit(
        id="audit_seq_2",
        site_id="site_trend_facility",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 75, "pass_count": 2, "fail_count": 1, "unsure_count": 0}),
    )
    session.add(a2)
    f1_a2 = Finding(
        id="f1_a2",
        audit_id="audit_seq_2",
        rule_id="exit_path_not_blocked",
        status="pass",
        confidence=0.95,
        timestamp_s=2.0,
        frame_idx=1,
        severity="high",
        rationale="Egress corridor completely unobstructed",
        ai_verdict="pass",
        final_verdict="pass",
    )
    f2_a2 = Finding(
        id="f2_a2",
        audit_id="audit_seq_2",
        rule_id="extinguisher_visible",
        status="fail",
        confidence=0.91,
        timestamp_s=4.0,
        frame_idx=2,
        severity="high",
        rationale="Extinguisher bracket still empty",
        ai_verdict="fail",
        final_verdict="fail",
    )
    session.add(f1_a2)
    session.add(f2_a2)
    session.commit()

    resp = client.get("/api/sites/site_trend_facility/trends")
    assert resp.status_code == 200
    data = resp.json()

    assert data["site"]["name"] == "Research Lab Complex"
    assert len(data["score_trend"]) == 2
    assert data["score_trend"][0]["score"] == 50
    assert data["score_trend"][1]["score"] == 75

    # 1. Open issues from latest audit
    assert len(data["open_issues"]) == 1
    assert data["open_issues"][0]["rule_id"] == "extinguisher_visible"

    # 2. Recurring issues (failed in both audits)
    assert len(data["recurring_issues"]) == 1
    assert data["recurring_issues"][0]["rule_id"] == "extinguisher_visible"
    assert data["recurring_issues"][0]["fail_occurrences"] == 2

    # 3. Resolved issues (failed in audit 1, passed in audit 2)
    assert len(data["resolved_issues"]) == 1
    assert data["resolved_issues"][0]["rule_id"] == "exit_path_not_blocked"
    assert data["resolved_issues"][0]["status"] == "resolved"


def test_site_trends_single_audit_notice_and_non_pass_deficiencies(clean_db: Path):
    """With a single audit, trend_notice says 'Trends need at least 2 audits' and open_deficiencies includes all non-pass findings."""
    client = TestClient(app)
    session = next(get_session())

    site = Site(id="site_single_audit", name="Single Audit Warehouse", location_label="Bay 7")
    session.add(site)

    audit = Audit(
        id="audit_single_01",
        site_id="site_single_audit",
        template_id="campus_fire_exit_core",
        status="completed",
        summary_json=json.dumps({"score": 60, "pass_count": 2, "fail_count": 1, "unsure_count": 1}),
    )
    session.add(audit)

    # 1 fail finding
    f_fail = Finding(
        id="f_single_fail",
        audit_id="audit_single_01",
        rule_id="exit_path_not_blocked",
        status="fail",
        confidence=0.88,
        timestamp_s=1.0,
        frame_idx=0,
        severity="high",
        rationale="Blocked pathway",
        final_verdict="fail",
    )
    # 1 needs_review / unsure finding
    f_review = Finding(
        id="f_single_review",
        audit_id="audit_single_01",
        rule_id="extinguisher_accessible",
        status="unsure",
        confidence=0.5,
        timestamp_s=2.0,
        frame_idx=1,
        severity="medium",
        rationale="Partially obscured",
        final_verdict="needs_review",
    )
    # 1 pass finding
    f_pass = Finding(
        id="f_single_pass",
        audit_id="audit_single_01",
        rule_id="exit_sign_visible",
        status="pass",
        confidence=0.99,
        timestamp_s=3.0,
        frame_idx=2,
        severity="high",
        rationale="Clearly visible",
        final_verdict="pass",
    )
    session.add(f_fail)
    session.add(f_review)
    session.add(f_pass)
    session.commit()

    resp = client.get("/api/sites/site_single_audit/trends")
    assert resp.status_code == 200
    data = resp.json()

    # Open deficiencies must equal non-pass findings (fail + needs_review) = 2
    assert len(data["open_issues"]) == 2
    rule_ids = {iss["rule_id"] for iss in data["open_issues"]}
    assert rule_ids == {"exit_path_not_blocked", "extinguisher_accessible"}

    # With a single audit: notice must be present, recurring & resolved must be empty
    assert data["trend_notice"] == "Trends need at least 2 audits"
    assert len(data["recurring_issues"]) == 0
    assert len(data["resolved_issues"]) == 0
