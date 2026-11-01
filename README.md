# AuditLens

> **Walk through. Get proof. Fix what matters.**  
> An assistive safety pre-audit tool powered by foundation models.

Upload a phone walkthrough video or photos of a room, workshop, or lab. Choose a safety checklist or type your own rule. Receive an evidence-backed audit report with synchronized bounding-box overlays, optical clearance width measurements, confidence scores, and plain-language fixes.

**⚠️ Disclaimer:** AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Always verify against local regulations and a qualified inspector.

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 18+
- `ffmpeg` (`brew install ffmpeg` on macOS, or `apt-get install ffmpeg` on Linux)

```bash
# 1. Setup Python venv and install frontend dependencies
make setup

# 2. Start backend (:8000) and frontend (:5173) concurrently
make dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

- Click **"Launch Guided Demo"** on Home to experience an instant walkthrough in replay mode with realistic timeline events, bounding box overlays, and verified evidence.
- Or click **"Load Demo Audit (Demo Data)"** to run an end-to-end audit with the synthetic video under mock mode in 1 click.

---

## 🛠️ CLI Runner & Evaluation Benchmark

AuditLens can run completely headless from the command line:

```bash
# Generate the synthetic 25-second walkthrough video
make sample-video

# Run full audit from terminal with live event timeline & findings table
backend/.venv/bin/python backend/scripts/run_audit_cli.py --video data/sample_walkthrough.mp4 --template fire_exit_safety

# Run the Precision & Recall evaluation benchmark suite (comparing baseline vs full pipeline)
backend/.venv/bin/python eval/run_eval.py --mode both
```

---

## 🧪 Testing

```bash
# Run all backend pytest unit, smoke, replay, and calibration tests
make test

# Run frontend unit tests (letterbox coordinate projection, formatters, models used panel)
cd frontend && npm test

# TypeScript typecheck & production build
make lint
cd frontend && npm run build
```

---

## 🐳 Production Deployment & Hosting

### Option A: Docker Compose (Quickest)

```bash
docker compose up --build
```
Mounts `./data` to `/data` with persistent SQLite and file uploads, and configures `CORS_ORIGINS=*`.

### Option B: Docker Container

AuditLens includes a production-ready `Dockerfile` with `ffmpeg` and OpenCV native libraries pre-installed.

```bash
# Build Docker container
docker build -t auditlens-backend -f backend/Dockerfile backend/

# Run container with persistent data volume mounted
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  -e CORS_ORIGINS="https://yourdomain.com,http://localhost:5173" \
  -e PROVIDER_MODE=mock \
  --name auditlens-api \
  auditlens-backend
```

### Option C: Demo Recording & Offline Replay Fallback

For reliable offline demonstrations or environments where live AI APIs cannot be reached:

```bash
# Record an audit run to data/fixtures/demo_recording.json
make record-demo

