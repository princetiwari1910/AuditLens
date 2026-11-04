"""Unit tests for Task 3: Concept variants, NMS merging (IoU 0.5), min_confidence thresholds, and footage limits."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch
import pytest

from app.agent.rules import evaluate_presence_rule, merge_concept_detections
from app.models import FindingStatus, RuleModel, RuleType
from scripts.tune_concepts import main as tune_concepts_main


def test_merge_concept_detections_nms_iou_half():
    """Verify that detections with IoU >= 0.5 are merged, keeping max confidence."""
    # Two overlapping boxes for 'fire extinguisher' and 'red cylinder' on frame 0
    dets = [
        {
            "frame_id": 0,
            "timestamp_s": 1.0,
            "prompt": "fire extinguisher",
            "score": 0.82,
            "bbox": {"x": 0.20, "y": 0.20, "w": 0.20, "h": 0.40},
        },
        {
            "frame_id": 0,
            "timestamp_s": 1.0,
            "prompt": "red fire extinguisher cylinder",
            "score": 0.94,  # higher confidence
            "bbox": {"x": 0.21, "y": 0.20, "w": 0.19, "h": 0.41},  # IoU > 0.8
        },
        # Distinct non-overlapping detection on frame 0
        {
            "frame_id": 0,
            "timestamp_s": 1.0,
            "prompt": "emergency exit sign",
            "score": 0.88,
            "bbox": {"x": 0.70, "y": 0.10, "w": 0.25, "h": 0.15},
        },
    ]

    merged = merge_concept_detections(dets, iou_thresh=0.5)

    # 3 inputs -> 2 merged outputs
    assert len(merged) == 2
    # The extinguisher detection must keep the max score (0.94)
    ext_det = next(d for d in merged if "extinguisher" in d["prompt"])
    assert ext_det["score"] == 0.94
    assert ext_det["prompt"] == "red fire extinguisher cylinder"


def test_min_confidence_override_leads_to_unsure():
    """Verify that a detection below rule min_confidence produces UNSURE (weak evidence), not FAIL."""
    dets = [
        {
            "frame_id": 0,
            "timestamp_s": 1.0,
            "prompt": "fire extinguisher",
            "score": 0.65,
            "bbox": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
        }
    ]

    # Rule with custom high threshold of 0.75
    status, conf, rationale, best = evaluate_presence_rule(dets, threshold=0.75)
    assert status == FindingStatus.UNSURE
    assert conf == 0.65
    assert "weak confidence" in rationale or "requires physical verification" in rationale


def test_presence_rule_not_enough_footage():
    """Verify that no detections with < 6 usable frames produces UNSURE ('not enough footage')."""
    # 3 frames analyzed, no detection
    status, conf, rationale, best = evaluate_presence_rule([], frames_count=3, min_usable_frames=6)
    assert status == FindingStatus.UNSURE
    assert "not enough footage" in rationale
    assert best is None


def test_presence_rule_fails_when_enough_footage():
    """Verify that no detections with >= 6 usable frames produces FAIL."""
    status, conf, rationale, best = evaluate_presence_rule([], frames_count=8, min_usable_frames=6)
    assert status == FindingStatus.FAIL
    assert "No matching objects detected" in rationale


def test_concept_variant_max_words_validator():
    """Verify that concepts with more than 5 words are rejected by RuleModel."""
    # 5 words: allowed
    rule = RuleModel(
        id="test_rule",
        title="Valid Rule",
        type=RuleType.PRESENCE,
        concepts=["red fire extinguisher on wall"],
    )
    assert len(rule.concepts) == 1

    # 6 words: rejected
    with pytest.raises(ValueError, match="exceeds maximum 5 words"):
        RuleModel(
            id="test_invalid",
            title="Invalid Rule",
            type=RuleType.PRESENCE,
            concepts=["red fire extinguisher mounted high on wall"],
        )


def test_tune_concepts_cli(tmp_path):
    """Verify tune-concepts script executes and prints output table."""
    img = tmp_path / "test.jpg"
    import cv2
    import numpy as np

    mat = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.imwrite(str(img), mat)

    captured_out = io.StringIO()
    with patch("sys.stdout", captured_out), patch(
        "sys.argv",
        ["tune_concepts.py", f"--images={img}", "--concepts=fire extinguisher,red extinguisher"],
    ):
        ret = tune_concepts_main()
        assert ret == 0

    out = captured_out.getvalue()
    assert "AuditLens Concept Tuning Tool" in out
    assert "fire extinguisher" in out
    assert "red extinguisher" in out
