#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_TMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP"' EXIT
export AGENT_MEMORY_ANCHOR_HOME="$TEST_TMP"

# Transcript discovery now spans every installed environment, so a test that does
# not pin its roots would read the developer's real chats. Point both environments
# at empty directories; tests that need transcripts set these themselves.
mkdir -p "$TEST_TMP/cursor-projects" "$TEST_TMP/claude-projects"
export AGENT_MEMORY_CURSOR_PROJECTS="$TEST_TMP/cursor-projects"
export AGENT_MEMORY_CLAUDE_PROJECTS="$TEST_TMP/claude-projects"

cd "$ROOT/tests"

echo
echo "== Plugin structure =="
(cd "$ROOT" && node "$ROOT/scripts/validate-plugin.mjs")

echo
echo "== Local data =="
# The suite points the anchor at tmp for isolation; unset it here so the check
# resolves the real hub and has actual names to match, not just shapes.
(cd "$ROOT" && env -u AGENT_MEMORY_ANCHOR_HOME \
  python3 "$ROOT/scripts/check-local-leaks.py" --repo "$ROOT")

echo
echo "== Python tests =="
python3 -m unittest discover -v

echo
echo "== Shell tests =="
bash test_shell_scripts.sh

echo
echo "All tests passed."