# Run backend with DEMO_REPLAY=1 to replay recorded events with realistic timing
DEMO_REPLAY=1 make backend
```
> [!IMPORTANT]
> The UI explicitly tags replayed executions with a prominent **"Recorded run"** badge. Replay is strictly a fallback and is never presented as live.

### Option B: Reverse Proxy Configuration (Nginx & SSE)

When running behind an Nginx or Cloudflare reverse proxy, disable response buffering so Server-Sent Events (SSE) stream in real time without lag:

```nginx
location /api/audits/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;

    # Critical SSE proxy directives
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
}
```

---

## 🏆 Hackathon Build History & Architecture (Started Oct 27, 2026)

AuditLens was architected and built from scratch starting on **October 27, 2026** during the hackathon window as a complete end-to-end safety pre-audit system:

1. **Provider Discipline & Foundation Model Contracts** (`backend/app/providers/`):
   - Strict typed abstract base classes: `Segmenter` (`SAM 3.1`), `Reasoner` (`Muse Spark`), and `Transcriber` (`Muse Voice Transcribe`).
   - Drop-in `Meta` provider stubs raising clear `NotImplementedError("TODO(meta)...")` pointing to `docs/META_INTEGRATION.md` for live API enablement without changing business logic.
   - Built-in Record/Replay proxy: records live model responses to `data/fixtures/<hash>.json` and replays them deterministically with zero network calls and realistic timing.
   - Provider client hardening: budget guard ($5 per audit, $100 global cap), exponential backoff and jitter retry on 429/5xx, concurrency semaphores (1 video, 4 images), and strict Pydantic JSON schema validation for verdicts.
   - Secure config: `MODEL_API_KEY` read strictly from the environment; never logged, exposed via health endpoints, or checked into git.
2. **Deterministic Evidence-First Rule Engine** (`backend/app/rules/`):
   - 5 core rule evaluators: Presence, Absence, Count, Colocation, and Optical Measurement.
   - **Evidence First Contract:** All findings must originate from measured tool evidence with recorded uncertainty; ungrounded assertions strictly default to `unsure` ("Needs Review").
   - Default phone-ready template `campus_fire_exit_core.json` (4 rules that can be shot on a phone, no measurement required), alongside experimental templates.
3. **Upload Normalization & Quality-Aware Keyframe Selection**:
   - `ffprobe` inspection of uploaded `.mp4` and `.mov` videos.
   - Automatic `ffmpeg` transcode to H.264 mp4 (yuv420p, +faststart, autorotate applied, long edge <= 960px).
   - Quality-aware keyframe selection filtering blurry frames via Laplacian variance, removing near-duplicates, enforcing minimum gap, and capping at 24 keyframes.
4. **Voice Notes & Audio Grounding**:
   - MediaRecorder voice note recording in browser and audio upload endpoint.
   - Synchronized transcription timestamp matching findings within ±5 seconds with audio playback.
5. **Interactive Review & Verification UI** (`frontend/`):
   - Synchronized HTML5 video player with canvas bounding box overlays, letterbox coordinate transformation, and timestamp markers.
   - Before/after audit comparison view (`/compare`) tracking resolved vs new violations.
   - Transparent "Models Used" panel exposing model IDs, provider mode, cost, call count, and uncertainty disclaimers.
   - Exportable print & PDF report.
6. **Evaluation, Calibration & Ground-Truth Tooling** (`eval/` & `/eval`):
   - Keyframe ground-truth labeling CLI (`backend/scripts/label_keyframes.py`) with unified per-frame/per-rule schema (`data/labels/<video_id>.json`).
   - Benchmark evaluation harness (`eval/run_eval.py`) comparing Full Pipeline vs Direct Chat Vision Baseline.
   - Empirical Precision, Recall, F1, Confusion Matrices, and "Needs Review" Abstain Calibration curves.
   - Interactive `/eval` calibration dashboard displaying Reliability (confidence vs accuracy) and Abstain vs Accuracy tradeoff curves.
   - Honest mock mode stamping: prominent "MOCK, NOT A RESULT" banner with comparison deltas hidden until real foundation models are connected.

---

## ⚠️ System Limitations

AuditLens is designed for fast, assistive walkthrough pre-audits. To ensure reliable and safe operation:

1. **Assistive Pre-Audit Only:** AuditLens highlights potential violations and points inspectors to specific video timestamps; it does not constitute a certified regulatory sign-off or replace licensed safety inspectors.
2. **Field-of-View & Occlusion:** The system only assesses visible evidence captured in the walkthrough video. Items concealed behind closed doors, inside cabinets, or blocked by passing personnel cannot be analyzed.
3. **Lighting & Motion Blur:** Low-light environments or rapid phone panning introduce motion blur. While the quality-aware frame selector filters blurry frames, severe blur will result in an `unsure` ("Needs Review") status.
4. **Scale Calibration for Measurement:** Distance and clearance measurements require an optical scale reference (e.g., standard A4 paper placed on the floor) to calibrate pixel-to-meter ratios.
5. **Audio-Visual Temporal Window:** Auditor voice notes are associated with visual findings within a ±5-second window of the recorded timestamp.
6. **Redaction & Privacy Notice:** Stored frames and exported evidence are blurred (best effort). The original upload is kept for playback and frames are sent to the model before blurring. AuditLens is **never** described as privacy-safe.
7. **Evidence Bundle Integrity:** The downloaded evidence bundle (`/api/audits/{id}/bundle`) is an **integrity check (hashes in a manifest), not a digital signature and not legal evidence**.

---

## 🔌 How to Connect Real Meta Providers

AuditLens is prepared for seamless drop-in integration with Meta's developer APIs once credentials are provided:

1. **Obtain API Credentials:**
   Sign up at [dev.meta.ai](https://dev.meta.ai) and obtain your Meta Model API key.

2. **Configure `.env`:**
   Add your key to `.env` (gitignored and never logged):
   ```bash
   MODEL_API_KEY="your_meta_api_key_here"
   PROVIDER_MODE="meta"
   ```

3. **Supported Models:**
   - **Visual Grounding & Segmentation:** SAM 3.1 (`MODEL_ID_SEGMENTATION="SAM 3.1"`)
   - **Reasoning & Tool Execution:** Muse Spark (`MODEL_ID_AGENT="Muse Spark"`)
   - **Multilingual Speech-to-Text:** Muse Voice Transcribe (`MODEL_ID_TRANSCRIPTION="Muse Voice Transcribe"`)

4. **Detailed Integration Guide:**
   See [`docs/META_INTEGRATION.md`](file:///Users/princetiwari19/Documents/AuditLens/docs/META_INTEGRATION.md) for endpoint contracts, token budgets, request schemas, and migration steps from mock to production mode. Provider calls automatically inherit client hardening (request timeouts, exponential backoff with jitter on 429/5xx, semaphores, and budget guards).

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Input ["1. Multimodal Capture"]
        Video["Phone Walkthrough Video (.mp4)"]
        Audio["Inspector Voice Memos (.wav/.webm)"]
    end

    subgraph Sampling ["2. Extraction & Caching"]
        Frames["Keyframe Extraction (OpenCV / ffmpeg)"]
        Cache["Scenario & Prompt Hash Cache (SQLite)"]
    end

    subgraph Providers ["3. Foundation Model Layer (Provider Contract)"]
        SAM["SAM 3.1 Segmenter\n(Masks, Boxes & Clear Width)"]
        Spark["Muse Spark Reasoner\n(Tool Calling & Evidence Assembly)"]
        Voice["Muse Voice Transcriber\n(Hinglish & Multilingual ASR)"]
    end

    subgraph CoreEngine ["4. Evidence-First Rule Engine"]
        Rules["Rule Evaluators\n• Presence & Absence\n• Count & Colocation\n• Optical Measurement"]
        Evidence["Evidence First Guard\n(No Evidence -> 'unsure' / Needs Review)"]
    end

    subgraph Output ["5. Human-in-the-Loop Delivery"]
        SSE["Live SSE Timeline (/api/audits/{id}/events)"]
        Report["Interactive Report & PDF (/audits/{id})"]
        EvalDash["Calibration & Benchmark Dashboard (/eval)"]
    end

    Video --> Frames
    Audio --> Voice
    Frames --> Cache
    Cache --> SAM
    SAM --> Rules
    Voice --> Rules
    Spark --> Rules
    Rules --> Evidence
    Evidence --> SSE
    SSE --> Report
    Evidence --> EvalDash
```

