"""Queue chats needing Open threads curation — sessionStart reminder."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.pending_chats import slugs_from_workspace_roots

QUEUE_NAME = "pointer-curation-queue.json"


def queue_path(memory_home: Path) -> Path:
    return memory_home / ".state" / QUEUE_NAME


def _load(memory_home: Path) -> list[dict[str, Any]]:
    path = queue_path(memory_home)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def _save(memory_home: Path, items: list[dict[str, Any]]) -> None:
    path = queue_path(memory_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def enqueue(
    memory_home: Path,
    *,
    chat_id: str,
    project_rel: str,
    reason: str,
    workspace_slug: str | None = None,
    staging_path: str | None = None,
    pointer_confidence: float | None = None,
    kind: str = "pointer",
) -> None:
    items = _load(memory_home)
    items = [
        i
        for i in items
        if not (i.get("chat_id") == chat_id and (i.get("kind") or "pointer") == kind)
    ]
    items.append(
        {
            "kind": kind,
            "chat_id": chat_id,
            "project_rel": project_rel,
            "workspace_slug": workspace_slug or "",
            "reason": reason,
            "staging_path": staging_path,
            "pointer_confidence": pointer_confidence,
            "queued_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    _save(memory_home, items[-30:])


def enqueue_open_thread_draft(
    memory_home: Path,
    *,
    chat_id: str,
    project_rel: str,
    draft_result: dict[str, Any],
    workspace_slug: str | None = None,
    staging_path: str | None = None,
) -> None:
    if not draft_result.get("drafted"):
        return
    enqueue(
        memory_home,
        chat_id=chat_id,
        project_rel=project_rel,
        reason="open-thread-draft",
        workspace_slug=workspace_slug,
        staging_path=staging_path,
        kind="open-thread",
    )


def enqueue_compaction(
    memory_home: Path,
    *,
    chat_id: str,
    workspace_slug: str | None = None,
    segment_count: int = 0,
    reason: str = "rolling_segments",
) -> None:
    slug = workspace_slug or "project"
    project_rel = f"projects/{slug}.md"
    enqueue(
        memory_home,
        chat_id=chat_id,
        project_rel=project_rel,
        reason=f"{reason}:{segment_count}",
        workspace_slug=workspace_slug,
        kind="compaction",
    )


def list_pending(
    memory_home: Path,
    *,
    workspace_slugs: set[str] | None = None,
    kind: str | None = "pointer",
) -> list[dict[str, Any]]:
    items = _load(memory_home)
    if kind is not None:
        items = [i for i in items if (i.get("kind") or "pointer") == kind]
    if not workspace_slugs:
        return items
    lowered = {s.lower() for s in workspace_slugs}
    return [
        i
        for i in items
        if (i.get("workspace_slug") or "").lower() in lowered
        or any(s in (i.get("project_rel") or "") for s in lowered)
    ]


def mark_done(memory_home: Path, chat_id: str, *, kind: str | None = None) -> bool:
    items = _load(memory_home)
    if kind is None:
        new_items = [i for i in items if i.get("chat_id") != chat_id]
    else:
        new_items = [
            i
            for i in items
            if not (
                i.get("chat_id") == chat_id and (i.get("kind") or "pointer") == kind
            )
        ]
    if len(new_items) == len(items):
        return False
    _save(memory_home, new_items)
    return True


def session_start_user_message(
    memory_home: Path,
    workspace_roots: list[str] | None,
) -> str | None:
    slugs = slugs_from_workspace_roots(workspace_roots or [])
    pending_pointer = list_pending(
        memory_home, workspace_slugs=slugs if slugs else None, kind="pointer"
    )
    pending_open_thread = list_pending(
        memory_home, workspace_slugs=slugs if slugs else None, kind="open-thread"
    )
    compaction = list_pending(
        memory_home, workspace_slugs=slugs if slugs else None, kind="compaction"
    )
    if not pending_pointer and not pending_open_thread and not compaction:
        return None
    lines: list[str] = []
    if pending_open_thread:
        lines.append(
            f"[agent-memory] {len(pending_open_thread)} chat(s) have ## Open threads "
            "[auto] drafts (add-thread / semantic-merge-prompt.md):"
        )
        for item in pending_open_thread[:3]:
            rel = item.get("project_rel", "?")
            reason = item.get("reason", "open-thread-draft")
            lines.append(f"  - {rel} ({reason})")
        if len(pending_open_thread) > 3:
            lines.append(f"  - ... +{len(pending_open_thread) - 3} more")
    if pending_pointer:
        lines.append(
            f"[agent-memory] {len(pending_pointer)} chat(s) may need ## Open threads "
            "(add-thread / semantic-merge-prompt.md):"
        )
        for item in pending_pointer[:3]:
            rel = item.get("project_rel", "?")
            reason = item.get("reason", "pointer")
            lines.append(f"  - {rel} ({reason})")
        if len(pending_pointer) > 3:
            lines.append(f"  - ... +{len(pending_pointer) - 3} more")
    if compaction:
        lines.append(
            f"[agent-memory] {len(compaction)} chat(s) need rolling compaction "
            "(semantic-merge-prompt.md):"
        )
        for item in compaction[:2]:
            lines.append(f"  - {item.get('chat_id', '?')[:8]}… ({item.get('reason', '')})")
    lines.append("Run semantic-merge / add-thread before new work.")
    return "\n".join(lines)


def needs_enqueue(
    apply_result: dict[str, Any] | None,
    *,
    draft_result: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Enqueue when an ``[auto]`` Open threads draft was written and needs curation."""
    draft = draft_result or (apply_result or {}).get("draft_result") or {}
    if draft.get("drafted") and draft.get("needs_curation"):
        return True, "open-thread-draft"
    return False, ""
