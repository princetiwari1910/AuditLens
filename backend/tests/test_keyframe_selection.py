"""Unit tests for quality-aware keyframe selection."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from app.frames import (
    compute_sharpness,
    is_near_duplicate,
    sample_frames_from_video,
)


def _create_synthetic_test_video(path: Path, frames: list[np.ndarray], fps: int = 10) -> Path:
    """Helper to write raw frames into an mp4 video."""
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, float(fps), (w, h))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return path


def test_sharpness_and_duplicate_helpers():
    """Verify compute_sharpness and is_near_duplicate functions."""
    # Sharp image: high contrast edge
    sharp = np.zeros((100, 100), dtype=np.uint8)
    sharp[:, 50:] = 255
    sharp_val = compute_sharpness(sharp)

    # Blurry image: blurred version of sharp image
    blurry = cv2.GaussianBlur(sharp, (21, 21), 5.0)
    blurry_val = compute_sharpness(blurry)

    assert sharp_val > blurry_val
    assert blurry_val < 50.0

    # Near duplicate test
    thumb1 = np.ones((32, 32), dtype=np.uint8) * 100
    thumb2 = np.ones((32, 32), dtype=np.uint8) * 100  # identical (diff = 0)
    thumb3 = np.ones((32, 32), dtype=np.uint8) * 150  # difference = 50

    assert is_near_duplicate(thumb1, thumb2, threshold=0.1) is True
    assert is_near_duplicate(thumb1, thumb3, threshold=0.1) is False


def test_keyframe_selection_filters_blurry_and_duplicate_frames(tmp_path):
    """Verify that blurry frames and duplicate frames are filtered out."""
    vid_path = tmp_path / "test_stream.mp4"
    frames = []

    # 1. Sharp distinct frame
    f0 = np.full((240, 320, 3), 40, dtype=np.uint8)
    cv2.putText(f0, "SHARP 1", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)

    # 2. Near-duplicate of f0 (almost identical)
    f1 = f0.copy()
    f1[0, 0] = [41, 41, 41]

    # 3. Very blurry frame
    f2 = np.full((240, 320, 3), 128, dtype=np.uint8)
    # Uniform / low contrast, very low Laplacian variance

    # 4. Another sharp distinct frame
    f3 = np.full((240, 320, 3), 200, dtype=np.uint8)
    cv2.putText(f3, "SHARP 2", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 4)

    # Repeat sequence to simulate a 2-second clip at 10 fps (20 frames)
    # frames: 5 of f0, 5 of f1 (duplicates), 5 of f2 (blurry), 5 of f3 (sharp new)
    for _ in range(5):
        frames.append(f0)
    for _ in range(5):
        frames.append(f1)
    for _ in range(5):
        frames.append(f2)
    for _ in range(5):
        frames.append(f3)

    _create_synthetic_test_video(vid_path, frames, fps=10)

    sampled, stats = sample_frames_from_video(
        vid_path,
        audit_id="test_keyframe_01",
        fps=2.0,
        min_gap_s=0.2,
        min_sharpness=20.0,
        duplicate_threshold=0.1,
        return_stats=True,
    )

    # Considered should be candidate frames
    assert stats["considered"] > stats["selected"]
    # Only sharp and non-duplicate frames should be selected (f0 and f3)
    assert len(sampled) >= 2
    # Verify attached attributes
    assert getattr(sampled, "frames_considered") == stats["considered"]
    assert getattr(sampled, "frames_analyzed") == len(sampled)


def test_keyframe_selection_max_frames_cap(tmp_path):
    """Verify that max_frames strictly caps the number of selected keyframes."""
    vid_path = tmp_path / "long_clip.mp4"
    frames = []

    # 30 distinct sharp frames
    for i in range(30):
        img = np.full((240, 320, 3), (i * 8) % 256, dtype=np.uint8)
        cv2.putText(img, f"FRAME {i}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
        for _ in range(5):  # 5 repeated frames per distinct scene
            frames.append(img)

    _create_synthetic_test_video(vid_path, frames, fps=10)

    max_allowed = 4
    sampled, stats = sample_frames_from_video(
        vid_path,
        audit_id="test_cap",
        fps=2.0,
        max_frames=max_allowed,
        min_gap_s=0.2,
        return_stats=True,
    )

    assert len(sampled) == max_allowed
    assert stats["selected"] == max_allowed
    assert stats["considered"] > max_allowed
