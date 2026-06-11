"""Rolling baseline for distill health — detect degradation vs personal norm."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

BASELINE_FILENAME = "health-baseline.json"
DEFAULT_DEGRADATION_DROP = 0.15
MIN_BASELINE_SAMPLES = 3
MIN_WINDOW_DISTILLS = 2


def baseline_path(memory_home: Path) -> Path:
    return memory_home / "logs" / BASELINE_FILENAME


def load_baseline(memory_home: Path) -> dict[str, Any]:
    path = baseline_path(memory_home)
    if not path.is_file():
        return {"samples": [], "pointer_hit_rates": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"samples": [], "pointer_hit_rates": []}
    if not isinstance(data, dict):
        return {"samples": [], "pointer_hit_rates": []}
    data.setdefault("samples", [])
    data.setdefault("pointer_hit_rates", [])
    return data


def save_baseline(memory_home: Path, data: dict[str, Any]) -> None:
    path = baseline_path(memory_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_snapshot(
    memory_home: Path,
    *,
    pointer_hit_rate: float | None,
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
            "pointer_hit_rate": pointer_hit_rate,
            "distilled": distilled_count,
            "errors": error_count,
        }
    )
    samples = samples[-max_samples:]
    rates = [
        float(s["pointer_hit_rate"])
        for s in samples
        if s.get("pointer_hit_rate") is not None
    ]
    data["samples"] = samples
    data["pointer_hit_rates"] = rates
    if rates:
        data["pointer_hit_median"] = sorted(rates)[len(rates) // 2]
    save_baseline(memory_home, data)
    return data


def check_degradation(
    window_stats: dict[str, Any],
    baseline: dict[str, Any],
    *,
    drop_threshold: float = DEFAULT_DEGRADATION_DROP,
) -> dict[str, Any]:
    """Compare 7d window to rolling median baseline."""
    current = window_stats.get("pointer_extracted_rate")
    median = baseline.get("pointer_hit_median")
    samples = baseline.get("pointer_hit_rates") or []
    distilled = int(window_stats.get("distilled") or 0)
    errors = int(window_stats.get("errors") or 0)

    out: dict[str, Any] = {
        "baseline_samples": len(samples),
        "baseline_median_hit_rate": median,
        "degraded": False,
        "degradation_reason": None,
    }

    if errors > 0:
        out["degraded"] = True
        out["degradation_reason"] = f"errors={errors}"

    if (
        current is not None
        and median is not None
        and len(samples) >= MIN_BASELINE_SAMPLES
        and distilled >= MIN_WINDOW_DISTILLS
        and float(current) < float(median) - drop_threshold
    ):
        out["degraded"] = True
        out["degradation_reason"] = (
            f"pointer_hit {float(current):.0%} vs baseline median {float(median):.0%}"
        )
        out["pointer_delta"] = float(current) - float(median)

    if (
        current is not None
        and distilled >= MIN_WINDOW_DISTILLS
        and float(current) < 0.25
        and len(samples) < MIN_BASELINE_SAMPLES
    ):
        out["degraded"] = True
        out["degradation_reason"] = f"pointer_hit {float(current):.0%} below 25% floor"

    return out
