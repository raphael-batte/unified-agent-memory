"""Transcript watermarks — message counts and tail hashes for distill freshness."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lib.secrets_guard import is_terminal_noise, sanitize_message
from lib.transcript import extract_raw_user_texts


def _usable_user_texts(jsonl: Path) -> list[str]:
    try:
        raw_texts, _, _ = extract_raw_user_texts(jsonl)
    except Exception:
        return []
    out: list[str] = []
    for text in raw_texts:
        clean, _n = sanitize_message(text)
        if clean is None or is_terminal_noise(clean):
            continue
        out.append(clean)
    return out


def count_usable_user_messages(jsonl: Path) -> int:
    return len(_usable_user_texts(jsonl))


def tail_content_hash(jsonl: Path, *, tail_messages: int = 5) -> str:
    """Short hash of last N usable user messages (detects tail edits without mtime)."""
    tail = _usable_user_texts(jsonl)[-tail_messages:]
    if not tail:
        return ""
    blob = "\n---\n".join(tail)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def transcript_watermark(jsonl: Path) -> dict[str, int | str]:
    return {
        "user_message_count": count_usable_user_messages(jsonl),
        "tail_hash": tail_content_hash(jsonl),
    }
