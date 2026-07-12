#!/usr/bin/env python3
"""Resolve agent-memory project slug for the current or given workspace path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.memory_config import resolve_memory_home  # noqa: E402
from lib.workspace_slug_resolve import resolve_slug  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Workspace directory (default: cwd)",
    )
    parser.add_argument("--memory-home", help="Hub path override")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    memory_home = resolve_memory_home(
        args.memory_home, script_file=str(SCRIPT_DIR / "resolve-workspace-slug.py")
    )
    slug, reason = resolve_slug(workspace, memory_home=memory_home)
    distill = (
        str((memory_home / "chats/projects" / f"{slug}.md").resolve())
        if slug
        else None
    )

    if args.json:
        print(
            json.dumps(
                {
                    "workspace": str(workspace),
                    "memory_home": str(memory_home),
                    "slug": slug,
                    "distill_path": distill,
                    "reason": reason,
                },
                ensure_ascii=False,
            )
        )
    else:
        if slug:
            print(slug)
        else:
            print("", end="")
    return 0 if slug else 1


if __name__ == "__main__":
    raise SystemExit(main())
