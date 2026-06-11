#!/usr/bin/env bash
# Sourced by plugin hooks — resolve plugin bundle + external hub.

_hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_hook_plugin_root() {
  local candidate
  candidate="$(cd "$_hook_dir/.." && pwd)"
  if [[ -f "$candidate/.cursor-plugin/plugin.json" ]]; then
    echo "$candidate"
    return 0
  fi
  if command -v python3 &>/dev/null; then
    local resolved
    resolved="$(python3 - "$_hook_dir" <<'PY' 2>/dev/null || true
import sys
from pathlib import Path

hook_dir = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(hook_dir.parent / "scripts"))
from lib.memory_config import detect_plugin_root

root = detect_plugin_root(hook_dir / "hook_env.sh")
if root:
    print(root)
PY
)"
    if [[ -n "$resolved" ]]; then
      echo "$resolved"
      return 0
    fi
  fi
  return 1
}

# Back-compat name used in hook scripts
resolve_hook_framework() {
  resolve_hook_plugin_root
}

resolve_hook_memory_home() {
  local plugin
  plugin="$(resolve_hook_plugin_root)" || return 1
  python3 - "$plugin" <<'PY' 2>/dev/null || return 1
import sys
from pathlib import Path

plugin = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(plugin / "scripts"))
from lib.memory_config import resolve_memory_home

print(resolve_memory_home(None, script_file=plugin / "scripts" / "boundary-hooks.py"))
PY
}
