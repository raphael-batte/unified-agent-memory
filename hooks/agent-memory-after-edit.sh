#!/usr/bin/env bash
# afterFileEdit — log memory-relevant file saves (chats hub).
set -euo pipefail

_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$_HOOK_DIR/hook_env.sh"
FRAMEWORK="$(resolve_hook_plugin_root)" || exit 0
LOG="${AGENT_MEMORY_EDIT_LOG:-$HOME/.cursor/hooks/agent-memory-edit.log}"

python3 - "$LOG" "$FRAMEWORK" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

log_path = Path(sys.argv[1])
framework = Path(sys.argv[2])

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = (
    data.get("filePath")
    or data.get("file_path")
    or data.get("path")
    or data.get("file")
    or ""
)
if not path:
    sys.exit(0)

p = Path(path).resolve()
name = p.name
parts = {x.lower() for x in p.parts}

memory_hit = False
kind = ""
if "chats" in parts and p.suffix == ".md":
    memory_hit = True
    kind = "chat"
elif name == "manifest.json" and "chats" in parts:
    memory_hit = True
    kind = "manifest"

if not memory_hit:
    sys.exit(0)

log_path.parent.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
line = f"{stamp} [{kind}] saved {p}"
with log_path.open("a", encoding="utf-8") as fh:
    fh.write(line + "\n")

msg = f"[agent-memory] {kind} updated — see {log_path}"
print(msg)
print(msg, file=sys.stderr)

if kind in ("chat", "manifest") and framework.is_dir():
    verify = framework / "scripts" / "verify-memory.py"
    if verify.is_file():
        hint = (
            f"[agent-memory] consider: python3 {verify} "
            f"--memory-home $MEMORY_HOME"
        )
        print(hint)
        print(hint, file=sys.stderr)
PY

exit 0
