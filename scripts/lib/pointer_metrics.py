"""Pointer-related metrics (v0.14+ event schema)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.distill_metrics import append_metric

_EVENT_POINTER_CLOBBERED = "pointer_clobbered_cross_chat"
_EVENT_POINTER_FEEDBACK = "pointer_feedback"

_CHAT_ID_IN_RECENT = re.compile(r"\]\(([0-9a-f-]{8,})\)", re.I)


def _chat_ids_from_recent(bullets: list[str]) -> list[str]:
    ids: list[str] = []
    for bullet in bullets:
        for match in _CHAT_ID_IN_RECENT.finditer(bullet):
            ids.append(match.group(1))
    return ids


def maybe_log_pointer_clobbered(
    memory_home: Path | None,
    *,
    workspace_slug: str,
    new_chat_id: str,
    existing_recent: list[str],
    prev_next_step: str | None,
    next_kind: str,
) -> None:
    """
  Log when a real Next step overwrites another chat's context in the same project.
  Heuristic: previous next step existed + another chat id still in Recent.
    """
    if memory_home is None or next_kind != "extracted" or not prev_next_step:
        return
    other_ids = [cid for cid in _chat_ids_from_recent(existing_recent) if cid != new_chat_id]
    if not other_ids:
        return
    append_metric(
        memory_home,
        {
            "event": _EVENT_POINTER_CLOBBERED,
            "workspace_slug": workspace_slug,
            "new_chat_id": new_chat_id,
            "other_chat_ids": other_ids[:3],
            "prev_next_step_preview": prev_next_step[:120],
        },
    )


def log_pointer_feedback(memory_home: Path, row: dict[str, Any]) -> None:
    """Session-start pointer usability feedback (v0.16+)."""
    out = dict(row)
    out.setdefault("event", _EVENT_POINTER_FEEDBACK)
    append_metric(memory_home, out)
