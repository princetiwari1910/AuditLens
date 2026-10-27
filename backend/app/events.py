"""Server-Sent Events (SSE) manager and persistent JSONL event replay."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import json
import logging
from pathlib import Path
import time
from typing import Any, AsyncGenerator

from app.storage import get_audit_dir

logger = logging.getLogger("auditlens.events")


class EventStreamManager:
    """
    Manages live SSE subscriber queues per audit and persists events to events.jsonl.
    Allows late-joining clients to replay the full audit history before receiving live events.
    Thread-safe emission using loop.call_soon_threadsafe.
    """

    def __init__(self) -> None:
        # audit_id -> set of (asyncio.Queue, asyncio.AbstractEventLoop)
        self._subscribers: dict[str, set[tuple[asyncio.Queue, asyncio.AbstractEventLoop]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    def get_events_file(self, audit_id: str) -> Path:
        return get_audit_dir(audit_id) / "events.jsonl"

    def read_history(self, audit_id: str) -> list[dict[str, Any]]:
        """Read all historical events recorded for this audit from disk."""
        events_file = self.get_events_file(audit_id)
        if not events_file.exists():
            return []

        events = []
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return events

    def emit(self, event: dict[str, Any]) -> None:
        """
        Record event to events.jsonl and broadcast to all connected subscriber queues.
        Thread-safe and synchronous callable suitable for agent runner callbacks.
        """
        audit_id = event.get("audit_id", "")
        if not audit_id:
            return

        if not event.get("ts"):
            event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 1. Append to disk (JSONL)
        events_file = self.get_events_file(audit_id)
        events_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as exc:
            logger.error("Failed to append event to %s: %s", events_file, exc)

        # 2. Dispatch to live async queues in a thread-safe manner
        if audit_id in self._subscribers:
            for q, loop in list(self._subscribers[audit_id]):
                try:
                    if loop.is_running():
                        loop.call_soon_threadsafe(q.put_nowait, event)
                    else:
                        q.put_nowait(event)
                except Exception as exc:
                    logger.debug("Could not deliver event to subscriber queue: %s", exc)

    async def subscribe(self, audit_id: str, session: Any = None) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator yielding historical events followed by live streamed events.
        Automatically unregisters on client disconnect.
        Guarantees keep-alive pings every 10-15s and a final event on completion/failure.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        sub_tuple = (queue, loop)

        # Register queue before reading history so no live events are missed during disk read
        async with self._lock:
            self._subscribers[audit_id].add(sub_tuple)

        seen_signatures: set[str] = set()

        try:
            # 1. Replay past events from disk
            history = self.read_history(audit_id)
            has_terminal = False

            for past_evt in history:
                sig = f"{past_evt.get('type')}:{past_evt.get('ts')}:{json.dumps(past_evt.get('payload', {}), sort_keys=True)}"
                seen_signatures.add(sig)
                yield past_evt
                if past_evt.get("type") in ("audit_completed", "error"):
                    has_terminal = True
                    return

            # 2. Check if DB already shows audit as completed or failed without a recorded terminal event
            if session is not None and not has_terminal:
                from app.models import Audit, AuditStatus
                audit = session.get(Audit, audit_id)
                if audit:
                    if audit.status == AuditStatus.COMPLETED.value:
                        summary = json.loads(audit.summary_json) if audit.summary_json else {}
                        term_event = {
                            "type": "audit_completed",
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "audit_id": audit_id,
                            "payload": {"summary": summary, "recovered": True},
                        }
                        self.emit(term_event)
                        yield term_event
                        return
                    elif audit.status == AuditStatus.FAILED.value:
                        term_event = {
                            "type": "error",
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "audit_id": audit_id,
                            "payload": {"error": audit.error or "Audit processing failed", "recovered": True},
                        }
                        self.emit(term_event)
                        yield term_event
                        return

            # 3. Stream live events
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=12.0)
                    sig = f"{event.get('type')}:{event.get('ts')}:{json.dumps(event.get('payload', {}), sort_keys=True)}"
                    if sig in seen_signatures:
                        continue
                    seen_signatures.add(sig)

                    yield event
                    if event.get("type") in ("audit_completed", "error"):
                        break
                except asyncio.TimeoutError:
                    # Keep-alive ping every 12 seconds
                    yield {
                        "type": "ping",
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "audit_id": audit_id,
                        "payload": {},
                    }

        finally:
            async with self._lock:
                if audit_id in self._subscribers and sub_tuple in self._subscribers[audit_id]:
                    self._subscribers[audit_id].remove(sub_tuple)


# Global singleton manager
event_manager = EventStreamManager()
