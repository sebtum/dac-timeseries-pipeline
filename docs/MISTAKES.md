# Mistake log

Append-only, newest last. Written **at the moment the mistake surfaces**, not reconstructed
at session end — the reasoning behind a mistake is only recoverable while it's fresh.

Two sections, two different purposes:

- **Assistant errors** — so Claude stops repeating them. Read at session start.
- **Corrected design calls** — so the same call doesn't get repeated later. This is study
  material, not a scoreboard.

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
made without running the check — and any violation of the working session contract in
`CLAUDE.md`, e.g. volunteering a design decision before Sebastian has proposed one, or
softening a wrong call into a leading question instead of naming the problem.

### E-01 — Planned reconnaissance as a full in-memory pandas pass over the raw CSV   [M0, 2026-08-23]

**Claimed / did:** proposed the M0 profiling pass as a Python script that loads all 520,005 rows
into pandas and computes every check from `MISTAKES.md` C-03 in memory, against
`data/raw/dac_raw_timeseries.csv`.

**Actually true:** three things, each independently sufficient to reject it.
1. Most of those checks are not destroyed by ingestion, so they can run as SQL aggregations
   against InfluxDB — where the technique actually scales and where a real system would run them.
   `task/TASK.md` frames the CSV as what already landed in a historian; in production there is no
   CSV to load.
2. A full in-memory load is the weakest possible answer to U-06, which is registered as the most
   predictable review challenge, and it contradicts the standing rule at `ROADMAP.md:78-79`.
3. The duplicate-census portion was **already designed** — ADR-0007:90 specifies a single
   streaming pass sorted by series key then time, duplicates adjacent, memory O(1). Re-doing it in
   pandas would have been a second, worse implementation of a settled decision.

**Why I got it wrong:** I treated **position on the milestone board as a data dependency.** M0 sits
before M1 and M2, so I assumed all M0 work must read the source file. Board order is bookkeeping;
it says nothing about which measurements require which system state. I never asked the question
that actually decides it.

**Rule that prevents a repeat:** before planning any pre-ingest analysis, ask *what does the write
destroy?* Only that set is forced upstream of ingestion; everything else belongs in the database.
And before writing a component, check whether an existing ADR already specifies its shape.

### E-02 — Proposed a per-check profiling package, and spent a clarifying question on it   [M0, 2026-08-23]

**Claimed / did:** offered a `profiling/` package with one module per check family as the
recommended structure, justified by "M3 reuses the detectors", and put it to Sebastian as a
multiple-choice question alongside an output-format question.

**Actually true:** building reusable detector infrastructure before M3's per-signal policy exists
is designing ahead of the decision — the reuse was speculative, and the structure invited exactly
the C-02 failure, since a module holding run-length logic is one commit away from holding a
smoothing rule. `docs/decisions/README.md` also names file layout explicitly as trivia, below the
threshold that deserves a decision at all.

**Why I got it wrong:** I mistook "this might be reused later" for a present requirement, and then
escalated a layout preference into a question that consumed decision bandwidth reserved for design
calls.

**Rule that prevents a repeat:** pick a default for layout, say plainly that it is trivia and
redirectable, and move on. Reserve questions for decisions whose answer changes the work.

### E-03 — Collision detection module does a full in-memory sort, contradicting its own O(1) framing   [M0, 2026-08-29]

**Claimed / did:** wrote `pipeline/collisions.py` and `scripts/pre_ingest_census.py` as "the
sort-then-compare-adjacent pass ADR-0007:90 specifies," implying it delivers the memory-bounded
property that ADR-0007 and ADR-0003 (U-06) both lean on.

**Actually true:** the streaming pass genuinely is O(1) — one row at a time, fixed-size counters
— but the collision step appends every parsed row into a Python list and calls `sorted()` on the
whole thing before comparing adjacent rows. That's an O(n) in-memory sort. ADR-0007's "O(1) in
the streaming step" claim covers only the *comparison* pass after sorting; it says nothing about
the sort itself being memory-bounded, and I built the sort as a plain in-memory one anyway. For
the actual 50MB/520,005-row file this is harmless, but if this module is what M2 reuses for real
ingestion — which the ADR-0007 addendum says it is — it doesn't yet deliver the bounded-memory
property U-06 needs defended, and ADR-0003 already flags that defense as incomplete.

**Why I got it wrong:** I pattern-matched "streaming pass, one row at a time" from the rest of
the script and assumed it covered the sort step too, without checking each stage's actual memory
profile separately. A pipeline can be streaming in four stages and batch in the fifth, and only
checking the overall shape misses that.

