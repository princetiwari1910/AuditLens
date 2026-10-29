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

- Click **"Load Demo Audit (Demo Data)"** on the top right to run an end-to-end audit with the pre-generated synthetic video in 1 click without uploading any files.

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
# Run all 44 backend pytest tests (rules, cache, cost, evidence-first, API, replay)
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

## 🧠 Architecture & Foundation Model Targets

AuditLens isolates all AI reasoning behind strict interfaces so switching between mock and real execution requires zero refactoring:

| Capability | Interface | Current Mock | Target Foundation Model |
|---|---|---|---|
| **Visual Grounding & Segmentation** | `SegmentationProvider` | `scenarios/demo_room.json` | **SAM 3.1** |
| **Agent Reasoning & Tool Calling** | `AgentProvider` | Deterministic `ToolRegistry` Planner | **Muse Spark** |
| **Audio Speech-to-Text** | `TranscriptionProvider` | Canned Hinglish voice memos | **Muse Voice Transcribe** |

See [docs/META_INTEGRATION.md](docs/META_INTEGRATION.md) for the drop-in integration checklist.

---

## 📄 Makefile Commands

| Command | Description |
|---|---|
| `make setup` | Create virtualenv, install pip & npm packages, setup `.env` |
| `make dev` | Start backend (:8000) and frontend (:5173) concurrently |
| `make test` | Run all 44 backend pytest unit, smoke, and replay tests |
| `make lint` | Run TypeScript typecheck (`tsc --noEmit`) |
| `make sample-video` | Generate the 25-second synthetic walkthrough video |
| `make record-demo` | Capture completed audit events & findings to fixtures |
| `make clean` | Remove `.venv`, `node_modules`, and local build artifacts |

---

## ⚖️ License & Hackathon Context

Built for the **Meta Global AI Developer Hackathon**.
Assisting workplace facility managers and lab technicians perform rapid pre-audits between official inspections.
