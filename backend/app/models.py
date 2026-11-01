"""SQLModel database models and Pydantic schemas for AuditLens."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Self
import uuid

from pydantic import BaseModel, Field as PydanticField, field_validator, model_validator
from sqlmodel import Field, SQLModel

from app.concept_validation import validate_concept


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


class EvidenceStrength(str, Enum):
    MASK_BACKED = "mask_backed"
    MODEL_ATTESTED = "model_attested"
    VOICE_NOTE = "voice_note"


class DetectorType(str, Enum):
    SAM = "sam"
    SPARK_VISION = "spark_vision"
    SAM_THEN_SPARK = "sam_then_spark"


class EvidenceItem(BaseModel):
    id: str = PydanticField(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    frame_id: int
    ts: float
    source: str  # "sam" | "spark" | "voice"
    concept: str
    box: dict[str, float] | None = None
    mask_ref: Any | None = None
    score: float = 0.0
    strength: EvidenceStrength = EvidenceStrength.MODEL_ATTESTED


class RuleModel(BaseModel):
    id: str
    title: str
    type: RuleType
    severity: Severity = Severity.MEDIUM
    sam_prompts: list[str] = PydanticField(default_factory=list)
    params: dict[str, Any] = PydanticField(default_factory=dict)
    fix_text: str = ""
    detector: str = "sam"
    evidence_needed: str = "Bounding box detection and confidence score"

    @field_validator("detector", mode="before")
    @classmethod
    def normalize_detector(cls, v: Any) -> str:
        if not v:
            return "sam"
        v_str = str(v).lower().strip()
        if "spark_vision" in v_str or v_str == "spark":
            return "spark_vision"
        if "sam_then_spark" in v_str or "hybrid" in v_str:
            return "sam_then_spark"
        if "sam" in v_str:
            return "sam"
        return "sam"


class TemplateModel(BaseModel):
    id: str
    name: str
    description: str = ""
    disclaimer: str = (
        "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. "
        "Verify against local regulations and a qualified inspector."
    )
    rules: list[RuleModel] = PydanticField(default_factory=list)

    @model_validator(mode="after")
    def validate_concepts_on_load(self) -> Self:
        """Validate that all rules in template use plain noun phrases for SAM 3.1."""
        for rule in self.rules:
            for prompt in rule.sam_prompts:
                validate_concept(prompt, rule_id=rule.id)
        return self


# ── Database Tables (SQLModel) ────────────────────────────────────────────────

class Site(SQLModel, table=True):
    __tablename__ = "site"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    name: str = Field(index=True)
    location_label: str = Field(default="")
    created_at: datetime = Field(default_factory=_utc_now)


class Audit(SQLModel, table=True):
    __tablename__ = "audit"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    site_id: str | None = Field(default=None, index=True)
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
    source_provider_mode: str | None = Field(default=None)
    fix_plan_json: str | None = Field(default=None)


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
    evidence_ledger_json: str = "[]"
    strongest_evidence_json: str | None = Field(default=None)
    decision_policy: str = "default"
    detector: str = "sam"
    support_count: int = 1
    stability: float = 1.0
    escalation_steps_json: str = "[]"
    ai_verdict: str = Field(default="unsure")
    final_verdict: str = Field(default="unsure")


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    audit_id: str = Field(index=True)
    finding_id: str = Field(index=True)
    actor_label: str = Field(default="reviewer")
    action: str = Field(index=True)  # "approve_ai", "override_pass", "override_fail"
    before: str
    after: str
    note: str
    ts: datetime = Field(default_factory=_utc_now)


class VoiceNote(SQLModel, table=True):
    __tablename__ = "voice_note"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    audit_id: str = Field(index=True)
    timestamp_s: float
    audio_path: str = Field(default="")
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


class AuditSpan(SQLModel, table=True):
    __tablename__ = "audit_span"

    id: int | None = Field(default=None, primary_key=True)
    audit_id: str = Field(index=True)
    stage: str = Field(index=True)
    model: str = Field(default="")
    concept: str | None = Field(default=None)
    latency_ms: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    cache_hit: bool = Field(default=False)
    retries: int = Field(default=0)
    step_reason: str = Field(default="")
    simulated: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utc_now)


class ShareToken(SQLModel, table=True):
    __tablename__ = "share_token"

    id: str = Field(default_factory=_gen_uuid, primary_key=True)
    audit_id: str = Field(index=True)
    token_hash: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime | None = Field(default=None)
    access_count: int = Field(default=0)

