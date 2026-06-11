# Live distill — agent prompt (preCompact)

Use when `preCompact` hook fires and context is about to be compacted. Mechanical staging may already exist; this file captures what the **agent** still knows that regex extract missed.

## Inputs

- Mechanical staging: path from hook `staging_path` (if `distill.status == distilled`)
- Transcript: current chat JSONL (read tail if needed)
- Output file: path from hook `user_message` (pattern `merge-staging/<slug>-<date>-<chat8>-live.md`)

## Task

1. Read mechanical staging + last ~20 transcript turns (user + assistant).
2. Write **one** markdown file at the output path with:
   - `## Summary` — 1–3 bullets, chat language, ≤200 chars each, actionable facts/decisions not already in staging
   - `## Next step candidate` (optional) — single imperative bullet if clearer than mechanical pointer
3. No secrets, no raw tool dumps, no translation of user language.
4. Prefer concrete next actions (file paths, commands, version numbers) over "continue working".

## Quality bar

| Bad | Good |
|-----|------|
| "We discussed the project" | "v0.18: pointer_feedback uses token overlap; live file at merge-staging/…-live.md" |
| Duplicate of mechanical Summary | Delta: what compact will erase (in-flight reasoning, rejected options) |

## After save

- File must exist before compact completes; `sessionEnd` merge picks up `*-live.md` automatically.
- Do **not** edit `projects/*.md` here — merge runs on session end with `--apply`.
