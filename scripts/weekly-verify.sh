#!/usr/bin/env bash
# Weekly cron helper — strict secrets + optional gitleaks + doctor summary.
# Example crontab (Sunday 09:00):
#   0 9 * * 0 cd /path/to/cursor-agent-memory && bash scripts/weekly-verify.sh
set -euo pipefail

usage() {
  echo "Usage: $0 [--dry-run]"
  echo "  MEMORY_HOME  defaults to <clone>/memory/"
  echo "  AGENT_MEMORY_WEEKLY_LOG  log dir (default: \$MEMORY_HOME/logs)"
  exit 0
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1
[[ -n "${1:-}" && "$1" != "--dry-run" ]] && { echo "Unknown arg: $1" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/config.sh
source "$SCRIPT_DIR/lib/config.sh"
FRAMEWORK="$REPO_ROOT"
MEMORY_HOME="$(resolve_memory_home "${MEMORY_HOME:-}")"

if [[ "$DRY" -eq 1 ]]; then
  echo "would run memory-doctor --strict-secrets --gitleaks"
  echo "would run verify-memory --strict-secrets --gitleaks -q"
  echo "would run memory-health.py --update-baseline --strict --notify"
  echo "MEMORY_HOME=$MEMORY_HOME"
  exit 0
fi

LOG_DIR="${AGENT_MEMORY_WEEKLY_LOG:-$MEMORY_HOME/logs}"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/weekly-verify-$STAMP.log"

{
  echo "=== weekly-verify $STAMP ==="
  echo "MEMORY_HOME=$MEMORY_HOME"
  echo
  python3 "$FRAMEWORK/scripts/memory-doctor.py" --memory-home "$MEMORY_HOME" --strict-secrets --gitleaks
  echo
  python3 "$FRAMEWORK/scripts/verify-memory.py" --memory-home "$MEMORY_HOME" --strict-secrets --gitleaks -q
  echo
  python3 "$FRAMEWORK/scripts/memory-health.py" --memory-home "$MEMORY_HOME" --update-baseline --strict --notify
  echo
  echo "done"
} 2>&1 | tee "$LOG_FILE"

echo "Log: $LOG_FILE"
