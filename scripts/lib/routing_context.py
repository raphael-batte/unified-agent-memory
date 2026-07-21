"""Render the forward pointer as context for environments that inject on events.

Cursor keeps Open threads in front of the agent with an alwaysApply rule, so the
pointer is simply always present. Claude Code has no such rule but does have events,
so we inject the same information at the two moments it is useful: session start and
prompt submit. Injecting on every prompt would be noise, hence the debounce.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from lib.hub_lock import write_json_atomic
from lib.open_threads import collect_open_threads
from lib.workspace_slug_resolve import resolve_slug

#: Do not re-inject the pointer more often than this within one session.
INJECT_DEBOUNCE_SECONDS = 30 * 60

#: Keep the injected block small — it competes with the user's own context.
MAX_THREADS = 5

_STATE_NAME = "routing-inject.json"


def _state_path(memory_home: Path) -> Path:
    return memory_home / ".state" / _STATE_NAME


def render_open_threads(
    memory_home: Path,
    workspace: Path | None = None,
    *,
    days: int = 30,
    max_threads: int = MAX_THREADS,
) -> str | None:
    """Compact Open threads block, or None when there is nothing to say."""
    slug = None
    if workspace is not None:
        slug, _reason = resolve_slug(workspace, memory_home=memory_home)

    threads = collect_open_threads(memory_home, days=days, priority_slug=slug)
    if not threads:
        return None

    lines = ["[agent-memory] Open threads — where you left off:"]
    for thread in threads[:max_threads]:
        age = f" ({thread.age_days}d)" if thread.age_days is not None else ""
        lines.append(f"- [{thread.slug}] {thread.label}: {thread.text}{age}")
    if len(threads) > max_threads:
        lines.append(f"- …and {len(threads) - max_threads} more")
    return "\n".join(lines)


def should_inject(
    memory_home: Path,
    session_id: str,
    *,
    debounce_seconds: int = INJECT_DEBOUNCE_SECONDS,
) -> bool:
    path = _state_path(memory_home)
    if not path.is_file():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    row = data.get(session_id) if isinstance(data, dict) else None
    if not isinstance(row, dict):
        return True
    ts = row.get("ts")
    if not isinstance(ts, (int, float)):
        return True
    return (time.time() - float(ts)) >= debounce_seconds


def record_injection(memory_home: Path, session_id: str) -> None:
    path = _state_path(memory_home)
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}
    data[session_id] = {"ts": time.time()}
    write_json_atomic(path, data)
