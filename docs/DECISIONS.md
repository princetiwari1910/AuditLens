# Design Decisions

## 2024-XX-XX: Mock-first architecture

**Context:** We don't have Meta API access yet.
**Decision:** Build the full app against provider interfaces. Mock implementations
return deterministic data from a scenario file. The agent runner is a
deterministic planner that exercises the same tool interface a real LLM would.
**Consequence:** When the API arrives, we implement `providers/meta.py` without
touching any other code.

## 2024-XX-XX: SQLite for storage

**Context:** Hackathon scope, single user, no concurrent writes.
**Decision:** SQLite via SQLModel. Simple, no setup, file-based.
**Consequence:** Easy to test; can migrate to PostgreSQL later if needed.

## 2024-XX-XX: SSE for real-time updates

**Context:** The audit runs 10–30 seconds. The user needs progress feedback.
**Decision:** Server-Sent Events over `GET /api/audits/{id}/events`.
**Consequence:** Simpler than WebSocket. One-directional is sufficient.
