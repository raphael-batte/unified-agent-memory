"""Selective assistant snippets for distill extract."""

from __future__ import annotations

import re

from lib.defaults import ASSISTANT_SNIPPET_MAX, DEFAULT_KEYWORDS
from lib.secrets_guard import sanitize_message
from lib.transcript_parse import ParsedTranscript, parse_transcript

_DECISION_LINE = re.compile(
    r"(?:decided|decision|recommend|summary|next step|deploy|architecture|"
    r"\u0440\u0435\u0448\u0435\u043d\u0438\u0435|\u0441\u043b\u0435\u0434\u0443\u044e\u0449)",
    re.I,
)


def _score_assistant(text: str) -> float:
    lower = text.lower()
    score = 0.0
    if _DECISION_LINE.search(text):
        score += 2.0
    if any(kw in lower for kw in DEFAULT_KEYWORDS):
        score += 1.5
    if len(text) >= 80:
        score += 0.5
    if "```" in text:
        score += 0.5
    return score


def extract_assistant_snippets_from_parsed(
    parsed: ParsedTranscript,
    *,
    max_snippets: int = ASSISTANT_SNIPPET_MAX,
    tail_rows: int = 30,
) -> list[str]:
    rows: list[tuple[float, str]] = []
    for msg in parsed.assistant_blocks[-tail_rows:]:
        clean, _n = sanitize_message(msg.text)
        if not clean:
            continue
        score = _score_assistant(clean)
        if score <= 0:
            continue
        snippet = re.sub(r"\s+", " ", clean)
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."
        rows.append((score, snippet))

    rows.sort(key=lambda r: -r[0])
    out: list[str] = []
    seen: set[str] = set()
    for _score, snippet in rows:
        key = snippet[:100].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(snippet)
        if len(out) >= max_snippets:
            break
    return out


def extract_assistant_snippets(
    jsonl,
    *,
    max_snippets: int = ASSISTANT_SNIPPET_MAX,
    tail_rows: int = 30,
) -> list[str]:
    from pathlib import Path

    path = Path(jsonl)
    if not path.is_file():
        return []
    parsed = parse_transcript(path)
    return extract_assistant_snippets_from_parsed(
        parsed, max_snippets=max_snippets, tail_rows=tail_rows
    )
