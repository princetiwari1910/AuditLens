"""Abstract provider interfaces and normalized data contracts for AuditLens."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


# ── Segmentation Data Contracts ───────────────────────────────────────────────

@dataclass
class SegmentDetection:
    """Normalized object detection / segmentation result produced by Segmenter."""
    label: str
    box: dict[str, float]  # Normalized {x, y, w, h} within 0.0 .. 1.0
    score: float
    mask: list[list[float]] | str | None = None  # Normalized polygon or mask representation
    frame_id: int = 0
    timestamp_s: float = 0.0


@dataclass
class Detection:
    """Normalized object detection / segmentation result (backward-compatible)."""
    frame_id: int
    timestamp_s: float
    prompt: str
    score: float
    bbox: dict[str, float]  # Normalized {x, y, w, h} within 0.0 .. 1.0
    polygon: list[list[float]] | None = None  # Normalized list of [x, y] coordinates


# ── Transcription Data Contracts ──────────────────────────────────────────────

@dataclass
class TranscriptTurn:
    """Turn within an audio transcription with timestamps."""
    start_s: float
    end_s: float
    text: str
    speaker: str | None = None


@dataclass
class TranscriptSegment:
    """Segment within an audio transcript (backward-compatible)."""
    start_s: float
    end_s: float
    text: str


@dataclass
class Transcript:
    """Normalized speech-to-text transcript."""
    text: str
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    turns: list[TranscriptTurn] = field(default_factory=list)


# ── Reasoning Data Contracts ──────────────────────────────────────────────────

@dataclass
class Verdict:
    """Verdict produced by Reasoner for a specific safety rule."""
    verdict: str  # "pass" | "fail" | "unsure"
    reason: str
    cited_frames: list[int] = field(default_factory=list)
    confidence: float = 0.0


# ── Provider Protocols ────────────────────────────────────────────────────────

@runtime_checkable
class Segmenter(Protocol):
    """Abstract interface for image segmentation models (e.g. SAM 3.1)."""

    def segment(
        self,
        image: str | bytes | Path,
        text_prompts: list[str],
    ) -> list[SegmentDetection]:
        """Segment image against given text prompts."""
        ...


@runtime_checkable
class Reasoner(Protocol):
    """Abstract interface for LLM / vision reasoning agent (e.g. Muse Spark)."""

    def judge(
        self,
        rule: dict[str, Any] | Any,
        evidence: dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        """Evaluate rule against evidence and return verdict JSON with cited frames."""
        ...

    def verify_presence(
        self,
        concept: str,
        frames: list[dict[str, Any]] | list[str],
    ) -> dict[str, Any]:
        """Verify presence of a concept across frames; return {present: bool, cited_frame_ids: list[int], rationale: str}."""
        ...


@runtime_checkable
class Transcriber(Protocol):
    """Abstract interface for speech-to-text models (e.g. Muse Voice Transcribe)."""

    def transcribe(
        self,
        audio: str | bytes | Path,
    ) -> list[TranscriptTurn] | Transcript:
        """Transcribe an audio recording into turns with timestamps."""
        ...


# ── Backward-compatible Protocols ─────────────────────────────────────────────

@runtime_checkable
class SegmentationProvider(Protocol):
    """Visual grounding & segmentation model interface (Target: SAM 3.1)."""

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        """Detect objects matching prompt across given frame paths."""
        ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Audio speech-to-text interface (Target: Muse Voice Transcribe)."""

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        """Transcribe an audio recording into text."""
        ...


@runtime_checkable
class AgentProvider(Protocol):
    """Orchestrator interface for reasoning and tool execution (Target: Muse Spark)."""

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        """Execute the audit plan over rules using tools, emitting events."""
        ...

