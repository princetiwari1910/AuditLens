"""Tests for detection cache keys, scenario hash invalidation, and clear-cache functionality."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlmodel import Session, select

from app.agent.tools import ExecutionContext, ToolRegistry
from app.cache import clear_cache_entries, compute_cache_key, get_cached_result
from app.config import get_settings
from app.db import engine, init_db, reset_engine
from app.models import CacheEntry
from app.providers.mock import MockSegmentationProvider, MockTranscriptionProvider


@pytest.fixture
def cache_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine()

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    yield tmp_path

    reset_engine()
    get_settings.cache_clear()


def test_cache_key_includes_scenario_hash_and_version():
    """Verify compute_cache_key produces different keys when scenario_hash or version changes."""
    k1 = compute_cache_key("f_hash_123", "segmentation", "exit door", provider_version="1.0", scenario_hash="hash_a")
    k2 = compute_cache_key("f_hash_123", "segmentation", "exit door", provider_version="1.0", scenario_hash="hash_b")
    k3 = compute_cache_key("f_hash_123", "segmentation", "exit door", provider_version="2.0", scenario_hash="hash_a")
    k_same = compute_cache_key("f_hash_123", "segmentation", "exit door", provider_version="1.0", scenario_hash="hash_a")

    assert k1 != k2, "Changing scenario_hash must produce different cache key"
    assert k1 != k3, "Changing provider_version must produce different cache key"
    assert k1 == k_same, "Identical arguments must produce identical cache key"


def test_changing_scenario_changes_detection_results_without_stale_cache(cache_test_env):
    """
    Verify that updating a scenario file invalidates the detection cache key
    and returns updated detections instead of stale cached data.
    """
    tmp_path = cache_test_env
    scenario_path = tmp_path / "custom_scenario.json"
    dummy_frame = tmp_path / "frame_000.jpg"
    dummy_frame.write_bytes(b"synthetic_jpeg_bytes_001")

    # 1. Scenario v1: Exit door has high score (0.95 -> Pass)
    v1_items = [
        {
            "prompt": "exit door",
            "aliases": ["emergency exit"],
            "start_s": 0.0,
            "end_s": 5.0,
            "bbox": {"x": 0.4, "y": 0.2, "w": 0.15, "h": 0.35},
            "score": 0.95,
        }
    ]
    scenario_path.write_text(json.dumps(v1_items), encoding="utf-8")

    eng = engine()
    with Session(eng) as session:
        provider_v1 = MockSegmentationProvider(scenario_file=scenario_path)
        ctx = ExecutionContext(
            audit_id="audit_cache_test",
            rules=[],
            frames=[{"idx": 0, "path": str(dummy_frame), "timestamp_s": 1.0, "sha256": "hash_frame_0"}],
            segmentation_provider=provider_v1,
            transcription_provider=MockTranscriptionProvider(),
            session=session,
        )
        registry = ToolRegistry(ctx)

        # First query with v1
        res_v1 = registry.execute("find_objects", prompt="exit door")
        dets_v1 = res_v1["detections"]
        assert len(dets_v1) == 1
        assert dets_v1[0]["score"] == 0.95

        # Confirm result was written to CacheEntry
        entries = session.exec(select(CacheEntry)).all()
        assert len(entries) >= 1
        hash_v1 = provider_v1.scenario_hash

    # 2. Scenario v2: Exit door updated to marginal score (0.45 -> Unsure)
    v2_items = [
        {
            "prompt": "exit door",
            "aliases": ["emergency exit"],
            "start_s": 0.0,
            "end_s": 5.0,
            "bbox": {"x": 0.4, "y": 0.2, "w": 0.15, "h": 0.35},
            "score": 0.45,
        }
    ]
    scenario_path.write_text(json.dumps(v2_items), encoding="utf-8")

    with Session(eng) as session:
        provider_v2 = MockSegmentationProvider(scenario_file=scenario_path)
        assert provider_v2.scenario_hash != hash_v1, "Scenario hash must update after file modification"

        ctx2 = ExecutionContext(
            audit_id="audit_cache_test_2",
            rules=[],
            frames=[{"idx": 0, "path": str(dummy_frame), "timestamp_s": 1.0, "sha256": "hash_frame_0"}],
            segmentation_provider=provider_v2,
            transcription_provider=MockTranscriptionProvider(),
            session=session,
        )
        registry2 = ToolRegistry(ctx2)

        # Query with v2: MUST NOT return stale 0.95
        res_v2 = registry2.execute("find_objects", prompt="exit door")
        dets_v2 = res_v2["detections"]
        assert len(dets_v2) == 1
        assert dets_v2[0]["score"] == 0.45, f"Expected 0.45 from updated scenario, got stale score: {dets_v2[0]['score']}"


def test_clear_cache_entries(cache_test_env):
    """Verify clear_cache_entries deletes all rows from the cache_entry table."""
    eng = engine()
    with Session(eng) as session:
        e1 = CacheEntry(key="k1", provider="p", prompt="p", result_json="[]")
        e2 = CacheEntry(key="k2", provider="p", prompt="p", result_json="[]")
        session.add(e1)
        session.add(e2)
        session.commit()

        entries_before = session.exec(select(CacheEntry)).all()
        assert len(entries_before) == 2

        count = clear_cache_entries(session)
        assert count == 2

        entries_after = session.exec(select(CacheEntry)).all()
        assert len(entries_after) == 0
