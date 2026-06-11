"""Token budget helpers for distill sampling."""

from __future__ import annotations

import re

from lib.message_importance import rank_messages

_CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")


def estimate_tokens(text: str) -> int:
    cyrillic = len(_CYRILLIC_RE.findall(text))
    latin = max(0, len(text) - cyrillic)
    weighted = latin + int(cyrillic * 1.5)
    return max(1, weighted // 4)


def select_by_importance(
    messages: list[str],
    *,
    max_messages: int,
    token_budget: int | None = None,
    always_include_first: bool = True,
) -> list[str]:
    """Pick messages by importance score, preserving chronological order in output."""
    if not messages or max_messages <= 0:
        return []
    if len(messages) <= max_messages and token_budget is None:
        return messages

    ranked = rank_messages(messages)
    chosen_indices: set[int] = set()
    tokens = 0

    if always_include_first and messages:
        chosen_indices.add(0)
        tokens += estimate_tokens(messages[0])

    for idx, _score, msg in ranked:
        if len(chosen_indices) >= max_messages:
            break
        if idx in chosen_indices:
            continue
        cost = estimate_tokens(msg)
        if token_budget is not None and tokens + cost > token_budget:
            continue
        chosen_indices.add(idx)
        tokens += cost

    # Fill remaining slots from tail if budget allows
    if len(chosen_indices) < max_messages:
        for idx in range(len(messages) - 1, -1, -1):
            if len(chosen_indices) >= max_messages:
                break
            if idx in chosen_indices:
                continue
            cost = estimate_tokens(messages[idx])
            if token_budget is not None and tokens + cost > token_budget:
                continue
            chosen_indices.add(idx)
            tokens += cost

    return [messages[i] for i in sorted(chosen_indices)]


def window_messages(
    messages: list[str],
    *,
    window_size: int,
    overlap: int = 2,
) -> list[list[str]]:
    """Split messages into overlapping windows for map-reduce."""
    if not messages:
        return []
    if len(messages) <= window_size:
        return [messages]
    windows: list[list[str]] = []
    step = max(1, window_size - overlap)
    for start in range(0, len(messages), step):
        chunk = messages[start : start + window_size]
        if chunk:
            windows.append(chunk)
        if start + window_size >= len(messages):
            break
    return windows
