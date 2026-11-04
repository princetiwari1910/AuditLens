"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR: Path = (PROJECT_ROOT / "data").resolve()


class Settings(BaseSettings):
    """Central configuration – every value has a safe default for local dev."""

    # Provider mode: "mock", "meta", "record", or "replay"
    PROVIDER_MODE: str = "mock"

    # File storage root (defaults to <PROJECT_ROOT>/data)
    DATA_DIR: Path = DEFAULT_DATA_DIR

    @field_validator("DATA_DIR", mode="before")
    @classmethod
    def resolve_data_dir(cls, v: Any) -> Path:
        if v is None or v == "":
            return DEFAULT_DATA_DIR
        p = Path(v)
        if not p.is_absolute():
            return (PROJECT_ROOT / p).resolve()
        return p.resolve()

    # Upload limits
    MAX_UPLOAD_MB: int = 200
    MAX_VIDEO_DURATION_S: int = 90  # 90-second maximum walkthrough limit

    # Frame sampling
    FRAME_FPS: int = 1

    # Rule evaluation
    MIN_CONFIDENCE_PASS: float = 0.6

    # CORS Allowed Origins (comma-separated or single string e.g. "http://localhost:5173,https://auditlens.app")
    CORS_ORIGINS: str = "*"

    # Target Meta Foundation Models:
    # - Segmentation: SAM 3.1
    # - Agent Planner: Muse Spark (tool-calling over ToolRegistry)
    # - Transcription: Muse Voice Transcribe
    MODEL_ID_SEGMENTATION: str = "SAM 3.1"
    MODEL_ID_AGENT: str = "Muse Spark"
    MODEL_ID_TRANSCRIPTION: str = "Muse Voice Transcribe"

    @field_validator("MODEL_ID_AGENT", "MODEL_ID_SEGMENTATION", "MODEL_ID_TRANSCRIPTION", "ESCALATION_MODEL", mode="after")
    @classmethod
    def reject_contributor_models(cls, v: str | None) -> str | None:
        if v and "-contributor" in v.lower():
            raise ValueError(
                f"Model ID '{v}' rejected: '-contributor' models train on user content. "
                "Only Standard mode models are permitted."
            )
        return v

    # Demo Replay fallback flag (DEMO_REPLAY=1 replays recorded audit fixtures)
    DEMO_REPLAY: bool = False

    # API key for target foundation models (SAM 3.1, Muse Spark, Muse Voice)
    # Read from environment only; NEVER logged or returned in API responses
    MODEL_API_KEY: str = ""
    META_API_KEY: str = ""
    META_BASE_URL: str = "https://api.meta.ai/v1"

    # Official pricing rates from dev.meta.ai/docs/pricing-rate-limits
    # SAM image: $2.50 / 1k ($0.0025 / img)
    # SAM video: $0.20 / 1k frames ($0.0002 / frame, min 50 frames)
    # Spark standard: $1.25 in / $4.25 out per 1M tokens ($0.00125/1k in, $0.00425/1k out)
    # Voice: $0.18 / hour ($0.003 / min)
    PRICE_SAM_PER_IMAGE_USD: float = 0.0025
    PRICE_SAM_VIDEO_PER_FRAME_USD: float = 0.0002
    PRICE_MUSE_SPARK_INPUT_PER_1K_USD: float = 0.00125
    PRICE_MUSE_SPARK_OUTPUT_PER_1K_USD: float = 0.00425
    PRICE_MUSE_VOICE_PER_MIN_USD: float = 0.003

    # Estimated unit prices – mock mode rates for backward compatibility
    UNIT_PRICE_SEGMENTATION: float = 0.002
    UNIT_PRICE_AGENT_INPUT: float = 0.003
    UNIT_PRICE_AGENT_OUTPUT: float = 0.015
    UNIT_PRICE_TRANSCRIPTION: float = 0.006

    # BudgetGuard defaults: $1 per audit, $20 total during dev
    MAX_BUDGET_PER_AUDIT_USD: float = 1.0
    MAX_GLOBAL_BUDGET_USD: float = 20.0

    # Rate limits and flags per dev.meta.ai/docs/pricing-rate-limits
    PROVIDER_RATE_LIMIT_RPM: int = 3000
    SAM_VIDEO_MODE: bool = False

    PROVIDER_REQUEST_TIMEOUT_S: float = 15.0
    PROVIDER_MAX_RETRIES: int = 3
    VIDEO_CONCURRENCY_LIMIT: int = 1
    IMAGE_CONCURRENCY_LIMIT: int = 4

    # ── Feature Flags (default ON unless stated, env overridable) ──────────────
    ENABLE_EVIDENCE_MODEL: bool = True
    ENABLE_HYBRID_DETECTORS: bool = True
    ENABLE_TRACKING: bool = True
    ENABLE_ACTIVE_GATHERING: bool = True
    PRIVACY_MODE: bool = True
    ENABLE_HUMAN_REVIEW: bool = True
    ENABLE_TRACE_OBSERVABILITY: bool = True
    ENABLE_EVIDENCE_BUNDLE: bool = True
    ENABLE_FIX_PLAN: bool = True
    ENABLE_SITES: bool = True
    ENABLE_NATURAL_LANGUAGE_CHECKLIST: bool = True
    ENABLE_STRUCTURED_VOICE_NOTES: bool = True
    ENABLE_ESCALATION_CASCADE: bool = False  # default OFF per WP16
    ESCALATION_MODEL: str | None = None

    # Reasoning effort for Muse Spark (dev.meta.ai/docs/reasoning)
    # Values: minimal, low, medium, high, xhigh, max
    # Default "low" to reduce reasoning token cost/latency.
    # Per-call overrides: verdict, verify_presence, extract_note use SPARK_REASONING_EFFORT (low).
    # fix_plan and compile_template use high by default (complex tasks).
    SPARK_REASONING_EFFORT: str = "low"
    SPARK_REASONING_EFFORT_HIGH: str = "high"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [orig.strip() for orig in self.CORS_ORIGINS.split(",") if orig.strip()]

    def ensure_dirs(self) -> None:
        """Create required data directories on startup."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "audits").mkdir(exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton – import this everywhere."""
    return Settings()
