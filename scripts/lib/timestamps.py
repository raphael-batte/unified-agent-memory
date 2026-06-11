"""ISO timestamps for distill freshness — shared by pending, boundary, manifest."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    """Current local time as YYYY-MM-DDTHH:MM:SS."""
    return datetime.now().isoformat(timespec="seconds")


def parse_distilled_at(value: str | None) -> datetime | None:
    """
    Parse manifest distilled_at.
    Accepts ISO datetime or legacy date-only (treated as midnight local).
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if "T" in raw:
        try:
            return datetime.fromisoformat(raw[:19])
        except ValueError:
            pass
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return None


def transcript_mtime(jsonl: Path) -> float:
    return jsonl.stat().st_mtime


def transcript_is_newer_than_distill(jsonl: Path, distilled_at: str | None) -> bool:
    """True when jsonl mtime is strictly after distilled_at."""
    parsed = parse_distilled_at(distilled_at)
    if parsed is None:
        return True
    return transcript_mtime(jsonl) > parsed.timestamp()


def staging_date_slug(distilled_at: str) -> str:
    """Filesystem-safe date portion for staging filenames."""
    parsed = parse_distilled_at(distilled_at)
    if parsed is None:
        return distilled_at[:10].replace(":", "-")
    return parsed.strftime("%Y-%m-%d")
