#!/usr/bin/env bash
# Claude Code hook entry point — one wrapper for every event.
#
# Usage: agent-memory-hook.sh [session-start|boundary]
#
# Claude passes the event JSON on stdin and reads our reply from stdout. A memory
# plugin must never break a session, so this always exits 0 and always prints valid
# JSON, even when the distill fails.
#
# The mode is derived from the payload's hook_event_name. An explicit argument
# overrides it, but we do not depend on one: if the harness ignored the `args` field
# we would silently run SessionStart in boundary mode, where it is a no-op, and the
# bootstrap would never happen with nothing in the logs to show for it.
set -uo pipefail

MODE_ARG="${1:-}"

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
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
# Restrictive mode — the log may sit under ~/.claude and must not leak prompts.
touch "$LOG" 2>/dev/null || true
chmod 600 "$LOG" 2>/dev/null || true
INPUT="$(cat)"

EVENT="$(
  python3 -c 'import json,sys
try:
    print(json.loads(sys.stdin.read()).get("hook_event_name") or "")
except Exception:
    print("")' <<<"$INPUT" 2>/dev/null || true
)"

if [[ -n "$MODE_ARG" ]]; then
  MODE="$MODE_ARG"
elif [[ "$EVENT" == "SessionStart" ]]; then
  MODE="session-start"
else
  MODE="boundary"
fi

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

# Never log raw stdin — UserPromptSubmit payloads can carry the user's prompt.
# Event name + byte length is enough to tell empty vs malformed vs ok.
{
  printf '%s %s exit=%s event=%s stdin=%sB\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE" "$EXIT" "${EVENT:-none}" "${#INPUT}"
  if [[ -z "${INPUT//[[:space:]]/}" ]]; then
    echo "--- empty stdin: hook received no payload ---"
  elif [[ $EXIT -ne 0 ]]; then
    echo "--- failure: payload not logged (PII) ---"
  fi
  if [[ -s "$TMPERR" ]]; then
    echo "--- stderr ---"
    cat "$TMPERR"
  fi
} >>"$LOG" 2>/dev/null || true

printf '%s\n' "$RESULT"
exit 0
