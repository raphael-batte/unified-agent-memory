#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_TMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP"' EXIT
export AGENT_MEMORY_ANCHOR_HOME="$TEST_TMP"

cd "$ROOT/tests"

echo
echo "== Plugin structure =="
(cd "$ROOT" && node "$ROOT/scripts/validate-plugin.mjs")

echo
echo "== Python tests =="
python3 -m unittest discover -v

echo
echo "== Shell tests =="
bash test_shell_scripts.sh

echo
echo "All tests passed."
