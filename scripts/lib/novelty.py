"""Filter distill candidates that repeat existing project context."""

from __future__ import annotations

import re
from pathlib import Path

from lib.defaults import (
    DECISION_FUZZY_JACCARD_THRESHOLD,
    DECISION_JUNK_MARKERS,
    DECISION_MIN_CONTENT_LEN,
    decision_fuzzy_dedup_enabled,
)
from lib.markdown_sections import bullets as _bullets
from lib.markdown_sections import parse_sections as _parse_sections

_NORM_RE = re.compile(r"\s+")
_TIER_PREFIX_RE = re.compile(r"^\[(curated|extracted|bootstrap)\]\s*", re.I)
_LABEL_PREFIX_RE = re.compile(r"^\*\*[^*]+:\*\*\s*")

TIER_CURATED = 3
TIER_BOOTSTRAP = 2
TIER_EXTRACTED = 1


def normalize_snippet(text: str, *, max_len: int = 80) -> str:
    return _NORM_RE.sub(" ", text.strip().lower())[:max_len]


def strip_decision_markers(text: str) -> str:
    """Drop tier prefix and optional ``**label:**`` before content comparison."""
    body = text.strip()
    m = _TIER_PREFIX_RE.match(body)
    if m:
        body = body[m.end() :].strip()
    m = _LABEL_PREFIX_RE.match(body)
    if m:
        body = body[m.end() :].strip()
    return body


def decision_tier(bullet: str) -> int:
    lower = bullet.strip().lower()
    if lower.startswith("[curated]"):
        return TIER_CURATED
    if lower.startswith("[bootstrap]"):
        return TIER_BOOTSTRAP
    if lower.startswith("[extracted]"):
        return TIER_EXTRACTED
    return TIER_EXTRACTED


def normalize_decision_content(text: str, *, max_len: int = 80) -> str:
    return normalize_snippet(strip_decision_markers(text), max_len=max_len)


def is_decision_junk(text: str) -> bool:
    body = strip_decision_markers(text)
    lower = body.lower()
    return any(marker in lower for marker in DECISION_JUNK_MARKERS)


def _numeric_tokens(tokens: set[str]) -> set[str]:
    return {tok for tok in tokens if any(ch.isdigit() for ch in tok)}


def _token_set(norm: str) -> set[str]:
    return {tok for tok in norm.split() if tok}


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    union = len(left | right)
    return inter / union if union else 0.0


def _duplicate_key(
    norm: str,
    seen: dict[str, tuple[int, int]],
    *,
    fuzzy: bool,
) -> str | None:
    tokens = _token_set(norm)
    for key in seen:
        if norm == key or norm in key or key in norm:
            return key
        if fuzzy and tokens:
            other = _token_set(key)
            nums_left = _numeric_tokens(tokens)
            nums_right = _numeric_tokens(other)
            if nums_left and nums_right and nums_left != nums_right:
                continue
            if jaccard_similarity(tokens, other) >= DECISION_FUZZY_JACCARD_THRESHOLD:
                return key
    return None


def dedupe_decision_bullets(
    bullets: list[str],
    *,
    fuzzy: bool | None = None,
    drop_junk: bool = True,
) -> list[str]:
    """
    Tier-priority dedup on decision content (marker/label agnostic).

    curated > bootstrap > extracted/plain; stable order for kept bullets.
    """
    if fuzzy is None:
        fuzzy = decision_fuzzy_dedup_enabled()
    seen: dict[str, tuple[int, int]] = {}
    out: list[str] = []
    for bullet in bullets:
        stripped = bullet.strip()
        if not stripped:
            continue
        if drop_junk and is_decision_junk(stripped):
            continue
        norm = normalize_decision_content(stripped)
        if not norm:
            continue
        tier = decision_tier(stripped)
        dup = _duplicate_key(norm, seen, fuzzy=fuzzy)
        if dup is None:
            seen[norm] = (tier, len(out))
            out.append(stripped)
            continue
        existing_tier, existing_idx = seen[dup]
        if tier > existing_tier:
            out[existing_idx] = stripped
            del seen[dup]
            seen[norm] = (tier, existing_idx)
        elif tier == existing_tier:
            continue
        else:
            continue
    return out


def collect_prior_texts(project_path: Path | None) -> list[str]:
    if project_path is None or not project_path.is_file():
        return []
    _preamble, sections = _parse_sections(
        project_path.read_text(encoding="utf-8", errors="replace")
    )
    prior: list[str] = []
    for section in ("Decisions", "Open threads", "Summary"):
        for bullet in _bullets(sections.get(section, "")):
            if section == "Decisions":
                norm = normalize_decision_content(bullet)
            else:
                norm = normalize_snippet(bullet)
            if len(norm) >= DECISION_MIN_CONTENT_LEN:
                prior.append(norm)
        body = (sections.get(section) or "").strip()
        if body and not _bullets(body):
            norm = (
                normalize_decision_content(body)
                if section == "Decisions"
                else normalize_snippet(body)
            )
            if len(norm) >= DECISION_MIN_CONTENT_LEN:
                prior.append(norm)
    return prior


def is_novel(text: str, prior_texts: list[str]) -> bool:
    if is_decision_junk(text):
        return False
    if len(normalize_snippet(text)) < DECISION_MIN_CONTENT_LEN:
        return False
    norm = normalize_decision_content(text)
    fuzzy = decision_fuzzy_dedup_enabled()
    seen = {p: (TIER_CURATED, 0) for p in prior_texts}
    return _duplicate_key(norm, seen, fuzzy=fuzzy) is None


def dedupe_bullets(bullets: list[str]) -> list[str]:
    """Decision-aware dedup (archive + live compact)."""
    return dedupe_decision_bullets(bullets)


def filter_novel_items(items: list[str], prior_texts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        norm = normalize_decision_content(item)
        if norm in seen:
            continue
        if not is_novel(item, prior_texts + list(seen)):
            continue
        seen.add(norm)
        out.append(item)
    return out
