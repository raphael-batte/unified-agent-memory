"""On-disk hub health metrics for memory-health dashboard."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from lib.forward_pointer import NO_POINTER_MARKER, STALE_POINTER_PREFIX
from lib.pointer_curation_queue import list_pending
from lib.project_merge import _bullets, _parse_sections
from lib.timestamps import parse_distilled_at

_STAGING_UUID_RE = re.compile(r"-([0-9a-f]{8})\.md$", re.I)


def _parse_ts(value: str | None) -> datetime | None:
    return parse_distilled_at(value)


def analyze_project_pointers(memory_home: Path) -> dict:
    projects = memory_home / "chats" / "projects"
    extracted = 0
    placeholder = 0
    curated = 0
    empty = 0
    total = 0
    if not projects.is_dir():
        return {
            "projects_scanned": 0,
            "pointer_extracted": 0,
            "pointer_placeholder": 0,
            "pointer_curated": 0,
            "pointer_empty": 0,
            "pointer_extracted_rate": None,
        }
    for path in projects.glob("*.md"):
        if path.name == "example.md":
            continue
        _preamble, sections = _parse_sections(
            path.read_text(encoding="utf-8", errors="replace")
        )
        bullets = _bullets(sections.get("Next step", ""))
        if not bullets:
            empty += 1
            total += 1
            continue
        for bullet in bullets:
            total += 1
            if bullet.strip().lower().startswith("[curated]"):
                curated += 1
            elif NO_POINTER_MARKER in bullet or bullet.strip().startswith(STALE_POINTER_PREFIX):
                placeholder += 1
            else:
                extracted += 1
    rate = extracted / total if total else None
    return {
        "projects_scanned": len(list(projects.glob("*.md"))),
        "pointer_extracted": extracted,
        "pointer_placeholder": placeholder,
        "pointer_curated": curated,
        "pointer_empty": empty,
        "pointer_extracted_rate": rate,
    }


def analyze_curation_queue(memory_home: Path) -> dict:
    items = list_pending(memory_home)
    if not items:
        return {"queue_size": 0, "queue_max_age_hours": None, "queue_median_age_hours": None}
    ages: list[float] = []
    now = datetime.now()
    for item in items:
        ts = _parse_ts(str(item.get("queued_at") or ""))
        if ts is None:
            continue
        ages.append((now - ts).total_seconds() / 3600.0)
    if not ages:
        return {"queue_size": len(items), "queue_max_age_hours": None, "queue_median_age_hours": None}
    ages.sort()
    mid = ages[len(ages) // 2]
    return {
        "queue_size": len(items),
        "queue_max_age_hours": round(max(ages), 1),
        "queue_median_age_hours": round(mid, 1),
    }


def analyze_staging_orphans(
    memory_home: Path,
    *,
    orphan_days: int = 7,
) -> dict:
    staging_dir = memory_home / "chats" / "merge-staging"
    if not staging_dir.is_dir():
        return {"staging_files": 0, "staging_orphans": 0, "staging_orphan_rate": None}
    cutoff = datetime.now().timestamp() - orphan_days * 86400
    total = 0
    orphans = 0
    for path in staging_dir.glob("*.md"):
        total += 1
        try:
            st_mtime = path.stat().st_mtime
        except OSError:
            continue
        if st_mtime >= cutoff:
            continue
        slug_part = path.stem.rsplit("-", 2)[0] if "-" in path.stem else path.stem
        project = memory_home / "chats" / "projects" / f"{slug_part}.md"
        if not project.is_file():
            orphans += 1
            continue
        try:
            if project.stat().st_mtime < st_mtime:
                orphans += 1
        except OSError:
            orphans += 1
    rate = orphans / total if total else None
    return {
        "staging_files": total,
        "staging_orphans": orphans,
        "staging_orphan_rate": rate,
    }


def analyze_hub_disk(memory_home: Path) -> dict:
    out = {}
    out.update(analyze_project_pointers(memory_home))
    out.update(analyze_curation_queue(memory_home))
    out.update(analyze_staging_orphans(memory_home))
    return out
