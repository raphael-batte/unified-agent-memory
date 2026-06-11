#!/usr/bin/env bash
# Integration tests for bash scripts. Run via tests/run-tests.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

OLD_HUB="$TMP/old"
NEW_HUB="$TMP/new"
mkdir -p "$OLD_HUB/context" "$OLD_HUB/feedback" "$OLD_HUB/chats/projects"
echo "# Old conventions" > "$OLD_HUB/context/conventions.md"
echo '{"processed":[],"pending":[]}' > "$OLD_HUB/chats/manifest.json"
mkdir -p "$OLD_HUB/feedback"
echo -e "## T\n\n+ win" > "$OLD_HUB/feedback/wins.md"

# plugin bundle layout
test -f "$ROOT/.cursor-plugin/plugin.json"
test -f "$ROOT/hooks/hooks.json"
test -f "$ROOT/skills/agent-memory/SKILL.md"
python3 -c "
import json
from pathlib import Path
hooks = json.loads(Path('$ROOT/hooks/hooks.json').read_text())
assert 'sessionStart' in hooks['hooks']
assert 'workspaceOpen' in hooks['hooks']
"

# simulate install-local (tmp only — never touch real ~/.cursor)
PLUGIN_DST="$TMP/plugins/local/agent-memory"
mkdir -p "$(dirname "$PLUGIN_DST")"
ln -sfn "$ROOT" "$PLUGIN_DST"
test -f "$PLUGIN_DST/.cursor-plugin/plugin.json"

# migrate
bash "$ROOT/scripts/migrate-memory.sh" --from "$OLD_HUB" --to "$NEW_HUB"
test -f "$NEW_HUB/context/conventions.md"
test -f "$NEW_HUB/feedback/wins.md"
test -f "$NEW_HUB/config.json"

# migrate does not overwrite
echo "KEEP" > "$NEW_HUB/context/conventions.md"
bash "$ROOT/scripts/migrate-memory.sh" --from "$OLD_HUB" --to "$NEW_HUB"
grep -q "KEEP" "$NEW_HUB/context/conventions.md"

# first-run scope CLI
python3 "$ROOT/scripts/first-run-scope.py" --memory-home "$NEW_HUB" --preset 7d >/dev/null
test -f "$NEW_HUB/.state/first-run-scope.json"

# skills-status
bash "$ROOT/scripts/skills-status.sh" \
  --memory-home "$NEW_HUB" --framework-root "$ROOT" >/dev/null

# config.sh resolve
# shellcheck source=../scripts/lib/config.sh
source "$ROOT/scripts/lib/config.sh"
resolved="$(resolve_memory_home "$NEW_HUB")"
test "$(python3 -c "import os; print(os.path.realpath('${resolved}'))")" \
  = "$(python3 -c "import os; print(os.path.realpath('${NEW_HUB}'))")"

# boundary-hooks CLI (session-start catchup JSON)
TEST_WS="$TMP/workspace"
mkdir -p "$TEST_WS"
boundary_out="$(printf '%s' '{"workspace_roots":["'"$TEST_WS"'"]}' \
  | MEMORY_HOME="$NEW_HUB" python3 "$ROOT/scripts/boundary-hooks.py" session-start \
    --memory-home "$NEW_HUB")"
echo "$boundary_out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'catchup' in d"

# sync-memory scan-only
scan_out="$(python3 "$ROOT/scripts/sync-memory.py" --memory-home "$NEW_HUB" --scan-only 2>/dev/null)"
echo "$scan_out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pending_90d' in d"

# sync-memory dry-run (plugin skips legacy hooks by default)
sync_out="$(python3 "$ROOT/scripts/sync-memory.py" --memory-home "$NEW_HUB" --dry-run 2>/dev/null)"
echo "$sync_out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('dry_run') is True; assert d.get('distills')==0"

EMPTY_PR="$TMP/empty-projects"
mkdir -p "$EMPTY_PR"
sync_hooks="$(python3 "$ROOT/scripts/sync-memory.py" --memory-home "$NEW_HUB" \
  --projects-root "$EMPTY_PR" 2>/dev/null || true)"
echo "$sync_hooks" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hooks'].get('reason')=='plugin_hooks_in_bundle'"

chmod +x "$ROOT/scripts/weekly-verify.sh"
weekly_out="$(bash "$ROOT/scripts/weekly-verify.sh" --dry-run 2>&1)"
echo "$weekly_out" | grep -q "would run memory-doctor"
echo "$weekly_out" | grep -q "memory-health"
echo "$weekly_out" | grep -q "update-baseline"
test -x "$ROOT/scripts/weekly-verify.sh"

# init-memory on empty hub
INIT_HUB="$TMP/init-hub"
mkdir -p "$INIT_HUB"
MEMORY_HOME="$INIT_HUB" bash "$ROOT/scripts/init-memory.sh" >/dev/null
test -f "$INIT_HUB/config.json"
test -f "$INIT_HUB/chats/manifest.json"

# init then migrate — manifest merge after template init (regression)
RACE_OLD="$TMP/race-old"
RACE_NEW="$TMP/race-new"
mkdir -p "$RACE_OLD/chats/projects" "$RACE_OLD/context" "$RACE_OLD/feedback"
echo '{"processed":[{"id":"x1","distilled_at":"2026-06-08","summary":"s"}],"pending":[]}' \
  > "$RACE_OLD/chats/manifest.json"
echo "# Restored context with enough lines for verify" > "$RACE_OLD/context/GLOBAL_CONTEXT.md"
echo "## Me" >> "$RACE_OLD/context/GLOBAL_CONTEXT.md"
echo "- user" >> "$RACE_OLD/context/GLOBAL_CONTEXT.md"
MEMORY_HOME="$RACE_NEW" bash "$ROOT/scripts/init-memory.sh" >/dev/null
bash "$ROOT/scripts/migrate-memory.sh" --from "$RACE_OLD" --to "$RACE_NEW"
python3 -c "
import json
from pathlib import Path
m = json.loads(Path('$RACE_NEW/chats/manifest.json').read_text())
assert len(m.get('processed', [])) == 1, m
"

echo "shell tests: OK"
