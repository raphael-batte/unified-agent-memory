# Architecture — Agent Memory

Human-oriented overview. Runtime protocol for agents: [INSTRUCTIONS.md](INSTRUCTIONS.md).

## Problem

Coding agents start each session with no durable memory. Project rules help for one repo, but not for:

- cross-project conventions (deploy, git, CI)
- what you already rejected or praised
- distilled history of long chat threads
- where you stopped yesterday in a multi-repo workflow

This framework is a **routed memory system**: small INDEX-first files, explicit layer choice per task, rotation at size limits, and tooling so agents never load megabyte jsonl transcripts.

## Environment modules

An **agent environment** is a module under `scripts/lib/envs/` declaring the rules of its
harness: where transcripts live, how they are laid out, what triggers a distill, where its
anchor sits, and what shape a trigger's payload and reply take. Everything above that layer —
distill, merge, search, Open threads — is environment agnostic and must not branch on the
harness. Adding one (Codex, say) is a new module plus a registry entry.

| | `cursor` | `claude` |
|---|---|---|
| Transcripts | `~/.cursor/projects/*/agent-transcripts/**/*.jsonl` | `~/.claude/projects/<encoded-cwd>/<session>.jsonl` |
| Row shape | role at top level | role under `message` |
| Trigger | launchd every 30m — **hooks unsupported since June 2026** | event hooks |
| Payload workspace | `workspace_roots` list | single `cwd` |
| Reply shape | `user_message` | `hookSpecificOutput.additionalContext` |

Claude rows are normalized onto the Cursor row shape before parsing, so tool calls and
TodoWrite reconstruction are shared rather than reimplemented.

## Shared hub, two writers

Both environments write one hub on different schedules. The Cursor cron script guards itself
with a `mkdir` lock at `$MEMORY_HOME/.state/periodic-sync.lock`; the hook path adopts that same
lock rather than inventing a second protocol. Writes go through temp + `os.replace`, so a
reader never sees a partial file. A hook that cannot take the lock within 5 seconds does not
wait — it writes staging and returns, leaving the durable apply to the next trigger. Manifest
entries record `env` so it is visible which environment produced a chat.

## Plugin bundle + external hub

| Entity | Location | On plugin update |
|--------|----------|------------------|
| **Bundle** (code) | Cursor plugin dir (`~/.cursor/plugins/local/agent-memory/`) | replaced |
| **Anchor** (per env) | `~/.cursor/agent-memory/` · `~/.claude/agent-memory/` | survives |
| **Hub** (data, shared) | path from anchor (default `~/.agent-memory/`) | survives |

Path resolution: `MEMORY_HOME` — CLI → env → anchor → default. `PLUGIN_ROOT` — script path → `.cursor-plugin/plugin.json`.

Install: `bash scripts/install-local.sh` → Reload Cursor → `init-memory.sh` (idempotent).

Contributions: PR → `main` ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Layer model

Each layer answers a different question. **Do not load all layers every session.**

| Layer | Path | Answers | Typical size |
|-------|------|---------|--------------|
| **Global context** | `$MEMORY_HOME/context/` | Who? Which projects? Rules? Infra? | ~30–80 lines/file |
| **Preferences** | `context/preferences.md` | How does the user think and communicate? | ~40 lines |
| **Feedback** | `feedback/wins.md`, `fails.md` | What worked (+) / failed (−) across sessions? | grows; archive ~80 lines |
| **Chat memory** | `chats/projects/<slug>.md` | History + **`## Open threads`** forward pointer | ~100 lines/file |

**Separation of concerns:**

- `conventions.md` — normative rules (deploy policy, git flow)
- `preferences.md` — style and thinking (not rules)
- `feedback/` — empirical lessons; `_superseded_` when a fail became a convention
- `chats/projects/` — distill history; **Open threads** = where to continue (curated + optional `[auto]` drafts)

## Routing (session start)

```
Continue known repo     → memory-routing-hint.py → open_threads (rolling 30d, cross-hub)
                         → chats/projects/<slug>.md → ## Open threads
Thread vague / stale    → drill [title](uuid) in ## Recent → transcript tail
Past decisions / why    → distill ## Decisions; chat link if still thin
New or unknown project  → GLOBAL_CONTEXT.md → Projects table
Deploy / CI / git task  → conventions.md
Proposing architecture  → fails + wins + preferences (Flow E)
```

**`## Next step` was removed** (v0.29+) — deprecated since v0.24. The forward pointer is `## Open threads`; distill never creates the old section, and existing bodies are left untouched wherever a hub still has one.

Distill runs on Claude Code's `SessionStart`, `Stop`, `PreCompact` and `SessionEnd`, and on
Cursor's 2-hourly job. Manual batch: `sync-memory.py`.

