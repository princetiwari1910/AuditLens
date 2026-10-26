"""AuditLens FastAPI application entry-point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hooks."""
    settings = get_settings()
    settings.ensure_dirs()
    yield


app = FastAPI(
    title="AuditLens API",
    description="Evidence-backed safety audit from walkthrough videos.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS – allow the Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health endpoint ──────────────────────────────────────────────────────
@app.get("/api/health")
async def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "provider_mode": settings.PROVIDER_MODE}
