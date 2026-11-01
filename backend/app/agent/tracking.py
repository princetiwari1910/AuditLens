"""Object tracking across keyframes and temporal consensus evaluation (WP2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid


def compute_iou(box_a: dict[str, float] | None, box_b: dict[str, float] | None) -> float:
    """Calculate Intersection over Union (IoU) for normalized bounding boxes {x, y, w, h}."""
    if not box_a or not box_b:
        return 0.0

    ax1, ay1 = float(box_a.get("x", 0.0)), float(box_a.get("y", 0.0))
    ax2, ay2 = ax1 + float(box_a.get("w", 0.0)), ay1 + float(box_a.get("h", 0.0))

    bx1, by1 = float(box_b.get("x", 0.0)), float(box_b.get("y", 0.0))
    bx2, by2 = bx1 + float(box_b.get("w", 0.0)), by1 + float(box_b.get("h", 0.0))

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection

    return intersection / union if union > 0.0 else 0.0


@dataclass
class Track:
    """Temporal trajectory of a single physical object across video frames."""

    track_id: str = field(default_factory=lambda: f"trk_{uuid.uuid4().hex[:8]}")
    concept: str = ""
    detections: list[dict[str, Any]] = field(default_factory=list)
    start_frame: int = 0
    end_frame: int = 0
    start_ts: float = 0.0
    end_ts: float = 0.0

    @property
    def support_count(self) -> int:
        """Distinct frames where this object was observed."""
        return len({int(d.get("frame_id", 0)) for d in self.detections})

    @property
    def best_detection(self) -> dict[str, Any] | None:
        """Detection with the highest confidence score in this track."""
        if not self.detections:
            return None
        return max(self.detections, key=lambda d: float(d.get("score", 0.0)))

    @property
    def average_confidence(self) -> float:
        if not self.detections:
            return 0.0
        return sum(float(d.get("score", 0.0)) for d in self.detections) / len(self.detections)

    @property
    def stability(self) -> float:
        """Observation continuity across frame span (1.0 = present in every intermediate frame)."""
        span = max(1, (self.end_frame - self.start_frame) + 1)
        return min(1.0, round(self.support_count / span, 2))

    def to_dict(self) -> dict[str, Any]:
        best = self.best_detection
        return {
            "track_id": self.track_id,
            "concept": self.concept,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_ts": round(self.start_ts, 2),
            "end_ts": round(self.end_ts, 2),
            "support_count": self.support_count,
            "average_confidence": round(self.average_confidence, 2),
            "stability": self.stability,
            "best_detection": best,
        }


class ObjectTracker:
    """Greedy IoU tracker with gap tolerance to link detections into physical tracks."""

    def __init__(self, iou_threshold: float = 0.35, max_gap_frames: int = 3) -> None:
        self.iou_threshold = iou_threshold
        self.max_gap_frames = max_gap_frames

    def track(self, detections: list[dict[str, Any]]) -> list[Track]:
        """Group detections across keyframes into continuous physical object tracks."""
        if not detections:
            return []

        # Sort detections by frame index then timestamp
        sorted_dets = sorted(detections, key=lambda d: (int(d.get("frame_id", 0)), float(d.get("timestamp_s", 0.0))))

        tracks: list[Track] = []

        # Group by concept first so different objects never merge
        by_concept: dict[str, list[dict[str, Any]]] = {}
        for d in sorted_dets:
            c = str(d.get("prompt", "")).lower().strip()
            by_concept.setdefault(c, []).append(d)

        for concept, concept_dets in by_concept.items():
            concept_tracks: list[Track] = []

            # Group by frame index
            frames_map: dict[int, list[dict[str, Any]]] = {}
            for d in concept_dets:
                fid = int(d.get("frame_id", 0))
                frames_map.setdefault(fid, []).append(d)

            for fid in sorted(frames_map.keys()):
                frame_dets = frames_map[fid]

                # Find candidate tracks within gap tolerance
                candidates = [
                    trk for trk in concept_tracks
                    if (fid - trk.end_frame) <= self.max_gap_frames
                ]

                matched_track_ids: set[str] = set()
                matched_det_indices: set[int] = set()

                # Greedy match by highest IoU
                match_pairs: list[tuple[float, Track, int, dict[str, Any]]] = []
                for det_idx, det in enumerate(frame_dets):
                    det_box = det.get("bbox")
                    for trk in candidates:
                        if trk.track_id in matched_track_ids:
                            continue
                        last_det = trk.detections[-1]
                        last_box = last_det.get("bbox")
                        iou = compute_iou(det_box, last_box)
                        if iou >= self.iou_threshold:
                            match_pairs.append((iou, trk, det_idx, det))

                match_pairs.sort(key=lambda x: x[0], reverse=True)

                for iou, trk, det_idx, det in match_pairs:
                    if trk.track_id in matched_track_ids or det_idx in matched_det_indices:
                        continue
                    # Match confirmed: append to track
                    trk.detections.append(det)
                    trk.end_frame = fid
                    trk.end_ts = float(det.get("timestamp_s", 0.0))
                    matched_track_ids.add(trk.track_id)
                    matched_det_indices.add(det_idx)

                # Unmatched detections initiate new tracks
                for det_idx, det in enumerate(frame_dets):
                    if det_idx in matched_det_indices:
                        continue
                    ts = float(det.get("timestamp_s", 0.0))
                    new_trk = Track(
                        concept=concept,
                        detections=[det],
                        start_frame=fid,
                        end_frame=fid,
                        start_ts=ts,
                        end_ts=ts,
                    )
                    concept_tracks.append(new_trk)

            tracks.extend(concept_tracks)

        return tracks


def evaluate_temporal_consensus(
    tracks: list[Track],
    total_frames: int = 1,
    min_k: int = 2,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    """
    Evaluate temporal consensus across tracks for a rule:
    - k-of-n frames requirement
    - Confidence-weighted consensus score
    - Outputs best evidence frame, support count, and stability
    """
    if not tracks:
        return {
            "has_consensus": False,
            "support_count": 0,
            "stability": 0.0,
            "best_evidence_frame": 0,
            "best_detection": None,
            "consensus_score": 0.0,
            "track_count": 0,
            "tracks": [],
        }

    # Best track is the one with highest support count then highest average confidence
    best_track = max(tracks, key=lambda t: (t.support_count, t.average_confidence))
    best_det = best_track.best_detection
    best_frame = int(best_det.get("frame_id", 0)) if best_det else best_track.start_frame

    # Confidence-weighted score incorporates support and mean confidence
    k_ratio = min(1.0, best_track.support_count / max(1, min_k))
    consensus_score = round(best_track.average_confidence * (0.6 + 0.4 * k_ratio), 2)
    has_consensus = best_track.support_count >= min_k and best_track.average_confidence >= min_confidence

    return {
        "has_consensus": has_consensus,
        "support_count": best_track.support_count,
        "stability": best_track.stability,
        "best_evidence_frame": best_frame,
        "best_detection": best_det,
        "consensus_score": consensus_score,
        "track_count": len(tracks),
        "tracks": [t.to_dict() for t in tracks],
    }
