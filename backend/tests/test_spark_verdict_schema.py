"""Tests for strict Muse Spark Reasoner verdict schema and fallback validation."""

import pytest
from app.providers import get_reasoner
from app.providers.schemas import (
    SPARK_VERDICT_JSON_SCHEMA,
    ReasonerVerdict,
    VerdictStatus,
    compute_schema_depth,
    validate_verdict,
)


def test_schema_depth_and_no_recursive_refs():
    """Verify JSON schema depth is <= 3 and contains no recursive $ref."""
    depth = compute_schema_depth(SPARK_VERDICT_JSON_SCHEMA)
    assert depth <= 3
    assert "$ref" not in str(SPARK_VERDICT_JSON_SCHEMA)


def test_valid_verdict_parsing():
    """Verify standard valid Spark Reasoner verdict passes validation."""
    valid_data = {
        "status": "pass",
        "reason": "Fire extinguisher is securely mounted at 1.2m height.",
        "cited_frame_ids": [0, 2],
        "confidence": 0.95,
    }
    verdict = validate_verdict(valid_data)
    assert verdict.status == VerdictStatus.PASS
    assert verdict.verdict == "pass"
    assert verdict.confidence == 0.95
    assert verdict.cited_frame_ids == [0, 2]
    assert verdict.cited_frames == [0, 2]


def test_backward_compatibility_aliases():
    """Verify legacy verdict and cited_frames aliases are normalized seamlessly."""
    legacy_data = {
        "verdict": "FAIL",
        "reason": "Exit path obstructed by pallet.",
        "cited_frames": ["4", "5"],
        "confidence": 0.88,
    }
    verdict = validate_verdict(legacy_data)
    assert verdict.status == VerdictStatus.FAIL
    assert verdict.verdict == "fail"
    assert verdict.cited_frame_ids == [4, 5]


def test_invalid_status_enum_forces_unsure():
    """Verify unrecognized status enum is rejected and forced to unsure."""
    invalid_status = {
        "status": "conditional_pass",  # Not in ("pass", "fail", "unsure")
        "reason": "Looks okay but uncertain.",
        "cited_frame_ids": [1],
    }
    verdict = validate_verdict(invalid_status)
    assert verdict.status == VerdictStatus.UNSURE
    assert verdict.confidence == 0.50
    assert "Schema validation fallback" in verdict.reason


def test_missing_reason_forces_unsure():
    """Verify missing reason field forces unsure."""
    missing_reason = {
        "status": "pass",
    }
    verdict = validate_verdict(missing_reason)
    assert verdict.status == VerdictStatus.UNSURE
    assert verdict.confidence == 0.50


def test_malformed_json_string_forces_unsure():
    """Verify malformed JSON string forces unsure."""
    bad_json = "this is not json {status: pass"
    verdict = validate_verdict(bad_json)
    assert verdict.status == VerdictStatus.UNSURE
    assert verdict.confidence == 0.50
    assert "invalid JSON" in verdict.reason


def test_reasoner_provider_returns_schema_compliant_dict():
    """Verify get_reasoner().judge() returns schema-compliant dictionary."""
    reasoner = get_reasoner()
    result = reasoner.judge(
        rule={"id": "test_rule", "type": "presence", "title": "Fire Extinguisher"},
        evidence=[{"frame_id": 1, "score": 0.9}],
    )
    assert result["status"] in ("pass", "fail", "unsure")
    assert "reason" in result
    assert isinstance(result["cited_frame_ids"], list)
    assert 0.0 <= result["confidence"] <= 1.0
