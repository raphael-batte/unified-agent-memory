"""Structured crash rows for boundary hooks — always land in metrics JSONL."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from lib.distill_metrics import append_metric


def report_hook_crash(
    memory_home: Path,
    *,
    mode: str,
    event: str | None = None,
    exit_code: int | None = None,
    error_class: str,
    detail: str,
    stderr_tail: str | None = None,
) -> None:
    row: dict[str, Any] = {
        "event": event or mode,
        "status": "crash",
        "error_class": error_class,
        "detail": detail[:500],
        "hook_mode": mode,
    }
    if exit_code is not None:
        row["exit_code"] = exit_code
    if stderr_tail:
        row["stderr_tail"] = stderr_tail[-800:]
    try:
        append_metric(memory_home, row)
    except OSError:
        pass


def report_exception(
    memory_home: Path,
    *,
    mode: str,
    event: str | None,
    exc: BaseException,
) -> None:
    report_hook_crash(
        memory_home,
        mode=mode,
        event=event,
        error_class=type(exc).__name__,
        detail=str(exc) or traceback.format_exc(limit=3),
    )
