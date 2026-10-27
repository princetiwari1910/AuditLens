"""Storage layout and file upload validation for AuditLens."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from app.config import get_settings

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm"}

ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_VIDEO_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS


class StorageValidationError(ValueError):
    """Raised when an upload fails validation (size, type, etc.)."""
    pass


def get_audit_dir(audit_id: str) -> Path:
    """Return and create the base directory for an audit."""
    settings = get_settings()
    d = settings.DATA_DIR / "audits" / audit_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_audit_video_path(audit_id: str) -> Path | None:
    """Return the path to the stored walkthrough video for an audit if it exists."""
    audit_dir = get_audit_dir(audit_id)
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        candidate = audit_dir / f"walkthrough{ext}"
        if candidate.exists():
            return candidate
    return None


def get_frames_dir(audit_id: str) -> Path:
    """Return and create the frames directory for an audit."""
    d = get_audit_dir(audit_id) / "frames"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_overlays_dir(audit_id: str) -> Path:
    """Return and create the overlays directory for an audit."""
    d = get_audit_dir(audit_id) / "overlays"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_audio_dir(audit_id: str) -> Path:
    """Return and create the voice notes directory for an audit."""
    d = get_audit_dir(audit_id) / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def validate_file_extension(filename: str, allowed_extensions: set[str]) -> str:
    """Validate extension and return normalized lowercase suffix."""
    suffix = Path(filename).suffix.lower()
    if not suffix or suffix not in allowed_extensions:
        allowed_str = ", ".join(sorted(allowed_extensions))
        raise StorageValidationError(
            f"Unsupported file format '{suffix}'. Allowed formats: {allowed_str}"
        )
    return suffix


def validate_file_size(size_bytes: int, max_bytes: int | None = None) -> None:
    """Validate file size against max_upload_bytes."""
    settings = get_settings()
    limit = max_bytes if max_bytes is not None else settings.max_upload_bytes
    if size_bytes > limit:
        max_mb = limit / (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        raise StorageValidationError(
            f"File size ({actual_mb:.1f} MB) exceeds maximum allowed limit of {max_mb:.0f} MB"
        )


async def save_upload_file(
    file: UploadFile,
    dest_path: Path,
    allowed_extensions: set[str] | None = None,
    max_bytes: int | None = None,
) -> int:
    """
    Stream and save an UploadFile to dest_path while validating type and size.
    Returns the total bytes written.
    """
    if allowed_extensions is not None:
        filename = file.filename or "upload"
        validate_file_extension(filename, allowed_extensions)

    settings = get_settings()
    limit = max_bytes if max_bytes is not None else settings.max_upload_bytes

    total_bytes = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(dest_path, "wb") as out_f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > limit:
                # Clean up partially written file
                out_f.close()
                if dest_path.exists():
                    dest_path.unlink()
                max_mb = limit / (1024 * 1024)
                raise StorageValidationError(
                    f"Upload exceeds maximum allowed limit of {max_mb:.0f} MB"
                )
            out_f.write(chunk)

    if total_bytes == 0:
        if dest_path.exists():
            dest_path.unlink()
        raise StorageValidationError("Uploaded file is empty (0 bytes)")

    return total_bytes
