"""Rolling incremental distill state per chat."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.defaults import (
    ROLLING_COMPACTION_ENQUEUE,
    ROLLING_COMPACTION_HARD_CAP,
    ROLLING_SUMMARY_MAX,
)
from lib.message_importance import mechanical_bullets
from lib.transcript_cursor import safe_path_component


def mechanical_compact_segments(segments: list[dict]) -> tuple[list[dict], list[str]]:
    """Dedup bullets across rolling segments; trim to summary cap."""
    bullets: list[str] = []
    seen: set[str] = set()
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        for raw in seg.get("bullets") or []:
            key = str(raw)[:80].lower()
            if key in seen:
                continue
            seen.add(key)
            bullets.append(str(raw))
    trimmed = bullets[-ROLLING_SUMMARY_MAX:]
    compact_segments = (
        [{"from": 0, "to": 0, "bullets": trimmed, "compacted": True}] if trimmed else []
    )
    return compact_segments, trimmed


def rolling_path(memory_home: Path, chat_id: str) -> Path:
    safe_id = safe_path_component(chat_id, fallback="chat")
    return memory_home / "chats" / "rolling" / f"{safe_id}.json"


def load_rolling(memory_home: Path, chat_id: str) -> dict[str, Any] | None:
    path = rolling_path(memory_home, chat_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_rolling(memory_home: Path, chat_id: str, data: dict[str, Any]) -> Path:
    path = rolling_path(memory_home, chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def last_processed_count(
    memory_home: Path,
    chat_id: str,
    manifest_entry: dict[str, Any] | None,
) -> int:
    rolling = load_rolling(memory_home, chat_id)
    if rolling and isinstance(rolling.get("last_user_count"), int):
        return int(rolling["last_user_count"])
    if manifest_entry and manifest_entry.get("watermark_user_count") is not None:
        return int(manifest_entry["watermark_user_count"])
    return 0


def build_incremental(
    all_messages: list[str],
    *,
    memory_home: Path,
    chat_id: str,
    manifest_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return incremental segment info for extract."""
    start = last_processed_count(memory_home, chat_id, manifest_entry)
    new_msgs = all_messages[start:] if start < len(all_messages) else []
    rolling = load_rolling(memory_home, chat_id) or {
        "chat_id": chat_id,
        "last_user_count": 0,
        "segments": [],
    }
    segments = list(rolling.get("segments") or [])
    segment_bullets: list[str] = []
    if new_msgs:
        segment_bullets = mechanical_bullets(new_msgs, max_items=5)
    prior_bullets: list[str] = []
    for seg in segments:
        if isinstance(seg, dict):
            prior_bullets.extend(seg.get("bullets") or [])
    rolling_summary = (prior_bullets + segment_bullets)[-12:]
    return {
        "incremental_from": start,
        "incremental_count": len(new_msgs),
        "incremental_bullets": segment_bullets,
        "rolling_summary": rolling_summary,
        "is_incremental": bool(new_msgs) and start > 0,
    }


def update_rolling_after_merge(
    memory_home: Path,
    chat_id: str,
    *,
    total_user_count: int,
    incremental_bullets: list[str] | None,
    incremental_from: int,
    workspace_slug: str | None = None,
    enqueue_threshold: int = ROLLING_COMPACTION_ENQUEUE,
    hard_cap: int = ROLLING_COMPACTION_HARD_CAP,
) -> dict:
    rolling = load_rolling(memory_home, chat_id) or {
        "chat_id": chat_id,
        "last_user_count": 0,
        "segments": [],
    }
    segments = list(rolling.get("segments") or [])
    if incremental_bullets:
        segments.append(
            {
                "from": incremental_from,
                "to": total_user_count,
                "bullets": incremental_bullets,
            }
        )
    compacted = False
    if len(segments) >= hard_cap:
        segments, summary = mechanical_compact_segments(segments)
        rolling["rolling_summary"] = summary
        compacted = True
    rolling["last_user_count"] = total_user_count
    rolling["segments"] = segments[-hard_cap:]
    save_rolling(memory_home, chat_id, rolling)

    queued = False
    if len(segments) >= enqueue_threshold:
        from lib.pointer_curation_queue import enqueue_compaction  # noqa: E402

        enqueue_compaction(
            memory_home,
            chat_id=chat_id,
            workspace_slug=workspace_slug,
            segment_count=len(segments),
            reason="rolling_segments" if not compacted else "rolling_hard_cap",
        )
        queued = True
    return {"segment_count": len(segments), "compaction_queued": queued, "compacted": compacted}
