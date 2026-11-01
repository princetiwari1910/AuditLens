"""Active evidence gathering (bounded agentic loop) for unsure rules (WP3)."""

from __future__ import annotations

import cv2
import logging
from pathlib import Path
import time
from typing import Any, Callable

from app.agent.tracking import compute_iou
from app.config import get_settings
from app.costlog import log_cost
from app.models import EvidenceItem, EvidenceStrength, FindingStatus
from app.providers.client import BudgetExceededError, estimate_segmentation_cost

logger = logging.getLogger("auditlens.agent.escalation")


def generate_2x2_tiles(
    image_path: str,
    output_dir: Path,
    overlap: float = 0.10,
) -> list[dict[str, Any]]:
    """
    Split a keyframe image into 2x2 overlapping tiles.
    Returns tile paths with normalized offset and scale relative to full frame.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    img = cv2.imread(image_path)
    if img is None:
        return []

    h, w = img.shape[:2]
    # Tile width and height with overlap
    half_w = int(w * (0.5 + overlap / 2))
    half_h = int(h * (0.5 + overlap / 2))

    quadrants = [
        ("tl", 0, 0, half_w, half_h, 0.0, 0.0, half_w / w, half_h / h),
        ("tr", w - half_w, 0, w, half_h, (w - half_w) / w, 0.0, half_w / w, half_h / h),
        ("bl", 0, h - half_h, half_w, h, 0.0, (h - half_h) / h, half_w / w, half_h / h),
        ("br", w - half_w, h - half_h, w, h, (w - half_w) / w, (h - half_h) / h, half_w / w, half_h / h),
    ]

    base_name = Path(image_path).stem
    tiles: list[dict[str, Any]] = []

    for name, x1, y1, x2, y2, norm_x, norm_y, norm_w, norm_h in quadrants:
        crop = img[y1:y2, x1:x2]
        tile_file = output_dir / f"{base_name}_tile_{name}.jpg"
        cv2.imwrite(str(tile_file), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        tiles.append({
            "path": str(tile_file),
            "name": name,
            "x_offset": norm_x,
            "y_offset": norm_y,
            "w_scale": norm_w,
            "h_scale": norm_h,
        })

    return tiles


def map_tile_box_to_full(box: dict[str, float], tile: dict[str, Any]) -> dict[str, float]:
    """Map a normalized box within a tile back to normalized full-frame coordinates."""
    bx = float(box.get("x", 0.0))
    by = float(box.get("y", 0.0))
    bw = float(box.get("w", 0.0))
    bh = float(box.get("h", 0.0))

    return {
        "x": round(tile["x_offset"] + (bx * tile["w_scale"]), 4),
        "y": round(tile["y_offset"] + (by * tile["h_scale"]), 4),
        "w": round(bw * tile["w_scale"], 4),
        "h": round(bh * tile["h_scale"], 4),
    }


def nms_merge(detections: list[dict[str, Any]], iou_thresh: float = 0.40) -> list[dict[str, Any]]:
    """Merge duplicate bounding box detections across overlapping tiles using NMS."""
    if not detections:
        return []

    sorted_dets = sorted(detections, key=lambda d: float(d.get("score", 0.0)), reverse=True)
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

    return kept


def run_active_evidence_gathering(
    rule_id: str,
    concept: str,
    candidate_frame: dict[str, Any],
    all_frames: list[dict[str, Any]],
    segmenter: Any,
    reasoner: Any,
    audit_id: str,
    work_dir: Path,
    session: Any = None,
    pass_threshold: float = 0.60,
    emit_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Active evidence gathering loop (at most 3 steps per rule):
    (a) zoom tiles (2x2 overlapping tiles of candidate frame)
    (b) neighbor frames (+-2s sharp frames)
    (c) Spark vision verification (verify_presence)
    Stops at the first confident outcome or when budget limit is reached.
    """
    steps_log: list[dict[str, Any]] = []
    confident_detection: dict[str, Any] | None = None
    step_count = 0
    max_steps = 3

    target_ts = float(candidate_frame.get("timestamp_s", 0.0))
    target_idx = int(candidate_frame.get("idx", 0))
    target_path = str(candidate_frame.get("path", ""))

    # ── Step 1: Zoom Tiles (2x2) ──────────────────────────────────────────────
    if step_count < max_steps:
        step_count += 1
        t0 = time.time()
        tiles_dir = work_dir / f"escalation_{rule_id}_tiles"
        tiles = generate_2x2_tiles(target_path, tiles_dir)

        tile_detections: list[dict[str, Any]] = []
        cost_step1 = 0.0
        try:
            if tiles:
                tile_paths = [t["path"] for t in tiles]
                cost_step1 = estimate_segmentation_cost(len(tile_paths))
                raw_dets = segmenter.find_objects(tile_paths, concept)

                for d in raw_dets:
                    t_idx = d.frame_id if d.frame_id < len(tiles) else 0
                    tile_info = tiles[t_idx]
                    full_box = map_tile_box_to_full(d.bbox, tile_info)
                    tile_detections.append({
                        "frame_id": target_idx,
                        "timestamp_s": target_ts,
                        "prompt": concept,
                        "score": d.score,
                        "bbox": full_box,
                        "polygon": d.polygon,
                        "source": "sam_zoom_tile",
                        "tile": tile_info["name"],
                    })

                merged = nms_merge(tile_detections)
                best_tile_det = max(merged, key=lambda x: x["score"]) if merged else None

                if best_tile_det and best_tile_det["score"] >= pass_threshold:
                    confident_detection = best_tile_det

            duration_ms = max(int((time.time() - t0) * 1000), 5)
            step_record = {
                "step": "zoom_tiles",
                "step_index": 1,
                "reason": "Initial full-frame search inconclusive; inspecting 2x2 high-resolution tiles.",
                "cost_usd": cost_step1,
                "latency_ms": duration_ms,
                "result": f"Found {len(tile_detections)} candidates ({'Confident match' if confident_detection else 'Uncertain'})",
                "stopped_here": bool(confident_detection),
            }
            steps_log.append(step_record)
            if emit_event:
                emit_event("escalation_step", step_record)

            if session is not None and cost_step1 > 0:
                log_cost(session, "segmentation", "escalation_zoom_tiles", units=len(tiles), audit_id=audit_id, latency_ms=duration_ms, cache_hit=False)

        except BudgetExceededError as bee:
            steps_log.append({"step": "zoom_tiles", "step_index": 1, "error": str(bee), "stopped_here": True})
            return {"confident": False, "best_detection": None, "steps": steps_log, "escalation_ran": True}

        if confident_detection:
            return {"confident": True, "best_detection": confident_detection, "steps": steps_log, "escalation_ran": True}

    # ── Step 2: Neighbor Frames (+-2s) ────────────────────────────────────────
    if step_count < max_steps:
        step_count += 1
        t0 = time.time()
        neighbor_frames = [
            f for f in all_frames
            if f.get("idx") != target_idx and abs(float(f.get("timestamp_s", 0.0)) - target_ts) <= 2.1
        ]

        cost_step2 = 0.0
        try:
            if neighbor_frames:
                n_paths = [f["path"] for f in neighbor_frames]
                cost_step2 = estimate_segmentation_cost(len(n_paths))
                raw_n_dets = segmenter.find_objects(n_paths, concept)

                n_dets: list[dict[str, Any]] = []
                for d in raw_n_dets:
                    nf = neighbor_frames[d.frame_id] if d.frame_id < len(neighbor_frames) else neighbor_frames[0]
                    n_dets.append({
                        "frame_id": nf["idx"],
                        "timestamp_s": nf["timestamp_s"],
                        "prompt": concept,
                        "score": d.score,
                        "bbox": d.bbox,
                        "polygon": d.polygon,
                        "source": "sam_neighbor_frame",
                    })

                best_n_det = max(n_dets, key=lambda x: x["score"]) if n_dets else None
                if best_n_det and best_n_det["score"] >= pass_threshold:
                    confident_detection = best_n_det

            duration_ms = max(int((time.time() - t0) * 1000), 5)
            step_record = {
                "step": "neighbor_frames",
                "step_index": 2,
                "reason": f"Checking temporal neighborhood within +-2s of {target_ts:.1f}s ({len(neighbor_frames)} frames).",
                "cost_usd": cost_step2,
                "latency_ms": duration_ms,
                "result": f"Inspected {len(neighbor_frames)} neighbor frames ({'Confident match' if confident_detection else 'Uncertain'})",
                "stopped_here": bool(confident_detection),
            }
            steps_log.append(step_record)
            if emit_event:
                emit_event("escalation_step", step_record)

            if session is not None and cost_step2 > 0:
                log_cost(session, "segmentation", "escalation_neighbor_frames", units=len(neighbor_frames), audit_id=audit_id, latency_ms=duration_ms, cache_hit=False)

        except BudgetExceededError as bee:
            steps_log.append({"step": "neighbor_frames", "step_index": 2, "error": str(bee), "stopped_here": True})
            return {"confident": False, "best_detection": None, "steps": steps_log, "escalation_ran": True}

        if confident_detection:
            return {"confident": True, "best_detection": confident_detection, "steps": steps_log, "escalation_ran": True}

    # ── Step 3: Spark Vision Verification (verify_presence) ───────────────────
    if step_count < max_steps and hasattr(reasoner, "verify_presence"):
        step_count += 1
        t0 = time.time()
        frames_for_spark = [candidate_frame] + [
            f for f in all_frames if abs(float(f.get("timestamp_s", 0.0)) - target_ts) <= 2.1
        ][:3]

        try:
            spark_res = reasoner.verify_presence(concept, frames_for_spark)
            duration_ms = max(int((time.time() - t0) * 1000), 10)
            is_present = spark_res.get("present", False)

            if is_present:
                cited = spark_res.get("cited_frame_ids", [target_idx])
                first_cited = cited[0] if cited else target_idx
                cited_ts = next((float(f["timestamp_s"]) for f in all_frames if f["idx"] == first_cited), target_ts)
                confident_detection = {
                    "frame_id": first_cited,
                    "timestamp_s": cited_ts,
                    "prompt": concept,
                    "score": 0.85,
                    "bbox": {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5},
                    "polygon": None,
                    "source": "spark_vision_verification",
                    "rationale": spark_res.get("rationale", ""),
                }

            step_record = {
                "step": "spark_vision",
                "step_index": 3,
                "reason": "Final multimodal verification query to Muse Spark 1.3.",
                "cost_usd": 0.002,
                "latency_ms": duration_ms,
                "result": f"Spark verified present: {is_present}",
                "stopped_here": True,
            }
            steps_log.append(step_record)
            if emit_event:
                emit_event("escalation_step", step_record)

            if session is not None:
                log_cost(session, "agent", "escalation_spark_vision", units=0.5, audit_id=audit_id, latency_ms=duration_ms, cache_hit=False)

        except BudgetExceededError as bee:
            steps_log.append({"step": "spark_vision", "step_index": 3, "error": str(bee), "stopped_here": True})

    return {
        "confident": bool(confident_detection),
        "best_detection": confident_detection,
        "steps": steps_log,
        "escalation_ran": True,
    }
