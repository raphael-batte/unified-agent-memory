"""Extract decision candidates from all user messages (O(n) cue scan)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.defaults import (
    DECISION_COMMITMENT_CUE_MAX_START,
    DECISION_CORRECTION_CUE_MAX_START,
    DECISION_JUNK_MARKERS,
    DECISION_MAX_SOURCE_CHARS,
    DECISION_MIN_LENGTH,
    DECISION_NEGATION_MAX_START,
    DECISION_OUTPUT_MAX_LEN,
    MAX_DECISION_CANDIDATES,
)
from lib.lang_cues import (
    build_commitment_pattern,
    build_correction_pattern,
    load_lang_cues,
)

_NORM_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+", re.I)
# Russian negation cues via escapes (framework sources stay ASCII-only)
_NEGATION_QUESTION_RE = re.compile(
    r"(?:"
    r"\u043d\u0435\s+\u043d\u0430\u0434\u043e|"
    r"\u043d\u0435\s+\u043d\u0443\u0436\u043d\u043e|"
    r"\u043d\u0435\s+\u0431\u0443\u0434\u0435\u043c|"
    r"don't|do\s+not|no\s+need"
    r")(?:\b|\s|$)",
    re.I,
)


def _empty_stats() -> dict[str, int]:
    return {
        "marker": 0,
        "position": 0,
        "question": 0,
        "length": 0,
        "junk": 0,
        "duplicate": 0,
    }


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


def _has_junk_markers(text: str) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in DECISION_JUNK_MARKERS):
        return True
    if lower.count("{") >= 3 and '"lighthouse' in lower:
        return True
    if "<agent_skills>" in lower or "<git_status>" in lower:
        return True
    urls = _URL_RE.findall(text)
    if len(urls) >= 2:
        return True
    pipe_lines = sum(1 for line in text.splitlines() if "│" in line or "✓" in line)
    if pipe_lines >= 2:
        return True
    return False


def _scan_text(text: str, *, max_source: int) -> str:
    """For long pastes, scan only the leading line if it is substantive."""
    text = _NORM_RE.sub(" ", text.strip())
    if len(text) <= max_source:
        return text
    first_line = text.split("\n", 1)[0].strip()
    first_line = _NORM_RE.sub(" ", first_line)
    if len(first_line) >= DECISION_MIN_LENGTH:
        return first_line
    return text[:max_source]


def _is_negation_question(
    text: str,
    *,
    max_start: int = DECISION_NEGATION_MAX_START,
) -> bool:
    """Negation cue must lead the message to exempt a trailing question mark."""
    head = text[:max_start].lstrip()
    return bool(_NEGATION_QUESTION_RE.match(head))


_EN_CORRECTION_START = (
    "don't",
    "do not",
    "instead",
    "wrong",
    "fix",
    "broken",
    "regression",
    "revert",
    "not working",
)


def _correction_at_start(
    text: str,
    cues: dict[str, list[str]],
    *,
    max_start: int = DECISION_CORRECTION_CUE_MAX_START,
) -> bool:
    """Correction cue at message start (avoids false match of negation inside RU homonyms)."""
    head = text[:max_start].strip().lower()
    for cue in list(cues.get("correction_cues") or []) + list(_EN_CORRECTION_START):
        c = cue.lower()
        if head.startswith(c):
            return True
    return False


def extract_decision_candidates(
    messages: list[str],
    segments: list[dict] | None = None,
    *,
    memory_home: Path | None = None,
    max_items: int = MAX_DECISION_CANDIDATES,
    min_len: int = DECISION_MIN_LENGTH,
    max_len: int = DECISION_OUTPUT_MAX_LEN,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Scan all user messages for commitment / correction cues.
    Returns (candidates, rejection_stats).
    """
    stats = _empty_stats()
    if not messages:
        return [], stats

    cues = load_lang_cues(memory_home=memory_home)
    commitment_pat = build_commitment_pattern(cues)
    correction_pat = build_correction_pattern(cues)
    segs = segments or []

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, msg in enumerate(messages):
        raw = _NORM_RE.sub(" ", msg.strip())
        if len(raw) < min_len:
            continue

        if _has_junk_markers(raw):
            stats["junk"] += 1
            continue

        text = _scan_text(raw, max_source=DECISION_MAX_SOURCE_CHARS)
        if len(text) < min_len:
            stats["length"] += 1
            continue

        if text.rstrip().endswith("?"):
            prefix = text[:DECISION_COMMITMENT_CUE_MAX_START]
            has_cue = bool(
                _correction_at_start(text, cues)
                or commitment_pat.search(prefix)
            )
            if not has_cue and not _is_negation_question(text):
                stats["question"] += 1
                continue

        source: str | None = None
        display = text

        corr_prefix = text[:DECISION_CORRECTION_CUE_MAX_START]
        corr = correction_pat.search(corr_prefix)
        if corr:
            source = "correction"
        else:
            commit_prefix = text[:DECISION_COMMITMENT_CUE_MAX_START]
            commit = commitment_pat.search(commit_prefix)
            if commit:
                tail = (commit.group(1) or "").strip()
                if len(tail) >= min_len:
                    display = tail
                    source = "commitment"
                elif len(text) >= min_len:
                    source = "commitment"
            else:
                if correction_pat.search(text) or commitment_pat.search(text):
                    stats["position"] += 1
                continue

        display = _trim_decision(display, max_len=max_len)
        if len(display) < min_len:
            stats["length"] += 1
            continue

        if display.rstrip().endswith("?") and source != "correction":
            if not _is_negation_question(text):
                stats["question"] += 1
                continue

        if _has_junk_markers(display):
            stats["marker"] += 1
            continue

        key = display[:80].lower()
        if key in seen:
            stats["duplicate"] += 1
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

    candidates.sort(
        key=lambda row: (
            0 if row["source"] == "correction" else 1,
            -int(row["message_index"]),
        )
    )
    return candidates[:max_items], stats