**Rule that prevents a repeat:** when a design record makes a Big-O claim, verify it stage by
stage before reusing the claim to describe new code — "streaming" is not one property of a
script, it's a property that has to hold independently at every step that touches all the data.

### E-04 — Claimed standard deviation cannot be re-aggregated across rollup buckets   [M1, 2026-08-30]

**Claimed / did:** argued that storing `avg`, `std` and `median` per rollup bucket was insufficient
because "you cannot compute an hourly median from 60 medians, and you can't get hourly std from 60
stds", and recommended storing `count, sum, sum_of_squares, min, max` instead so the statistics
would be mergeable.

**Actually true:** the median half is right; the std half is wrong. With `count` and `mean` retained
alongside — which the proposed schema already had — the pooling is exact:
`Σx = n·m` and `Σx² = n·(s² + m²)`, so the combined variance is
`Σ[nᵢ(sᵢ² + mᵢ²)]/N − M²`. `(count, mean, std)` and `(count, sum, sumsq)` carry identical
information. Sebastian pushed back on this directly and was correct. Sum and sum-of-squares are
still worth storing here, but for two much narrower reasons than the one I gave: with *sample* std
(denominator n−1) a bucket of one sample has undefined std and is genuinely unrecoverable — which
happens for all four ambient signals at 1-minute buckets — and pooling raw sums is associative
addition with no convention to get wrong.

**Why I got it wrong:** I evaluated the mergeability of `std` **in isolation**, as a property of
that one statistic, when mergeability is a property of the *stored tuple*. Then I generalised from
a true statement about medians — order statistics genuinely are not decomposable — to "higher
moments in general", which does not follow: variance is a function of the first two raw moments and
those are additive. Reasoning by analogy from one aggregate to another skipped the two lines of
algebra that would have settled it.

**Rule that prevents a repeat:** before calling any aggregate non-mergeable, write down the whole
set of columns being stored and check whether the sufficient statistics are recoverable from it.
"Is X mergeable?" is not a well-formed question — "is X recoverable from the tuple I am keeping?"
is. And when a claim reduces to two lines of algebra, do the algebra instead of arguing from a
neighbouring case.

---

## Corrected design calls

Template:

