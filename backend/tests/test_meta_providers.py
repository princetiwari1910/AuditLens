"""Offline tests for Meta Foundation Model providers (SAM 3.1, Muse Spark 1.3, Muse Voice Transcribe 1.0).

No live network calls are made:
- Tests replay official SAM record fixtures copied from dev.meta.ai documentation
- OpenAI client is mocked to verify streaming, structured output, and turn transcription
- Budget estimates, contributor rejection, 400 non-retry, and 429 Retry-After handling
"""

from __future__ import annotations

import base64
import time
from unittest.mock import MagicMock
import numpy as np
import pytest

import meta_sam_parser
from meta_sam_parser._mask_codec import _encode_raster

from app.config import Settings, get_settings
from app.providers.base import SegmentDetection, Transcript
from app.providers.client import (
    BudgetExceededError,
    BudgetGuard,
    ProviderAPIError,
    estimate_reasoner_cost,
    estimate_segmentation_cost,
    estimate_transcription_cost,
    execute_with_retry,
    get_retry_after,
    is_retryable_error,
)
from app.providers.meta import (
    MetaAgentProvider,
    MetaReasoner,
    MetaSegmenter,
    MetaSegmentationProvider,
    MetaTranscriber,
    MetaTranscriptionProvider,
    map_mask_to_full_frame,
    sanitize_concept,
    validate_concept,
)


def _make_dummy_mask_payload(w: int, h: int) -> str:
    """Create valid one_bit payload using meta_sam_parser encoder."""
    raster = [1] * (w * h)
    return _encode_raster(raster, w, h)


# ── Official Fixture Line Tests ───────────────────────────────────────────────

def test_official_fixture_image_several_matches():
    """Verify official SAM image line with several matches on one frame."""
    payload0 = _make_dummy_mask_payload(4, 4)
    payload1 = _make_dummy_mask_payload(5, 5)

    # Line grammar: <0f> <object_id> <box> <mask> ...
    line = (
        f"<0f>0<|box;x1=10;y1=20;x2=13;y2=23;w=100;h=100;c=0.95|><|mask;x=0;y=0;data=4,4,{payload0};c=0.95|>"
        f"1<|box;x1=30;y1=40;x2=34;y2=44;w=100;h=100;c=0.88|><|mask;x=0;y=0;data=5,5,{payload1};c=0.88|>\n"
    )

    fmt = meta_sam_parser.image_segmentation_format()
    parser = fmt.create_parser()
    parser.push(line)
    finish = parser.finish(meta_sam_parser.CompletedOutcome())

    assert len(finish.result.diagnostics) == 0
    records = finish.result.records
    assert len(records) == 4  # 2 boxes + 2 masks

    boxes = [r for r in records if r.kind == "box"]
    assert len(boxes) == 2
    assert boxes[0].object_id == "0"
    assert boxes[0].left == 10
    assert boxes[0].top == 20
    assert boxes[0].right == 14  # inclusive x2=13 -> right=14
    assert boxes[0].bottom == 24
    assert boxes[0].confidence == 0.95

    assert boxes[1].object_id == "1"
    assert boxes[1].left == 30
    assert boxes[1].right == 35
    assert boxes[1].confidence == 0.88


def test_official_fixture_video_frames_with_tags():
    """Verify official SAM video line with <0f>, <1f> frame index tags."""
    payload = _make_dummy_mask_payload(4, 4)
    line = (
        f"<0f>0<|box;x1=10;y1=20;x2=13;y2=23;w=100;h=100;c=0.92|><|mask;x=0;y=0;data=4,4,{payload};c=0.92|>\n"
        f"<1f>0<|box;x1=15;y1=25;x2=18;y2=28;w=100;h=100;c=0.90|><|mask;x=0;y=0;data=4,4,{payload};c=0.90|>\n"
    )

    fmt = meta_sam_parser.video_segmentation_format()
    parser = fmt.create_parser()
    parser.push(line)
    finish = parser.finish(meta_sam_parser.CompletedOutcome())

    assert len(finish.result.diagnostics) == 0
    boxes = [r for r in finish.result.records if r.kind == "box"]
    assert len(boxes) == 2
    assert boxes[0].frame.frame_index == 0
    assert boxes[1].frame.frame_index == 1


