# Agent Memory — Instructions for AI Agents

Read when user invokes **@agent-memory** (single entry skill).

**Do not load every layer every session.** Read files directly — internal detail lives in `skills/*/SKILL.md`.

---

## Setup (first time)

User says: **set up agent memory**. Run the wizard in `skills/agent-memory/SKILL.md` → Set up agent memory (hub path, scan, scope, verify).

## Sync (refresh)

User says: **sync with agent memory**. Ask: **180 days** (default) + optional **limit**. Run `sync-memory.py`. Report: Projects N · Distills M · Ready to work.

See [ONBOARDING.md](ONBOARDING.md) · [docs/SYNC-AND-TRIGGERS.md](docs/SYNC-AND-TRIGGERS.md).

---

## When to read what

| Question | Files |
|----------|-------|
| Who am I / my projects | `$MEMORY_HOME/context/GLOBAL_CONTEXT.md` |
| Git, CI, deploy rules | `$MEMORY_HOME/context/conventions.md` |
| Servers, paths, ports | `$MEMORY_HOME/context/infra.md` |
| Where we stopped | `$MEMORY_HOME/chats/projects/<slug>.md` → **## Next step** (auto on distill) |
| What we discussed | `$MEMORY_HOME/chats/projects/<slug>.md` |
| «How did we do X» / find past decision | `memory-search.py "terms"` first, then hit `path#section` |
| Full chat when distill thin | `[title](uuid)` link in distill ## Recent |
| What worked / failed (+/−) | `$MEMORY_HOME/feedback/{wins,fails}.md` |
| How user thinks | `$MEMORY_HOME/context/preferences.md` |

---

## Session start

**Goal:** minimum context to act. One layer is often enough.

### Step 0 — route by question

| Situation | Read |
|-----------|------|
| Continue known repo | **distill** `chats/projects/<slug>.md` → **## Next step** first, then Recent / Decisions |
| `## Next step` has `_No forward pointer._` or `[?]` | **Mandatory drill-down:** follow `[title](uuid)` in that line → transcript tail (~10–20 turns, not full jsonl); then `## Decisions` / `## Recent` in same file |
| User asks «what did we decide» / history / «why» | distill `## Decisions` for that slug |
| New project, unknown workspace | **GLOBAL_CONTEXT** — Projects table |
| Task touches deploy, git, CI, secrets | **conventions.md** (not every session) |
| Task touches SSH, prod, Docker ports | **infra.md** (not every session) |
| Proposing CI, deploy, staging, architecture, process | **feedback** fails + wins + **preferences.md** |
| User previously rejected an approach | **fails.md** (honour `_superseded_` → rule in conventions) |

### Step 1 — Typical flows

**Flow A — continue known project (most common)**

```
1. chats/projects/<slug>.md → ## Next step (if _No forward pointer._ or [?] → drill chat link in that line first)
2. ## Decisions + latest Recent
3. If still thin → open [title](uuid) from Recent (transcript tail only)
```

**Flow B — need background on decisions**

```
1. chats/projects/<slug>.md → ## Decisions
```

**Flow C — first session / hub setup**

```
1. context/GLOBAL_CONTEXT.md
```

**Flow D — cross-project convention question**

```
1. context/conventions.md
2. Optional: GLOBAL_CONTEXT.md → Projects
```

**Flow E — proposing a plan / policy / architecture**

```
1. feedback/fails.md     (skip _superseded_ lines)
2. feedback/wins.md
3. context/preferences.md
4. context/conventions.md if touching rules
```

### Step 2 — INDEX if lost

- `context/INDEX.md` — global layer map
- `chats/INDEX.md` — which project distill exists
- `feedback/INDEX.md` — wins/fails map

### Rules

- Apply silently — do not dump files to the user
- Never load raw `agent-transcripts/*.jsonl` into context
- `$MEMORY_HOME` default: `<clone>/memory/` (gitignored; override with env var)

### Secrets policy (hard requirement)

**Never** store passwords, tokens, API keys, private keys, JWT, htpasswd hashes, Basic-auth URLs, or `.env` / `db_config` **values** in `$MEMORY_HOME` or distill output.

