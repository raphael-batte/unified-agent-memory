"""Pointer-related metrics (v0.14+ event schema)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.distill_metrics import append_metric

_EVENT_POINTER_FEEDBACK = "pointer_feedback"


def log_pointer_feedback(memory_home: Path, row: dict[str, Any]) -> None:
    """Session-start pointer usability feedback (v0.16+)."""
    out = dict(row)
    out.setdefault("event", _EVENT_POINTER_FEEDBACK)
    append_metric(memory_home, out)
