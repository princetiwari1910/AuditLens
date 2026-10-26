"""Server-Sent Events (SSE) manager and persistent JSONL event replay."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, AsyncGenerator

from app.storage import get_audit_dir


class EventStreamManager:
    """
    Manages live SSE subscriber queues per audit and persists events to events.jsonl.
    Allows late-joining clients to replay the full audit history before receiving live events.
    """

    def __init__(self) -> None:
        # audit_id -> set of asyncio.Queue
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
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

        # 1. Append to disk (JSONL)
        events_file = self.get_events_file(audit_id)
        events_file.parent.mkdir(parents=True, exist_ok=True)
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        # 2. Dispatch to live async queues
        if audit_id in self._subscribers:
            for q in list(self._subscribers[audit_id]):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def subscribe(self, audit_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator yielding historical events followed by live streamed events.
        Automatically unregisters on client disconnect.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # First, yield past events from disk
        history = self.read_history(audit_id)
        seen_timestamps = set()
        for past_evt in history:
            # Yield past event
            yield past_evt
            if past_evt.get("type") in ("audit_completed", "error"):
                # Already terminal, stop streaming
                return

        # Register queue for live events
        async with self._lock:
            self._subscribers[audit_id].add(queue)

        try:
            while True:
                # Wait for next live event (with timeout to send keep-alive comments)
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event
                    if event.get("type") in ("audit_completed", "error"):
                        # Terminal event reached
                        break
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield {"type": "ping", "audit_id": audit_id, "payload": {}}
        finally:
            async with self._lock:
                if audit_id in self._subscribers and queue in self._subscribers[audit_id]:
                    self._subscribers[audit_id].remove(queue)


# Global singleton manager
event_manager = EventStreamManager()
