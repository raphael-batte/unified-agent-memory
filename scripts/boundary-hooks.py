#!/usr/bin/env python3
"""CLI for Cursor boundary hooks (sessionStart / preCompact / sessionEnd)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.boundary_hooks import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
