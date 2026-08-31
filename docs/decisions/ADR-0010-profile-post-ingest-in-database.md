# ADR-0010 — Profile post-ingest in the database; measure pre-ingest only what ingestion destroys

Status: Accepted
Milestone: M0   Deliverable: C, D   Date: 2026-08-23

## Context

`MISTAKES.md` C-03 settled *which* checks the reconnaissance pass runs. It never settled **where
they run**, and the implicit answer — because M0 sits before M1 and M2 on the milestone board —
was that all of them read `data/raw/dac_raw_timeseries.csv` directly. The first M0 execution plan
did exactly that: one Python script loading all 520,005 rows into pandas and computing every check
in memory.

Two facts make that the wrong default:

- **It is the weakest available answer to U-06**, the memory-scaling challenge already registered
  as the most predictable review challenge. A profiling design whose first act is "load the entire
  dataset into RAM" concedes the point before the question is asked.
- **On a real system there is no CSV to load.** `task/TASK.md` frames the file as "what already
  landed in a local historian/buffer"; deliverable H makes that explicit. The realistic workflow is
  cheap aggregation in the database plus targeted samples pulled into Python — which is also the
  standing rule at `ROADMAP.md:78-79`.

One hard constraint pushes the other way, and it is not negotiable:

- **InfluxDB deduplicates points sharing table + tag set + timestamp, last-write-wins, silently.**
  This is ADR-0007's founding premise. Ingest therefore *destroys* one row of every colliding pair.
  U-07 (the win-policy), U-08 (the definition of "same"), and U-11 (whether categoricals collide)
  are all decisions about ingestion that can only be informed by evidence ingestion erases.

So reconnaissance is not uniformly relocatable. The question is where the line falls.

## Options considered

