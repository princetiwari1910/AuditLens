"""Unit tests for Provider Contracts (Segmenter, Reasoner, Transcriber) and Record/Replay wrapper."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import init_db
from app.main import app
from app.providers.base import (
    Detection,
    SegmentDetection,
    Segmenter,
    Reasoner,
    Transcriber,
    Transcript,
)
from app.providers.meta import (
    MetaSegmenter,
    MetaReasoner,
    MetaTranscriber,
)
from app.providers.mock import (
    MockSegmenter,
    MockReasoner,
    MockTranscriber,
)
from app.providers.record_replay import (
    RecordReplaySegmenter,
    RecordReplayReasoner,
    RecordReplayTranscriber,
)


def test_meta_provider_raises_not_implemented():
    """Meta providers must strictly raise NotImplementedError with TODO(meta)."""
    seg = MetaSegmenter()
    with pytest.raises(NotImplementedError) as exc_seg:
        seg.segment("dummy_img.jpg", ["fire extinguisher"])
    assert "TODO(meta)" in str(exc_seg.value)

    reasoner = MetaReasoner()
    with pytest.raises(NotImplementedError) as exc_reason:
        reasoner.judge({"title": "Test rule"}, {})
    assert "TODO(meta)" in str(exc_reason.value)

    transcriber = MetaTranscriber()
    with pytest.raises(NotImplementedError) as exc_trans:
        transcriber.transcribe("dummy_audio.wav")
    assert "TODO(meta)" in str(exc_trans.value)


def test_mock_provider_implements_interfaces():
    """Mock providers implement Segmenter, Reasoner, and Transcriber interfaces."""
    seg = MockSegmenter()
    assert isinstance(seg, Segmenter)
    detections = seg.segment("dummy.jpg", ["extinguisher"])
    assert isinstance(detections, list)

    reasoner = MockReasoner()
    assert isinstance(reasoner, Reasoner)
    verdict = reasoner.judge({"title": "Check exit", "type": "presence"}, [{"frame_id": 1}])
    assert "verdict" in verdict
    assert verdict["verdict"] in ("pass", "fail", "unsure")
    assert "reason" in verdict
    assert "cited_frames" in verdict

    transcriber = MockTranscriber()
    assert isinstance(transcriber, Transcriber)
    trans = transcriber.transcribe("dummy.wav")
    assert isinstance(trans, Transcript)
    assert len(trans.turns) > 0
    assert trans.turns[0].text


def test_record_replay_segmenter(tmp_path, monkeypatch):
    """Record mode saves fixture to disk; replay mode loads without calling inner provider."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    get_settings.cache_clear()

    mock_seg = MockSegmenter()

    # 1. Record mode
    recorder = RecordReplaySegmenter(mock_seg, mode="record")
    recorded_dets = recorder.find_objects(["dummy_frame.jpg"], "fire extinguisher")
    assert isinstance(recorded_dets, list)

    # Verify fixture file was created
    fixtures = list((data_dir / "fixtures").glob("*.json"))
    assert len(fixtures) == 1
    with open(fixtures[0], "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert "detections" in saved_data
    assert saved_data["prompt"] == "fire extinguisher"

    # 2. Replay mode
    class FailingSegmenter:
        def find_objects(self, *args, **kwargs):
            raise AssertionError("Inner provider must NOT be called in replay mode!")

    replayer = RecordReplaySegmenter(FailingSegmenter(), mode="replay")
    replayed_dets = replayer.find_objects(["dummy_frame.jpg"], "fire extinguisher")
    assert len(replayed_dets) == len(recorded_dets)
    assert replayed_dets[0].prompt == recorded_dets[0].prompt

    # 3. Missing fixture raises FileNotFoundError in replay mode
    with pytest.raises(FileNotFoundError):
        replayer.find_objects(["unrecorded_frame.jpg"], "unrecorded prompt")


def test_record_replay_reasoner(tmp_path, monkeypatch):
    """Reasoner record and replay saves and loads verdict."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    get_settings.cache_clear()

    mock_reasoner = MockReasoner()
    rule = {"id": "rule_1", "type": "presence", "title": "Check Extinguisher"}
    evidence = [{"frame_id": 0, "score": 0.95}]

    # Record
    recorder = RecordReplayReasoner(mock_reasoner, mode="record")
    res1 = recorder.judge(rule, evidence)
    assert res1["verdict"] == "pass"

    # Replay
    class FailingReasoner:
        def judge(self, *args, **kwargs):
            raise AssertionError("Must not call network or inner provider during replay!")

    replayer = RecordReplayReasoner(FailingReasoner(), mode="replay")
    res2 = replayer.judge(rule, evidence)
    assert res2 == res1


def test_model_api_key_not_logged_or_exposed_in_health(monkeypatch):
    """MODEL_API_KEY must never be returned in /api/health."""
    monkeypatch.setenv("MODEL_API_KEY", "secret_meta_api_key_12345")
    get_settings.cache_clear()
    init_db()

    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "secret_meta_api_key_12345" not in json.dumps(data)
        assert "MODEL_API_KEY" not in data
        assert "api_key" not in str(data).lower()
