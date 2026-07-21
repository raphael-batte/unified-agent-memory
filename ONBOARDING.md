# Onboarding — Cursor plugin

One skill, one sync command. Framework repo is **English-only**; your `$MEMORY_HOME` hub can be any language.

## Prerequisites

- Cursor with **Skills** and **Plugins** (local plugins)
- Python 3.10+

## Quick start

From [the repo](https://github.com/raphael-batte/cursor-agent-memory) (clone anywhere), then:

```bash
bash scripts/install-local.sh
```

| Step | What it does |
|------|----------------|
| `install-local.sh` | Symlinks bundle → `~/.cursor/plugins/local/agent-memory`, skills → `~/.cursor/skills/`, **global routing rule** → `~/.cursor/rules/agent-memory-routing.mdc` |
| Reload Cursor | Plugin discovers skills, hooks, and bundled `rules/` |
| `init-memory.sh` | Creates hub + anchor (idempotent; never overwrites user data); re-links global rule |

Default hub: `~/.agent-memory/` — **shared by every environment**, so Cursor and Claude Code
read and write the same memory. First `sessionStart` may create template stubs; **restore** via
`migrate-memory.sh --from backup`. Upgrading from a pre-0.28 per-environment hub:
`python3 scripts/migrate-memory.py --to-shared`.

### Claude Code

```bash
/plugin marketplace add raphael-batte/cursor-agent-memory   # or a local clone path
/plugin install agent-memory
```

Hooks ship with the plugin; `~/.claude/settings.json` is not modified. Hooks are read when a
session starts, so open a **new** session after installing. `PostToolUse` is deliberately not
declared — the apply-guard it would call is not wired to the hook CLI, and an empty hook is
worse than none.

```bash
bash scripts/init-memory.sh   # optional — hooks also init idempotently
bash scripts/migrate-memory.sh --from /path/to/backup   # reinstall restore (merge mode)
```

### First run (hook + chat wizard)

1. **Reload Cursor** after `install-local.sh`.
2. Open any project — `sessionStart` creates hub + anchor (short reminder in chat).
3. Add **`@agent-memory`** → say **`set up agent memory`**.
4. Agent asks: hub path (default / custom / migrate) → distill scope → runs verify.

### Sync in Cursor (after setup)

1. Add **`@agent-memory`** in chat.
2. Say: **`sync with agent memory`** — agent scans transcripts, asks period/limit if needed, runs sync.

### What sync + hooks do automatically

| Output | How |
|--------|-----|
| `chats/manifest.json` | Tracks processed Cursor chats |
| `chats/merge-staging/` | Raw candidates per chat (for agent review) |
| `chats/projects/<slug>.md` | **Recent**, **`## Open threads`** (curated + optional `[auto]` drafts), optional **`[bootstrap]` Decisions** on first sync |
| `context/GLOBAL_CONTEXT.md` → **Projects** | Rows from distilled workspaces |
| Boundary hooks | `sessionStart` / `sessionEnd` / `preCompact` re-distill stale chats; may draft `[auto]` Open threads |

**Forward pointer** — **`## Open threads`** in each project distill + rolling 30d cross-hub via `memory-routing-hint.py`. Curate: `memory-pointer.py add-thread <project> <label> "…"`.

### Session routing (automatic)

After install, **`agent-memory-routing.mdc`** is active globally (`alwaysApply: true`):

- Resolves your workspace → distill slug via `scripts/memory-routing-hint.py`
- Agent reads rolling **Open threads** before answering (including off-topic questions in a new chat)
- No per-project setup required; optional legacy override: `init-project-rules.sh --project <path>`

### After sync — agent should offer (optional)

1. **`fill Me in GLOBAL_CONTEXT from our chats`**
2. **Review `[bootstrap]` Decisions** — semantic merge from `merge-staging/`
3. **Curate `## Open threads`** — replace `[auto]` drafts via `add-thread` or semantic-merge; drill `[title](uuid)` in Recent if thread is vague

Manual sync:

```bash
python3 scripts/sync-memory.py --days 180
python3 scripts/memory-doctor.py
python3 scripts/verify-memory.py --memory-home "$MEMORY_HOME"
```

---

## Existing hub (migrate path)

If you already have data (e.g. `<clone>/memory/`):

```bash
bash scripts/migrate-memory.sh --from /path/to/old-hub --to "$HOME/.agent-memory"
# or keep old path — init-memory + doctor --fix writes anchor
python3 scripts/memory-doctor.py --fix
```

---

## Legacy install cleanup

After switching to the plugin, **remove** to avoid double hooks/distill:

- Broken or duplicate skill symlinks under `~/.cursor/skills/` (re-run `install-local.sh` to refresh)
- `agent-memory-*` entries in `~/.cursor/hooks.json` (pre-plugin global hooks)
- Optional: `~/.cursor/hooks/agent-memory.env` (deprecated; anchor replaces it)

`install-local.sh` intentionally links `skills/agent-memory` → `~/.cursor/skills/agent-memory` so `@agent-memory` appears in chat and Settings → Skills.

---

## Contributors / dev loop

```bash
bash scripts/install-local.sh   # symlink this clone as the plugin bundle
bash tests/run-tests.sh
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Verify setup

```bash
python3 scripts/memory-doctor.py
python3 scripts/memory-status.py --brief
```

Anchors: `~/.cursor/agent-memory/config.json` · `~/.claude/agent-memory/config.json`
(both point at the shared hub)  
Transcripts (read-only): `~/.cursor/projects/*/agent-transcripts/` ·
`~/.claude/projects/<encoded-cwd>/*.jsonl`  
Inventory across environments: `python3 scripts/list-chats.py --json`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Sync finds 0 chats | Transcripts under `~/.cursor/projects/` |
| verify failed | `memory-doctor.py --memory-home "$MEMORY_HOME"` |
| Hooks silent | Reload Cursor; check plugin at `~/.cursor/plugins/local/agent-memory` |
| Periodic sync | `bash scripts/install-periodic-sync.sh` — every 2h when Cursor is open (`scripts/sync-if-cursor-open.sh`) |
| Stale Open threads | Close chat (sessionEnd distill) or `list-chats.py --pending`; curate `[auto]` via add-thread |
| Wrong paths after move | `memory-doctor.py --fix`; check anchor `memory_home` |
| Rule reads wrong distill | `python3 scripts/memory-routing-hint.py --json .` — check slug; or `init-project-rules.sh --slug <name-from-chats/projects>` (optional per-repo override) |

Details: [MIGRATION.md](MIGRATION.md) · [INSTRUCTIONS.md](INSTRUCTIONS.md)