```
+---------------------------------------------------------------------------------------------------+
|                                      AUDITLENS ARCHITECTURE                                       |
+---------------------------------------------------------------------------------------------------+
|  [Phone Video / Voice Memos] ---> [Keyframe Sampling (1 fps)] + [Scenario Cache (SQLite)]         |
|                                                     |                                             |
|                                                     v                                             |
|  [FOUNDATION MODEL CONTRACTS]                                                                     |
|    - SAM 3.1: Segmenter (prompts -> bounding boxes, masks, optical width)                         |
|    - Muse Spark: Reasoner (rule + visual evidence -> structured verdict)                          |
|    - Muse Voice: Transcriber (voice notes -> timestamped transcript turns)                        |
|                                                     |                                             |
|                                                     v                                             |
|  [EVIDENCE-FIRST RULE ENGINE]                                                                     |
|    - Five Rule Evaluators (Presence, Absence, Count, Colocation, Measurement)                     |
|    - Evidence Guard: Findings require tool measurements; missing evidence -> "unsure"            |
|                                                     |                                             |
|                                                     v                                             |
|  [DELIVERY & CALIBRATION]                                                                         |
|    - Real-time Server-Sent Events (SSE) Agent Timeline                                            |
|    - Interactive Video Player with Responsive Letterbox Overlays & PDF Export                     |
|    - Evaluation Harness: Precision/Recall/F1 + Reliability & Abstain Calibration (/eval)          |
+---------------------------------------------------------------------------------------------------+
```

---



## 📄 Makefile Commands

| Command | Description |
|---|---|
| `make setup` | Create virtualenv, install pip & npm packages, setup `.env` |
| `make dev` | Start backend (:8000) and frontend (:5173) concurrently |
| `make test` | Run all 61 backend pytest unit, smoke, replay, and calibration tests |
| `make lint` | Run TypeScript typecheck (`tsc --noEmit`) |
| `make sample-video` | Generate the 25-second synthetic walkthrough video |
| `make record-demo` | Capture completed audit events & findings to fixtures |
| `make clean` | Remove `.venv`, `node_modules`, and local build artifacts |

---

## ⚖️ License & Hackathon Context

Built for the **Meta Global AI Developer Hackathon**.
Assisting workplace facility managers and lab technicians perform rapid pre-audits between official inspections.
