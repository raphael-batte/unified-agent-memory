"""Extract decision candidates from all user messages (O(n) cue scan)."""

from __future__ import annotations

import re
from pathlib import Path

from lib.lang_cues import (
    build_commitment_pattern,
    build_correction_pattern,
    load_lang_cues,
)

_NORM_RE = re.compile(r"\s+")


def _segment_for_index(segments: list[dict], index: int) -> int:
    for seg in segments:
        start = int(seg["start"])
        if start <= index < start + int(seg["count"]):
            return int(seg["segment"])
    return 1


def _trim_decision(text: str, *, max_len: int) -> str:
    text = _NORM_RE.sub(" ", text.strip())
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 3].rstrip()
    cut = re.sub(r"\s+\S*$", "", cut)
    if not cut:
        cut = text[: max_len - 3]
    return cut.rstrip(" \t\n\r.,;:-") + "..."


def extract_decision_candidates(
    messages: list[str],
    segments: list[dict] | None = None,
    *,
    memory_home: Path | None = None,
    max_items: int = 6,
    min_len: int = 20,
    max_len: int = 200,
) -> list[dict]:
    """
    Scan all user messages for commitment / correction cues.
    Returns [{text, segment, source, message_index}, ...].
    """
    if not messages:
        return []
    cues = load_lang_cues(memory_home=memory_home)
    commitment_pat = build_commitment_pattern(cues)
    correction_pat = build_correction_pattern(cues)
    segs = segments or []

    candidates: list[dict] = []
    seen: set[str] = set()

    for i, msg in enumerate(messages):
        text = _NORM_RE.sub(" ", msg.strip())
        if len(text) < min_len:
            continue

        source: str | None = None
        display = text

        corr = correction_pat.search(text)
        if corr:
            source = "correction"
        else:
            commit = commitment_pat.search(text)
            if commit:
                tail = (commit.group(1) or "").strip()
                if len(tail) >= min_len:
                    display = tail
                    source = "commitment"
                elif len(text) >= min_len:
                    source = "commitment"

        if not source:
            continue

        display = _trim_decision(display, max_len=max_len)
        if len(display) < min_len:
            continue

        key = display[:80].lower()
        if key in seen:
            continue
        seen.add(key)

        candidates.append(
            {
                "text": display,
                "segment": _segment_for_index(segs, i) if segs else 1,
                "source": source,
                "message_index": i,
            }
        )

    # Prefer corrections and later commitments (more settled decisions).
    candidates.sort(
        key=lambda row: (
            0 if row["source"] == "correction" else 1,
            -int(row["message_index"]),
        )
    )
    return candidates[:max_items]
