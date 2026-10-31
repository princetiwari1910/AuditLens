"""Video normalization and metadata inspection using ffprobe and ffmpeg."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.config import get_settings
from app.storage import StorageValidationError


def require_ffmpeg_and_ffprobe() -> tuple[str, str]:
    """Ensure ffmpeg and ffprobe are available on PATH; fail loudly if missing."""
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        missing = []
        if not ffmpeg_bin:
            missing.append("ffmpeg")
        if not ffprobe_bin:
            missing.append("ffprobe")
        raise RuntimeError(
            f"Missing required video tools: {', '.join(missing)}. "
            f"Please install ffmpeg (e.g. 'brew install ffmpeg' or 'apt-get install ffmpeg') to process video uploads."
        )
    return ffmpeg_bin, ffprobe_bin


def probe_video(video_path: Path) -> dict[str, Any]:
    """Run ffprobe to extract stream, codec, pixel format, and rotation metadata."""
    _, ffprobe_bin = require_ffmpeg_and_ffprobe()

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:
        raise StorageValidationError(f"Failed to probe video file: {exc}")

    if res.returncode != 0:
        err = res.stderr.strip() or "unreadable video format"
        raise StorageValidationError(f"Unreadable or corrupt video file: {err}")

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise StorageValidationError("Could not parse video metadata from ffprobe.")

    return data


def inspect_and_normalize_video(
    raw_video_path: Path,
    output_video_path: Path,
    max_duration_s: float | None = None,
) -> tuple[Path, dict[str, Any]]:
    """
    Validate and normalize video:
    - Check duration against limit (default: settings.MAX_VIDEO_DURATION_S).
    - Check codec, pixel format, dimensions, and rotation tag.
    - If not H.264 + yuv420p or has rotation or long side > 960 px:
      transcode using ffmpeg (H.264 mp4, yuv420p, +faststart, autorotate applied, max long side 960px).
    - If already normalized H.264 mp4, simply copy/move to output_video_path.
    Returns (normalized_path, metadata_dict).
    """
    settings = get_settings()
    max_dur = max_duration_s if max_duration_s is not None else float(settings.MAX_VIDEO_DURATION_S)

    ffmpeg_bin, _ = require_ffmpeg_and_ffprobe()
    probe_data = probe_video(raw_video_path)

    streams = probe_data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise StorageValidationError("No video stream found in uploaded file.")

    # 1. Duration check
    format_info = probe_data.get("format", {})
    dur_str = video_stream.get("duration") or format_info.get("duration")
    duration_s = 0.0
    if dur_str:
        try:
            duration_s = float(dur_str)
        except ValueError:
            duration_s = 0.0

    if duration_s > max_dur:
        raise StorageValidationError(
            f"Video duration ({duration_s:.1f}s) exceeds maximum allowed limit of {max_dur:.0f}s. "
            f"Please upload a shorter walkthrough clip (up to {max_dur:.0f}s)."
        )

    # 2. Inspect properties
    codec_name = str(video_stream.get("codec_name", "")).lower()
    pix_fmt = str(video_stream.get("pix_fmt", "")).lower()
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))

    # Check rotation tag and display matrix side data
    has_rotation = False
    tags = video_stream.get("tags", {})
    if tags:
        rot_val = tags.get("rotate") or tags.get("rotation")
        if rot_val and str(rot_val) not in ("0", "0.0"):
            has_rotation = True

    for side_data in video_stream.get("side_data_list", []):
        if "rotation" in side_data and side_data["rotation"] != 0:
            has_rotation = True

    long_side = max(width, height)
    is_mp4 = raw_video_path.suffix.lower() == ".mp4"

    needs_transcode = (
        codec_name != "h264"
        or pix_fmt != "yuv420p"
        or has_rotation
        or long_side > 960
        or not is_mp4
    )

    metadata = {
        "original_codec": codec_name,
        "original_pix_fmt": pix_fmt,
        "original_width": width,
        "original_height": height,
        "has_rotation": has_rotation,
        "duration_s": duration_s,
        "transcoded": needs_transcode,
    }

    output_video_path.parent.mkdir(parents=True, exist_ok=True)

    if not needs_transcode and raw_video_path.resolve() != output_video_path.resolve():
        # Already compliant H.264 yuv420p mp4 <= 960px without rotation
        shutil.copy2(str(raw_video_path), str(output_video_path))
        return output_video_path, metadata

    # 3. Transcode with ffmpeg
    scale_filter = "scale=w='if(gt(iw,ih),min(960,iw),-2)':h='if(gt(iw,ih),-2,min(960,ih))'"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(raw_video_path),
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_video_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        err = res.stderr.strip() or "ffmpeg transcode failed"
        raise StorageValidationError(f"Failed to normalize video: {err}")

    # Remove raw upload if distinct to save space and keep original out of repository
    if raw_video_path.exists() and raw_video_path.resolve() != output_video_path.resolve():
        try:
            raw_video_path.unlink()
        except OSError:
            pass

    return output_video_path, metadata
