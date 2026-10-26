"""Tests for Milestone 4: Agent tools, Evidence-First enforcement, rules engine, measurement, and comparison."""

import pytest
from sqlmodel import Session

from app.agent.compare import ComparisonStatus, classify_transition, compare_audits
from app.agent.measure import A4_LONG_SIDE_METERS, compute_pixels_per_meter, estimate_clear_width
from app.agent.rules import (
    compute_summary_score,
    deduplicate_detections,
    evaluate_absence_rule,
    evaluate_colocation_rule,
    evaluate_count_rule,
    evaluate_measurement_rule,
    evaluate_presence_rule,
    parse_custom_rule,
)
from app.agent.runner import AgentRunner
from app.agent.tools import EvidenceError, ExecutionContext, ToolRegistry
from app.config import get_settings
from app.db import engine, init_db, reset_engine
from app.models import Audit, FindingStatus, RuleModel, RuleType, Severity
from app.providers.mock import MockSegmentationProvider, MockTranscriptionProvider


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


# ── 1. Evidence-First Enforcement Tests ────────────────────────────────────────

def test_evidence_first_rejects_invalid_result_id():
    """Verify record_finding rejects any finding referencing a forged/nonexistent result_id."""
    ctx = ExecutionContext(
        audit_id="audit_ef_01",
        rules=[RuleModel(id="r1", title="Extinguisher", type=RuleType.PRESENCE)],
        frames=[],
        segmentation_provider=MockSegmentationProvider(),
        transcription_provider=MockTranscriptionProvider(),
    )
    registry = ToolRegistry(ctx)

    with pytest.raises(EvidenceError, match="Evidence validation failed"):
        registry.execute(
            "record_finding",
            rule_id="r1",
            status="pass",
            confidence=0.95,
            evidence_ids=["res_fake_nonexistent_id"],
        )


def test_evidence_first_forces_unsure_when_no_evidence():
    """Verify that omitting evidence_ids forces the finding to 'unsure' with zero confidence."""
    ctx = ExecutionContext(
        audit_id="audit_ef_02",
        rules=[RuleModel(id="r1", title="Extinguisher", type=RuleType.PRESENCE)],
        frames=[],
        segmentation_provider=MockSegmentationProvider(),
        transcription_provider=MockTranscriptionProvider(),
    )
    registry = ToolRegistry(ctx)

    res = registry.execute(
        "record_finding",
        rule_id="r1",
        status="pass",
        confidence=0.99,
        evidence_ids=[],  # No evidence
    )
    f = res["finding"]
    assert f["status"] == FindingStatus.UNSURE.value
    assert f["confidence"] == 0.0
    assert "no supporting visual evidence" in f["rationale"]


# ── 2. Rule Evaluation Engine (All Five Types) ────────────────────────────────

def test_presence_rule_evaluation():
    # Pass: score >= 0.6
    st_p, conf_p, _, _ = evaluate_presence_rule([{"score": 0.85, "timestamp_s": 1.0}])
    assert st_p == FindingStatus.PASS
    assert conf_p == 0.85

    # Unsure: 0.3 <= score < 0.6
    st_u, conf_u, _, _ = evaluate_presence_rule([{"score": 0.45, "timestamp_s": 2.0}])
    assert st_u == FindingStatus.UNSURE
    assert conf_u == 0.45

    # Fail: score < 0.3 or empty
    st_f, _, _, _ = evaluate_presence_rule([{"score": 0.15, "timestamp_s": 3.0}])
    assert st_f == FindingStatus.FAIL
    st_none, _, _, _ = evaluate_presence_rule([])
    assert st_none == FindingStatus.FAIL


def test_absence_rule_evaluation():
    # Pass: 0 detections
    st_p, conf_p, _, _ = evaluate_absence_rule([])
    assert st_p == FindingStatus.PASS
    assert conf_p == 1.0

    # Fail: obstacle detected with score >= 0.6
    st_f, conf_f, _, _ = evaluate_absence_rule([{"score": 0.82, "timestamp_s": 5.0}])
    assert st_f == FindingStatus.FAIL
    assert conf_f == 0.82

    # Unsure: borderline obstacle detection
    st_u, conf_u, _, _ = evaluate_absence_rule([{"score": 0.40, "timestamp_s": 5.0}])
    assert st_u == FindingStatus.UNSURE


