"""Topic segments in long chats — cues, pause gaps, lexical shift, merge to cap."""

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


def _preview_from_chunk(chunk: list[str]) -> str:
    if not chunk:
        return "(segment)"
    preview = chunk[0][:120].strip()
    if len(preview) > 117:
        preview = preview[:117] + "..."
    return preview or "(segment)"


def _raw_segments_from_breaks(
    messages: list[str],
    breaks: list[int],
) -> list[dict]:
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
        segments.append(
            {
                "segment": len(segments) + 1,
                "start": start,
                "count": len(chunk),
                "end": end,
                "preview": _preview_from_chunk(chunk),
            }
        )
    return segments


def _merge_pair(segments: list[dict], left: int, right: int) -> list[dict]:
    if left > right:
        left, right = right, left
    merged = {
        "segment": segments[left]["segment"],
        "start": segments[left]["start"],
        "count": segments[left]["count"] + segments[right]["count"],
        "end": segments[right]["end"],
        "preview": segments[left]["preview"],
    }
    out = segments[:left] + [merged] + segments[right + 1 :]
    return out


def _merge_small_segments(
    segments: list[dict],
    *,
    min_segment_msgs: int,
) -> list[dict]:
    segs = list(segments)
    if len(segs) <= 1:
        return segs
    while True:
        merged_any = False
        for i, seg in enumerate(segs):
            if seg["count"] >= min_segment_msgs:
                continue
            if len(segs) <= 1:
                break
            if i == 0:
                partner = 1
            elif i == len(segs) - 1:
                partner = i - 1
            else:
                left = segs[i - 1]["count"]
                right = segs[i + 1]["count"]
                partner = i - 1 if left <= right else i + 1
            lo, hi = sorted((i, partner))
            segs = _merge_pair(segs, lo, hi)
            merged_any = True
            break
        if not merged_any:
            break
    return segs


def _merge_to_cap(segments: list[dict], *, max_segments: int) -> list[dict]:
    segs = list(segments)
    while len(segs) > max_segments:
        best_i = 0
        best_sum = segs[0]["count"] + segs[1]["count"]
        for i in range(len(segs) - 1):
            combined = segs[i]["count"] + segs[i + 1]["count"]
            if combined < best_sum:
                best_sum = combined
                best_i = i
        segs = _merge_pair(segs, best_i, best_i + 1)
    for idx, seg in enumerate(segs, start=1):
        seg["segment"] = idx
    return segs


def merge_segments(
    segments: list[dict],
    *,
    max_segments: int = 6,
    min_segment_msgs: int = 3,
) -> list[dict]:
    """Merge adjacent segments until count <= max_segments; absorb tiny segments."""
    if not segments:
        return []
    segs = _merge_small_segments(segments, min_segment_msgs=min_segment_msgs)
    segs = _merge_to_cap(segs, max_segments=max_segments)
    return segs


def segment_messages(
    messages: list[str],
    *,
    timestamps: list[str | None] | None = None,
    max_segments: int = 6,
    min_segment_msgs: int = 3,
    pause_minutes: int = 30,
    jaccard_window: int = 5,
    jaccard_min: float = 0.15,
    memory_home: Path | None = None,
) -> list[dict]:
    """
    Split user messages into topic segments with full chat coverage.
    Returns [{segment, start, count, end, preview}, ...] or [] for single-topic chats.
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
    raw = _raw_segments_from_breaks(messages, breaks)
    if len(raw) <= 1:
        return []
    merged = merge_segments(
        raw,
        max_segments=max_segments,
        min_segment_msgs=min_segment_msgs,
    )
    total_covered = sum(seg["count"] for seg in merged)
    if total_covered != len(messages):
        raise ValueError(
            f"segment coverage mismatch: {total_covered} != {len(messages)}"
        )
    return merged
