# Retrospectives

One file per working session: `<n>-YYYY-MM-DD.md`, e.g. `01-2026-08-11.md`.

Written when Sebastian says the session is wrapping up — before context runs out, not after.
The most important section is the last one: the next session starts by reading it.

## Template

```markdown
# Session <n> — YYYY-MM-DD

**Board at close:** M# <name>, phase <Discuss|Plan|Execute|Verify|Done>

## Shipped
What actually exists now that didn't before. Files, running services, verified results.

## What went well
Specific. "The reconnaissance found X before we designed around it" — not "good progress".

## What went wrong
Both sides: assistant errors (E-nn) and design calls that needed correcting (C-nn), each
linked to `../MISTAKES.md`. Also process failures — a phase skipped, a verify criterion
written after the fact, a decision made in code instead of in Discuss.

## Decisions open
Things surfaced but not settled, with what's blocking each.

## Unknowns moved
Which U-nn resolved, which got promoted to assumptions.

## First move next session
One concrete action. Not "continue M3".
```

## Rule

The retrospective reports what happened, including the parts that didn't work. A retro with
no "what went wrong" entries in a session that had corrections in `MISTAKES.md` is wrong and
should be rewritten.
