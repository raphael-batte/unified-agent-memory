#!/usr/bin/env bash
# Bootstrap external memory hub from templates (idempotent — never overwrites user data).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$REPO_ROOT/INSTRUCTIONS.md" ]]; then
  echo "Error: not a plugin bundle: $REPO_ROOT" >&2
  exit 1
fi

PLUGIN_ROOT="$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from lib.memory_config import resolve_plugin_root
r = resolve_plugin_root(script_file='$SCRIPT_DIR/init-memory.sh')
print(r or '')
")"

if [[ -z "$PLUGIN_ROOT" ]]; then
  echo "Error: could not resolve plugin root" >&2
  exit 1
fi

MEMORY_HOME="$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from lib.memory_config import resolve_memory_home
print(resolve_memory_home('${MEMORY_HOME:-}' or None, script_file='$SCRIPT_DIR/init-memory.sh'))
")"

TEMPLATES="$PLUGIN_ROOT/templates"
MANIFEST="$MEMORY_HOME/chats/manifest.json"
ANCHOR_FILE="$HOME/.cursor/agent-memory/config.json"

echo "Agent Memory — init"
echo "  Plugin:    $PLUGIN_ROOT"
echo "  Hub:       $MEMORY_HOME"
echo "  Anchor:    $ANCHOR_FILE"
echo

copy_tree() {
  local src="$1" dst="$2"
  mkdir -p "$dst"
  if command -v rsync &>/dev/null; then
    rsync -a --ignore-existing "$src/" "$dst/"
  else
    cp -Rn "$src/." "$dst/" 2>/dev/null || true
  fi
}

mkdir -p "$MEMORY_HOME"
copy_tree "$TEMPLATES/context" "$MEMORY_HOME/context"
copy_tree "$TEMPLATES/chats" "$MEMORY_HOME/chats"
copy_tree "$TEMPLATES/feedback" "$MEMORY_HOME/feedback"

if [[ ! -f "$MEMORY_HOME/config.json" ]]; then
  cp "$TEMPLATES/config.json" "$MEMORY_HOME/config.json"
  echo "  created: hub config.json"
else
  echo "  kept:    hub config.json"
fi

python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from pathlib import Path
from lib.memory_config import persist_paths
persist_paths(Path('$PLUGIN_ROOT'), Path('$MEMORY_HOME'))
"

mkdir -p "$MEMORY_HOME/chats/projects" "$MEMORY_HOME/chats/archive"
mkdir -p "$MEMORY_HOME/feedback/archive"
mkdir -p "$MEMORY_HOME/scripts" "$MEMORY_HOME/skills" "$MEMORY_HOME/sources"
mkdir -p "$MEMORY_HOME/logs" "$MEMORY_HOME/.state"

if [[ ! -f "$MANIFEST" ]]; then
  cp "$TEMPLATES/chats/manifest.json" "$MANIFEST"
  echo "  created: chats/manifest.json"
else
  echo "  kept:    chats/manifest.json"
fi

for script in list-chats.py verify-memory.py memory-status.py; do
  cp -f "$PLUGIN_ROOT/scripts/$script" "$MEMORY_HOME/scripts/$script"
  chmod +x "$MEMORY_HOME/scripts/$script"
done
cp -rf "$PLUGIN_ROOT/scripts/lib" "$MEMORY_HOME/scripts/"

touch "$MEMORY_HOME/sources/.gitkeep" 2>/dev/null || true

if [[ ! -f "$MEMORY_HOME/README.md" ]]; then
  cat > "$MEMORY_HOME/README.md" <<EOF
# Personal Memory Hub

User data for [agent-memory]($PLUGIN_ROOT). **Outside the plugin bundle — survives updates.**

- \`context/\` — identity, rules, preferences
- \`feedback/\` — wins (+) and fails (−)
- \`chats/\` — distilled history + \`manifest.json\`

Anchor: \`$ANCHOR_FILE\`
EOF
fi

echo
echo "Done."
echo "  Hub:    $MEMORY_HOME"
echo "  Anchor: $ANCHOR_FILE"
echo "  Sync:   say 'sync with agent memory' in Cursor"
