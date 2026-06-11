"""CLI guard before distill-merge --apply when curated Decisions may need review."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lib.chats_manifest import processed_by_id
from lib.defaults import APPLY_REVIEW_MAX_DAYS
from lib.project_merge import LAST_UPDATED, _bullets, _parse_sections
from lib.timestamps import parse_distilled_at

BOOTSTRAP_PREFIX = "[bootstrap]"


def curated_decision_count(project_path: Path) -> int:
    """Non-bootstrap ## Decisions bullets in project distill file."""
    if not project_path.is_file():
        return 0
    text = project_path.read_text(encoding="utf-8", errors="replace")
    _, sections = _parse_sections(text)
    bullets = _bullets(sections.get("Decisions", ""))
    return sum(
        1
        for bullet in bullets
        if bullet.strip() and not bullet.strip().startswith(BOOTSTRAP_PREFIX)
    )


def _last_distill_datetime(
    project_path: Path,
    manifest: dict,
    chat_id: str,
) -> datetime | None:
    entry = processed_by_id(manifest).get(chat_id)
    if entry:
        parsed = parse_distilled_at(entry.get("distilled_at"))
        if parsed is not None:
            return parsed
    if project_path.is_file():
        text = project_path.read_text(encoding="utf-8", errors="replace")
        m = LAST_UPDATED.search(text)
        if m:
            raw = m.group(0).split(":", 1)[-1].strip()
            parsed = parse_distilled_at(raw)
            if parsed is not None:
                return parsed
    return None


def check_cli_apply_guard(
    memory_home: Path,
    chat_id: str,
    project_path: Path,
    manifest: dict,
    *,
    max_age_days: int = APPLY_REVIEW_MAX_DAYS,
) -> str | None:
    """
    Return block reason for CLI --apply without --force-apply, else None.
    Blocks when curated Decisions exist and last distill is older than max_age_days.
    """
    curated = curated_decision_count(project_path)
    if curated == 0:
        return None

    last_dt = _last_distill_datetime(project_path, manifest, chat_id)
    if last_dt is None:
        return None

    age_days = (datetime.now() - last_dt).days
    if age_days <= max_age_days:
        return None

    return (
        f"## Decisions has {curated} curated bullet(s); "
        f"last distill {age_days}d ago (>{max_age_days}d) — "
        "review merge-staging first. Use --force-apply to skip."
    )
