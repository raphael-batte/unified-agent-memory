---
name: semantic-merge
description: >
  Curates ## Decisions and ## Open threads from distill merge-staging files.
  Use after boundary distill or sync-memory when staging exists, on session end,
  or when user says "semantic merge", "curate decisions", or "update open threads".
  Pair with templates/chats/semantic-merge-prompt.md and pointer-curate-prompt.md.
---

# Semantic merge

Hub staging → curated `chats/projects/<slug>.md`.

## When

- `merge-staging/<slug>-*.md` exists after hook/sync distill
- Session had outcome but Open threads not updated — read `pointer-curate-prompt.md`
- Long chat: prefer `## Topic segments` + `## Decision candidates` from extract; fallback `## Window summaries (map-reduce)`

## Steps

1. Read staging — **Topic segments**, **Decision candidates**, Raw candidates, Rolling summary; map-reduce windows only if no segments.
2. Update target `## Decisions` — write `[curated]` bullets; paraphrase durable facts only; preserve language. Leave `[extracted]` to hooks/`--apply`.
3. Update `## Open threads` (forward pointer) — one `**[label]**` bullet per active direction; upsert by label, cap 5–7. Prefer `memory-pointer.py add-thread <project> <dir> "…"`.
4. **`## Next step` was removed** — the forward pointer is `## Open threads`.
5. `verify-memory.py`; never paste secrets.

## Session end

Before ending a session with an outcome: refresh `## Open threads` for each direction you touched, add the `## Recent` outcome line, then run this semantic merge over staging.

## Templates

- `$FRAMEWORK_ROOT/templates/chats/semantic-merge-prompt.md`
- `$FRAMEWORK_ROOT/templates/chats/pointer-curate-prompt.md`
