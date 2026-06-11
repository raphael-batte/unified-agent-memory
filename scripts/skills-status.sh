#!/usr/bin/env bash
# Show framework vs personal skills and Cursor symlink state.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/config.sh
source "$SCRIPT_DIR/lib/config.sh"

MEMORY_HOME_OVERRIDE=""
FRAMEWORK_OVERRIDE=""
CURSOR_SKILLS="${CURSOR_SKILLS:-$HOME/.cursor/skills}"

usage() {
  cat <<EOF
Usage: $0 [--memory-home PATH] [--framework-root PATH]

Shows:
  ~/.cursor/skills/     — linked skills (framework vs personal)
  \$MEMORY_HOME/skills/ — domain skills not necessarily linked
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --memory-home) MEMORY_HOME_OVERRIDE="$2"; shift 2 ;;
    --framework-root) FRAMEWORK_OVERRIDE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown: $1"; usage; exit 1 ;;
  esac
done

FRAMEWORK_ROOT="$(resolve_framework_root "$FRAMEWORK_OVERRIDE" "$REPO_ROOT")"
if [[ -z "$FRAMEWORK_ROOT" ]]; then
  FRAMEWORK_ROOT="$REPO_ROOT"
fi
MEMORY_HOME="$(resolve_memory_home "$MEMORY_HOME_OVERRIDE" "$FRAMEWORK_ROOT")"

FRAMEWORK_NAMES=(agent-memory global-context chat-memory feedback-memory)

is_framework_name() {
  local n="$1"
  for f in "${FRAMEWORK_NAMES[@]}"; do
    [[ "$f" == "$n" ]] && return 0
  done
  return 1
}

echo "Skills status"
echo "  Cursor dir:  $CURSOR_SKILLS"
echo "  Memory hub:  $MEMORY_HOME"
echo "  Framework:   $FRAMEWORK_ROOT"
echo

echo "── ~/.cursor/skills ─────────────────────"
if [[ ! -d "$CURSOR_SKILLS" ]]; then
  echo "  (directory missing)"
else
  count=0
  fw=0
  personal=0
  for entry in "$CURSOR_SKILLS"/*; do
    [[ -e "$entry" ]] || continue
    name="$(basename "$entry")"
    [[ "$name" == "*" ]] && continue
    count=$((count + 1))
    kind="personal"
    target="(dir)"
    ok="✓"
    if [[ -L "$entry" ]]; then
      target="$(readlink "$entry")"
      if [[ ! -e "$entry" ]]; then ok="✗ broken"; fi
      resolved="$(cd "$(dirname "$entry")" && cd "$(dirname "$target")" 2>/dev/null && pwd)/$(basename "$target")" 2>/dev/null || true
      if [[ -n "$resolved" && "$resolved" == "$FRAMEWORK_ROOT"* ]]; then
        kind="framework"
        fw=$((fw + 1))
      else
        personal=$((personal + 1))
      fi
    elif is_framework_name "$name"; then
      kind="framework?"
      fw=$((fw + 1))
    else
      personal=$((personal + 1))
    fi
    printf "  %s %-22s %-11s → %s\n" "$ok" "$name" "[$kind]" "$target"
  done
  if [[ $count -eq 0 ]]; then
    echo "  (empty)"
  fi
  echo "  Total: $count ($fw framework · $personal personal)"
fi
echo

echo "── \$MEMORY_HOME/skills (domain) ─────────"
hub_skills="$MEMORY_HOME/skills"
if [[ ! -d "$hub_skills" ]]; then
  echo "  (missing — run init-memory.sh)"
else
  unlinked=0
  for dir in "$hub_skills"/*; do
    [[ -d "$dir" ]] || continue
    name="$(basename "$dir")"
    [[ -f "$dir/SKILL.md" ]] || continue
    if [[ -e "$CURSOR_SKILLS/$name" ]]; then
      state="linked"
    else
      state="not linked"
      unlinked=$((unlinked + 1))
    fi
    echo "  $name — $state"
  done
  echo "  Unlinked: $unlinked (add under hub/skills/; plugin loads bundle skills)"
fi
echo

echo "── Framework skills (available) ───────────"
for name in "${FRAMEWORK_NAMES[@]}"; do
  if [[ "$name" == "agent-memory" ]]; then
    src="$FRAMEWORK_ROOT"
  else
    src="$FRAMEWORK_ROOT/skills/$name"
  fi
  if [[ -e "$src" ]]; then
    echo "  ✓ $name"
  else
    echo "  ✗ $name (missing at $src)"
  fi
done
