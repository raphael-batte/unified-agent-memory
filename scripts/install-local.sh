#!/usr/bin/env bash
# Install local plugin bundle + link skills for @agent-memory in Cursor.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_NAME="agent-memory"

# shellcheck source=lib/plugin-install.sh
source "$SCRIPT_DIR/lib/plugin-install.sh"

if [[ ! -f "$SRC/.cursor-plugin/plugin.json" ]]; then
  echo "Error: not a plugin bundle (missing .cursor-plugin/plugin.json): $SRC" >&2
  exit 1
fi

echo "Validating plugin bundle..."
(cd "$SRC" && node "$SCRIPT_DIR/validate-plugin.mjs")

TARGET="$(link_local_plugin "$SRC" "$PLUGIN_NAME")"
echo "Agent Memory — local plugin install"
echo "  Bundle:  $SRC"
echo "  Plugin:  $TARGET"
echo
echo "Linking bundle skills → $(cursor_skills_dir)/"
link_bundle_skills "$SRC"

echo
echo "Linking global routing rule → $(cursor_rules_dir)/"
link_global_routing_rules "$SRC"

echo
echo "Verifying install..."
verify_plugin_install "$SRC" "$PLUGIN_NAME"

echo
echo "Install OK."
echo
echo "Next:"
echo "  1. Reload Cursor window (Developer: Reload Window)"
echo "  2. bash $SRC/scripts/init-memory.sh   # hub + anchor (idempotent)"
echo "  3. In chat: @agent-memory → set up agent memory / sync with agent memory"
echo "  Rules:  $(cursor_rules_dir)/$(global_routing_rule_name) (alwaysApply — session routing)"
echo "  Status: bash $SCRIPT_DIR/skills-status.sh"
