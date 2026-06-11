#!/usr/bin/env bash
# Sourced by installed Cursor hooks — resolve FRAMEWORK without a fixed install path.
# Usage: source "$(dirname "$0")/hook_env.sh"  (from ~/.cursor/hooks/*.sh)

_hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$_hook_dir/agent-memory.env" ]]; then
  # shellcheck disable=SC1091
  source "$_hook_dir/agent-memory.env"
fi

resolve_hook_memory_home() {
  if [[ -n "${MEMORY_HOME:-}" && -d "${MEMORY_HOME}" ]]; then
    echo "$(cd "${MEMORY_HOME}" && pwd)"
    return 0
  fi
  local fw
  fw="$(resolve_hook_framework 2>/dev/null || true)"
  if [[ -n "$fw" && -d "$fw/memory" ]]; then
    echo "$(cd "$fw/memory" && pwd)"
    return 0
  fi
  return 1
}

resolve_hook_framework() {
  if [[ -n "${AGENT_MEMORY_FRAMEWORK:-}" && -d "${AGENT_MEMORY_FRAMEWORK}" ]]; then
    echo "$(cd "${AGENT_MEMORY_FRAMEWORK}" && pwd)"
    return 0
  fi
  if [[ -n "${FRAMEWORK_ROOT:-}" && -d "${FRAMEWORK_ROOT}" ]]; then
    echo "$(cd "${FRAMEWORK_ROOT}" && pwd)"
    return 0
  fi
  if command -v python3 &>/dev/null; then
    local resolved
    resolved="$(python3 - <<'PY' 2>/dev/null || true
import json
import os
from pathlib import Path

def ok(path: str) -> str | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if p.is_dir() and (p / "INSTRUCTIONS.md").is_file():
        return str(p.resolve())
    return None

for key in ("FRAMEWORK_ROOT", "AGENT_MEMORY_FRAMEWORK"):
    hit = ok(os.environ.get(key, ""))
    if hit:
        print(hit)
        raise SystemExit(0)

global_cfg = Path.home() / ".config" / "cursor-agent-memory" / "config.json"
if global_cfg.is_file():
    data = json.loads(global_cfg.read_text(encoding="utf-8"))
    hit = ok(str(data.get("framework_root", "")).strip())
    if hit:
        print(hit)
        raise SystemExit(0)
    hub = ok(str(data.get("memory_home", "")).strip())
    if hub:
        hub_cfg = Path(hub) / "config.json"
        if hub_cfg.is_file():
            hdata = json.loads(hub_cfg.read_text(encoding="utf-8"))
            hit = ok(str(hdata.get("framework_root", "")).strip())
            if hit:
                print(hit)
PY
)"
    if [[ -n "$resolved" ]]; then
      echo "$resolved"
      return 0
    fi
  fi
  return 1
}
