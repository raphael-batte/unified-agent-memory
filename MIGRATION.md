# Migration & AI workflow

Move an existing memory hub to this framework, install the plugin in Cursor and/or
Claude Code, and distill chats.

**Bundle (git / plugin):** skills, scripts, hooks — replaceable.  
**Anchors:** `~/.cursor/agent-memory/config.json` and `~/.claude/agent-memory/config.json` —
each a `memory_home` pointer (survives updates). Both point at the **same** hub.  
**Hub (never git):** `$MEMORY_HOME` — context, feedback, chats. Default `~/.agent-memory/`,
shared by every environment.

Setup: [ONBOARDING.md](ONBOARDING.md)

---

## 1. Fresh install

```bash
# from your clone of github.com/raphael-batte/unified-agent-memory
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
{ "memory_home": "/home/example-user/.agent-memory" }
```

Example hub `config.json`:

```json
{
  "plugin_root": "/home/example-user/.cursor/plugins/local/agent-memory",
  "framework_root": "/home/example-user/.cursor/plugins/local/agent-memory",
  "memory_home": "/home/example-user/.agent-memory"
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
  --to "$HOME/.agent-memory"
```

Flags: `--overwrite` (source wins everywhere) · `--ignore-existing` (legacy, deprecated) · `--dry-run` · `--json`

### Upgrading from a per-environment hub (pre-0.28)

Older installs kept the hub inside Cursor's anchor directory. One command moves it to the
shared location and repoints **every** environment's anchor:

```bash
python3 scripts/migrate-memory.py --to-shared --dry-run   # inspect first
python3 scripts/migrate-memory.py --to-shared
```

Idempotent — running it again on an already-shared hub only re-asserts the anchors. Nothing
is deleted from the old location; move it aside yourself once you have verified the new hub
with `python3 scripts/verify-memory.py --strict`.

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
| `agent-memory-*` in `~/.cursor/hooks.json` | Plugin provides `hooks/cursor/hooks.json` |
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

`chats/projects/<slug>.md` **## Open threads** is curated via `memory-pointer.py add-thread` (and optional `[auto]` drafts on boundary distills). Migrate any per-repo “what’s next” notes into Open threads or delete obsolete files.

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
