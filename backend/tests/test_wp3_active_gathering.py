"""Unit tests for WP3: Active evidence gathering bounded agentic loop."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from app.agent.escalation import (
    generate_2x2_tiles,
    map_tile_box_to_full,
    nms_merge,
    run_active_evidence_gathering,
)
from app.providers.base import Detection
from app.providers.client import BudgetExceededError


@pytest.fixture
def sample_image(tmp_path: Path) -> str:
    """Create a temporary 640x480 test image."""
    img_path = tmp_path / "test_frame.jpg"
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw a distinct rectangle in top-right quadrant
    cv2.rectangle(img, (350, 50), (450, 150), (0, 255, 0), -1)
    cv2.imwrite(str(img_path), img)
    return str(img_path)


# ── 1. Zoom Tile Geometry & Box Mapping ───────────────────────────────────────

def test_generate_2x2_tiles_and_mapping(sample_image: str, tmp_path: Path):
    tiles_dir = tmp_path / "tiles"
    tiles = generate_2x2_tiles(sample_image, tiles_dir, overlap=0.10)
    assert len(tiles) == 4, "Must generate exactly 4 quadrants (2x2)"

    # Names should be tl, tr, bl, br
    names = [t["name"] for t in tiles]
    assert names == ["tl", "tr", "bl", "br"]

    # Test coordinate mapping: box in center of top-right tile
    tr_tile = next(t for t in tiles if t["name"] == "tr")
    tile_box = {"x": 0.2, "y": 0.3, "w": 0.4, "h": 0.4}
    full_box = map_tile_box_to_full(tile_box, tr_tile)

    assert 0.0 <= full_box["x"] <= 1.0
    assert 0.0 <= full_box["y"] <= 1.0
    assert full_box["w"] > 0 and full_box["h"] > 0
    # Top-right tile x_offset is > 0.4
    assert full_box["x"] >= tr_tile["x_offset"]


def test_nms_merge():
    dets = [
        {"bbox": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}, "score": 0.90},
        {"bbox": {"x": 0.11, "y": 0.11, "w": 0.2, "h": 0.2}, "score": 0.85},  # duplicate
        {"bbox": {"x": 0.7, "y": 0.7, "w": 0.2, "h": 0.2}, "score": 0.88},  # distinct
    ]
    merged = nms_merge(dets, iou_thresh=0.4)
    assert len(merged) == 2, "NMS must suppress overlapping duplicate"
    assert merged[0]["score"] == 0.90


# ── 2. Active Evidence Gathering Bounded Loop ─────────────────────────────────

class TileAwareMockSegmenter:
    """Mock segmenter that misses at full frame but succeeds on tiles."""

    def __init__(self, succeed_on_tiles: bool = True, succeed_on_neighbors: bool = False):
        self.succeed_on_tiles = succeed_on_tiles
        self.succeed_on_neighbors = succeed_on_neighbors
        self.calls: list[list[str]] = []

    def find_objects(self, frame_paths: list[str], prompt: str, timestamps_s: list[float] | None = None) -> list[Detection]:
        self.calls.append(list(frame_paths))
        results: list[Detection] = []
        for idx, p in enumerate(frame_paths):
            if "tile_" in p and self.succeed_on_tiles:
                results.append(
                    Detection(
                        frame_id=idx,
                        timestamp_s=0.0,
                        prompt=prompt,
                        score=0.88,
                        bbox={"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3},
                        polygon=[[0.2, 0.2], [0.5, 0.2], [0.5, 0.5]],
                    )
                )
            elif "neighbor" in p and self.succeed_on_neighbors:
                results.append(
                    Detection(
                        frame_id=idx,
                        timestamp_s=1.0,
                        prompt=prompt,
                        score=0.91,
                        bbox={"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.3},
                    )
                )
        return results


class MockSparkReasoner:
    """Mock reasoner for step 3."""

    def __init__(self, present: bool = True):
        self.present = present
        self.calls: list[str] = []

    def verify_presence(self, concept: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(concept)
        cited = [f["idx"] for f in frames if "idx" in f][:2] if self.present else []
        return {
            "present": self.present,
            "cited_frame_ids": cited,
            "rationale": f"Spark verified '{concept}' present." if self.present else "Not present.",
        }


def test_escalation_loop_stops_at_step1_when_tiles_succeed(sample_image: str, tmp_path: Path):
    """Segmenter misses full frame but finds object in tile -> stops at step 1."""
    segmenter = TileAwareMockSegmenter(succeed_on_tiles=True)
    reasoner = MockSparkReasoner()

    candidate = {"idx": 0, "path": sample_image, "timestamp_s": 0.0}
    all_frames = [candidate, {"idx": 1, "path": sample_image, "timestamp_s": 1.0}]

    res = run_active_evidence_gathering(
        rule_id="extinguisher_visible",
        concept="fire extinguisher",
        candidate_frame=candidate,
        all_frames=all_frames,
        segmenter=segmenter,
        reasoner=reasoner,
        audit_id="audit_test_wp3",
        work_dir=tmp_path,
        pass_threshold=0.60,
    )

    assert res["confident"] is True
    assert res["best_detection"] is not None
    assert res["best_detection"]["score"] >= 0.60
    assert len(res["steps"]) == 1, "Must stop immediately at step 1 on confident tile match"
    assert res["steps"][0]["step"] == "zoom_tiles"
    assert res["steps"][0]["stopped_here"] is True
    assert len(reasoner.calls) == 0, "Spark verification must not be called when step 1 succeeded"


def test_escalation_loop_progresses_through_steps_and_respects_max_3(sample_image: str, tmp_path: Path):
    """Misses tiles, misses neighbors, resolved by Spark at step 3."""
    segmenter = TileAwareMockSegmenter(succeed_on_tiles=False, succeed_on_neighbors=False)
    reasoner = MockSparkReasoner(present=True)

    candidate = {"idx": 0, "path": sample_image, "timestamp_s": 0.0}
    all_frames = [
        candidate,
        {"idx": 1, "path": sample_image, "timestamp_s": 1.0},
        {"idx": 2, "path": sample_image, "timestamp_s": 2.0},
    ]

    res = run_active_evidence_gathering(
        rule_id="exit_sign_visible",
        concept="exit sign",
        candidate_frame=candidate,
        all_frames=all_frames,
        segmenter=segmenter,
        reasoner=reasoner,
        audit_id="audit_test_wp3_3steps",
        work_dir=tmp_path,
        pass_threshold=0.60,
    )

    assert len(res["steps"]) == 3, "Must run at most 3 steps: tiles, neighbors, spark"
    step_names = [s["step"] for s in res["steps"]]
    assert step_names == ["zoom_tiles", "neighbor_frames", "spark_vision"]
    assert res["confident"] is True
    assert len(reasoner.calls) == 1, "Spark called exactly once at step 3"
