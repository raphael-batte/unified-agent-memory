"""Agent environment protocol — one module per harness (cursor, claude, codex…).

An environment module declares the *rules of its harness*: where transcripts live, how
they are laid out, what triggers a distill (periodic cron vs event hooks), where its
anchor config sits, and what shape a trigger's payload and reply take.

Everything above this layer (distill, merge, search, Open threads) is environment
agnostic and must not branch on the harness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Canonical internal event names. Harness-specific names normalize onto these.
EVENT_SESSION_START = "sessionStart"
EVENT_PRE_COMPACT = "preCompact"
EVENT_SESSION_END = "sessionEnd"
EVENT_AFTER_EDIT = "afterFileEdit"
EVENT_LIVE_DISTILL = "liveDistill"
EVENT_PROMPT_SUBMIT = "promptSubmit"

CANONICAL_EVENTS = frozenset(
    {
        EVENT_SESSION_START,
        EVENT_PRE_COMPACT,
        EVENT_SESSION_END,
        EVENT_AFTER_EDIT,
        EVENT_LIVE_DISTILL,
        EVENT_PROMPT_SUBMIT,
    }
)

TRIGGER_CRON = "cron"
TRIGGER_HOOKS = "hooks"


class AgentEnv:
    """Base environment. Subclasses declare rules; they do not own distill logic."""

    name: str = "unknown"
    trigger_kind: str = TRIGGER_CRON
    #: Environment variable that overrides the transcript root (testing, custom installs).
    root_env_var: str = ""

    # --- transcripts ---

    def default_transcript_root(self) -> Path:
        raise NotImplementedError

    def transcript_root(self) -> Path:
        import os

        if self.root_env_var:
            override = os.environ.get(self.root_env_var, "").strip()
            if override:
                return Path(override).expanduser()
        return self.default_transcript_root()

    def is_available(self) -> bool:
        """True when this harness is actually installed on the machine."""
        return self.transcript_root().is_dir()

    def build_transcript_index(self, root: Path | None = None) -> dict[str, Path]:
        """Map chat/session id -> newest transcript path."""
        raise NotImplementedError

    def find_transcript(
        self, uuid: str, root: Path | None = None, *, use_cache: bool = True
    ) -> Path | None:
        raise NotImplementedError

    def workspace_from_path(self, jsonl: Path, root: Path | None = None) -> str:
        """Workspace folder id owning this transcript — layout specific."""
        raise NotImplementedError

    def is_ignored(self, jsonl: Path) -> bool:
        """Transcripts that exist but are not this conversation's history."""
        return False

    # --- hub anchor ---

    def anchor_dir(self) -> Path:
        raise NotImplementedError

    # --- triggers ---

    def normalize_event(self, payload: dict[str, Any]) -> str | None:
        """Harness event name -> canonical name, or None when not our concern."""
        raise NotImplementedError

    def workspace_roots(self, payload: dict[str, Any]) -> list[str]:
        """Open workspace paths the payload implies."""
        roots = payload.get("workspace_roots")
        if isinstance(roots, list):
            return [r for r in roots if isinstance(r, str) and r.strip()]
        return []

    def format_output(self, event: str, result: dict[str, Any]) -> dict[str, Any]:
        """Shape a handler result into what this harness expects on stdout."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<AgentEnv {self.name} trigger={self.trigger_kind}>"
