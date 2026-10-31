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
        base = MetaSegmentationProvider()
    elif mode == "mock":
        base = MockSegmentationProvider()
    else:
        base = MetaSegmentationProvider() if settings.MODEL_API_KEY else MockSegmentationProvider()

    wrap_mode = mode if mode in ("record", "replay") else "passthrough"
    return RecordReplaySegmenter(base, mode=wrap_mode)


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    mode = settings.PROVIDER_MODE.lower()

    if mode == "meta":
        base = MetaTranscriptionProvider()
    elif mode == "mock":
        base = MockTranscriptionProvider()
    else:
        base = MetaTranscriptionProvider() if settings.MODEL_API_KEY else MockTranscriptionProvider()

    wrap_mode = mode if mode in ("record", "replay") else "passthrough"
    return RecordReplayTranscriber(base, mode=wrap_mode)


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
        base = MetaReasoner()
    elif mode == "mock":
        base = MockReasoner()
    else:
        base = MetaReasoner() if settings.MODEL_API_KEY else MockReasoner()

    wrap_mode = mode if mode in ("record", "replay") else "passthrough"
    return RecordReplayReasoner(base, mode=wrap_mode)
