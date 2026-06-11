# Migration & AI workflow

Move an existing memory hub to this framework, install the Cursor plugin, and distill chats.

**Bundle (git / plugin):** skills, scripts, hooks — replaceable.  
**Anchor:** `~/.cursor/agent-memory/config.json` — `memory_home` pointer (survives updates).  
**Hub (never git):** `$MEMORY_HOME` — context, feedback, chats.

Setup: [ONBOARDING.md](ONBOARDING.md)

---

## 1. Fresh install

```bash
# from your clone of github.com/raphael-batte/cursor-agent-memory
bash scripts/install-local.sh
# Reload Cursor — first sessionStart bootstraps hub; or:
bash scripts/init-memory.sh
```

In Cursor with `@agent-memory`: **sync with agent memory**.

Manual:

```bash
python3 scripts/sync-memory.py --days 180
```

Paths: anchor + `$MEMORY_HOME/config.json` (written by `init-memory` / `memory-doctor --fix`).

Example anchor:

```json
{ "memory_home": "/Users/you/.cursor/agent-memory" }
```

Example hub `config.json`:

```json
{
  "plugin_root": "/Users/you/.cursor/plugins/local/agent-memory",
  "framework_root": "/Users/you/.cursor/plugins/local/agent-memory",
  "memory_home": "/Users/you/.cursor/agent-memory"
}
```

---

## 2. Migrate from an old hub

Restores a backup into `$MEMORY_HOME`. **Default mode is `--merge`** (order-independent vs `init-memory`):

- **`manifest.json`** — merged by chat id (not skipped)
- **Template stubs** (`context/*`, `feedback/*`, …) — replaced from backup if dest still matches `templates/`
- **User-edited files** — kept; warning printed
- **Project distills** (`chats/projects/`, staging) — copied when missing

```bash
bash scripts/migrate-memory.sh \
  --from /path/to/old-hub \
  --to "$HOME/.cursor/agent-memory"
```

Flags: `--overwrite` (source wins everywhere) · `--ignore-existing` (legacy, deprecated) · `--dry-run` · `--json`

Then:

```bash
python3 scripts/memory-doctor.py --fix
python3 scripts/memory-doctor.py --rebuild-manifest   # if registry still desynced
```

Safe after reinstall: migrate works even if `sessionStart` already ran `init-memory.sh`.

To keep a custom hub path, set `--to` accordingly; `doctor --fix` updates the anchor.

---

## 3. Legacy → plugin

If you previously used symlink skills or global hooks:

| Remove | Why |
|--------|-----|
| `~/.cursor/skills/agent-memory` symlink | Plugin provides skill from bundle |
| `agent-memory-*` in `~/.cursor/hooks.json` | Plugin provides `hooks/hooks.json` |
| `~/.cursor/hooks/agent-memory.env` (optional) | Anchor + plugin hooks replace env file |

Then `install-local.sh` + Reload + `init-memory.sh` (idempotent).

---

## 4. Secrets (hard requirement)

**Never** put passwords, tokens, API keys, JWT, private keys, or `.env` values into `$MEMORY_HOME`.

```bash
python3 scripts/verify-memory.py --memory-home "$MEMORY_HOME"
```

---

## 5. Chat distill workflow

**Do not** paste raw `.jsonl` into chat.

```bash
python3 scripts/list-chats.py --memory-home "$MEMORY_HOME" --pending
python3 scripts/distill-merge.py "$UUID" --strategy auto --memory-home "$MEMORY_HOME"
python3 scripts/distill-merge.py "$UUID" --apply --memory-home "$MEMORY_HOME"
python3 scripts/verify-memory.py --memory-home "$MEMORY_HOME" --strict-secrets
```

---

## 6. Forward pointer

`chats/projects/<slug>.md` **## Next step** is updated automatically on boundary distills (`lib/forward_pointer.py`). Migrate any per-repo “what’s next” notes into the distill or delete obsolete files.

---

## Quick reference

| Situation | Doc |
|-----------|-----|
| First-time setup | [ONBOARDING.md](ONBOARDING.md) |
| Old hub path | §2 migrate + `memory-doctor.py --fix` |
| Double distill / duplicate hooks | §3 legacy cleanup |

Repair paths:

```bash
python3 scripts/memory-doctor.py --fix
bash scripts/install-local.sh   # then Reload Cursor
```
