#!/usr/bin/env bash
# Post-upgrade smoke: doctor, verify, optional search sample.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_HOME="${MEMORY_HOME:-$HOME/.cursor/agent-memory}"

echo "Agent Memory — hub upgrade verify"
echo "  Hub: $MEMORY_HOME"
echo

python3 "$SCRIPT_DIR/memory-doctor.py" --memory-home "$MEMORY_HOME"
python3 "$SCRIPT_DIR/verify-memory.py" --memory-home "$MEMORY_HOME"
python3 "$SCRIPT_DIR/memory-search.py" "deploy" --memory-home "$MEMORY_HOME" --top 3 || true

echo
echo "OK — hub compatible with current framework"
