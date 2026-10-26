"""Provider module for AuditLens AI capabilities."""

from app.config import get_settings
from app.providers.base import (
    Detection,
    Transcript,
    TranscriptSegment,
    SegmentationProvider,
    TranscriptionProvider,
    AgentProvider,
)
from app.providers.mock import (
    MockSegmentationProvider,
    MockTranscriptionProvider,
    MockAgentProvider,
)
from app.providers.meta import (
    MetaSegmentationProvider,
    MetaTranscriptionProvider,
    MetaAgentProvider,
)


def get_segmentation_provider() -> SegmentationProvider:
    settings = get_settings()
    if settings.PROVIDER_MODE == "meta":
        return MetaSegmentationProvider()
    return MockSegmentationProvider()


def get_transcription_provider() -> TranscriptionProvider:
    settings = get_settings()
    if settings.PROVIDER_MODE == "meta":
        return MetaTranscriptionProvider()
    return MockTranscriptionProvider()


def get_agent_provider() -> AgentProvider:
    settings = get_settings()
    if settings.PROVIDER_MODE == "meta":
        return MetaAgentProvider()
    return MockAgentProvider()
