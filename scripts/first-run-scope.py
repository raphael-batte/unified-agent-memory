#!/usr/bin/env python3
"""Set first-run distill scope (agent runs after user picks preset)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.first_run import SCOPE_PRESETS, write_scope  # noqa: E402
from lib.memory_config import resolve_memory_home  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home", help="Hub path override")
    parser.add_argument(
        "--preset",
        choices=sorted(SCOPE_PRESETS.keys()),
        help="Scope preset",
    )
    parser.add_argument("--days", type=int, help="Override days window")
    parser.add_argument("--limit", type=int, help="Max chats to distill")
    args = parser.parse_args()

    memory_home = resolve_memory_home(
        args.memory_home, script_file=str(SCRIPT_DIR / "first-run-scope.py")
    )

    if args.preset:
        scope = dict(SCOPE_PRESETS[args.preset])
    elif args.days is not None:
        scope = {"days": args.days, "limit": args.limit}
    else:
        parser.error("provide --preset or --days")
        return 2

    write_scope(memory_home, scope)
    out = {"status": "ok", "memory_home": str(memory_home), "scope": scope}
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
