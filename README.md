# AuditLens

**Evidence-backed safety pre-audit from walkthrough videos.**

Upload a phone walkthrough video or photos of a room, workshop, or lab. Choose a safety checklist or type your own rule. Receive an evidence-backed audit report with bounding-box overlays, optical measurements, confidence scores, and plain-language fixes.

**Disclaimer:** AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Always verify against local regulations and a qualified inspector.

---

## 🚀 Quick Start

### Mock mode (no API key required — recommended for first run)

```bash
make setup
make dev
```

Open [http://localhost:5173](http://localhost:5173). Click **Launch Guided Demo** for an instant replay audit with realistic timeline events, bounding-box overlays, and verified evidence.

### Live mode (with Meta API key)

```bash
export MODEL_API_KEY="your_key"
export PROVIDER_MODE=meta
make dev
```

---

## 📦 How Meta Models Are Used

| Model | Job | Input | Output |
|---|---|---|---|
| **SAM 3.1** | Object detection & segmentation (bounding boxes + masks) | Frame image + noun-phrase prompt (max 5 words) | Normalized box `[x,y,w,h]`, binary mask (one-bit RLE), confidence score |
| **Muse Spark** | Rule verdicts, fix-action plans, template compilation, voice-note structuring | Rule description + keyframe images + cited frame IDs | `{status: "pass"\|"fail"\|"unsure", reason, cited_frame_ids[], confidence}`, structured fix plan or template JSON |
| **Muse Voice Transcribe** | Audio transcription, turn-level timestamps | Audio file (up to 25 MB) | Full text, language, segments with start/end times, turns with speaker labels |

All model calls go through the **BudgetGuard** (`$5 per audit, $100 global cap`) with retry logic (429/5xx with Retry-After, 400 never retried) and concurrency limits (1 video, 4 images).

---

## 🏠 Architecture

```
┌──────────────────────────── Browser (React + TypeScript) ────────────────────────────┐
│ Home → Capture (Voice + Video) → Processing (SSE stream) → Report → Compare / Sites   │
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
│                   ├─ privacy.py       best-effort person blurring on stored frames │
│                   ├─ cache.py         hash = sha256(frame)+prompt+provider           │
│                   ├─ Providers (Contract-isolated)                                   │
│                   │    ├─ Segmenter   (MockSegmenter, MetaSegmenter)                   │
│                   │    ├─ Reasoner    (MockReasoner, MetaReasoner)                     │
│                   │    └─ Transcriber (MockTranscriber, MetaTranscriber)                   │
│                   ├─ tracking.py      IoU object tracker & temporal consensus        │
│                   ├─ escalation.py    active evidence gathering (2x2 tiles → spark) │
│                   ├─ concept_val.py   rejects conjunctions, negation, spatial words  │
│                   ├─ trace.py         observability spans (latency, cost, cache hit) │
│                   ├─ bundle.py        integrity check bundle (manifest hashes)       │
│                   └─ costlog.py       cost tracking & model telemetry                │
│  Storage: SQLite (SQLModel) + persistent files under ./data/audits/{id}/             │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎛️ Modes

| Mode | Env | Description |
|---|---|---|
| **Mock** | `PROVIDER_MODE=mock` (default) | Deterministic scenarios from `demo_room.json`. All findings stamped `MOCK`. Zero network calls. |
| **Recorded** | `DEMO_REPLAY=1` | Replays recorded fixture replays with realistic timing. Zero network calls. Prominent **RECORDED RUN** badge. |
| **Live** | `PROVIDER_MODE=meta` + `MODEL_API_KEY` | Calls real Meta Foundation Model APIs (SAM 3.1, Muse Spark, Muse Voice). Full production mode. |

**Health endpoint** `/api/health` shows `provider_mode` and `demo_mode` — never any key material.

---

## 📊 Evaluation

Run the benchmark harness to compare Full Pipeline vs Vision-Chat Baseline:

```bash
# Both modes (default)
eval/run_eval.py

# Pipeline only
eval/run_eval.py --mode pipeline

# Baseline only
eval/run_eval.py --mode baseline

# Abort if cost exceeds $X
eval/run_eval.py --max-cost 5.0
```

Results are written to `eval/results.md` with:

- Precision, recall and F1 per rule
- Unsure rate (needs review)
- Cost and latency per clip
- Stamped with provider mode, model IDs and date

**Mock mode guard:** evaluation refuses to run unless `--allow-mock` is passed, and stamps `"SIMULATED, NOT A RESULT"`.

---

## ⚠️ System Limitations

1. **Assistive pre-audit only** — highlights potential violations and points inspectors to video timestamps; does not constitute certified regulatory sign-off or replace licensed safety inspectors.
2. **Field-of-view & occlusion** — only assesses visible evidence captured in the walkthrough video; items concealed behind doors, cabinets, or passing personnel cannot be analyzed.
3. **Lighting & motion blur** — low-light or rapid phone panning introduces motion blur; severe blur results in `unsure` ("Needs Review") status.
4. **Scale calibration for measurement** — distance/clearance measurements require an optical scale reference (e.g., A4 paper on floor) to calibrate pixel-to-meter ratios.
5. **Audio-visual temporal window** — voice notes associated with visual findings within ±5 seconds of recorded timestamp.
6. **Redaction & privacy** — stored frames and exported evidence are blurred (best effort). The original upload is kept for playback and frames are sent to the model API before blurring. **AuditLens is never described as privacy-safe.**
7. **Evidence bundle integrity** — downloaded bundle is an integrity check (hashes in a manifest), not a digital signature or legal evidence.

---

## 🔌 Connecting Real Meta Providers

1. Sign up at [dev.meta.ai](https://dev.meta.ai) and obtain your API key.
2. Add to `.env` (gitignored):
   ```bash
   MODEL_API_KEY="your_key"
   PROVIDER_MODE=meta
   ```
3. Supported models:
   - **SAM 3.1** — visual grounding & segmentation
   - **Muse Spark** — reasoning & tool execution
   - **Muse Voice Transcribe** — speech-to-text
4. See [`docs/META_INTEGRATION.md`](docs/META_INTEGRATION.md) for endpoint contracts, token budgets, request schemas, and migration steps from mock to production mode.

---

## 📦 Installation & Development

```bash
make setup          # Python venv + frontend deps
make dev            # Start backend (:8000) + frontend (:5173)
make sample-video   # Generate synthetic walkthrough video (25 s)
make test           # Run all 254 backend + frontend tests
make lint           # Typecheck + production build
```

**Test counts:** 254 backend tests (all milestones WP1–WP16), 49 frontend unit tests.

---

## 📂 Repository Structure

```
auditlens/
├── backend/          # FastAPI application (Python 3.11)
├── frontend/         # React + TypeScript + Vite + Tailwind
├── eval/             # Evaluation harness & benchmark tooling
├── data/             # Persistent SQLite + uploaded audit files
├── docs/             # Architecture, decisions, meta integration
├── scripts/          # CLI utilities (make_sample_video, record_demo, etc.)
└── README.md         # You are here
```
