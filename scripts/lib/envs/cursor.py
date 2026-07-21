"""Cursor environment rules.

Cursor dropped hook support in June 2026, so this environment is **cron triggered**:
a launchd job runs `scripts/sync-if-cursor-open.sh` every 2 hours. The event names below
are still honoured for manual/legacy invocations of `boundary-hooks.py`.

This module only declares rules and delegates — Cursor's parsing and sync logic stays
where it is (`lib/transcript_cursor.py`, `scripts/sync-if-cursor-open.sh`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib import transcript_cursor
from lib.envs.base import CANONICAL_EVENTS, TRIGGER_CRON, AgentEnv


class CursorEnv(AgentEnv):
    name = "cursor"
    trigger_kind = TRIGGER_CRON
    root_env_var = "AGENT_MEMORY_CURSOR_PROJECTS"

    def default_transcript_root(self) -> Path:
        return Path.home() / ".cursor" / "projects"

    def build_transcript_index(self, root: Path | None = None) -> dict[str, Path]:
        return transcript_cursor.build_transcript_index(root or self.transcript_root())

    def find_transcript(
        self, uuid: str, root: Path | None = None, *, use_cache: bool = True
    ) -> Path | None:
        return transcript_cursor.find_transcript(
            uuid, root or self.transcript_root(), use_cache=use_cache
        )

    def workspace_from_path(self, jsonl: Path, root: Path | None = None) -> str:
        """Layout: <root>/<workspace>/agent-transcripts/[…]/<chat>.jsonl"""
        found = transcript_cursor.workspace_from_path(jsonl, root or self.transcript_root())
        if found != "unknown":
            return found
        parts = jsonl.parts
        return parts[-4] if len(parts) >= 4 else "unknown"

    def is_ignored(self, jsonl: Path) -> bool:
        return "/subagents/" in str(jsonl)

    def anchor_dir(self) -> Path:
        return Path.home() / ".cursor" / "agent-memory"

    def normalize_event(self, payload: dict[str, Any]) -> str | None:
        event = payload.get("hook_event_name")
        if isinstance(event, str) and event in CANONICAL_EVENTS:
            return event
        return None

    def format_output(self, event: str, result: dict[str, Any]) -> dict[str, Any]:
        """Cursor reads `user_message` from hook stdout."""
        message = result.get("user_message")
        return {"user_message": message} if message else {}


ENV = CursorEnv()
