#!/usr/bin/env bash
# sessionStart — catch-up distill for open workspace (background).
set -euo pipefail

_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$_HOOK_DIR/hook_env.sh"
FRAMEWORK="$(resolve_hook_plugin_root)" || {
  echo "[agent-memory] plugin root unknown — install plugin or run install-local.sh" >&2
  printf '%s\n' '{}'
  exit 0
}
LOG="${AGENT_MEMORY_SESSION_START_LOG:-$HOME/.cursor/hooks/agent-memory-session-start.log}"

INPUT="$(cat)"
TMPERR="$(mktemp)"
trap 'rm -f "$TMPERR"' EXIT
EXIT=0
RESULT="$(python3 "$FRAMEWORK/scripts/boundary-hooks.py" session-start <<<"$INPUT" 2>"$TMPERR")" || EXIT=$?

if [[ $EXIT -ne 0 ]] || ! echo "$RESULT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  python3 "$FRAMEWORK/scripts/boundary-crash-report.py" \
    --mode session-start --event sessionStart --exit-code "$EXIT" \
    --detail "invalid or empty session-start JSON" --stderr-file "$TMPERR" 2>/dev/null || true
  RESULT='{}'
fi

mkdir -p "$(dirname "$LOG")"
{
  echo "$(date '+%Y-%m-%d %H:%M:%S') session-start exit=$EXIT"
  if [[ -s "$TMPERR" ]]; then
    echo "--- stderr ---"
    cat "$TMPERR"
    echo "--- stdout ---"
  fi
  echo "$RESULT"
} >>"$LOG"

if echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('user_message') else 1)" 2>/dev/null; then
  USER_MSG="$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('user_message',''))")"
  printf '%s\n' "{\"user_message\": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$USER_MSG")}"
else
  printf '%s\n' '{}'
fi

exit 0
