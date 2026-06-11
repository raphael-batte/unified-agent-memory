#!/usr/bin/env bash
# Bump SemVer in VERSION and prepend CHANGELOG entry.
# Usage: bump-version.sh {patch|minor|major} "change description"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$REPO_ROOT/VERSION"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

BUMP="${1:-}"
MSG="${2:-}"

usage() {
  echo "Usage: $0 {patch|minor|major} \"change description\""
  exit 1
}

[[ -n "$BUMP" && -n "$MSG" ]] || usage
[[ -f "$VERSION_FILE" ]] || { echo "Missing VERSION"; exit 1; }

CURRENT="$(tr -d '[:space:]' < "$VERSION_FILE")"
IFS=. read -r MAJOR MINOR PATCH <<< "$CURRENT"
[[ -n "${MAJOR:-}" && -n "${MINOR:-}" && -n "${PATCH:-}" ]] || {
  echo "Invalid VERSION: $CURRENT"
  exit 1
}

case "$BUMP" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
  *) usage ;;
esac

NEW="${MAJOR}.${MINOR}.${PATCH}"
DATE="$(date +%Y-%m-%d)"

printf '%s\n' "$NEW" > "$VERSION_FILE"

# Classify changelog section from bump level
case "$BUMP" in
  major) SECTION="Changed" ;;
  minor) SECTION="Added" ;;
  patch) SECTION="Fixed" ;;
esac

ENTRY="## [${NEW}] - ${DATE}

### ${SECTION}

- ${MSG}
"

# Insert after [Unreleased] block header
if grep -q '^## \[Unreleased\]' "$CHANGELOG"; then
  python3 - "$CHANGELOG" "$ENTRY" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
entry = sys.argv[2]
text = path.read_text(encoding="utf-8")
marker = "## [Unreleased]"
if marker not in text:
    raise SystemExit("CHANGELOG missing [Unreleased]")
head, tail = text.split(marker, 1)
# tail starts with newline + maybe content until next ##
lines = tail.splitlines(keepends=True)
rest = "".join(lines)
if rest.startswith("\n"):
    rest = rest[1:]
# find next ## heading
idx = rest.find("\n## ")
if idx == -1:
    new_tail = "\n" + entry + "\n" + rest
else:
    before, after = rest[:idx], rest[idx + 1 :]
    new_tail = "\n" + entry + "\n" + before + after
path.write_text(head + marker + "\n" + new_tail, encoding="utf-8")
PY
else
  echo "CHANGELOG missing ## [Unreleased] — add it manually"
  exit 1
fi

# Sync version line in README and SKILL.md
for f in "$REPO_ROOT/README.md" "$REPO_ROOT/SKILL.md" "$REPO_ROOT/skills/agent-memory/SKILL.md"; do
  [[ -f "$f" ]] || continue
  if grep -q '^\*\*Version:\*\*' "$f"; then
    sed -i '' "s/^\*\*Version:\*\*.*/**Version:** ${NEW} — see [VERSIONING.md](VERSIONING.md)/" "$f"
  fi
done

PLUGIN_JSON="$REPO_ROOT/.cursor-plugin/plugin.json"
if [[ -f "$PLUGIN_JSON" ]]; then
  python3 - "$PLUGIN_JSON" "$NEW" <<'PY'
import json, sys
path, ver = sys.argv[1], sys.argv[2]
data = json.loads(open(path, encoding="utf-8").read())
data["version"] = ver
open(path, "w", encoding="utf-8").write(json.dumps(data, indent=2) + "\n")
PY
fi

echo "Bumped: ${CURRENT} → ${NEW}"
echo "CHANGELOG: ### ${SECTION} — ${MSG}"
echo "Stage: git add VERSION CHANGELOG.md README.md SKILL.md skills/agent-memory/SKILL.md .cursor-plugin/plugin.json"