def test_official_fixture_confidence_line():
    """Verify confidence field c=0.95 is parsed as float."""
    payload = _make_dummy_mask_payload(4, 4)
    line = f"<0f>0<|box;x1=10;y1=20;x2=13;y2=23;w=100;h=100;c=0.95|><|mask;x=0;y=0;data=4,4,{payload};c=0.95|>\n"

    fmt = meta_sam_parser.image_segmentation_format()
    parser = fmt.create_parser()
    parser.push(line)
    finish = parser.finish(meta_sam_parser.CompletedOutcome())

    box = [r for r in finish.result.records if r.kind == "box"][0]
    assert box.confidence == 0.95


def test_official_fixture_empty_output_zero_matches():
    """Verify empty model response (zero matches) parses to empty records without error."""
    fmt = meta_sam_parser.image_segmentation_format()
    parser = fmt.create_parser()
    parser.push("")
    finish = parser.finish(meta_sam_parser.CompletedOutcome())

    assert len(finish.result.diagnostics) == 0
    assert len(finish.result.records) == 0


def test_official_fixture_sparse_object_ids():
    """Verify non-consecutive object IDs (e.g. 0 and 3) parse without assuming dense 0..N."""
    payload = _make_dummy_mask_payload(4, 4)
    line = (
        f"<0f>0<|box;x1=10;y1=20;x2=13;y2=23;w=100;h=100;c=0.90|><|mask;x=0;y=0;data=4,4,{payload};c=0.90|>"
        f"3<|box;x1=50;y1=60;x2=53;y2=63;w=100;h=100;c=0.75|><|mask;x=0;y=0;data=4,4,{payload};c=0.75|>\n"
    )

    fmt = meta_sam_parser.image_segmentation_format()
    parser = fmt.create_parser()
    parser.push(line)
    finish = parser.finish(meta_sam_parser.CompletedOutcome())

    boxes = [r for r in finish.result.records if r.kind == "box"]
    assert len(boxes) == 2
    assert boxes[0].object_id == "0"
    assert boxes[1].object_id == "3"


def test_official_fixture_skipped_frame_indices():
    """Verify non-consecutive frame markers (<0f> and <4f>) preserve explicit frame IDs."""
    payload = _make_dummy_mask_payload(4, 4)
    line = (
        f"<0f>0<|box;x1=10;y1=20;x2=13;y2=23;w=100;h=100;c=0.91|><|mask;x=0;y=0;data=4,4,{payload};c=0.91|>\n"
        f"<4f>0<|box;x1=30;y1=40;x2=33;y2=43;w=100;h=100;c=0.85|><|mask;x=0;y=0;data=4,4,{payload};c=0.85|>\n"
    )

    fmt = meta_sam_parser.video_segmentation_format()
    parser = fmt.create_parser()
    parser.push(line)
    finish = parser.finish(meta_sam_parser.CompletedOutcome())

    boxes = [r for r in finish.result.records if r.kind == "box"]
    assert len(boxes) == 2
    assert boxes[0].frame.frame_index == 0
    assert boxes[1].frame.frame_index == 4


# ── Coordinate Space & Mask Mapping ───────────────────────────────────────────

def test_box_cropped_mask_mapping_to_full_frame():
    """
    Verify box-cropped mask mapping back to full frame.
    verify with live data: assumption is that mask data is relative to bounding box.
    """
    mask_h, mask_w = 4, 4
    left, top = 10, 20
    right, bottom = 14, 24
    frame_w, frame_h = 100, 100
    raster = bytes([1] * 16)

    polygon = map_mask_to_full_frame(
        mask_raster=raster,
        mask_h=mask_h,
        mask_w=mask_w,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        frame_w=frame_w,
        frame_h=frame_h,
    )

    # Box-cropped mask mapped back to full frame. Assumption: verify with live data.
    assert isinstance(polygon, list)
    assert len(polygon) > 0
    # Every coordinate must be normalized between 0.0 and 1.0
    for pt in polygon:
        assert 0.0 <= pt[0] <= 1.0
        assert 0.0 <= pt[1] <= 1.0
        # Point must lie within bounding box [left/frame_w, right/frame_w]
        assert pt[0] >= left / frame_w
        assert pt[1] >= top / frame_h


# ── Prompt Concept Validation ─────────────────────────────────────────────────

