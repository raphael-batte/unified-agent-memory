"""Claude Code environment rules.

Claude Code is **hook triggered**: the harness runs our commands on real events and
passes JSON on stdin. That is richer than Cursor's cron path — `Stop` gives per-turn
distill and `PreCompact` (trigger=auto) fires exactly when the context window fills,
so memory survives compaction and hard session kills, not just a clean exit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib import transcript_claude
from lib.envs.base import (
    EVENT_AFTER_EDIT,
    EVENT_LIVE_DISTILL,
    EVENT_PRE_COMPACT,
    EVENT_PROMPT_SUBMIT,
    EVENT_SESSION_END,
    EVENT_SESSION_START,
    TRIGGER_HOOKS,
    AgentEnv,
)

#: Claude Code hook event -> canonical internal event.
EVENT_MAP: dict[str, str] = {
    "SessionStart": EVENT_SESSION_START,
    "UserPromptSubmit": EVENT_PROMPT_SUBMIT,
    "Stop": EVENT_LIVE_DISTILL,
    "PreCompact": EVENT_PRE_COMPACT,
    "SessionEnd": EVENT_SESSION_END,
    "PostToolUse": EVENT_AFTER_EDIT,
}

_REVERSE_EVENT_MAP: dict[str, str] = {v: k for k, v in EVENT_MAP.items()}


class ClaudeEnv(AgentEnv):
    name = "claude"
    trigger_kind = TRIGGER_HOOKS
    root_env_var = "AGENT_MEMORY_CLAUDE_PROJECTS"

    def default_transcript_root(self) -> Path:
        return Path.home() / ".claude" / "projects"

    def build_transcript_index(self, root: Path | None = None) -> dict[str, Path]:
        return transcript_claude.build_transcript_index(root or self.transcript_root())

    def find_transcript(self, uuid: str, root: Path | None = None) -> Path | None:
        return transcript_claude.find_transcript(uuid, root or self.transcript_root())

    def anchor_dir(self) -> Path:
        return Path.home() / ".claude" / "agent-memory"

    def normalize_event(self, payload: dict[str, Any]) -> str | None:
        event = payload.get("hook_event_name")
        if not isinstance(event, str):
            return None
        return EVENT_MAP.get(event)

    def workspace_roots(self, payload: dict[str, Any]) -> list[str]:
        """Claude sends a single `cwd` rather than Cursor's `workspace_roots` list."""
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            return [cwd.strip()]
        return super().workspace_roots(payload)

    def format_output(self, event: str, result: dict[str, Any]) -> dict[str, Any]:
        """Claude injects context via `hookSpecificOutput.additionalContext`."""
        message = result.get("user_message")
        if not message:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": _REVERSE_EVENT_MAP.get(event, event),
                "additionalContext": message,
            }
        }


ENV = ClaudeEnv()
