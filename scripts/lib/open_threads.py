"""Aggregate ## Open threads across all project distills into a rolling window.

The forward pointer is no longer a single ## Next step per workspace: it is the
union of every active direction touched in the last N days, across the whole hub.
Workspace slug is only a sort hint, not a visibility gate — a thread recorded in
Trendymen.md still surfaces when asked from the steaklovers-dev workspace.

Aggregation is done on read (no materialized index) so it is always consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lib.defaults import HUB_RETENTION_DAYS
from lib.markdown_sections import (
    bullets as _bullets,
    last_updated_from_preamble,
    parse_sections,
)
from lib.project_merge import parse_open_thread
from lib.timestamps import parse_distilled_at


@dataclass(frozen=True)
class OpenThread:
    slug: str
    label: str
    text: str
    updated: str | None  # raw date string, or file fallback
    updated_dt: datetime | None
    age_days: int | None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "label": self.label,
            "text": self.text,
            "updated": self.updated,
            "age_days": self.age_days,
        }


def _project_files(memory_home: Path) -> list[Path]:
    projects = memory_home / "chats" / "projects"
    if not projects.is_dir():
        return []
    return sorted(p for p in projects.glob("*.md") if p.stem != "example")


def threads_in_file(path: Path) -> list[OpenThread]:
    """Parse Open threads from one project file; undated bullets fall back to
    the file's ``_Last updated_`` so pre-timestamp threads never silently vanish."""
    text = path.read_text(encoding="utf-8", errors="replace")
    preamble, sections = parse_sections(text)
    file_fallback = last_updated_from_preamble(preamble)
    out: list[OpenThread] = []
    for bullet in _bullets(sections.get("Open threads", "")):
        parsed = parse_open_thread(bullet)
        if parsed is None:
            continue
        raw_date = parsed["updated"] or file_fallback
        dt = parse_distilled_at(raw_date)
        out.append(
            OpenThread(
                slug=path.stem,
                label=parsed["label"],
                text=parsed["text"],
                updated=raw_date,
                updated_dt=dt,
                age_days=None,
            )
        )
    return out


def collect_open_threads(
    memory_home: Path,
    *,
    days: int = HUB_RETENTION_DAYS,
    now: datetime | None = None,
    priority_slug: str | None = None,
) -> list[OpenThread]:
    """
    Union of active directions across the hub, newest first.

    - Filters out threads whose tail-of-topic timestamp is older than ``days``.
      Undated threads (no stamp, no file fallback) are kept — they never age out
      until they get a real timestamp.
    - Keyed by ``(slug, label)`` — same label in two projects is two directions,
      never merged.
    - ``priority_slug`` (current workspace) sorts first as a hint, not a gate.
    """
    now = now or datetime.now()
    collected: list[OpenThread] = []
    for path in _project_files(memory_home):
        for th in threads_in_file(path):
            age = None
            if th.updated_dt is not None:
                age = (now - th.updated_dt).days
                if days > 0 and age > days:
                    continue
            collected.append(
                OpenThread(
                    slug=th.slug,
                    label=th.label,
                    text=th.text,
                    updated=th.updated,
                    updated_dt=th.updated_dt,
                    age_days=age,
                )
            )

    def sort_key(t: OpenThread) -> tuple:
        is_priority = 0 if (priority_slug and t.slug == priority_slug) else 1
        # newest first; undated (None) sink to the bottom within their group
        ts = t.updated_dt.timestamp() if t.updated_dt else float("-inf")
        return (is_priority, -ts, t.slug, t.label)

    collected.sort(key=sort_key)
    return collected
