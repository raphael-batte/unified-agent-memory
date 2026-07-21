"""Environment registry — resolve which agent harness we are running under."""

from __future__ import annotations

import os
from pathlib import Path

from lib.envs.base import (
    CANONICAL_EVENTS,
    TRIGGER_CRON,
    TRIGGER_HOOKS,
    AgentEnv,
)
from lib.envs.claude import ENV as CLAUDE_ENV
from lib.envs.cursor import ENV as CURSOR_ENV

__all__ = [
    "CANONICAL_EVENTS",
    "TRIGGER_CRON",
    "TRIGGER_HOOKS",
    "AgentEnv",
    "CLAUDE_ENV",
    "CURSOR_ENV",
    "all_envs",
    "available_envs",
    "detect_env",
    "get_env",
    "transcript_roots",
]

_REGISTRY: dict[str, AgentEnv] = {
    CURSOR_ENV.name: CURSOR_ENV,
    CLAUDE_ENV.name: CLAUDE_ENV,
}

#: Default when nothing identifies the caller — keeps legacy Cursor behaviour.
DEFAULT_ENV_NAME = CURSOR_ENV.name


def all_envs() -> list[AgentEnv]:
    return list(_REGISTRY.values())


def available_envs() -> list[AgentEnv]:
    """Environments actually installed on this machine (transcript root exists)."""
    return [env for env in _REGISTRY.values() if env.is_available()]


def get_env(name: str) -> AgentEnv:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown agent environment: {name}") from None


def detect_env() -> AgentEnv:
    """Which harness is invoking us — explicit override wins, then harness markers."""
    forced = os.environ.get("AGENT_MEMORY_ENV", "").strip()
    if forced:
        return get_env(forced)
    if os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip():
        return CLAUDE_ENV
    if os.environ.get("CLAUDE_PROJECT_DIR", "").strip():
        return CLAUDE_ENV
    return _REGISTRY[DEFAULT_ENV_NAME]


def transcript_roots(*, only_available: bool = True) -> list[Path]:
    """Every transcript root to scan — the hub is shared across environments."""
    envs = available_envs() if only_available else all_envs()
    roots: list[Path] = []
    seen: set[str] = set()
    for env in envs:
        root = env.transcript_root()
        key = str(root)
        if key not in seen:
            seen.add(key)
            roots.append(root)
    return roots
