# Schema reference

Compact reference for deliverable A. Every number here traces to a cited source — an ADR, the
pre-ingest census, or the data dictionary. Nothing here is a new decision; see the cited ADRs for
the reasoning behind each call.

## 1. The two tables

Two InfluxDB tables, split by value type, same tag set on both
(ADR-0006, Decision):

| | `readings_numeric` | `readings_state` |
|---|---|---|
| **tags** | `experiment_id`, `source`, `signal` | `experiment_id`, `source`, `signal` |
| **fields** | `value` (float64), `quality` (string) | `value` (string), `quality` (string) |
| **signals** | 23 numeric signals | `valve_state`, `process_state` |

`quality` is a **field on both tables, not a tag** — it describes one reading at one instant, not
what the series *is*; tagging on it would fragment a single sensor into a GOOD series and a BAD
series (ADR-0006, Why).

**Why the split exists** (ADR-0006, Context/Why):
- In InfluxDB 3, a column's type is fixed by its first write, per `(table, column)`. 23 of the 25
  `(source, signal)` pairs are numeric; two (`valve_state`, `process_state`) are categorical
  strings. A single `value` field cannot hold both — this is a hard write-time constraint, not a
  style preference.
- Deliverable A requires that raw values be preserved unchanged and that this be shown by query.
  Encoding the two categorical signals as integers (the rejected Option 1) would mean the database
  never holds what the sensor actually reported, and would invent a numeric ordering that doesn't
  exist — `mean(value)` over a window spanning `STARTUP` and `LOAD_CHANGE` would return a number
  that looks fine and means nothing. Two tables, one float-typed and one string-typed, avoid both
  problems: raw values are stored exactly as they appear in the CSV, and there is no type conflict.

## 2. Cardinality — 150 series, measured

**150 series**, measured directly against the raw CSV by the pre-ingest census
(`reports/pre_ingest_census.md`), not estimated: 520,005 rows resolve to 25 distinct
`(source, signal)` pairs (signal names are unique across sources, so `signal` alone identifies a
series within an experiment) across 6 experiments → 6 × 25 = 150 distinct `(experiment_id, source,
signal)` series (ADR-0006, Context, citing the same scan). Cardinality grows linearly in
experiment count only, and is not a constraint at this scale (ADR-0006, Why).

Also from the same scan (ADR-0006, Context): quality flags are `GOOD` 519,675 / `UNCERTAIN` 230 /
`BAD` 100 — 0.06% non-`GOOD`, which is why `quality` as a dense field is noted as "99.94%
redundant" but kept anyway, because it makes exclusion a `WHERE` clause on the same row
(ADR-0006, Consequences).

## 3. Retention — four tiers (ADR-0011, Decision)

