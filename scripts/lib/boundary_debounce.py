"""Debounce boundary distill — skip duplicate preCompact/sessionEnd within N seconds."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from lib.defaults import BOUNDARY_DEBOUNCE_SECONDS

_STATE_NAME = "boundary-debounce.json"


def _state_path(memory_home: Path) -> Path:
    return memory_home / ".state" / _STATE_NAME


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def should_skip_debounce(
    memory_home: Path,
    chat_id: str,
    *,
    debounce_seconds: int = BOUNDARY_DEBOUNCE_SECONDS,
) -> bool:
    path = _state_path(memory_home)
    data = _load_state(path)
    row = data.get(chat_id)
    if not isinstance(row, dict):
        return False
    ts = row.get("ts")
    if not isinstance(ts, (int, float)):
        return False
    return (time.time() - float(ts)) < debounce_seconds


def record_boundary_distill(memory_home: Path, chat_id: str) -> None:
    path = _state_path(memory_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_state(path)
    data[chat_id] = {"ts": time.time()}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
