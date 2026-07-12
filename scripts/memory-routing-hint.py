#!/usr/bin/env python3
"""Print routing context for the agent (hub, slug, distill path, Next step preview)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.memory_config import resolve_memory_home, resolve_plugin_root  # noqa: E402
from lib.workspace_slug_resolve import extract_next_step, resolve_slug  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--memory-home")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    script = str(SCRIPT_DIR / "memory-routing-hint.py")
    memory_home = resolve_memory_home(args.memory_home, script_file=script)
    plugin_root = resolve_plugin_root(script_file=script, memory_home=memory_home)

    slug, reason = resolve_slug(workspace, memory_home=memory_home)
    distill_path = (
        memory_home / "chats" / "projects" / f"{slug}.md" if slug else None
    )
    next_step = extract_next_step(distill_path) if distill_path else None

    payload = {
        "memory_home": str(memory_home),
        "plugin_root": str(plugin_root) if plugin_root else None,
        "workspace": str(workspace),
        "slug": slug,
        "slug_reason": reason,
        "distill_path": str(distill_path) if distill_path else None,
        "next_step_preview": next_step,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"memory_home: {payload['memory_home']}")
        print(f"slug: {slug or '(unresolved)'} ({reason})")
        if distill_path:
            print(f"distill: {distill_path}")
        if next_step:
            print(f"next_step: {next_step}")
        else:
            print("next_step: (missing or empty — read full distill)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
