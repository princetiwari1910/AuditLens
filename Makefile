.PHONY: setup dev backend frontend test lint clean clear-cache eval sample-video record-demo smoke-ui live-audit

VIDEO ?= ./data/sample_walkthrough.mp4

# ── Setup ────────────────────────────────────────────────────────────────
setup: setup-backend setup-frontend
	@echo "✅  Setup complete. Run 'make dev' to start."

setup-backend:
	cd backend && python3 -m venv .venv && \
		.venv/bin/pip install --upgrade pip && \
		.venv/bin/pip install -r requirements.txt
	cp -n .env.example .env 2>/dev/null || true

setup-frontend:
	cd frontend && npm install

# ── Development ──────────────────────────────────────────────────────────
dev:
	@echo "Starting backend (port 8000) and frontend (port 5173)…"
	$(MAKE) backend & $(MAKE) frontend & wait

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

# ── Quality ──────────────────────────────────────────────────────────────
test:
	cd backend && .venv/bin/pytest tests/ -v

smoke-ui:
	bash scripts/smoke_ui.sh

lint:
	cd frontend && npx tsc --noEmit

eval:
	backend/.venv/bin/python eval/run_eval.py --mode both --allow-mock

# ── Utilities ────────────────────────────────────────────────────────────
live-audit:
	cd backend && PROVIDER_MODE=record .venv/bin/python scripts/run_audit_cli.py --video "$(VIDEO)" --live

sample-video:
	cd backend && .venv/bin/python scripts/make_sample_video.py

record-demo:
	cd backend && .venv/bin/python scripts/record_demo.py

clear-cache:
	cd backend && .venv/bin/python scripts/clear_cache.py

clean:
	rm -rf backend/.venv frontend/node_modules data/
