# Chat Memory — Index

Distilled conversation history. Skill: **agent-memory** (routing) · **semantic-merge** (curate Decisions)

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

| File | Note |
|------|------|
| `archive/<slug>-decisions.md` | Evicted `[extracted]` decisions (searchable, 0.7× weight) |
| _(manual)_ | Optional rotation when `projects/<slug>.md` > ~100 lines — agent semantic-merge |

See [archive/README.md](archive/README.md).

## Transcripts

- **Manifest:** [manifest.json](manifest.json) — `date` vs `distilled_at`
- **Pending:** `python3 $MEMORY_HOME/scripts/list-chats.py --pending`
- **Source:** `~/.cursor/projects/*/agent-transcripts/<uuid>/<uuid>.jsonl`
