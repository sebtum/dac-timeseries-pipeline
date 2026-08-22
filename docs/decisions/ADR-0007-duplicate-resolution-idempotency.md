# ADR-0007 — Same-timestamp duplicate resolution and ingest idempotency

Status: Accepted
Milestone: M2   Deliverable: B, C   Date: 2026-08-22

## Context

ADR-0006 settled that ingest stores raw values unchanged. That is necessary for "raw values must
be preserved unchanged" but **not sufficient**, because of how InfluxDB stores points:

- Points sharing **table + tag set + timestamp** are deduplicated **last-write-wins**. No error,
  no warning, no rejected line. Two rows claiming the same instant for the same series collapse
  into one and the loss is invisible.
- Deliverable D names duplicates explicitly as something the data contains, so this is not a
  hypothetical.

The consequence is that an "ingest as-is" script can lose data while looking completely
faithful — the worst failure mode available, because nothing in the output signals it happened.
The M2 verify criterion ("row counts reconcile CSV → Influx per experiment and signal") is the
test that would catch it, and this ADR exists so that it passes by construction rather than by
investigation afterwards.

A second question rides along, because the same storage behaviour drives it: **re-run safety.**
M2 requires that re-running ingestion is safe.

Two classes of collision, which need separating before anything else can be decided:

- **Exact duplicate** — same tags, same timestamp, **same value**. The collapse loses nothing;
  the second row was redundant.
- **Conflicting duplicate** — same tags, same timestamp, **different value**. Real information
  loss, and a data-quality event in its own right: contradictory readings for one instant mean a
  logger replayed a buffer, two sources wrote the same tag, or a clock stepped backwards.

## Options considered

### Option 1 — Disambiguate in the series key (an `occurrence` tag)
Colliding rows get `occurrence=1`, normal rows `occurrence=0`, so both survive in InfluxDB.
Advantages: both readings stay queryable *inside the data*, where anyone who queries will find
them; no separate store to consult; series count barely moves (150 → 150 + a few).
Caveats: **the tag rides on all 520,005 points**, so any query that does not filter it returns
two rows where one is expected — every unfiltered `mean()`, energy integration or Grafana panel
silently double-counts a conflicting pair. That moves the silent-error risk from ingest, which
runs once under supervision, to query time, which runs constantly and is touched by people who
do not know the tag exists. It also **does not avoid the detection work**: stamping
`occurrence=1` requires already knowing the row collides, which is the same pass Option 3 runs.
The only detection-free variant — a global row counter — gives every point a unique tag and
turns 150 series into 520,005. Finally, safety here depends on duplicates staying *rare*; a
logger systematically replaying its buffer (exactly the deliverable H scenario) would grow
`occurrence` and series count with it.

### Option 2 — Perturb the timestamp
Nudge colliding points by 1 ns so both persist.
Advantages: both readings survive; no schema change; no detection needed beyond collision.
Caveats: fabricates time. Every downstream query that trusts timestamps is reading a small lie,
and the exercise is explicitly about not silently altering data.

### Option 3 — Detect at ingest, record conflicts in their own table
Advantages: distorts neither the schema nor the timeline — no synthetic tag on the hot path, no
invented nanoseconds; converts a silent storage behaviour into an explicit, countable,
queryable data-quality event, which is precisely deliverable C's framing; normal queries need
no filter and cannot double-count.
Caveats: requires a definition of "same" for float comparison; requires a stated win-policy for
which reading is kept; covers **intra-run** duplicates only — a duplicate spanning two batches,
a parallelised run, or a re-run is invisible to in-process detection, so cross-run collisions
are a separate concern; the conflict record must be deliberately made queryable or the evidence
ends up in a log nobody opens.

### Option 4 — Accept the collapse and explain the delta
Advantages: simplest possible ingest; nothing to build.
Caveats: the explanation has to be produced after the fact by re-reading the CSV to characterise
what collapsed — the analysis happens anyway, just later and under worse conditions, and until
it is done the reconciliation is an unexplained discrepancy.

## Decision

**Detect same-timestamp collisions during ingest and record conflicting ones in a
`readings_conflicts` table. Achieve idempotency through a deterministic natural key rather than
added machinery.**

```
readings_conflicts
  tags:   experiment_id, source, signal
  fields: value_kept, quality_kept, value_discarded, quality_discarded,
          source_row_kept, source_row_discarded, reason, resolution
```

Exact duplicates are counted, not recorded individually. Conflicting duplicates write one point
to the readings table per the win-policy and one row here.

