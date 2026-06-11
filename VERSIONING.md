# Versioning

Framework repo: **SemVer** `MAJOR.MINOR.PATCH` in [VERSION](VERSION). History: [CHANGELOG.md](CHANGELOG.md).

| Bump | When |
|------|------|
| **PATCH** | Doc fixes, script bugs, wording in skills/templates |
| **MINOR** | New skill, new template, new verify check (non-breaking) |
| **MAJOR** | Breaking protocol: path renames, manifest schema, superseded format, Flow changes |

Data hub `$MEMORY_HOME` uses dates and episodes — not this version.

## Before every commit (framework changes)

```bash
bash scripts/bump-version.sh patch "short description of change"
# or: minor | major
git add VERSION CHANGELOG.md README.md SKILL.md
git commit -m "fix: short description (v0.1.1)"
```

**Pre-commit hook** blocks commits that change **behaviour** (scripts, skills, `INSTRUCTIONS.md`, hooks…) without updating `VERSION` or `CHANGELOG.md`.

**No bump needed** when the commit touches only:

- `README.md`
- `docs/**`
- `templates/**`
- `LICENSE`, `.gitignore`

### Escape hatches (rare)

```bash
git commit --no-verify -m "docs: fix typo in INSTRUCTIONS"
SKIP_VERSION_CHECK=1 git commit -m "…"
```

Use `--no-verify` sparingly — if it becomes habitual, the hook loses meaning.

## First-time git setup

```bash
cd "$FRAMEWORK_ROOT"
git init
bash scripts/install-git-hooks.sh
```

## Pull requests

All changes go through PR → `main`. CI runs tests, gitleaks, and version-check. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Release tags

After merge to `main`:

```bash
git tag -a v$(cat VERSION) -m "cursor-agent-memory $(cat VERSION)"
git push origin main --tags   # when remote exists
```

Push tag `v*` triggers [`.github/workflows/release.yml`](.github/workflows/release.yml): runs CI, checks `v$(cat VERSION)` matches the tag, publishes GitHub Release with the matching CHANGELOG section.

## Schema (data hub, separate)

`chats/manifest.json` → `_schema.version` bumps only when manifest **format** breaks (MAJOR framework change). Document migration in CHANGELOG **Migration** section.
