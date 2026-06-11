# Session smoke — agent self-check

Use at **session start** when memory routing matters (new topic, architecture, CI/deploy, or user asks "load context").

**Goal:** prove layers were actually read — not guessed from training data.

---

## 1. Layer verification (after reading routed files)

Agent answers **internally** (do not dump files unless user asks). If any answer is wrong or empty — re-read that layer.

```markdown
- [ ] GLOBAL_CONTEXT — name active projects from Projects table
- [ ] conventions — state one cross-project rule (one sentence)
- [ ] distill Next step — state forward pointer from `chats/projects/<slug>.md`
- [ ] feedback/fails — name one `_superseded_` lesson (if proposing plans / CI / deploy)
```

**Pass:** answers match file content.  
**Fail:** vague, wrong, or "I don't have access" without reading.

---

## 2. Drift detection (monthly or when routing feels off)

User asks **before** agent reads files:

> "Without reading memory files — what do you know about my projects?"

| Response | Meaning |
|----------|---------|
| "I don't know without the files" / asks to read GLOBAL_CONTEXT | ✅ routing discipline OK |
| Lists projects from "memory" without reading | ❌ drift — agent ignoring hub |
| Silent or generic | ⚠️ re-run layer verification |

After drift check, proceed normally: read distill ## Next step → act.

---

## 3. Weekly integrity (human or cron)

```bash
python3 $FRAMEWORK_ROOT/scripts/verify-memory.py --memory-home "$MEMORY_HOME"
```

Fix all ❌ before relying on memory for big decisions.

---

## Routing reminder

| Situation | Read (usually enough) |
|-----------|------------------------|
| Continue known repo | `chats/projects/<slug>.md` → ## Next step |
| Propose CI / deploy / architecture | `feedback/fails.md` → `wins.md` → `preferences.md` |
| Cross-project rules | `conventions.md` |

Full protocol: [INSTRUCTIONS.md](../INSTRUCTIONS.md)
