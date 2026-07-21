# Contributing

Thanks for helping improve **cursor-agent-memory**. All changes land via **pull request** into `main`.

## Workflow

1. **Fork** [raphael-batte/cursor-agent-memory](https://github.com/raphael-batte/cursor-agent-memory) (or branch from `main` if you are a maintainer).
2. **Branch:** `feat/…`, `fix/…`, or `docs/…` from current `main`.
3. **Install hooks** (once per clone):
   ```bash
   bash scripts/install-git-hooks.sh
   ```
4. **Develop** — clone repo, then `bash scripts/install-local.sh` (symlink as local plugin). Hub lives outside bundle (`~/.agent-memory/` by default; per-env anchors under `~/.cursor/agent-memory/` and `~/.claude/agent-memory/`).
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

- `memory/`, `.devhub/`, `.agent-memory/` — personal hub / distill data
- Passwords, tokens, API keys anywhere in the repo
- User-specific paths unless in examples with placeholders
- **Real project, client, or product names** — including obfuscated denylists of them

## Generic plugin rule (mandatory)

**Tests are part of the public repo.** Examples, fixtures, docs, and test strings must use
**fictional names only**.

| Use | Do not use |
|-----|------------|
| `example-app`, `other-app`, `alpha-hub`, `beta-app`, `widget-ui` | Real portfolio / client / product slugs |
| `example-user`, path segments `me` / `alice` in synthetics | Real macOS usernames or a personal `Work` checkout path |
| `https://example.org/` | Production hostnames you own |

Applies to `scripts/`, `tests/`, `templates/`, `docs/`, `hooks/`, `rules/`, `skills/`, and
top-level markdown. Agent rule: `.cursor/rules/no-local-naming.mdc`.

**Enforcement is at push, not only in the tree.** `bash scripts/install-git-hooks.sh` installs a
`pre-push` hook running `scripts/check-local-leaks.py` over every ref you push — branches by the
lines they add, tags by their whole tree. Tags matter: they can carry commits that are on no
branch, which is how a name reached the public remote before this existed.

The checker derives what to block from your hub's project slugs and your account name, so no
denylist of real names is ever committed here. On a machine without a hub (CI, a fresh clone) it
falls back to shape checks — real home paths, obfuscated denylists. Generic technology names you
have cleared go in `.leakcheck-allow`; never a client or product name.

Run it by hand: `python3 scripts/check-local-leaks.py --rev v1.2.3 --show-matches`. Findings are
redacted unless you ask, because they print in public CI logs. `--no-verify` exists, but a push
to a public remote cannot be undone — history and forks keep it.

## Code style

- Framework repo: **English only** in docs, scripts, skills (enforced by tests).
- Match existing patterns in `scripts/lib/`.
- Minimal scope — one concern per PR when possible.

## Questions

Open a [GitHub issue](https://github.com/raphael-batte/cursor-agent-memory/issues) or discuss in the PR.
