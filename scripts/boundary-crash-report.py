#!/usr/bin/env python3
"""Emit structured crash row when boundary hook shell wrapper fails."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.boundary_crash import report_hook_crash  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home")
    parser.add_argument("--mode", default="boundary")
    parser.add_argument("--event", default="boundary")
    parser.add_argument("--exit-code", type=int, default=1)
    parser.add_argument("--error-class", default="boundary_hook_exit")
    parser.add_argument("--detail", default="hook failed")
    parser.add_argument("--stderr-file", metavar="PATH")
    args = parser.parse_args()

    hub = resolve_memory_home(args.memory_home, script_file=__file__)
    stderr_tail = None
    if args.stderr_file:
        p = Path(args.stderr_file).expanduser()
        if p.is_file():
            stderr_tail = p.read_text(encoding="utf-8", errors="replace")

    report_hook_crash(
        hub,
        mode=args.mode,
        event=args.event,
        exit_code=args.exit_code,
        error_class=args.error_class,
        detail=args.detail,
        stderr_tail=stderr_tail,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
