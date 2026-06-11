"""Pointer provenance classes and curated Next step markers."""

from __future__ import annotations

import re
from typing import Any

CURATED_POINTER_PREFIX = "[curated]"
STRONG_POINTER_SOURCES = frozenset({"user_commitment", "todo_state"})
AGENT_LIVE_POINTER_SOURCE = "agent_live"
PROVENANCE_CURATED = "curated"
PROVENANCE_STRONG_SIGNAL = "strong_signal"
PROVENANCE_AGENT_LIVE = "agent_live"
PROVENANCE_AUTO = "auto"
# Backward-compatible alias (v0.15–0.17 manifest values)
PROVENANCE_LIVE = PROVENANCE_STRONG_SIGNAL

_CURATED_RE = re.compile(r"^\[curated\]\s*", re.I)
_LEGACY_LIVE = frozenset({"live"})


def normalize_provenance(value: str | None) -> str:
    """Map legacy manifest `live` → `strong_signal`."""
    if not value:
        return PROVENANCE_AUTO
    if value in _LEGACY_LIVE:
        return PROVENANCE_STRONG_SIGNAL
    return value


def pointer_provenance_class(source: str) -> str:
    if source == AGENT_LIVE_POINTER_SOURCE:
        return PROVENANCE_AGENT_LIVE
    if source in STRONG_POINTER_SOURCES:
        return PROVENANCE_STRONG_SIGNAL
    return PROVENANCE_AUTO


def is_strong_pointer_source(source: str) -> bool:
    return source in STRONG_POINTER_SOURCES or source == AGENT_LIVE_POINTER_SOURCE


def strip_curated_marker(bullet: str) -> str:
    return _CURATED_RE.sub("", bullet.strip()).strip()


def is_curated_next_step(bullet: str) -> bool:
    return bool(_CURATED_RE.match(bullet.strip()))


def find_curated_next_step(bullets: list[str]) -> str | None:
    for bullet in bullets:
        if is_curated_next_step(bullet):
            text = strip_curated_marker(bullet)
            if text:
                return text
    return None


def format_curated_next_step(text: str) -> str:
    body = text.strip()
    if is_curated_next_step(body):
        return f"- {body}"
    return f"- {CURATED_POINTER_PREFIX} {body}"


def watermark_changed(extract: dict, manifest_entry: dict[str, Any] | None) -> bool:
    from lib.distill_watermark import watermark_needs_redistill

    if manifest_entry is None:
        return True
    wm = {
        "user_message_count": int(
            extract.get("watermark_user_count") or extract.get("user_message_count") or 0
        ),
        "tail_hash": str(extract.get("watermark_tail_hash") or ""),
    }
    return watermark_needs_redistill(manifest_entry, wm)
