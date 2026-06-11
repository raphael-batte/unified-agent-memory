#!/usr/bin/env python3
"""Continue first-run distill after scope is set (agent-orchestrated)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.first_run import (  # noqa: E402
    is_initialized,
    mark_initialized,
    read_scope,
    ready_message,
    recommend_scope,
    run_distill_batch,
    scan_chat_stats,
)
from lib.memory_config import resolve_memory_home, resolve_plugin_root  # noqa: E402
from lib.pending_chats import DEFAULT_PROJECTS_ROOT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-home", help="Hub path override")
    parser.add_argument("--projects-root", metavar="DIR")
    args = parser.parse_args()

    memory_home = resolve_memory_home(
        args.memory_home, script_file=str(SCRIPT_DIR / "first-run-continue.py")
    )
    if is_initialized(memory_home):
        out = {"status": "already_initialized", "memory_home": str(memory_home)}
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    plugin = resolve_plugin_root(
        script_file=str(SCRIPT_DIR / "first-run-continue.py"),
        memory_home=memory_home,
    )
    if plugin is None:
        print("Error: plugin root not found", file=sys.stderr)
        return 1

    projects_root = (
        Path(args.projects_root).expanduser().resolve()
        if args.projects_root
        else DEFAULT_PROJECTS_ROOT
    )

    scope = read_scope(memory_home)
    if scope is None:
        scan = scan_chat_stats(memory_home, projects_root=projects_root)
        scope = recommend_scope(scan)
        if scope is None:
            print(
                "Error: no scope — run first-run-scope.py --preset … first",
                file=sys.stderr,
            )
            return 1

    batch = run_distill_batch(
        memory_home,
        scope,
        plugin_root=plugin,
        projects_root=projects_root,
    )
    stats = {
        "memory_home": str(memory_home),
        "distilled": batch.get("distilled", 0),
        "auto_fallback": batch.get("auto_fallback", 0),
        "projects": batch.get("projects", 0),
        "scope": scope,
    }
    mark_initialized(memory_home, stats)
    out = {
        "status": "complete",
        "batch": batch,
        "message": ready_message(stats),
    }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
