# ADR-0011 — Retention, tiering, and the rollup schema

Status: Accepted
Milestone: M1   Deliverable: A   Date: 2026-08-30

## Context

ADR-0006 settled what a point *is*. Deliverable A asks a second question in the same paragraph:
"months of high-resolution electrochemical data adds up — what's your retention/downsampling/
tiering strategy, and what stays at full resolution vs. gets rolled up over time?" That half had
no decision until now.

Facts measured before deciding, not estimated:

- **520,005 rows, 31,877,732 bytes of CSV** = 61.3 bytes/row as text. Six experiments × 2 h =
  12 experiment-hours (`reports/pre_ingest_census.md`).
- Signals by nominal rate (`task/DATA_DICTIONARY.md`): 9 at ~1 Hz, 4 at ~0.5 Hz, 6 at ~0.2 Hz,
  4 at ~1/60 Hz, 2 event-based.
- Extrapolated to **one plant logging continuously**: 9×86,400 + 4×43,200 + 6×17,280 + 4×1,440 =
  **1,059,840 points/day ≈ 387 M points/plant-year.** The 1 Hz group alone is 73% of it. This
  number *is* the "months of data adds up" question.
- Bytes-per-point in Parquet is **not** derivable from the CSV figure; it is measured post-ingest
  at M2.5 rather than guessed here, consistent with how cardinality was handled in ADR-0006.
- Rollup ratios are fixed arithmetic: 1 Hz → 1 min is 60:1; 1 Hz → 5 min is 300:1.

Constraints that shape everything below, verified against the documentation rather than assumed:

- **In InfluxDB 3 Core a retention period is set at `create database` and cannot be changed
  afterwards.** Changing it means creating a new database and migrating data. Retention is
  therefore **per-database, not per-table**, so any tier with a distinct retention period is a
  distinct database.
- **Core enforces retention at query time**: expired points are filtered out of results while
  still present in storage, deleted asynchronously by a background service. The failure mode is
  therefore *silent* — a write succeeds and the data is simply invisible.
- **No tier of InfluxDB — Core or Enterprise — has per-range, per-row or per-experiment retention
  exemption.** Enterprise adds *updatable* database retention and *table-level* retention
  (themselves not updatable after creation). There is no "pin this window" feature anywhere.
- **InfluxDB 3 stores data as Apache Parquet in an object store** (`--object-store` = file, s3,
  google, azure). The storage format is open, not proprietary as TSM was in 1.x/2.x.

## Options considered

### Option 1 — One database, infinite retention, no rollup
Advantages: nothing to build; every query hits full resolution; no tier boundaries to defend; no
risk of a rollup and its source disagreeing.
Caveats: does not answer the question the brief actually asked — "keep everything" is the absence
of a retention strategy, not one; 387 M points/plant-year grows without bound and the cost answer
becomes "it gets expensive"; forecloses nothing but demonstrates nothing.

### Option 2 — One database with a retention period, no rollup
Advantages: simplest thing that is genuinely a policy; one number to defend; storage bounded.
Caveats: expiry is total — after the window there is no record at all that the plant ran, so
long-horizon trend questions ("is stack voltage drifting year over year") become unanswerable;
throws away the 60:1 win that costs almost nothing to take.

### Option 3 — Tiered: bounded raw + 1-minute rollup + unbounded intervals of interest + cold Parquet
Advantages: full resolution where it is needed and cheap aggregates where it is not; the
intervals-of-interest tier gives back exactly what Option 2 destroys, deliberately rather than by
accident; cold tier is nearly free because the files are already Parquet; each tier's retention is
a stated number with a reason.
Caveats: three databases instead of one, because Core's retention is per-database; a rollup is
code that has to be written, tested and monitored; the rollup and raw can disagree; pinning is
build-work rather than configuration.

### Option 4 — InfluxDB 3 Enterprise for table-level and updatable retention
Advantages: retention changeable after the fact, so a wrong number costs a command rather than a
re-ingest; different retention for `readings_numeric` and `readings_state` inside one database.
Caveats: rejected already in ADR-0004/A-02 on licensing grounds; and it does **not** solve the
problem it looks like it solves — there is still no per-range pin, so the intervals-of-interest
database is required at every tier. Enterprise buys the ability to change one's mind, not a
feature this design is missing.

## Decision

**Option 3.** Three InfluxDB databases plus a cold Parquet tier:

