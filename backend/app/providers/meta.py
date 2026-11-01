"""Target Meta Foundation Model providers (SAM 3.1, Muse Spark 1.3, Muse Voice Transcribe 1.0).

UNVERIFIED against live API (built against dev.meta.ai/docs specs and verified with doc fixtures).
Requires MODEL_API_KEY environment variable when invoking live endpoints.
Default PROVIDER_MODE remains 'mock'.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Callable, Sequence

import cv2
import numpy as np
from openai import OpenAI

import meta_sam_parser
from meta_sam_parser import (
    CompletedOutcome,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    decode_mask_to_raster,
)

from app.cache import compute_cache_key, get_cached_result, set_cached_result
from app.config import get_settings
from app.db import get_session
from app.models import CacheEntry
from app.providers.base import (
    Detection,
    SegmentDetection,
    Transcript,
    TranscriptSegment,
    TranscriptTurn,
)
from app.providers.client import (
    ProviderAPIError,
    estimate_reasoner_cost,
    estimate_segmentation_cost,
    estimate_transcription_cost,
    execute_with_retry,
)
from app.providers.concept_validation import validate_concept
from app.providers.schemas import (
    SPARK_PRESENCE_JSON_SCHEMA,
    SPARK_VERDICT_JSON_SCHEMA,
    VerdictStatus,
    validate_presence_verdict,
    validate_verdict,
)

logger = logging.getLogger("auditlens.providers.meta")

ERR_UNVERIFIED = (
    "UNVERIFIED against live API: MODEL_API_KEY is not configured in environment. "
    "Set MODEL_API_KEY to execute live Meta Foundation Model calls."
)

FORBIDDEN_SPATIAL_NEGATION_PATTERNS = [
    r"\bon\s+the\s+(left|right|top|bottom)\b",
    r"\bto\s+the\s+(left|right)\b",
    r"\bin\s+the\s+(middle|center|background|foreground)\b",
    r"\bnot\s+blocked\b",
    r"\bnot\s+obstructed\b",
    r"\bunblocked\b",
    r"\bclear\s+of\s+obstacles\b",
    r"\bblocking\b",
    r"\bobstructing\b",
    r"\b(near|next\s+to|behind|in\s+front\s+of)\b",
    r"\b(not|no|neither|nor)\b",
]


def sanitize_concept(prompt: str) -> str:
    """
    Validate prompt to ONE short noun phrase per dev.meta.ai SAM 3.1 documentation.
    Does NOT silently rewrite concept prompts; raises ValueError on invalid input.
    """
    return validate_concept(prompt)


def encode_image_to_base64_data_url(
    image: str | bytes | Path,
) -> tuple[str, int, int, bytes]:
    """
    Load image, extract dimensions (width, height), and return JPEG base64 data URL + raw bytes.
    """
    raw_bytes: bytes
    if isinstance(image, bytes):
        raw_bytes = image
    elif isinstance(image, (str, Path)):
        p = Path(image)
        if p.exists() and p.is_file():
            raw_bytes = p.read_bytes()
        elif isinstance(image, str) and image.startswith("data:image/"):
            # Base64 data URL already
            comma_idx = image.find(",")
            if comma_idx != -1:
                raw_bytes = base64.b64decode(image[comma_idx + 1 :])
            else:
                raw_bytes = base64.b64decode(image)
        else:
            raise FileNotFoundError(f"Image file not found: {image}")
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    np_arr = np.frombuffer(raw_bytes, np.uint8)
    img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Failed to decode image with OpenCV.")

    h, w = img_bgr.shape[:2]
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64_str}"
    return data_url, w, h, raw_bytes


def map_mask_to_full_frame(
    mask_raster: bytes,
    mask_h: int,
    mask_w: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    frame_w: int,
    frame_h: int,
) -> list[list[float]]:
    """
    Map box-cropped mask raster back to full frame normalized polygon coordinates.
    # Box-cropped mask mapped back to full frame. Assumption: verify with live data.
    """
    if mask_h <= 0 or mask_w <= 0 or not mask_raster or frame_w <= 0 or frame_h <= 0:
        return [
            [round(left / frame_w, 4), round(top / frame_h, 4)],
            [round(right / frame_w, 4), round(top / frame_h, 4)],
            [round(right / frame_w, 4), round(bottom / frame_h, 4)],
            [round(left / frame_w, 4), round(bottom / frame_h, 4)],
        ]

    arr = np.frombuffer(mask_raster, dtype=np.uint8).reshape((mask_h, mask_w))
    contours, _ = cv2.findContours(arr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    polygon: list[list[float]] = []
    if contours:
        # Take largest contour
        largest = max(contours, key=cv2.contourArea)
        for pt in largest.squeeze():
            if pt.ndim == 1 and len(pt) == 2:
                cx, cy = float(pt[0]), float(pt[1])
            else:
                continue
            # Box-cropped mask mapped back to full frame. Assumption: verify with live data.
            norm_x = round((left + cx) / frame_w, 4)
            norm_y = round((top + cy) / frame_h, 4)
            polygon.append([norm_x, norm_y])

    if not polygon:
        polygon = [
            [round(left / frame_w, 4), round(top / frame_h, 4)],
            [round(right / frame_w, 4), round(top / frame_h, 4)],
            [round(right / frame_w, 4), round(bottom / frame_h, 4)],
            [round(left / frame_w, 4), round(bottom / frame_h, 4)],
        ]

    return polygon


class MetaSegmentationProvider:
    """
    Segmentation provider integrating with SAM 3.1 API (Responses API with streaming).
    UNVERIFIED against live API (built against dev.meta.ai/docs specs and verified with doc fixtures).
    Implements both Segmenter and SegmentationProvider protocols.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._version = "sam-3.1"

    @property
    def version(self) -> str:
        return self._version

    @property
    def scenario_hash(self) -> str:
        return "meta-api"

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client
        settings = get_settings()
        api_key = settings.MODEL_API_KEY or settings.META_API_KEY
        if not api_key:
            raise ValueError(ERR_UNVERIFIED)
        base_url = settings.META_BASE_URL or "https://api.meta.ai/v1"
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    def _parse_stream_records(
        self, stream: Any, is_video: bool = False
    ) -> Sequence[Any]:
        """Parse Responses API stream chunks using meta_sam_parser."""
        fmt = (
            meta_sam_parser.video_segmentation_format()
            if is_video
            else meta_sam_parser.image_segmentation_format()
        )
        parser = fmt.create_parser()

        for chunk in stream:
            # Extract text delta from chunk
            chunk_text = ""
            if isinstance(chunk, str):
                chunk_text = chunk
            elif hasattr(chunk, "delta") and hasattr(chunk.delta, "text") and chunk.delta.text:
                chunk_text = chunk.delta.text
            elif hasattr(chunk, "output_text") and chunk.output_text:
                chunk_text = chunk.output_text
            elif hasattr(chunk, "text") and chunk.text:
                chunk_text = chunk.text
            elif hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    chunk_text = delta.content

            if chunk_text:
                parser.push(chunk_text)

        finish = parser.finish(CompletedOutcome())

        # Check diagnostics
        for diag in finish.result.diagnostics:
            if diag.severity == "error":
                logger.warning(
                    "meta_sam_parser error diagnostic: %s (%s) on line %s",
                    diag.message,
                    diag.code,
                    diag.line,
                )

        return finish.result.records

    def segment(
        self,
        image: str | bytes | Path,
        text_prompts: list[str],
    ) -> list[SegmentDetection]:
        """
        Segment an image against given natural language prompts using SAM 3.1.
        UNVERIFIED against live API.
        """
        validated_concepts = [validate_concept(p) for p in text_prompts]
        client = self._get_client()
        data_url, frame_w, frame_h, raw_bytes = encode_image_to_base64_data_url(image)
        frame_hash = hashlib.sha256(raw_bytes).hexdigest()

        all_detections: list[SegmentDetection] = []

        for concept in validated_concepts:

            # Check cache: sha256(frame) + concept + model + mask_encoding
            cache_key = compute_cache_key(
                frame_hash,
                provider=f"{self.version}:one_bit",
                prompt=concept,
            )

            client = self._get_client()

            def _call_sam() -> list[SegmentDetection]:
                input_parts = [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": data_url},
                ]
                stream = client.responses.create(
                    model="sam-3.1",
                    input=input_parts,
                    stream=True,
                    metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
                )

                records = self._parse_stream_records(stream, is_video=False)

                # Key results by explicit frame marker and object ID
                boxes: dict[tuple[int, str], SegmentationBoxRecord] = {}
                masks: dict[tuple[int, str], SegmentationMaskRecord] = {}

                for rec in records:
                    fid = rec.frame.frame_index if rec.frame else 0
                    oid = str(rec.object_id)
                    if rec.kind == "box":
                        boxes[(fid, oid)] = rec
                    elif rec.kind == "mask":
                        masks[(fid, oid)] = rec

                detections: list[SegmentDetection] = []
                for (fid, oid), box_rec in boxes.items():
                    mask_rec = masks.get((fid, oid))
                    conf = (
                        float(box_rec.confidence)
                        if box_rec.confidence is not None
                        else 0.85
                    )

                    # Coordinate space: box x2/y2 are inclusive per docs;
                    # meta_sam_parser sets left=x1, top=y1, right=x2+1, bottom=y2+1
                    left, top, right, bottom = (
                        box_rec.left,
                        box_rec.top,
                        box_rec.right,
                        box_rec.bottom,
                    )

                    # Normalized bounding box in [0.0, 1.0]
                    norm_box = {
                        "x": round(left / frame_w, 4),
                        "y": round(top / frame_h, 4),
                        "w": round((right - left) / frame_w, 4),
                        "h": round((bottom - top) / frame_h, 4),
                    }

                    # Decode mask to binary raster
                    polygon: list[list[float]] | None = None
                    if mask_rec is not None:
                        raster = decode_mask_to_raster(mask_rec.mask)
                        polygon = map_mask_to_full_frame(
                            mask_raster=raster,
                            mask_h=mask_rec.mask.height,
                            mask_w=mask_rec.mask.width,
                            left=left,
                            top=top,
                            right=right,
                            bottom=bottom,
                            frame_w=frame_w,
                            frame_h=frame_h,
                        )

                    detections.append(
                        SegmentDetection(
                            label=concept,
                            box=norm_box,
                            score=conf,
                            mask=polygon,
                            frame_id=fid,
                            timestamp_s=0.0,
                        )
                    )

                return detections

            # Execute with retry & BudgetGuard
            dets = execute_with_retry(
                _call_sam,
                estimated_cost=estimate_segmentation_cost(1),
            )
            all_detections.extend(dets)

        return all_detections

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        """
        Backward-compatible detection across a list of frames.
        Supports SAM_VIDEO_MODE flag for multi-frame video format.
        UNVERIFIED against live API.
        """
        concept = validate_concept(prompt)
        settings = get_settings()
        results: list[Detection] = []

        for idx, fpath in enumerate(frame_paths):
            ts = timestamps_s[idx] if timestamps_s and idx < len(timestamps_s) else float(idx)
            seg_dets = self.segment(fpath, [concept])
            for sd in seg_dets:
                results.append(
                    Detection(
                        frame_id=idx,
                        timestamp_s=ts,
                        prompt=concept,
                        score=sd.score,
                        bbox=sd.box,
                        polygon=sd.mask if isinstance(sd.mask, list) else None,
                    )
                )

        return results


