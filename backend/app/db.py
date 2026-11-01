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
    """Create all tables defined in models.py and add any newly introduced columns."""
    import app.models  # noqa: F401
    eng = engine_instance or engine()
    SQLModel.metadata.create_all(eng)

    # Migrate any added columns on existing SQLite databases safely
    try:
        with eng.connect() as conn:
            audit_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(audit)").fetchall()]
            for col_name, col_type in [
                ("provider_mode", "VARCHAR DEFAULT 'mock'"),
                ("model_segmentation", "VARCHAR DEFAULT 'SAM 3.1'"),
                ("model_agent", "VARCHAR DEFAULT 'Muse Spark'"),
                ("model_transcription", "VARCHAR DEFAULT 'Muse Voice Transcribe'"),
                ("is_replay", "BOOLEAN DEFAULT 0"),
            ]:
                if col_name not in audit_cols:
                    conn.exec_driver_sql(f"ALTER TABLE audit ADD COLUMN {col_name} {col_type}")

            cost_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(cost_log)").fetchall()]
            for col_name, col_type in [
                ("model_id", "VARCHAR DEFAULT ''"),
                ("latency_ms", "INTEGER DEFAULT 0"),
                ("cache_hit", "BOOLEAN DEFAULT 0"),
            ]:
                if col_name not in cost_cols:
                    conn.exec_driver_sql(f"ALTER TABLE cost_log ADD COLUMN {col_name} {col_type}")

            finding_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(finding)").fetchall()]
            for col_name, col_type in [
                ("evidence_ledger_json", "TEXT DEFAULT '[]'"),
                ("strongest_evidence_json", "TEXT DEFAULT NULL"),
                ("decision_policy", "VARCHAR DEFAULT 'default'"),
                ("detector", "VARCHAR DEFAULT 'sam'"),
                ("support_count", "INTEGER DEFAULT 1"),
                ("stability", "FLOAT DEFAULT 1.0"),
                ("escalation_steps_json", "TEXT DEFAULT '[]'"),
                ("ai_verdict", "VARCHAR DEFAULT 'unsure'"),
                ("final_verdict", "VARCHAR DEFAULT 'unsure'"),
            ]:
                if col_name not in finding_cols:
                    conn.exec_driver_sql(f"ALTER TABLE finding ADD COLUMN {col_name} {col_type}")
            conn.commit()
    except Exception:
        pass


def get_session() -> Generator[Session, None, None]:
    """Dependency for FastAPI route handlers."""
    with Session(engine()) as session:
        yield session
