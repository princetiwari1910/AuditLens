"""Deterministic rule evaluation logic for all five safety rule types."""

from __future__ import annotations

import re
from typing import Any
from app.config import get_settings
from app.models import FindingStatus, RuleModel, RuleType, Severity


def compute_summary_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate weighted safety compliance score (0 - 100):
    - Status values: pass = 1.0, unsure = 0.5, fail = 0.0
    - Severity weights: high = 3, medium = 2, low = 1
    Returns compliance score, breakdown by status, and breakdown by severity.
    """
    severity_weights = {
        "high": 3.0,
        "medium": 2.0,
        "low": 1.0,
    }
    status_values = {
        "pass": 1.0,
        "unsure": 0.5,
        "fail": 0.0,
    }

    status_counts = {"pass": 0, "fail": 0, "unsure": 0}
    severity_counts = {"high": 0, "medium": 0, "low": 0}

    total_weight = 0.0
    weighted_sum = 0.0

    for f in findings:
        status = str(f.get("status", "unsure")).lower()
        severity = str(f.get("severity", "medium")).lower()

        status_counts[status] = status_counts.get(status, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

        w = severity_weights.get(severity, 2.0)
        v = status_values.get(status, 0.5)

        total_weight += w
        weighted_sum += (v * w)

    if total_weight > 0:
        score = round((weighted_sum / total_weight) * 100.0)
    else:
        score = 0

    return {
        "score": score,
        "pass": status_counts.get("pass", 0),
        "fail": status_counts.get("fail", 0),
        "unsure": status_counts.get("unsure", 0),
        "by_severity": severity_counts,
    }


def parse_custom_rule(text: str, rule_idx: int = 1) -> RuleModel:
    """
    Parse a user-entered freeform sentence into a structured RuleModel using keyword heuristics.
    TODO(meta): Replace keyword heuristic with Muse Spark natural language rule compiler.
    """
    norm = text.strip()
    lower = norm.lower()
    rule_id = f"custom_rule_{rule_idx}_{re.sub(r'[^a-z0-9]+', '_', lower)[:24].strip('_')}"

    # Absence keywords
    absence_patterns = ["no ", "free of", "without", "never", "not ", "clear of", "prevent"]
    if any(pat in lower for pat in absence_patterns):
        # Extract target object by removing leading negative trigger
        cleaned = re.sub(r"^(no\s+|free\s+of\s+|ensure\s+no\s+|without\s+)", "", lower).strip()
        return RuleModel(
            id=rule_id,
            title=norm,
            type=RuleType.ABSENCE,
            severity=Severity.HIGH,
            sam_prompts=[cleaned] if cleaned else ["obstacle"],
            params={"threshold": 0.6},
            fix_text=f"Remove {cleaned or 'detected hazard'} to ensure a clear path.",
        )

    # Count keywords
    if any(k in lower for k in ["at least", "count", "number of", "minimum"]):
        m = re.search(r"\b(\d+)\b", lower)
        min_count = int(m.group(1)) if m else 2
        return RuleModel(
            id=rule_id,
            title=norm,
            type=RuleType.COUNT,
            severity=Severity.MEDIUM,
            sam_prompts=[norm],
            params={"min_count": min_count, "min_score": 0.55},
            fix_text=f"Ensure at least {min_count} compliant items are visible.",
        )

    # Default to presence rule
    return RuleModel(
        id=rule_id,
        title=norm,
        type=RuleType.PRESENCE,
        severity=Severity.HIGH,
        sam_prompts=[norm],
        params={"min_score": 0.6},
        fix_text=f"Install or verify presence of {norm}.",
    )


# ── Rule Type Evaluators ──────────────────────────────────────────────────────

def merge_concept_detections(
    detections: list[dict[str, Any]],
    iou_thresh: float = 0.5,
) -> list[dict[str, Any]]:
    """
    Merge detections across concept variants using Non-Maximum Suppression (IoU >= 0.5).
    Keeps the detection with maximum confidence when bounding boxes overlap on the same frame.
    """
    if not detections:
        return []

    from app.agent.tracking import compute_iou

    # Group by frame_id
    by_frame: dict[int, list[dict[str, Any]]] = {}
    for d in detections:
        fid = int(d.get("frame_id", 0))
        by_frame.setdefault(fid, []).append(d)

    merged: list[dict[str, Any]] = []

    for fid, frame_dets in by_frame.items():
        # Sort descending by score
        sorted_dets = sorted(
            frame_dets,
            key=lambda d: float(d.get("score", 0.0)),
            reverse=True,
        )
        kept: list[dict[str, Any]] = []
        for d in sorted_dets:
            d_box = d.get("bbox")
            suppressed = False
            for k in kept:
                k_box = k.get("bbox")
                if compute_iou(d_box, k_box) >= iou_thresh:
                    suppressed = True
                    break
            if not suppressed:
                kept.append(d)
        merged.extend(kept)

    # Sort merged results by frame_id and score descending
    merged.sort(key=lambda d: (int(d.get("frame_id", 0)), -float(d.get("score", 0.0))))
    return merged


def evaluate_presence_rule(
    detections: list[dict[str, Any]],
    threshold: float | None = None,
    frames_count: int | None = None,
    min_usable_frames: int | None = None,
) -> tuple[FindingStatus, float, str, dict[str, Any] | None]:
    """
    Evaluate presence rule:
    - PASS: best score >= threshold (default 0.6)
    - UNSURE: detection below threshold (weak evidence)
    - FAIL: no detection if frames_count >= min_usable_frames (default 6)
    - UNSURE: no detection if frames_count < min_usable_frames ("not enough footage")
    Returns: (status, confidence, rationale, best_detection)
    """
    settings = get_settings()
    thresh = threshold if threshold is not None else settings.MIN_CONFIDENCE_PASS
    n_min = min_usable_frames if min_usable_frames is not None else getattr(settings, "MIN_USABLE_FRAMES_PRESENCE", 6)

    if not detections:
        total_frames = frames_count if frames_count is not None else n_min
        if total_frames < n_min:
            return (
                FindingStatus.UNSURE,
                0.0,
                f"Candidate object not observed, but not enough footage was analyzed ({total_frames}/{n_min} frames); physical verification required.",
                None,
            )
        return (
            FindingStatus.FAIL,
            0.0,
            "No matching objects detected in any sampled walkthrough frame.",
            None,
        )

    best = max(detections, key=lambda d: float(d.get("score", 0.0)))
    best_score = float(best.get("score", 0.0))

    if best_score >= thresh:
        return (
            FindingStatus.PASS,
            best_score,
            f"Object confirmed present with {best_score:.0%} confidence at {best.get('timestamp_s', 0.0):.1f}s.",
            best,
        )
    elif best_score >= 0.30:
        # A detection below min_confidence is weak evidence and leads to unsure
        return (
            FindingStatus.UNSURE,
            best_score,
            f"Candidate object detected with weak confidence ({best_score:.0%} < {thresh:.0%}); requires physical verification.",
            best,
        )
    else:
        return (
            FindingStatus.FAIL,
            best_score,
            f"Object not detected (highest detection signal {best_score:.0%} is below verification threshold).",
            best,
        )


def evaluate_absence_rule(
    detections: list[dict[str, Any]],
    threshold: float | None = None,
) -> tuple[FindingStatus, float, str, dict[str, Any] | None]:
    """
    Evaluate absence rule (e.g. exit path not blocked, no cables):
    - PASS: no detections with score >= 0.3 (area is clear)
    - FAIL: any detection with score >= threshold
    - UNSURE: best score between 0.3 and threshold
    """
    settings = get_settings()
    thresh = threshold if threshold is not None else settings.MIN_CONFIDENCE_PASS

    if not detections:
        return (
            FindingStatus.PASS,
            1.0,
            "No prohibited items or blocking obstacles detected across walkthrough.",
            None,
        )

    best = max(detections, key=lambda d: float(d.get("score", 0.0)))
    best_score = float(best.get("score", 0.0))

    if best_score >= thresh:
        return (
            FindingStatus.FAIL,
            best_score,
            f"Blocking hazard detected at {best.get('timestamp_s', 0.0):.1f}s ({best_score:.0%} confidence).",
            best,
        )
    elif best_score >= 0.30:
        return (
            FindingStatus.UNSURE,
            best_score,
            f"Potential obstacle detected with marginal confidence ({best_score:.0%}); inspection advised.",
            best,
        )
    else:
        return (
            FindingStatus.PASS,
            round(1.0 - best_score, 2),
            "Area appears free of obstructions; low-level image noise detected below hazard threshold.",
            None,
        )


def deduplicate_detections(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    De-duplicate detections across time and space.
    Continuous observations of the same object (contiguous track within 2.5s or similar spatial location)
    are merged into a single distinct instance.
    """
    if not detections:
        return []

    sorted_dets = sorted(detections, key=lambda d: float(d.get("timestamp_s", 0.0)))
    unique_instances: list[dict[str, Any]] = []

    for d in sorted_dets:
        t = float(d.get("timestamp_s", 0.0))
        bbox = d.get("bbox", {})
        bx = float(bbox.get("x", 0.0))
        by = float(bbox.get("y", 0.0))

        is_duplicate = False
        for u in unique_instances:
            last_t = float(u.get("last_seen_s", u.get("timestamp_s", 0.0)))
            u_box = u.get("bbox", {})
            ux = float(u_box.get("x", 0.0))
            uy = float(u_box.get("y", 0.0))

            spatial_dist = abs(bx - ux) + abs(by - uy)
            # Same spatial position or continuous track within 2.5 seconds
            if spatial_dist < 0.15 or (abs(t - last_t) <= 2.5 and spatial_dist < 0.25):
                is_duplicate = True
                u["last_seen_s"] = t
                if float(d.get("score", 0.0)) > float(u.get("score", 0.0)):
                    u["score"] = d.get("score", 0.0)
                    u["bbox"] = d.get("bbox")
                    u["polygon"] = d.get("polygon")
                break

        if not is_duplicate:
            item = dict(d)
            item["last_seen_s"] = t
            unique_instances.append(item)

    return unique_instances