```markdown
### C-nn — <one-line title>   [M#, YYYY-MM-DD]
**Proposed:** …
**Problem with it:** the actual defect, stated first and plainly.
**Principle:** the general rule this is an instance of — the part that transfers.
**Defense:** how to say the right answer out loud when challenged.
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

**Defense:** "I treat gap-filling differently by acquisition mode. Polled signals get a
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

**Defense:** "Profiling and cleaning are separate steps for me. The profiling pass only
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

**Defense:** "I check three things, not one. Whether a value is plausible — range,
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

**Defense:** "Ingestion doesn't transform. It lands the data as reported, and every
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

**Defense:** "Idempotency here is free rather than built. The point key is a pure
function of the input row, and InfluxDB deduplicates on tag set plus timestamp last-write-wins,
so re-running the ingest converges to the same state — same checksum in, same database out. What
would break it is putting anything non-deterministic in a point: an ingest timestamp, a run id,
or a conflict-resolution rule that depends on the order rows happen to arrive. That last one is
why my rule for choosing between two conflicting readings is based on their content, not on
which one I saw first."

### C-06 — Retention window specified without checking it against the data's own time span   [M1, 2026-08-30]

**Proposed:** 90 days raw retention, 1 year of 1-minute rollups, then cold storage — as the
starting-point policy, explicitly pending a conversation with the lab manager.

**Problem with it:** the tier *shape* is right and the stakeholder framing is right, but 90 days
applied to this database deletes five of the six experiments. The experiments run 2026-03-02 to
2026-06-15; the wall clock is 2026-08-30; 90 days back is 2026-06-01, so only `EXP_005` survives.
Deliverables F and G would have nothing to compare. The failure is silent rather than loud:
InfluxDB 3 Core enforces retention **at query time**, filtering expired points out of results
while they still sit in storage pending async deletion — so the ingest succeeds and reports
success, and the data is merely invisible. That specifically breaks M2's "row counts reconcile
CSV → Influx" criterion in a misleading direction: counting writes passes, querying counts back
fails, and the debugging points at the ingest code rather than at retention. Core also fixes a
retention period at `create database` and forbids changing it, so the recovery is a new database
plus a full re-ingest. Secondary defect: the proposal never addressed what retention does to
deliverable A's "raw values preserved unchanged", which ADR-0006 deliberately staked on being
demonstrable *by query* — expiring the raw database silently reverts that guarantee to a claim
about a gitignored CSV, the exact position ADR-0006 was written to escape (see C-04).

**Principle:** a retention period is a statement about data age *relative to now*, so it has to
be validated against the timestamp span of the data that will actually be written under it — not
against the imagined steady-state system. Historical backfill and retention are natural enemies,
and the conflict is silent in both directions. The corollary: a policy that is correct as a
*plant* policy can be wrong as *this database's* configuration, and those two claims must be
stated separately rather than conflated. Always check whether a retention decision deletes a
guarantee some other decision depends on.

**Defense:** "My plant policy and my configuration for this dataset are deliberately
different numbers, and I'd rather say that than pretend one number serves both. As a plant policy
I'd start at 90 days of raw pending a conversation with the process owners about how far back
anyone actually re-opens a run. For this database it would be wrong: the experiments are March to
June and I'm loading them in August, so a 90-day window silently hides five of six — and it *is*
silent, because Core enforces retention at query time, so the write succeeds and the data just
isn't there. That's also why I check retention against the span of the data I'm about to write
rather than against the system I imagine running. And since Core fixes retention at database
creation with no way to alter it, getting that wrong costs a re-ingest, not a config edit."

### C-07 — Asserted a per-range "pin to full resolution" feature that does not exist   [M1, 2026-08-30]

**Proposed:** for important time intervals selected by scientists, "I believe there is a feature
to pin them and store them as high resolution untouched."

**Problem with it:** there is no such feature in InfluxDB 3 Core. Retention is per-database,
uniform across the database, immutable after creation, with no per-series, per-table or
per-time-range exemption, hold or pin. Claiming it under review fails on the first follow-up
question. The instinct is good — retention holds on regions of interest are a real historian
pattern — but it is build-work here, and calling it a feature hides the design problem that
matters: **pinning is retroactive.** A scientist marks a window as interesting after the fact,
often weeks later after a fault or an odd result, which means a short raw window doubles as a
deadline for noticing. If the mechanism is "copy the range into a database with no retention",
it only protects data somebody thought to pin *before* the raw tier expired.

**Principle:** never let "I think the product does this" stand in for a design decision — check,
because the difference between a feature and build-work is the difference between a config line
and a component with its own failure modes. And when a mechanism is triggered by a human noticing
something, the trigger's latency is part of the design: ask how long the user has to act, and
what happens when they miss it.

**Defense:** "Pinning regions of interest isn't something Core gives me — retention
there is per-database, uniform and fixed at creation — so it's a component I build: a scientist
marks a window, and a job copies that range into a database with no retention, with the window's
metadata in Postgres alongside the experiment record. The thing I'd flag about it is that pinning
is retroactive. People decide a window mattered after the fact, so the raw retention period is
really a deadline for noticing, and I'd want that number set by how late people realistically
re-open a run rather than by storage cost alone."

### C-08 — Attributed a per-range "pin" capability to InfluxDB Enterprise   [M1, 2026-08-30]

**Proposed:** after C-07, the revised position was "InfluxDB Enterprise allows you to pin
experiments, but since I'm not paying for it we stick to the workaround."

**Problem with it:** Enterprise does not have that capability either, so the claim relocated the
error rather than fixing it. What Enterprise actually adds over Core on retention is that database
retention periods become **updatable after creation** (`influxdb3 update database` / PATCH), and
that **table-level** retention periods can override the database setting (those, once created, are
themselves not updatable). There is no per-range, per-row or per-experiment exemption at any tier
of the product. The framing also under-sold the chosen design: the copy-into-a-no-retention-database
approach is not a budget workaround for a missing paid feature, it is the actual answer at every
tier, so presenting it as a downgrade concedes ground that does not need conceding.

**Principle:** when a claim about a product feature is corrected, re-verify the *replacement*
claim rather than moving it up a pricing tier — "the paid version must have it" is a guess wearing
the costume of a fact. And separately: know which of your designs are forced by a genuine product
limit and which are simply correct, because describing a correct design as a workaround invites an
attack that would otherwise not exist.

**Defense:** "Retention in InfluxDB is per-database and, on Core, fixed at creation. What
Enterprise would buy me is being able to *change* a retention period after the fact and to set
different retention per table — which is worth real money, because on Core a wrong retention number
costs a re-ingest rather than a command. What Enterprise would *not* buy me is pinning: no tier of
the product can exempt a time range from expiry. So copying interesting windows into a database with
no retention isn't a budget compromise, it's the design I'd write on Enterprise too."
