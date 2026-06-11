"""Cross-layer duplicate hints — fails ↔ conventions keyword overlap."""

from __future__ import annotations

import re
from pathlib import Path

from lib.defaults import (
    CROSS_LAYER_MAX_DF,
    CROSS_LAYER_MIN_SHARED_BIGRAMS,
    DOMAIN_STOPWORDS,
)

HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
FAIL_BULLET = re.compile(r"^-\s+(.+?)\s*$", re.M)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{3,}", re.I)

STOPWORDS = frozenset(
    {
        "that", "this", "with", "from", "when", "only", "must", "never",
        "always", "should", "have", "been", "were", "they", "them", "your",
        "into", "about", "after", "before", "each", "more", "than", "then",
        "also", "just", "like", "some", "such", "what", "which", "will",
        "would", "could", "there", "their", "these", "those", "being",
    }
)

ALL_STOPWORDS = STOPWORDS | DOMAIN_STOPWORDS


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def raw_token_sequence(text: str) -> list[str]:
    return [
        t.lower()
        for t in TOKEN_RE.findall(text)
        if t.lower() not in ALL_STOPWORDS
    ]


def token_set(text: str) -> set[str]:
    return set(raw_token_sequence(text))


def build_document_frequency(texts: list[str]) -> dict[str, int]:
    """Count how many hub texts contain each token (document = one section body)."""
    df: dict[str, int] = {}
    for text in texts:
        for token in token_set(text):
            df[token] = df.get(token, 0) + 1
    return df


def significant_tokens(text: str, df: dict[str, int], *, max_df: int = CROSS_LAYER_MAX_DF) -> set[str]:
    return {t for t in token_set(text) if df.get(t, 0) <= max_df}


def significant_bigrams(
    text: str,
    df: dict[str, int],
    *,
    max_df: int = CROSS_LAYER_MAX_DF,
) -> set[str]:
    seq = [t for t in raw_token_sequence(text) if df.get(t, 0) <= max_df]
    if len(seq) < 2:
        return set()
    return {f"{seq[i]} {seq[i + 1]}" for i in range(len(seq) - 1)}


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            current = m.group(1).strip()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def _bigram_overlap_warning(
    label_a: str,
    label_b: str,
    bigrams_a: set[str],
    bigrams_b: set[str],
    *,
    min_shared: int = CROSS_LAYER_MIN_SHARED_BIGRAMS,
) -> str | None:
    shared = bigrams_a & bigrams_b
    if len(shared) < min_shared:
        return None
    ordered = sorted(shared)
    sample = "; ".join(ordered[:3])
    extra = max(0, len(shared) - 3)
    suffix = f" (+{extra} more)" if extra else ""
    return f"phrase overlap {label_a} ↔ {label_b}: {sample}{suffix}"


def collect_cross_layer_warnings(memory_home: Path) -> list[str]:
    """Warnings only — do not fail verify."""
    warnings: list[str] = []
    fails_text = read_text(memory_home / "feedback" / "fails.md")
    conv_text = read_text(memory_home / "context" / "conventions.md")
    conv_lower = conv_text.lower()

    # Legacy: superseded fail bullet echoed in conventions (substring)
    for match in FAIL_BULLET.finditer(fails_text):
        bullet = match.group(1).strip()
        if len(bullet) < 20:
            continue
        tail = fails_text[match.end() : match.end() + 120]
        if "_superseded" not in tail.lower():
            continue
        key = bullet[:40].lower()
        if key in conv_lower:
            warnings.append(
                f"superseded fail may duplicate conventions: {bullet[:60]}…"
            )

    conv_sections = split_sections(conv_text)
    fail_sections = split_sections(fails_text)
    section_bodies = [
        body.strip()
        for body in list(conv_sections.values()) + list(fail_sections.values())
        if body.strip()
    ]
    df = build_document_frequency(section_bodies)

    conv_bigrams = {
        name: significant_bigrams(body, df)
        for name, body in conv_sections.items()
        if body.strip()
    }

    for fail_name, fail_body in fail_sections.items():
        if not fail_body.strip():
            continue
        fail_bg = significant_bigrams(fail_body, df)
        if len(fail_bg) < CROSS_LAYER_MIN_SHARED_BIGRAMS:
            continue
        for conv_name, conv_bg in conv_bigrams.items():
            msg = _bigram_overlap_warning(
                f"fails/{fail_name}",
                f"conventions/{conv_name}",
                fail_bg,
                conv_bg,
            )
            if msg and msg not in warnings:
                warnings.append(msg)

    return warnings
