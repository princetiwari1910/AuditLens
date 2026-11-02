#!/usr/bin/env bash
set -e

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [ -n "$FRONTEND_PID" ]; then
    echo "[smoke_ui.sh] Stopping temporary frontend dev server (PID $FRONTEND_PID)..."
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [ -n "$BACKEND_PID" ]; then
    echo "[smoke_ui.sh] Stopping temporary backend server (PID $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

# 1. Ensure backend is running
if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "[smoke_ui.sh] Starting backend server on http://127.0.0.1:8000..."
  (cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) &
  BACKEND_PID=$!
  for i in {1..30}; do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      echo "[smoke_ui.sh] Backend server ready."
      break
    fi
    sleep 0.5
  done
else
  echo "[smoke_ui.sh] Backend is already running on port 8000."
fi

# 2. Ensure frontend is running
if ! curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then
  echo "[smoke_ui.sh] Starting frontend dev server on http://127.0.0.1:5173..."
  (cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
  FRONTEND_PID=$!
  for i in {1..30}; do
    if curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then
      echo "[smoke_ui.sh] Frontend dev server ready."
      break
    fi
    sleep 0.5
  done
else
  echo "[smoke_ui.sh] Frontend is already running on port 5173."
fi

# 3. Run headless Chrome smoke test
echo "[smoke_ui.sh] Executing headless Chrome UI smoke tests..."
node scripts/smoke_ui.mjs
