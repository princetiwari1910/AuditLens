"""Pytest configuration and global test lifecycle hooks."""

import pytest
from sse_starlette.sse import AppStatus
from app.db import reset_engine
from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_sse_and_engine(tmp_path, monkeypatch):
    """Reset SSE AppStatus, SQLModel engine, and isolate EVAL_OUTPUT_DIR."""
    eval_tmp = tmp_path / "eval_sandbox"
    eval_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVAL_OUTPUT_DIR", str(eval_tmp.resolve()))

    AppStatus.should_exit_event = None
    reset_engine()
    get_settings.cache_clear()
    yield
    AppStatus.should_exit_event = None
    reset_engine()
    get_settings.cache_clear()
