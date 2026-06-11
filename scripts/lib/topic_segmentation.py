"""Topic segments in long chats — cues, pause gaps, lexical shift."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from lib.defaults import DOMAIN_STOPWORDS
from pathlib import Path

from lib.lang_cues import build_new_task_pattern, load_lang_cues
from lib.timestamps import parse_distilled_at

_NEW_TASK_CACHE: dict[str, re.Pattern[str]] = {}
_TOKEN_RE = re.compile(r"[\w\u0400-\u04ff]+", re.UNICODE)


def clear_new_task_cache() -> None:
    _NEW_TASK_CACHE.clear()


def _new_task_pattern(memory_home: Path | None = None) -> re.Pattern[str]:
    key = str(memory_home or "")
    if key not in _NEW_TASK_CACHE:
        _NEW_TASK_CACHE[key] = build_new_task_pattern(
            load_lang_cues(memory_home=memory_home)
        )
    return _NEW_TASK_CACHE[key]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_distilled_at(value)
    if parsed is not None:
        return parsed
    try:
        return datetime.fromisoformat(str(value).strip()[:19])
    except ValueError:
        return None


def _significant_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if len(tok) > 2 and tok not in DOMAIN_STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def _collect_breaks(
    messages: list[str],
    *,
    timestamps: list[str | None] | None,
    pause_minutes: int,
    jaccard_window: int,
    jaccard_min: float,
    memory_home: Path | None = None,
) -> list[int]:
    new_task = _new_task_pattern(memory_home)
    breaks = {0}
    for i in range(1, len(messages)):
        if new_task.search(messages[i]):
            breaks.add(i)
            continue
        if timestamps and i < len(timestamps):
            prev_ts = _parse_ts(timestamps[i - 1])
            curr_ts = _parse_ts(timestamps[i])
            if (
                prev_ts is not None
                and curr_ts is not None
                and curr_ts - prev_ts > timedelta(minutes=pause_minutes)
            ):
                breaks.add(i)
                continue
        if i >= jaccard_window:
            left_msgs = messages[i - jaccard_window : i]
            right_msgs = messages[i : i + jaccard_window]
            left_tokens: set[str] = set()
            right_tokens: set[str] = set()
            for msg in left_msgs:
                left_tokens |= _significant_tokens(msg)
            for msg in right_msgs:
                right_tokens |= _significant_tokens(msg)
            if left_tokens and right_tokens and _jaccard(left_tokens, right_tokens) < jaccard_min:
                breaks.add(i)
    return sorted(breaks)


def segment_messages(
    messages: list[str],
    *,
    timestamps: list[str | None] | None = None,
    max_segments: int = 6,
    pause_minutes: int = 30,
    jaccard_window: int = 5,
    jaccard_min: float = 0.15,
    memory_home: Path | None = None,
) -> list[dict]:
    """
    Split user messages into topic segments.
    Returns [{segment, start, count, preview}, ...].
    """
    if not messages:
        return []
    breaks = _collect_breaks(
        messages,
        timestamps=timestamps,
        pause_minutes=pause_minutes,
        jaccard_window=jaccard_window,
        jaccard_min=jaccard_min,
        memory_home=memory_home,
    )
    if breaks == [0]:
        breaks = [0, len(messages)]
    elif breaks[-1] != len(messages):
        breaks.append(len(messages))

    segments: list[dict] = []
    for idx in range(len(breaks) - 1):
        start = breaks[idx]
        end = breaks[idx + 1]
        chunk = messages[start:end]
        if not chunk:
            continue
        preview = chunk[0][:120].strip()
        if len(preview) > 117:
            preview = preview[:117] + "..."
        segments.append(
            {
                "segment": len(segments) + 1,
                "start": start,
                "count": len(chunk),
                "preview": preview or "(segment)",
            }
        )
        if len(segments) >= max_segments:
            break
    return segments if len(segments) > 1 else []
