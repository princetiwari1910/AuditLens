"""Tests for SSE event replay, keep-alive headers, and guaranteed terminal final events."""

from __future__ import annotations

import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_engine
from app.events import event_manager
from app.main import app
from app.models import Audit, AuditStatus
from app.storage import get_audit_dir


@pytest.fixture
def clean_client(tmp_path, monkeypatch):
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit_event = None

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine()

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    client = TestClient(app)
    yield client, tmp_path

    AppStatus.should_exit_event = None
    reset_engine()
    get_settings.cache_clear()


def test_sse_headers_and_media_type(clean_client):
    """Verify GET /api/audits/{id}/events returns text/event-stream with proxy unbuffering headers."""
    client, tmp_path = clean_client
    settings = get_settings()

    from sqlmodel import Session
    from app.db import engine
    with Session(engine()) as session:
        audit = Audit(template_id="fire_exit_safety", status=AuditStatus.COMPLETED.value)
        session.add(audit)
        session.commit()
        session.refresh(audit)
        audit_id = audit.id

    # Add a mock terminal event
    event_manager.emit({
        "type": "audit_completed",
        "ts": "2026-10-27T10:00:00Z",
        "audit_id": audit_id,
        "payload": {"summary": {"score": 85}},
    })

    with client.stream("GET", f"/api/audits/{audit_id}/events") as resp:
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type
        assert resp.headers.get("cache-control") == "no-cache, no-transform"
        assert resp.headers.get("x-accel-buffering") == "no"
        assert resp.headers.get("access-control-allow-origin") == "*"


def test_sse_event_replay_order(clean_client):
    """Verify that late-connecting subscribers receive full historical events in order."""
    client, tmp_path = clean_client

    from sqlmodel import Session
    from app.db import engine
    with Session(engine()) as session:
        audit = Audit(template_id="fire_exit_safety", status=AuditStatus.PROCESSING.value)
        session.add(audit)
        session.commit()
        session.refresh(audit)
        audit_id = audit.id

    # Emit a sequence of historical events to disk
    historical_events = [
        {"type": "audit_started", "ts": "2026-10-27T10:00:01Z", "audit_id": audit_id, "payload": {}},
        {"type": "frames_sampled", "ts": "2026-10-27T10:00:02Z", "audit_id": audit_id, "payload": {"count": 10}},
        {"type": "tool_call", "ts": "2026-10-27T10:00:03Z", "audit_id": audit_id, "payload": {"tool": "find_objects"}},
        {"type": "audit_completed", "ts": "2026-10-27T10:00:04Z", "audit_id": audit_id, "payload": {"summary": {"score": 90}}},
    ]

    for ev in historical_events:
        event_manager.emit(ev)

    # Late subscriber connects
    received_types = []
    with client.stream("GET", f"/api/audits/{audit_id}/events") as resp:
        for line in resp.iter_lines():
            if line and line.startswith("data:"):
                data_str = line.replace("data:", "").strip()
                parsed = json.loads(data_str)
                received_types.append(parsed.get("type"))
                if parsed.get("type") == "audit_completed":
                    break

    assert received_types == ["audit_started", "frames_sampled", "tool_call", "audit_completed"]


def test_sse_final_event_on_failure(clean_client):
    """Verify that when an audit fails, a final terminal error event is guaranteed in the stream."""
    client, tmp_path = clean_client

    from sqlmodel import Session
    from app.db import engine
    with Session(engine()) as session:
        audit = Audit(
            template_id="fire_exit_safety",
            status=AuditStatus.FAILED.value,
            error="Simulated camera sensor corruption",
        )
        session.add(audit)
        session.commit()
        session.refresh(audit)
        audit_id = audit.id

    # Connect to stream for failed audit where no events were written to events.jsonl
    received_events = []
    with client.stream("GET", f"/api/audits/{audit_id}/events") as resp:
        for line in resp.iter_lines():
            if line and line.startswith("data:"):
                data_str = line.replace("data:", "").strip()
                parsed = json.loads(data_str)
                received_events.append(parsed)
                if parsed.get("type") == "error":
                    break

    assert len(received_events) >= 1
    last_evt = received_events[-1]
    assert last_evt["type"] == "error"
    assert "Simulated camera sensor corruption" in last_evt["payload"].get("error", "")
