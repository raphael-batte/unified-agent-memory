#!/usr/bin/env bash
# Generate workspace Cursor rule with resolved MEMORY_HOME and workspace slug.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Paths resolved via Python (reads hook env file without polluting shell MEMORY_HOME)

TEMPLATE="$REPO_ROOT/templates/cursor-rule/agent-memory-session-start.mdc.in"
RULE_NAME="agent-memory-session-start.mdc"

usage() {
  echo "Usage: $0 --project /path/to/workspace [--slug SLUG] [--dry-run]"
  echo "Writes: <project>/.cursor/rules/$RULE_NAME"
  exit 1
}

PROJECT=""
SLUG=""
DRY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown: $1" >&2; usage ;;
  esac
done

[[ -n "$PROJECT" ]] || usage
PROJECT="$(cd "$(eval echo "$PROJECT")" && pwd)"

SCRIPT_PATH="$SCRIPT_DIR/init-project-rules.sh"
unset MEMORY_HOME FRAMEWORK_ROOT AGENT_MEMORY_FRAMEWORK AGENT_MEMORY_INSTALL 2>/dev/null || true
PATH_LINES="$(
  python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '${SCRIPT_DIR}')
from lib.memory_config import resolve_framework_root, resolve_memory_home
script = '${SCRIPT_PATH}'
hub = resolve_memory_home(None, script_file=script)
fw = resolve_framework_root(script_file=script, memory_home=hub) or Path('${REPO_ROOT}').resolve()
print(fw)
print(hub)
"
)"
FRAMEWORK_ROOT="$(printf '%s\n' "$PATH_LINES" | sed -n '1p')"
MEMORY_HOME="$(printf '%s\n' "$PATH_LINES" | sed -n '2p')"

if [[ -z "$SLUG" ]]; then
  SLUG="$(basename "$PROJECT")"
fi

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Missing template: $TEMPLATE" >&2
  exit 1
fi

DISTILL="$MEMORY_HOME/chats/projects/${SLUG}.md"
if [[ ! -f "$DISTILL" ]]; then
  echo "WARNING: distill not found: $DISTILL" >&2
  echo "Available project distills:" >&2
  if compgen -G "$MEMORY_HOME/chats/projects/"*.md >/dev/null 2>&1; then
    for f in "$MEMORY_HOME/chats/projects/"*.md; do
      basename "${f%.md}"
    done >&2
  else
    echo "  (none yet — run sync first)" >&2
  fi
  echo "Re-run with: $0 --project \"$PROJECT\" --slug <name-from-list>" >&2
  avail=()
  if compgen -G "$MEMORY_HOME/chats/projects/"*.md >/dev/null 2>&1; then
    while IFS= read -r f; do avail+=("$(basename "${f%.md}")"); done < <(ls -1 "$MEMORY_HOME/chats/projects/"*.md)
  fi
  if [[ ${#avail[@]} -eq 1 ]]; then
    echo "hint: only distill is '${avail[0]}', use --slug ${avail[0]}" >&2
  fi
else
  echo "OK: distill found: $DISTILL"
fi

OUT_DIR="$PROJECT/.cursor/rules"
OUT_FILE="$OUT_DIR/$RULE_NAME"

rendered="$(sed \
  -e "s|{{MEMORY_HOME}}|$MEMORY_HOME|g" \
  -e "s|{{FRAMEWORK_ROOT}}|$FRAMEWORK_ROOT|g" \
  -e "s|{{WORKSPACE_SLUG}}|$SLUG|g" \
  "$TEMPLATE")"

if [[ "$DRY" -eq 1 ]]; then
  echo "would write: $OUT_FILE"
  printf '%s\n' "$rendered"
  exit 0
fi

mkdir -p "$OUT_DIR"
printf '%s\n' "$rendered" >"$OUT_FILE"
echo "Wrote: $OUT_FILE"
