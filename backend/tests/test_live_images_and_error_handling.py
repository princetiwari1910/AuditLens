"""Tests for Task 2: Live photos/images input, findings table output, and redacted error resilience."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from sqlmodel import Session, select

from app.agent.runner import redact_error
from app.db import engine, init_db
from app.models import Audit, Finding, FindingStatus
from scripts.run_audit_cli import run_cli_audit


def test_redact_error_comprehensive():
    """Verify that redact_error sanitizes API keys, bearer tokens, base64 images, and headers."""
    # 1. Bearer token
    err1 = "401 Unauthorized: Bearer sk-meta-live-abcdef1234567890"
    redacted1 = redact_error(err1)
    assert "sk-meta-live" not in redacted1
    assert "Bearer [REDACTED]" in redacted1

    # 2. Key param
    err2 = "Exception calling endpoint with api_key='secret-key-12345'"
    redacted2 = redact_error(err2)
    assert "secret-key-12345" not in redacted2
    assert "api_key=[REDACTED]" in redacted2

    # 3. Base64 data URL
    err3 = "400 Bad Request on payload: {'image_url': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA='}"
    redacted3 = redact_error(err3)
    assert "/9j/4AAQSkZJRgAB" not in redacted3
    assert "[base64 redacted]" in redacted3

    # 4. Request headers dictionary
    err4 = "Error with headers: {'Authorization': 'Bearer 12345', 'Host': 'api.meta.ai'}"
    redacted4 = redact_error(err4)
    assert "12345" not in redacted4
    assert "[REDACTED]" in redacted4


def test_run_cli_audit_with_images(tmp_path):
    """Verify run_cli_audit handles photo inputs as keyframes without transcoding."""
    img1 = tmp_path / "photo1.jpg"
    img2 = tmp_path / "photo2.jpg"

    mat1 = np.zeros((100, 100, 3), dtype=np.uint8)
    mat2 = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.imwrite(str(img1), mat1)
    cv2.imwrite(str(img2), mat2)

    captured_out = io.StringIO()
    with patch("sys.stdout", captured_out):
        run_cli_audit(images=f"{img1},{img2}", template_id="fire_exit_safety")

    output = captured_out.getvalue()
    # Must report photos input and keyframe sampling
    assert "Photos" in output or "keyframes" in output
    assert "EVIDENCE FRAME" in output
    assert "RULE" in output
    assert "CONFIDENCE" in output
    assert "LATENCY" in output