def evaluate_count_rule(
    detections: list[dict[str, Any]],
    min_count: int = 2,
    threshold: float | None = None,
) -> tuple[FindingStatus, float, str, dict[str, Any] | None]:
    """
    Evaluate count rule (e.g. at least 2 exits visible across walkthrough).
    """
    settings = get_settings()
    thresh = threshold if threshold is not None else settings.MIN_CONFIDENCE_PASS

    valid_dets = [d for d in detections if float(d.get("score", 0.0)) >= 0.30]
    unique_items = deduplicate_detections(valid_dets)

    confident_items = [u for u in unique_items if float(u.get("score", 0.0)) >= thresh]

    if len(confident_items) >= min_count:
        avg_conf = sum(float(u["score"]) for u in confident_items) / len(confident_items)
        rep = confident_items[0]
        return (
            FindingStatus.PASS,
            round(avg_conf, 2),
            f"Found {len(confident_items)} distinct instances (minimum required: {min_count}).",
            rep,
        )
    elif len(unique_items) >= min_count:
        # We reached count only by including lower-confidence items
        rep = unique_items[0] if unique_items else None
        return (
            FindingStatus.UNSURE,
            0.50,
            f"Observed {len(unique_items)} candidate instances, but some have marginal confidence.",
            rep,
        )
    else:
        rep = unique_items[0] if unique_items else None
        return (
            FindingStatus.FAIL,
            0.30,
            f"Only {len(confident_items)} distinct instances detected (minimum required: {min_count}).",
            rep,
        )


