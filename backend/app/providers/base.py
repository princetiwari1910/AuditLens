"""Abstract provider interfaces and normalized data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class Detection:
    """Normalized object detection / segmentation result."""
    frame_id: int
    timestamp_s: float
    prompt: str
    score: float
    bbox: dict[str, float]  # Normalized {x, y, w, h} within 0.0 .. 1.0
    polygon: list[list[float]] | None = None  # Normalized list of [x, y] coordinates


@dataclass
class TranscriptSegment:
    """Segment within an audio transcript."""
    start_s: float
    end_s: float
    text: str


@dataclass
class Transcript:
    """Normalized speech-to-text transcript."""
    text: str
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)


class SegmentationProvider(Protocol):
    """Visual grounding & segmentation model interface (e.g. Segment Anything / SAM)."""

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        """Detect objects matching prompt across given frame paths."""
        ...


class TranscriptionProvider(Protocol):
    """Audio speech-to-text interface (e.g. Meta ASR)."""

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        """Transcribe an audio recording into text."""
        ...


class AgentProvider(Protocol):
    """Orchestrator interface for reasoning and tool execution."""

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        """Execute the audit plan over rules using tools, emitting events."""
        ...