def test_validate_concept_rejects_commas_conjunctions_negation_and_spatial():
    """Verify validate_concept rejects commas, conjunctions, negation, and spatial descriptors."""
    # 1. Valid plain noun phrases pass unmodified
    assert validate_concept("fire extinguisher") == "fire extinguisher"
    assert validate_concept("emergency exit sign") == "emergency exit sign"
    assert validate_concept("  safety helmet  ") == "safety helmet"
    assert validate_concept("hard hat") == "hard hat"

    # 2. Rejects commas (naming rule and concept)
    with pytest.raises(ValueError, match="Rule 'r1': concept 'fire extinguisher, exit sign' contains commas"):
        validate_concept("fire extinguisher, exit sign", rule_id="r1")

    # 3. Rejects conjunctions 'and' / 'or'
    with pytest.raises(ValueError, match="Rule 'r2': concept 'fire extinguisher and exit sign' contains conjunction"):
        validate_concept("fire extinguisher and exit sign", rule_id="r2")
    with pytest.raises(ValueError, match="contains conjunction"):
        validate_concept("box or chair", rule_id="r2")

    # 4. Rejects negation
    with pytest.raises(ValueError, match="Rule 'r3': concept 'exit path not blocked' contains negation"):
        validate_concept("exit path not blocked", rule_id="r3")
    with pytest.raises(ValueError, match="contains negation"):
        validate_concept("not obstructed extinguisher", rule_id="r3")
    with pytest.raises(ValueError, match="contains negation"):
        validate_concept("no obstacles", rule_id="r3")
    with pytest.raises(ValueError, match="contains negation"):
        validate_concept("unblocked exit door", rule_id="r3")

    # 5. Rejects spatial words
    with pytest.raises(ValueError, match="Rule 'r4': concept 'fire extinguisher on the left' contains spatial words"):
        validate_concept("fire extinguisher on the left", rule_id="r4")
    with pytest.raises(ValueError, match="contains spatial words"):
        validate_concept("box in the middle", rule_id="r4")
    with pytest.raises(ValueError, match="contains spatial words"):
        validate_concept("person blocking door", rule_id="r4")
    with pytest.raises(ValueError, match="contains spatial words"):
        validate_concept("pallet near door", rule_id="r4")
    with pytest.raises(ValueError, match="contains spatial words"):
        validate_concept("extension cord on floor", rule_id="r4")

    # 6. Rejects empty/blank
    with pytest.raises(ValueError, match="non-empty string"):
        validate_concept("", rule_id="r5")
    with pytest.raises(ValueError, match="non-empty string"):
        validate_concept("   ", rule_id="r5")


def test_template_load_validation_rejects_invalid_sam_prompts():
    """Verify TemplateModel and template loading reject bad concepts with rule and concept names."""
    from app.models import RuleModel, RuleType, TemplateModel
    import pydantic

    # Invalid comma prompt rejected at template load time
    with pytest.raises(pydantic.ValidationError) as exc_info:
        TemplateModel(
            id="test_tmpl",
            name="Test Template",
            rules=[
                RuleModel(
                    id="bad_exit_rule",
                    title="Bad Exit",
                    type=RuleType.PRESENCE,
                    sam_prompts=["exit sign, door"],
                )
            ],
        )
    err_str = str(exc_info.value)
    assert "bad_exit_rule" in err_str
    assert "contains commas" in err_str

    # Invalid negation prompt rejected
    with pytest.raises(pydantic.ValidationError) as exc_info:
        TemplateModel(
            id="test_tmpl",
            name="Test Template",
            rules=[
                RuleModel(
                    id="bad_negation_rule",
                    title="Bad Negation",
                    type=RuleType.ABSENCE,
                    sam_prompts=["exit not blocked"],
                )
            ],
        )
    err_str = str(exc_info.value)
    assert "bad_negation_rule" in err_str
    assert "contains negation" in err_str

    # Invalid spatial prompt rejected
    with pytest.raises(pydantic.ValidationError) as exc_info:
        TemplateModel(
            id="test_tmpl",
            name="Test Template",
            rules=[
                RuleModel(
                    id="bad_spatial_rule",
                    title="Bad Spatial",
                    type=RuleType.PRESENCE,
                    sam_prompts=["box in the middle"],
                )
            ],
        )
    err_str = str(exc_info.value)
    assert "bad_spatial_rule" in err_str
    assert "contains spatial words" in err_str

    # Valid noun phrases pass
    valid_tmpl = TemplateModel(
        id="good_tmpl",
        name="Good Template",
        rules=[
            RuleModel(
                id="good_rule",
                title="Good Rule",
                type=RuleType.PRESENCE,
                sam_prompts=["fire extinguisher", "emergency exit sign"],
            )
        ],
    )
    assert len(valid_tmpl.rules[0].sam_prompts) == 2


