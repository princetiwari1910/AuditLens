"""Tests for Task 1: SAM concurrency, Retry-After handling, image downscaling, and live keyframe caps."""

from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from app.config import get_settings
from app.frames import sample_frames_from_video
from app.providers.base import Detection
from app.providers.client import execute_with_retry, get_image_semaphore, is_retryable_error
from app.providers.meta import (
    MetaSegmentationProvider,
    encode_image_to_base64_data_url,
)


def test_sam_concurrency_semaphore_honors_env_default(monkeypatch):
    """Verify SAM concurrency semaphore defaults to 8 and is configurable via env."""
    settings = get_settings()
    assert settings.SAM_CONCURRENCY == 8

    # Ensure semaphore uses SAM_CONCURRENCY
    import app.providers.client as client_module

    client_module._image_semaphore = None
    sem = client_module.get_image_semaphore()
    assert sem._value == 8

    # Check env override
    monkeypatch.setenv("SAM_CONCURRENCY", "12")
    get_settings.cache_clear()
    client_module._image_semaphore = None
    sem2 = client_module.get_image_semaphore()
    assert sem2._value == 12

    # Clean up cache
    monkeypatch.delenv("SAM_CONCURRENCY", raising=False)
    get_settings.cache_clear()
    client_module._image_semaphore = None


def test_execute_with_retry_honors_retry_after():
    """Verify that execute_with_retry honors Retry-After on 429 rate limit."""
    call_times: list[float] = []

    class RateLimitError(Exception):
        status_code = 429
        retry_after = 0.15

    def flappy_provider_call():
        call_times.append(time.perf_counter())
        if len(call_times) < 2:
            raise RateLimitError("Rate limit exceeded (429)")
        return "success"

    res = execute_with_retry(
        flappy_provider_call,
        max_retries=2,
        base_delay=0.01,
        audit_id="test_retry",
    )
    assert res == "success"
    assert len(call_times) == 2
    # Delay between attempt 1 and attempt 2 should be at least retry_after (0.15s)
    elapsed = call_times[1] - call_times[0]
    assert elapsed >= 0.14


def test_encode_image_resizes_long_side_to_960(tmp_path):
    """Verify that images larger than 960px on the long side are downscaled to 960px."""
    # Create large 1920x1080 test image
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.circle(img, (960, 540), 200, (0, 0, 255), -1)
    img_path = tmp_path / "large_frame.jpg"
    cv2.imwrite(str(img_path), img)

    data_url, width, height, raw_bytes = encode_image_to_base64_data_url(img_path)

    # Long side should be exactly 960
    assert width == 960
    assert height == 540
    assert data_url.startswith("data:image/jpeg;base64,")


def test_live_mode_caps_keyframes_at_12(tmp_path, monkeypatch):
    """Verify that in live/record mode, sample_frames_from_video caps keyframes at 12."""
    from scripts.make_sample_video import generate_sample_video

    vid_path = tmp_path / "test_walkthrough.mp4"
    generate_sample_video(vid_path, duration_s=15)

    monkeypatch.setenv("PROVIDER_MODE", "record")
    get_settings.cache_clear()

    frames = sample_frames_from_video(
        video_path=vid_path,
        audit_id="test_cap",
        fps=2.0,
        min_gap_s=0.1,
        min_sharpness=0.0,
    )

    # Must be capped at LIVE_MAX_KEYFRAMES (12)
    assert len(frames) <= 12

    get_settings.cache_clear()


def test_find_objects_runs_concurrently(tmp_path):
    """Verify that find_objects processes multiple frames concurrently."""
    seg = MetaSegmentationProvider()

    # Create 4 small test frames
    frame_paths = []
    for i in range(4):
        f = tmp_path / f"f_{i}.jpg"
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.imwrite(str(f), img)
        frame_paths.append(str(f))

    active_threads: set[int] = set()

    def mock_segment(img_path, prompts):
        active_threads.add(threading.get_ident())
        time.sleep(0.05)
        return []

    with patch.object(seg, "segment", side_effect=mock_segment):
        dets = seg.find_objects(frame_paths, prompt="fire extinguisher")
        assert dets == []
        # When concurrent, multiple worker threads should have run
        assert len(active_threads) > 1
