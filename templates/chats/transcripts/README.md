# Imported transcripts (generic jsonl)

Drop `{uuid}.jsonl` here when the chat is **not** in Cursor `agent-transcripts/`.

**Format:** one JSON object per line — `{"role":"user","content":"..."}`  
Parsed by `transcript_generic` adapter (see `lib/transcript.py`).

`distill-extract.py <uuid> --memory-home $MEMORY_HOME` finds files at:

- `transcripts/<uuid>.jsonl`
- `transcripts/<uuid>/<uuid>.jsonl`

Do not commit secrets. Run `verify-memory.py` after distill.
