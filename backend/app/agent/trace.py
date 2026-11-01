"""Span-based execution tracing and observability for AuditLens audits (WP6)."""

from __future__ import annotations

import json
import logging
from typing import Any
from sqlmodel import Session, select

from app.config import get_settings
from app.models import Audit, AuditSpan

logger = logging.getLogger(__name__)


def record_span(
    session: Session | None,
    audit_id: str,
    stage: str,
    model: str = "",
    concept: str | None = None,
    latency_ms: int = 0,
    cost_usd: float = 0.0,
    cache_hit: bool = False,
    retries: int = 0,
    step_reason: str = "",
    simulated: bool | None = None,
) -> AuditSpan | None:
    """Record an individual audit execution span into the database."""
    if not audit_id or session is None:
        return None

    settings = get_settings()
    if not getattr(settings, "ENABLE_TRACE_OBSERVABILITY", True):
        return None

    if simulated is None:
        simulated = (settings.PROVIDER_MODE == "mock")

    span = AuditSpan(
        audit_id=audit_id,
        stage=stage,
        model=model,
        concept=concept,
        latency_ms=int(latency_ms),
        cost_usd=round(float(cost_usd), 6),
        cache_hit=cache_hit,
        retries=int(retries),
        step_reason=step_reason,
        simulated=simulated,
    )
    try:
        session.add(span)
        session.commit()
        session.refresh(span)
        return span
    except Exception as exc:
        logger.warning("Failed to record trace span: %s", exc)
        return None


def get_audit_trace(session: Session, audit_id: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retrieve all execution spans and aggregated totals for an audit."""
    settings = get_settings()
    spans = session.exec(
        select(AuditSpan).where(AuditSpan.audit_id == audit_id).order_by(AuditSpan.id.asc())
    ).all()

    total_cost = round(sum(s.cost_usd for s in spans), 4)
    total_latency = sum(s.latency_ms for s in spans)
    cache_hits = sum(1 for s in spans if s.cache_hit)

    if summary is None:
        audit = session.get(Audit, audit_id)
        if audit and audit.summary_json:
            try:
                summary = json.loads(audit.summary_json)
            except Exception:
                summary = {}
        else:
            summary = {}

    frames_analyzed = summary.get("frames_analyzed", 0) if summary else 0
    frames_considered = summary.get("frames_considered", 0) if summary else 0
    if frames_considered == 0 and frames_analyzed > 0:
        frames_considered = frames_analyzed
    calls_saved_by_keyframes = max(0, frames_considered - frames_analyzed)

    return {
        "audit_id": audit_id,
        "spans": [
            {
                "id": s.id,
                "stage": s.stage,
                "model": s.model,
                "concept": s.concept,
                "latency_ms": s.latency_ms,
                "cost_usd": s.cost_usd,
                "cache_hit": s.cache_hit,
                "retries": s.retries,
                "step_reason": s.step_reason,
                "simulated": bool(getattr(s, "simulated", False)),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in spans
        ],
        "totals": {
            "total_spans": len(spans),
            "total_latency_ms": total_latency,
            "total_cost_usd": total_cost,
            "budget_cap_usd": float(settings.MAX_BUDGET_PER_AUDIT_USD),
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / len(spans), 2) if spans else 0.0,
            "calls_saved_by_cache": cache_hits,
            "frames_considered": frames_considered,
            "frames_analyzed": frames_analyzed,
            "frames_saved_by_selection": calls_saved_by_keyframes,
            "calls_saved_by_keyframes": calls_saved_by_keyframes,
        },
    }
