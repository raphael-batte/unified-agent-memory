#!/usr/bin/env bash
# Point git at tracked hooks in scripts/hooks/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/scripts/hooks"

cd "$REPO_ROOT"

if ! git rev-parse --git-dir &>/dev/null; then
  git init
  echo "Initialized git repository"
fi

chmod +x "$HOOKS_DIR/pre-commit"
git config core.hooksPath scripts/hooks

echo "Git hooks installed: core.hooksPath → scripts/hooks"
echo "Pre-commit: framework changes require VERSION or CHANGELOG bump"
echo "Run: bash scripts/bump-version.sh patch \"description\" before commit"
