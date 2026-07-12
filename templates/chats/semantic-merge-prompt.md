# Semantic merge — agent prompt (copy into chat)

Use after `distill-merge.py` wrote `chats/merge-staging/<slug>-*.md`.

## Inputs

- Staging: `$MEMORY_HOME/chats/merge-staging/<file>.md`
- Target: `$MEMORY_HOME/chats/<project_rel>` (from staging header or manifest `distilled_to`)
- Language: **preserve original chat language** — do not translate

## Task

1. Read staging **## Topic segments** and **## Decision candidates** (from `distill-extract`) — primary source for long chats.
2. Read `## Raw candidates` — context only; **not** decisions verbatim.
3. If `chats/reduce-staging/<slug>-*.md` exists — prefer **## Reduced map summaries** (agent map phase done).
4. Else if `chats/map-staging/` exists — run `distill-map.py <uuid> --reduce` after filling Map sections, then read reduce-staging.
5. If only `## Window summaries (map-reduce)` — reduce each `[wN]` block into 1–2 Decisions bullets.
6. Read target `## Decisions` — keep existing `[curated]` / `[bootstrap]`; do not delete mechanical `[extracted]` (hooks manage cap + archive).
7. Write **new** `[curated]` bullets only where a candidate expresses a durable decision, preference, or constraint.
8. Paraphrase; merge duplicates; drop noise, commands, one-off debug, credentials.
9. Update `## Open threads` — **primary multi-track state** (rolling 30d). One bullet per
   active direction: `- **[label]** where it stopped · _upd YYYY-MM-DD_`.
   - `label` is auto: topic-segment slug / path in the message / workspace slug — never a
     hardcoded project enum.
   - `· _upd DATE_` is the **tail-of-topic timestamp** = last activity of that direction;
     the CLI stamps it and refreshes on re-touch. It drives the 30d window + eviction.
   - Upsert by label (replace the matching bullet, don't stack duplicates); cap 5–7,
     drop directions with no activity ~30d.
   - Junk filter: skip system prompts, `<mcp_meta_tools>`, bullets < 40 chars, and dupes.
   - Prefer the CLI so formatting/cap stay consistent:
     `memory-pointer.py add-thread <project> <dir> "…"`.
10. **`## Next step` is deprecated** — do not curate; forward pointer = Open threads only.
11. Do **not** paste raw candidate text into Decisions; do not duplicate bullets already in `chats/archive/<slug>-decisions.md`.
12. Run `verify-memory.py`; hooks already updated Recent + `[extracted]` — do not `--apply` over curated Decisions.

## Output format (Decisions bullets)

- One line per decision; imperative or past-tense fact
- Preserve chat link from staging Recent when present: `[title](full-uuid)`
- Or short ref: `` (`<uuid-prefix>`) ``
- No passwords, tokens, API keys, `.env` values

## Example transform

| Raw candidate | Curated Decision |
|---------------|------------------|
| "fix submit so row creates on real submit only" | **Ghost articles:** create row only on real submit; title required (`43f91e19`) |
| "what is the local admin password" | *(skip — no secret; use .admpassfile locally, not in hub)* |

## Checklist before save

- [ ] No verbatim long user quotes in Decisions
- [ ] Language matches chat (RU/EN mixed OK if source mixed)
- [ ] `verify-memory.py` passes
- [ ] File still ≤ 100 lines (archive older blocks if needed)
