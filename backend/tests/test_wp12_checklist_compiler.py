"""Tests for WP12: Natural Language Checklist Compiler with Concept Validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_engine
from app.main import app
from app.providers.base import Reasoner
from app.providers.mock import MockReasoner
from app.providers.record_replay import RecordReplayReasoner


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    return tmp_path


def test_compile_template_plain_language_success(clean_db: Path):
    client = TestClient(app)
    text = (
        "- Verify fire extinguisher is mounted\n"
        "- Ensure illuminated exit sign is visible\n"
        "- Check that storage boxes are absent from egress hallway"
    )

    resp = client.post("/api/templates/compile", json={"text": text})
    assert resp.status_code == 200
    data = resp.json()

    assert data["valid"] is True
    assert len(data["errors"]) == 0

    tmpl = data["template"]
    assert tmpl["status"] == "experimental"
    assert tmpl["human_reviewed"] is True
    assert len(tmpl["rules"]) == 3

    # Check that prompts are valid noun phrases
    for rule in tmpl["rules"]:
        assert len(rule["sam_prompts"]) >= 1
        for prompt in rule["sam_prompts"]:
            assert " and " not in prompt
            assert " or " not in prompt
            assert "not" not in prompt


def test_compile_template_concept_validation_rejection(clean_db: Path):
    client = TestClient(app)

    # 1. Conjunction violation ('and'/'or')
    resp1 = client.post(
        "/api/templates/compile",
        json={"text": "Check hallway for prompt: boxes and pallets"},
    )
    assert resp1.status_code == 422
    err_data1 = resp1.json()["detail"]
    assert any("conjunction" in e for e in err_data1["errors"])

    # 2. Negation violation ('not', 'no')
    resp2 = client.post(
        "/api/templates/compile",
        json={"text": "Inspect prompt: not blocked exit doorway"},
    )
    assert resp2.status_code == 422
    err_data2 = resp2.json()["detail"]
    assert any("negation" in e for e in err_data2["errors"])

    # 3. Spatial words violation ('on the wall', 'in front of')
    resp3 = client.post(
        "/api/templates/compile",
        json={"text": "Inspect prompt: fire extinguisher on the wall"},
    )
    assert resp3.status_code == 422
    err_data3 = resp3.json()["detail"]
    assert any("spatial" in e for e in err_data3["errors"])


def test_compile_empty_text_returns_400(clean_db: Path):
    client = TestClient(app)
    resp = client.post("/api/templates/compile", json={"text": "   "})
    assert resp.status_code == 400


def test_compile_template_compound_or_negated_sentence_warning(clean_db: Path):
    client = TestClient(app)
    # Sentence contains compound conjunction 'and' and negation 'not'
    text = "- Ensure fire extinguisher is mounted and exit hallway is not blocked"
    resp = client.post("/api/templates/compile", json={"text": text})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    # Must return compound or negated statement warning
    assert "warnings" in data
    assert any("Compound or negated statement: split it into separate rules or confirm" in w for w in data["warnings"])
    assert len(data["template"]["rules"]) >= 1


def test_compile_template_separates_condition_and_concept(clean_db: Path):
    client = TestClient(app)
    text = "Verify fire extinguisher is mounted"
    resp = client.post("/api/templates/compile", json={"text": text})
    assert resp.status_code == 200
    rule = resp.json()["template"]["rules"][0]
    # Condition and SAM concept are distinct properties
    assert "condition" in rule
    assert rule["condition"] == "Verify fire extinguisher is mounted"
    assert "sam_prompts" in rule
    assert "fire extinguisher" in rule["sam_prompts"]


def test_record_replay_reasoner_compile_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.providers.record_replay.get_fixtures_dir", lambda: fixtures_dir)

    inner = MockReasoner()
    record_reasoner = RecordReplayReasoner(inner=inner, mode="record")

    text = "Verify fire extinguisher is mounted"
    draft = record_reasoner.compile_template(text)
    assert draft["status"] == "experimental"
    assert draft["human_reviewed"] is True

    # In replay mode: loaded from saved fixture
    replay_reasoner = RecordReplayReasoner(inner=None, mode="replay")
    replayed_draft = replay_reasoner.compile_template(text)
    assert replayed_draft["id"] == draft["id"]
    assert replayed_draft["rules"] == draft["rules"]


def test_meta_agent_provider_compile_template_without_key():
    from app.providers.meta import MetaAgentProvider

    provider = MetaAgentProvider()
    with pytest.raises(ValueError, match="UNVERIFIED against live API"):
        provider.compile_template("Check exit signs")


def test_create_audit_with_invalid_custom_rules_concept(clean_db: Path):
    client = TestClient(app)
    invalid_rules = [
        {
            "id": "rule_1",
            "title": "Check obstacles",
            "sam_prompts": ["boxes and pallets"],
        }
    ]
    resp = client.post(
        "/api/audits",
        data={"custom_rules": json.dumps(invalid_rules)},
        files={"video": ("test.mp4", b"dummy video content", "video/mp4")},
    )
    assert resp.status_code == 422
    assert "conjunction" in resp.json()["detail"]

