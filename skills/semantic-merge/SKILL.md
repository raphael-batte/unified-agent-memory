---
name: semantic-merge
description: >
  Curates ## Decisions and ## Next step from distill merge-staging files.
  Use after boundary distill or sync-memory when staging exists, on session end,
  or when user says "semantic merge", "curate decisions", or "fix next step".
  Pair with templates/chats/semantic-merge-prompt.md and pointer-curate-prompt.md.
---

# Semantic merge

Hub staging → curated `chats/projects/<slug>.md`.

## When

- `merge-staging/<slug>-*.md` exists after hook/sync distill
- `## Next step` is `_No forward pointer._` or `[?]` — also read `pointer-curate-prompt.md`
- Long chat: prefer `## Topic segments` + `## Decision candidates` from extract; fallback `## Window summaries (map-reduce)`

## Steps

1. Read staging — **Topic segments**, **Decision candidates**, Raw candidates, Rolling summary; map-reduce windows only if no segments.
2. Update target `## Decisions` — write `[curated]` bullets; paraphrase durable facts only; preserve language. Leave `[extracted]` to hooks/`--apply`.
3. If pointer placeholder — one curated bullet under `## Next step` (pointer-curate-prompt).
4. `verify-memory.py`; never paste secrets.

## Templates

- `$FRAMEWORK_ROOT/templates/chats/semantic-merge-prompt.md`
- `$FRAMEWORK_ROOT/templates/chats/pointer-curate-prompt.md`
