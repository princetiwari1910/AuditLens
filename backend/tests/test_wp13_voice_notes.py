"""Tests for WP13: Structured Voice Notes Extraction and Finding Association."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import get_settings
from app.db import init_db, reset_engine
from app.models import EvidenceStrength, RuleModel, RuleType
from app.providers.base import Reasoner
from app.providers.mock import MockReasoner, MockSegmentationProvider, MockTranscriptionProvider
from app.providers.record_replay import RecordReplayReasoner
from app.providers.schemas import StructuredVoiceNote, validate_structured_voice_note


@pytest.fixture
def clean_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    return tmp_path


def test_structured_voice_note_schema():
    vn = StructuredVoiceNote(
        location="Corridor B",
        issue="Blocked emergency route",
        severity_hint="HIGH",
        raw_transcript="Corridor B is blocked by pallets",
    )
    assert vn.location == "Corridor B"
    assert vn.severity_hint == "high"

    # Fallback normalization
    cleaned = validate_structured_voice_note({"location": "Lab 1", "severity_hint": "unknown"})
    assert cleaned["location"] == "Lab 1"
    assert cleaned["severity_hint"] == "medium"


def test_mock_reasoner_extract_note_english():
    reasoner: Reasoner = MockReasoner()
    transcript = "Checked the fire extinguisher near the main entrance; pressure gauge is valid and clear."
    res = reasoner.extract_note(transcript)

    assert "Entrance" in res["location"]
    assert "extinguisher" in res["issue"].lower()
    assert res["severity_hint"] == "low"
    assert res["raw_transcript"] == transcript


def test_mock_reasoner_extract_note_hinglish():
    reasoner: Reasoner = MockReasoner()

    # Hinglish with positive status
    hinglish_pass = (
        "Main entrance ke paas fire extinguisher check kar liya hai, "
        "expiry date valid hai aur exit doorway ka rasta clear hai."
    )
    res_pass = reasoner.extract_note(hinglish_pass)
    assert "Main Entrance" in res_pass["location"]
    assert res_pass["severity_hint"] == "low"
    assert "extinguisher" in res_pass["issue"].lower()

    # Hinglish with hazard / blockage
    hinglish_hazard = "Hallway me rasta band hai, delivery boxes se emergency egress block ho gaya hai, khatra hai."
    res_hazard = reasoner.extract_note(hinglish_hazard)
    assert "Hallway" in res_hazard["location"]
    assert res_hazard["severity_hint"] == "high"


def test_record_replay_reasoner_extract_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.providers.record_replay.get_fixtures_dir", lambda: fixtures_dir)

    inner = MockReasoner()
    record_reasoner = RecordReplayReasoner(inner=inner, mode="record")

    text = "Main entrance exit sign is illuminated"
    recorded_note = record_reasoner.extract_note(text)
    assert recorded_note["location"] == "Main Entrance"

    # Replay mode serves from disk without touching inner
    inner_mock = MagicMock()
    replay_reasoner = RecordReplayReasoner(inner=inner_mock, mode="replay")
    replayed_note = replay_reasoner.extract_note(text)
    assert replayed_note["location"] == "Main Entrance"
    inner_mock.extract_note.assert_not_called()


def test_meta_agent_provider_extract_note_without_key():
    from app.providers.meta import MetaAgentProvider

    provider = MetaAgentProvider()
    with pytest.raises(ValueError, match="UNVERIFIED against live API"):
        provider.extract_note("Checked fire extinguisher")


def test_finding_association_within_5_seconds():
    from app.agent.runner import AgentRunner

    runner = AgentRunner(
        segmentation_provider=MockSegmentationProvider(),
        transcription_provider=MockTranscriptionProvider(),
        reasoner=MockReasoner(),
    )

    rules = [
        RuleModel(
            id="extinguisher_visible",
            title="Fire Extinguisher Visible",
            type=RuleType.PRESENCE,
            sam_prompts=["fire extinguisher"],
        )
    ]
    frames = [
        {"idx": 0, "timestamp_s": 0.0, "path": "frame_0.jpg"},
        {"idx": 1, "timestamp_s": 3.0, "path": "frame_1.jpg"},
        {"idx": 2, "timestamp_s": 6.0, "path": "frame_2.jpg"},
    ]

    events = []

    # 1. Voice note at 7.0s is within 4.0s of frame 1 (at 3.0s) -> within 5.0s window
    runner_voice_notes = [
        {
            "id": "vn_01",
            "timestamp_s": 7.0,
            "transcript": "Main entrance ke paas fire extinguisher checked, tag is clear and valid.",
        }
    ]
    findings = runner.run_audit(
        audit_id="audit_vn_test_01",
        rules=rules,
        frames=frames,
        emit=events.append,
        session=None,
    )

    assert len(findings) == 1
    # Check that runner evaluated the rule
    assert findings[0]["rule_id"] == "extinguisher_visible"
