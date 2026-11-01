"""Frame sampling, hashing, and storage using OpenCV."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sqlmodel import Session

from app.config import get_settings
from app.models import Frame
from app.storage import get_frames_dir

logger = logging.getLogger(__name__)


class VideoProcessingError(ValueError):
    """Raised when video cannot be read, decoded, or sampled."""
    pass


class FrameList(list):
    """List of Frame objects annotated with candidate frame statistics."""

    def __init__(self, items: list[Frame] | None = None, frames_considered: int = 0):
        super().__init__(items or [])
        self.frames_considered = frames_considered
        self.frames_analyzed = len(self)


def compute_sha256(data: bytes) -> str:
    """Compute hex sha256 digest of binary data."""
    return hashlib.sha256(data).hexdigest()


def compute_sharpness(gray: np.ndarray) -> float:
    """Compute variance of the Laplacian as a metric of image sharpness."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_near_duplicate(
    thumb_a: np.ndarray, thumb_b: np.ndarray, threshold: float = 0.1
) -> bool:
    """Check if two small grayscale thumbnails are visually near-identical."""
    diff = float(np.mean(np.abs(thumb_a.astype(float) - thumb_b.astype(float))))
    return diff < threshold


def sample_frames_from_video(
    video_path: str | Path,
    audit_id: str,
    fps: float | None = None,
    session: Session | None = None,
    max_frames: int = 24,
    min_gap_s: float = 0.5,
    min_sharpness: float = 10.0,
    duplicate_threshold: float = 0.1,
    return_stats: bool = False,
    segmenter: Any = None,
) -> Any:
    """
    Quality-aware keyframe selection from video:
    - Filters frames below Laplacian variance sharpness threshold
    - Removes visually near-duplicate frames
    - Enforces min gap between frames
    - Caps output at max_frames (default 24)
    - Logs candidate frames considered vs keyframes selected
    """
    settings = get_settings()
    sample_fps = fps if fps is not None else settings.FRAME_FPS
    if sample_fps <= 0:
        sample_fps = 1.0

    video_str = str(video_path)
    if not os.path.exists(video_str):
        raise VideoProcessingError(f"Video file does not exist: {video_str}")

    cap = cv2.VideoCapture(video_str)
    if not cap.isOpened():
        raise VideoProcessingError(
            f"Cannot open video file (unreadable or corrupt format): {video_str}"
        )

    native_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if native_fps <= 0 or total_frames <= 0:
        cap.release()
        raise VideoProcessingError(
            f"Video has invalid metadata (fps={native_fps}, frames={total_frames}): {video_str}. File may be corrupt or unreadable."
        )

    duration_s = total_frames / native_fps
    if duration_s > settings.MAX_VIDEO_DURATION_S:
        cap.release()
        raise VideoProcessingError(
            f"Walkthrough video duration ({duration_s:.1f}s) exceeds maximum allowed limit of {settings.MAX_VIDEO_DURATION_S}s. "
            "Please upload a focused walkthrough clip of 90 seconds or less."
        )

    # Determine candidate inspection step and effective min gap
    candidate_fps = max(sample_fps * 4.0, 4.0)
    candidate_step = max(1, int(round(native_fps / candidate_fps)))
    effective_min_gap = min_gap_s if fps is None else max(min_gap_s, (1.0 / fps) * 0.9)

    frames_dir = get_frames_dir(audit_id)
    frames: list[Frame] = []
    current_frame_pos = 0
    saved_idx = 0
    frames_considered = 0

    last_selected_ts: float | None = None
    prev_thumbnail: np.ndarray | None = None
    best_candidate: tuple[np.ndarray, float, float] | None = None  # (mat, ts, sharpness)
    max_sharpness_seen = -1.0

    try:
        while True:
            ret, mat = cap.read()
            if not ret:
                break

            if current_frame_pos % candidate_step == 0:
                frames_considered += 1
                timestamp_s = round(current_frame_pos / native_fps, 3)
                gray = cv2.cvtColor(mat, cv2.COLOR_BGR2GRAY)
                sharpness = compute_sharpness(gray)
                thumb = cv2.resize(gray, (32, 32))

                if sharpness > max_sharpness_seen:
                    max_sharpness_seen = sharpness
                    best_candidate = (mat.copy(), timestamp_s, sharpness)

                # 1. max_frames limit
                if len(frames) >= max_frames:
                    current_frame_pos += 1
                    continue

                # 2. Min gap between selected frames
                if last_selected_ts is not None and (timestamp_s - last_selected_ts) < (effective_min_gap - 1e-4):
                    current_frame_pos += 1
                    continue

                # 3. Sharpness filtering
                if sharpness < min_sharpness:
                    current_frame_pos += 1
                    continue

                # 4. Near-duplicate filtering
                if prev_thumbnail is not None and is_near_duplicate(thumb, prev_thumbnail, duplicate_threshold):
                    current_frame_pos += 1
                    continue

                # Privacy redaction (WP4): blur person masks in memory; unblurred originals are never persisted
                if segmenter is not None and getattr(settings, "PRIVACY_MODE", True):
                    from app.agent.privacy import redact_frame_image
                    mat, _ = redact_frame_image(mat, segmenter=segmenter)

                # Frame passed all quality filters -> encode and save
                frame_filename = f"frame_{saved_idx:04d}.jpg"
                frame_out_path = frames_dir / frame_filename

                success, buffer = cv2.imencode(".jpg", mat, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if not success:
                    raise VideoProcessingError(
                        f"Failed to encode frame at position {current_frame_pos} to JPEG"
                    )

                jpeg_bytes = buffer.tobytes()
                frame_sha256 = compute_sha256(jpeg_bytes)

                with open(frame_out_path, "wb") as f:
                    f.write(jpeg_bytes)

                frame_row = Frame(
                    audit_id=audit_id,
                    idx=saved_idx,
                    timestamp_s=timestamp_s,
                    path=str(frame_out_path),
                    sha256=frame_sha256,
                )
                frames.append(frame_row)
                if session is not None:
                    session.add(frame_row)

                saved_idx += 1
                last_selected_ts = timestamp_s
                prev_thumbnail = thumb

            current_frame_pos += 1
    finally:
        cap.release()

    # Fallback if all frames were filtered out: save the highest-quality candidate
    if not frames and best_candidate is not None:
        mat_fallback, ts_fallback, _ = best_candidate
        if segmenter is not None and getattr(settings, "PRIVACY_MODE", True):
            from app.agent.privacy import redact_frame_image
            mat_fallback, _ = redact_frame_image(mat_fallback, segmenter=segmenter)
        frame_filename = "frame_0000.jpg"
        frame_out_path = frames_dir / frame_filename
        success, buffer = cv2.imencode(".jpg", mat_fallback, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if success:
            jpeg_bytes = buffer.tobytes()
            with open(frame_out_path, "wb") as f:
                f.write(jpeg_bytes)
            frame_row = Frame(
                audit_id=audit_id,
                idx=0,
                timestamp_s=ts_fallback,
                path=str(frame_out_path),
                sha256=compute_sha256(jpeg_bytes),
            )
            frames.append(frame_row)
            if session is not None:
                session.add(frame_row)

    if not frames:
        raise VideoProcessingError(
            f"No frames could be extracted from video: {video_str}"
        )

    logger.info(
        "Keyframe selection: considered %d frames, selected %d frames (max_frames=%d)",
        frames_considered,
        len(frames),
        max_frames,
    )

    out_frames = FrameList(frames, frames_considered=frames_considered)

    if session is not None:
        session.commit()
        for f in out_frames:
            session.refresh(f)

    if return_stats:
        return out_frames, {"considered": frames_considered, "selected": len(out_frames)}
    return out_frames


def sample_frames_from_images(
    image_paths: list[str | Path],
    audit_id: str,
    session: Session | None = None,
    segmenter: Any = None,
) -> list[Frame]:
    """
    Process uploaded standalone image files as audit frames.
    """
    frames_dir = get_frames_dir(audit_id)
    frames: list[Frame] = []

    for idx, img_path in enumerate(image_paths):
        path_str = str(img_path)
        if not os.path.exists(path_str):
            continue

        settings = get_settings()
        dest_filename = f"frame_{idx:04d}.jpg"
        dest_path = frames_dir / dest_filename

        mat = cv2.imread(path_str)
        if mat is not None and segmenter is not None and getattr(settings, "PRIVACY_MODE", True):
            from app.agent.privacy import redact_frame_image
            mat, _ = redact_frame_image(mat, segmenter=segmenter)
            success, buffer = cv2.imencode(".jpg", mat, [cv2.IMWRITE_JPEG_QUALITY, 90])
            data = buffer.tobytes() if success else Path(path_str).read_bytes()
        else:
            with open(path_str, "rb") as f:
                data = f.read()

        sha = compute_sha256(data)
        with open(dest_path, "wb") as f:
            f.write(data)

        # Assign 1s interval per uploaded photo
        timestamp_s = float(idx)
        frame_row = Frame(
            audit_id=audit_id,
            idx=idx,
            timestamp_s=timestamp_s,
            path=str(dest_path),
            sha256=sha,
        )
        frames.append(frame_row)
        if session is not None:
            session.add(frame_row)

    if not frames:
        raise VideoProcessingError("No valid images provided to sample frames from.")

    if session is not None:
        session.commit()
        for f in frames:
            session.refresh(f)

    return frames
