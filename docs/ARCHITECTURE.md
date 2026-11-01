# AuditLens — Architecture

## System Diagram

```
┌──────────────────────────── Browser (React / TypeScript) ────────────────────────────┐
│ Home → Capture (Voice + Video) → Processing (SSE stream) → Report → Compare / Sites  │
│  OverlayCanvas: bounding boxes/masks synced to video currentTime                     │
│  EvidenceViewerModal: cited keyframe strip, keyboard navigation, best-frame overlays │
│  ReviewQueuePanel: auditor human-in-the-loop overrides & audit log verification       │
│  TracePage: execution waterfall, model latencies, token costs, cache savings         │
└────────────────────────▲──────────────────────────────┬──────────────────────────────┘
                         │ JSON / SSE                   │ multipart video/audio upload
┌────────────────────────┴──────────────────────────────▼──────────────────────────────┐
│ FastAPI Backend (Python 3.11 + OpenCV + FFmpeg)                                      │
│  API Layer ──► Background Job Runner (per audit)                                     │
│                   │                                                                  │
│                   ├─ keyframes.py     Laplacian sharpness + perceptual deduplication │
│                   ├─ privacy.py       in-memory person blur (unblurred never saved)  │
│                   ├─ cache.py         hash = sha256(frame)+prompt+provider           │
│                   ├─ Providers (Contract-isolated)                                   │
│                   │    ├─ Segmenter   (MockSegmenter, RecordReplay, MetaSegmenter)   │
│                   │    ├─ Reasoner    (MockReasoner, RecordReplay, MetaReasoner)     │
│                   │    └─ Transcriber (MockTranscriber, RecordReplay, MetaTranscriber)│
│                   ├─ tracking.py      IoU object tracker & temporal consensus        │
│                   ├─ escalation.py    active evidence gathering (2x2 tiles -> spark) │
│                   ├─ concept_val.py   rejects conjunctions, negation, spatial words  │
│                   ├─ trace.py         observability spans (latency, cost, cache hit) │
│                   ├─ bundle.py        tamper-evident ZIP evidence bundle with SHA-256│
│                   └─ costlog.py       cost tracking & model telemetry                │
│  Storage: SQLite (SQLModel) + persistent files under ./data/audits/{id}/             │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Provider Discipline & Truth

AuditLens enforces strict separation across three provider environments:

1. **`mock` (Default)**:
   - Uses deterministic local scenarios (`backend/app/scenarios/`) and synthetic frames.
   - All findings, scores, eval metrics, and trace spans derived from mock mode are permanently stamped **`MOCK`** or **`SIMULATED, NOT A RESULT`** across the API and frontend UI.
   - Never hallucinates fake live API behavior.

2. **`replay`**:
   - Zero network requests. Operates exclusively off recorded response fixtures located in `data/fixtures/`.
   - UI and reports prominently display **`RECORDED RUN`** / **`OFFLINE REPLAY`** banners. Replay is an offline testing fallback, never presented as live inspection.

3. **`record`**:
   - Used when authenticated against Meta endpoints (`MODEL_API_KEY`) to persist verified API responses for downstream replay fixtures.

4. **`meta` (Live Meta API Target)**:
   - Targets Meta AI endpoints:
     - Media Segmentation: `sam-3.1` (OpenAI-compatible Responses API, 1-bit PNG / RLE masks)
     - Multimodal Reasoner: `muse-spark` (structured schema outputs, tool calling, fix action plans)
     - Speech-to-Text: `muse-voice-transcribe` (whisper/audio turn transcription)
   - **Status Truth**: Mark everything **"UNVERIFIED against live API"** until `scripts/smoke_meta.py` passes with a verified `MODEL_API_KEY`.
   - Safety: Contributor and beta models (e.g. `-contributor`) are strictly rejected. No plaintext keys are ever logged or checked into git.

---

## Containerized Deployment (Docker & Compose)

### Dockerfile (`backend/Dockerfile`)
- Base image: `python:3.11-slim`
- OS-level dependencies: `ffmpeg`, `libgl1`, `libglib2.0-0`, `libgomp1`, `curl`
- Unbuffered Python execution with standard OpenCV headless bindings (`opencv-python-headless`).
- Volume mount: `/app/data` (or host `./data` mapped to container).
- Health check: Queries `http://localhost:8000/api/health` every 15–30 seconds.

### Docker Compose (`docker-compose.yml`)
```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: auditlens-backend
    ports:
      - "8000:8000"
    environment:
      - DATA_DIR=/data
      - CORS_ORIGINS=*
      - PROVIDER_MODE=mock
      - DEMO_REPLAY=0
      - FRAME_FPS=1
      - MAX_UPLOAD_MB=200
      - MAX_VIDEO_DURATION_S=90
    volumes:
      - ./data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 5s
```

### SSE-Safe Production Streaming
- Server-Sent Events endpoint `GET /api/audits/{id}/events` serves real-time job execution.
- Headers:
  - `Cache-Control: no-cache, no-transform`
  - `X-Accel-Buffering: no` (disables Nginx reverse proxy buffering)
  - `Connection: keep-alive`
  - Automated keep-alive pings transmitted every 15 seconds to prevent client timeout drops.

---

## Database Entities (SQLModel + SQLite)

| Model | Table | Purpose |
|---|---|---|
| `Audit` | `audit` | Core inspection record: template, provider mode, model IDs, summary score, status |
| `Site` | `site` | Physical location entity (e.g. Building A, Lab 4) for longitudinal trend analysis |
| `Frame` | `frame` | Sampled video keyframe path, timestamp, and SHA-256 content digest |
| `Finding` | `finding` | Rule verdict (pass/fail/unsure), confidence, mask overlay, optical measurement, rationale, fix text |
| `VoiceNote` | `voice_note` | Auditor audio walkthrough recordings, transcript, and attached findings |
| `AuditLog` | `audit_log` | Append-only ledger of human review overrides and supervisor sign-offs |
| `AuditSpan` | `audit_span` | Fine-grained telemetry spans: model name, latency ms, token cost, cache hit |
| `ShareToken` | `share_token` | Cryptographic SHA-256 token hash for secure read-only report sharing |
| `CacheEntry` | `cache_entry` | Deterministic model response cache keyed by frame hash + concept |
| `CostLog` | `cost_log` | Per-call invocation tracking and budget guard enforcement |
