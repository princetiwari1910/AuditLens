"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration – every value has a safe default for local dev."""

    # Provider mode: "mock" or "meta"
    PROVIDER_MODE: str = "mock"

    # File storage root
    DATA_DIR: Path = Path("./data")

    # Upload limits
    MAX_UPLOAD_MB: int = 200

    # Frame sampling
    FRAME_FPS: int = 1

    # Rule evaluation
    MIN_CONFIDENCE_PASS: float = 0.6

    # Meta API (used only when PROVIDER_MODE == "meta")
    META_API_KEY: str = ""      # TODO(meta): set from Meta developer portal
    META_BASE_URL: str = ""     # TODO(meta): set from official docs

    # Estimated unit prices – placeholders until official pricing is known
    # TODO(meta): update with real pricing from dev.meta.ai/docs
    UNIT_PRICE_SEGMENTATION: float = 0.002   # per image
    UNIT_PRICE_AGENT_INPUT: float = 0.003    # per 1K input tokens
    UNIT_PRICE_AGENT_OUTPUT: float = 0.015   # per 1K output tokens
    UNIT_PRICE_TRANSCRIPTION: float = 0.006  # per minute of audio

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    def ensure_dirs(self) -> None:
        """Create required data directories on startup."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "audits").mkdir(exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton – import this everywhere."""
    return Settings()
