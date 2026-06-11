# Pointer curation — agent prompt (session end)

Use when boundary distill wrote `## Next step` with `_No forward pointer._`, `[?]`, or sessionEnd hook says low-confidence pointer.

## Inputs

- Target: `$MEMORY_HOME/chats/projects/<slug>.md` (or path from hook `project_rel`)
- Staging: latest `chats/merge-staging/<slug>-*.md`
- Optional: chat link in `## Recent` — `[title](uuid)` for transcript tail

## Task

1. Read staging tail + `## Window summaries` / `## Assistant snippets` if present.
2. Read current `## Next step` — if placeholder, replace with **one** actionable bullet.
3. Prefer `memory-pointer.py set <project> "…"` or bullet prefix `[curated]` so auto-distill does not overwrite.
4. Write a single line the user would recognize as «what we do next» — imperative, ≤200 chars.
5. Preserve chat language (RU/EN); no secrets; no raw regex dump.
6. If truly unclear, keep `[?]` but add concrete drill: which file/command to open first.

## Quality bar

| Bad | Good |
|-----|------|
| "Continue working on the project" | "Run `bash tests/smoke.sh` after fixture import; fix first failing URL test" |
| Verbatim last user question | Paraphrased commitment: "Ship v0.10.1 baseline alerts, then push tag" |

## After save

- `verify-memory.py --memory-home $MEMORY_HOME`
- Do **not** overwrite `## Decisions` here — use semantic-merge for that.
