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
│                   ├─ privacy.py       stored frames & exported evidence blur (effort)│
│                   ├─ cache.py         hash = sha256(frame)+prompt+provider           │
│                   ├─ Providers (Contract-isolated)                                   │
│                   │    ├─ Segmenter   (MockSegmenter, RecordReplay, MetaSegmenter)   │
│                   │    ├─ Reasoner    (MockReasoner, RecordReplay, MetaReasoner)     │
│                   │    └─ Transcriber (MockTranscriber, RecordReplay, MetaTranscriber)│
│                   ├─ tracking.py      IoU object tracker & temporal consensus        │
│                   ├─ escalation.py    active evidence gathering (2x2 tiles -> spark) │
│                   ├─ concept_val.py   rejects conjunctions, negation, spatial words  │
│                   ├─ trace.py         observability spans (latency, cost, cache hit) │
│                   ├─ bundle.py        integrity check bundle (manifest hashes)       │
│                   └─ costlog.py       cost tracking & model telemetry                │
│  Storage: SQLite (SQLModel) + persistent files under ./data/audits/{id}/             │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Provider Discipline & Truth

AuditLens enforces strict separation across provider environments:

1. **`mock` (Default)**:
   - Uses deterministic local scenarios (`backend/app/scenarios/`) and synthetic frames.
   - All findings, scores, eval metrics, and trace spans derived from mock mode are permanently stamped **`MOCK`** or **`SIMULATED, NOT A RESULT`** across the API and frontend UI.
   - Never hallucinates fake live API behavior.

2. **`replay`**:
   - Zero network requests. Operates exclusively off recorded response fixtures located in `data/fixtures/`.
   - **Public Deployment Safety:** When `PROVIDER_MODE=replay`, the system **refuses to start any live provider call even if `MODEL_API_KEY` is set**. Any attempt to execute a live Meta call raises an immediate `RuntimeError`.
   - UI and reports prominently display **`RECORDED RUN`** / **`OFFLINE REPLAY`** banners. Replay is an offline testing fallback, never presented as live inspection.

3. **`record`**:
   - Used when authenticated against Meta endpoints (`MODEL_API_KEY`) to persist verified API responses for downstream replay fixtures.

4. **`meta` (Live Meta API Target)**:
   - Targets Meta AI endpoints:
     - Media Segmentation: `sam-3.1` (OpenAI-compatible Responses API, 1-bit PNG / RLE masks)
     - Multimodal Reasoner: `muse-spark` (structured schema outputs, tool calling, fix action plans)
     - Speech-to-Text: `muse-voice-transcribe` (whisper/audio turn transcription)
   - **Status Truth**: Marked **"UNVERIFIED against live API"** until `scripts/smoke_meta.py` passes with a verified `MODEL_API_KEY`.
   - Safety: Contributor and beta models (e.g. `-contributor`) are strictly rejected. No plaintext keys are ever logged or checked into git.

---

## Redaction & Privacy Notice

> [!WARNING]
> **Stored frames and exported evidence are blurred (best effort). The original upload is kept for playback and frames are sent to the model before blurring.**
> AuditLens is **never** described as privacy-safe.

- Blurring is applied in-memory via OpenCV Gaussian blur over detected person bounding boxes and masks.
- Missed object detections mean missed blurring.
- The raw walkthrough upload video is stored locally in the audit directory to enable playback in the audit viewer.
- Keyframe frames sampled for AI vision inspection are transmitted to foundation models before local redaction occurs.

---

## Evidence Bundle Integrity

> [!NOTE]
> The evidence bundle (`GET /api/audits/{id}/bundle`) is an **integrity check (hashes in a manifest), not a digital signature and not legal evidence**.

- Packages audit artifacts into a standard ZIP archive: `report.json`, `trace.json`, `audit_log.json`, `frames/`, `overlays/`, and `manifest.json`.
- `manifest.json` tabulates SHA-256 cryptographic digests for every bundled file and records a root `manifest_hash`.
- Verified using `python scripts/verify_bundle.py <bundle.zip>`.
- Does **not** certify statutory, regulatory, or OSHA/NFPA legal compliance.

---

## Share Links & Read-Only Confinement

- **Single-Audit Confinement:** A share token (`/api/share/{token}`) is cryptographically bound to its specific audit ID (`ShareToken.token_hash = sha256(token)`).
- **No Cross-Audit Access:** A share token can only read its own audit record. Attempting to use a token to query another audit (`GET /api/audits/{other_id}?token={token}`) returns `HTTP 403 Forbidden`.
- **Zero Write/Review Surface:** Share links expose **no** write, upload, cancel, or human review endpoints. Calling modification methods on `/api/share/{token}` yields `HTTP 405 Method Not Allowed` or `HTTP 404 Not Found`.

---

## Feature Flags & Defaults (`backend/app/config.py`)

Every capability in AuditLens is governed by an explicit feature flag in `app/config.py` with environment variable override support:

| Feature Flag | Default | Description |
|---|---|---|
| `ENABLE_EVIDENCE_MODEL` | `True` | Structured `EvidenceItem` tracking, strength tiers (`mask_backed`, `model_attested`, `voice_note`), and decision policy |
| `ENABLE_HYBRID_DETECTORS` | `True` | Hybrid rule detectors (`sam_then_spark`, `spark_vision`, `sam`) |
| `ENABLE_TRACKING` | `True` | Keyframe IoU object tracking across time, recovering single tracks across flicker and computing stability |
| `ENABLE_ACTIVE_GATHERING` | `True` | Bounded agentic escalation loop ($2\times 2$ zoom tiles $\to \pm 2\text{s}$ neighbor keyframes $\to$ Spark verification; max 3 steps) |
| `PRIVACY_MODE` | `True` | Best-effort person blurring on stored keyframes and overlays |
| `ENABLE_HUMAN_REVIEW` | `True` | Review queue endpoints and append-only `AuditLog` table for human auditor sign-offs |
| `ENABLE_TRACE_OBSERVABILITY` | `True` | Detailed per-stage execution spans in `AuditSpan` (latency, estimated cost, cache hits) |
| `ENABLE_EVIDENCE_BUNDLE` | `True` | Generation of verifiable ZIP archive with SHA-256 manifest integrity check |
| `ENABLE_FIX_PLAN` | `True` | Grounded fix action plan generation (`FixAction` schema) |
| `ENABLE_SITES` | `True` | Multi-audit facility/site entities and longitudinal safety compliance trends |
| `ENABLE_NATURAL_LANGUAGE_CHECKLIST` | `True` | Natural language rule compilation rejecting conjunctions, spatial words, and negation |
| `ENABLE_STRUCTURED_VOICE_NOTES` | `True` | Auditor voice memo transcription with structured location/severity extraction and $\pm 5\text{s}$ finding association |
| `ENABLE_ESCALATION_CASCADE` | **`False`** | Optional cascade retrying unsure verdicts with high-capacity model (e.g. `muse-wonder-1.0`); **must default to false** |
| `ESCALATION_MODEL` | `None` | Model ID for escalation cascade (must never contain `-contributor`) |
| `DEMO_REPLAY` | `False` | Replay recorded audit fixtures with realistic event timing if live API is unavailable |
| `SAM_VIDEO_MODE` | `False` | SAM 3.1 video segmentation mode (requires minimum 50 frames per request) |

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
