"""Manifest watermark — decide redistill from message count + tail hash."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.defaults import MIN_NEW_USER_MESSAGES
from lib.timestamps import transcript_is_newer_than_distill
from lib.transcript_stats import transcript_watermark


def has_watermark(entry: dict[str, Any]) -> bool:
    return (
        entry.get("watermark_user_count") is not None
        or bool(entry.get("watermark_tail_hash"))
    )


def watermark_needs_redistill(
    entry: dict[str, Any],
    watermark: dict[str, int | str],
    *,
    min_new_messages: int = MIN_NEW_USER_MESSAGES,
) -> bool:
    stored_count = entry.get("watermark_user_count")
    stored_hash = entry.get("watermark_tail_hash") or ""
    current_count = int(watermark.get("user_message_count") or 0)
    current_hash = str(watermark.get("tail_hash") or "")

    if stored_count is not None:
        if current_count - int(stored_count) >= min_new_messages:
            return True
    if stored_hash and current_hash and stored_hash != current_hash:
        return True
    if stored_count is None and current_hash and stored_hash != current_hash:
        return True
    return False


def needs_distill_with_watermark(
    entry: dict[str, Any] | None,
    jsonl: Path,
    *,
    min_new_messages: int = MIN_NEW_USER_MESSAGES,
) -> bool:
    if entry is None:
        return True
    if not has_watermark(entry):
        return transcript_is_newer_than_distill(jsonl, entry.get("distilled_at"))
    wm = transcript_watermark(jsonl)
    return watermark_needs_redistill(entry, wm, min_new_messages=min_new_messages)


def watermark_for_manifest(jsonl: Path) -> dict[str, int | str]:
    return transcript_watermark(jsonl)
