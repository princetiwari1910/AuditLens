"""Offline tests for SAM request shape, Spark vision smoke step, and live audit error resilience.

Verifies:
1. MetaSegmenter request shape matches dev.meta.ai Responses API spec byte-for-byte.
2. Spark vision presence smoke step execution.
3. Live audit runner resilience: provider error does not crash the run, logs redacted error to trace,
   and downgrades rule to unsure.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

import pytest
from sqlmodel import Session, select

from app.agent.runner import AgentRunner, redact_error
from app.db import engine, init_db
from app.models import Audit, AuditSpan, Finding, FindingStatus, RuleModel
from app.providers.meta import (
    MetaSegmenter,
    build_sam_request_input,
    redact_sam_input_shape,
)
from scripts.smoke_meta import StepResult, run_spark_vision_step


# ── 1. SAM Request Shape ───────────────────────────────────────────────────────


def test_build_sam_request_input_shape_byte_for_byte():
    """Verify input[0] has type message, role user, and exactly 2 content parts."""
    concept = "fire extinguisher"
    data_url = "data:image/jpeg;base64,ZmFrZWltYWdlZGF0YQ=="

    req_input = build_sam_request_input(concept, data_url)

    assert isinstance(req_input, list)
    assert len(req_input) == 1

    msg = req_input[0]
    assert set(msg.keys()) == {"type", "role", "content"}, "Must have ONLY type, role, content keys"
    assert msg["type"] == "message"
    assert msg["role"] == "user"

    content = msg["content"]
    assert isinstance(content, list)
    assert len(content) == 2, "Must contain exactly two content items"

    # Part 1: input_text
    part1 = content[0]
    assert set(part1.keys()) == {"type", "text"}
    assert part1["type"] == "input_text"
    assert part1["text"] == concept

    # Part 2: input_image
    part2 = content[1]
    assert set(part2.keys()) == {"type", "image_url"}
    assert part2["type"] == "input_image"
    assert part2["image_url"] == data_url


def test_redact_sam_input_shape():
    """Verify redact_sam_input_shape redacts large base64 data but preserves structure."""
    long_data_url = "data:image/jpeg;base64," + ("A" * 200)
    req_input = build_sam_request_input("exit sign", long_data_url)

    redacted = redact_sam_input_shape(req_input)
    assert len(redacted) == 1
    redacted_url = redacted[0]["content"][1]["image_url"]
    assert "redacted" in redacted_url
    assert len(redacted_url) < len(long_data_url)
    assert redacted[0]["content"][0]["text"] == "exit sign"


def test_meta_segmenter_sends_exact_request_shape(tmp_path):
    """Verify MetaSegmenter calls client.responses.create with the byte-for-byte exact shape."""
    img_file = tmp_path / "frame.jpg"
    import cv2
    import numpy as np

    cv2.imwrite(str(img_file), np.zeros((50, 50, 3), dtype=np.uint8))

    mock_client = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.delta.text = ""
    mock_client.responses.create.return_value = [mock_chunk]

    segmenter = MetaSegmenter(client=mock_client)
    segmenter.segment(img_file, ["fire extinguisher"])

    mock_client.responses.create.assert_called_once()
    kwargs = mock_client.responses.create.call_args.kwargs
    assert kwargs["model"] == "sam-3.1"
    assert kwargs["stream"] is True
    assert kwargs["metadata"] == {"mask_encoding": "one_bit", "include_confidence": "true"}

    call_input = kwargs["input"]
    assert len(call_input) == 1
    assert call_input[0]["type"] == "message"
    assert call_input[0]["role"] == "user"
    assert len(call_input[0]["content"]) == 2
    assert call_input[0]["content"][0] == {"type": "input_text", "text": "fire extinguisher"}
    assert call_input[0]["content"][1]["type"] == "input_image"
    assert call_input[0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


# ── 2. Spark Vision Smoke Step ─────────────────────────────────────────────────


def test_spark_vision_smoke_step(tmp_path):
    """Verify run_spark_vision_step runs presence verification using verify_presence."""
    img_file = tmp_path / "smoke_frame.jpg"
    img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)  # dummy jpeg header

    with patch("app.providers.meta.MetaAgentProvider") as mock_provider_cls:
        mock_instance = MagicMock()
        mock_instance.verify_presence.return_value = {
            "present": True,
            "cited_frame_ids": [0],
            "rationale": "Fire extinguisher mounted on wall.",
        }
        mock_provider_cls.return_value = mock_instance

        res = run_spark_vision_step(
            image_path=img_file,
            concept="fire extinguisher",
            fixtures_dir=tmp_path / "fixtures",
            record=False,
        )

        assert res.name == "Spark vision"
        assert res.status == "PASS"
        assert res.latency_ms >= 0
        assert res.cost_usd > 0
        assert any("present=True" in d for d in res.details)


def test_spark_vision_smoke_step_handles_failure(tmp_path):
    """Verify run_spark_vision_step captures errors without raising."""
    img_file = tmp_path / "smoke_frame.jpg"
    img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)

    with patch("app.providers.meta.MetaAgentProvider") as mock_provider_cls:
        mock_instance = MagicMock()
        mock_instance.verify_presence.side_effect = RuntimeError("400 Bad Request: simulated")
        mock_provider_cls.return_value = mock_instance

        res = run_spark_vision_step(
            image_path=img_file,
            concept="fire extinguisher",
            fixtures_dir=tmp_path / "fixtures",
            record=False,
        )

        assert res.name == "Spark vision"
        assert res.status == "FAIL"
        assert "400 Bad Request" in res.error


# ── 3. Live Audit Error Resilience & Redaction ─────────────────────────────────


def test_redact_error_strips_tokens_and_keys():
    """Verify redact_error strips secrets, bearer tokens and api keys from messages."""
    msg = "HTTP 401: Invalid token Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz and MODEL_API_KEY=meta_live_secret_key_12345"
    redacted = redact_error(msg)
    assert "Bearer [REDACTED]" in redacted
    assert "meta_live_secret_key_12345" not in redacted
    assert "eyJhbGci" not in redacted


def test_live_provider_error_does_not_crash_audit(tmp_path):
    """Verify that a provider error during rule evaluation does not crash run_audit,
    logs the redacted error to trace, and downgrades the finding to unsure."""
    init_db()
    eng = engine()

    test_audit_id = f"live_err_{uuid.uuid4().hex[:8]}"

    with Session(eng) as session:
        audit = Audit(
            id=test_audit_id,
            template_id="fire_exit_safety",
            status="queued",
            video_path=str(tmp_path / "dummy.mp4"),
        )
        session.add(audit)
        session.commit()

    # Rule 1 will fail with an error; Rule 2 will succeed
    rule1 = RuleModel(
        id="failing_rule",
        type="presence",
        title="Failing Rule",
        sam_prompts=["broken concept"],
    )
    rule2 = RuleModel(
        id="passing_rule",
        type="presence",
        title="Passing Rule",
        sam_prompts=["valid concept"],
    )

    # Mock segmenter: throws on first concept, succeeds on second
    mock_segmenter = MagicMock()

    def find_objects_side_effect(frame_paths, prompt, timestamps_s=None):
        if "broken concept" in prompt:
            raise RuntimeError("Live Meta API error with Bearer sk-meta-secret-1234567890abcdef")
        from app.providers.base import Detection
        return [
            Detection(
                frame_id=0,
                timestamp_s=0.0,
                prompt=prompt,
                score=0.92,
                bbox={"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3},
                polygon=[[0.2, 0.2], [0.5, 0.2], [0.5, 0.5], [0.2, 0.5]],
            )
        ]

    mock_segmenter.find_objects.side_effect = find_objects_side_effect
    mock_segmenter.segment.side_effect = lambda img, prompts: []

    mock_transcriber = MagicMock()
    mock_reasoner = MagicMock()

    runner = AgentRunner(
        segmentation_provider=mock_segmenter,
        transcription_provider=mock_transcriber,
        reasoner=mock_reasoner,
    )

    events: list[dict] = []
    with Session(eng) as session:
        findings = runner.run_audit(
            audit_id=test_audit_id,
            rules=[rule1, rule2],
            frames=[{"idx": 0, "path": str(tmp_path / "f0.jpg"), "timestamp_s": 0.0}],
            emit=lambda e: events.append(e),
            session=session,
        )

        # Audit completed, did NOT crash
        assert len(findings) == 2

        # Check finding 1 downgraded to unsure
        f1 = next(f for f in findings if f["rule_id"] == "failing_rule")
        assert f1["status"] == FindingStatus.UNSURE.value
        assert "Provider error fallback" in f1["rationale"]
        assert "sk-meta-secret" not in f1["rationale"], "Secret must be redacted!"
        assert "[REDACTED]" in f1["rationale"]

        # Check trace span was logged for provider_error
        spans = session.exec(
            select(AuditSpan).where(
                AuditSpan.audit_id == test_audit_id,
                AuditSpan.stage == "provider_error",
            )
        ).all()
        assert len(spans) == 1
        assert "sk-meta-secret" not in spans[0].step_reason
        assert "[REDACTED]" in spans[0].step_reason

        # Finding 2 succeeded normally
        f2 = next(f for f in findings if f["rule_id"] == "passing_rule")
        assert f2["status"] == FindingStatus.PASS.value
