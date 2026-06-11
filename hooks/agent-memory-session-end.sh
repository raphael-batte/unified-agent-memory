#!/usr/bin/env bash
# sessionEnd — checklist after boundary distill.
set -euo pipefail

_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$_HOOK_DIR/hook_env.sh"
FRAMEWORK="$(resolve_hook_plugin_root)" || {
  echo "[agent-memory] plugin root unknown" >&2
  exit 0
}
MEMORY_HOME="$(resolve_hook_memory_home 2>/dev/null || true)"
LOG="${AGENT_MEMORY_SESSION_LOG:-$HOME/.cursor/hooks/agent-memory-session.log}"

if [[ -z "$MEMORY_HOME" ]]; then
  echo "[agent-memory] memory hub unknown — run init-memory.sh" >&2
  exit 0
fi

emit() {
  echo "$1"
  echo "$1" >&2
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

mkdir -p "$(dirname "$LOG")"
emit "[agent-memory] Session end — boundary distill updates Recent + ## Next step"
emit "  1. Review merge-staging/ if Decisions need curation"
emit "  2. verify-memory.py --memory-home $MEMORY_HOME"

if [[ -f "$FRAMEWORK/scripts/list-chats.py" ]]; then
  pending="$(python3 "$FRAMEWORK/scripts/list-chats.py" --memory-home "$MEMORY_HOME" 2>/dev/null | head -1 || true)"
  if [[ -n "$pending" ]]; then
    emit "  Chats: $pending"
  fi
fi

exit 0
