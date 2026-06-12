"""Strip Cursor-injected context blocks from user message text."""

from __future__ import annotations

import re

from lib.defaults import SYSTEM_BLOCK_TAGS, SYSTEM_SINGLE_LINE_TAGS

_PAIR_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _pair_pattern(tag: str) -> re.Pattern[str]:
    if tag not in _PAIR_RE_CACHE:
        _PAIR_RE_CACHE[tag] = re.compile(
            rf"<{re.escape(tag)}>.*?</{re.escape(tag)}>",
            re.DOTALL | re.IGNORECASE,
        )
    return _PAIR_RE_CACHE[tag]


def clear_system_block_cache() -> None:
    _PAIR_RE_CACHE.clear()


def strip_system_blocks(
    text: str,
    *,
    tags: tuple[str, ...] | None = None,
    single_line_tags: tuple[str, ...] | None = None,
) -> str:
    """
    Remove paired XML-like blocks injected into user messages (git_status, etc.).
    Iterates until stable so nested/overlapping blocks are handled.
    """
    if not text or not text.strip():
        return ""
    tag_list = tags if tags is not None else SYSTEM_BLOCK_TAGS
    single_tags = single_line_tags if single_line_tags is not None else SYSTEM_SINGLE_LINE_TAGS

    out = text
    changed = True
    while changed:
        changed = False
        for tag in tag_list:
            new_out, count = _pair_pattern(tag).subn("", out)
            if count:
                out = new_out
                changed = True

    for tag in single_tags:
        pat = re.compile(
            rf"<{re.escape(tag)}>.*?</{re.escape(tag)}>",
            re.DOTALL | re.IGNORECASE,
        )
        new_out, count = pat.subn("", out)
        if count:
            out = new_out

    out = re.sub(r"\s+", " ", out).strip()
    return out
