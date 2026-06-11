#!/usr/bin/env bash
# Delivery only — symlink plugin bundle into Cursor local plugins. No bootstrap.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_NAME="agent-memory"
TARGET="${CURSOR_PLUGINS_LOCAL:-$HOME/.cursor/plugins/local}/$PLUGIN_NAME"

if [[ ! -f "$SRC/.cursor-plugin/plugin.json" ]]; then
  echo "Error: not a plugin bundle (missing .cursor-plugin/plugin.json): $SRC" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  rm -rf "$TARGET"
fi
ln -sfn "$SRC" "$TARGET"

echo "Agent Memory — local plugin install"
echo "  Bundle:  $SRC"
echo "  Linked:  $TARGET"
echo
echo "Next:"
echo "  1. Reload Cursor window (Developer: Reload Window)"
echo "  2. bash $SRC/scripts/init-memory.sh   # hub + anchor (idempotent)"
echo "  3. In chat: sync with agent memory"
