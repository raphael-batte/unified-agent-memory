# Evicted decisions archive

`archive/<slug>-decisions.md` — FIFO-evicted `[extracted]` bullets from `chats/projects/<slug>.md` when the per-file cap is exceeded (default 30 extracted).

- **Not** a full snapshot of `projects/<slug>.md` — curated, `[bootstrap]`, and `[auto]` bullets stay in the active project file.
- **Format:** `# Archived …` + `## Decisions` + bullet list (indexed by `memory-search.py` at 0.7× score vs active layer).
- **Dedup:** duplicate evictions are not re-appended; `compact_archive_decisions()` can rewrite the file.

For rotating an oversized **project** file (> ~100 lines), use semantic-merge and manual archive of old blocks — see [../INDEX.md](../INDEX.md).