def test_count_rule_deduplication_and_evaluation():
    # 3 detections: two are temporally and spatially close (duplicates), one is separate
    dets = [
        {"score": 0.90, "timestamp_s": 2.0, "bbox": {"x": 0.4, "y": 0.2}},
        {"score": 0.92, "timestamp_s": 2.5, "bbox": {"x": 0.41, "y": 0.21}},  # Duplicate
        {"score": 0.88, "timestamp_s": 18.0, "bbox": {"x": 0.8, "y": 0.3}},   # Distinct instance
    ]
    deduped = deduplicate_detections(dets)
    assert len(deduped) == 2

    # Min count = 2 -> PASS
    st, conf, _, _ = evaluate_count_rule(dets, min_count=2, threshold=0.6)
    assert st == FindingStatus.PASS
    assert conf >= 0.85

    # Min count = 3 -> FAIL (only 2 distinct)
    st_fail, _, _, _ = evaluate_count_rule(dets, min_count=3, threshold=0.6)
    assert st_fail == FindingStatus.FAIL


def test_measurement_rule_evaluation():
    # 1. Clear Pass: 1.4m width with 0.1m uncertainty vs 1.0m required (1.4 - 0.1 = 1.3 >= 1.0)
    st_p, conf_p, _ = evaluate_measurement_rule({"width_m": 1.4, "uncertainty_m": 0.1}, min_width_m=1.0)
    assert st_p == FindingStatus.PASS

    # 2. Clear Fail: 0.7m width with 0.1m uncertainty vs 1.0m required (0.7 + 0.1 = 0.8 < 1.0)
    st_f, conf_f, _ = evaluate_measurement_rule({"width_m": 0.7, "uncertainty_m": 0.1}, min_width_m=1.0)
    assert st_f == FindingStatus.FAIL

    # 3. Borderline Unsure: 1.05m width with 0.15m uncertainty (worst-case 0.9m < 1.0, best-case 1.2m >= 1.0)
    st_u, conf_u, _ = evaluate_measurement_rule({"width_m": 1.05, "uncertainty_m": 0.15}, min_width_m=1.0)
    assert st_u == FindingStatus.UNSURE


def test_colocation_rule_evaluation():
    # Person with overlapping helmet
    containers = [{"score": 0.90, "timestamp_s": 5.0, "bbox": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.5}}]
    matching_helmets = [{"score": 0.92, "timestamp_s": 5.0, "bbox": {"x": 0.35, "y": 0.3, "w": 0.1, "h": 0.1}}]

    st_p, _, _, _ = evaluate_colocation_rule(containers, matching_helmets, min_overlap=0.20)
    assert st_p == FindingStatus.PASS

    # Person without helmet -> FAIL
    st_f, _, _, _ = evaluate_colocation_rule(containers, [], min_overlap=0.20)
    assert st_f == FindingStatus.FAIL


def test_custom_rule_parsing():
    r_abs = parse_custom_rule("No loose wires across walkway")
    assert r_abs.type == RuleType.ABSENCE
    assert "loose wires" in r_abs.sam_prompts[0]

    r_cnt = parse_custom_rule("At least 3 fire exits visible")
    assert r_cnt.type == RuleType.COUNT
    assert r_cnt.params["min_count"] == 3

    r_pres = parse_custom_rule("First aid kit mounted near entrance")
    assert r_pres.type == RuleType.PRESENCE


# ── 3. Measurement Calibration Tests ──────────────────────────────────────────

def test_measurement_scale_and_uncertainty():
    # A4 sheet calibration: 110 px = 0.297m -> ~370.37 ppm
    ref_det = {"bbox": {"w": 110.0 / 1280.0, "h": 75.0 / 720.0}}
    ppm, method = compute_pixels_per_meter({"type": "a4"}, 1280, 720, ref_det)
    assert round(ppm, 1) == 370.4
    assert "A4 optical reference" in method

    # Measure walkway with an obstacle in middle
    # Walkway span: 0.15 to 0.85 = 0.70 of 1280px = 896px total span (~2.42m)
    # Add an obstacle between 0.40 and 0.55
    obstacle = [{"x": 0.40, "y": 0.60, "w": 0.15, "h": 0.25}]
    meas = estimate_clear_width(obstacle, 1280, 720, pixels_per_meter=ppm)

    # Free gaps: left gap is 0.40 - 0.15 = 0.25 norm (~320px = ~0.86m)
    # Right gap is 0.85 - 0.55 = 0.30 norm (~384px = ~1.04m)
    assert meas.width_m > 0.95
    assert meas.uncertainty_m >= 0.05
    assert "perspective" in meas.assumptions.lower()