| Layer | Rule |
|-------|------|
| **distill-extract.py** | Redacts known secret patterns; drops short `.env`-only noise; field `secrets_redacted` in JSON |
| **Agent merge** | Do not copy credentials from extract into `chats/projects/*.md`; paraphrase without secrets |
| **feedback / conventions / infra** | Hosts and paths OK; **no** live passwords, tokens, or key material |
| **verify-memory.py** | `no secrets in hub` must pass — run weekly (regex; optional `--strict-secrets`, `--gitleaks` if installed) |

Secrets handling is a **safety net**, not vault-grade protection. If a chat contained credentials: distill may show `[REDACTED-SECRET]`; write decisions in neutral form ("use env on server", not the value).

```bash
python3 $FRAMEWORK_ROOT/scripts/verify-memory.py --memory-home "$MEMORY_HOME"
```

### Step 3 — Session start verification (when routing matters)

After reading routed layers, **self-check** (internal — do not dump files unless asked):

| Layer read | Prove it — answer from file |
|------------|------------------------------|
| GLOBAL_CONTEXT | Name projects from Projects table |
| conventions | State one cross-project rule in one sentence |
| distill Next step | State forward pointer from `chats/projects/<slug>.md` |
| feedback/fails | Name one `_superseded_` lesson (Flow E / proposing) |

If any answer is wrong or empty → re-read that layer. Full checklist: [scripts/session-smoke.md](scripts/session-smoke.md).

**Drift detection (monthly):** user asks "without reading memory files — what do you know about my projects?" — correct answer is "I don't know without the files"; listing projects without reading = routing broken.

**Weekly integrity:** `python3 scripts/verify-memory.py --memory-home "$MEMORY_HOME"` → fix all ❌.

---

## Session end

**Goal:** persist only what changed this session.

### Checklist

| If this happened… | Update… |
|-------------------|---------|
| New **cross-project** rule (git, CI, deploy policy) | `$MEMORY_HOME/context/conventions.md` |
| New host, path, port | `$MEMORY_HOME/context/infra.md` |
| New project in rotation | `$MEMORY_HOME/context/GLOBAL_CONTEXT.md` → Projects row |
| Substantive **decisions, preferences, plans** from chat | `$MEMORY_HOME/chats/projects/<slug>.md` |
| Distilled a Cursor chat | `distill-merge.py <uuid>` → manifest + `merge-staging/`; merge staging into `projects/<slug>.md` |
| User **rejected** a proposal | `$MEMORY_HOME/feedback/fails.md` (− bullet under `## YYYY-MM Topic`) |
| User **praised** an approach | `$MEMORY_HOME/feedback/wins.md` (+ bullet) |
| Rejection became a **stable rule** | `conventions.md` **and** `_superseded → conventions.md § <heading>` on fail line |
| User stated **thinking / comms** preference | `$MEMORY_HOME/context/preferences.md` |

### After writing

- Set `_Last updated_` or `distilled_at` (ISO `YYYY-MM-DDTHH:MM:SS`; legacy date-only OK) in touched files
- Trim `## Recent` in chat files to last **3** sessions
- Do **not** put session progress in `conventions.md`

---

## Core idea (layers)

| Layer | Location | Answers | Max size |
|-------|----------|---------|----------|
| **Global context** | `context/` | Who? Rules? Projects? | ~40–80 lines/file |
| **Preferences** | `context/preferences.md` | How user thinks? | ~40 lines |
| **Feedback** | `feedback/wins.md`, `fails.md` | What +/− worked? | accumulates, ~80 then archive |
| **Chat memory** | `chats/projects/` | History + **## Next step** (forward pointer) | ~100 lines/file |

**Separation:** rules (conventions) ≠ style (preferences) ≠ lessons (feedback) ≠ history (Decisions/Recent) ≠ now (**Next step** in distill).

---

## Global context (`context/`)

```
context/
├── INDEX.md
├── GLOBAL_CONTEXT.md     Me + Projects (~30 lines)
├── conventions.md        Stable rules (normative now)
├── preferences.md        Thinking / communication style
├── infra.md              Hosts, paths
└── archive/              Rotated conventions
```

**Rotation:** `conventions.md` > ~80 lines → `archive/NNN-YYYY-MM-DD-conventions-<slug>.md`

