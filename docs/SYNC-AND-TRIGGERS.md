# Sync and boundary triggers

Technical reference for distill-first memory with **forward pointer** (`## Next step`).

## Design goals

1. **Distill-first** — `chats/projects/<slug>.md` is primary history and forward pointer.
2. **Plugin hooks** — bundle `hooks/hooks.json`; no global hooks merge in normal install.
3. **One skill** — `agent-memory` routes all layers.
4. **Event-driven** — distill on session boundaries; `apply=True` updates Recent + Next step.

## Hub config

`$MEMORY_HOME/config.json`:

```json
{
  "plugin_root": "",
  "framework_root": "",
  "memory_home": "",
  "retention_days": 90,
  "thresholds": {
    "max_extracted_decisions_per_file": 30,
    "max_decisions_add_per_distill": 6,
    "max_layer_file_lines": 100,
    "distill_token_budget": 12000,
    "segment_max": 6
  }
}
```

Omit `thresholds` to use defaults from `scripts/lib/defaults.py`.

Anchor (fixed): `~/.cursor/agent-memory/config.json` → `{ "memory_home": "..." }`.

## Triggers (plugin bundle)

| Cursor event | Script | Action |
|--------------|--------|--------|
| `sessionStart` / `workspaceOpen` | `hooks/agent-memory-session-start.sh` | First-run bootstrap; catch-up distill |
| `sessionEnd` | `hooks/agent-memory-boundary.sh` | Distill + apply → Recent + **Next step** |
| `sessionEnd` | `hooks/agent-memory-session-end.sh` | Checklist log |
| `preCompact` | `hooks/agent-memory-boundary.sh` | Distill + reminder |
| `afterFileEdit` | `hooks/agent-memory-after-edit.sh` | Log chats hub edits |

## First run (`lib/first_run.py`)

**Hook (passive):** idempotent `init-memory` + anchor; short `user_message` → `@agent-memory` **set up agent memory**. No auto-distill on hook.

**Chat wizard (skill):** hub path → scan → scope presets → `first-run-scope.py` + `first-run-continue.py` → `verify-memory.py`.

Sentinel: `$MEMORY_HOME/.state/initialized` (set by `first-run-continue` or existing manifest).

## sync-memory.py (manual batch)

1. `init-memory.sh` (idempotent)
2. List pending chats in `--days` window
3. `order_for_distill()` — **oldest pending first** (scan inventory stays newest-first)
4. `distill-extract` + `distill-merge` each with `apply=True`, `bootstrap_decisions=True` on first sync (`--apply` merges novel `[extracted]`; FIFO evict to `archive/<slug>-decisions.md`)
5. Bootstrap `GLOBAL_CONTEXT.md` Projects table
6. `verify-memory.py`

Does **not** install legacy global hooks when plugin manifest is present.

CLI: `--scan-only`, `--dry-run`, `--no-hooks`, `--days`, `--limit`.

## Forward pointer

`lib/forward_pointer.py` — heuristics on transcript tail with **confidence** tier. Hooks write `## Next step` mechanically; on placeholder or low confidence, `sessionEnd` emits `user_message` for agent curation.

## Distill freshness (v0.10+)

- **Watermark** — `manifest.json` stores `watermark_user_count` + `watermark_tail_hash`
- **Debounce** — `lib/boundary_debounce.py` limits repeat boundary distills
- **Long chats** — topic segmentation + importance strategy (`auto`); map-reduce fallback; semantic-merge for `[curated]` Decisions
- **`[extracted]` cap** — `enforce_extracted_decisions_cap` in `project_merge.py`; archive searchable at 0.7× via `hub_search.py`

## Key modules

| Module | Role |
|--------|------|
| `lib/pending_chats.py` | Scan + pending list; `order_for_distill()` oldest-first |
| `lib/project_merge.py` | `[extracted]` merge, cap, archive evict |
| `lib/hub_search.py` | BM25 over projects + archive + context |
| `lib/boundary_hooks.py` | Hook dispatch |
| `lib/first_run.py` | Plugin first-run bootstrap |
| `lib/global_context_bootstrap.py` | Projects table |
| `lib/forward_pointer.py` | ## Next step heuristics |