| Tier | Database | Retention | Contents |
|---|---|---|---|
| Raw | `dac_raw` | **9 months** (plant policy) | `readings_numeric`, `readings_state`, values exactly as reported (ADR-0006) |
| Rollup | `dac_rollup` | **1 year** | 1-minute buckets of numeric signals only |
| Intervals of interest | `dac_pinned` | **none** | full-resolution copies of pinned time ranges, incl. `readings_state` |
| Cold | object storage | lifecycle policy | Parquet, queried by DuckDB/Athena/Spark with no InfluxDB in the path |

**The retention period is a parameter of the init script, not a constant in it.** 9 months is the
*plant policy* this ADR defends; the local/demo environment is initialised with a different value,
committed with its reason. Dev and prod diverging on retention is normal and needs no apology.

**Rollup interval: 1 minute.** The floor is the **slowest polled rate** (60 s ambient), so every
signal gets a non-empty bucket. LCM(1, 2, 5, 60) also equals 60 here, but LCM is not the criterion
and would give the wrong answer if ambient were 90 s (LCM 180, correct floor 90).

**Rollup schema**, per `(experiment_id, source, signal, bucket_start)`:

```
verdict-independent (never invalidated by a policy change):
  count_all, min_all, max_all, sum_all, sumsq_all
verdict-dependent (computed over included samples only):
  count_included, mean, std, median
composition:
  count_good, count_uncertain, count_bad
provenance:
  policy_version
```

**Quality policy:** `UNCERTAIN` is treated as `BAD` for aggregation. The included-sample predicate
is **M3's pipeline verdict**, not acquisition-time `quality` — the data dictionary warns the
acquisition flag is not exhaustive, and a stuck sensor reads in range with a `GOOD` flag (C-03).
At M1 the *machinery* is built and verified against a stated placeholder predicate
(`quality = 'GOOD'`); M3 supplies the *policy* and the rollup is rebuilt.

**`readings_state` is never rolled up.** It goes to the longest tier at full fidelity.

**Pinning is a copy, not an exemption:** a pin is a time range copied into `dac_pinned`, with the
range's metadata in Postgres. Ranges come from multiple **producers** — experiment metadata,
scientist selection, automatic detection later — and are keyed by time range, never by experiment
identity.

## Why

**The tier count is forced, not chosen.** Core fixes retention per database and forbids changing
it, so "raw for 9 months, aggregates for a year, some things forever" is arithmetically three
databases. There is no arrangement of one database that expresses it.

**9 months is defended as a policy and configured as a parameter.** The number itself is a
stakeholder decision that has not happened — it belongs to the electrochemical lab manager and the
process owners, and the honest answer is "here is my default and here is who decides it." But a
retention period is a claim about data age *relative to now*, and this dataset is historical
backfill: the experiments ran 2026-03-02 to 2026-06-15 against an August wall clock. A 90-day
window would have hidden five of six experiments silently (MISTAKES.md C-06). Separating the plant
policy from this database's configuration is what keeps both claims true at once.

**The rollup is a cache, not a record, and the freeze point is the expiry boundary.** Inside the
raw window a bucket's rollup is provisional and disposable — recompute at will. It becomes
permanent only when raw drops out from under it. Two things follow. First, `policy_version` is
still required, for a better reason than "the verdict evolves": per bucket there is exactly one
verdict, the one in force at expiry, but across the table, buckets crossed the expiry line under
different policy generations, and that mixture is permanent and accumulates forever at the trailing
edge. The stamp labels which generation sealed each frozen bucket. Second, it creates a hard
operational invariant — **rollup lag must stay strictly below the raw retention period** — and
violating it is unrecoverable.

**This is why 9 months is a good number rather than an arbitrary one.** The raw window is not "how
far back can we look", it is **"how far back can we still change our mind"**: the period during
which a corrected cleaning policy can still be applied to data that has not yet been frozen into
its rollup.

**Splitting the rollup columns by verdict dependence is cheap and buys permanence.** Five extra
numeric columns against a 60:1 reduction is nothing. `min_all`/`max_all` in particular — the
physical extremes actually observed — should never be subject to a cleaning opinion, and they
survive raw expiry as ground truth no policy change can invalidate.

**On sufficient statistics:** `count + mean + std` *is* algebraically sufficient to re-aggregate
(`sum = n·m`, `sumsq = n·(s² + m²)`), so storing sum and sumsq is redundant in principle. They are
stored anyway for two concrete reasons: with *sample* std (denominator n−1) an n=1 bucket has
undefined std and is unrecoverable — which happens for all four ambient signals at 1-minute
buckets — and pooling sums is associative addition with no formula to get wrong, where pooling
means and stds requires the weighted formula and an n-vs-n−1 convention that yields a plausible
wrong number when confused. **The convention here is population std (denominator n).** Median is
genuinely non-mergeable and is frozen at the tier that computed it.

