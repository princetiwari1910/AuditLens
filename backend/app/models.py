"""SQLModel database models and Pydantic schemas for AuditLens."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_uuid() -> str:
    return str(uuid.uuid4())


# ── Rule and Template Pydantic Schemas ─────────────────────────────────────────

class RuleType(str, Enum):
    PRESENCE = "presence"
    ABSENCE = "absence"
    COUNT = "count"
    MEASUREMENT = "measurement"
    COLOCATION = "colocation"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNSURE = "unsure"


class AuditStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RuleModel(BaseModel):
    id: str
    title: str
    type: RuleType
    severity: Severity = Severity.MEDIUM
    sam_prompts: list[str] = PydanticField(default_factory=list)
    params: dict[str, Any] = PydanticField(default_factory=dict)
    fix_text: str = ""
    detector: str = "SAM 3.1"
    evidence_needed: str = "Bounding box detection and confidence score"


class TemplateModel(BaseModel):
    id: str
    name: str
    description: str = ""
    disclaimer: str = (
        "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. "
        "Verify against local regulations and a qualified inspector."
    )
    rules: list[RuleModel] = PydanticField(default_factory=list)


# ── Database Tables (SQLModel) ────────────────────────────────────────────────

class Audit(SQLModel, table=True):
    __tablename__ = "audit"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    template_id: str = Field(index=True)
    custom_rules_json: str | None = Field(default=None)
    status: str = Field(default=AuditStatus.QUEUED.value, index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    video_path: str | None = Field(default=None)
    duration_s: float | None = Field(default=None)
    summary_json: str | None = Field(default=None)
    error: str | None = Field(default=None)
    provider_mode: str = Field(default="mock")
    model_segmentation: str = Field(default="SAM 3.1")
    model_agent: str = Field(default="Muse Spark")
    model_transcription: str = Field(default="Muse Voice Transcribe")
    is_replay: bool = Field(default=False)


class Frame(SQLModel, table=True):
    __tablename__ = "frame"

    id: int | None = Field(default=None, primary_key=True)
    audit_id: str = Field(index=True)
    idx: int = Field(index=True)
    timestamp_s: float
    path: str
    sha256: str = Field(index=True)


class CacheEntry(SQLModel, table=True):
    __tablename__ = "cache_entry"

    key: str = Field(primary_key=True)
    provider: str = Field(index=True)
    prompt: str
    result_json: str
    created_at: datetime = Field(default_factory=_utc_now)


class Finding(SQLModel, table=True):
    __tablename__ = "finding"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    audit_id: str = Field(index=True)
    rule_id: str = Field(index=True)
    status: str = Field(index=True)  # "pass", "fail", "unsure"
    confidence: float
    timestamp_s: float
    frame_idx: int
    overlay_path: str | None = Field(default=None)
    measurement_json: str | None = Field(default=None)
    rationale: str = ""
    fix_text: str = ""
    severity: str = "medium"
    sources_json: str = "[]"


class VoiceNote(SQLModel, table=True):
    __tablename__ = "voice_note"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    audit_id: str = Field(index=True)
    timestamp_s: float
    audio_path: str
    transcript: str | None = Field(default=None)
    language: str | None = Field(default=None)


class CostLog(SQLModel, table=True):
    __tablename__ = "cost_log"

    id: int | None = Field(default=None, primary_key=True)
    audit_id: str | None = Field(default=None, index=True)
    provider: str = Field(index=True)
    operation: str
    units: float
    est_cost_usd: float
    model_id: str = Field(default="")
    latency_ms: int = Field(default=0)
    cache_hit: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utc_now)
