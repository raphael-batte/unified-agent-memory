#!/usr/bin/env bash
# Claude Code hook entry point — one wrapper for every event.
#
# Usage: agent-memory-hook.sh <session-start|boundary>
#
# Claude passes the event JSON on stdin and reads our reply from stdout. A memory
# plugin must never break a session, so this always exits 0 and always prints valid
# JSON, even when the distill fails.
set -uo pipefail

MODE="${1:-boundary}"

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [[ -z "$PLUGIN_ROOT" ]]; then
  _HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PLUGIN_ROOT="$(cd "$_HOOK_DIR/../.." && pwd)"
fi

if [[ ! -f "$PLUGIN_ROOT/scripts/boundary-hooks.py" ]]; then
  echo "[agent-memory] plugin root not found: $PLUGIN_ROOT" >&2
  printf '%s\n' '{}'
  exit 0
fi

LOG="${AGENT_MEMORY_CLAUDE_HOOK_LOG:-$HOME/.claude/agent-memory-hook.log}"
INPUT="$(cat)"

TMPERR="$(mktemp)"
trap 'rm -f "$TMPERR"' EXIT

EXIT=0
RESULT="$(
  AGENT_MEMORY_ENV=claude python3 "$PLUGIN_ROOT/scripts/boundary-hooks.py" \
    "$MODE" --hook-output <<<"$INPUT" 2>"$TMPERR"
)" || EXIT=$?

if [[ $EXIT -ne 0 ]] || ! python3 -c "import json,sys; json.load(sys.stdin)" <<<"$RESULT" 2>/dev/null; then
  RESULT='{}'
fi

{
  printf '%s %s exit=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE" "$EXIT"
  if [[ -s "$TMPERR" ]]; then
    echo "--- stderr ---"
    cat "$TMPERR"
  fi
} >>"$LOG" 2>/dev/null || true

printf '%s\n' "$RESULT"
exit 0
