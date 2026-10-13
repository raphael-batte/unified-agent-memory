#!/usr/bin/env bash
# Periodic hub sync — only when Cursor is running; skip if no pending chats.
# Install: bash scripts/install-periodic-sync.sh
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sync-if-cursor-open.sh [--dry-run] [--force]

Runs incremental sync when Cursor is open and there are pending chats.
Designed for launchd StartInterval (default every 30 minutes).

Env:
  MEMORY_HOME              Hub path (via anchor if unset)
  AGENT_MEMORY_SYNC_DAYS   Scan window (default: 7)
  AGENT_MEMORY_SYNC_LIMIT  Max chats per run (default: 5)
  AGENT_MEMORY_CRON_LOG    Append log (default: $MEMORY_HOME/logs/cron-sync.log)
  AGENT_MEMORY_SYNC_FORCE  1 = skip Cursor-running check (testing)

Flags:
  --dry-run   Report actions without syncing
  --force     Same as AGENT_MEMORY_SYNC_FORCE=1
EOF
  exit 0
}

DRY=0
FORCE="${AGENT_MEMORY_SYNC_FORCE:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) usage ;;
    --dry-run) DRY=1; shift ;;
    --force) FORCE=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/config.sh
source "$SCRIPT_DIR/lib/config.sh"

FRAMEWORK="$(resolve_framework_root "${AGENT_MEMORY_FRAMEWORK:-}")"
if [[ -z "$FRAMEWORK" ]]; then
  FRAMEWORK="$REPO_ROOT"
fi
MEMORY_HOME="$(resolve_memory_home "${MEMORY_HOME:-}")"
DAYS="${AGENT_MEMORY_SYNC_DAYS:-7}"
LIMIT="${AGENT_MEMORY_SYNC_LIMIT:-5}"
LOG="${AGENT_MEMORY_CRON_LOG:-$MEMORY_HOME/logs/cron-sync.log}"
LOCK_DIR="$MEMORY_HOME/.state/periodic-sync.lock"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() {
  local line
  line="$(ts) $*"
  mkdir -p "$(dirname "$LOG")"
  echo "$line" >>"$LOG"
  echo "$line"
}

cursor_running() {
  if pgrep -f "/Applications/Cursor.app/Contents/MacOS/Cursor" >/dev/null 2>&1; then
    return 0
  fi
  pgrep -x Cursor >/dev/null 2>&1
}

pending_count() {
  python3 -c "
import sys
sys.path.insert(0, '${FRAMEWORK}/scripts')
from pathlib import Path
from lib.memory_config import resolve_memory_home
from lib.pending_chats import list_chats_needing_distill

mh = resolve_memory_home('${MEMORY_HOME}')
print(len(list_chats_needing_distill(mh, days=int('${DAYS}'), limit=None)))
"
}

if [[ "$FORCE" != "1" ]]; then
  if ! cursor_running; then
    log "skip: Cursor not running"
    exit 0
  fi
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "skip: sync already running (lock $LOCK_DIR)"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# Snapshot what Cursor's agent can see and score chats that are due — cheap,
# and needed even when there is nothing new to distill.
if [[ "$DRY" -eq 0 ]]; then
  python3 "$FRAMEWORK/scripts/pointer-effect.py" --memory-home "$MEMORY_HOME" --cron \
    >>"$LOG" 2>&1 || log "pointer-effect: failed (non-fatal)"
fi

pending="$(pending_count)"
if [[ "$pending" -eq 0 ]]; then
  log "skip: no pending chats (days=$DAYS)"
  exit 0
fi

if [[ "$DRY" -eq 1 ]]; then
  log "dry-run: would sync pending=$pending days=$DAYS limit=$LIMIT hub=$MEMORY_HOME"
  exit 0
fi

log "sync start pending=$pending days=$DAYS limit=$LIMIT"
set +e
python3 "$FRAMEWORK/scripts/sync-memory.py" \
  --memory-home "$MEMORY_HOME" \
  --framework-root "$FRAMEWORK" \
  --days "$DAYS" \
  --limit "$LIMIT" \
  --no-hooks \
  >>"$LOG" 2>&1
rc=$?
set -e
log "sync done exit=$rc pending_before=$pending"
exit "$rc"
