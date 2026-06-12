# Feedback Memory — Index

What worked (+) and what failed (−). Skill: **agent-memory** (`feedback/` routing)  
**Accumulates** — unlike chat distill (rotates). Read **on demand** when proposing plans.

## When to read

| Situation | Read |
|-----------|------|
| Proposing architecture / CI / deploy / workflow | [fails.md](fails.md) + [wins.md](wins.md) + [../context/preferences.md](../context/preferences.md) |
| User rejected an idea before | fails.md — skip lines with `_superseded_` (rule is in conventions) |
| Normal coding task | skip — use distill ## Next step |

## Files

| File | Content |
|------|---------|
| [wins.md](wins.md) | `+` what worked in practice |
| [fails.md](fails.md) | `−` rejected / failed approaches |
| [../context/preferences.md](../context/preferences.md) | how user thinks (not technical rules) |

## vs other layers

| Layer | Question |
|-------|----------|
| conventions.md | what is the rule **now** |
| preferences.md | how to communicate / decide |
| feedback/ | what **worked or failed** empirically |
| chats/projects/ | what we **discussed** (neutral facts) |

## Format

```markdown
## YYYY-MM Topic
+  short win
-  short fail
  _superseded → conventions.md § <heading> (optional bullet keyword)_
```

## Rotation

When wins.md or fails.md > ~80 lines → `archive/NNN-YYYY-MM-feedback-<slug>.md`

| NNN | Date | File | Note |
|-----|------|------|------|
| — | — | _(none yet)_ | |