**`readings_state` is exempted on semantics, not size.** It is tiny (~73 rows across all six
experiments: 7–19 `process_state` and 3–5 `valve_state` each), but the reason not to roll it up is
C-01's: these signals are written on change, so an empty bucket means *no change*, not *no data*.
Aggregating them would repeat exactly the failure ADR-0006 rejected integer encoding to avoid —
`mean()` over a state column returning a number that looks fine and means nothing. Because they
never expire and never roll up, they become the permanent index into what happened.

**Interval selection must not depend on the event stream.** Gating retention on `process_state` /
`valve_state` transitions would gate an irreversible action on two signals that have not been
profiled (that is M2.5), and C-02's principle applies: validate the gate before trusting the
gating. A missing state-change event would mean a real transition is never pinned and, after nine
months, is gone with no record that anything was missed. Experiment windows come instead from
`experiments.json` → Postgres, a source that cannot silently lose an event.

**The cold tier is nearly free because the format is already right.** In 1.x/2.x, TSM was
proprietary and cold tiering meant an export-and-convert ETL job. In v3 the cold tier is *the same
Parquet files* under an object-storage lifecycle policy, readable directly by DuckDB, Athena, Spark
or anything Arrow-native.

## Consequences

- **Three databases, created once.** Retention is immutable on Core, so a wrong number costs a
  database re-create and a re-ingest, not a config edit. `docker compose down -v` plus re-init is
  the local recovery path.
- **The rollup must be monitored, not merely scheduled.** Rollup lag below raw retention is a hard
  invariant. Its violation is the failure mode where every point still looks individually fine
  while the pipeline has stopped moving data — deliverable H's named failure, arrived at from this
  design rather than recited.
- **A quality-policy change forces a rollup rebuild** over the window where raw still exists.
  Beyond it, old buckets keep their old `policy_version` and are honestly labelled rather than
  silently wrong.
- **Pinning is build-work with a deadline.** It is retroactive — people decide a window mattered
  after the fact — so the raw retention period doubles as *how long someone has to notice*. That
  reframing is the strongest argument for setting the number by how late runs get re-opened rather
  than by storage cost.
- **Duplicated storage for pinned ranges**, accepted and small.
- **Influx does not manage the cold tier.** Core writes Parquet where it is pointed; it will not
  migrate files to a colder class or know they moved. The lifecycle policy and the catalogue of
  what lives where are ours. Claiming "InfluxDB tiers it automatically" would be false.
- **The M1 verify criterion splits**: machinery at M1 against a stated predicate, policy at M3.
- **Retention is proven behaviourally, not by configuration** — see ROADMAP M1 Verify. Reading
  retention back via `influxdb3 show databases` or `GET /api/v3/configure/database` reported
  nothing on Core 3.7.0 (influxdata/influxdb#27082), so a configuration assertion could silently
  assert nothing.
- **Open:** where the rollup executes (U-04) is unresolved and interacts with U-09 — a Processing
  Engine plugin cannot read an M3 verdict that never materialises into InfluxDB.

## Assumptions relied on

A-01, A-02, A-03 (the retention numbers are defaults standing in for a stakeholder conversation)

## Related

ADR-0004 (Core, SQL — created U-04, U-05), ADR-0005 (Postgres metadata, the pin-range producer),
ADR-0006 (what a point is), ADR-0010 (profiling post-ingest). Corrections behind this record:
MISTAKES.md C-06, C-07, C-08.

## Defense

Raw stays nine months at full resolution, one-minute rollups keep a year, anything anyone marked
as interesting is copied into a database with no retention at all, and beyond that it is Parquet in
object storage read by DuckDB with no InfluxDB in the path. The nine months is a starting default,
not a derived number — that conversation belongs to the process owners — but I'd defend the *shape*
hard, because on Core retention is per-database and fixed at creation, so tiers are databases and a
wrong number costs a re-ingest. Two things I'd point at specifically. The rollup is a cache, not a
record: inside the raw window I can recompute it, so the retention period is really "how far back
can I still change my mind about a cleaning rule", and that gives me a hard invariant — rollup lag
must stay below raw retention, or buckets freeze with a stale aggregate and there is no recovery.
And I split the rollup columns by whether they depend on a quality verdict, so count, min and max
over every sample survive forever regardless of what the cleaning policy later decides. The state
signals are never rolled up at all — they're written on change, so an empty bucket means nothing
changed rather than no data, and averaging them would be meaningless.
