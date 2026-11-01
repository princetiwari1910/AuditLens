"""Unit tests for WP1: Evidence model, hybrid detectors, decision policy, and verify_presence."""

import pytest
from app.agent.rules import apply_decision_policy, select_strongest_evidence
from app.config import Settings
from app.models import (
    DetectorType,
    EvidenceItem,
    EvidenceStrength,
    FindingStatus,
    RuleModel,
    RuleType,
    TemplateModel,
)
from app.providers.mock import MockReasoner
from app.providers.record_replay import RecordReplayReasoner
from app.providers.schemas import validate_presence_verdict


# ── 1. Evidence Models & Strength ─────────────────────────────────────────────

def test_evidence_item_structure_and_strength():
    ev_mask = EvidenceItem(
        frame_id=1,
        ts=1.5,
        source="sam",
        concept="fire extinguisher",
        box={"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
        mask_ref=[[0.1, 0.2], [0.4, 0.2], [0.4, 0.6]],
        score=0.92,
        strength=EvidenceStrength.MASK_BACKED,
    )
    assert ev_mask.id.startswith("ev_")
    assert ev_mask.strength == EvidenceStrength.MASK_BACKED
    assert ev_mask.score == 0.92

    ev_model = EvidenceItem(
        frame_id=2,
        ts=2.0,
        source="spark",
        concept="fire extinguisher",
        score=0.85,
        strength=EvidenceStrength.MODEL_ATTESTED,
    )
    assert ev_model.strength == EvidenceStrength.MODEL_ATTESTED
    assert ev_model.box is None


# ── 2. Detector Validation in RuleModel ───────────────────────────────────────

def test_detector_field_and_normalization():
    # Explicit valid detectors
    r_sam = RuleModel(id="r1", title="R1", type=RuleType.PRESENCE, detector="sam")
    assert r_sam.detector == "sam"

    r_spark = RuleModel(id="r2", title="R2", type=RuleType.PRESENCE, detector="spark_vision")
    assert r_spark.detector == "spark_vision"

    r_hybrid = RuleModel(id="r3", title="R3", type=RuleType.PRESENCE, detector="sam_then_spark")
    assert r_hybrid.detector == "sam_then_spark"

    # Backward compatibility with legacy template descriptions
    r_legacy = RuleModel(id="r4", title="R4", type=RuleType.PRESENCE, detector="SAM 3.1")
    assert r_legacy.detector == "sam"

    r_default = RuleModel(id="r5", title="R5", type=RuleType.PRESENCE)
    assert r_default.detector == "sam"


# ── 3. Decision Policy Enforcement ───────────────────────────────────────────

def test_pass_requires_mask_or_two_distinct_model_frames():
    # Case A: Mask-backed evidence passes with mask_backed_pass
    mask_evidence = [
        {
            "id": "e1",
            "frame_id": 1,
            "ts": 1.0,
            "source": "sam",
            "concept": "fire extinguisher",
            "score": 0.88,
            "strength": "mask_backed",
        }
    ]
    status, conf, policy, rat = apply_decision_policy(
        rule_type="presence",
        provisional_status=FindingStatus.PASS,
        confidence=0.88,
        evidence_items=mask_evidence,
    )
    assert status == FindingStatus.PASS
    assert policy == "mask_backed_pass"

    # Case B: Model-attested evidence on ONLY ONE frame is downgraded to UNSURE
    single_frame_attested = [
        {
            "id": "e2",
            "frame_id": 3,
            "ts": 3.0,
            "source": "spark",
            "concept": "fire extinguisher",
            "score": 0.85,
            "strength": "model_attested",
        }
    ]
    status, conf, policy, rat = apply_decision_policy(
        rule_type="presence",
        provisional_status=FindingStatus.PASS,
        confidence=0.85,
        evidence_items=single_frame_attested,
    )
    assert status == FindingStatus.UNSURE
    assert policy == "single_frame_attested_insufficient"

    # Case C: Model-attested evidence on >= 2 distinct frames passes
    two_frame_attested = [
        {
            "id": "e2a",
            "frame_id": 2,
            "ts": 2.0,
            "source": "spark",
            "concept": "fire extinguisher",
            "score": 0.82,
            "strength": "model_attested",
        },
        {
            "id": "e2b",
            "frame_id": 5,
            "ts": 5.0,
            "source": "spark",
            "concept": "fire extinguisher",
            "score": 0.89,
            "strength": "model_attested",
        },
    ]
    status, conf, policy, rat = apply_decision_policy(
        rule_type="presence",
        provisional_status=FindingStatus.PASS,
        confidence=0.85,
        evidence_items=two_frame_attested,
    )
    assert status == FindingStatus.PASS
    assert policy == "multi_frame_model_attested_pass"


def test_absence_fail_requires_consensus_and_escalation():
    # Case A: Presence item missing, but escalation loop has NOT run -> UNSURE
    status, conf, policy, rat = apply_decision_policy(
        rule_type="presence",
        provisional_status=FindingStatus.FAIL,
        confidence=0.70,
        evidence_items=[],
        escalation_ran=False,
        min_absence_k=2,
        num_frames_evaluated=5,
    )
    assert status == FindingStatus.UNSURE
    assert policy == "absence_unverified_escalation_unsure"

    # Case B: Presence item missing, escalation loop HAS run with k>=2 frames evaluated -> FAIL
    status, conf, policy, rat = apply_decision_policy(
        rule_type="presence",
        provisional_status=FindingStatus.FAIL,
        confidence=0.80,
        evidence_items=[],
        escalation_ran=True,
        min_absence_k=2,
        num_frames_evaluated=4,
    )
    assert status == FindingStatus.FAIL
    assert policy == "absence_escalated_consensus_fail"

    # Case C: Absence rule (e.g. exit path blocked) detecting hazard -> FAIL
    status, conf, policy, rat = apply_decision_policy(
        rule_type="absence",
        provisional_status=FindingStatus.FAIL,
        confidence=0.90,
        evidence_items=[{"strength": "mask_backed", "score": 0.90}],
    )
    assert status == FindingStatus.FAIL
    assert policy == "hazard_detected_fail"


# ── 4. Strongest Evidence Selection ───────────────────────────────────────────

def test_select_strongest_evidence_ranking():
    items = [
        {"id": "ev_v", "strength": "voice_note", "score": 0.95},
        {"id": "ev_m", "strength": "model_attested", "score": 0.80},
        {"id": "ev_mask_low", "strength": "mask_backed", "score": 0.70},
        {"id": "ev_mask_high", "strength": "mask_backed", "score": 0.88},
    ]
    strongest = select_strongest_evidence(items)
    assert strongest is not None
    assert strongest["id"] == "ev_mask_high"  # mask_backed with highest score wins


# ── 5. Reasoner.verify_presence Contract ─────────────────────────────────────

def test_mock_reasoner_verify_presence():
    mr = MockReasoner()
    frames = [
        {"idx": 0, "path": "frame_0.jpg"},
        {"idx": 1, "path": "frame_1.jpg"},
        {"idx": 2, "path": "frame_2.jpg"},
    ]
    res_pos = mr.verify_presence("fire extinguisher", frames)
    assert res_pos["present"] is True
    assert len(res_pos["cited_frame_ids"]) > 0
    assert all(fid in [0, 1, 2] for fid in res_pos["cited_frame_ids"])
    assert "[MOCK]" in res_pos["rationale"]

    res_neg = mr.verify_presence("alien artifact", frames)
    assert res_neg["present"] is False
    assert res_neg["cited_frame_ids"] == []


def test_presence_verdict_schema_rejects_invented_frame_ids():
    raw_invalid = {
        "present": True,
        "cited_frame_ids": [999, 888],  # Invented frame IDs not in [0, 1, 2]
        "rationale": "Object detected on non-existent frame 999.",
    }
    validated = validate_presence_verdict(raw_invalid, allowed_frame_ids=[0, 1, 2])
    assert validated["present"] is False
    assert validated["cited_frame_ids"] == []
    assert "failed to cite valid frame IDs" in validated["rationale"]


def test_meta_reasoner_verify_presence_requires_key():
    from app.providers.meta import MetaReasoner, ERR_UNVERIFIED

    mr = MetaReasoner()
    frames = [{"idx": 0, "path": "dummy.jpg"}]
    with pytest.raises(ValueError, match="UNVERIFIED against live API"):
        mr.verify_presence("fire extinguisher", frames)


# ── 6. Config Flag ────────────────────────────────────────────────────────────

def test_hybrid_detectors_flag_config(monkeypatch):
    monkeypatch.setenv("ENABLE_HYBRID_DETECTORS", "false")
    s = Settings()
    assert s.ENABLE_HYBRID_DETECTORS is False
