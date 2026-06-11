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
| `install-local.sh` | Symlinks bundle → `~/.cursor/plugins/local/agent-memory` (delivery only) |
| Reload Cursor | Plugin discovers skills + hooks from bundle |
| `init-memory.sh` | Creates hub + anchor (idempotent; never overwrites user data) |

Default hub: `~/.cursor/agent-memory/` (first `sessionStart` may create template stubs; **restore** via `migrate-memory.sh --from backup`).

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
| `chats/projects/<slug>.md` | **Recent**, **`## Next step`** (pointer or explicit placeholder + chat drill link), optional **`[bootstrap]` Decisions** on first sync |
| `context/GLOBAL_CONTEXT.md` → **Projects** | Rows from distilled workspaces |
| Boundary hooks | `sessionStart` / `sessionEnd` / `preCompact` re-distill stale chats and refresh **Next step** |

**Forward pointer** — one file per project slug under `chats/projects/` (`## Next step`).

### After sync — agent should offer (optional)

1. **`fill Me in GLOBAL_CONTEXT from our chats`**
2. **Review `[bootstrap]` Decisions** — semantic merge from `merge-staging/`
3. **Curate `## Next step`** if placeholder `[?]` / `_No forward pointer._` — or drill chat link first, then edit

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
bash scripts/migrate-memory.sh --from /path/to/old-hub --to "$HOME/.cursor/agent-memory"
# or keep old path — init-memory + doctor --fix writes anchor
python3 scripts/memory-doctor.py --fix
```

---

## Legacy install cleanup

After switching to the plugin, **remove** to avoid double hooks/distill:

- `~/.cursor/skills/agent-memory` symlink (if present)
- `agent-memory-*` entries in `~/.cursor/hooks.json` (pre-plugin global hooks)
- Optional: `~/.cursor/hooks/agent-memory.env` (deprecated; anchor replaces it)

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

Anchor: `~/.cursor/agent-memory/config.json`  
Transcripts (read-only): `~/.cursor/projects/*/agent-transcripts/`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Sync finds 0 chats | Transcripts under `~/.cursor/projects/` |
| verify failed | `memory-doctor.py --memory-home "$MEMORY_HOME"` |
| Hooks silent | Reload Cursor; check plugin at `~/.cursor/plugins/local/agent-memory` |
| Stale Next step | Close chat (sessionEnd distill) or `list-chats.py --pending` |
| Wrong paths after move | `memory-doctor.py --fix`; check anchor `memory_home` |
| Rule reads wrong distill | `init-project-rules.sh --slug <name-from-chats/projects>` |

Details: [MIGRATION.md](MIGRATION.md) · [INSTRUCTIONS.md](INSTRUCTIONS.md)
