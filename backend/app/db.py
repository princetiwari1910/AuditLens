"""Database engine and session management for AuditLens."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def get_db_path() -> Path:
    settings = get_settings()
    settings.ensure_dirs()
    return settings.DATA_DIR / "auditlens.db"


_engine = None
_cached_db_path: Path | None = None


def engine():
    """Return the current database engine, recreating if db_path changed."""
    global _engine, _cached_db_path
    current_path = get_db_path()
    if _engine is None or _cached_db_path != current_path:
        sqlite_url = f"sqlite:///{current_path}"
        _engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        _cached_db_path = current_path
    return _engine


def reset_engine():
    """Reset engine singleton for testing."""
    global _engine, _cached_db_path
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _cached_db_path = None


def init_db(engine_instance=None) -> None:
    """Create all tables defined in models.py."""
    import app.models  # noqa: F401
    eng = engine_instance or engine()
    SQLModel.metadata.create_all(eng)


def get_session() -> Generator[Session, None, None]:
    """Dependency for FastAPI route handlers."""
    with Session(engine()) as session:
        yield session
