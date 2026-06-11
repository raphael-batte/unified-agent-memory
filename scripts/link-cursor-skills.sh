#!/usr/bin/env bash
# LEGACY: symlink skills into ~/.cursor/skills/ — use plugin install (install-local.sh).
set -euo pipefail

echo "[agent-memory] deprecated: use plugin install (bash scripts/install-local.sh)" >&2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/config.sh
source "$SCRIPT_DIR/lib/config.sh"

CURSOR_SKILLS="${CURSOR_SKILLS:-$HOME/.cursor/skills}"
FORCE=false
DRY_RUN=false
ONLY=""
PERSONAL=""
MEMORY_HOME_OVERRIDE=""
FRAMEWORK_OVERRIDE=""
DO_LIST=false

FRAMEWORK_NAMES=(agent-memory global-context chat-memory semantic-merge feedback-memory)

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --only name,name     Link only these framework skills (default: all)
  --personal name      Link domain skill from \$MEMORY_HOME/skills/
  --list               Show available framework + hub skills
  --dry-run            Print actions without linking
  --force              Replace existing symlinks
  --memory-home PATH   Hub path for --personal
  --framework-root PATH  Framework clone (default: config.json)

Framework skills: ${FRAMEWORK_NAMES[*]}
EOF
}

framework_src() {
  local name="$1"
  if [[ "$name" == "agent-memory" ]]; then
    echo "$FRAMEWORK_ROOT"
  else
    echo "$FRAMEWORK_ROOT/skills/$name"
  fi
}

link_skill() {
  local name="$1" src="$2"
  local dest="$CURSOR_SKILLS/$name"
  if [[ ! -e "$src" ]]; then
    echo "  skip: $name (missing $src)"
    return 1
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "  would link: $dest → $src"
    return 0
  fi
  mkdir -p "$CURSOR_SKILLS"
  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ "$FORCE" == true ]]; then
      rm -rf "$dest"
      ln -sf "$src" "$dest"
      echo "  relinked: $dest → $src"
    else
      echo "  exists: $dest (skip — use --force)"
    fi
  else
    ln -sf "$src" "$dest"
    echo "  linked: $dest → $src"
  fi
}

list_available() {
  echo "Framework ($FRAMEWORK_ROOT):"
  for name in "${FRAMEWORK_NAMES[@]}"; do
    src="$(framework_src "$name")"
    [[ -e "$src" ]] && mark="✓" || mark="✗"
    echo "  $mark $name"
  done
  echo
  echo "Personal (\$MEMORY_HOME/skills):"
  local hub="$MEMORY_HOME/skills"
  if [[ ! -d "$hub" ]]; then
    echo "  (no hub skills dir)"
    return
  fi
  local found=false
  for dir in "$hub"/*; do
    [[ -d "$dir" && -f "$dir/SKILL.md" ]] || continue
    found=true
    echo "  ✓ $(basename "$dir")"
  done
  if [[ "$found" == false ]]; then
    echo "  (none)"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --list) DO_LIST=true; shift ;;
    --only) ONLY="$2"; shift 2 ;;
    --personal) PERSONAL="$2"; shift 2 ;;
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

if [[ "$DO_LIST" == true ]]; then
  list_available
  exit 0
fi

if [[ -n "$PERSONAL" ]]; then
  src="$MEMORY_HOME/skills/$PERSONAL"
  echo "Linking personal skill: $PERSONAL"
  link_skill "$PERSONAL" "$src"
  exit $?
fi

names=()
if [[ -n "$ONLY" ]]; then
  IFS=',' read -ra names <<< "$ONLY"
else
  names=("agent-memory")
fi

echo "Linking framework skills → $CURSOR_SKILLS"
for name in "${names[@]}"; do
  name="$(echo "$name" | xargs)"
  link_skill "$name" "$(framework_src "$name")" || true
done

write_hub_config_paths "$FRAMEWORK_ROOT" "$MEMORY_HOME"
write_cursor_hook_env "$FRAMEWORK_ROOT" "$MEMORY_HOME"

echo "Done."
echo "  Framework: $FRAMEWORK_ROOT"
echo "  Status: bash $SCRIPT_DIR/skills-status.sh"
echo "  Invoke: @agent-memory (single entry skill)"
echo "  All layers: link with --only agent-memory,global-context,... if needed"
