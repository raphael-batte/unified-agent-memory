# Architecture — Agent Memory

Human-oriented overview. Runtime protocol for agents: [INSTRUCTIONS.md](INSTRUCTIONS.md).

## Problem

Cursor agents start each session with no durable memory. Project rules help for one repo, but not for:

- cross-project conventions (deploy, git, CI)
- what you already rejected or praised
- distilled history of long chat threads
- where you stopped yesterday in a multi-repo workflow

This framework is a **routed memory system**: small INDEX-first files, explicit layer choice per task, rotation at size limits, and tooling so agents never load megabyte jsonl transcripts.

## Plugin bundle + external hub

| Entity | Location | On plugin update |
|--------|----------|------------------|
| **Bundle** (code) | Cursor plugin dir (`~/.cursor/plugins/local/agent-memory/`) | replaced |
| **Anchor** | `~/.cursor/agent-memory/config.json` | survives |
| **Hub** (data) | path from anchor (default `~/.cursor/agent-memory/`) | survives |

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
| **Chat memory** | `chats/projects/<slug>.md` | History + **`## Next step`** forward pointer | ~100 lines/file |

**Separation of concerns:**

- `conventions.md` — normative rules (deploy policy, git flow)
- `preferences.md` — style and thinking (not rules)
- `feedback/` — empirical lessons; `_superseded_` when a fail became a convention
- `chats/projects/` — distill history; **Next step** = where to continue (auto on hooks)

## Routing (session start)

```
Continue known repo     → chats/projects/<slug>.md → ## Next step first
No pointer / [?]        → mandatory drill: [title](uuid) in Next step → transcript tail
Past decisions / why    → distill ## Decisions; chat link if still thin
New or unknown project  → GLOBAL_CONTEXT.md → Projects table
Deploy / CI / git task  → conventions.md
Proposing architecture  → fails + wins + preferences (Flow E)
```

Boundary hooks distill on `sessionStart` (first-run + catch-up), `workspaceOpen`, `sessionEnd`, `preCompact`. Manual batch: `sync-memory.py`.

Full routing table and self-checks: [INSTRUCTIONS.md → Session start](INSTRUCTIONS.md#session-start).

## Chat distill pipeline

Transcripts live in `~/.cursor/projects/*/agent-transcripts/` (read-only). Agents must **not** load raw jsonl.

```
transcript jsonl
    → distill-extract.py     structured JSON (~10–50 KB)
    → distill-merge.py       manifest + merge-staging/*.md
    → semantic-merge skill   agent curates ## Decisions
    → apply on hooks/sync     Recent ≤3 + ## Next step (pointer or placeholder + drill link)
    → verify-memory.py       integrity + secrets scan
```

- **Staging** holds raw candidates for human/agent review.
- **`--apply`** does not write raw user bullets into Decisions or Summary (v0.5+).
- **manifest.json** tracks `distilled_at` + watermark (`watermark_user_count`, `watermark_tail_hash`) for content-aware re-distill.
- **Long chats** — importance-weighted sampling, token budget, mechanical map-reduce windows in staging; agent reduces via semantic-merge skill.
- **Pointer** — regex in hooks; agent curates via `pointer-curate-prompt.md` when confidence low.
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

- **Deep tier** (`--deep`) reads `chats/extracts/*.json` not older than `retention_days` in hub `config.json` — same window as `memory-doctor --fix` cleanup.
- Agents: «how did we do X» / past decision → run search before reading files blindly ([INSTRUCTIONS.md](INSTRUCTIONS.md)).

## Skills and hooks

**Plugin bundle** ships `skills/agent-memory/SKILL.md` and `hooks/hooks.json` (no global `~/.cursor/hooks.json` merge). Other protocols under `skills/*/SKILL.md` for on-demand Read.

| Hook | Role |
|------|------|
| `sessionStart` / `workspaceOpen` | First-run bootstrap; catch-up distill |
| `sessionEnd` / `preCompact` | Distill current chat; pointer queue |
| `afterFileEdit` | Log chats hub edits |

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

When a layer file exceeds ~80–100 lines, archive to `archive/NNN-YYYY-MM-DD-<slug>.md` and keep INDEX pointers. Prevents unbounded growth and keeps agent context small.

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
