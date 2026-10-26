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
) -> CostLog:
    """
    Record a provider usage row into the cost_log table with estimated cost.
    """
    est_cost = calculate_estimated_cost(operation, units)
    entry = CostLog(
        audit_id=audit_id,
        provider=provider,
        operation=operation,
        units=float(units),
        est_cost_usd=est_cost,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_audit_cost_summary(session: Session, audit_id: str) -> dict[str, Any]:
    """
    Summarize provider calls and estimated cost for a given audit.
    """
    logs = session.exec(select(CostLog).where(CostLog.audit_id == audit_id)).all()
    total_calls = len(logs)
    total_cost_usd = round(sum(l.est_cost_usd for l in logs), 4)

    by_provider: dict[str, dict[str, Any]] = {}
    for entry in logs:
        if entry.provider not in by_provider:
            by_provider[entry.provider] = {"calls": 0, "units": 0.0, "cost_usd": 0.0}
        by_provider[entry.provider]["calls"] += 1
        by_provider[entry.provider]["units"] += entry.units
        by_provider[entry.provider]["cost_usd"] = round(
            by_provider[entry.provider]["cost_usd"] + entry.est_cost_usd, 4
        )

    return {
        "audit_id": audit_id,
        "total_calls": total_calls,
        "total_cost_usd": total_cost_usd,
        "by_provider": by_provider,
    }
