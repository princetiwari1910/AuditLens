"""Deterministic mock agent runner implementing the AgentProvider protocol."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable
import uuid

logger = logging.getLogger("auditlens.agent.runner")

import cv2
import numpy as np
from sqlmodel import Session, select

from app.agent.escalation import run_active_evidence_gathering
from app.agent.rules import (
    apply_decision_policy,
    compute_summary_score,
    evaluate_absence_rule,
    evaluate_colocation_rule,
    evaluate_count_rule,
    evaluate_measurement_rule,
    evaluate_presence_rule,
    select_strongest_evidence,
)
from app.agent.tools import ExecutionContext, ToolRegistry
from app.agent.trace import record_span
from app.agent.tracking import ObjectTracker, evaluate_temporal_consensus
from app.config import get_settings
from app.costlog import log_cost
from app.models import Audit, AuditStatus, EvidenceItem, EvidenceStrength, Finding, FindingStatus, Frame, RuleModel, RuleType, VoiceNote
from app.storage import get_overlays_dir


def redact_error(err: Exception | str) -> str:
    """Redact secret tokens, API keys, and bearer tokens from error strings."""
    msg = str(err)
    msg = re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]+', 'Bearer [REDACTED]', msg)
    msg = re.sub(
        r'(api[_-]?key|model[_-]?api[_-]?key|key)["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-\.]+',
        r'\1=[REDACTED]',
        msg,
        flags=re.IGNORECASE,
    )
    return msg


def _make_event(event_type: str, audit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audit_id": audit_id,
        "payload": payload,
    }


def draw_overlay_image(
    base_frame_path: str,
    output_path: Path,
    finding: dict[str, Any],
    detection: dict[str, Any] | None = None,
) -> str:
    """
    Generate an annotated evidence image using OpenCV with color-coded status badges,
    bounding boxes, and rule labels.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_str = str(output_path)

    img = None
    if Path(base_frame_path).exists():
        img = cv2.imread(base_frame_path)

    if img is None:
        # Fallback canvas if frame path is missing
        img = np.full((720, 1280, 3), (230, 230, 230), dtype=np.uint8)

    h_img, w_img = img.shape[:2]
    status = str(finding.get("status", "unsure")).lower()

    # Color BGR
    if status == "pass":
        color = (40, 180, 40)      # Green
        status_txt = "PASS"
    elif status == "fail":
        color = (30, 30, 220)      # Red
        status_txt = "FAIL"
    else:
        color = (20, 150, 220)     # Amber / Unsure
        status_txt = "UNSURE"

    font = cv2.FONT_HERSHEY_SIMPLEX

    # Draw detection bounding box or polygon if available
    if detection:
        bbox = detection.get("bbox")
        polygon = detection.get("polygon")

        if polygon and len(polygon) >= 3:
            pts = np.array(
                [[int(pt[0] * w_img), int(pt[1] * h_img)] for pt in polygon],
                dtype=np.int32,
            )
            cv2.polylines(img, [pts], isClosed=True, color=color, thickness=3)
        elif bbox:
            bx = int(bbox.get("x", 0) * w_img)
            by = int(bbox.get("y", 0) * h_img)
            bw = int(bbox.get("w", 0.1) * w_img)
            bh = int(bbox.get("h", 0.1) * h_img)
            cv2.rectangle(img, (bx, by), (bx + bw, by + bh), color, 3)

    # Top overlay banner
    banner_h = 60
    overlay_strip = img[0:banner_h, 0:w_img].copy()
    cv2.rectangle(img, (0, 0), (w_img, banner_h), (30, 30, 30), -1)
    cv2.addWeighted(img[0:banner_h, 0:w_img], 0.85, overlay_strip, 0.15, 0, img[0:banner_h, 0:w_img])

    # Status badge
    cv2.rectangle(img, (20, 12), (130, 48), color, -1)
    cv2.putText(img, status_txt, (35, 37), font, 0.7, (255, 255, 255), 2)

    # Rule and rationale text
    rule_id = finding.get("rule_id", "")
    conf = finding.get("confidence", 0.0)
    info_txt = f"Rule: {rule_id}  |  Confidence: {conf:.0%}"
    cv2.putText(img, info_txt, (150, 36), font, 0.65, (240, 240, 240), 2)

    cv2.imwrite(out_str, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out_str


class AgentRunner:
    """
    Deterministic mock planner running through the ToolRegistry.
    Can be seamlessly swapped with an LLM AgentProvider without modifying downstream systems.
    """

    def __init__(
        self,
        segmentation_provider: Any,
        transcription_provider: Any,
        reasoner: Any | None = None,
    ) -> None:
        self.segmentation_provider = segmentation_provider
        self.transcription_provider = transcription_provider
        self.reasoner = reasoner

    def run_audit(
        self,
        audit_id: str,
        rules: list[RuleModel],
        frames: list[dict[str, Any]],
        emit: Callable[[dict[str, Any]], None],
        session: Session | None = None,
        frames_considered: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute deterministic audit plan:
        1. Emits audit_started and frames_sampled events
        2. Iterates over rules, calling tools via ToolRegistry
        3. Enforces Evidence-First validation for findings
        4. Transcribes voice notes and associates with findings
        5. Writes OpenCV overlays and saves finding rows
        6. Emits audit_completed (or error) with final summary
        """
        t_start = time.time()
        considered_count = frames_considered if frames_considered is not None else len(frames)
        emit(_make_event("audit_started", audit_id, {"rule_count": len(rules), "frame_count": len(frames)}))
        emit(_make_event("frames_sampled", audit_id, {"frame_count": len(frames), "considered": considered_count, "analyzed": len(frames)}))

        # Query existing voice notes from database
        voice_notes_data: list[dict[str, Any]] = []
        if session is not None:
            vn_rows = session.exec(select(VoiceNote).where(VoiceNote.audit_id == audit_id)).all()
            for vn in vn_rows:
                # Transcribe if not already done
                if not vn.transcript and vn.audio_path and Path(vn.audio_path).exists():
                    try:
                        t_trans = time.time()
                        trans = self.transcription_provider.transcribe(vn.audio_path)
                        vn.transcript = trans.text
                        vn.language = trans.language
                        session.add(vn)
                        session.commit()
                        session.refresh(vn)
                        trans_lat = max(int((time.time() - t_trans) * 1000), 15)
                        log_cost(
                            session,
                            provider="transcription",
                            operation="transcription",
                            units=0.5,
                            audit_id=audit_id,
                            latency_ms=trans_lat,
                            cache_hit=False,
                        )
                    except Exception:
                        pass
                voice_notes_data.append({
                    "id": vn.id,
                    "timestamp_s": vn.timestamp_s,
                    "transcript": vn.transcript,
                    "language": vn.language,
                })

        ctx = ExecutionContext(
            audit_id=audit_id,
            rules=rules,
            frames=frames,
            segmentation_provider=self.segmentation_provider,
            transcription_provider=self.transcription_provider,
            voice_notes=voice_notes_data,
            session=session,
            reasoner=self.reasoner,
        )
        registry = ToolRegistry(ctx)

        # 1. First tool call: list_rules
        t0 = time.time()
        emit(_make_event("tool_call", audit_id, {"tool": "list_rules", "args_summary": {}}))
        list_rules_res = registry.execute("list_rules")
        duration_ms = int((time.time() - t0) * 1000)
        emit(_make_event("tool_result", audit_id, {"tool": "list_rules", "result_summary": f"Loaded {len(rules)} rules", "duration_ms": duration_ms}))

        if session is not None:
            # Trace keyframe selection span (WP6)
            record_span(
                session=session,
                audit_id=audit_id,
                stage="keyframe_selection",
                model="opencv",
                latency_ms=25,
                step_reason=f"Quality selection: {considered_count} considered -> {len(frames)} selected",
            )
            # Log agent planning reasoning cost (Muse Spark)
            log_cost(
                session,
                provider="agent",
                operation="agent_input",
                units=round(0.8 + 0.15 * len(rules), 2),
                audit_id=audit_id,
                latency_ms=max(duration_ms, 25),
                cache_hit=False,
            )
            log_cost(
                session,
                provider="agent",
                operation="agent_output",
                units=0.25,
                audit_id=audit_id,
                latency_ms=12,
                cache_hit=False,
            )

        findings: list[dict[str, Any]] = []

        try:
            for rule in rules:
                try:
                    r_type = rule.type
                    prompts = rule.sam_prompts or [rule.title]
                    primary_prompt = prompts[0]
                    detector = getattr(rule, "detector", "sam") or "sam"

                    best_rep_detection: dict[str, Any] | None = None
                    evidence_ids: list[str] = [list_rules_res["result_id"]]
                    measurement_data: dict[str, Any] | None = None
                    evidence_ledger: list[dict[str, Any]] = []

                    # ── Rule Type Dispatch via Tools ──────────────────────────────
                    if detector == "spark_vision" and r_type == "presence":
                        emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "verify_presence", "args_summary": {"concept": primary_prompt}}))
                        t0 = time.time()
                        v_res = registry.execute("verify_presence", concept=primary_prompt)
                        emit(_make_event("tool_result", audit_id, {"tool": "verify_presence", "result_summary": f"Verified: {v_res['present']}", "duration_ms": int((time.time() - t0) * 1000)}))
                        evidence_ids.append(v_res["result_id"])

                        is_pres = v_res.get("present", False)
                        cited = v_res.get("cited_frame_ids", [])
                        status = FindingStatus.PASS if is_pres else FindingStatus.FAIL
                        conf = 0.85 if is_pres else 0.40
                        rationale = v_res.get("rationale") or f"Spark vision verification: {primary_prompt} {'present' if is_pres else 'absent'}."

                        for fid in cited:
                            f_ts = next((float(f.get("timestamp_s", 0.0)) for f in frames if f.get("idx") == fid), 0.0)
                            evidence_ledger.append({
                                "id": f"ev_{uuid.uuid4().hex[:8]}",
                                "frame_id": fid,
                                "ts": f_ts,
                                "source": "spark",
                                "concept": primary_prompt,
                                "box": None,
                                "mask_ref": None,
                                "score": conf,
                                "strength": EvidenceStrength.MODEL_ATTESTED.value,
                            })

                    elif r_type == "presence":
                        emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "find_objects", "args_summary": {"prompt": primary_prompt}}))
                        t0 = time.time()
                        find_res = registry.execute("find_objects", prompt=primary_prompt)
                        emit(_make_event("tool_result", audit_id, {"tool": "find_objects", "result_summary": f"Found {find_res['count']} detections", "duration_ms": int((time.time() - t0) * 1000)}))
                        evidence_ids.append(find_res["result_id"])

                        status, conf, rationale, best_det = evaluate_presence_rule(
                            find_res["detections"],
                            threshold=rule.params.get("min_score"),
                        )
                        best_rep_detection = best_det

                        for d in find_res.get("detections", []):
                            has_mask = bool(d.get("polygon") or d.get("mask"))
                            evidence_ledger.append({
                                "id": f"ev_{uuid.uuid4().hex[:8]}",
                                "frame_id": int(d.get("frame_id", 0)),
                                "ts": float(d.get("timestamp_s", 0.0)),
                                "source": "sam",
                                "concept": primary_prompt,
                                "box": d.get("bbox"),
                                "mask_ref": d.get("polygon") or d.get("mask"),
                                "score": float(d.get("score", 0.0)),
                                "strength": EvidenceStrength.MASK_BACKED.value if has_mask else EvidenceStrength.MODEL_ATTESTED.value,
                            })

                        # If hybrid sam_then_spark and initial pass is not confirmed
                        if detector == "sam_then_spark" and (status == FindingStatus.UNSURE or not find_res.get("detections")):
                            emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "verify_presence", "args_summary": {"concept": primary_prompt, "escalation": True}}))
                            t0 = time.time()
                            v_res = registry.execute("verify_presence", concept=primary_prompt)
                            emit(_make_event("tool_result", audit_id, {"tool": "verify_presence", "result_summary": f"Escalated verification: {v_res['present']}", "duration_ms": int((time.time() - t0) * 1000)}))
                            evidence_ids.append(v_res["result_id"])
                            if v_res.get("present"):
                                status = FindingStatus.PASS
                                conf = 0.85
                                rationale += f" [Escalated Spark verification: {v_res.get('rationale')}]"
                                for fid in v_res.get("cited_frame_ids", []):
                                    f_ts = next((float(f.get("timestamp_s", 0.0)) for f in frames if f.get("idx") == fid), 0.0)
                                    evidence_ledger.append({
                                        "id": f"ev_{uuid.uuid4().hex[:8]}",
                                        "frame_id": fid,
                                        "ts": f_ts,
                                        "source": "spark",
                                        "concept": primary_prompt,
                                        "box": None,
                                        "mask_ref": None,
                                        "score": 0.85,
                                        "strength": EvidenceStrength.MODEL_ATTESTED.value,
                                    })

                    elif r_type == "absence":
                        all_dets = []
                        for p in prompts:
                            emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "find_objects", "args_summary": {"prompt": p}}))
                            t0 = time.time()
                            f_res = registry.execute("find_objects", prompt=p)
                            emit(_make_event("tool_result", audit_id, {"tool": "find_objects", "result_summary": f"Found {f_res['count']} detections for '{p}'", "duration_ms": int((time.time() - t0) * 1000)}))
                            evidence_ids.append(f_res["result_id"])
                            all_dets.extend(f_res["detections"])

                        status, conf, rationale, best_det = evaluate_absence_rule(
                            all_dets,
                            threshold=rule.params.get("threshold"),
                        )
                        best_rep_detection = best_det

                    elif r_type == "count":
                        emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "find_objects", "args_summary": {"prompt": primary_prompt}}))
                        t0 = time.time()
                        find_res = registry.execute("find_objects", prompt=primary_prompt)
                        emit(_make_event("tool_result", audit_id, {"tool": "find_objects", "result_summary": f"Found {find_res['count']} detections", "duration_ms": int((time.time() - t0) * 1000)}))
                        evidence_ids.append(find_res["result_id"])

                        status, conf, rationale, best_det = evaluate_count_rule(
                            find_res["detections"],
                            min_count=int(rule.params.get("min_count", 2)),
                            threshold=rule.params.get("min_score"),
                        )
                        best_rep_detection = best_det

                    elif r_type == "measurement":
                        ref_cfg = rule.params.get("reference", {"type": "a4"})
                        if isinstance(ref_cfg, str):
                            ref_cfg = {"type": ref_cfg}

                        emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "measure_clear_width", "args_summary": {"prompts": prompts}}))
                        t0 = time.time()
                        meas_res = registry.execute("measure_clear_width", obstacle_prompts=prompts, reference=ref_cfg)
                        emit(_make_event("tool_result", audit_id, {"tool": "measure_clear_width", "result_summary": f"Width: {meas_res['width_m']:.2f}m (+/- {meas_res['uncertainty_m']:.2f}m)", "duration_ms": int((time.time() - t0) * 1000)}))
                        evidence_ids.append(meas_res["result_id"])
                        measurement_data = meas_res

                        status, conf, rationale = evaluate_measurement_rule(
                            meas_res,
                            min_width_m=float(rule.params.get("min_width_m", 1.0)),
                        )

                    elif r_type == "colocation":
                        c_prompt = rule.params.get("container_prompt", "person")
                        i_prompt = rule.params.get("item_prompt", prompts[-1])
                        min_ov = float(rule.params.get("min_overlap", 0.20))

                        emit(_make_event("tool_call", audit_id, {"rule_id": rule.id, "tool": "check_colocation", "args_summary": {"container": c_prompt, "item": i_prompt}}))
                        t0 = time.time()
                        colo_res = registry.execute("check_colocation", container_prompt=c_prompt, item_prompt=i_prompt, min_overlap=min_ov)
                        emit(_make_event("tool_result", audit_id, {"tool": "check_colocation", "result_summary": f"{len(colo_res['matches'])} colocation matches", "duration_ms": int((time.time() - t0) * 1000)}))
                        evidence_ids.append(colo_res["result_id"])

                        status, conf, rationale, best_det = evaluate_colocation_rule(
                            colo_res["containers"],
                            colo_res["items"],
                            min_overlap=min_ov,
                        )
                        best_rep_detection = best_det

                    else:
                        # Fallback
                        status = "unsure"
                        conf = 0.5
                        rationale = f"Unsupported rule type '{r_type}'."

                    # Frame index and timestamp for the finding
                    rep_frame_idx = best_rep_detection.get("frame_id", 0) if best_rep_detection else 0
                    rep_timestamp_s = best_rep_detection.get("timestamp_s", 0.0) if best_rep_detection else 0.0

                    # Check for nearby voice note evidence
                    sources = ["segmentation"]
                    if detector == "spark_vision":
                        sources = ["spark_vision"]
                    elif detector == "sam_then_spark" and 'v_res' in locals():
                        sources = ["segmentation", "spark_vision"]
                    if measurement_data:
                        sources.append("measurement")
                    if voice_notes_data:
                        closest_note = min(voice_notes_data, key=lambda vn: abs(vn["timestamp_s"] - rep_timestamp_s))
                        if abs(closest_note["timestamp_s"] - rep_timestamp_s) <= 5.0:
                            sources.append("voice_note")
                            raw_transcript = closest_note.get("transcript") or ""
                            structured_note: dict[str, Any] = {}
                            if raw_transcript:
                                try:
                                    extract_reasoner = self.reasoner
                                    if extract_reasoner is None:
                                        from app.providers.mock import MockReasoner
                                        extract_reasoner = MockReasoner()
                                    if hasattr(extract_reasoner, "extract_note"):
                                        structured_note = extract_reasoner.extract_note(raw_transcript)
                                except Exception:
                                    pass

                            loc_str = structured_note.get("location", "")
                            issue_str = structured_note.get("issue", "")
                            sev_hint = structured_note.get("severity_hint", "")

                            tag_parts = [p for p in [loc_str, sev_hint] if p]
                            tag_header = f"Auditor Note: ({', '.join(tag_parts)})" if tag_parts else "Auditor Note:"
                            if raw_transcript:
                                rationale += f" [{tag_header} \"{raw_transcript}\"]"

                            evidence_ledger.append({
                                "id": f"ev_{uuid.uuid4().hex[:8]}",
                                "frame_id": rep_frame_idx,
                                "ts": float(closest_note["timestamp_s"]),
                                "source": "voice",
                                "concept": issue_str or raw_transcript or "voice note",
                                "location": loc_str or "general",
                                "severity_hint": sev_hint or "medium",
                                "box": None,
                                "mask_ref": None,
                                "score": 0.90,
                                "strength": EvidenceStrength.VOICE_NOTE.value,
                            })

                    # Temporal consensus via ObjectTracker (WP2)
                    supp_cnt = 1
                    stability_val = 1.0
                    settings = get_settings()
                    if getattr(settings, "ENABLE_TRACKING", True):
                        tracker_input_dets = []
                        if r_type == "presence" and 'find_res' in locals():
                            tracker_input_dets = find_res.get("detections", [])
                        elif r_type == "absence" and 'all_dets' in locals():
                            tracker_input_dets = all_dets
                        elif r_type == "count" and 'find_res' in locals():
                            tracker_input_dets = find_res.get("detections", [])

                        if tracker_input_dets:
                            tracker = ObjectTracker()
                            rule_tracks = tracker.track(tracker_input_dets)
                            consensus_res = evaluate_temporal_consensus(
                                rule_tracks,
                                total_frames=len(frames),
                                min_k=int(rule.params.get("min_k", 2)),
                                min_confidence=float(rule.params.get("min_score", 0.6)),
                            )
                            supp_cnt = consensus_res["support_count"]
                            stability_val = consensus_res["stability"]
                            if consensus_res["best_detection"]:
                                best_rep_detection = consensus_res["best_detection"]

                    # Active Evidence Gathering (WP3) bounded loop if presence rule is unsure or concept never detected
                    escalation_steps: list[dict[str, Any]] = []
                    escalation_did_run = False
                    if getattr(settings, "ENABLE_ACTIVE_GATHERING", True) and r_type == RuleType.PRESENCE and (status in (FindingStatus.UNSURE, "unsure") or not best_rep_detection):
                        candidate_f = frames[rep_frame_idx] if rep_frame_idx < len(frames) else (frames[0] if frames else {})
                        work_d = settings.DATA_DIR / "audits" / audit_id
                        esc_res = run_active_evidence_gathering(
                            rule_id=rule.id,
                            concept=primary_prompt,
                            candidate_frame=candidate_f,
                            all_frames=frames,
                            segmenter=self.segmentation_provider,
                            reasoner=self.reasoner,
                            audit_id=audit_id,
                            work_dir=work_d,
                            session=session,
                            pass_threshold=rule.params.get("min_score", 0.60),
                            emit_event=lambda t, p: emit(_make_event(t, audit_id, p)),
                        )
                        escalation_steps = esc_res.get("steps", [])
                        escalation_did_run = esc_res.get("escalation_ran", False)
                        if esc_res.get("confident") and esc_res.get("best_detection"):
                            best_rep_detection = esc_res["best_detection"]
                            rep_frame_idx = int(best_rep_detection.get("frame_id", rep_frame_idx))
                            rep_timestamp_s = float(best_rep_detection.get("timestamp_s", rep_timestamp_s))
                            status = FindingStatus.PASS
                            conf = float(best_rep_detection.get("score", 0.85))
                            rationale += f" [Resolved via active evidence gathering ({best_rep_detection.get('source')})]"
                            evidence_ledger.append({
                                "id": f"ev_{uuid.uuid4().hex[:8]}",
                                "frame_id": rep_frame_idx,
                                "ts": rep_timestamp_s,
                                "source": "sam" if "sam" in best_rep_detection.get("source", "") else "spark",
                                "concept": primary_prompt,
                                "box": best_rep_detection.get("bbox"),
                                "mask_ref": best_rep_detection.get("polygon"),
                                "score": conf,
                                "strength": EvidenceStrength.MASK_BACKED.value if best_rep_detection.get("polygon") else EvidenceStrength.MODEL_ATTESTED.value,
                            })

                    # Apply Decision Policy (WP1)
                    status, conf, decision_policy, policy_rat = apply_decision_policy(
                        rule_type=r_type,
                        provisional_status=status,
                        confidence=conf,
                        evidence_items=evidence_ledger,
                        escalation_ran=(escalation_did_run or (detector == "sam_then_spark" and 'v_res' in locals())),
                        min_absence_k=2,
                        num_frames_evaluated=len(frames),
                    )
                    if policy_rat:
                        rationale = f"{rationale} ({policy_rat})" if rationale else policy_rat

                    strongest_ev = select_strongest_evidence(evidence_ledger)

                    # Record finding through ToolRegistry (strictly checks evidence_ids)
                    rec_res = registry.execute(
                        "record_finding",
                        rule_id=rule.id,
                        status=status.value if hasattr(status, "value") else str(status),
                        confidence=conf,
                        evidence_ids=evidence_ids,
                        frame_id=rep_frame_idx,
                        timestamp_s=rep_timestamp_s,
                        measurement=measurement_data,
                        rationale=rationale,
                        severity=rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity),
                        sources=sources,
                        fix_text=rule.fix_text if status != "pass" else "",
                        evidence_ledger=evidence_ledger,
                        strongest_evidence=strongest_ev,
                        decision_policy=decision_policy,
                        detector=detector,
                        support_count=supp_cnt,
                        stability=stability_val,
                        escalation_steps=escalation_steps,
                    )

                    created_finding = rec_res["finding"]

                    # Generate visual overlay image
                    overlays_dir = get_overlays_dir(audit_id)
                    overlay_filename = f"overlay_{created_finding['id']}.jpg"
                    overlay_path = overlays_dir / overlay_filename

                    base_frame_path = ""
                    for f in frames:
                        if f["idx"] == rep_frame_idx:
                            base_frame_path = f["path"]
                            break
                    if not base_frame_path and frames:
                        base_frame_path = frames[0]["path"]

                    draw_overlay_image(
                        base_frame_path=base_frame_path,
                        output_path=overlay_path,
                        finding=created_finding,
                        detection=best_rep_detection,
                    )

                    created_finding["overlay_url"] = f"/api/audits/{audit_id}/overlays/{created_finding['id']}"
                    findings.append(created_finding)

                    # Persist finding row in database
                    if session is not None:
                        finding_row = Finding(
                            id=created_finding["id"],
                            audit_id=audit_id,
                            rule_id=created_finding["rule_id"],
                            status=created_finding["status"],
                            confidence=created_finding["confidence"],
                            timestamp_s=created_finding["timestamp_s"],
                            frame_idx=created_finding["frame_idx"],
                            overlay_path=str(overlay_path),
                            measurement_json=json.dumps(measurement_data) if measurement_data else None,
                            rationale=created_finding["rationale"],
                            fix_text=created_finding["fix_text"],
                            severity=created_finding["severity"],
                            sources_json=json.dumps(sources),
                            evidence_ledger_json=json.dumps(created_finding.get("evidence_ledger", [])),
                            strongest_evidence_json=json.dumps(created_finding.get("strongest_evidence")) if created_finding.get("strongest_evidence") else None,
                            decision_policy=created_finding.get("decision_policy", "default"),
                            detector=created_finding.get("detector", "sam"),
                            support_count=supp_cnt,
                            stability=stability_val,
                            escalation_steps_json=json.dumps(created_finding.get("escalation_steps", [])),
                            ai_verdict=created_finding["status"],
                            final_verdict=created_finding["status"],
                        )
                        session.add(finding_row)
                        session.commit()

                        # Trace execution spans (WP6)
                        record_span(
                            session=session,
                            audit_id=audit_id,
                            stage="segmentation",
                            model=settings.MODEL_ID_SEGMENTATION,
                            concept=primary_prompt,
                            latency_ms=45,
                            cost_usd=round(len(frames) * 0.0002, 5),
                            cache_hit=False,
                            step_reason=f"Segmented concept '{primary_prompt}' for rule {rule.id}",
                        )
                        for esc_step in escalation_steps:
                            record_span(
                                session=session,
                                audit_id=audit_id,
                                stage="active_gathering",
                                model=esc_step.get("model", settings.MODEL_ID_SEGMENTATION),
                                concept=primary_prompt,
                                latency_ms=int(esc_step.get("latency_ms", 35)),
                                cost_usd=float(esc_step.get("cost_usd", 0.001)),
                                step_reason=f"Step {esc_step.get('step')}: {esc_step.get('action')} ({esc_step.get('outcome')})",
                            )

                    emit(_make_event("finding_recorded", audit_id, created_finding))

                except Exception as rule_exc:
                    # A live provider error must never crash the run: log the redacted error into the trace and downgrade that rule to "unsure"
                    redacted_err = redact_error(rule_exc)
                    logger.warning("Provider error evaluating rule '%s': %s", rule.id, redacted_err)
                    if session is not None:
                        record_span(
                            session=session,
                            audit_id=audit_id,
                            stage="provider_error",
                            model=getattr(rule, "detector", "meta_provider") or "meta_provider",
                            concept=getattr(rule, "sam_prompts", [rule.title])[0] if getattr(rule, "sam_prompts", None) else rule.title,
                            latency_ms=0,
                            cost_usd=0.0,
                            step_reason=f"Provider error downgraded to unsure: {redacted_err}",
                        )
                    fallback_finding = {
                        "id": f"f_{uuid.uuid4().hex[:8]}",
                        "rule_id": rule.id,
                        "status": FindingStatus.UNSURE.value,
                        "confidence": 0.50,
                        "timestamp_s": 0.0,
                        "frame_id": 0,
                        "rationale": f"Provider error fallback (rule downgraded to unsure): {redacted_err}",
                        "fix_text": f"Manual inspection required due to provider error on rule '{rule.id}'.",
                        "severity": getattr(rule, "severity", "medium") or "medium",
                        "sources": ["error_fallback"],
                        "evidence_ledger": [],
                        "strongest_evidence": None,
                        "decision_policy": "error_fallback",
                        "detector": getattr(rule, "detector", "sam") or "sam",
                        "support_count": 0,
                        "stability": 0.0,
                        "escalation_steps": [],
                    }
                    findings.append(fallback_finding)
                    if session is not None:
                        try:
                            session.rollback()
                        except Exception:
                            pass
                        finding_row = Finding(
                            id=fallback_finding["id"],
                            audit_id=audit_id,
                            rule_id=rule.id,
                            status=fallback_finding["status"],
                            confidence=fallback_finding["confidence"],
                            timestamp_s=fallback_finding["timestamp_s"],
                            frame_idx=int(fallback_finding.get("frame_id", 0)),
                            rationale=fallback_finding["rationale"],
                            fix_text=fallback_finding["fix_text"],
                            severity=fallback_finding["severity"],
                            sources_json=json.dumps(fallback_finding["sources"]),
                            evidence_ledger_json="[]",
                            strongest_evidence_json=None,
                            decision_policy="error_fallback",
                            detector=fallback_finding["detector"],
                            support_count=0,
                            stability=0.0,
                            escalation_steps_json="[]",
                            ai_verdict=fallback_finding["status"],
                            final_verdict=fallback_finding["status"],
                        )
                        session.add(finding_row)
                        session.commit()
                    emit(_make_event("finding_recorded", audit_id, fallback_finding))

            # Compute summary score and counts
            summary = compute_summary_score(findings)
            summary["frames_analyzed"] = len(frames)
            summary["frames_considered"] = considered_count

            # Generate prioritized fix plan grounded in findings (WP10)
            fix_plan: list[dict[str, Any]] = []
            try:
                plan_reasoner = self.reasoner
                if plan_reasoner is None:
                    from app.providers.mock import MockReasoner
                    plan_reasoner = MockReasoner()
                if hasattr(plan_reasoner, "plan_fixes"):
                    res = plan_reasoner.plan_fixes(findings)
                    fix_plan = res if isinstance(res, list) else []
            except Exception as e:
                logger.warning("Could not generate fix plan: %s", e)
                fix_plan = []

            if not isinstance(fix_plan, list):
                fix_plan = []

            # Update audit in database
            if session is not None:
                audit = session.get(Audit, audit_id)
                if audit:
                    audit.status = AuditStatus.COMPLETED.value
                    audit.summary_json = json.dumps(summary)
                    audit.fix_plan_json = json.dumps(fix_plan)
                    audit.duration_s = round(time.time() - t_start, 2)
                    session.add(audit)
                    session.commit()

            # ALWAYS emit final event
            emit(_make_event("audit_completed", audit_id, {"summary": summary, "findings_count": len(findings)}))
            return findings

        except Exception as exc:
            err_msg = str(exc)
            if session is not None:
                audit = session.get(Audit, audit_id)
                if audit:
                    audit.status = AuditStatus.FAILED.value
                    audit.error = err_msg
                    session.add(audit)
                    session.commit()

            # ALWAYS emit error event as final event on failure
            emit(_make_event("error", audit_id, {"error": err_msg}))
            raise
