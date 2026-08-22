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

### C-01 — Staleness horizon aimed at the wrong signal class   [M1, 2026-08-22]

**Proposed:** forward-fill values with a time limit, after which the signal becomes UNKNOWN
rather than carrying the last reading — applied to event-based signals (`process_state`,
`valve_state`).

**Problem with it:** those two signals are written *on change*, not polled. A declared state
does not decay. `STEADY_STATE` logged at 14:00 with no further event until 15:30 means steady
state for 90 minutes; expiring it to UNKNOWN after five invents a data gap that never existed
and would blank out most of every experiment.

**Principle:** the handling rule follows from **how the signal is acquired**, not from how long
ago the last sample arrived. For polled signals, silence is evidence of a fault — 1 Hz voltage
absent for 40 s is a real gap and filling it is a lie, so a staleness horizon belongs there. For
event-based signals, silence is evidence of *no change*, which is information rather than its
absence. Ask "what does the absence of a sample mean for this signal" before choosing a fill.

**Debrief phrasing:** "I treat gap-filling differently by acquisition mode. Polled signals get a
staleness horizon — beyond it I mark the value unknown rather than carry it, because for a
polled sensor silence means something broke. Event-based signals like `process_state` are
written on change, so silence means nothing changed; those get last-observation-carried-forward
to the next event with no expiry. That's most of the answer to why a pH signal and a plant state
signal can't share a rule."

### C-02 — Cleaning policy filed as reconnaissance   [M0, 2026-08-22]

**Proposed:** steady-state smoothing and interpolation rules listed among the checks to run
against the raw data during M0.

**Problem with it:** those are M3 cleaning decisions, not M0 reconnaissance. Reconnaissance
*characterises* defects; it does not fix them. Mixing the two means design decisions get made
while looking at exploratory output, before any verify criteria exist for them — which is the
specific failure the four-phase protocol is built to prevent. Secondary defect: gating smoothing
on `process_state == STEADY_STATE` takes a dependency on an event signal that has not itself
been validated at that point.

**Principle:** keep measurement separate from remediation, and do not let a later phase's
decision get made inside an earlier phase's tooling. Also: any rule that keys off another signal
inherits that signal's data-quality problems — validate the gate before trusting the gating.

**Debrief phrasing:** "Profiling and cleaning are separate steps for me. The profiling pass only
measures — rates, ranges, gaps, duplicates — and writes numbers to a file. Nothing is smoothed
or filled until there's a written policy per signal with a stated justification, because if I
decide the cleaning rule while staring at the exploratory output I've fitted the rule to what I
happened to see."

### C-03 (partial) — Check list covered only point-level defects   [M0, 2026-08-22]

**Proposed:** a data-quality check list covering time alignment, sampling rates, unit coherence,
range checks, missing values, outliers, and physical relationships (`P = U·I`, mass and energy
conservation).

**Problem with it:** the right half is genuinely strong — reaching for conservation checks and
the independently-logged `power` cross-check unprompted is the best thing in the list. What is
missing is two entire categories. **Structural/temporal defects**: duplicates, out-of-order
samples, and gaps as distinct from missing values (no row at all versus a row with no value —
different detection, different meaning). **Degenerate-but-plausible defects**: a stuck sensor
frozen at 82.4 V is in range, flagged `GOOD`, and passes every check on the list; range checks
structurally cannot catch it, only a variance-over-window test can. Also sensor noise and
outliers were treated as one thing; they are different classes needing different treatment.

**Principle:** point-level validity ("is this value plausible") is only one axis. A defect can
live in the *relationship between* samples (ordering, spacing, repetition) rather than in any
single one, and the most dangerous defects are the ones that look individually fine. This is the
same failure mode deliverable H asks about at the pipeline level.

**Debrief phrasing:** "I check three things, not one. Whether a value is plausible — range,
units, physical relationships. Whether the *series* is well formed — duplicates, out-of-order
timestamps, gaps versus nulls, actual sample interval versus nominal. And whether a signal is
degenerate rather than wrong — a stuck transmitter reads perfectly in range with a good quality
flag, so it needs a rolling variance test, and that's exactly the class of failure where every
individual point looks fine."

### C-04 (self-corrected before any code) — Transform-at-ingest instead of load-then-transform   [M1, 2026-08-22]

**Proposed:** encode the two categorical signals as integers during ingestion so a single
numeric `value` column could serve all 25 signals, with the code→label mapping in Postgres.

**Problem with it:** the database would then never hold what the sensor actually reported.
Deliverable A requires raw values preserved unchanged, and under that layout the only unmodified
copy is a gitignored CSV outside the system — so "raw is preserved" becomes an assertion about a
file rather than something demonstrable by query, which is what the M1 verify criterion asks
for. Reversed on his own initiative once that cost was on the table; see ADR-0006.

**Principle:** get raw in unchanged, transform downstream. An ingest that transforms destroys
the evidence you later need in order to *defend* the transformation. The corollary is a test for
any proposed ingest step: if this step is wrong, can I still prove what the source said?

**Debrief phrasing:** "Ingestion doesn't transform. It lands the data as reported, and every
transformation happens downstream where it's visible, reversible and testable. I did consider
encoding the categorical signals to integers to get a uniform numeric column, and rejected it —
that puts a transformation in the one place where I can't audit it afterwards, and it would have
meant the database never held what the sensor actually said."

### C-05 (partial) — "There is no good solution" for idempotent writes   [M2, 2026-08-22]

**Proposed:** after working through same-timestamp collisions, concluded that every option for
idempotent writes had a fatal flaw and none was satisfactory.

**Problem with it:** the pessimism was misplaced. Last-write-wins deduplication on
`(table, tag set, timestamp)` — the exact behaviour that causes the duplicate-collapse hazard —
*is* the idempotency mechanism. The same input converges to the same database state however many
times it is written, including after a run that died halfway. Nothing needed building; the
condition is only that every point be a pure function of its input row, which rules out
`ingested_at` fields, run ids in the tag set, and encounter-order-dependent conflict resolution.
The half that was right: recognising that silent last-write-wins is a hazard for raw
preservation. It is both things at once.

**Principle:** before building machinery around a storage behaviour you dislike, check whether
that behaviour already solves an adjacent problem. A property that is a hazard in one direction
is often a guarantee in another.

**Debrief phrasing:** "Idempotency here is free rather than built. The point key is a pure
function of the input row, and InfluxDB deduplicates on tag set plus timestamp last-write-wins,
so re-running the ingest converges to the same state — same checksum in, same database out. What
would break it is putting anything non-deterministic in a point: an ingest timestamp, a run id,
or a conflict-resolution rule that depends on the order rows happen to arrive. That last one is
why my rule for choosing between two conflicting readings is based on their content, not on
which one I saw first."
