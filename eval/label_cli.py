#!/usr/bin/env python3
"""Convenience alias for keyframe ground truth labeling CLI."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.label_keyframes import main

if __name__ == "__main__":
    main()