# ── 4. Comparison Engine Tests (All Categories) ───────────────────────────────

def test_compare_audits_all_categories():
    assert classify_transition("fail", "pass") == ComparisonStatus.RESOLVED
    assert classify_transition("pass", "fail") == ComparisonStatus.NEW_ISSUE
    assert classify_transition("fail", "fail") == ComparisonStatus.STILL_OPEN
    assert classify_transition("pass", "pass") == ComparisonStatus.UNCHANGED_PASS
    assert classify_transition("unsure", "pass") == ComparisonStatus.UNSURE_CHANGE
    assert classify_transition("fail", "unsure") == ComparisonStatus.UNSURE_CHANGE

    before = [
        {"rule_id": "r1", "status": "fail", "confidence": 0.8},
        {"rule_id": "r2", "status": "pass", "confidence": 0.9},
        {"rule_id": "r3", "status": "fail", "confidence": 0.7},
        {"rule_id": "r4", "status": "pass", "confidence": 0.95},
        {"rule_id": "r5", "status": "unsure", "confidence": 0.5},
    ]
    after = [
        {"rule_id": "r1", "status": "pass", "confidence": 0.92},   # RESOLVED
        {"rule_id": "r2", "status": "fail", "confidence": 0.85},   # NEW ISSUE
        {"rule_id": "r3", "status": "fail", "confidence": 0.75},   # STILL OPEN
        {"rule_id": "r4", "status": "pass", "confidence": 0.91},   # UNCHANGED PASS
        {"rule_id": "r5", "status": "pass", "confidence": 0.88},   # UNSURE CHANGE
    ]

    res = compare_audits(before, after, "b1", "a1")
    s = res["summary"]
    assert s["resolved"] == 1
    assert s["new_issue"] == 1
    assert s["still_open"] == 1
    assert s["unchanged_pass"] == 1
    assert s["unsure_change"] == 1


# ── 5. Summary Score Calculation Test ─────────────────────────────────────────

def test_summary_score_calculation():
    findings = [
        {"status": "pass", "severity": "high"},     # 1.0 * 3 = 3.0
        {"status": "pass", "severity": "medium"},   # 1.0 * 2 = 2.0
        {"status": "unsure", "severity": "high"},   # 0.5 * 3 = 1.5
        {"status": "fail", "severity": "high"},     # 0.0 * 3 = 0.0
    ]
    # Total weight = 3 + 2 + 3 + 3 = 11.0
    # Weighted sum = 3.0 + 2.0 + 1.5 + 0.0 = 6.5
    # Score = round(6.5 / 11.0 * 100) = 59
    summary = compute_summary_score(findings)
    assert summary["score"] == 59
    assert summary["pass"] == 2
    assert summary["unsure"] == 1
    assert summary["fail"] == 1


# ── 6. Full AgentRunner Execution Test ────────────────────────────────────────

def test_agent_runner_full_run():
    events_collected = []

    def emit(evt):
        events_collected.append(evt)

    runner = AgentRunner(
        segmentation_provider=MockSegmentationProvider(),
        transcription_provider=MockTranscriptionProvider(),
    )

    rules = [
        RuleModel(id="extinguisher", title="Extinguisher visible", type=RuleType.PRESENCE, sam_prompts=["fire extinguisher"], severity=Severity.HIGH),
        RuleModel(id="exit_path", title="Exit path clear width", type=RuleType.MEASUREMENT, sam_prompts=["box"], severity=Severity.HIGH),
    ]
    frames = [
        {"idx": 0, "timestamp_s": 0.0, "path": "/dummy/frame_0.jpg", "sha256": "h0"},
        {"idx": 1, "timestamp_s": 1.0, "path": "/dummy/frame_1.jpg", "sha256": "h1"},
    ]

    findings = runner.run_audit("audit_test_runner", rules, frames, emit)
    assert len(findings) == 2

    # Verify event sequence
    event_types = [e["type"] for e in events_collected]
    assert event_types[0] == "audit_started"
    assert event_types[1] == "frames_sampled"
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "finding_recorded" in event_types
    assert event_types[-1] == "audit_completed"
