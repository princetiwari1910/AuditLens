"""Strict JSON Schema and Pydantic validation for Spark Reasoner verdicts."""

from __future__ import annotations

from enum import Enum
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("auditlens.providers.schemas")


class VerdictStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNSURE = "unsure"


# ── Strict JSON Schema for Muse Spark Reasoner verdicts ───────────────────────
# Nesting depth: 3 (depth <= 3)
# No recursive $ref references
# Strict enums for status
SPARK_VERDICT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ReasonerVerdict",
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["pass", "fail", "unsure"],
            "description": "Verdict indicating compliance status.",
        },
        "reason": {
            "type": "string",
            "description": "Plain-English explanation citing observed visual or audio evidence.",
        },
        "cited_frame_ids": {
            "type": "array",
            "description": "List of frame indices cited as visual evidence.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence probability between 0.0 and 1.0.",
        },
    },
    "required": ["status", "reason"],
    "additionalProperties": True,
}


def compute_schema_depth(schema: Any, current_depth: int = 1) -> int:
    """Calculate maximum nesting depth of a JSON schema dictionary."""
    if not isinstance(schema, dict) or not schema:
        return current_depth

    # Check for forbidden recursive refs
    if "$ref" in schema:
        raise ValueError("Recursive references ($ref) are forbidden in Spark verdict schema.")

    max_d = current_depth
    for key, val in schema.items():
        if isinstance(val, dict):
            max_d = max(max_d, compute_schema_depth(val, current_depth + 1))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    max_d = max(max_d, compute_schema_depth(item, current_depth + 1))
    return max_d


class ReasonerVerdict(BaseModel):
    """
    Pydantic representation of the Spark Reasoner verdict with backward-compatible access.
    """
    status: VerdictStatus
    reason: str
    cited_frame_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.50)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)

        # Map 'verdict' -> 'status'
        if "status" not in normalized and "verdict" in normalized:
            normalized["status"] = normalized["verdict"]

        # Map 'cited_frames' -> 'cited_frame_ids'
        if "cited_frame_ids" not in normalized and "cited_frames" in normalized:
            normalized["cited_frame_ids"] = normalized["cited_frames"]

        # Normalize status string to lowercase
        if "status" in normalized:
            raw_val = normalized["status"]
            if isinstance(raw_val, VerdictStatus):
                normalized["status"] = raw_val.value
            else:
                normalized["status"] = str(raw_val).strip().lower()

        return normalized

    @field_validator("cited_frame_ids", mode="before")
    @classmethod
    def clean_frame_ids(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if isinstance(v, (int, float)):
            return [int(v)]
        if isinstance(v, list):
            res = []
            for item in v:
                try:
                    res.append(int(item))
                except (ValueError, TypeError):
                    continue
            return res
        return []

    @property
    def verdict(self) -> str:
        return self.status.value

    @property
    def cited_frames(self) -> list[int]:
        return self.cited_frame_ids

    def to_dict(self) -> dict[str, Any]:
        """Return dictionary containing both standard and backward-compatible fields."""
        return {
            "status": self.status.value,
            "verdict": self.status.value,
            "reason": self.reason,
            "cited_frame_ids": list(self.cited_frame_ids),
            "cited_frames": list(self.cited_frame_ids),
            "confidence": round(float(self.confidence), 4),
        }


def validate_verdict(raw_data: Any) -> ReasonerVerdict:
    """
    Validate raw model response against strict ReasonerVerdict schema.
    If validation fails or output is malformed, logs a warning and forces
    status="unsure" to adhere to the Evidence-First working agreement.
    """
    data = raw_data
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except Exception as json_err:
            logger.warning(
                "Spark verdict is not valid JSON (%s). Forcing 'unsure' verdict.",
                json_err,
            )
            return ReasonerVerdict(
                status=VerdictStatus.UNSURE,
                reason=f"Model output parsing failure (invalid JSON): {json_err}",
                cited_frame_ids=[],
                confidence=0.50,
            )

    if not isinstance(data, dict):
        logger.warning(
            "Spark verdict response must be a JSON object, got %s. Forcing 'unsure' verdict.",
            type(data).__name__,
        )
        return ReasonerVerdict(
            status=VerdictStatus.UNSURE,
            reason=f"Model output format failure (expected object, got {type(data).__name__})",
            cited_frame_ids=[],
            confidence=0.50,
        )

    try:
        verdict_obj = ReasonerVerdict.model_validate(data)
        return verdict_obj
    except Exception as exc:
        logger.warning(
            "Spark verdict failed schema validation: %s. Forcing 'unsure' fallback.",
            exc,
        )
        return ReasonerVerdict(
            status=VerdictStatus.UNSURE,
            reason=f"Schema validation fallback: {exc}",
            cited_frame_ids=[],
            confidence=0.50,
        )
