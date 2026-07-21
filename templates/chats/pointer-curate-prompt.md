# Pointer curation — agent prompt (session end)

Use when a session had a clear outcome but **## Open threads** was not updated.

## Inputs

- Target: `$MEMORY_HOME/chats/projects/<slug>.md` (or path from hook `project_rel`)
- Staging: latest `chats/merge-staging/<slug>-*.md`
- Rolling view: `memory-pointer.py threads --days 30`
- Optional: chat link in `## Recent` — `[title](uuid)` for transcript tail

## Task

1. Read staging tail + topic segments / outcome from the session.
2. For **each active direction touched** (≤30d): upsert one Open threads bullet.
3. Prefer CLI:
   `memory-pointer.py add-thread <project> <label> "where we stopped · outcome"`
4. Label = auto (segment preview / path / workspace slug), not a hardcoded project list.
5. Cap 5–7 bullets per project file; close finished directions (remove bullet).
6. Preserve chat language (RU/EN); no secrets.

## Quality bar

| Bad | Good |
|-----|------|
| "Continue working on the project" | `**[widget-ui]** Footer deploy OK on staging — smoke mobile accordion` |
| Verbatim last user question | Paraphrased state: `**[agent-memory]** PR #1 merged; add-thread ops on hub` |

## Do not use

- **`memory-pointer.py set`** — removed; `## Next step` no longer exists.
- Auto-distill does not write Open threads — curation is agent/CLI only.

## After save

- `verify-memory.py --memory-home $MEMORY_HOME`
- Decisions → semantic-merge, not here.
