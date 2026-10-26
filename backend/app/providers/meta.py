"""Real Meta API providers (TODO: implement after Meta API access)."""

from __future__ import annotations

from typing import Any, Callable

from app.providers.base import Detection, Transcript

ERR_MSG = "Implement after Meta API access: see docs/META_INTEGRATION.md"


class MetaSegmentationProvider:
    """
    Segmentation provider integrating with Meta SAM API.
    TODO(meta): implement once API credentials arrive.
    """

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        # TODO(meta): Call Meta SAM endpoint, normalize bounding boxes & polygons to [0, 1]
        raise NotImplementedError(ERR_MSG)


class MetaTranscriptionProvider:
    """
    Speech-to-text provider integrating with Meta ASR API.
    TODO(meta): implement once API credentials arrive.
    """

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        # TODO(meta): Call Meta ASR endpoint, return Transcript with segments
        raise NotImplementedError(ERR_MSG)


class MetaAgentProvider:
    """
    Planner provider integrating with Meta Llama / LLM tool-calling.
    TODO(meta): implement once API credentials arrive.
    """

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        # TODO(meta): Invoke Meta LLM with tool schemas and execute planner
        raise NotImplementedError(ERR_MSG)