Retention is per-database in InfluxDB 3 Core and immutable after `create database`, so each tier
with a distinct retention period is a distinct database (ADR-0011, Context). The plant-policy value
is the stakeholder default this ADR defends; the local value is what this repo's environment is
actually configured with, per `.env.example` (T2) as recorded in `docs/plans/M1.md` ("Three calls
made in this phase").

| Tier | Database | Plant policy | Local value | Reason |
|---|---|---|---|---|
| Raw | `dac_raw` | 9 months | **1 year** (`365d`) | Plant policy: a stakeholder decision belonging to the lab manager/process owners, not derived here (ADR-0011, Why). Local: the six experiments are historical backfill (2026-03-02 → 2026-06-15) against an August wall clock; a 9-month *local* window would have silently expired `EXP_004` around 2026-12-02, before it was ever queried (M1.md; MISTAKES.md C-06). |
| Rollup | `dac_rollup` | 1 year | **5 years** (`5y`) | 1-minute buckets of numeric signals only; a cache with a longer horizon than raw because it is 60:1 smaller (ADR-0011, Decision/Why). Local value has no specific ratio to raw's 365d — just headroom so the rollup outlives raw locally the way the plant-policy rollup outlives plant-policy raw (`.env.example`). |
| Intervals of interest | `dac_pinned` | none | none | Full-resolution copies of pinned time ranges, including `readings_state`, kept indefinitely because pinning is deliberate rather than accidental retention (ADR-0011, Decision). |
| Cold | object storage | lifecycle policy | — | Parquet under an object-store lifecycle policy, queried by DuckDB/Athena/Spark with no InfluxDB in the path; nearly free because the storage format is already Parquet, not a proprietary format needing export/convert (ADR-0011, Why). |

## 4. Rollup column set (ADR-0011, Decision)

Per `(experiment_id, source, signal, bucket_start)`, one row per 1-minute bucket. The floor
interval of 1 minute is set by the slowest polled rate (ambient, ~1/60 Hz) so every signal gets a
non-empty bucket (ADR-0011, Decision).

| Group | Columns | Behavior under a policy change |
|---|---|---|
| **Verdict-independent** | `count_all`, `min_all`, `max_all`, `sum_all`, `sumsq_all` | Never invalidated — computed over *every* sample regardless of quality verdict. `min_all`/`max_all` are the physical extremes actually observed and survive raw expiry as ground truth no cleaning-policy change can revise. |
| **Verdict-dependent** | `count_included`, `mean`, `std`, `median` | Computed only over samples the inclusion predicate accepts. Recomputable inside the raw window; frozen once raw expires. |
| **Composition** | `count_good`, `count_uncertain`, `count_bad` | Breakdown of the acquisition-time `quality` flag per bucket. |
| **Provenance** | `policy_version` | Stamps which predicate generation sealed the bucket at the moment it froze (raw expiry) — needed because buckets across the table freeze under different policy generations over time, and that mixture is permanent (ADR-0011, Why). |

**Std is population std (denominator n), not sample std (n−1).** With sample std, an n=1 bucket has
undefined std and is unrecoverable — which happens for all four ambient signals at 1-minute
buckets — so the convention is fixed as population std (ADR-0011, Why).

`sum_all`/`sumsq_all` are stored even though `count + mean + std` is algebraically sufficient to
re-derive them, because pooling sums is associative addition with nothing to get wrong, whereas
pooling means/stds requires a weighted formula and an n-vs-n−1 convention that silently yields a
plausible wrong number if confused (ADR-0011, Why).

**Quality policy at M1:** the inclusion predicate is a stated placeholder, `quality == 'GOOD'`
(`UNCERTAIN` excluded, treated as `BAD`). This is *not* the real policy — the real policy is M3's
pipeline verdict, since acquisition-time `quality` is not exhaustive (a stuck sensor can read
`GOOD` in-range). M1 builds and verifies the machinery against the placeholder; M3 supplies the
policy and the rollup is rebuilt (ADR-0011, Decision).

## 5. Volume arithmetic

Per-signal nominal rates, by count of signals at each rate (`task/DATA_DICTIONARY.md`, cited in
ADR-0011, Context): **9 signals at ~1 Hz, 4 at ~0.5 Hz, 6 at ~0.2 Hz, 4 at ~1/60 Hz, 2 event-based**
(the two categorical `readings_state` signals, written on change, not polled — excluded from the
count below).

Extrapolated to one plant logging continuously for a full day (points/day = signal count × samples/second × 86,400 s/day):

| Rate group | Signals | Samples/day per signal | Points/day |
|---|---|---|---|
| ~1 Hz | 9 | 86,400 (1 × 86,400) | 777,600 |
| ~0.5 Hz | 4 | 43,200 (0.5 × 86,400) | 172,800 |
| ~0.2 Hz | 6 | 17,280 (0.2 × 86,400) | 103,680 |
| ~1/60 Hz | 4 | 1,440 (86,400 / 60) | 5,760 |
| **Total** | 23 | — | **1,059,840 points/day** |

777,600 + 172,800 + 103,680 + 5,760 = **1,059,840 points/day**, matching ADR-0011's stated figure.
The 1 Hz group alone is 73% of it (ADR-0011, Context).

Extrapolated to a plant-year: 1,059,840 × 365 = 386,841,600 ≈ **387 M points/plant-year**
(ADR-0011, Context).

**Rollup ratio at one minute:** for a 1 Hz signal, 60 samples/minute compress into one bucket, i.e.
**60:1** (ADR-0011, Context: "Rollup ratios are fixed arithmetic: 1 Hz → 1 min is 60:1").

## 6. The rollup-lag invariant

**Rollup lag must stay strictly below the raw retention period** (ADR-0011, Why). The rollup is a
cache, not a record: inside the raw window, a bucket's aggregate is provisional and can be
recomputed at will; it becomes permanent only once raw drops out from under it at the retention
boundary.

**Consequence of violating it:** if the rollup job stalls or falls behind, buckets cross the raw
retention expiry boundary before the rollup job has caught up to them — carrying a **stale or
missing aggregate that is then permanently frozen**, because raw data needed to recompute it is
gone. There is **no recovery path**: retention on Core deletes asynchronously and irreversibly, and
nothing else holds the raw samples once they expire. This is named as the failure mode where every
individual point still looks fine while the pipeline has silently stopped moving data — the rollup
must therefore be *monitored*, not merely scheduled (ADR-0011, Consequences).

## 7. Why `readings_state` is never rolled up

`readings_state` (`process_state`, `valve_state`) goes to the longest tier at full fidelity and is
**never rolled up** (ADR-0011, Decision) — exempted on semantics, not size (ADR-0011, Why):

- These signals are **written on change**, not polled. An empty bucket therefore means *no change*,
  not *no data* — the two are indistinguishable if the bucket is aggregated the same way a polled
  numeric signal would be.
- Aggregating them would repeat the exact failure ADR-0006 rejected integer-encoding categoricals
  to avoid: `mean()` over a state column would return a number that looks fine and means nothing,
  because there is no numeric ordering between `STARTUP`, `STEADY_STATE`, `LOAD_CHANGE`, and
  `SHUTDOWN` for an aggregate to respect.
- The table is tiny regardless (~73 rows across all six experiments: 7–19 `process_state` and 3–5
  `valve_state` rows each, per ADR-0011, Why) — size is not why it's exempt, but it does mean the
  exemption costs nothing in storage.
- Because they never expire and never roll up, `readings_state` rows become the permanent index
  into what happened on the plant (ADR-0011, Why).

## Sources cited

- ADR-0005 — PostgreSQL for experiment metadata
- ADR-0006 — Time-series data model: tags, fields, numeric/state split
- ADR-0011 — Retention, tiering, and the rollup schema
- ADR-0012 — Postgres migrations, `experiments.json` loader with per-field provenance
- `reports/pre_ingest_census.md` — measured row/series counts, quality distribution
- `task/DATA_DICTIONARY.md` — per-signal nominal sample rates
- `docs/plans/M1.md` — local retention values (T2 scope, "Three calls made in this phase")
