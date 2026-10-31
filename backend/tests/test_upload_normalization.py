"""Unit and integration tests for upload normalization (HEVC, rotated, large resolution)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import init_db
from app.main import app
from app.storage import StorageValidationError, validate_file_extension, ALLOWED_VIDEO_EXTENSIONS
from app.video_norm import (
    inspect_and_normalize_video,
    probe_video,
    require_ffmpeg_and_ffprobe,
)


def create_synthetic_test_clip(
    output_path: Path,
    duration_s: float = 1.0,
    width: int = 320,
    height: int = 240,
    vcodec: str = "libx264",
    pix_fmt: str = "yuv420p",
    rotate_deg: int | None = None,
) -> Path:
    """Generate a tiny synthetic video clip with specified codec, resolution, and rotation."""
    ffmpeg_bin, _ = require_ffmpeg_and_ffprobe()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg_bin, "-y"]
    if rotate_deg is not None:
        cmd.extend(["-display_rotation", str(rotate_deg), "-noautorotate"])

    cmd.extend([
        "-f", "lavfi",
        "-i", f"color=c=blue:s={width}x{height}:d={duration_s}:r=10",
        "-c:v", vcodec,
        "-pix_fmt", pix_fmt,
        str(output_path),
    ])

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"ffmpeg failed to create test clip: {res.stderr}"
    return output_path


def test_allowed_extensions_strictly_mp4_and_mov():
    """Verify only .mp4 and .mov are accepted for video upload."""
    assert ALLOWED_VIDEO_EXTENSIONS == {".mp4", ".mov"}
    assert validate_file_extension("walkthrough.mp4", ALLOWED_VIDEO_EXTENSIONS) == ".mp4"
    assert validate_file_extension("room.mov", ALLOWED_VIDEO_EXTENSIONS) == ".mov"

    with pytest.raises(StorageValidationError, match="Unsupported file format"):
        validate_file_extension("video.avi", ALLOWED_VIDEO_EXTENSIONS)

    with pytest.raises(StorageValidationError, match="Unsupported file format"):
        validate_file_extension("clip.webm", ALLOWED_VIDEO_EXTENSIONS)


def test_fail_loudly_if_ffmpeg_or_ffprobe_missing(monkeypatch):
    """When ffmpeg or ffprobe is not on PATH, require_ffmpeg_and_ffprobe must fail loudly."""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    with pytest.raises(RuntimeError, match="Missing required video tools"):
        require_ffmpeg_and_ffprobe()


def test_normalize_hevc_video_to_h264(tmp_path):
    """Synthetic HEVC (libx265) video is converted to H.264 yuv420p mp4."""
    raw_hevc = tmp_path / "raw_hevc.mp4"
    create_synthetic_test_clip(raw_hevc, vcodec="libx265", pix_fmt="yuv420p")

    # Verify input is indeed hevc
    raw_probe = probe_video(raw_hevc)
    assert raw_probe["streams"][0]["codec_name"].lower() == "hevc"

    out_mp4 = tmp_path / "normalized.mp4"
    final_path, meta = inspect_and_normalize_video(raw_hevc, out_mp4)

    assert final_path.exists()
    assert meta["transcoded"] is True

    # Verify output is H.264
    out_probe = probe_video(out_mp4)
    vstream = out_probe["streams"][0]
    assert vstream["codec_name"].lower() == "h264"
    assert vstream["pix_fmt"].lower() == "yuv420p"


def test_normalize_rotated_video(tmp_path):
    """Video with rotate metadata/side data has autorotate applied."""
    raw_rotated = tmp_path / "rotated.mp4"
    # Create with rotate=90 metadata
    create_synthetic_test_clip(raw_rotated, width=640, height=480, rotate_deg=90)

    raw_probe = probe_video(raw_rotated)
    vstream = raw_probe["streams"][0]
    side_data = vstream.get("side_data_list") or []
    assert any(s.get("rotation") != 0 for s in side_data)

    out_mp4 = tmp_path / "normalized_rotated.mp4"
    final_path, meta = inspect_and_normalize_video(raw_rotated, out_mp4)

    assert final_path.exists()
    assert meta["has_rotation"] is True
    assert meta["transcoded"] is True

    # After ffmpeg autorotate transcode, rotation is baked in and side data cleared
    out_probe = probe_video(out_mp4)
    out_side_data = out_probe["streams"][0].get("side_data_list") or []
    assert not any(s.get("rotation") != 0 for s in out_side_data)


def test_downscale_large_resolution_video(tmp_path):
    """High-res video (e.g. 1920x1080) is downscaled so long side is at most 960 px."""
    raw_1080p = tmp_path / "raw_1080p.mp4"
    create_synthetic_test_clip(raw_1080p, width=1280, height=720)

    out_mp4 = tmp_path / "downscaled.mp4"
    final_path, meta = inspect_and_normalize_video(raw_1080p, out_mp4)

    out_probe = probe_video(out_mp4)
    vstream = out_probe["streams"][0]
    out_w = int(vstream["width"])
    out_h = int(vstream["height"])

    assert max(out_w, out_h) <= 960
    assert out_w == 960
    assert out_h == 540  # 1280x720 aspect ratio preserved: 720 * 960 / 1280 = 540


def test_reject_video_exceeding_duration_limit(tmp_path):
    """Walkthroughs longer than max_duration_s are rejected with clear error."""
    long_clip = tmp_path / "long_clip.mp4"
    create_synthetic_test_clip(long_clip, duration_s=3.0)

    out_mp4 = tmp_path / "out.mp4"
    with pytest.raises(StorageValidationError, match="Video duration .* exceeds maximum allowed limit"):
        inspect_and_normalize_video(long_clip, out_mp4, max_duration_s=2.0)


def test_upload_api_normalizes_mov_file(tmp_path, monkeypatch):
    """Upload endpoint accepts .mov and stores normalized H.264 mp4."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))
    monkeypatch.setenv("PROVIDER_MODE", "mock")

    get_settings.cache_clear()
    init_db()

    mov_path = tmp_path / "upload.mov"
    create_synthetic_test_clip(mov_path, width=480, height=360)

    with TestClient(app) as client:
        with open(mov_path, "rb") as f:
            resp = client.post(
                "/api/audits",
                files={"video": ("upload.mov", f, "video/quicktime")},
                data={"template_id": "campus_fire_exit_core"},
            )

        assert resp.status_code == 201
        audit_id = resp.json()["id"]

        # Stored video must be walkthrough.mp4 (H.264)
        audit_video = data_dir / "audits" / audit_id / "walkthrough.mp4"
        assert audit_video.exists()

        probe = probe_video(audit_video)
        assert probe["streams"][0]["codec_name"].lower() == "h264"
