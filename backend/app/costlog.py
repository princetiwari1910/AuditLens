"""AuditLens provider call cost logging and tracking."""

from __future__ import annotations

from typing import Any
from sqlmodel import Session, func, select

from app.config import get_settings
from app.models import CostLog


def calculate_estimated_cost(operation: str, units: float) -> float:
    """
    Calculate estimated USD cost using UNIT_PRICE_* placeholders from config.
    NOTE: These are placeholder rates and must be updated once official Meta pricing is released.
    """
    settings = get_settings()
    op = operation.strip().lower()

    if op in ("segmentation", "find_objects", "sam"):
        # units = number of frames processed
        unit_price = settings.UNIT_PRICE_SEGMENTATION
        return round(units * unit_price, 6)

    elif op in ("agent_input", "llm_input"):
        # units = 1K input tokens
        unit_price = settings.UNIT_PRICE_AGENT_INPUT
        return round(units * unit_price, 6)

    elif op in ("agent_output", "llm_output"):
        # units = 1K output tokens
        unit_price = settings.UNIT_PRICE_AGENT_OUTPUT
        return round(units * unit_price, 6)

    elif op in ("transcription", "asr", "audio"):
        # units = minutes of audio
        unit_price = settings.UNIT_PRICE_TRANSCRIPTION
        return round(units * unit_price, 6)

    return 0.0


def log_cost(
    session: Session,
    provider: str,
    operation: str,
    units: float,
    audit_id: str | None = None,
    model_id: str | None = None,
    latency_ms: int = 0,
    cache_hit: bool = False,
) -> CostLog:
    """
    Record a provider usage row into the cost_log table with estimated cost,
    model id, latency, and cache hit metadata.
    """
    settings = get_settings()
    if not model_id:
        prov = provider.strip().lower()
        if "sam" in prov or "seg" in prov:
            model_id = settings.MODEL_ID_SEGMENTATION
        elif "voice" in prov or "trans" in prov or "asr" in prov:
            model_id = settings.MODEL_ID_TRANSCRIPTION
        else:
            model_id = settings.MODEL_ID_AGENT

    est_cost = 0.0 if cache_hit else calculate_estimated_cost(operation, units)
    entry = CostLog(
        audit_id=audit_id,
        provider=provider,
        operation=operation,
        units=float(units),
        est_cost_usd=est_cost,
        model_id=model_id,
        latency_ms=int(latency_ms),
        cache_hit=cache_hit,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_audit_cost_summary(session: Session, audit_id: str) -> dict[str, Any]:
    """
    Summarize provider calls, latency, cache hits, and estimated cost for a given audit.
    Includes explicit evidence fields for segmentation, agent, and transcription models.
    """
    settings = get_settings()
    logs = session.exec(select(CostLog).where(CostLog.audit_id == audit_id)).all()
    total_calls = len(logs)
    total_cost_usd = round(sum(l.est_cost_usd for l in logs), 4)

    # Standard model metadata and plain-English roles
    provider_meta = {
        "segmentation": {
            "name": "Segmentation",
            "model_id": settings.MODEL_ID_SEGMENTATION,
            "role": f"{settings.MODEL_ID_SEGMENTATION}: finds and measures items",
        },
        "agent": {
            "name": "Agent / Reasoning",
            "model_id": settings.MODEL_ID_AGENT,
            "role": f"{settings.MODEL_ID_AGENT}: reasons over rules, dispatches tools, and evaluates evidence",
        },
        "transcription": {
            "name": "Voice Transcription",
            "model_id": settings.MODEL_ID_TRANSCRIPTION,
            "role": f"{settings.MODEL_ID_TRANSCRIPTION}: transcribes audio notes into searchable evidence",
        },
    }

    by_provider: dict[str, dict[str, Any]] = {}
    for prov_key, meta in provider_meta.items():
        by_provider[prov_key] = {
            "name": meta["name"],
            "model_id": meta["model_id"],
            "role": meta["role"],
            "calls": 0,
            "cache_hits": 0,
            "latency_ms": 0,
            "units": 0.0,
            "cost_usd": 0.0,
            "simulated": (settings.PROVIDER_MODE == "mock"),
        }

    for entry in logs:
        prov = entry.provider.lower()
        target_key = "agent"
        if "sam" in prov or "seg" in prov:
            target_key = "segmentation"
        elif "voice" in prov or "trans" in prov or "asr" in prov:
            target_key = "transcription"

        # Also support raw entry.provider key if different from canonical target_key
        # by keeping canonical target_key updated and mirroring if requested
        p = by_provider[target_key]
        p["calls"] += 1
        if entry.cache_hit:
            p["cache_hits"] += 1
        p["latency_ms"] += entry.latency_ms
        p["units"] = round(p["units"] + entry.units, 2)
        p["cost_usd"] = round(p["cost_usd"] + entry.est_cost_usd, 4)
        if entry.model_id:
            p["model_id"] = entry.model_id

        # Also store raw provider key if needed by older tests (e.g. "mock_sam")
        if entry.provider not in by_provider:
            by_provider[entry.provider] = {
                "name": entry.provider,
                "model_id": entry.model_id or p["model_id"],
                "role": p["role"],
                "calls": 0,
                "cache_hits": 0,
                "latency_ms": 0,
                "units": 0.0,
                "cost_usd": 0.0,
                "simulated": (settings.PROVIDER_MODE == "mock"),
            }
        if entry.provider != target_key:
            raw_p = by_provider[entry.provider]
            raw_p["calls"] += 1
            if entry.cache_hit:
                raw_p["cache_hits"] += 1
            raw_p["latency_ms"] += entry.latency_ms
            raw_p["units"] = round(raw_p["units"] + entry.units, 2)
            raw_p["cost_usd"] = round(raw_p["cost_usd"] + entry.est_cost_usd, 4)

    return {
        "audit_id": audit_id,
        "provider_mode": settings.PROVIDER_MODE,
        "total_calls": total_calls,
        "total_cost_usd": total_cost_usd,
        "by_provider": by_provider,
        "models": {
            "segmentation": settings.MODEL_ID_SEGMENTATION,
            "agent": settings.MODEL_ID_AGENT,
            "transcription": settings.MODEL_ID_TRANSCRIPTION,
        },
    }
