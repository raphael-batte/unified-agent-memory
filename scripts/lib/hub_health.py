"""On-disk hub health metrics for memory-health dashboard."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from lib.defaults import HUB_RETENTION_DAYS
from lib.open_threads import _project_files, threads_in_file
from lib.pointer_curation_queue import list_pending
from lib.timestamps import parse_distilled_at

_STAGING_UUID_RE = re.compile(r"-([0-9a-f]{8})\.md$", re.I)


def _parse_ts(value: str | None) -> datetime | None:
    return parse_distilled_at(value)


def analyze_open_threads_coverage(memory_home: Path, *, days: int = HUB_RETENTION_DAYS) -> dict:
    """Share of projects carrying a forward pointer, measured on disk.

    This replaces the old ``## Next step`` extraction rate, which reported 0%
    on every healthy hub once that section was retired. Coverage needs no
    metrics history, so it is trustworthy the day it ships.

    ``fresh`` counts only projects with a thread updated within ``days``;
    ``covered`` counts any thread, including undated ones that never age out.
    """
    paths = _project_files(memory_home)
    if not paths:
        return {
            "projects_scanned": 0,
            "threads_total": 0,
            "threads_auto": 0,
            "projects_covered": 0,
            "projects_curated": 0,
            "projects_fresh": 0,
            "threads_coverage_rate": None,
            "threads_curated_rate": None,
            "threads_fresh_rate": None,
        }

    now = datetime.now()
    threads_total = 0
    threads_auto = 0
    covered = 0
    fresh = 0
    curated_projects = 0
    for path in paths:
        threads = threads_in_file(path)
        threads_total += len(threads)
        threads_auto += sum(1 for th in threads if th.text.lower().startswith("[auto]"))
        if not threads:
            continue
        covered += 1
        if any(not th.text.lower().startswith("[auto]") for th in threads):
            curated_projects += 1
        if any(
            th.updated_dt is None or (now - th.updated_dt).days <= days
            for th in threads
        ):
            fresh += 1

    scanned = len(paths)
    return {
        "projects_scanned": scanned,
        "threads_total": threads_total,
        "threads_auto": threads_auto,
        "projects_covered": covered,
        "projects_curated": curated_projects,
        "projects_fresh": fresh,
        "threads_coverage_rate": covered / scanned,
        "threads_curated_rate": curated_projects / scanned,
        "threads_fresh_rate": fresh / scanned,
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
    out.update(analyze_open_threads_coverage(memory_home))
    out.update(analyze_curation_queue(memory_home))
    out.update(analyze_staging_orphans(memory_home))
    return out
