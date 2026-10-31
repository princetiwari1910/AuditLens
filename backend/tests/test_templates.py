"""Unit tests verifying hero scenario safety templates (College Lab & Hostel)."""

from __future__ import annotations

from app.template_loader import get_template, list_templates


def test_hero_templates_exist_and_validate():
    """Verify college_lab_safety and hostel_fire_safety templates exist and have detector/evidence fields."""
    tmpls = list_templates()
    tmpl_ids = [t.id for t in tmpls]
    assert "campus_fire_exit_core" in tmpl_ids
    assert "college_lab_safety" in tmpl_ids
    assert "hostel_fire_safety" in tmpl_ids
    assert "fire_exit_safety" in tmpl_ids

    # College Lab Safety
    lab = get_template("college_lab_safety")
    assert lab is not None
    assert len(lab.rules) >= 5
    for rule in lab.rules:
        assert rule.detector != ""
        assert rule.evidence_needed != ""

    # Hostel Fire Safety
    hostel = get_template("hostel_fire_safety")
    assert hostel is not None
    assert len(hostel.rules) >= 5
    for rule in hostel.rules:
        assert rule.detector != ""
        assert rule.evidence_needed != ""


def test_campus_fire_exit_core_default_template():
    """Verify campus_fire_exit_core has exactly 4 phone-friendly rules and no measurement rules."""
    tmpls = list_templates()
    assert tmpls[0].id == "campus_fire_exit_core", "campus_fire_exit_core must be default first template"

    core = get_template("campus_fire_exit_core")
    assert core is not None
    assert len(core.rules) == 4

    rule_ids = [r.id for r in core.rules]
    expected_ids = [
        "extinguisher_visible",
        "exit_sign_visible",
        "exit_path_not_blocked",
        "extinguisher_accessible",
    ]
    assert rule_ids == expected_ids

    for r in core.rules:
        assert r.type != "measurement", f"Rule {r.id} must not be a measurement rule"
        assert r.detector, f"Rule {r.id} must name its detector"
        assert r.evidence_needed, f"Rule {r.id} must state required evidence"
