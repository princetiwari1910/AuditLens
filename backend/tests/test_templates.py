"""Unit tests verifying hero scenario safety templates (College Lab & Hostel)."""

from __future__ import annotations

from app.template_loader import get_template, list_templates


def test_hero_templates_exist_and_validate():
    """Verify college_lab_safety and hostel_fire_safety templates exist and have detector/evidence fields."""
    tmpls = list_templates()
    tmpl_ids = [t.id for t in tmpls]
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
