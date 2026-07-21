"""Find chats that need distill — pending or stale vs manifest."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from lib import envs
from lib.chats_manifest import load_manifest, processed_by_id
from lib.distill_watermark import needs_distill_with_watermark
from lib.envs.base import AgentEnv
from lib.transcript_cursor import workspace_slug

DEFAULT_PROJECTS_ROOT = Path.home() / ".cursor/projects"


def _chat_row(
    jsonl: Path,
    chat_id: str,
    projects_root: Path,
    env: AgentEnv,
) -> dict[str, Any]:
    workspace = env.workspace_from_path(jsonl, projects_root)
    st = jsonl.stat()
    return {
        "id": chat_id,
        "project": workspace_slug(workspace),
        "workspace": workspace,
        "env": env.name,
        "mtime": st.st_mtime,
        "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
        "path": str(jsonl.resolve()),
        "jsonl": jsonl,
    }


def needs_distill(
    chat_id: str,
    jsonl: Path,
    manifest: dict[str, Any],
) -> bool:
    """True when unprocessed, watermark changed, or legacy mtime > distilled_at."""
    entry = processed_by_id(manifest).get(chat_id)
    return needs_distill_with_watermark(entry, jsonl)


def slugs_from_workspace_roots(roots: list[str] | None) -> set[str]:
    """Map open workspace paths to transcript project slugs."""
    slugs: set[str] = set()
    if not roots:
        return slugs
    for root in roots:
        if not isinstance(root, str) or not root.strip():
            continue
        name = Path(root).expanduser().resolve().name
        if not name:
            continue
        slugs.add(name)
        slugs.add(workspace_slug(f"Users-me-Work-{name}"))
        slugs.add(name.lower())
    return {s for s in slugs if s}


def _scan_targets(projects_root: Path | None) -> list[tuple[AgentEnv, Path]]:
    """(environment, root) pairs to scan.

    With an explicit root we probe it with every environment: the layouts are
    disjoint (Cursor nests under ``agent-transcripts/``, Claude is flat), so at most
    one of them matches and callers keep passing a single path as before.
    """
    if projects_root is not None:
        return [(env, projects_root) for env in envs.all_envs()]
    return [(env, env.transcript_root()) for env in envs.available_envs()]


def scan_transcript_rows(
    projects_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Inventory every environment's transcripts — the hub is shared."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for env, root in _scan_targets(projects_root):
        for chat_id, jsonl in env.build_transcript_index(root).items():
            if env.is_ignored(jsonl) or chat_id in seen:
                continue
            seen.add(chat_id)
            rows.append(_chat_row(jsonl, chat_id, root, env))
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def filter_by_days(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if days <= 0:
        return rows
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [r for r in rows if r["date"] >= cutoff]


def order_for_distill(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bulk distill: oldest transcript mtime first (scan inventory stays newest-first)."""
    return list(reversed(rows))


def filter_by_slugs(
    rows: list[dict[str, Any]], slugs: set[str]
) -> list[dict[str, Any]]:
    if not slugs:
        return rows
    lowered = {s.lower() for s in slugs}
    return [
        r
        for r in rows
        if r["project"].lower() in lowered
        or workspace_slug(r["workspace"]).lower() in lowered
    ]


def _pending_in_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    return [r for r in rows if needs_distill(r["id"], r["jsonl"], manifest)]


def list_chats_needing_distill(
    memory_home: Path,
    *,
    projects_root: Path | None = None,
    days: int = 180,
    workspace_slugs: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    rows = scan_transcript_rows(projects_root)
    rows = filter_by_days(rows, days)
    if workspace_slugs:
        rows = filter_by_slugs(rows, workspace_slugs)
    pending = _pending_in_rows(rows, manifest)
    if limit is not None and limit > 0:
        pending = pending[:limit]
    return pending


def scan_chat_stats(
    memory_home: Path,
    *,
    projects_root: Path | None = None,
    windows: tuple[int, ...] = (90, 180),
) -> dict[str, Any]:
    """
    Fast inventory for sync dialog — no distill, no jsonl parsing.
    """
    manifest = load_manifest(memory_home / "chats" / "manifest.json")
    rows = scan_transcript_rows(projects_root)
    processed_ids = set(processed_by_id(manifest))

    stats: dict[str, Any] = {
        "status": "ok",
        "memory_home": str(memory_home),
        "total_chats": len(rows),
        "processed_in_manifest": len(processed_ids),
        "windows_days": list(windows),
    }

    for days in windows:
        in_window = filter_by_days(rows, days)
        pending = _pending_in_rows(in_window, manifest)
        stats[f"active_{days}d"] = len(in_window)
        stats[f"pending_{days}d"] = len(pending)

    stats["message"] = (
        f"Total chats: {stats['total_chats']}. "
        f"Active 90d: {stats.get('active_90d', 0)} "
        f"(pending {stats.get('pending_90d', 0)}). "
        f"Active 180d: {stats.get('active_180d', 0)} "
        f"(pending {stats.get('pending_180d', 0)})."
    )
    return stats