def evaluate_measurement_rule(
    measurement: dict[str, Any],
    min_width_m: float = 1.0,
) -> tuple[FindingStatus, float, str]:
    """
    Evaluate walkway clear-width measurement against required minimum:
    - PASS: width_m - uncertainty_m >= min_width_m (clear even in worst-case uncertainty)
    - FAIL: width_m + uncertainty_m < min_width_m (violates minimum even in best-case)
    - UNSURE: within the uncertainty margin of min_width_m
    """
    width = float(measurement.get("width_m", 0.0))
    unc = float(measurement.get("uncertainty_m", 0.10))

    worst_case_pass = width - unc
    best_case_fail = width + unc

    if worst_case_pass >= min_width_m:
        conf = 0.92
        rationale = (
            f"Measured walkway clear width of {width:.2f} m (+/- {unc:.2f} m) meets required {min_width_m:.2f} m."
        )
        return FindingStatus.PASS, conf, rationale
    elif best_case_fail < min_width_m:
        conf = 0.88
        rationale = (
            f"Measured walkway clear width of {width:.2f} m (+/- {unc:.2f} m) is below required {min_width_m:.2f} m."
        )
        return FindingStatus.FAIL, conf, rationale
    else:
        conf = 0.55
        rationale = (
            f"Walkway clear width ({width:.2f} +/- {unc:.2f} m) is borderline near the {min_width_m:.2f} m threshold."
        )
        return FindingStatus.UNSURE, conf, rationale


