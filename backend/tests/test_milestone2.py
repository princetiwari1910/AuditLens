"""Tests for Milestone 2: models, templates, storage, frame sampling, sample video."""

import os
from pathlib import Path
import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, init_db, reset_engine
from app.frames import VideoProcessingError, sample_frames_from_video, sample_frames_from_images
from app.models import Audit, Frame, RuleType, TemplateModel
from app.storage import (
    StorageValidationError,
    get_audit_dir,
    get_frames_dir,
    get_overlays_dir,
    validate_file_extension,
    validate_file_size,
)
from app.template_loader import get_template, list_templates
from scripts.make_sample_video import generate_sample_video


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Point DATA_DIR to a temporary directory for isolation."""
    monkeypatch.setattr(get_settings(), "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def test_templates_load_and_validate():
    """Verify both templates load and pass strict Pydantic validation."""
    templates = list_templates()
    assert len(templates) >= 2

    tmpl_ids = {t.id for t in templates}
    assert "fire_exit_safety" in tmpl_ids
    assert "workshop_ppe" in tmpl_ids

    fire = get_template("fire_exit_safety")
    assert fire is not None
    assert len(fire.rules) == 5
    assert "assistive pre-audit tool" in fire.disclaimer

    ppe = get_template("workshop_ppe")
    assert ppe is not None
    assert len(ppe.rules) == 5

    # Check all 5 rule types are represented across templates
    all_rule_types = {r.type for t in templates for r in t.rules}
    assert RuleType.PRESENCE in all_rule_types
    assert RuleType.ABSENCE in all_rule_types
    assert RuleType.COUNT in all_rule_types
    assert RuleType.MEASUREMENT in all_rule_types
    assert RuleType.COLOCATION in all_rule_types


def test_storage_validation():
    """Test file extension and size validation."""
    # Valid extensions
    assert validate_file_extension("video.mp4", {".mp4", ".mov"}) == ".mp4"
    assert validate_file_extension("PHOTO.JPEG", {".jpg", ".jpeg"}) == ".jpeg"

    # Invalid extension
    with pytest.raises(StorageValidationError, match="Unsupported file format"):
        validate_file_extension("script.sh", {".mp4", ".mov"})

    # Valid size
    validate_file_size(10 * 1024 * 1024, max_bytes=20 * 1024 * 1024)

    # Exceeded size
    with pytest.raises(StorageValidationError, match="exceeds maximum allowed limit"):
        validate_file_size(25 * 1024 * 1024, max_bytes=20 * 1024 * 1024)


def test_sample_video_and_frame_sampling(tmp_path):
    """Test generating a synthetic video and sampling frames at 1 fps."""
    video_path = tmp_path / "test_synth.mp4"
    # Generate a short 5-second video for fast testing
    generate_sample_video(video_path, duration_s=5, fps=25)
    assert video_path.exists()
    assert video_path.stat().st_size > 0

    eng = engine()
    audit_id = "test_audit_001"

    with Session(eng) as session:
        audit = Audit(id=audit_id, template_id="fire_exit_safety")
        session.add(audit)
        session.commit()

        frames = sample_frames_from_video(video_path, audit_id=audit_id, fps=1.0, session=session)

        # 5 seconds at 1 fps should yield 5 or 6 frames
        assert len(frames) in (5, 6)
        for idx, f in enumerate(frames):
            assert f.audit_id == audit_id
            assert f.idx == idx
            assert Path(f.path).exists()
            assert len(f.sha256) == 64  # valid SHA-256 hex string

        # Query frames from DB
        db_frames = session.exec(select(Frame).where(Frame.audit_id == audit_id)).all()
        assert len(db_frames) == len(frames)


def test_unreadable_video_error(tmp_path):
    """Verify clear error is raised for corrupt or missing video."""
    with pytest.raises(VideoProcessingError, match="Video file does not exist"):
        sample_frames_from_video(tmp_path / "missing.mp4", audit_id="fail_audit")

    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"not a valid video content")
    with pytest.raises(VideoProcessingError, match="Cannot open video file"):
        sample_frames_from_video(corrupt_file, audit_id="fail_audit")
