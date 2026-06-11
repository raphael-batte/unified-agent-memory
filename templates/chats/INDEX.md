# Chat Memory — Index

Distilled conversation history. Skill: **chat-memory**

## When to read

**On demand** — not every session. Use when you need past decisions or «what did we discuss».

| Situation | Read |
|-----------|------|
| Current next step | `projects/<slug>.md` → **## Next step** |
| Past decisions / why | `projects/<slug>.md` → **## Decisions** |

## Projects

| File | Scope |
|------|-------|
| [example.md](projects/example.md) | Template — copy/rename for your project |

## Archives

| NNN | Date | File | Note |
|-----|------|------|------|
| — | — | _(none yet)_ | Rotate when project file > ~100 lines |

## Transcripts

- **Manifest:** [manifest.json](manifest.json) — `date` vs `distilled_at`
- **Pending:** `python3 $MEMORY_HOME/scripts/list-chats.py --pending`
- **Source:** `~/.cursor/projects/*/agent-transcripts/<uuid>/<uuid>.jsonl`
