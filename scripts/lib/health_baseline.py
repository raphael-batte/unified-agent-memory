"""Rolling baseline for distill health — detect degradation vs personal norm.

Pointer hit rate used to drive degradation here. It cannot any more: since
`## Next step` was retired (v0.24) every apply reports `deprecated_passthrough`,
so the rate is pinned at 0% and both rules fired on a perfectly healthy hub —
a permanent ⚠ in `memory-status` and a notification on every `memory-health
--notify` run. Errors are the only trustworthy signal until the Open-threads
metrics land (see `open_thread_drafted` in the distill metric, added separately);
a rate needs weeks of history before a floor means anything.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

BASELINE_FILENAME = "health-baseline.json"
MIN_WINDOW_DISTILLS = 2


def baseline_path(memory_home: Path) -> Path:
    return memory_home / "logs" / BASELINE_FILENAME


def load_baseline(memory_home: Path) -> dict[str, Any]:
    path = baseline_path(memory_home)
    if not path.is_file():
        return {"samples": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"samples": []}
    if not isinstance(data, dict):
        return {"samples": []}
    data.setdefault("samples", [])
    return data


def save_baseline(memory_home: Path, data: dict[str, Any]) -> None:
    path = baseline_path(memory_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_snapshot(
    memory_home: Path,
    *,
    distilled_count: int,
    error_count: int,
    max_samples: int = 30,
) -> dict[str, Any]:
    """Append today's window stats; keep last N daily snapshots."""
    data = load_baseline(memory_home)
    today = datetime.now().strftime("%Y-%m-%d")
    samples: list[dict[str, Any]] = [
        s for s in data.get("samples", []) if s.get("date") != today
    ]
    samples.append(
        {
            "date": today,
            "distilled": distilled_count,
            "errors": error_count,
        }
    )
    data["samples"] = samples[-max_samples:]
    # Retired keys are dropped rather than migrated — a stale median would only
    # invite someone to wire the old rule back up.
    for key in ("pointer_hit_rates", "pointer_hit_median"):
        data.pop(key, None)
    save_baseline(memory_home, data)
    return data


def check_degradation(
    window_stats: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Flag a degraded window. Errors only — see the module docstring."""
    errors = int(window_stats.get("errors") or 0)

    out: dict[str, Any] = {
        "baseline_samples": len(baseline.get("samples") or []),
        "degraded": False,
        "degradation_reason": None,
    }

    if errors > 0:
        out["degraded"] = True
        out["degradation_reason"] = f"errors={errors}"

    return out
