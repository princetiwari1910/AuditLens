"""Frame sampling, hashing, and storage using OpenCV."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import cv2
from sqlmodel import Session

from app.config import get_settings
from app.models import Frame
from app.storage import get_frames_dir


class VideoProcessingError(ValueError):
    """Raised when video cannot be read, decoded, or sampled."""
    pass


def compute_sha256(data: bytes) -> str:
    """Compute hex sha256 digest of binary data."""
    return hashlib.sha256(data).hexdigest()


def sample_frames_from_video(
    video_path: str | Path,
    audit_id: str,
    fps: float | None = None,
    session: Session | None = None,
) -> list[Frame]:
    """
    Sample video frames at `fps` (default: settings.FRAME_FPS), save as JPEGs,
    compute SHA256 checksums, and optionally persist Frame rows to the database.

    Raises VideoProcessingError if the video cannot be opened or is unreadable.
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

    # Calculate frame step based on requested sample_fps
    frame_step = max(1, int(round(native_fps / sample_fps)))
    frames_dir = get_frames_dir(audit_id)

    frames: list[Frame] = []
    current_frame_pos = 0
    saved_idx = 0

    try:
        while True:
            ret, mat = cap.read()
            if not ret:
                break

            if current_frame_pos % frame_step == 0:
                timestamp_s = round(current_frame_pos / native_fps, 3)
                frame_filename = f"frame_{saved_idx:04d}.jpg"
                frame_out_path = frames_dir / frame_filename

                # Encode to JPEG
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

            current_frame_pos += 1
    finally:
        cap.release()

    if not frames:
        raise VideoProcessingError(
            f"No frames could be extracted from video: {video_str}"
        )

    if session is not None:
        session.commit()
        for f in frames:
            session.refresh(f)

    return frames


def sample_frames_from_images(
    image_paths: list[str | Path],
    audit_id: str,
    session: Session | None = None,
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

        with open(path_str, "rb") as f:
            data = f.read()

        sha = compute_sha256(data)
        dest_filename = f"frame_{idx:04d}{Path(path_str).suffix.lower()}"
        dest_path = frames_dir / dest_filename

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
