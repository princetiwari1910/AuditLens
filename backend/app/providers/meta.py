"""Target Meta Foundation Model provider stubs (SAM 3.1, Muse Spark, Muse Voice Transcribe).

NOTE: Do not assume specific request/response shapes here; leave them as TODO(meta)
to be implemented directly against the official documentation at dev.meta.ai/docs.
"""

from __future__ import annotations

from typing import Any, Callable

from app.providers.base import Detection, Transcript

ERR_MSG = "Implement after Meta API access: see docs/META_INTEGRATION.md"


class MetaSegmentationProvider:
    """
    Segmentation provider integrating with SAM 3.1 API.
    TODO(meta): implement once API credentials arrive from dev.meta.ai/docs.
    """

    @property
    def version(self) -> str:
        return "sam-3.1"

    @property
    def scenario_hash(self) -> str:
        return "meta-api"

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        # TODO(meta): Call SAM 3.1 endpoint, normalize bounding boxes & polygons to [0, 1]
        raise NotImplementedError(ERR_MSG)


class MetaTranscriptionProvider:
    """
    Speech-to-text provider integrating with Muse Voice Transcribe API.
    TODO(meta): implement once API credentials arrive from dev.meta.ai/docs.
    """

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        # TODO(meta): Call Muse Voice Transcribe endpoint, return Transcript with segments
        raise NotImplementedError(ERR_MSG)


class MetaAgentProvider:
    """
    Planner provider integrating with Muse Spark agent tool-calling over the ToolRegistry.
    TODO(meta): implement once API credentials arrive from dev.meta.ai/docs.
    """

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        # TODO(meta): Invoke Muse Spark with tool schemas and execute planner
        raise NotImplementedError(ERR_MSG)
