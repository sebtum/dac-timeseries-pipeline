# ADR-0000 — Keep architecture decision records for this exercise

Status: Accepted
Milestone: —   Deliverable: —   Date: 2026-08-11

## Context

This repo is interview practice, not production code. The previous attempt at the exercise
was reverted (`2266be2`); it produced working artifacts but left almost nothing explaining
*why* anything was built the way it was. The brief says it directly: "There's no single
correct answer, but you should be able to justify each choice you make and say what you'd do
differently with more time." The debrief scores the reasoning, not the artifact.

So the reasoning has to be captured somewhere durable, at the moment it happens. The question
is where.

## Options considered

### Option 1 — Explain decisions in code comments and commit messages
Advantages: zero extra ceremony; lives next to the thing it explains; nothing to keep in
sync.
Caveats: captures *what* the code does, not the options that were rejected; comments
disappear when the code is refactored; a commit message is not somewhere you re-read the
night before an interview; nothing to review as a set.

### Option 2 — One running design document
Advantages: single file, easy to read top to bottom, tells a narrative.
Caveats: gets edited in place, so reversals overwrite the earlier position — and the reversals
are the most interesting material; no natural unit to point at when an interviewer asks about
one specific choice; grows into something nobody re-reads.

### Option 3 — One ADR per decision, immutable, superseded rather than edited
Advantages: forces the alternatives to be written down, which is exactly the muscle being
practiced; each decision is independently addressable; reversals are visible as history
rather than erased; the per-ADR "debrief answer" field turns the record into rehearsal
material.
Caveats: real overhead per decision; risks bureaucracy if applied to trivia; needs a rule for
what deserves one.

## Decision

Use one ADR per decision (Option 3), in `docs/decisions/`, with a mandatory "Debrief answer"
section — limited to decisions whose reversal would mean reworking code or re-running the
pipeline.

## Why

The specific failure mode of the last attempt was artifacts without justification, which is
precisely what the debrief penalises. Option 1 doesn't fix it and Option 2 fixes it only until
the first change of mind. The ceremony cost is affordable here because the exercise is
untimed (A-01) and because the *writing* is the practice — being made to name two real options
and say why one lost is the part that transfers to answering out loud.

## Consequences

- Every design conversation now has an artifact, which makes the debrief a matter of reading
  back rather than remembering.
- Decisions get slower. That's the intended trade at practice speed; it would not be at
  interview speed, and that difference is itself worth being able to state.
- Requires discipline about the threshold. If ADR-0007 is about a variable name, the
  threshold has failed.
- Rejected options are on the record, so "what would you do differently with more time" has a
  written answer instead of an improvised one.

## Assumptions relied on

A-01 (untimed scope — the overhead would not be affordable under a 60-minute clock)

## Debrief answer

I kept a decision record because on this kind of data almost nothing has one correct answer —
the value is in which trade you took and what you gave up. Each record names the options, the
property of *this* dataset that decided it, and what the choice forecloses. That also gives me
an honest answer to "what would you do differently": the alternatives are written down rather
than reconstructed after the fact. Under real time pressure I'd cut this to a decision log of
one line per call, and write it up afterwards.