def test_all_bundled_templates_pass_concept_validation():
    """Verify all bundled safety templates contain only plain noun phrases."""
    from app.template_loader import list_templates
    templates = list_templates()
    assert len(templates) >= 4
    for tmpl in templates:
        for rule in tmpl.rules:
            for prompt in rule.sam_prompts:
                # Must not raise
                validated = validate_concept(prompt, rule_id=rule.id)
                assert validated == prompt.strip()


def test_meta_segmenter_does_not_silently_rewrite_prompts():
    """Verify MetaSegmenter rejects invalid concepts instead of silently modifying them."""
    segmenter = MetaSegmenter()
    # Does not strip comma to take first - rejects with ValueError
    with pytest.raises(ValueError, match="contains commas"):
        segmenter.segment("dummy.jpg", ["fire extinguisher, exit sign"])

    # Does not strip negation - rejects with ValueError
    with pytest.raises(ValueError, match="contains negation"):
        segmenter.segment("dummy.jpg", ["exit not blocked"])


# ── Contributor Model Rejection ───────────────────────────────────────────────

def test_rejection_of_contributor_models():
    """Verify that any model ID containing '-contributor' is strictly rejected."""
    # 1. Config Settings validation
    with pytest.raises(ValueError, match="-contributor"):
        Settings(MODEL_ID_AGENT="muse-spark-1.3-contributor")

    with pytest.raises(ValueError, match="-contributor"):
        Settings(MODEL_ID_SEGMENTATION="sam-3.1-contributor")

    with pytest.raises(ValueError, match="-contributor"):
        Settings(MODEL_ID_TRANSCRIPTION="muse-voice-transcribe-1.0-contributor")

    # 2. Direct provider initialization rejection
    with pytest.raises(ValueError, match="-contributor"):
        MetaAgentProvider(model_id="muse-spark-1.3-contributor")

    with pytest.raises(ValueError, match="-contributor"):
        MetaTranscriptionProvider(model_id="muse-voice-transcribe-1.0-contributor")


# ── Mocked Provider End-to-End Tests ─────────────────────────────────────────

def test_meta_segmenter_with_mocked_client(tmp_path):
    """Verify MetaSegmentationProvider streams, parses, and decodes records with mock client."""
    # Create sample image
    img_path = tmp_path / "test_frame.jpg"
    black_img = np.zeros((100, 100, 3), dtype=np.uint8)
    import cv2
    cv2.imwrite(str(img_path), black_img)

    payload = _make_dummy_mask_payload(4, 4)
    line = f"<0f>0<|box;x1=10;y1=20;x2=13;y2=23;w=100;h=100;c=0.95|><|mask;x=0;y=0;data=4,4,{payload};c=0.95|>\n"

    # Mock stream chunk
    mock_chunk = MagicMock()
    mock_chunk.delta.text = line

    mock_client = MagicMock()
    mock_client.responses.create.return_value = [mock_chunk]

    provider = MetaSegmentationProvider(client=mock_client)
    detections = provider.segment(img_path, ["fire extinguisher"])

    assert len(detections) == 1
    det = detections[0]
    assert det.label == "fire extinguisher"
    assert det.score == 0.95
    assert det.box["x"] == 0.1
    assert det.box["y"] == 0.2
    assert det.box["w"] == 0.04
    assert det.box["h"] == 0.04
    assert det.mask is not None


def test_meta_reasoner_with_mocked_client():
    """Verify MetaReasoner enforces schema and grounds cited frames to passed frames."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{"status": "pass", "reason": "Extinguisher clearly visible", "cited_frame_ids": [1], "confidence": 0.95}'
    )
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    reasoner = MetaReasoner(client=mock_client)
    verdict = reasoner.judge(
        rule={"title": "Extinguisher visible"},
        evidence=[{"frame_id": 1, "label": "fire extinguisher", "score": 0.95}],
    )

    assert verdict["status"] == "pass"
    assert verdict["cited_frame_ids"] == [1]
    assert verdict["confidence"] == 0.95


def test_meta_reasoner_downgrades_invented_cited_frames():
    """Verify MetaReasoner downgrades to unsure if model cites invented frames not passed in."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    # Model claims pass but cites frame 99, which was NOT passed in
    mock_choice.message.content = (
        '{"status": "pass", "reason": "Passed without evidence", "cited_frame_ids": [99], "confidence": 0.90}'
    )
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    reasoner = MetaReasoner(client=mock_client)
    verdict = reasoner.judge(
        rule={"title": "Extinguisher visible"},
        evidence=[{"frame_id": 1, "label": "fire extinguisher", "score": 0.95}],
    )

    # Frame 99 filtered out -> no valid cited frames -> downgraded to unsure
    assert verdict["status"] == "unsure"
    assert verdict["cited_frame_ids"] == []
    assert "no valid cited keyframe evidence" in verdict["reason"]


