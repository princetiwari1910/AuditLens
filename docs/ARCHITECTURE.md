# AuditLens — Architecture

## System Diagram

```
┌──────────────────────────── Browser (React) ────────────────────────────┐
│ Home → Capture → Processing (SSE timeline) → Report → Compare          │
│  OverlayCanvas draws boxes/polygons on <video> synced to currentTime    │
└───────────────▲──────────────────────────────┬──────────────────────────┘
                │ JSON / SSE                     │ multipart upload
┌───────────────┴──────────────────────────────▼──────────────────────────┐
│ FastAPI backend                                                          │
│  API layer ──► Job runner (background task per audit)                    │
│                   │                                                      │
│                   ├─ frames.py        ffmpeg/OpenCV sample at 1 fps      │
│                   ├─ cache.py         key = sha256(frame)+prompt+provider│
│                   ├─ Providers (interfaces)                              │
│                   │    ├─ SegmentationProvider  (mock now, SAM later)    │
│                   │    ├─ AgentProvider         (mock now, LLM later)    │
│                   │    └─ TranscriptionProvider (mock now, ASR later)    │
│                   ├─ agent/tools.py   plain Python tools + JSON schemas  │
│                   ├─ agent/rules.py   rule evaluation                    │
│                   ├─ agent/measure.py geometry + scale                   │
│                   ├─ agent/compare.py re-audit comparison                │
│                   └─ costlog.py       every provider call is logged      │
│  Storage: SQLite (SQLModel) + files under ./data/audits/{id}/            │
└──────────────────────────────────────────────────────────────────────────┘
```

## Audit Flow

1. `POST /api/audits` — upload video, create audit (status=queued), start background job.
2. **Frame sampling** — extract frames at 1 fps, save as JPEGs.
3. **Rule evaluation** — for each rule, call tools: `find_objects`, `measure`, `check_colocation`, etc.
4. **Voice notes** — transcribe and attach to nearest timestamp.
5. **Overlay generation** — draw bounding boxes / polygons with OpenCV.
6. **Summary** — compute pass/fail/unsure counts and score.
7. **SSE events** — stream progress to the frontend in real time.

## Provider Interfaces

| Provider | Mock | Real (Phase 2) |
|----------|------|-----------------|
| SegmentationProvider | Scenario JSON | Meta SAM |
| AgentProvider | Deterministic planner | Meta LLM tool-calling |
| TranscriptionProvider | Static transcript | Meta ASR |

## Database

SQLite via SQLModel. Tables: `audit`, `frame`, `finding`, `voice_note`, `cache_entry`, `cost_log`.

## Config

All settings via environment variables with sensible defaults. See `.env.example`.