### Option 1 — Profile everything pre-ingest, in Python, against the CSV
Advantages: available immediately, no stack required; measures the source rather than a
possibly-buggy copy of it; a single pass answers everything at once.
Caveats: full in-memory load concedes U-06; the technique does not transfer to any dataset larger
than a laptop, which is the scenario the brief explicitly asks about ("months of high-resolution
electrochemical data"); it also duplicates work, since ADR-0007:90 already specifies a streaming
detection pass for exactly the duplicate portion.

### Option 2 — Profile everything post-ingest, in SQL against InfluxDB
Advantages: the technique scales and is what would actually be done in production; aggregations
run where the data is; targeted Python pulls stay small; it exercises the schema from ADR-0006 and
finds schema problems early.
Caveats: **impossible for the duplicate census**, because the write that makes the data queryable
is the write that deletes half the evidence. Also erases out-of-order arrival (storage is
time-sorted) and timestamp string formats (parsed to instants). Circular besides: the census exists
to decide ingest's duplicate policy, so it cannot run after ingest.

### Option 3 — Split by what ingestion destroys
Advantages: each measurement runs in the cheapest place that can still see it; the pre-ingest pass
shrinks to a small streaming job rather than a full load, so U-06 is answered rather than conceded;
the bulk of profiling gets the scalable SQL treatment; nothing is measured twice.
Caveats: two profiling surfaces instead of one, with a rule for which is which that has to be
stated and defended; the post-ingest profile describes stored data rather than source data.

## Decision

**Option 3. A minimal streaming pass before ingestion measures only what the write erases or what
ingest needs as input. Everything else is profiled after ingestion, with SQL aggregations against
InfluxDB plus targeted Python pulls for anything SQL cannot express.**

### Measured pre-ingest, and why each cannot move

| measurement | why it cannot move |
|---|---|
| Same-timestamp collisions: counts per experiment and signal; exact vs conflicting under *several* equality definitions; quality cross-tabulation of conflicting pairs; whether the two categorical signals collide; verbatim sample pairs | last-write-wins deletes one row of each pair (U-07, U-08, U-11) |
| Out-of-order arrivals — a row whose timestamp precedes its predecessor in file order | file order is erased by time-sorted storage; the property exists only in the source |
| Timestamp string-format variants, counted per source | parsed to instants at ingest (U-01); guessing wrong means every point in a source lands at the wrong instant, recoverable only by full re-ingest |
| Row counts per experiment and signal; SHA-256 verification | the left-hand side of ADR-0007:139's reconciliation identity — by definition it has to come from the source |
| Empty or non-parseable `value` cells; which signals carry non-numeric values | drives the numeric/state routing branch, which ADR-0006:117 requires be driven by a declared list — this confirms the declared list matches reality before anything is written |

### Measured post-ingest, in SQL

Value ranges against the documented ranges; actual sample intervals against nominal rates; gaps;
run-lengths of identical consecutive values; noise characterisation (distribution of consecutive
differences, separately from outliers); and the physical relationships — `power` against
`voltage × current`, `co2_out_ppm` against `co2_in_ppm`, `current` against `current_setpoint`,
`pressure_drop` against `air_flow`.

Nothing here is destroyed by ingestion, and all of it is either an aggregation SQL does well or a
bounded sample worth pulling into Python.

## Why

The line between the two sets is not "small things versus big things" or "structure versus values".
It is a single question, and it is the part that transfers: **what does the write erase?** Anything
whose evidence survives ingestion belongs in the database, where the technique scales and matches
what a real system would do. Anything the write destroys has to be measured upstream of it, and
that set turns out to be small and specific rather than most of the work.

The reason the first plan got this wrong is worth naming, because it is a general trap: **ordering
on a milestone board was mistaken for a data dependency.** M0 precedes M1 and M2 on the board, so
reconnaissance "obviously" ran against the CSV. But board order is a bookkeeping artifact and
carries no information about which measurements require which state.

Option 1's other cost is that it duplicates a design that already exists. ADR-0007:90 specifies
duplicate detection as a single pass over data sorted by series key then time, with duplicates
adjacent and memory O(1). That is already the right shape for the census — the census is that pass
with the writes turned off. Re-implementing it in pandas would have been a second, worse version of
a decision already made.

Option 2 is not merely inconvenient but self-defeating: the census exists to choose ingest's
duplicate policy, and running it after ingest means the policy was already applied. There is no
ordering of Option 2 that works.

## Consequences

- **The post-ingest profile describes stored data, not source data.** A value-level ingest bug
  would be faithfully profiled rather than caught. The reconciliation identity guards row counts
  only, not values. This is the real price of the decision and it should be stated rather than
  discovered.
- **Profiling now spans March–June 2026 in SQL, so it collides with U-05** — InfluxDB 3 Core's
  ~72h single-query span cap. U-05 was registered as an M5/M6 concern; it is now a dependency of
  profiling. Arguably an improvement, since it forces a known blocker into the open earlier, but
  the sequencing changed and the board has to reflect it.
- **The pre-ingest pass reports every candidate definition of "same" rather than applying one.**
  It exists to answer U-08, so presupposing an answer would defeat it. Byte-identical source text,
  parsed-float equality, and equality within tolerance are all reported, alongside verbatim sample
  pairs so the decision is made by looking at real rows.
- **U-06 is substantially answered rather than deferred.** The pre-ingest pass is O(1) streaming;
  the bulk of profiling is pushed into the database; Python sees only bounded samples. That is a
  defensible answer to "what happens when this does not fit in RAM" instead of an admission.
- **M1's retention and downsampling design is made against nominal sample rates** from
  `task/DATA_DICTIONARY.md`, because measured rates now arrive after ingestion. Acceptable — the
  nominal rates are documented and the arithmetic does not depend on the small deviations — but the
  design should be revisited once real rates exist.
- **Reconnaissance no longer precedes ingestion on the milestone board.** Where the post-ingest
  profiling sits was **U-16**, resolved 2026-08-29: a new milestone, M2.5, between M2 and M3 —
  see `ROADMAP.md` and `ASSUMPTIONS.md`.
- **How the pre-ingest census is packaged** — as M2's ingest detector run in a mode that writes
  nothing, or as a standalone script — was **U-15**, resolved 2026-08-29: the detector is
  reused, scoped to detection only — see the addendum on ADR-0007 and `ASSUMPTIONS.md`.
- **No verdict labels in any profile output**, pre- or post-ingest: counts, distributions and
  samples only. A profiler that emits `STUCK` has made an M3 cleaning decision inside M0 tooling,
  which is exactly C-02. The constraint is grep-checkable and should be checked.

## Assumptions relied on

A-01 (untimed scope), A-02 (Core is adequate — U-05 now bears on profiling as well as on M5/M6)

## Related

ADR-0006 (data model), ADR-0007 (duplicate resolution — supplies the streaming detection design
this reuses). `MISTAKES.md` C-02 (measurement is not remediation), C-03 (the check list itself),
E-01 (the error this ADR corrects). Open unknowns created here: U-15, U-16. Bears on U-05, U-06.

## Defense

I profile the data in the database, not by loading the CSV into pandas — cheap aggregations in SQL
where the data already is, and targeted samples pulled into Python only where SQL can't express
what I need. That's the same thing I'd do against a real historian, where there's no CSV to load
and the dataset doesn't fit in memory anyway. The exception is a small set of things that
ingestion destroys, and those have to be measured upstream of the write: duplicate collisions,
because InfluxDB deduplicates on tag set plus timestamp last-write-wins and silently deletes one
row of every conflicting pair; out-of-order arrivals, because storage is time-sorted so file order
is gone; and the raw timestamp string formats, because those get parsed to instants and a wrong
timezone guess means re-ingesting everything. So the rule I use to decide where a check runs is
just: what does the write erase? That set is small and specific, and it runs as an O(1) streaming
pass rather than a full load. The honest cost is that the post-ingest profile describes stored data
rather than the source — if ingestion had a value-level bug, I'd be profiling the bug — so the
reconciliation count between CSV and database is what backstops that, and it only covers row
counts, not values.
