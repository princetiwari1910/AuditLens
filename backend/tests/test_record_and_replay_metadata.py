"""Tests for source_provider_mode fixture stamping, replay derivation, keyframe counts, and voice notes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, init_db
from app.job_runner import replay_demo_audit
from app.models import Audit, Finding, VoiceNote
from scripts.record_demo import record_demo


def test_record_demo_stamps_mock_source_provider_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Recording with PROVIDER_MODE=mock must stamp source_provider_mode='mock'."""
    settings = get_settings()
    monkeypatch.setattr(settings, "PROVIDER_MODE", "mock")

    out_fixture = tmp_path / "mock_recording.json"
    res_path = record_demo(
        template_id="campus_fire_exit_core",
        output_path=out_fixture,
        save_bundled=False,
    )

    assert res_path == out_fixture
    assert out_fixture.exists()

    with open(out_fixture, "r", encoding="utf-8") as fp:
        fixture = json.load(fp)

    assert fixture["source_provider_mode"] == "mock"
    assert "frames_analyzed" in fixture["summary"]
    assert fixture["summary"]["frames_analyzed"] > 0
    assert "frames_considered" in fixture["summary"]
    assert fixture["summary"]["frames_considered"] > 0
    assert len(fixture.get("voice_notes", [])) >= 1

    # Verify at least one finding has voice_note in sources and rationale
    has_vn_finding = any(
        "voice_note" in f.get("sources_json", "") for f in fixture.get("findings", [])
    )
    assert has_vn_finding


def test_record_demo_stamps_record_source_provider_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Recording with PROVIDER_MODE=record must stamp source_provider_mode='record'."""
    settings = get_settings()
    monkeypatch.setattr(settings, "PROVIDER_MODE", "record")

    out_fixture = tmp_path / "record_mode_fixture.json"
    res_path = record_demo(
        template_id="campus_fire_exit_core",
        output_path=out_fixture,
        save_bundled=False,
    )

    assert res_path == out_fixture
    assert out_fixture.exists()

    with open(out_fixture, "r", encoding="utf-8") as fp:
        fixture = json.load(fp)

    assert fixture["source_provider_mode"] == "record"


def test_replay_derives_source_provider_mode_and_voice_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Replaying a fixture with source_provider_mode='record' populates the audit record and voice notes."""
    init_db()
    eng = engine()

    custom_fixture = {
        "recorded_at": "2026-11-01T12:00:00Z",
        "template_id": "campus_fire_exit_core",
        "source_provider_mode": "record",
        "duration_s": 20.0,
        "summary": {
            "score": 90,
            "pass": 3,
            "fail": 1,
            "unsure": 0,
            "frames_analyzed": 14,
            "frames_considered": 28,
        },
        "events": [],
        "findings": [
            {
                "rule_id": "exit_path_not_blocked",
                "status": "fail",
                "confidence": 0.95,
                "timestamp_s": 1.5,
                "frame_idx": 1,
                "measurement_json": None,
                "rationale": "Blocked exit path observed. [Auditor Note: \"Boxes blocking door\"]",
                "fix_text": "Clear the exit route.",
                "severity": "high",
                "sources_json": json.dumps(["segmentation", "voice_note"]),
            }
        ],
        "voice_notes": [
            {
                "timestamp_s": 1.5,
                "transcript": "Boxes blocking door",
                "language": "en",
            }
        ],
    }

    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    fixture_file = fixtures_dir / "demo_recording.json"
    with open(fixture_file, "w", encoding="utf-8") as fp:
        json.dump(custom_fixture, fp)

    settings = get_settings()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)

    import uuid
    audit_id = f"test_replay_{uuid.uuid4().hex[:8]}"
    with Session(eng) as session:
        audit = Audit(
            id=audit_id,
            template_id="campus_fire_exit_core",
            status="queued",
            provider_mode="replay",
            is_replay=True,
        )
        session.add(audit)
        session.commit()

        replay_demo_audit(audit_id, session)

    with Session(eng) as session:
        replayed_audit = session.get(Audit, audit_id)
        assert replayed_audit is not None
        assert replayed_audit.is_replay is True
        assert replayed_audit.source_provider_mode == "record"

        summary = json.loads(replayed_audit.summary_json)
        assert summary["frames_analyzed"] == 14
        assert summary["frames_considered"] == 28

        # Check voice note was saved to db
        vns = session.exec(select(VoiceNote).where(VoiceNote.audit_id == audit_id)).all()
        assert len(vns) == 1
        assert vns[0].transcript == "Boxes blocking door"
        assert vns[0].timestamp_s == 1.5

        # Check finding
        finding = session.exec(select(Finding).where(Finding.audit_id == audit_id)).first()
        assert finding is not None
        assert "voice_note" in json.loads(finding.sources_json)


def test_bundled_fixture_has_mock_source_provider_mode_and_real_frame_counts():
    """The bundled fixture demo_recording.json must have source_provider_mode='mock' and frames counts."""
    bundled_path = Path(__file__).resolve().parent.parent / "app" / "fixtures" / "demo_recording.json"
    assert bundled_path.exists()

    with open(bundled_path, "r", encoding="utf-8") as fp:
        fixture = json.load(fp)

    assert fixture.get("source_provider_mode") == "mock"
    assert fixture.get("summary", {}).get("frames_analyzed", 0) > 0
    assert fixture.get("summary", {}).get("frames_considered", 0) > 0
    assert len(fixture.get("voice_notes", [])) >= 1
