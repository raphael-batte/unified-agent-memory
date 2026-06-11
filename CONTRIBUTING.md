# Contributing

Thanks for helping improve **cursor-agent-memory**. All changes land via **pull request** into `main`.

## Workflow

1. **Fork** [raphael-batte/cursor-agent-memory](https://github.com/raphael-batte/cursor-agent-memory) (or branch from `main` if you are a maintainer).
2. **Branch:** `feat/…`, `fix/…`, or `docs/…` from current `main`.
3. **Install hooks** (once per clone):
   ```bash
   bash scripts/install-git-hooks.sh
   ```
4. **Develop** — clone repo, then `bash scripts/install-local.sh` (symlink as local plugin). Hub lives outside bundle (`~/.cursor/agent-memory/` by default).
5. **Test locally:**
   ```bash
   bash tests/run-tests.sh
   ```
6. **Version bump** when you change behaviour (scripts, skills, hooks, `INSTRUCTIONS.md`, tests that reflect protocol):
   ```bash
   bash scripts/bump-version.sh patch "short description"
   # or: minor | major
   ```
   Doc-only changes (`README.md`, `docs/`, `templates/`) do not require a bump.
7. **Open PR** → `main`. CI must pass (`test`, `gitleaks`, `version-check`).
8. **Review** — external PRs need maintainer approval.
9. **Merge** — squash merge preferred.
10. **Release** (maintainers, after merge): tag `v$(cat VERSION)` and push tag → GitHub Release.

## CI requirements

Every PR runs:

| Check | What |
|-------|------|
| **test** | `bash tests/run-tests.sh` |
| **gitleaks** | Secret scan |
| **version-check** | Behaviour diff must include `VERSION` or `CHANGELOG.md` |

Enable branch protection on `main`: require these checks before merge.

## What not to commit

- `memory/` — personal hub (chats, context, secrets)
- Passwords, tokens, API keys anywhere in the repo
- User-specific paths unless in examples with placeholders

## Code style

- Framework repo: **English only** in docs, scripts, skills (enforced by tests).
- Match existing patterns in `scripts/lib/`.
- Minimal scope — one concern per PR when possible.

## Questions

Open a [GitHub issue](https://github.com/raphael-batte/cursor-agent-memory/issues) or discuss in the PR.
