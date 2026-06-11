"""Filter distill candidates that repeat existing project context."""

from __future__ import annotations

import re
from pathlib import Path

from lib.project_merge import _bullets, _parse_sections

_NORM_RE = re.compile(r"\s+")


def normalize_snippet(text: str, *, max_len: int = 80) -> str:
    return _NORM_RE.sub(" ", text.strip().lower())[:max_len]


def collect_prior_texts(project_path: Path | None) -> list[str]:
    if project_path is None or not project_path.is_file():
        return []
    _preamble, sections = _parse_sections(
        project_path.read_text(encoding="utf-8", errors="replace")
    )
    prior: list[str] = []
    for section in ("Decisions", "Next step", "Open threads", "Summary"):
        for bullet in _bullets(sections.get(section, "")):
            norm = normalize_snippet(bullet)
            if len(norm) >= 16:
                prior.append(norm)
        body = (sections.get(section) or "").strip()
        if body and not _bullets(body):
            norm = normalize_snippet(body)
            if len(norm) >= 16:
                prior.append(norm)
    return prior


def is_novel(text: str, prior_texts: list[str]) -> bool:
    norm = normalize_snippet(text)
    if len(norm) < 16:
        return False
    for prior in prior_texts:
        if norm == prior:
            return False
        if norm in prior or prior in norm:
            return False
    return True


def filter_novel_items(items: list[str], prior_texts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        norm = normalize_snippet(item)
        if norm in seen:
            continue
        if not is_novel(item, prior_texts + [normalize_snippet(x) for x in out]):
            continue
        seen.add(norm)
        out.append(item)
    return out
