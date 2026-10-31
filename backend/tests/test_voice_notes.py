"""Unit tests for voice note recording, transcription stub, and finding attachment."""

from __future__ import annotations

import io
import json
from pathlib import Path
from starlette.testclient import TestClient

from app.db import init_db
from app.main import app
from app.models import Audit, AuditStatus, Finding
from sqlmodel import Session
from app.db import engine


def test_voice_note_transcription_and_finding_attachment(tmp_path, monkeypatch):
    """Uploading a voice note triggers transcription stub and attaches note to nearby finding."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    monkeypatch.setenv("PROVIDER_MODE", "mock")

    init_db()
    eng = engine()
    audit_id = "test_vn_audit"

    # Pre-populate audit and a finding at timestamp_s = 2.0
    with Session(eng) as session:
        audit = Audit(id=audit_id, template_id="fire_exit_safety", status=AuditStatus.COMPLETED.value)
        session.add(audit)
        finding = Finding(
            id="f_test_1",
            audit_id=audit_id,
            rule_id="extinguisher_visible",
            status="pass",
            confidence=0.92,
            timestamp_s=2.0,
            frame_idx=2,
            rationale="Fire extinguisher found on wall.",
            sources_json=json.dumps(["segmentation"]),
        )
        session.add(finding)
        session.commit()

    with TestClient(app) as client:
        # Upload voice note at timestamp 3.0s (within 5s of finding)
        audio_bytes = b"RIFF....WAVEfmt ...."
        resp = client.post(
            f"/api/audits/{audit_id}/voice-notes",
            files={"audio": ("auditor_note.wav", io.BytesIO(audio_bytes), "audio/wav")},
            data={"timestamp_s": "3.0"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["audit_id"] == audit_id
        assert data["transcript"] is not None
        assert "[STUB / MOCK]" in data["transcript"]

    # Verify finding was updated with voice_note source and auditor note rationale
    with Session(eng) as session:
        updated_f = session.get(Finding, "f_test_1")
        assert updated_f is not None
        sources = json.loads(updated_f.sources_json)
        assert "voice_note" in sources
        assert "[Auditor Note:" in updated_f.rationale
        assert "[STUB / MOCK]" in updated_f.rationale
