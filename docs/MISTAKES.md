# Mistake log

Append-only, newest last. Written **at the moment the mistake surfaces**, not reconstructed
at session end — the reasoning behind a mistake is only recoverable while it's fresh.

Two sections, two different purposes:

- **Assistant errors** — so Claude stops repeating them. Read at session start.
- **Corrected design calls** — so Sebastian doesn't make the same call in the real interview.
  This is study material, not a scoreboard.

Entry ids are sequential per section (`E-01`, `C-01`).

---

## Assistant errors

Template:

```markdown
### E-nn — <one-line title>   [M#, YYYY-MM-DD]
**Claimed / did:** …
**Actually true:** …
**Why I got it wrong:** the reasoning error, not just the wrong output.
**Rule that prevents a repeat:** …
```

Counts as an assistant error: a wrong fact, broken or misleading code, a verification claim
made without running the check — and any violation of the practice-mode contract in
`CLAUDE.md`, e.g. volunteering a design decision before Sebastian has proposed one, or
softening a wrong call into a leading question instead of naming the problem.

*(no entries yet)*

---

## Corrected design calls

Template:

```markdown
### C-nn — <one-line title>   [M#, YYYY-MM-DD]
**Proposed:** …
**Problem with it:** the actual defect, stated first and plainly.
**Principle:** the general rule this is an instance of — the part that transfers.
**Debrief phrasing:** how to say the right answer out loud when challenged.
```

Partially-right calls belong here too, marked as such — knowing which half was right is the
useful part. Calls that were right and needed no correction don't go here; they go in the ADR
as the accepted decision.

*(no entries yet)*
