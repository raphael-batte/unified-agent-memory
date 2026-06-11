"""Append-only distill / boundary metrics for health reporting."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

METRICS_FILENAME = "agent-memory-metrics.jsonl"


def metrics_path(memory_home: Path) -> Path:
    return memory_home / "logs" / METRICS_FILENAME


def append_metric(memory_home: Path, row: dict[str, Any]) -> None:
    path = metrics_path(memory_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(row)
    out.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")


def read_metrics(
    memory_home: Path,
    *,
    max_lines: int = 5000,
) -> list[dict[str, Any]]:
    path = metrics_path(memory_home)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows
