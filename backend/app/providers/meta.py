"""Target Meta Foundation Model provider stubs (SAM 3.1, Muse Spark, Muse Voice Transcribe).

NOTE: Do not assume specific request/response shapes here; leave them as TODO(meta)
to be implemented directly against the official documentation at dev.meta.ai/docs.
No fake outputs are returned here; all calls raise explicit NotImplementedError.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.providers.base import (
    Detection,
    SegmentDetection,
    Transcript,
    TranscriptTurn,
)

ERR_MSG = "TODO(meta): Implement after Meta API access: see docs/META_INTEGRATION.md"


class MetaSegmentationProvider:
    """
    Segmentation provider integrating with SAM 3.1 API.
    Implements both Segmenter and SegmentationProvider protocols.
    TODO(meta): implement once API credentials arrive from dev.meta.ai/docs.
    """

    @property
    def version(self) -> str:
        return "sam-3.1"

    @property
    def scenario_hash(self) -> str:
        return "meta-api"

    def segment(
        self,
        image: str | bytes | Path,
        text_prompts: list[str],
    ) -> list[SegmentDetection]:
        # TODO(meta): Call SAM 3.1 endpoint, normalize bounding boxes & polygons to [0, 1]
        raise NotImplementedError(ERR_MSG)

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        # TODO(meta): Call SAM 3.1 endpoint, normalize bounding boxes & polygons to [0, 1]
        raise NotImplementedError(ERR_MSG)


# Alias for clean Segmenter naming
MetaSegmenter = MetaSegmentationProvider


class MetaTranscriptionProvider:
    """
    Speech-to-text provider integrating with Muse Voice Transcribe API.
    Implements both Transcriber and TranscriptionProvider protocols.
    TODO(meta): implement once API credentials arrive from dev.meta.ai/docs.
    """

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        # TODO(meta): Call Muse Voice Transcribe endpoint, return Transcript with turns & segments
        raise NotImplementedError(ERR_MSG)


# Alias for clean Transcriber naming
MetaTranscriber = MetaTranscriptionProvider


class MetaAgentProvider:
    """
    Planner & reasoning provider integrating with Muse Spark agent tool-calling over ToolRegistry.
    Implements both Reasoner and AgentProvider protocols.
    TODO(meta): implement once API credentials arrive from dev.meta.ai/docs.
    """

    def judge(
        self,
        rule: dict[str, Any] | Any,
        evidence: dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        # TODO(meta): Call Muse Spark with rule and evidence, returning verdict JSON:
        # {"verdict": "pass"|"fail"|"unsure", "reason": str, "cited_frames": list[int]}
        raise NotImplementedError(ERR_MSG)

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        # TODO(meta): Invoke Muse Spark with tool schemas and execute planner
        raise NotImplementedError(ERR_MSG)


# Alias for clean Reasoner naming
MetaReasoner = MetaAgentProvider
