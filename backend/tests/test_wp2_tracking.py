"""Unit tests for WP2: Object tracking across keyframes and temporal consensus."""

import pytest
from app.agent.tracking import (
    ObjectTracker,
    Track,
    compute_iou,
    evaluate_temporal_consensus,
)
from app.config import Settings


# ── 1. IoU Calculation ────────────────────────────────────────────────────────

def test_compute_iou_geometry():
    # Identical boxes -> IoU = 1.0
    box_a = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    box_b = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    assert round(compute_iou(box_a, box_b), 2) == 1.0

    # Non-overlapping boxes -> IoU = 0.0
    box_c = {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}
    assert compute_iou(box_a, box_c) == 0.0

    # 50% partial overlap
    box_d = {"x": 0.2, "y": 0.1, "w": 0.2, "h": 0.2}
    # intersection: x in [0.2, 0.3], y in [0.1, 0.3] -> w=0.1, h=0.2, area=0.02
    # union: 0.04 + 0.04 - 0.02 = 0.06 -> iou = 0.02 / 0.06 = 0.333
    assert round(compute_iou(box_a, box_d), 2) == 0.33

    # None or empty box
    assert compute_iou(None, box_a) == 0.0
    assert compute_iou(box_a, None) == 0.0


# ── 2. Tracker: Flicker, Duplicates, Lost & Recovered ─────────────────────────

def test_tracker_flicker_recovers_single_track():
    """Flicker test: object detected at frame 0, absent at frame 1, seen at frame 2."""
    tracker = ObjectTracker(iou_threshold=0.3, max_gap_frames=2)
    dets = [
        {"frame_id": 0, "timestamp_s": 0.0, "prompt": "fire extinguisher", "score": 0.85, "bbox": {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3}},
        # frame 1 missed
        {"frame_id": 2, "timestamp_s": 2.0, "prompt": "fire extinguisher", "score": 0.90, "bbox": {"x": 0.11, "y": 0.21, "w": 0.15, "h": 0.3}},
    ]
    tracks = tracker.track(dets)
    assert len(tracks) == 1, "Flicker within gap tolerance should link to 1 physical track"
    assert tracks[0].support_count == 2
    assert tracks[0].start_frame == 0
    assert tracks[0].end_frame == 2


def test_tracker_duplicates_on_same_frame_become_separate_tracks():
    """Two extinguishers in the same room on the same frame become distinct tracks."""
    tracker = ObjectTracker(iou_threshold=0.3, max_gap_frames=2)
    dets = [
        {"frame_id": 0, "timestamp_s": 0.0, "prompt": "fire extinguisher", "score": 0.92, "bbox": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.2}},
        {"frame_id": 0, "timestamp_s": 0.0, "prompt": "fire extinguisher", "score": 0.88, "bbox": {"x": 0.7, "y": 0.2, "w": 0.1, "h": 0.2}},
        {"frame_id": 1, "timestamp_s": 1.0, "prompt": "fire extinguisher", "score": 0.91, "bbox": {"x": 0.11, "y": 0.2, "w": 0.1, "h": 0.2}},
        {"frame_id": 1, "timestamp_s": 1.0, "prompt": "fire extinguisher", "score": 0.85, "bbox": {"x": 0.72, "y": 0.2, "w": 0.1, "h": 0.2}},
    ]
    tracks = tracker.track(dets)
    assert len(tracks) == 2, "Two distinct spatial objects must produce 2 independent tracks"
    assert all(t.support_count == 2 for t in tracks)


def test_tracker_lost_beyond_gap_tolerance_starts_new_track():
    """If gap exceeds max_gap_frames, a new track must be started."""
    tracker = ObjectTracker(iou_threshold=0.3, max_gap_frames=2)
    dets = [
        {"frame_id": 0, "timestamp_s": 0.0, "prompt": "fire extinguisher", "score": 0.85, "bbox": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.2}},
        # gap = 4 frames (frame 4 - frame 0 = 4 > max_gap 2)
        {"frame_id": 4, "timestamp_s": 4.0, "prompt": "fire extinguisher", "score": 0.88, "bbox": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.2}},
    ]
    tracks = tracker.track(dets)
    assert len(tracks) == 2, "Gap exceeding tolerance must start a fresh track"


# ── 3. Temporal Consensus Evaluation ──────────────────────────────────────────

def test_temporal_consensus_k_of_n_and_confidence():
    track_strong = Track(
        concept="fire extinguisher",
        detections=[
            {"frame_id": 1, "timestamp_s": 1.0, "score": 0.90, "bbox": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.2}},
            {"frame_id": 2, "timestamp_s": 2.0, "score": 0.95, "bbox": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.2}},
            {"frame_id": 3, "timestamp_s": 3.0, "score": 0.92, "bbox": {"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.2}},
        ],
        start_frame=1,
        end_frame=3,
        start_ts=1.0,
        end_ts=3.0,
    )

    consensus = evaluate_temporal_consensus([track_strong], total_frames=5, min_k=2, min_confidence=0.7)
    assert consensus["has_consensus"] is True
    assert consensus["support_count"] == 3
    assert consensus["best_evidence_frame"] == 2  # frame 2 has highest score 0.95
    assert consensus["best_detection"]["score"] == 0.95
    assert consensus["stability"] == 1.0  # seen in all 3 frames from 1 to 3


def test_temporal_consensus_insufficient_frames():
    track_weak = Track(
        concept="exit sign",
        detections=[
            {"frame_id": 0, "timestamp_s": 0.0, "score": 0.80, "bbox": {"x": 0.4, "y": 0.1, "w": 0.2, "h": 0.1}},
        ],
        start_frame=0,
        end_frame=0,
    )
    consensus = evaluate_temporal_consensus([track_weak], total_frames=4, min_k=2, min_confidence=0.6)
    assert consensus["has_consensus"] is False, "Support count 1 does not satisfy min_k=2"
    assert consensus["support_count"] == 1


# ── 4. Config Flag ────────────────────────────────────────────────────────────

def test_tracking_config_flag(monkeypatch):
    monkeypatch.setenv("ENABLE_TRACKING", "false")
    s = Settings()
    assert s.ENABLE_TRACKING is False
