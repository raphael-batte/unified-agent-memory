"""Merge agent-memory hooks into ~/.cursor/hooks.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_agent_memory_hooks() -> dict[str, list[dict[str, Any]]]:
    return {
        "sessionStart": [
            {"command": "./hooks/agent-memory-session-start.sh"},
        ],
        "preCompact": [
            {"command": "./hooks/agent-memory-boundary.sh"},
        ],
        "sessionEnd": [
            {"command": "./hooks/agent-memory-boundary.sh"},
            {"command": "./hooks/agent-memory-session-end.sh"},
        ],
        "afterFileEdit": [
            {
                "command": "./hooks/agent-memory-after-edit.sh",
            },
        ],
    }


def merge_hooks_file(hooks_json: Path, *, dry_run: bool = False) -> dict:
    """
    Merge framework hooks into existing hooks.json.
    Returns summary of changes.
    """
    incoming = default_agent_memory_hooks()
    if hooks_json.is_file():
        try:
            data = json.loads(hooks_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"version": 1, "hooks": {}}
    else:
        data = {"version": 1, "hooks": {}}

    if not isinstance(data, dict):
        data = {"version": 1, "hooks": {}}
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    added: list[str] = []
    for event, entries in incoming.items():
        existing = hooks.get(event, [])
        if not isinstance(existing, list):
            existing = []
        existing_cmds = {
            e.get("command") for e in existing if isinstance(e, dict)
        }
        for entry in entries:
            cmd = entry.get("command")
            if cmd and cmd not in existing_cmds:
                existing.append(entry)
                added.append(f"{event}:{cmd}")
        hooks[event] = existing

    if not dry_run:
        hooks_json.parent.mkdir(parents=True, exist_ok=True)
        hooks_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {"hooks_json": str(hooks_json), "added": added, "dry_run": dry_run}
