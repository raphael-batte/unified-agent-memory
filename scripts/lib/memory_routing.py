"""Session read order — distill-first (forward pointer lives in chats/projects/)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def session_read_layers(
    *,
    workspace_slug: str | None = None,
) -> list[str]:
    """
    Ordered layer names for session start.
    Values: distill (includes ## Next step), global-context, feedback.
    """
    layers: list[str] = ["distill"]
    if not workspace_slug:
        layers.append("global-context")
    return layers


def routing_summary(memory_home: Path) -> dict[str, Any]:
    return {"memory_home": str(memory_home)}