---

## Feedback memory (`feedback/`)

```
feedback/
├── INDEX.md
├── wins.md       + empirical successes
├── fails.md      − rejected / failed (use _superseded_)
└── archive/
```

### Format

```markdown
## 2026-06 Deploy policy
+  manual approve after green CI — safe for solo prod
-  auto-deploy on merge — too risky without staging parity
  _superseded → conventions.md § Deploy (approval flow)_
```

**`_superseded_`:** when a fail is codified in `conventions.md`, mark the fail so agents do not treat it as an open debate.

**Rotation:** wins/fails > ~80 lines → `feedback/archive/NNN-YYYY-MM-feedback-<slug>.md`

---

## Chat memory (`chats/`)

```
chats/
├── INDEX.md
├── manifest.json         processed[] + pending[]; each entry has distilled_at
├── projects/<slug>.md    active distill (≤ ~100 lines; verify-memory)
├── archive/
│   └── <slug>-decisions.md   FIFO-evicted [extracted] (searchable, 0.7× weight)
├── merge-staging/        agent review after distill
└── extracts/             structured JSON per chat (--deep search)
```

### manifest.json (required after init)

```json
{
  "_schema": {
    "date": "transcript last activity (file mtime)",
    "distilled_at": "when distill merged into projects/*.md",
    "secrets_policy": "no credentials in hub; distill redacts; verify-memory weekly"
  },
  "processed": [
    {
      "id": "<uuid>",
      "workspace": "Users-<user>-Work-<project>",
      "date": "2026-06-04",
      "distilled_at": "2026-06-06",
      "distilled_to": ["projects/my-app.md"],
      "summary": "first user message excerpt"
    }
  ],
  "pending": []
}
```

**Re-distill** when pending: new chat, transcript **mtime** newer than `distilled_at`, or **watermark** changed (`watermark_user_count` / `watermark_tail_hash` in manifest entry — see `lib/distill_watermark.py`).

**Pending chats:** `python3 <framework>/scripts/list-chats.py --pending`

Transcripts (read-only): `~/.cursor/projects/*/agent-transcripts/<uuid>/<uuid>.jsonl` — skip `subagents/`.

### Chat distill rule

- **NEVER** read raw `.jsonl` into agent context
- **NEVER** write passwords/tokens/auth into `projects/*.md` or `manifest.json`
- **Preserve original chat language(s)** — do not translate during extract or merge
- **Flow:** `distill-extract.py` → `distill-merge.py` (manifest + staging) → agent curates `## Decisions` via semantic-merge → hooks/sync `--apply` for bookkeeping
- **Strategy:** `--strategy auto` → **importance** (per-segment selection for long chats); legacy: `tail`, `spread`, `all`
- **`--apply`:** Recent ≤3, `## Next step`, mechanical `## Summary` if empty, novel `[extracted]` from `decision_candidates` (cap 30 per file; FIFO evict to `archive/<slug>-decisions.md`). **Never** raw staging bullets into curated Decisions
- **`[extracted]` vs curated:** hooks append precision-filtered `[extracted]`; agent writes `[curated]` / keeps `[bootstrap]` — curated bullets are not evicted by cap

```bash
python3 $FRAMEWORK_ROOT/scripts/distill-merge.py <uuid> --strategy auto --memory-home "$MEMORY_HOME"
# Review staging: merge-staging/<slug>-<date>-<uuid>.md (## Raw candidates → curated Decisions)
python3 $FRAMEWORK_ROOT/scripts/distill-merge.py <uuid> --apply --memory-home "$MEMORY_HOME"
python3 $FRAMEWORK_ROOT/scripts/distill-merge.py <uuid> --apply --project example-app --memory-home "$MEMORY_HOME"
python3 $FRAMEWORK_ROOT/scripts/verify-memory.py --memory-home "$MEMORY_HOME" --strict-secrets --gitleaks
```

**Hooks:** plugin `hooks/hooks.json` — `sessionStart`/`workspaceOpen` (first-run + catch-up), `sessionEnd`/`preCompact` distill, `afterFileEdit` log. Do not merge into global `~/.cursor/hooks.json`.  
**Chat links:** Recent lines use `[title](uuid)` when transcript exists — follow link if distill lacks detail.  
**Cursor rule:** optional `templates/cursor-rule/agent-memory-session-end.mdc`.

