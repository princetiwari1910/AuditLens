#!/usr/bin/env python3
"""Root wrapper for backend/scripts/smoke_meta.py."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from scripts.smoke_meta import main

if __name__ == "__main__":
    sys.exit(main())
