# AuditLens

> Safety audits from walkthrough videos — an assistive pre-audit tool.

Upload a phone walkthrough video (or photos) of a room, workshop, or lab.
Choose a safety checklist or write your own rules. Receive an evidence-backed
audit report with findings, overlays, confidence scores, measurements, and
plain-language fixes.

**⚠️ Disclaimer:** AuditLens is an assistive pre-audit tool. It does not certify
legal compliance. Verify against local regulations and a qualified inspector.

## Quick Start

```bash
# Prerequisites: Python 3.11+, Node 18+, ffmpeg
# brew install ffmpeg  (if not installed)

make setup   # creates venv, installs deps, copies .env
make dev     # starts backend (:8000) and frontend (:5173)
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

## Commands

| Command              | Description                           |
| -------------------- | ------------------------------------- |
| `make setup`         | Install all dependencies              |
| `make dev`           | Start both servers                    |
| `make test`          | Run backend tests                     |
| `make lint`          | TypeScript type-check                 |
| `make sample-video`  | Generate a synthetic test video       |
| `make clean`         | Remove venv, node_modules, data       |

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Current Phase: Mock Mode

All AI providers return deterministic mock data. No API key is needed.
See [docs/META_INTEGRATION.md](docs/META_INTEGRATION.md) for the plan to
integrate real providers.

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLModel + SQLite, OpenCV (headless)
- **Frontend:** React + Vite + TypeScript, Tailwind CSS, TanStack Query

## License

Hackathon project — Meta Global AI Developer Hackathon.