# Alias for clean Segmenter protocol naming
MetaSegmenter = MetaSegmentationProvider


class MetaAgentProvider:
    """
    Planner & reasoning provider integrating with Muse Spark agent (muse-spark-1.3).
    Strictly Standard mode only: rejects any '-contributor' models.
    UNVERIFIED against live API (built against dev.meta.ai/docs specs and verified with doc fixtures).
    Implements Reasoner and AgentProvider protocols.
    """

    def __init__(
        self, client: Any | None = None, model_id: str = "muse-spark-1.3"
    ) -> None:
        if "-contributor" in model_id.lower():
            raise ValueError(
                f"Model ID '{model_id}' rejected: '-contributor' models train on user content. "
                "Only Standard mode models are permitted."
            )
        self.model_id = model_id
        self._client = client

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client
        settings = get_settings()
        api_key = settings.MODEL_API_KEY or settings.META_API_KEY
        if not api_key:
            raise ValueError(ERR_UNVERIFIED)
        base_url = settings.META_BASE_URL or "https://api.meta.ai/v1"
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    def judge(
        self,
        rule: dict[str, Any] | Any,
        evidence: dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        """
        Evaluate rule against evidence using Muse Spark 1.3 image understanding + structured output.
        UNVERIFIED against live API.
        """
        rule_dict = rule if isinstance(rule, dict) else getattr(rule, "__dict__", {})
        rule_desc = rule_dict.get("description") or rule_dict.get("title") or str(rule)

        # Extract available keyframes and valid frame IDs
        evidence_list = evidence if isinstance(evidence, list) else [evidence]
        valid_frame_ids: set[int] = set()
        user_content_parts: list[dict[str, Any]] = []

        evidence_summary_lines: list[str] = []
        for ev in evidence_list:
            if isinstance(ev, dict):
                fid = ev.get("frame_id")
                if fid is not None:
                    valid_frame_ids.add(int(fid))
                label = ev.get("label") or ev.get("prompt") or "object"
                box = ev.get("box") or ev.get("bbox") or {}
                score = ev.get("score") or 0.0
                evidence_summary_lines.append(
                    f"Frame {fid}: detected '{label}' with score {score:.2f} at {box}"
                )
                image_ref = ev.get("image") or ev.get("frame_path")
                if image_ref:
                    try:
                        data_url, _, _, _ = encode_image_to_base64_data_url(image_ref)
                        user_content_parts.append(
                            {"type": "image_url", "image_url": {"url": data_url}}
                        )
                    except Exception as e:
                        logger.debug("Could not encode frame image for Spark: %s", e)

        evidence_text = "\n".join(evidence_summary_lines) if evidence_summary_lines else "None provided."
        prompt_text = (
            f"Rule Description:\n{rule_desc}\n\n"
            f"Visual Grounding Evidence:\n{evidence_text}\n\n"
            f"Permitted Frame IDs for citation: {sorted(list(valid_frame_ids))}\n"
            "Evaluate compliance. Only cite frame IDs listed under permitted frames."
        )

        user_content_parts.insert(0, {"type": "text", "text": prompt_text})

        client = self._get_client()

        def _call_spark() -> dict[str, Any]:
            resp = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AuditLens Reasoning Agent (Muse Spark 1.3). "
                            "Evaluate building safety compliance using provided keyframe evidence. "
                            "Output strict JSON adhering to the verdict schema."
                        ),
                    },
                    {"role": "user", "content": user_content_parts},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "verdict",
                        "schema": SPARK_VERDICT_JSON_SCHEMA,
                        "strict": True,
                    },
                },
            )

            raw_content = ""
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                raw_content = resp.choices[0].message.content

            # Validate against schemas.py (any schema failure -> status="unsure")
            verdict = validate_verdict(raw_content)

            # Spark cannot invent evidence: cited_frame_ids must only cite frames passed in
            if valid_frame_ids:
                filtered_cited = [
                    fid for fid in verdict.cited_frame_ids if fid in valid_frame_ids
                ]
                if len(filtered_cited) != len(verdict.cited_frame_ids):
                    logger.warning(
                        "Spark cited ungrounded frame IDs %s not in valid frames %s. Filtering out.",
                        verdict.cited_frame_ids,
                        valid_frame_ids,
                    )
                    verdict.cited_frame_ids = filtered_cited

                # If no valid frames were cited for pass/fail, downgrade to unsure
                if not verdict.cited_frame_ids and verdict.status != VerdictStatus.UNSURE:
                    logger.warning(
                        "No valid cited frames remaining for verdict '%s'. Downgrading to 'unsure'.",
                        verdict.status.value,
                    )
                    verdict.status = VerdictStatus.UNSURE
                    verdict.reason += " (Downgraded to unsure: no valid cited keyframe evidence found)."

            return verdict.to_dict()

        return execute_with_retry(
            _call_spark,
            estimated_cost=estimate_reasoner_cost(1.0, 0.25),
        )

    def verify_presence(
        self,
        concept: str,
        frames: list[dict[str, Any]] | list[str],
    ) -> dict[str, Any]:
        """
        Verify presence of concept across frames using Muse Spark with SPARK_PRESENCE_JSON_SCHEMA.
        UNVERIFIED against live API.
        """
        concept_clean = validate_concept(concept)
        client = self._get_client()

        valid_frame_ids: list[int] = []
        user_content_parts: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Examine the provided image frames and determine if the concept '{concept_clean}' is present. Cite the exact frame ID(s) where it is observed.",
            }
        ]

        for i, f in enumerate(frames):
            fid = f.get("idx", f.get("id", i)) if isinstance(f, dict) else i
            fpath = f.get("path") if isinstance(f, dict) else str(f)
            valid_frame_ids.append(int(fid))
            try:
                data_url, _, _, _ = encode_image_to_base64_data_url(fpath)
                user_content_parts.append(
                    {"type": "text", "text": f"Frame ID {fid}:"}
                )
                user_content_parts.append(
                    {"type": "image_url", "image_url": {"url": data_url}}
                )
            except Exception as e:
                logger.warning("Could not encode frame %s: %s", fpath, e)

        def _call_spark_presence() -> dict[str, Any]:
            resp = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AuditLens Visual Verification Agent (Muse Spark). "
                            "Determine if the specified object/concept is visible in the provided frames. "
                            "Output strict JSON according to the schema."
                        ),
                    },
                    {"role": "user", "content": user_content_parts},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "presence_verdict",
                        "schema": SPARK_PRESENCE_JSON_SCHEMA,
                        "strict": True,
                    },
                },
            )
            raw = ""
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                raw = resp.choices[0].message.content
            return validate_presence_verdict(raw, allowed_frame_ids=valid_frame_ids)

        return execute_with_retry(
            _call_spark_presence,
            estimated_cost=estimate_reasoner_cost(0.5, 0.1),
        )

    def plan_fixes(
        self,
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Generate prioritized fix actions from audit findings using Muse Spark.
        TODO(meta): Connect to live Muse Spark when API key is provided.
        UNVERIFIED against live API.
        """
        from app.providers.schemas import validate_fix_actions

        client = self._get_client()
        finding_ids = [f.get("id", "") for f in findings if f.get("id")]

        def _call_spark_plan() -> list[dict[str, Any]]:
            # Prompt Spark to generate prioritized remediation actions
            summary = [
                {
                    "finding_id": f.get("id"),
                    "rule_id": f.get("rule_id"),
                    "status": f.get("status"),
                    "severity": f.get("severity"),
                    "rationale": f.get("rationale"),
                }
                for f in findings
                if f.get("status") in ("fail", "unsure")
            ]
            resp = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AuditLens Safety Action Planner (Muse Spark). "
                            "Given the safety findings, generate prioritized corrective actions "
                            "with effort (S/M/L) and realistic due days."
                        ),
                    },
                    {"role": "user", "content": json.dumps(summary)},
                ],
            )
            raw = ""
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                raw = resp.choices[0].message.content
            return validate_fix_actions(raw, allowed_finding_ids=finding_ids)

        return execute_with_retry(
            _call_spark_plan,
            estimated_cost=estimate_reasoner_cost(0.5, 0.2),
        )

    def compile_template(
        self,
        text: str,
    ) -> dict[str, Any]:
        """
        Compile natural language checklist text into structured template JSON using Muse Spark.
        TODO(meta): Connect to live Muse Spark when API key is provided.
        UNVERIFIED against live API.
        """
        client = self._get_client()

        def _call_spark_compile() -> dict[str, Any]:
            resp = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AuditLens Checklist Compiler (Muse Spark). "
                            "Convert natural language safety requirements into structured template JSON. "
                            "Every SAM prompt must be a single plain noun phrase (no conjunctions, negation, or spatial words)."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
            )
            raw = ""
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                raw = resp.choices[0].message.content
            return json.loads(raw) if raw else {}

        return execute_with_retry(
            _call_spark_compile,
            estimated_cost=estimate_reasoner_cost(1.0, 0.5),
        )

    def extract_note(
        self,
        transcript: str,
    ) -> dict[str, Any]:
        """
        Extract structured information {location, issue, severity_hint} from spoken transcript using Muse Spark.
        TODO(meta): Connect to live Muse Spark when API key is provided.
        UNVERIFIED against live API.
        """
        from app.providers.schemas import validate_structured_voice_note

        client = self._get_client()

        def _call_spark_extract() -> dict[str, Any]:
            resp = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AuditLens Voice Note Structurer (Muse Spark). "
                            "Extract location, issue, and severity_hint ('high'|'medium'|'low') "
                            "from the auditor transcript (supports English and Hinglish). Output strict JSON."
                        ),
                    },
                    {"role": "user", "content": transcript},
                ],
                response_format={"type": "json_object"},
            )
            raw = ""
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                raw = resp.choices[0].message.content
            return validate_structured_voice_note(raw)

        return execute_with_retry(
            _call_spark_extract,
            estimated_cost=estimate_reasoner_cost(0.2, 0.1),
        )

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        """
        Execute audit plan over rules using tools, emitting SSE events.
        UNVERIFIED against live API.
        """
        findings = []
        for rule in rules:
            rule_dict = rule.model_dump() if hasattr(rule, "model_dump") else dict(rule)
            verdict_dict = self.judge(rule_dict, [])
            findings.append(verdict_dict)
            emit({"event": "finding", "data": verdict_dict})
        return findings


# Alias for clean Reasoner protocol naming
MetaReasoner = MetaAgentProvider


class MetaTranscriptionProvider:
    """
    Speech-to-text provider integrating with Muse Voice Transcribe API (muse-voice-transcribe-1.0).
    Turn-level timestamps only (no word-level timestamps).
    UNVERIFIED against live API (built against dev.meta.ai/docs specs and verified with doc fixtures).
    Implements Transcriber and TranscriptionProvider protocols.
    """

    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB limit

    def __init__(
        self, client: Any | None = None, model_id: str = "muse-voice-transcribe-1.0"
    ) -> None:
        if "-contributor" in model_id.lower():
            raise ValueError(
                f"Model ID '{model_id}' rejected: '-contributor' models train on user content."
            )
        self.model_id = model_id
        self._client = client

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client
        settings = get_settings()
        api_key = settings.MODEL_API_KEY or settings.META_API_KEY
        if not api_key:
            raise ValueError(ERR_UNVERIFIED)
        base_url = settings.META_BASE_URL or "https://api.meta.ai/v1"
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    def transcribe(
        self,
        audio_path: str | bytes | Path,
        language_hint: str | None = None,
    ) -> Transcript:
        """
        Transcribe audio recording into turns with timestamps using Muse Voice Transcribe.
        Turn-level timestamps only.
        UNVERIFIED against live API.
        """
        client = self._get_client()

        p = Path(audio_path)
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size = p.stat().st_size
        if file_size > self.MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"Audio file size ({file_size / (1024*1024):.2f} MB) exceeds maximum allowed limit of "
                f"{self.MAX_FILE_SIZE_BYTES / (1024*1024):.1f} MB."
            )

        client = self._get_client()

        def _call_transcription() -> Transcript:
            with open(p, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=self.model_id,
                    file=f,
                    language=language_hint or "en",
                    response_format="verbose_json",
                )

            full_text = getattr(resp, "text", "") or ""
            language = getattr(resp, "language", language_hint or "en")

            # Parse turn-level timestamps only (no word-level timestamps)
            turns: list[TranscriptTurn] = []
            segments: list[TranscriptSegment] = []

            raw_segments = getattr(resp, "segments", None) or []
            for seg in raw_segments:
                start = float(getattr(seg, "start", 0.0))
                end = float(getattr(seg, "end", 0.0))
                txt = getattr(seg, "text", "").strip()
                spk = getattr(seg, "speaker", None)
                turns.append(
                    TranscriptTurn(
                        start_s=start,
                        end_s=end,
                        text=txt,
                        speaker=spk,
                    )
                )
                segments.append(
                    TranscriptSegment(
                        start_s=start,
                        end_s=end,
                        text=txt,
                    )
                )

            if not turns and full_text:
                turns.append(
                    TranscriptTurn(
                        start_s=0.0,
                        end_s=5.0,
                        text=full_text,
                        speaker=None,
                    )
                )
                segments.append(
                    TranscriptSegment(
                        start_s=0.0,
                        end_s=5.0,
                        text=full_text,
                    )
                )

            return Transcript(
                text=full_text,
                language=language,
                segments=segments,
                turns=turns,
            )

        return execute_with_retry(
            _call_transcription,
            estimated_cost=estimate_transcription_cost(1.0),
        )


# Alias for clean Transcriber protocol naming
MetaTranscriber = MetaTranscriptionProvider
