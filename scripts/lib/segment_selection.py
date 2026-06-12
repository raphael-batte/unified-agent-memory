"""Per-segment message selection and composite summary helpers."""

from __future__ import annotations

import math
import re

from lib.message_importance import mechanical_bullets, trim_message
from lib.token_budget import estimate_tokens, select_by_importance

_TRIM_RE = re.compile(r"\s+")


def sqrt_budgets(counts: list[int], total: int) -> list[int]:
    """Distribute integer budget across segments proportional to sqrt(count)."""
    if not counts or total <= 0:
        return []
    if len(counts) == 1:
        return [total]
    roots = [math.sqrt(max(1, c)) for c in counts]
    root_sum = sum(roots) or 1.0
    raw = [max(1, int(total * r / root_sum)) for r in roots]
    # Ensure at least one slot per non-empty segment and respect total cap.
    while sum(raw) > total:
        idx = max(range(len(raw)), key=lambda i: raw[i])
        if raw[idx] <= 1:
            break
        raw[idx] -= 1
    while sum(raw) < total:
        idx = max(range(len(raw)), key=lambda i: counts[i])
        raw[idx] += 1
    return raw


def _pick_global_indices(
    messages: list[str],
    segments: list[dict],
    *,
    max_messages: int,
    token_budget: int,
    max_chars: int,
) -> set[int]:
    counts = [int(seg["count"]) for seg in segments]
    msg_slots = sqrt_budgets(counts, max_messages)
    token_slots = sqrt_budgets(counts, token_budget)
    picked: set[int] = set()

    for seg, msg_cap, tok_cap in zip(segments, msg_slots, token_slots):
        start = int(seg["start"])
        count = int(seg["count"])
        chunk = messages[start : start + count]
        trimmed = [trim_message(m, max_chars=max_chars) for m in chunk]
        selected = select_by_importance(
            trimmed,
            max_messages=msg_cap,
            token_budget=tok_cap,
            always_include_first=True,
        )
        used_local: set[int] = set()
        for piece in selected:
            for j, candidate in enumerate(trimmed):
                if j in used_local:
                    continue
                if piece == candidate or (
                    len(piece) >= 24 and candidate.startswith(piece[:24])
                ):
                    picked.add(start + j)
                    used_local.add(j)
                    break
    return picked


def select_per_segment(
    messages: list[str],
    segments: list[dict],
    *,
    max_messages: int,
    token_budget: int,
    max_chars: int = 450,
) -> tuple[list[str], list[dict]]:
    """
    Importance sampling inside each topic segment with sqrt(count) budget share.
    Returns (selected_messages, segments enriched with bullets).
    """
    if not messages or not segments:
        return [], []
    picked = _pick_global_indices(
        messages,
        segments,
        max_messages=max_messages,
        token_budget=token_budget,
        max_chars=max_chars,
    )
    ordered = [
        trim_message(messages[i], max_chars=max_chars) for i in sorted(picked)
    ]
    enriched: list[dict] = []
    for seg in segments:
        start = int(seg["start"])
        end = start + int(seg["count"])
        seg_msgs = [
            trim_message(messages[i], max_chars=max_chars)
            for i in sorted(picked)
            if start <= i < end
        ]
        bullets = mechanical_bullets(seg_msgs, max_items=3)
        enriched.append({**seg, "bullets": bullets})
    return ordered, enriched


def build_summary_bullets(
    segments: list[dict],
    *,
    final_assistant: str | None,
    max_bullets: int = 5,
) -> list[str]:
    """Composite summary: one line per major segment + optional assistant tail."""
    if not segments:
        if final_assistant and final_assistant.strip():
            return [final_assistant.strip()[:500]]
        return []
    if len(segments) == 1:
        if final_assistant and final_assistant.strip():
            return [final_assistant.strip()[:500]]
        preview = str(segments[0].get("preview") or "").strip()
        return [preview] if preview else []

    bullets: list[str] = []
    seen: set[str] = set()
    for seg in segments:
        seg_bullets = seg.get("bullets") or []
        candidate = ""
        if seg_bullets:
            candidate = str(seg_bullets[0]).strip()
        elif seg.get("preview"):
            candidate = str(seg["preview"]).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        bullets.append(candidate)
        if len(bullets) >= max_bullets - 1:
            break

    if final_assistant and final_assistant.strip() and len(bullets) < max_bullets:
        tail = _TRIM_RE.sub(" ", final_assistant.strip())
        if len(tail) > 200:
            tail = tail[:197].rstrip() + "..."
        if tail and tail not in seen:
            bullets.append(tail)
    return bullets[:max_bullets]


def coverage_ratio(selected: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(min(1.0, selected / total), 4)
