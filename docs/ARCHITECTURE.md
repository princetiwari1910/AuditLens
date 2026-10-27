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
│                   │    ├─ SegmentationProvider  (mock now, SAM 3.1 later)│
│                   │    ├─ AgentProvider         (mock now, Muse Spark)   │
│                   │    └─ TranscriptionProvider (mock now, Muse Voice)   │
│                   ├─ agent/tools.py   plain Python tools + JSON schemas  │
│                   ├─ agent/rules.py   rule evaluation                    │
│                   ├─ agent/measure.py geometry + scale (A4 0.297m)       │
│                   ├─ agent/compare.py re-audit comparison                │
│                   └─ costlog.py       every provider call is logged      │
│  Storage: SQLite (SQLModel) + files under ./data/audits/{id}/            │
└──────────────────────────────────────────────────────────────────────────┘
```

## Audit Flow

1. `POST /api/audits` — upload video or photos, validate file type and 90-second duration limit, create audit (status=queued), start background job.
2. **Frame sampling** — extract frames at 1 fps with OpenCV, compute SHA-256 hash per frame.
3. **Rule evaluation** — for each rule, call tools: `list_rules`, `find_objects`, `measure_clear_width`, `check_colocation`.
4. **Voice notes** — transcribe and attach to nearest finding by timestamp as extra evidence (`"voice_note"`).
5. **Overlay generation** — render annotated evidence images with OpenCV (bounding boxes, polygons, status labels).
6. **Summary score** — compute weighted safety compliance score (0–100) and counts by status/severity.
7. **SSE events** — stream progress in real time (`audit_started` -> `frames_sampled` -> `tool_call` -> `tool_result` -> `finding_recorded` -> `audit_completed`).

## Provider Target Specifications

| Provider Interface | Mock Implementation | Real Target (Phase 2) |
|---|---|---|
| `SegmentationProvider` | `scenarios/demo_room.json` + seeded fallback | **SAM 3.1** |
| `AgentProvider` | Deterministic ToolRegistry planner | **Muse Spark** (tool-calling over ToolRegistry) |
| `TranscriptionProvider` | Hinglish canned segments | **Muse Voice Transcribe** |

## Database Schema (SQLModel + SQLite)

- `audit`: id (UUID), template_id, custom_rules_json, status, created_at, video_path, duration_s, summary_json, error
- `frame`: id, audit_id, idx, timestamp_s, path, sha256
- `cache_entry`: key (sha256), provider, prompt, result_json, created_at
- `finding`: id, audit_id, rule_id, status, confidence, timestamp_s, frame_idx, overlay_path, measurement_json, rationale, fix_text, severity, sources_json
- `voice_note`: id, audit_id, timestamp_s, audio_path, transcript, language
- `cost_log`: id, audit_id, provider, operation, units, est_cost_usd, created_at
