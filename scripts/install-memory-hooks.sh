#!/usr/bin/env bash
# LEGACY: merge hooks into ~/.cursor/hooks.json — plugin bundle provides hooks/hooks.json.
set -euo pipefail

echo "[agent-memory] deprecated: plugin hooks in hooks/ — use install-local.sh" >&2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/config.sh
source "$SCRIPT_DIR/lib/config.sh"
CURSOR_DIR="${CURSOR_DIR:-$HOME/.cursor}"
HOOKS_DIR="$CURSOR_DIR/hooks"
HOOKS_JSON="$CURSOR_DIR/hooks.json"
HOOKS_TEMPLATE="$REPO_ROOT/templates/cursor-hooks"

usage() {
  echo "Usage: $0 [--dry-run]"
  echo "Templates (same names as installed):"
  echo "  agent-memory-session-start.sh → sessionStart"
  echo "  agent-memory-boundary.sh      → preCompact, sessionEnd"
  echo "  agent-memory-session-end.sh   → sessionEnd (checklist)"
  echo "  agent-memory-after-edit.sh    → afterFileEdit"
  exit 1
}

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage
[[ -n "${1:-}" && "$1" != "--dry-run" ]] && usage

for name in agent-memory-session-start.sh agent-memory-boundary.sh \
  agent-memory-session-end.sh agent-memory-after-edit.sh; do
  if [[ ! -f "$HOOKS_TEMPLATE/$name" ]]; then
    echo "Missing template: $HOOKS_TEMPLATE/$name" >&2
    exit 1
  fi
done

if [[ "$DRY" -eq 1 ]]; then
  echo "would mkdir -p $HOOKS_DIR"
  echo "would cp agent-memory-session-start.sh agent-memory-boundary.sh"
  echo "would cp agent-memory-session-end.sh agent-memory-after-edit.sh"
  python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/scripts')
from lib.hooks_config import merge_hooks_file
from pathlib import Path
print(merge_hooks_file(Path('$HOOKS_JSON'), dry_run=True))
"
  exit 0
fi

mkdir -p "$HOOKS_DIR"
cp "$HOOKS_TEMPLATE/agent-memory-session-start.sh" "$HOOKS_DIR/"
cp "$HOOKS_TEMPLATE/agent-memory-boundary.sh" "$HOOKS_DIR/"
cp "$HOOKS_TEMPLATE/agent-memory-session-end.sh" "$HOOKS_DIR/"
cp "$HOOKS_TEMPLATE/agent-memory-after-edit.sh" "$HOOKS_DIR/"
chmod +x "$HOOKS_DIR/agent-memory-session-start.sh" \
  "$HOOKS_DIR/agent-memory-boundary.sh" \
  "$HOOKS_DIR/agent-memory-session-end.sh" \
  "$HOOKS_DIR/agent-memory-after-edit.sh"

FRAMEWORK_ROOT="$(resolve_framework_root "" "$REPO_ROOT")"
if [[ -z "$FRAMEWORK_ROOT" ]]; then
  FRAMEWORK_ROOT="$REPO_ROOT"
fi
MEMORY_HOME="$(resolve_memory_home "" "$FRAMEWORK_ROOT")"
write_cursor_hook_env "$FRAMEWORK_ROOT" "$MEMORY_HOME"
ENV_FILE="$HOOKS_DIR/agent-memory.env"

python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/scripts')
from lib.hooks_config import merge_hooks_file
from pathlib import Path
import json
r = merge_hooks_file(Path('$HOOKS_JSON'), dry_run=False)
print(json.dumps(r))
"

echo "Installed hooks:"
echo "  $HOOKS_DIR/agent-memory-session-start.sh"
echo "  $HOOKS_DIR/agent-memory-boundary.sh"
echo "  $HOOKS_DIR/agent-memory-session-end.sh"
echo "  $HOOKS_DIR/agent-memory-after-edit.sh"
echo "Framework env: $ENV_FILE"
echo "Session-start: $HOOKS_DIR/agent-memory-session-start.log"
echo "Boundary log:  $HOOKS_DIR/agent-memory-boundary.log"
echo "Session log:   $HOOKS_DIR/agent-memory-session.log"
echo "Edit log:      $HOOKS_DIR/agent-memory-edit.log"
echo "Reload Cursor window to activate hooks."
