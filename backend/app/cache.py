"""Caching layer for provider results based on frame hash, provider name, and prompt."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from sqlmodel import Session, select

from app.models import CacheEntry


@dataclass
class CacheReport:
    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return (self.hits / self.total) if self.total > 0 else 0.0


def compute_cache_key(
    frame_hash_or_bytes: str | bytes,
    provider: str,
    prompt: str,
    provider_version: str = "1.0.0",
    scenario_hash: str = "",
) -> str:
    """
    Generate deterministic cache key incorporating frame hash, provider name,
    prompt, provider version, and scenario hash:
    key = sha256(frame_identifier + ":" + provider + ":" + prompt + ":" + provider_version + ":" + scenario_hash)
    """
    if isinstance(frame_hash_or_bytes, bytes):
        frame_id = hashlib.sha256(frame_hash_or_bytes).hexdigest()
    else:
        frame_id = str(frame_hash_or_bytes)

    raw = (
        f"{frame_id}:"
        f"{provider.strip().lower()}:"
        f"{prompt.strip().lower()}:"
        f"{provider_version.strip()}:"
        f"{scenario_hash.strip()}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clear_cache_entries(session: Session) -> int:
    """Delete all entries from the cache_entry table."""
    from sqlmodel import delete
    result = session.exec(delete(CacheEntry))
    session.commit()
    return getattr(result, "rowcount", 0)


def get_cached_result(session: Session, key: str, report: CacheReport | None = None) -> Any | None:
    """
    Look up cached provider result by key.
    Updates CacheReport if provided.
    """
    entry = session.exec(select(CacheEntry).where(CacheEntry.key == key)).first()
    if entry is not None:
        if report is not None:
            report.hits += 1
        return json.loads(entry.result_json)

    if report is not None:
        report.misses += 1
    return None


def set_cached_result(
    session: Session,
    key: str,
    provider: str,
    prompt: str,
    result: Any,
) -> CacheEntry:
    """
    Store or update provider result in the cache table.
    """
    serialized = json.dumps(result)
    existing = session.exec(select(CacheEntry).where(CacheEntry.key == key)).first()
    if existing:
        existing.result_json = serialized
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_entry = CacheEntry(
        key=key,
        provider=provider,
        prompt=prompt,
        result_json=serialized,
    )
    session.add(new_entry)
    session.commit()
    session.refresh(new_entry)
    return new_entry
