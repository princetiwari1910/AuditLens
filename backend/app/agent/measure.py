"""Geometry, scale calibration, and horizontal walkway clear-width measurement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


A4_LONG_SIDE_METERS = 0.297  # Standard ISO 216 A4 length (297 mm)
DEFAULT_UNCERTAINTY_RATIO = 0.10  # +/- 10% uncertainty default


@dataclass
class MeasurementResult:
    width_m: float
    uncertainty_m: float
    pixels_per_meter: float
    method: str
    assumptions: str
    reference_type: str
    raw_pixel_width: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "width_m": round(self.width_m, 3),
            "uncertainty_m": round(self.uncertainty_m, 3),
            "pixels_per_meter": round(self.pixels_per_meter, 2),
            "method": self.method,
            "assumptions": self.assumptions,
            "reference_type": self.reference_type,
            "raw_pixel_width": round(self.raw_pixel_width, 1),
        }


def compute_pixels_per_meter(
    reference: dict[str, Any],
    frame_width_px: int = 1280,
    frame_height_px: int = 720,
    reference_detection: dict[str, Any] | None = None,
) -> tuple[float, str]:
    """
    Compute pixels_per_meter scale from either:
    1. 'manual': explicit pixels_per_meter provided in reference config.
    2. 'a4': detected A4 sheet bounding box in normalized coordinates.
             Uses the maximum dimension of the bbox as the A4 long edge (0.297 m).

    Returns (pixels_per_meter, method_description).
    """
    ref_type = str(reference.get("type", "a4")).lower()

    if ref_type == "manual":
        ppm = float(reference.get("pixels_per_meter", 400.0))
        return max(1.0, ppm), "Manual scale calibration (pixels_per_meter specified directly)"

    # A4 sheet calibration
    if reference_detection is not None and "bbox" in reference_detection:
        bbox = reference_detection["bbox"]
        # bbox is normalized {x, y, w, h}
        w_px = bbox.get("w", 0.08) * frame_width_px
        h_px = bbox.get("h", 0.08) * frame_height_px
        long_edge_px = max(w_px, h_px)
        if long_edge_px > 5:
            ppm = long_edge_px / A4_LONG_SIDE_METERS
            return ppm, f"A4 optical reference calibration ({long_edge_px:.1f}px = {A4_LONG_SIDE_METERS}m)"

    # Fallback default calibration based on standard smartphone 1080p/720p FOV at 2.5m walkway distance
    fallback_ppm = 380.0
    return fallback_ppm, "Standard room perspective heuristic calibration (no visible reference detected)"


def estimate_clear_width(
    obstacle_boxes: list[dict[str, float]],
    frame_width_px: int = 1280,
    frame_height_px: int = 720,
    pixels_per_meter: float = 380.0,
    walkway_x_min_norm: float = 0.15,
    walkway_x_max_norm: float = 0.85,
    method: str = "A4 optical reference calibration",
) -> MeasurementResult:
    """
    Estimate the minimum clear horizontal width across the walkway corridor at floor level.

    Limitations and Assumptions (Documented per specifications):
    1. Perspective distortion: 2D bounding box projections assume obstacles are roughly
       coplanar with the floor depth plane where the reference object is positioned.
    2. Reference placement: The reference object (e.g. A4 sheet) must reside at approximately
       the same focal distance / depth as the measured corridor bottleneck.
    3. Camera orientation: Assumes camera optical axis is approximately level or slightly tilted
       downward, avoiding extreme acute diagonal perspectives.

    Algorithm:
    - Defines the active walkway horizontal span [walkway_x_min, walkway_x_max].
    - Projects obstacle horizontal spans [obs_x, obs_x + obs_w] into this walkway corridor.
    - Determines the largest contiguous clear gap between obstacles and corridor boundaries.
    - Converts the minimum bottleneck opening to meters using pixels_per_meter.
    - Applies a default +/- 10% uncertainty band (minimum 0.05 m).
    """
    walkway_left_px = walkway_x_min_norm * frame_width_px
    walkway_right_px = walkway_x_max_norm * frame_width_px
    walkway_total_px = walkway_right_px - walkway_left_px

    if not obstacle_boxes:
        # No obstacles: full walkway width is clear
        width_m = walkway_total_px / pixels_per_meter
        uncertainty_m = max(0.05, width_m * DEFAULT_UNCERTAINTY_RATIO)
        return MeasurementResult(
            width_m=width_m,
            uncertainty_m=uncertainty_m,
            pixels_per_meter=pixels_per_meter,
            method=method,
            assumptions=(
                "Obstacle-free corridor; calibrated across active walkway horizontal span. "
                "Assumes planar floor geometry and consistent camera focal depth."
            ),
            reference_type="optical_reference",
            raw_pixel_width=walkway_total_px,
        )

    # Convert obstacle normalized bounding boxes to 1D horizontal segments within the walkway
    intervals: list[tuple[float, float]] = []
    for b in obstacle_boxes:
        # Only consider obstacles located in the lower half of the frame (floor / walkway level)
        y = b.get("y", 0.5)
        h = b.get("h", 0.2)
        if (y + h) >= 0.45:  # Touches or extends into floor zone
            obs_left = b.get("x", 0.0) * frame_width_px
            obs_right = obs_left + (b.get("w", 0.1) * frame_width_px)
            # Clip to walkway boundaries
            clipped_left = max(walkway_left_px, min(walkway_right_px, obs_left))
            clipped_right = max(walkway_left_px, min(walkway_right_px, obs_right))
            if clipped_right > clipped_left:
                intervals.append((clipped_left, clipped_right))

    if not intervals:
        width_m = walkway_total_px / pixels_per_meter
        uncertainty_m = max(0.05, width_m * DEFAULT_UNCERTAINTY_RATIO)
        return MeasurementResult(
            width_m=width_m,
            uncertainty_m=uncertainty_m,
            pixels_per_meter=pixels_per_meter,
            method=method,
            assumptions="Obstacles detected outside walkway floor zone; full corridor span preserved.",
            reference_type="optical_reference",
            raw_pixel_width=walkway_total_px,
        )

    # Merge overlapping obstacle intervals
    intervals.sort(key=lambda iv: iv[0])
    merged: list[tuple[float, float]] = [intervals[0]]
    for cur_left, cur_right in intervals[1:]:
        prev_left, prev_right = merged[-1]
        if cur_left <= prev_right:
            merged[-1] = (prev_left, max(prev_right, cur_right))
        else:
            merged.append((cur_left, cur_right))

    # Calculate free gaps between corridor edges and merged obstacles
    gaps: list[float] = []
    current_x = walkway_left_px
    for obs_left, obs_right in merged:
        gap = obs_left - current_x
        if gap > 0:
            gaps.append(gap)
        current_x = max(current_x, obs_right)

    final_gap = walkway_right_px - current_x
    if final_gap > 0:
        gaps.append(final_gap)

    max_gap_px = max(gaps) if gaps else 0.0
    width_m = max_gap_px / pixels_per_meter
    uncertainty_m = max(0.05, width_m * DEFAULT_UNCERTAINTY_RATIO)

    assumptions = (
        "Linear gap projection at floor level between detected obstacle bounding boxes. "
        "Assumes reference object resides at comparable depth with minimal perspective foreshortening."
    )

    return MeasurementResult(
        width_m=width_m,
        uncertainty_m=uncertainty_m,
        pixels_per_meter=pixels_per_meter,
        method=method,
        assumptions=assumptions,
        reference_type="optical_reference",
        raw_pixel_width=max_gap_px,
    )
