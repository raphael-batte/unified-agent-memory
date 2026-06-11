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
- Long chat: staging has `## Window summaries (map-reduce)` — reduce windows into Decisions bullets

## Steps

1. Read staging (Raw candidates, Window summaries, Assistant snippets, Rolling summary).
2. Update target `## Decisions` — paraphrase durable facts only; preserve language.
3. If pointer placeholder — one curated bullet under `## Next step` (pointer-curate-prompt).
4. `verify-memory.py`; never paste secrets.

## Templates

- `$FRAMEWORK_ROOT/templates/chats/semantic-merge-prompt.md`
- `$FRAMEWORK_ROOT/templates/chats/pointer-curate-prompt.md`
