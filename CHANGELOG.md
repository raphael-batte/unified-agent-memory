# Changelog

All notable changes to **cursor-agent-memory** (framework). Format [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning [SemVer](https://semver.org/).

Data hub (`$MEMORY_HOME`) is **not** versioned with this file.

## [Unreleased]

## [0.21.0] - 2026-06-08

### Added

- **`lib/segment_selection.py`** — per-segment sqrt(count) budget, message trim (~450 chars), composite `summary_bullets`
- **`lib/decision_extract.py`** — O(n) commitment/correction scan over **all** user messages; `decision_candidates` in extract
- **Extract schema** — `summary_bullets`, `decision_candidates`, `coverage_ratio`, `decisions_extracted`
- **Metrics** — `segment_count`, `coverage_ratio`, `decisions_extracted` on boundary distill events

### Changed

- **Topic segmentation (v0.20)** — full chat coverage: merge smallest adjacent segments until ≤6; `segment_min_messages` (default 3) absorbs false early breaks
- **Long-chat sampling (v0.20)** — chats ≥ `map_reduce_threshold` use per-segment importance selection instead of global top-N
- **`window_summaries`** — deprecated (empty in extract); segment `bullets` replace map-reduce windows
- **Merge** — mechanical `## Summary` from `summary_bullets` when empty; append novel `[extracted]` decisions (cap 6) without clobbering curated
- **Staging** — segment bullets + decision candidates; coverage line
- **Deep search** — indexes `summary_bullets`, `decision_candidates`, segment bullets in extracts
- **`novelty.py`** — uses `markdown_sections` (fixes import cycle with `project_merge`)

## [0.19.0] - 2026-06-11

### Added

- **`lib/hub_search.py`** + **`memory-search.py`** — BM25-lite search over hub bullets (no DB); prefix token match RU/EN; section weights; recency boost
- **`lib/markdown_sections.py`** — shared section/bullet parser for merge + search
- **`lib/search_lang.py`** — `search_synonyms` in `templates/lang/*.json` for query expansion
- **`--deep`** search tier — `chats/extracts/*.json` within `retention_days` (same knob as hub cleanup)
- **`scripts/verify-hub-upgrade.sh`** — post-upgrade doctor + verify + search smoke
- **`memory-health`** — `search_queries`, `search_hit_rate`

### Changed

- **Marketplace copy** — `plugin.json` description and version sync with `VERSION`
- **Docs** — README search section; SKILL routing for «how did we do X»; ARCHITECTURE search layer
- **CHANGELOG** — corrected release dates for 0.14–0.18

## [0.18.0] - 2026-06-11

### Added

- **Real pointer adherence (1.4)** — `pointer_feedback` compares `## Next step` tokens with session-tail user messages + open TodoWrite → `followed` / `partial` / `ignored` / `resumed_blind` / `unmeasured`
- **Agent live distill (2.2)** — `templates/chats/live-distill-prompt.md`; preCompact `user_message` targets `merge-staging/*-live.md`; merge reads agent live summary + next-step candidate
- **`lib/agent_live_distill.py`** — find/parse/enrich `*-live.md`; `agent_live` pointer source (0.92 confidence)

### Changed

- **Provenance rename** — `live` → `strong_signal` (user_commitment / todo_state); new `agent_live` class; legacy manifest `live` normalized on read
- **`last_assistant_summary`** — longest paragraph instead of last (less sign-off fluff)
- **`topic_segmentation`** — lazy `new_task` pattern with hub `config.lang` override
- **`ru.json`** — drop bare single-word RU commitment prefixes (false positives at 0.95)
- **`memory-health`** — `pointer_adherence_rate` + breakdown; disk hit rate uses `disk_hit`
- **Clobber metric** — no false `pointer_clobbered_cross_chat` when curated Next step preserved

## [0.17.0] - 2026-06-11

### Added

- **Topic segmentation 2.4** — pause gaps + Jaccard lexical shift (thresholds via hub `config.json`)
- **Rolling compaction 2.6** — queue at 15 segments, mechanical dedup at 25; `kind: compaction` in curation queue
- **`hub_retention.py`** — `memory-doctor --fix` deletes stale `merge-staging/` + `extracts/` for processed chats (default 30d)
- **`hub_health.py`** — disk pointer rate, curation queue age, staging orphan rate in `memory-health.py`

### Changed

- **2.7 Strategies** — `auto`/`importance` use ranked sampling; `tail`/`spread` are positional only
- **Token estimate** — Cyrillic-weighted `estimate_tokens()` for budget sampling

## [0.16.0] - 2026-06-10

### Added

- **`lib/pointer_feedback.py`** — sessionStart `pointer_feedback` metrics (hit/miss/skip) from project `## Next step`
- **`lib/live_distill.py`** — `liveDistill` event: extract + staging/manifest without `--apply` on sessionStart when watermark changed
- **`lib/novelty.py`** — filter staging candidates that repeat existing Decisions/Summary/Next step
- Hub `config.json` thresholds: `distill_token_budget`, `map_reduce_threshold`, `map_reduce_window_size`
- Extract fields: `tokens_estimated`, `token_budget`, `token_budget_exceeded`

### Changed

- **`memory-health.py`** — `pointer_session_hit_rate`, live distill + budget-exceeded counts
- **`distill-merge` staging** — novelty filter on raw messages and rolling summary
- **`handle_session_start`** — live distill for active transcript + pointer feedback logging

## [0.15.0] - 2026-06-09

### Added

- **`lib/structured_signals.py`** — TodoWrite open items as `todo_state` pointer signal (0.90); skipped when all todos completed
- **`lib/pointer_provenance.py`** — curated / live / auto classes; `[curated]` marker; watermark gate for overwriting curated Next step
- **`memory-pointer.py`** — `set` / `show` curated ## Next step; updates manifest `pointer_source` / `pointer_set_at`
- Extract fields: `open_todos`, `all_todos_completed`, watermark; staging ## Open todos + ## Pointer candidate when curated preserved

### Changed

- **`forward_pointer`** — `todo_state` tier; `assistant_pattern` 0.55; weak assistant pattern when last user message is a question
- **`apply_extract_to_project`** — does not clobber `[curated]` unless live signal + watermark change
- **Manifest** — optional `pointer_source`, `pointer_set_at` on processed entries

## [0.14.0] - 2026-06-08

### Added

- **`lib/transcript_parse.py`** — unified JSONL parser (user/assistant/tool/todo state); single-read cache
- **`templates/lang/en.json`**, **`ru.json`** + **`lib/lang_cues.py`** — cue phrases for pointer, corrections, topic breaks; optional hub `config.lang` override
- **`lib/pointer_metrics.py`** — `pointer_clobbered_cross_chat` event when merge overwrites another chat's Next step
- Extract field **`final_summary`**; staging ## Summary prefers assistant tail over `first_query`

### Changed

- **`forward_pointer`**, **`message_importance`**, **`topic_segmentation`** — patterns built from lang JSON (framework source stays English-only)
- **`distill-extract`**, **`assistant_snippets`**, **`forward_pointer`** — use shared transcript parser

## [0.13.0] - 2026-06-08

### Added

- **validate-plugin.mjs** — single-plugin marketplace structure check (manifest, skills frontmatter, hook scripts); runs in CI and `run-tests.sh`

### Changed

- **plugin.json** — `displayName`, `category`, `tags`, explicit `skills`/`hooks` paths, marketplace description
- **hooks.json** — `"version": 1`
- **Naming** — README and ARCHITECTURE use **Agent Memory** (no Cursor prefix in display name)

## [0.12.6] - 2026-06-08

### Fixed

- **migrate-memory** — default `--merge`: manifest merged by chat id; template stubs replaced from backup; loud report (copied/skipped/merged); `--overwrite` / deprecated `--ignore-existing`
- **Restore after reinstall** — safe when `init-memory` ran before migrate (sessionStart race)
- **memory-doctor** — `--rebuild-manifest`; desync warning when `processed=0` but project distills exist
- **verify-memory** — manifest desync surfaced as warning

## [0.12.5] - 2026-06-08

### Changed

- **Onboarding** — hook only creates hub + short `user_message`; full wizard in skill (`set up agent memory`)
- **SKILL.md** — steps: hub path / migrate → scan → scope → verify → optional GLOBAL_CONTEXT / Decisions
- **first_run.py** — `awaiting_setup` replaces hook auto-distill and scope prompts

## [0.12.4] - 2026-06-08

### Changed

- **Descriptions** — plugin.json, SKILL frontmatter, README, GitHub about: secrets redaction + verify/gitleaks
- **Schema** — README mermaid security layer; `manifest.json` `_schema.secrets_policy`

## [0.12.3] - 2026-06-08

### Fixed

- Strip legacy narrative; guard test; plugin logo
- CI: timezone-independent `test_same_day_redistill_with_iso` (GitHub runners before 09:00 UTC)

## [0.12.2] - 2026-06-08

### Changed

- **README** — plugin-first quick start; no git-clone hero; streamlined docs map
- **ARCHITECTURE / INSTRUCTIONS / SYNC-AND-TRIGGERS** — plugin hooks; removed legacy install narrative
- **sync-memory.py** — skips `install-memory-hooks.sh` when `.cursor-plugin/plugin.json` present
- **Shell tests** — plugin bundle layout, `first-run-scope`, legacy hook tests removed
- **MIGRATION** — removed backlog items from public quick reference

## [0.12.1] - 2026-06-08

### Added

- **First-run sentinel** — `$MEMORY_HOME/.state/initialized`; survives plugin updates
- **`lib/first_run.py`** — hub init, scan, scope presets, batch distill on `sessionStart` / `workspaceOpen`
- **`first-run-scope.py`** / **`first-run-continue.py`** — agent-orchestrated scope + continue after user choice
- **`[auto]` Decisions fallback** — `apply_mechanical_auto_decisions()` when distill fails on first run
- **Auto scope** — ≤40 pending (90d) → distill without prompt; larger libraries → `user_message` with presets

### Changed

- **`handle_session_start`** — first-run before catch-up; skips catch-up while awaiting scope
- **`hooks/hooks.json`** — `workspaceOpen` → same handler as `sessionStart`
- **ONBOARDING / SKILL** — first-run flow documented

## [0.12.0] - 2026-06-08

### Added

- **Cursor plugin shell** — `.cursor-plugin/plugin.json`, `hooks/hooks.json`, `skills/agent-memory/SKILL.md`
- **Fixed anchor** — `~/.cursor/agent-memory/config.json` (`memory_home` only; survives bundle updates)
- **External hub** — default `~/.cursor/agent-memory/`; templates materialize into hub, not bundle
- **`install-local.sh`** — delivery only (symlink + reload); no bootstrap in installer
- **`detect_plugin_root()`** — walk up to `.cursor-plugin/plugin.json` (location-agnostic)

### Changed

- **Path resolution** — `MEMORY_HOME`: CLI → env → anchor → default; `PLUGIN_ROOT` from bundle detect
- **`init-memory.sh`** — strictly idempotent; writes anchor + hub config via `persist_paths`
- **`memory-doctor --fix`** — align anchor + hub; migration note for legacy hooks/symlinks
- **Docs** — README, ONBOARDING, MIGRATION, ARCHITECTURE — plugin + anchor model

### Deprecated

- `link-cursor-skills.sh`, `install-memory-hooks.sh` — plugin bundle replaces symlinks / global hooks merge

## [0.11.0] - 2026-06-08

### Added

- **CONTRIBUTING.md** — PR → `main` workflow, local tests, version bump rules
- **PR template** — `.github/pull_request_template.md`
- **CI version-check** — `scripts/check-version-bump.py` on pull requests

### Changed

- **Single-clone model** — framework + gitignored `memory/` hub in one repo; simplified path resolution in `memory_config.py` and `config.sh`
- **Docs** — README, ARCHITECTURE, ONBOARDING, MIGRATION, SKILL, INSTRUCTIONS — prod-only setup (no dev/install narrative)

### Removed

- `dev.config.json` / `dev.config.json.example` and two-clone workflow
- `scripts/sync-to-install.sh`
- `.cursor/rules/cursor-agent-memory-dev.mdc`

## [0.10.2] - 2026-06-07

### Added

- **Pointer curation queue** — `.state/pointer-curation-queue.json`; sessionEnd enqueues placeholder/low-conf pointers; sessionStart `user_message` reminds agent
- **distill-map.py** — map-staging per window (`chats/map-staging/`) + `--reduce` → `reduce-staging/` for agent map-reduce pipeline
- **Metrics gap detector** — `memory-health.py` flags sessionStart telemetry without boundary events
- **Crash rows** — `boundary-crash-report.py` + Python exception handler; structured `{status: crash}` in metrics JSONL

### Changed

- **Boundary/session-start shells** — crash report on invalid JSON; session-start emits pointer queue `user_message`
- **distill-merge** — auto-writes map-staging for long chats; semantic-merge prompt prefers reduce-staging

## [0.10.1] - 2026-06-07

### Added

- **Health baseline** — `logs/health-baseline.json` rolling median pointer hit-rate; `memory-health.py --update-baseline --strict --notify` detects degradation vs personal norm
- **Agent pointer protocol** — `templates/chats/pointer-curate-prompt.md`; sessionEnd `user_message` + session-end rule point agents to curate `## Next step`
- **semantic-merge skill** — `skills/semantic-merge/SKILL.md` (was referenced but missing); map-reduce reduce step in semantic-merge prompt
- **Topic segments** — `topic_segmentation.py` for multi-task chats in extract/staging

### Changed

- **Metrics JSONL** — richer fields: `user_message_count`, `messages_used`, `strategy`, `truncated`, `secrets_redacted`
- **weekly-verify.sh** — health check with baseline update + macOS notification on degradation
- **ARCHITECTURE.md** / **SYNC-AND-TRIGGERS.md** — document v0.10 watermark, health, agent pointer model

## [0.10.0] - 2026-06-07

### Added

- **Manifest watermark** — `watermark_user_count` + `watermark_tail_hash` in `manifest.json`; `needs_distill()` prefers content delta over mtime alone (`transcript_stats.py`, `distill_watermark.py`)
- **Boundary debounce** — skip duplicate `preCompact`/`sessionEnd` distill for same chat within 30s (`boundary_debounce.py`)
- **Distill metrics** — append-only `logs/agent-memory-metrics.jsonl`; `memory-health.py` reports pointer hit-rate, errors, avg duration; wired into `weekly-verify.sh` and `memory-status.py`
- **Importance-weighted extract** — message scoring + token budget sampling; map-reduce `window_summaries` for chats ≥80 messages (`message_importance.py`, `token_budget.py`)
- **Assistant snippets** — selective assistant tail blocks in extract/staging (`assistant_snippets.py`)
- **Rolling incremental distill** — `chats/rolling/<chat>.json` + incremental bullets in staging (`rolling_distill.py`)
- **Pointer confidence** — `PointerResult` with source tier + confidence; `sessionEnd` prompts agent to curate `## Next step` when placeholder or low confidence

### Changed

- **Boundary hook** — `agent-memory-boundary.sh` splits stdout (JSON) from stderr (log only); boundary hooks record timing + metrics
- **`build_extract`** — accepts `memory_home` + manifest entry for incremental/rolling context

## [0.9.4] - 2026-06-07

### Security

- **Expanded secret detection** in `secrets_guard.py` — added provider-prefixed token patterns: Grafana (`glsa_`, `glc_`, legacy `eyJrIjoi…`), Slack (`xox[baprs]-`, `hooks.slack.com` webhooks), Google (`GOCSPX-` OAuth client secret, `6L…` reCAPTCHA, `AIza…` API key), GitHub fine-grained PAT (`github_pat_`), GitLab (`glpat-`), Stripe (`sk_live_`/`rk_live_`), Twilio (`SK…`), SendGrid (`SG.…`), npm (`npm_`), PyPI (`pypi-`); extended AWS to temp creds (`ASIA`) and private-key block to `DSA`/`PGP`
- **Fixed redaction miss on URL-encoded / concatenated secrets** — distinctive-prefix patterns no longer require leading/trailing `\b`, so secrets embedded in blobs like `…%22GOCSPX-…%22` are now redacted
- **Removed `eval` from path handling** — `lib/config.sh`, `migrate-memory.sh`, and `init-project-rules.sh` now expand a leading `~` via a safe `_expand_tilde` helper instead of `eval echo "$path"`, which would execute command substitutions / backticks embedded in `MEMORY_HOME`, `FRAMEWORK_ROOT`, or CLI path arguments
- **Path-traversal hardening** — slugs, uuids, `--project` overrides, and `manifest.distilled_to` entries are now reduced to a safe single path component (`safe_path_component`) before being interpolated into hub file paths, so a crafted transcript/extract/manifest cannot write or read outside the hub
- **Ignore `__pycache__`/`*.pyc`** — prevents committing compiled bytecode that embeds test fixture values

## [0.9.3] - 2026-06-07

### Fixed

- **`resolve_install_root`** — `dev.config.json` `install_root` wins over hook/env when running from dev clone; empty install dir (no `INSTRUCTIONS.md` yet) is valid — fixes CI `test_shell_scripts.sh` and local `sync-to-install --dry-run`

## [0.9.2] - 2026-06-07

### Added

- **`apply_guard.py`** — CLI `distill-merge --apply` blocks (exit 2) when curated `## Decisions` exist and last distill > N days; `--force-apply` / `--review-max-days` (default 7)
- **`init-project-rules.sh`** — generates per-workspace session-start `.mdc` with resolved `MEMORY_HOME` + slug; warns if distill missing
- **ONBOARDING «Second machine»** — 4-step multi-Mac setup

### Changed

- `resolve_memory_home()` — `DeprecationWarning` when reading legacy `~/.config/cursor-agent-memory/config.json`
- Hooks/sync pass `force_apply=True` — guard applies to CLI only; staging not overwritten on guard fail
- Hook env `MEMORY_HOME` ignored unless directory exists (skips stale broken paths)
- `agent-memory-session-end.mdc` — points to session-start rule

## [0.9.1] - 2026-06-07

### Added

- **`## Next step` placeholders** — `_No forward pointer._` or `[?] _Not refreshed._` with drill link to source chat when heuristics find no pointer
- **User commitment cues** in `forward_pointer.py` — last raw user message from jsonl; patterns `okay then`, `let's do`, RU commitment verbs
- **Explicit drill-down routing** in INSTRUCTIONS / SKILL when placeholder markers appear

### Changed

- Forward pointer priority: raw user commitment → user patterns → assistant patterns → assistant action-hint (lowest)
- `apply_extract_to_project()` always updates `## Next step` (pointer or placeholder) on every apply — including first sync / onboarding

## [0.9.0] - 2026-06-07

### Removed

- **Per-repo handoff layer** — `AGENT_HANDOFF.md`, `handoff_mode`, `templates/repo-handoff/`, `agent-handoff.mdc`

### Added

- **`## Next step`** forward pointer in `chats/projects/<slug>.md` — auto-extracted on every boundary distill (`lib/forward_pointer.py`)
- Boundary hooks use `apply=True` — Recent + Next step written on `sessionEnd` / `preCompact` / catch-up

### Changed

- Session routing: distill **Next step** first (no repo handoff files)
- `sync-memory.py` — no `--handoff-mode`; SKILL / INSTRUCTIONS / ONBOARDING updated

## [0.8.9] - 2026-06-07

### Added

- First sync seeds **`[bootstrap]` Decisions** from keyword-tagged user messages when `## Decisions` is empty
- ONBOARDING: post-sync agent offers (fill Me, review bootstrap, handoff setup); handoff section

### Changed

- `sync-memory.py` applies distills to `chats/projects/*.md` (`Recent` + bootstrap Decisions)
- `templates/feedback/fails.md` — no placeholder `_superseded § <heading>` (verify passes on fresh hub)
- README / GitHub description copy tightened

## [0.8.8] - 2026-06-07

### Changed

- Tests, fixtures, and docs use generic project names (`example-app`, `other-app`) — no real workspace names
- `tests/test_no_hardcoded_paths.py` — skip scanning itself (forbidden-pattern literals)

## [0.8.7] - 2026-06-07

### Changed

- **No hardcoded install paths** — removed `DEFAULT_INSTALL_ROOT`; install via `dev.config.json` / env / hook env only
- **Projects table paths** — decode Cursor workspace folder to real path; manifest stores `workspace_path`
- Docs/templates: `$MEMORY_HOME` / `$FRAMEWORK_ROOT` only — no legacy global config writes
- `tests/test_no_hardcoded_paths.py` — expanded forbidden path patterns

## [0.8.6] - 2026-06-07

### Added

- **Dev vs install split** — `dev.config.json` (gitignored) points dev clone at install root
- `scripts/sync-to-install.sh` — rsync framework dev → install; excludes `memory/`, `.git`, `dev.config.json`

### Changed

- **Clean dev repo** — scripts never create or use `<dev>/memory/` when `dev.config.json` exists
- `init-memory.sh`, `link-cursor-skills.sh`, `install-memory-hooks.sh` target install root + `<install>/memory/`
- Docs: [ONBOARDING.md](ONBOARDING.md), [ARCHITECTURE.md](ARCHITECTURE.md) — two-clone workflow

## [0.8.5] - 2026-06-07

### Changed

- **In-repo hub only** — default `$MEMORY_HOME` is `<clone>/memory/` (gitignored); no external hub or legacy global paths
- Framework scripts **do not write** legacy global config (read-only if present)
- `memory/config.json` holds `framework_root`, `memory_home`, `handoff_mode`
- Cursor hooks get `MEMORY_HOME` via `~/.cursor/hooks/agent-memory.env` (Cursor integration only)

## [0.8.4] - 2026-06-07

### Added

- `scripts/lib/hook_env.sh` — resolve framework clone path in Cursor hooks (no `$HOME/agent-memory` fallback)
- `persist_framework_root()` — writes real clone path to global + hub config on init/link/sync
- `tests/test_no_hardcoded_paths.py` — guard against fixed install directory in repo

### Changed

- Clone anywhere — paths resolved from config/env/script location
- Hook templates source `agent-memory.env` first; fail gracefully if framework unknown
- Restored root `SKILL.md` with `$FRAMEWORK_ROOT` / `$MEMORY_HOME` contract
- Docs: use `scripts/...` from repo root or `"$FRAMEWORK_ROOT/scripts/..."`

## [0.8.3] - 2026-06-07

### Added

- `lib/timestamps.py` — ISO `distilled_at`, mtime comparison, legacy `YYYY-MM-DD` compat

### Changed

- Re-distill when transcript **mtime** > `distilled_at` (same-day updates work)
- `manifest` / `_Last updated_` / staging use full ISO timestamps
- `collect_projects_from_manifest` keeps summary from latest `distilled_at`
- `filter_by_slugs` — exact slug match (no substring false positives)
- `sessionStart` catch-up — drop duplicate skip pass (`needs_distill` only in list)
- `_load_distill_modules()` — module-level cache
- `list-chats` STALE flag uses mtime vs `distilled_at`
- `verify-memory` rejects unparseable `distilled_at`

## [0.8.2] - 2026-06-06

### Added

- `sync-memory.py --scan-only` — fast inventory (`total_chats`, `active_90d/180d`, `pending_90d/180d`)
- Sync report fields: `distills_planned`, `truncated`, `candidates` (total before limit)

### Changed

- Sync flow: scan → user picks `--days` + `--limit` → run (documented in SKILL + ONBOARDING)
- `--dry-run` no longer reports fake `distills` count; uses `distills_planned`
- `sessionStart` catch-up skips when `workspace_roots` empty (no cross-project distill)

## [0.8.1] - 2026-06-06

### Added

- [ONBOARDING.md](ONBOARDING.md) — fresh clone walkthrough (one skill + sync)
- [docs/SYNC-AND-TRIGGERS.md](docs/SYNC-AND-TRIGGERS.md) — hooks and sync technical reference

### Changed

- INSTRUCTIONS, MIGRATION, ARCHITECTURE, README — distill-first, single skill, `handoff_mode`
- `session-end` hook checklist respects `handoff_mode: off`
- `memory-doctor.py` reports `handoff_mode`
- `init-memory.sh` next steps point to sync

## [0.8.0] - 2026-06-06

### Added

- **Distill-first core** — chat links `[title](uuid)` in staging/Recent when transcript exists
- `scripts/sync-memory.py` — init, hooks, batch distill (default 180 days), GLOBAL_CONTEXT bootstrap
- `handoff_mode` in hub config (`off` | `optional` | `required`)
- `sessionStart` catch-up distill (replaces handoff inject)
- Lib: `distill_links`, `pending_chats`, `memory_routing`, `global_context_bootstrap`
- Tests: `test_distill_links`, `test_pending_chats`, `test_memory_routing`, `test_sync_memory`, `test_global_context_bootstrap`

### Changed

- **Single skill onboarding** — `link-cursor-skills.sh` defaults to `agent-memory` only; expanded root `SKILL.md` with Sync protocol
- `preCompact` user_message references distills, not handoff
- `templates/config.json` — default `handoff_mode: optional`

### Removed

- `sessionStart` handoff `additional_context` inject (use distill + optional handoff read)

## [0.6.0] - 2026-06-06

### Added

- **Boundary hooks** — `sessionStart` injects `AGENT_HANDOFF.md` excerpt; `preCompact` / `sessionEnd` auto-distill pending chats
- `scripts/boundary-hooks.py`, `scripts/lib/boundary_hooks.py`
- Cursor templates: `agent-memory-session-start.sh`, `agent-memory-boundary.sh`
- `tests/test_boundary_hooks.py`

### Changed

- `install-memory-hooks.sh` — installs four hook scripts; merges `sessionStart`, `preCompact`, dual `sessionEnd` entries

## [0.5.1] - 2026-06-06

### Added

- [ARCHITECTURE.md](ARCHITECTURE.md) — human-oriented system overview (layers, routing, distill pipeline)

### Changed

- README — hero, layer diagram, inventory, docs map (closes gap vs INSTRUCTIONS depth)
- SKILL.md — version sync + link to ARCHITECTURE

## [0.5.0] - 2026-06-06

### Added

- **Release workflow** — `release.yml` on tag `v*`; guard tag == VERSION; GitHub Release from CHANGELOG section
- `scripts/extract-changelog.py` — extract one version block for release notes
- `.gitleaks.toml` — allowlist for test fixtures; pinned `GITLEAKS_VERSION` in CI

### Changed

- CI reusable via `workflow_call` (release job reuses test + gitleaks)
- `cross_layer_warnings` — document-frequency filter + bigram overlap; domain stopwords in `defaults.py`
- `gitleaks_scan` — auto `--config .gitleaks.toml` when present
- `--apply` no longer fills empty `## Summary` with raw `first_query` (agent/semantic-merge only)

## [0.4.3] - 2026-06-06

### Fixed

- CHANGELOG: English-only entry (CI `test_no_cyrillic_in_framework_repo`)

## [0.4.2] - 2026-06-06

### Fixed

- CI: `actions/setup-python@v6` (Node 24 native) — remove remaining setup-python deprecation warning

## [0.4.1] - 2026-06-06

### Fixed

- CI: `actions/checkout@v5`, `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` — silence Node 20 deprecation warnings

## [0.4.0] - 2026-06-06

### Added

- **semantic-merge** skill + `templates/chats/semantic-merge-prompt.md` — agent workflow for Raw candidates → Decisions
- Cursor rule `agent-memory-session-end.mdc` — checklist from `agent-memory-session.log`
- `lib/cross_layer_warnings.py` — keyword overlap fails ↔ conventions (+ superseded substring hints)
- **Generic transcript adapter** `lib/transcript_generic.py` + unified `lib/transcript.py`; hub path `$MEMORY_HOME/transcripts/<uuid>.jsonl`
- Extract field `transcript_adapter`: `cursor` | `generic`

### Changed

- `verify-memory` uses cross-layer warnings; `link-cursor-skills` includes semantic-merge
- `distill-extract` / `distill-merge` use unified transcript router

## [0.3.3] - 2026-06-06

### Fixed

- CI gitleaks job: install from versioned release asset (`gitleaks_*_linux_x64.tar.gz`)

## [0.3.2] - 2026-06-06

### Fixed

- `--apply` bookkeeping only: updates Recent≤3 + empty Summary — **does not** write raw user messages into `## Decisions`
- `--apply` target: `manifest.distilled_to` primary `projects/*.md` (not workspace slug); `--project` override
- Staging section renamed to `## Raw candidates (review — not Decisions)`

### Changed

- Hook templates aligned with `hooks.json`: `agent-memory-session-end.sh`, `agent-memory-after-edit.sh`
- Session hook logs to `~/.cursor/hooks/agent-memory-session.log` + stdout/stderr for visibility
- `gitleaks_scan`: prefers `gitleaks dir` (8.19+), falls back to `detect --no-git`

### Added

- GitHub Actions CI: `tests/run-tests.sh` + gitleaks adapter smoke on push/PR
- MIGRATION: multi-machine hub sync (private git repo)
- `primary_project_rel()` in `lib/chats_manifest.py`

## [0.3.1] - 2026-06-06

### Added

- `distill-merge.py --apply` — merge extract into `chats/projects/<slug>.md` (append Decisions, Recent≤3; secrets scan before write)
- `lib/project_merge.py` — project file merge helpers
- Hook v2: `afterFileEdit` template + `lib/hooks_config.py`; `install-memory-hooks.sh` installs sessionEnd + afterFileEdit
- `weekly-verify.sh` — cron helper (doctor + verify, strict secrets + gitleaks); `--dry-run`
- `lib/gitleaks_scan.py`; `verify-memory --gitleaks` / `--gitleaks-required`; `memory-doctor --gitleaks`
- `memory-doctor --fix` / `--fix-dry-run` — align global/hub `config.json`, relink skills (`lib/doctor_fix.py`)

### Tests

- `test_project_merge`, `test_hooks_config`, `test_gitleaks_scan`, `test_doctor_fix`; extended distill-merge, verify, doctor, shell suites

## [0.3.0] - 2026-06-06

### Added

- `distill-merge.py` — auto manifest `distilled_at`, extracts + `merge-staging/` (preserve chat language)
- `memory-doctor.py` — one-shot hub health (paths, chats, verify, skills)
- `lib/transcript_cursor.py` — Cursor jsonl adapter + `TranscriptSchemaError` + cached `find_transcript`
- `lib/chats_manifest.py`, `lib/defaults.py` — shared manifest/thresholds
- Cursor hooks template + `install-memory-hooks.sh` (sessionEnd reminder)
- `verify-memory --strict-secrets` — optional entropy scan (best-effort)
- Duplicate-lesson warnings in verify; path resolution documented in memory-doctor

### Changed

- `memory-status.py` — direct imports (no subprocess stdout regex)
- `list-chats.py` — `chat_counts()` API; cached transcript index
- Secrets docs: safety net wording (not a guarantee)
- INSTRUCTIONS: preserve chat language; distill-merge workflow

### Tests

- `test_distill_merge`, `test_transcript_cursor`, `test_memory_doctor`, `test_list_chats`, `test_defaults`, `test_chats_manifest`; updated existing suites

## [0.2.5] - 2026-06-06

### Added

- `lib/secrets_guard.py` — detect/redact secrets in distill; scan hub in `verify-memory`
- `distill-extract.py` — sanitizes user messages; JSON field `secrets_redacted`
- `verify-memory.py` — check `no secrets in hub` (context/feedback/chats)
- Tests: `test_secrets_guard.py`, `test_english_only.py`; docs: hard secrets policy in INSTRUCTIONS, MIGRATION, chat-memory skill
- English-only policy: removed Cyrillic from framework; agent prompts in MIGRATION.md translated

## [0.2.4] - 2026-06-06

### Fixed

- add MIGRATION.md setup and agent prompts guide

## [0.2.3] - 2026-06-06

### Fixed

- distill-extract --strategy spread/auto for long chats

## [0.2.2] - 2026-06-06

### Fixed

- add distill-extract.py for chat distill without raw jsonl

## [0.2.1] - 2026-06-06

### Fixed

- add unittest/shell tests; fix fails_open, --list exit code, migrate --to

## [0.2.0] - 2026-06-06

### Added

- v0.2: memory-status, config.json, skills-status, selective link, migrate

## [0.1.4] - 2026-06-06

### Fixed

- Neutral default paths: generic clone example, `$MEMORY_HOME` under clone or config

## [0.1.3] - 2026-06-06

### Added

- `scripts/publish-github.sh`

### Changed

- README: Feedback layer section; GitHub topics

## [0.1.2] - 2026-06-06

### Fixed

- Remove personal project paths and CI examples from framework docs
- `verify-memory.py`: conventions check is generic (sections), not coverage/staging keywords

## [0.1.1] - 2026-06-06

### Fixed

- Pre-commit: exempt doc-only paths (README, docs/, templates/)

## [0.1.0] - 2026-06-06

### Added

- Five memory layers: context, preferences, feedback, chats, handoff
- Skills: `agent-memory`, `global-context`, `chat-memory`, `agent-handoff`, `feedback-memory`
- `INSTRUCTIONS.md` — routing Flows A–E, session start/end, rotation
- Templates for context, feedback, chats, repo-handoff, cursor-rule
- `scripts/init-memory.sh`, `link-cursor-skills.sh`, `list-chats.py`
- `scripts/verify-memory.py` — weekly integrity checks (7 rules)
- `scripts/session-smoke.md` — session self-check + drift detection
- `_superseded → conventions.md § <heading>` format (not line numbers)
- SemVer: `VERSION`, this changelog, git pre-commit hook