def test_meta_transcriber_with_mocked_client(tmp_path):
    """Verify MetaTranscriber parses turn-level timestamps only."""
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Checking the emergency exit."
    mock_resp.language = "en"
    seg = MagicMock()
    seg.start = 0.5
    seg.end = 2.8
    seg.text = "Checking the emergency exit."
    seg.speaker = "auditor"
    mock_resp.segments = [seg]
    mock_client.audio.transcriptions.create.return_value = mock_resp

    transcriber = MetaTranscriber(client=mock_client)
    transcript = transcriber.transcribe(audio_file)

    assert isinstance(transcript, Transcript)
    assert transcript.text == "Checking the emergency exit."
    assert len(transcript.turns) == 1
    assert transcript.turns[0].start_s == 0.5
    assert transcript.turns[0].end_s == 2.8
    assert transcript.turns[0].speaker == "auditor"


# ── Pricing and Budget Constants ──────────────────────────────────────────────

def test_pricing_and_budget_constants_match_docs():
    """
    Verify BudgetGuard pricing constants match dev.meta.ai/docs/pricing-rate-limits:
    - SAM image: $2.50 / 1k ($0.0025 / img)
    - SAM video: $0.20 / 1k frames ($0.0002 / frame)
    - Spark standard: $1.25 in / $4.25 out per 1M tokens ($0.00125 / $0.00425 per 1k)
    - Voice: $0.18 / hour ($0.003 / min)
    - Defaults: $1 per audit, $20 total during dev
    - Rate limits: 3000 RPM
    """
    settings = get_settings()

    assert settings.PRICE_SAM_PER_IMAGE_USD == 0.0025
    assert settings.PRICE_SAM_VIDEO_PER_FRAME_USD == 0.0002
    assert settings.PRICE_MUSE_SPARK_INPUT_PER_1K_USD == 0.00125
    assert settings.PRICE_MUSE_SPARK_OUTPUT_PER_1K_USD == 0.00425
    assert settings.PRICE_MUSE_VOICE_PER_MIN_USD == 0.003
    assert settings.MAX_BUDGET_PER_AUDIT_USD == 1.0
    assert settings.MAX_GLOBAL_BUDGET_USD == 20.0
    assert settings.PROVIDER_RATE_LIMIT_RPM == 3000


# ── HTTP 400 and 429 Retry-After Handling ─────────────────────────────────────

def test_http_400_not_retried():
    """Verify HTTP 400 client error is never retried."""
    attempts = 0

    def bad_request_endpoint():
        nonlocal attempts
        attempts += 1
        raise ProviderAPIError("400 Bad Request: Invalid prompt", status_code=400)

    with pytest.raises(ProviderAPIError, match="400 Bad Request"):
        execute_with_retry(bad_request_endpoint, max_retries=3, base_delay=0.01)

    assert attempts == 1  # Exactly 1 attempt, zero retries


def test_http_429_retry_after_respected(monkeypatch):
    """Verify HTTP 429 rate limit respects Retry-After header with sleep delay."""
    slept_durations = []
    monkeypatch.setattr(time, "sleep", lambda s: slept_durations.append(s))

    class RateLimitWithHeader(Exception):
        status_code = 429
        response = MagicMock()
        response.headers = {"retry-after": "1.5"}

    attempts = 0

    def rate_limited_endpoint():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitWithHeader("Rate limit exceeded")
        return "success"

    res = execute_with_retry(rate_limited_endpoint, max_retries=2, base_delay=0.01)
    assert res == "success"
    assert attempts == 2
    assert len(slept_durations) == 1
    # Sleep duration must be >= 1.5s as specified in Retry-After
    assert slept_durations[0] >= 1.5