Full routing table and self-checks: [INSTRUCTIONS.md → Session start](INSTRUCTIONS.md#session-start).

## Chat distill pipeline

Transcripts are read-only and live under each environment's root (see the table above).
Agents must **not** load raw jsonl.

```
transcript jsonl
    → distill-extract.py     structured JSON (segments, summary_bullets, decision_candidates)
    → distill-merge.py       manifest + merge-staging/*.md
    → semantic-merge skill   agent curates ## Decisions ([curated] bullets)
    → apply on hooks/sync     Recent ≤3 + novel [extracted] (cap → archive)
    → open_thread_draft       optional [auto] ## Open threads from tail segment
    → verify-memory.py       integrity + secrets scan
```

- **Staging** — Raw candidates, topic segments, decision candidates, rolling summary (agent review).
- **`--apply`** — mechanical bookkeeping only; does not clobber curated Decisions (v0.5+).
- **Open threads** — curated via `memory-pointer.py add-thread`; distill writes `[auto]` drafts only; auto never overwrites curated (v0.26+).
- **manifest.json** — `distilled_at` + watermark (`watermark_user_count`, `watermark_tail_hash`) for content-aware re-distill.
- **Long chats** — topic segmentation + importance-weighted per-segment selection; optional map-reduce for very long threads.
- **`[extracted]`** — precision-filtered decisions (cue-at-start, junk markers); max 30 per project file; FIFO evict to `chats/archive/<slug>-decisions.md`.
- **Curation queue** — sessionStart lists pending `[auto]` open-thread drafts for semantic-merge / add-thread.
- **Health** — `memory-health.py` + weekly baseline; not just structure/secrets verify.

Details: [INSTRUCTIONS.md → Chat memory](INSTRUCTIONS.md#chat-memory-chats) · [MIGRATION.md](MIGRATION.md).

## Hub search (v0.19+)

No vector DB — on-demand **BM25-lite** over searchable units (bullets + context paragraphs):

```
memory-search.py "query" [--layer chats,context,feedback] [--deep] [--top 8]
    → lib/hub_search.py   scan hub markdown (+ optional extracts within retention_days)
    → templates/lang search_synonyms   query expansion (prod/production/…)
    → metrics.jsonl event search_query
```

- **Layers indexed:** `chats/projects/*.md`, `chats/archive/*-decisions.md`, `context/`, `feedback/`.
- **Archive weight** — evicted decisions score at **0.7×** vs active project bullets; corpus deduped per `(path, normalized text)`.
- **Deep tier** (`--deep`) — `chats/extracts/*.json` within `retention_days` (same window as `memory-doctor --fix` cleanup); includes `summary_bullets`, `decision_candidates`, segment bullets.
- Agents: «how did we do X» / past decision → run search before reading files blindly ([INSTRUCTIONS.md](INSTRUCTIONS.md)).

## Skills and hooks

**Plugin bundle** ships `skills/agent-memory/SKILL.md` for both environments, plus `hooks/claude/hooks.json` for Claude Code. Each environment's manifest lives under its own subdirectory: Claude Code also probes `hooks/hooks.json` at the bundle root and fails schema validation on Cursor's event names (`afterFileEdit`), so neither manifest may sit there.

**Cursor has no hook support** (dropped June 2026). `hooks/cursor/hooks.json` and the scripts beside it are **never executed** — Cursor's trigger is the launchd job, every 30 minutes. They are kept only for manual invocation and as the shape a future Cursor hook API would take; do not expect editing them to change anything. Other protocols under `skills/*/SKILL.md` for on-demand Read.

| Canonical event | Role |
|------|------|
| `sessionStart` | First-run bootstrap; catch-up distill; open-thread curation reminders |
| `promptSubmit` | Inject Open threads (Claude only — replaces Cursor's `alwaysApply` rule) |
| `liveDistill` | Per-turn distill to staging, no project apply (Claude `Stop`) |
| `sessionEnd` / `preCompact` | Distill current chat; enqueue open-thread curation on `[auto]` draft |
| `afterFileEdit` | Log chats hub edits |

`preCompact` with `trigger=auto` is the context-limit case: together with `liveDistill` it means
memory survives compaction and hard kills, not just a clean exit.

See [docs/SYNC-AND-TRIGGERS.md](docs/SYNC-AND-TRIGGERS.md) · [ONBOARDING.md](ONBOARDING.md).

## Verification and hygiene

| Tool | When | What |
|------|------|------|
| `memory-status.py` | anytime | dashboard: sizes, pending chats |
| `memory-doctor.py` | after setup | paths, skills, pending count |
| `verify-memory.py` | weekly | structure, secrets, rotation limits |
| `weekly-verify.sh` | cron | doctor + strict verify + gitleaks |

CI in this repo: tests + pinned gitleaks on every push; GitHub Release on tag.

## Rotation

- **Chat `[extracted]` cap** — automatic FIFO to `chats/archive/<slug>-decisions.md` (default 30); `compact_archive_decisions()` dedupes archive files.
- **Open threads cap** — 7 bullets; oldest `[auto]` evicted first at cap.
- **Manual rotation** — when `projects/<slug>.md` or context/feedback files exceed ~80–100 lines, agent archives older blocks to dated files and keeps INDEX pointers.

## What this is not

- Not a vector database or RAG product
- Not automatic — session end updates and distill are disciplined habits
- Not vault-grade secrets handling (regex + gitleaks safety net; never store credentials in the hub)

## Further reading

| Doc | For |
|-----|-----|
| [README.md](README.md) | Quick start, scripts list |
| [MIGRATION.md](MIGRATION.md) | First-time setup, migrate hub, agent prompts |
| [INSTRUCTIONS.md](INSTRUCTIONS.md) | Full agent protocol |
| [VERSIONING.md](VERSIONING.md) | SemVer and releases |