**Semantic merge:** skill `semantic-merge` + `templates/chats/semantic-merge-prompt.md` — agent curates Decisions from staging (not `--apply`).

**Search:** `memory-search.py` — active `projects/*.md` + `archive/*-decisions.md` + context/feedback; `--deep` adds `extracts/*.json` within `retention_days`. Prefer search before loading whole project files.

**Hub thresholds** (optional in `$MEMORY_HOME/config.json` → `thresholds`): `max_extracted_decisions_per_file` (30), `max_decisions_add_per_distill` (6), `max_layer_file_lines` (100), `distill_token_budget`, `segment_max`, etc. — defaults in `lib/defaults.py`.

**Generic transcripts:** import jsonl to `$MEMORY_HOME/transcripts/<uuid>.jsonl` — `transcript_generic` adapter.

**Weekly cron:** `bash $FRAMEWORK_ROOT/scripts/weekly-verify.sh` (uses resolved `$MEMORY_HOME`; logs to `$MEMORY_HOME/logs/`).

**Health / repair:** `memory-doctor.py` — overview; `--fix` aligns anchor + hub `config.json`; `--gitleaks` optional scan.

### Distill template

```markdown
## Summary | ## Decisions | ## Next step | ## Preferences | ## Open threads | ## Recent
```

**Forward pointer:** `## Next step` — one bullet, overwritten on each boundary distill (`lib/forward_pointer.py` heuristics on transcript tail). When no pointer is extracted, apply writes `_No forward pointer._` or `[?] _Not refreshed._` plus a drill link to the source chat. Agent may curate manually after hooks run.

---

## Scalability (all layers)

1. **INDEX first** — never load whole tree
2. **Route by question** — not all layers every time
3. **Rotate** before files grow large
4. **Freshness** — `distilled_at`, episode numbers, `_Last updated_`

---

## Skills

**One Cursor skill:** `@agent-memory` — install: `bash scripts/install-local.sh` → Reload Cursor

Deep dives (read on demand): `skills/semantic-merge/SKILL.md`, `templates/chats/semantic-merge-prompt.md`, [ARCHITECTURE.md](ARCHITECTURE.md).

---

## User onboarding

**Start here:** [ONBOARDING.md](ONBOARDING.md) · [MIGRATION.md](MIGRATION.md)

1. `git clone` → `bash scripts/install-local.sh` → Reload Cursor
2. `bash scripts/init-memory.sh` (hub + anchor, idempotent)
3. In chat: **sync with agent memory** (or `sync-memory.py`)

### Path resolution (all scripts)

`MEMORY_HOME`: CLI `--memory-home` → `$MEMORY_HOME` env → anchor `~/.cursor/agent-memory/config.json` → default `~/.cursor/agent-memory/`.  
`PLUGIN_ROOT`: detect from script path → `.cursor-plugin/plugin.json`.  
Scripts write user data **only** to `$MEMORY_HOME`; anchor at fixed path outside bundle.

---

## Anti-patterns

- Reading all layers on every message
- Re-proposing ideas marked `_superseded_` in fails.md
- Putting empirical +/- lessons only in chat memory (use feedback/)
- One giant context file
- Raw jsonl in memory files
- **Secrets in memory files** — passwords, tokens, API keys, JWT, private keys, `.env` values (blocked by distill redaction + `verify-memory`)
- Pasting credentials into chat distill «for reference»
- Committing `$MEMORY_HOME` to git
- Putting personal data inside the `agent-memory` framework clone
- Relying on stale **## Next step** without re-distill after long sessions

---

## Framework vs user data

| In git (`agent-memory` repo) | Private (`$MEMORY_HOME`) |
|------------------------------|--------------------------|
| INSTRUCTIONS, skills, templates | GLOBAL_CONTEXT, feedback, chats, manifest |
| Rotation rules | Domain-specific skills, books |

**Later (separate repo):** `architecture-advisor`-style skills — empty `references/`, user fills own sources. Not part of agent-memory.
