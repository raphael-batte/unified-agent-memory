#!/usr/bin/env bash
# Path resolution — delegates to scripts/lib/memory_config.py (plugin + anchor).

_expand_tilde() {
  local p="$1"
  if [[ "$p" == "~" ]]; then
    printf '%s' "$HOME"
  elif [[ "$p" == "~/"* ]]; then
    printf '%s' "$HOME/${p#~/}"
  else
    printf '%s' "$p"
  fi
}

_resolve_scripts_dir() {
  if [[ -n "${SCRIPT_DIR:-}" ]]; then
    echo "$SCRIPT_DIR"
    return
  fi
  # Always anchor on this file (scripts/lib/config.sh → scripts/), not the caller.
  local lib_dir
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ "$(basename "$lib_dir")" == "lib" ]]; then
    echo "$(dirname "$lib_dir")"
  else
    echo "$lib_dir"
  fi
}

_py_paths() {
  local scripts_dir override memory_override
  scripts_dir="$(_resolve_scripts_dir)"
  override="${1:-}"
  memory_override="${2:-}"
  python3 -c "
import sys
sys.path.insert(0, '${scripts_dir}')
from lib.memory_config import resolve_memory_home, resolve_plugin_root
mem = resolve_memory_home(
    '${memory_override}' or None or None,
    script_file='${scripts_dir}/init-memory.sh',
)
plugin = resolve_plugin_root(
    '${override}' or None,
    script_file='${scripts_dir}/init-memory.sh',
    memory_home=mem,
) or resolve_plugin_root(script_file='${scripts_dir}/init-memory.sh')
print(plugin or '')
print(mem)
"
}

resolve_plugin_root() {
  local override="${1:-}"
  local scripts_dir
  scripts_dir="$(_resolve_scripts_dir)"
  python3 -c "
import sys
sys.path.insert(0, '${scripts_dir}')
from lib.memory_config import resolve_plugin_root
r = resolve_plugin_root('${override}' or None, script_file='${scripts_dir}/init-memory.sh')
print(r or '')
"
}

resolve_framework_root() {
  resolve_plugin_root "$@"
}

resolve_memory_home() {
  local override="${1:-}"
  local scripts_dir
  scripts_dir="$(_resolve_scripts_dir)"
  python3 -c "
import sys
sys.path.insert(0, '${scripts_dir}')
from lib.memory_config import resolve_memory_home
print(resolve_memory_home('${override}' or None, script_file='${scripts_dir}/init-memory.sh'))
"
}

write_hub_config_paths() {
  local plugin_root="$1"
  local memory_home="${2:-}"
  local scripts_dir
  scripts_dir="$(_resolve_scripts_dir)"
  python3 -c "
import sys
sys.path.insert(0, '${scripts_dir}')
from pathlib import Path
from lib.memory_config import persist_paths
persist_paths(Path('${plugin_root}'), Path('${memory_home}'))
"
}

# Legacy — prefer plugin hooks; kept for migration cleanup only
write_cursor_hook_env() {
  local plugin_root="$1"
  local memory_home="${2:-$plugin_root/memory}"
  local hooks_dir="${CURSOR_DIR:-$HOME/.cursor}/hooks"
  mkdir -p "$hooks_dir"
  {
    printf 'AGENT_MEMORY_FRAMEWORK=%s\n' "$plugin_root"
    printf 'MEMORY_HOME=%s\n' "$memory_home"
  } > "$hooks_dir/agent-memory.env"
  echo "[agent-memory] deprecated: wrote $hooks_dir/agent-memory.env — use plugin hooks + anchor" >&2
}