Detection runs as a **single pass over data sorted by series key then time**, so duplicates are
adjacent and memory stays O(1) rather than requiring a set of every key seen.

## Why

Options 1 and 3 both require the identical detection pass, so the real choice between them is
*where the result is written* — into the series key, or into a separate table. Writing it into
the series key taxes every query forever to preserve a handful of readings; writing it into a
table gets the same "evidence lives in the database, queryable alongside the data" property
with no cost on the hot path. Given that framing, Option 1's only advantage evaporates.

Option 2 is excluded on principle: an exercise whose central instruction is *don't silently fix
data* cannot answer a data problem by fabricating timestamps.

Option 4 is not wrong so much as deferred work. The characterisation of what collapsed has to
happen either way; doing it at ingest, where both rows are in hand, is strictly cheaper than
reconstructing it later from a count mismatch.

On idempotency: the storage behaviour that causes this whole problem is also its solution.
Last-write-wins deduplication on `(table, tag set, timestamp)` means the same input converges to
the same database state however many times it is written — including after a run that died
halfway. Re-run safety is therefore a **property of the design, not a feature to build**, and it
holds on exactly one condition: every point must be a pure function of its input row.

Recording both readings in full, rather than just the discarded value, is deliberate. A conflict
where the discarded row was flagged `BAD` and the kept row `GOOD` is a completely different
story from two `GOOD` rows disagreeing — the first is a logger doing its job, the second is a
real fault — and that distinction is only recoverable later if both were stored.

## Consequences

- **Idempotency constrains what may enter a point.** No `ingested_at` tag or field, no batch id
  or run id in the tag set, no ordering-dependent behaviour. Any of those and re-running writes
  new, different points instead of converging.
- **The win-policy must be content-based, not encounter-based.** "Last row seen wins" is
  deterministic only because a file is read top to bottom; parallelise by experiment or move to
  streaming and it becomes a race. The policy itself is left open (U-07) but this constraint on
  it is settled here.
- **`readings_conflicts` is keyed the same way** — `(experiment_id, source, signal)` + timestamp
  — so a re-run rewrites the identical conflict record rather than accumulating copies. The
  conflicts table is idempotent for the same reason the readings tables are.
- **Input identity is the committed SHA-256.** Same checksum in, same database out. That is the
  sentence that closes the re-run question.
- **Cross-run duplicates are out of scope for in-process detection** and remain a distinct
  concern; LWW convergence covers correctness, but a duplicate that spans two separately-invoked
  ingests will not appear in `readings_conflicts`.
- **A reconciliation identity now exists**, which makes "nothing silently dropped" provable
  arithmetic instead of an assertion, satisfying the M2 verify criterion by construction:

      CSV rows = readings rows + exact-duplicate collapses + conflict discards

  Every term is countable and two of the three are queryable from InfluxDB.
- **Sorting before ingest bounds memory**, which partially answers the memory-scaling challenge
  in U-06: the naive approach (remember every key seen) is O(rows); sort-then-compare-adjacent
  is O(1) in the streaming step. Streaming systems reach the same place with a bounded lateness
  window instead of a full sort.
- The `value_kept` / `value_discarded` columns are float, so `readings_conflicts` inherits the
  same categorical problem ADR-0006 solved — conflicts on `valve_state` or `process_state` need
  either a second conflicts table or string columns. **Left open**, to be settled when the
  duplicate census (M0) shows whether categorical signals collide at all.

## Assumptions relied on

A-01, A-02

## Related

ADR-0006 (time-series data model). Open unknowns created here: U-07 (win-policy), U-08
(definition of "same" for float comparison).

## Debrief answer

Ingesting raw doesn't by itself preserve raw, because InfluxDB deduplicates points sharing tags
and timestamp last-write-wins, silently — so duplicate rows would collapse and I'd have lost
data while the load looked clean. I split duplicates into exact ones, where the collapse loses
nothing and I just count them, and conflicting ones, where two different values claim the same
instant — that's a data-quality event, not a nuisance, so it goes into its own table with both
readings and both quality flags recorded. I chose that over adding a disambiguating tag because
the tag would sit on every one of the 520,000 points and any query that forgot to filter it
would double-count, which moves the silent-error risk from ingest to query time. Idempotency I
get for free from the same deduplication behaviour: the point key is a pure function of the
input row, so re-running converges to the same state — which is why nothing in a point is
allowed to be an ingest timestamp or a run id. The end result is that CSV rows equals stored
rows plus collapses plus discards, so "nothing was silently dropped" is arithmetic I can show
rather than a claim.
