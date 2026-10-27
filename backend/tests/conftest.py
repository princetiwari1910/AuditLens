"""Pytest configuration and global test lifecycle hooks."""

import pytest
from sse_starlette.sse import AppStatus
from app.db import reset_engine
from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_sse_and_engine():
    """Reset SSE AppStatus and SQLModel engine before and after every test."""
    AppStatus.should_exit_event = None
    reset_engine()
    get_settings.cache_clear()
    yield
    AppStatus.should_exit_event = None
    reset_engine()
    get_settings.cache_clear()
