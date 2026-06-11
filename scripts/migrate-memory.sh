#!/usr/bin/env bash
# Migrate data hub from an old path to MEMORY_HOME (manifest merge + template-aware).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$REPO_ROOT/.cursor-plugin/plugin.json" ]]; then
  echo "Error: not a plugin bundle: $REPO_ROOT" >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/migrate-memory.py" "$@"
