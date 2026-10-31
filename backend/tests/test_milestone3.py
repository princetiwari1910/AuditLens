"""Tests for Milestone 3: providers (mock and meta), caching, and cost logging."""

import re
import pytest
from sqlmodel import Session, select

from app.cache import CacheReport, compute_cache_key, get_cached_result, set_cached_result
from app.config import get_settings
from app.costlog import get_audit_cost_summary, log_cost
from app.db import engine, init_db, reset_engine
from app.models import CacheEntry, CostLog
from app.providers.meta import (
    ERR_MSG,
    MetaAgentProvider,
    MetaSegmentationProvider,
    MetaTranscriptionProvider,
)
from app.providers.mock import MockSegmentationProvider, MockTranscriptionProvider


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Isolate database for test execution."""
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def test_mock_segmentation_scenario_matches():
    """Verify scenario items (fire extinguisher, exit sign, box) return high quality detections."""
    provider = MockSegmentationProvider()
    frame_paths = [f"/path/frame_{i}.jpg" for i in range(15)]
    timestamps = [float(i) for i in range(15)]

    # Fire extinguisher is present between 0s and 9s in scenario
    ext_dets = provider.find_objects(frame_paths, prompt="fire extinguisher", timestamps_s=timestamps)
    assert len(ext_dets) > 0
    assert all(d.score >= 0.8 for d in ext_dets)
    assert ext_dets[0].bbox["w"] > 0
    assert ext_dets[0].bbox["h"] > 0

    # Emergency exit sign is present between 2s and 15s in scenario
    sign_dets = provider.find_objects(frame_paths, prompt="emergency exit sign", timestamps_s=timestamps)
    assert len(sign_dets) > 0
    assert all(d.score >= 0.9 for d in sign_dets)

    # Box (blocking obstacle) is present between 8s and 21s
    box_dets = provider.find_objects(frame_paths, prompt="box", timestamps_s=timestamps)
    assert len(box_dets) > 0

    # Low confidence scenario items leading to 'unsure' (score between 0.35 and 0.55)
    cable_dets = provider.find_objects(frame_paths, prompt="loose cable", timestamps_s=timestamps)
    assert len(cable_dets) > 0
    assert any(0.3 <= d.score < 0.6 for d in cable_dets)


def test_mock_segmentation_different_prompts_yield_different_results():
    """Verify that different non-scenario prompts return distinctly different deterministic detections."""
    provider = MockSegmentationProvider()
    frame_paths = [f"/path/frame_{i}.jpg" for i in range(20)]
    timestamps = [float(i) for i in range(20)]

    dets_ladder = provider.find_objects(frame_paths, prompt="aluminum ladder", timestamps_s=timestamps)
    dets_spill = provider.find_objects(frame_paths, prompt="chemical chemical spill puddle", timestamps_s=timestamps)

    # Both must be deterministic
    dets_ladder_repeat = provider.find_objects(frame_paths, prompt="aluminum ladder", timestamps_s=timestamps)
    assert [d.score for d in dets_ladder] == [d.score for d in dets_ladder_repeat]
    assert [d.bbox for d in dets_ladder] == [d.bbox for d in dets_ladder_repeat]

    # Different prompts MUST produce different detection lists / coordinates
    ladder_scores = [d.score for d in dets_ladder]
    spill_scores = [d.score for d in dets_spill]
    assert ladder_scores != spill_scores or len(dets_ladder) != len(dets_spill)


def test_mock_transcription_returns_hinglish():
    """Verify MockTranscriptionProvider returns the expected Hinglish transcript with segments."""
    provider = MockTranscriptionProvider()
    transcript = provider.transcribe("/path/dummy.wav")
    assert "Main entrance" in transcript.text
    assert "fire extinguisher" in transcript.text
    assert transcript.language == "hi-en"
    assert len(transcript.segments) >= 2


def test_meta_providers_raise_not_implemented():
    """Verify Meta providers raise NotImplementedError with the official prompt message."""
    seg = MetaSegmentationProvider()
    with pytest.raises(NotImplementedError, match=re.escape(ERR_MSG)):
        seg.find_objects(["/dummy.jpg"], "exit")

    asr = MetaTranscriptionProvider()
    with pytest.raises(NotImplementedError, match=re.escape(ERR_MSG)):
        asr.transcribe("/dummy.wav")

    agent = MetaAgentProvider()
    with pytest.raises(NotImplementedError, match=re.escape(ERR_MSG)):
        agent.run_audit(None, [], None, lambda x: None)


def test_cache_hits_and_misses():
    """Verify cache computation, miss on first call, hit on second call."""
    eng = engine()
    report = CacheReport()

    with Session(eng) as session:
        frame_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        provider_name = "mock_sam"
        prompt = "fire extinguisher"

        key = compute_cache_key(frame_hash, provider_name, prompt)
        assert len(key) == 64

        # 1. First lookup: Miss
        miss_res = get_cached_result(session, key, report)
        assert miss_res is None
        assert report.misses == 1
        assert report.hits == 0

        # 2. Store result
        mock_result = [{"score": 0.95, "bbox": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}}]
        saved = set_cached_result(session, key, provider_name, prompt, mock_result)
        assert saved.key == key

        # 3. Second lookup: Hit
        hit_res = get_cached_result(session, key, report)
        assert hit_res is not None
        assert hit_res == mock_result
        assert report.hits == 1
        assert report.misses == 1
        assert report.hit_rate == 0.5


def test_cost_log_written_and_calculated():
    """Verify cost_log entries are written with correct unit prices and summary works."""
    eng = engine()
    audit_id = "audit_cost_test_01"

    with Session(eng) as session:
        # Log segmentation for 25 frames
        entry1 = log_cost(session, provider="mock_sam", operation="segmentation", units=25.0, audit_id=audit_id)
        assert entry1.id is not None
        # 25 frames * 0.002 = 0.05
        assert entry1.est_cost_usd == 0.05

        # Log transcription for 2 minutes of audio
        entry2 = log_cost(session, provider="mock_asr", operation="transcription", units=2.0, audit_id=audit_id)
        # 2 min * 0.006 = 0.012
        assert entry2.est_cost_usd == 0.012

        # Verify summary
        summary = get_audit_cost_summary(session, audit_id)
        assert summary["total_calls"] == 2
        assert summary["total_cost_usd"] == 0.062
        assert "mock_sam" in summary["by_provider"]
        assert "mock_asr" in summary["by_provider"]
