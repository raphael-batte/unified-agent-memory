"""Pointer provenance classes for Open threads."""

from __future__ import annotations

from typing import Any

STRONG_POINTER_SOURCES = frozenset({"user_commitment", "todo_state"})
AGENT_LIVE_POINTER_SOURCE = "agent_live"
PROVENANCE_CURATED = "curated"
PROVENANCE_STRONG_SIGNAL = "strong_signal"
PROVENANCE_AGENT_LIVE = "agent_live"
PROVENANCE_AUTO = "auto"
# Backward-compatible alias (v0.15–0.17 manifest values)
PROVENANCE_LIVE = PROVENANCE_STRONG_SIGNAL

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
