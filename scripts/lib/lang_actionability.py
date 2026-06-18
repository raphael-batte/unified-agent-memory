"""Shared pointer-tail actionability checks (forward_pointer, decision_extract)."""

from __future__ import annotations

import re

from lib.defaults import DOMAIN_STOPWORDS, GENERIC_MESSAGE_START

_TOKEN_RE = re.compile(r"[\w\u0400-\u04ff]+", re.UNICODE)


def significant_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if len(tok) > 2 and tok not in DOMAIN_STOPWORDS
    }


def is_generic_only(text: str) -> bool:
    """True when the message has no substantive tokens beyond generic openers."""
    stripped = text.strip().lower()
    if not stripped:
        return True
    if stripped in GENERIC_MESSAGE_START:
        return True
    tokens = significant_tokens(stripped)
    if not tokens:
        raw = {t for t in _TOKEN_RE.findall(stripped) if t}
        return bool(raw) and raw <= GENERIC_MESSAGE_START
    return False


def is_pointer_actionable(text: str, *, min_len: int) -> bool:
    """Tail after commitment-strip must be long enough and not generic-only."""
    line = re.sub(r"\s+", " ", text.strip())
    if len(line) < min_len:
        return False
    return not is_generic_only(line)
