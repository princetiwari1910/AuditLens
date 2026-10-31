"""Provider module for AuditLens AI capabilities with record/replay support."""

from app.config import get_settings
from app.providers.base import (
    Detection,
    SegmentDetection,
    Transcript,
    TranscriptSegment,
    TranscriptTurn,
    SegmentationProvider,
    TranscriptionProvider,
    AgentProvider,
    Segmenter,
    Reasoner,
    Transcriber,
)
from app.providers.mock import (
    MockSegmentationProvider,
    MockTranscriptionProvider,
    MockAgentProvider,
    MockSegmenter,
    MockTranscriber,
    MockReasoner,
)
from app.providers.meta import (
    MetaSegmentationProvider,
    MetaTranscriptionProvider,
    MetaAgentProvider,
    MetaSegmenter,
    MetaTranscriber,
    MetaReasoner,
)
from app.providers.record_replay import (
    RecordReplaySegmenter,
    RecordReplayTranscriber,
    RecordReplayReasoner,
)


def get_segmentation_provider() -> SegmentationProvider:
    settings = get_settings()
    mode = settings.PROVIDER_MODE.lower()

    if mode == "meta":
        return MetaSegmentationProvider()
    elif mode in ("record", "replay"):
        # Wrap underlying provider (meta in production or mock for test recording)
        base = MetaSegmentationProvider() if settings.MODEL_API_KEY else MockSegmentationProvider()
        return RecordReplaySegmenter(base, mode=mode)
    return MockSegmentationProvider()


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    mode = settings.PROVIDER_MODE.lower()

    if mode == "meta":
        return MetaTranscriptionProvider()
    elif mode in ("record", "replay"):
        base = MetaTranscriptionProvider() if settings.MODEL_API_KEY else MockTranscriptionProvider()
        return RecordReplayTranscriber(base, mode=mode)
    return MockTranscriptionProvider()


def get_agent_provider() -> AgentProvider:
    settings = get_settings()
    mode = settings.PROVIDER_MODE.lower()

    if mode == "meta":
        return MetaAgentProvider()
    return MockAgentProvider()


def get_segmenter() -> Segmenter:
    """Returns provider conforming to the Segmenter protocol."""
    return get_segmentation_provider()  # type: ignore


def get_transcriber() -> Transcriber:
    """Returns provider conforming to the Transcriber protocol."""
    return get_transcription_provider()  # type: ignore


def get_reasoner() -> Reasoner:
    """Returns provider conforming to the Reasoner protocol."""
    settings = get_settings()
    mode = settings.PROVIDER_MODE.lower()

    if mode == "meta":
        return MetaReasoner()
    elif mode in ("record", "replay"):
        base = MetaReasoner() if settings.MODEL_API_KEY else MockReasoner()
        return RecordReplayReasoner(base, mode=mode)
    return MockReasoner()
