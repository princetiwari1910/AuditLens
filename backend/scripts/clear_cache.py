"""CLI script to clear AuditLens provider cache entries."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend directory is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import engine, init_db
from app.cache import clear_cache_entries
from sqlmodel import Session


def main() -> None:
    init_db()
    with Session(engine()) as session:
        count = clear_cache_entries(session)
        print(f"Cleared {count} cache entries from database.")


if __name__ == "__main__":
    main()