def compute_bbox_overlap(box1: dict[str, float], box2: dict[str, float]) -> float:
    """
    Compute intersection over box2 area (how much of the item box is inside the container box).
    """
    x1, y1, w1, h1 = box1.get("x", 0), box1.get("y", 0), box1.get("w", 0), box1.get("h", 0)
    x2, y2, w2, h2 = box2.get("x", 0), box2.get("y", 0), box2.get("w", 0), box2.get("h", 0)

    # Intersection coordinates
    inter_x1 = max(x1, x2)
    inter_y1 = max(y1, y2)
    inter_x2 = min(x1 + w1, x2 + w2)
    inter_y2 = min(y1 + h1, y2 + h2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    item_area = max(1e-6, w2 * h2)
    return inter_area / item_area


def evaluate_colocation_rule(
    containers: list[dict[str, Any]],
    items: list[dict[str, Any]],
    min_overlap: float = 0.20,
    threshold: float | None = None,
) -> tuple[FindingStatus, float, str, dict[str, Any] | None]:
    """
    Evaluate colocation (e.g. person wearing helmet):
    - PASS: every confident container has an overlapping item with overlap >= min_overlap
    - FAIL: at least one confident container lacks the required co-located item
    - UNSURE: container found but item overlap or score is marginal
    """
    settings = get_settings()
    thresh = threshold if threshold is not None else settings.MIN_CONFIDENCE_PASS

    confident_containers = [c for c in containers if float(c.get("score", 0.0)) >= thresh]

    if not confident_containers:
        # No people/containers detected
        return (
            FindingStatus.PASS,
            0.75,
            "No personnel detected in the active workspace area during this walkthrough.",
            None,
        )

    unprotected_containers = 0
    marginal_containers = 0
    best_match_det: dict[str, Any] | None = None

    for container in confident_containers:
        c_box = container.get("bbox", {})
        c_time = float(container.get("timestamp_s", 0.0))

        # Look for co-temporal items
        candidate_items = [
            it for it in items
            if abs(float(it.get("timestamp_s", 0.0)) - c_time) <= 1.5
        ]

        overlaps = [
            (compute_bbox_overlap(c_box, it.get("bbox", {})), it)
            for it in candidate_items
        ]

        if overlaps:
            best_overlap, best_it = max(overlaps, key=lambda x: x[0])
            it_score = float(best_it.get("score", 0.0))
            if best_overlap >= min_overlap and it_score >= thresh:
                best_match_det = best_it
            elif best_overlap >= (min_overlap * 0.5) or it_score >= 0.30:
                marginal_containers += 1
                best_match_det = best_it
            else:
                unprotected_containers += 1
        else:
            unprotected_containers += 1

    if unprotected_containers > 0:
        return (
            FindingStatus.FAIL,
            0.85,
            f"Detected {unprotected_containers} person(s) lacking required protective equipment.",
            confident_containers[0],
        )
    elif marginal_containers > 0:
        return (
            FindingStatus.UNSURE,
            0.50,
            "Protective equipment observed with marginal spatial alignment or confidence.",
            best_match_det or confident_containers[0],
        )
    else:
        return (
            FindingStatus.PASS,
            0.90,
            "All detected personnel are equipped with required protective equipment.",
            best_match_det or confident_containers[0],
        )


# ── Evidence Strength & Decision Policies (WP1) ───────────────────────────────

def select_strongest_evidence(evidence_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Select the strongest evidence item by strength hierarchy:
    mask_backed (3) > model_attested (2) > voice_note (1), with highest score as tiebreaker.
    """
    if not evidence_items:
        return None

    def _rank(item: dict[str, Any]) -> tuple[int, float]:
        strength = str(item.get("strength", "model_attested")).lower()
        if "mask" in strength:
            s_val = 3
        elif "model" in strength or "spark" in strength:
            s_val = 2
        else:
            s_val = 1
        return (s_val, float(item.get("score", 0.0)))

    return max(evidence_items, key=_rank)


def apply_decision_policy(
    rule_type: str,
    provisional_status: str | FindingStatus,
    confidence: float,
    evidence_items: list[dict[str, Any]],
    escalation_ran: bool = False,
    min_absence_k: int = 2,
    num_frames_evaluated: int = 0,
) -> tuple[FindingStatus, float, str, str]:
    """
    Evidence-First decision policy for safety findings:
    1. 'pass' requires mask_backed evidence, OR model_attested evidence across >=2 distinct frames.
       Single-frame model_attested evidence is insufficient for definitive PASS (downgraded to 'unsure').
    2. 'fail-by-absence' requires consensus across >=k frames AND active escalation loop (WP3) ran;
       otherwise status is held as 'unsure'.
    3. Returns: (final_status, confidence, policy_name, policy_rationale)
    """
    settings = get_settings()
    if not getattr(settings, "ENABLE_EVIDENCE_MODEL", True):
        status_enum = FindingStatus(str(provisional_status).lower())
        return status_enum, confidence, "legacy_policy", ""

    prov = str(provisional_status.value if hasattr(provisional_status, "value") else provisional_status).lower()

    mask_backed = [e for e in evidence_items if "mask" in str(e.get("strength", "")).lower()]
    model_attested = [
        e for e in evidence_items
        if "model" in str(e.get("strength", "")).lower() or str(e.get("source", "")).lower() in ("spark", "sam")
    ]

    # 1. PASS Policy Check
    if prov == "pass":
        if mask_backed:
            return (
                FindingStatus.PASS,
                confidence,
                "mask_backed_pass",
                "Verified with mask-backed visual evidence.",
            )
        distinct_frames = {
            int(e.get("frame_id", 0))
            for e in model_attested
            if float(e.get("score", 0.0)) >= 0.5 or e.get("source") == "spark"
        }
        if len(distinct_frames) >= 2:
            return (
                FindingStatus.PASS,
                confidence,
                "multi_frame_model_attested_pass",
                f"Verified with model-attested evidence across {len(distinct_frames)} distinct frames.",
            )
        # Single frame model-attested is insufficient for pass
        return (
            FindingStatus.UNSURE,
            min(confidence, 0.55),
            "single_frame_attested_insufficient",
            "Model attested on only 1 frame without spatial mask; downgraded to unsure pending multi-frame consensus.",
        )

    # 2. FAIL-BY-ABSENCE Policy Check
    if rule_type == "presence" and prov == "fail":
        frames_checked = max(num_frames_evaluated, len({int(e.get("frame_id", 0)) for e in evidence_items}))
        has_k_consensus = frames_checked >= min_absence_k
        if has_k_consensus and escalation_ran:
            return (
                FindingStatus.FAIL,
                confidence,
                "absence_escalated_consensus_fail",
                f"Item confirmed absent across {frames_checked} frames with active escalation verification.",
            )
        else:
            reason = "Absence verification pending escalation loop" if not escalation_ran else f"Insufficient frame consensus ({frames_checked} < {min_absence_k} frames)"
            return (
                FindingStatus.UNSURE,
                0.50,
                "absence_unverified_escalation_unsure",
                f"Item not detected, but {reason}; status held as unsure.",
            )

    # 3. Hazard detected (absence rule failing because obstacle was observed)
    if rule_type == "absence" and prov == "fail":
        return (
            FindingStatus.FAIL,
            confidence,
            "hazard_detected_fail",
            "Hazard or prohibited obstruction detected.",
        )

    status_enum = FindingStatus(prov) if prov in ("pass", "fail", "unsure") else FindingStatus.UNSURE
    return status_enum, confidence, "standard_eval", ""
