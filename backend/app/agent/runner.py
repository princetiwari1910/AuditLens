"""Deterministic mock agent runner implementing the AgentProvider protocol."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Callable

import cv2
import numpy as np
from sqlmodel import Session, select

from app.agent.rules import (
    compute_summary_score,
    evaluate_absence_rule,
    evaluate_colocation_rule,
    evaluate_count_rule,
    evaluate_measurement_rule,
    evaluate_presence_rule,
)
from app.agent.tools import ExecutionContext, ToolRegistry
from app.config import get_settings
from app.costlog import log_cost
from app.models import Audit, AuditStatus, Finding, Frame, RuleModel, VoiceNote
from app.storage import get_overlays_dir


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
    ) -> None:
        self.segmentation_provider = segmentation_provider
        self.transcription_provider = transcription_provider

    def run_audit(
        self,
        audit_id: str,
        rules: list[RuleModel],
        frames: list[dict[str, Any]],
        emit: Callable[[dict[str, Any]], None],
        session: Session | None = None,
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
        emit(_make_event("audit_started", audit_id, {"rule_count": len(rules), "frame_count": len(frames)}))
        emit(_make_event("frames_sampled", audit_id, {"frame_count": len(frames)}))

        # Query existing voice notes from database
        voice_notes_data: list[dict[str, Any]] = []
        if session is not None:
            vn_rows = session.exec(select(VoiceNote).where(VoiceNote.audit_id == audit_id)).all()
            for vn in vn_rows:
                # Transcribe if not already done
                if not vn.transcript and vn.audio_path and Path(vn.audio_path).exists():
                    try:
                        trans = self.transcription_provider.transcribe(vn.audio_path)
                        vn.transcript = trans.text
                        vn.language = trans.language
                        session.add(vn)
                        session.commit()
                        session.refresh(vn)
                        log_cost(session, provider="transcription", operation="transcription", units=0.5, audit_id=audit_id)
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
        )
        registry = ToolRegistry(ctx)

        # 1. First tool call: list_rules
        t0 = time.time()
        emit(_make_event("tool_call", audit_id, {"tool": "list_rules", "args_summary": {}}))
        list_rules_res = registry.execute("list_rules")
        emit(_make_event("tool_result", audit_id, {"tool": "list_rules", "result_summary": f"Loaded {len(rules)} rules", "duration_ms": int((time.time() - t0) * 1000)}))

        findings: list[dict[str, Any]] = []

        try:
            for rule in rules:
                r_type = rule.type
                prompts = rule.sam_prompts or [rule.title]
                primary_prompt = prompts[0]

                best_rep_detection: dict[str, Any] | None = None
                evidence_ids: list[str] = [list_rules_res["result_id"]]
                measurement_data: dict[str, Any] | None = None

                # ── Rule Type Dispatch via Tools ──────────────────────────────
                if r_type == "presence":
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
                if measurement_data:
                    sources.append("measurement")
                if voice_notes_data:
                    closest_note = min(voice_notes_data, key=lambda vn: abs(vn["timestamp_s"] - rep_timestamp_s))
                    if abs(closest_note["timestamp_s"] - rep_timestamp_s) <= 4.0:
                        sources.append("voice_note")
                        if closest_note.get("transcript"):
                            rationale += f" [Auditor Note: \"{closest_note['transcript']}\"]"

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
                    )
                    session.add(finding_row)
                    session.commit()

                emit(_make_event("finding_recorded", audit_id, created_finding))

            # Compute summary score and counts
            summary = compute_summary_score(findings)

            # Update audit in database
            if session is not None:
                audit = session.get(Audit, audit_id)
                if audit:
                    audit.status = AuditStatus.COMPLETED.value
                    audit.summary_json = json.dumps(summary)
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
