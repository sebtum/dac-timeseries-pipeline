# Schema reference

Compact reference for deliverable A. Every number here traces to a cited source — an ADR, the
pre-ingest census, or the data dictionary. Nothing here is a new decision; see the cited ADRs for
the reasoning behind each call.

## 1. The tables

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

### The conflicts table (M2, ADR-0007 addendum, ADR-0013)

A third table, `readings_conflicts`, holds one row per **discarded** reading when two or more
readings claim the same instant for the same series. The kept reading is in `readings_numeric` /
`readings_state`; both readings are here, so nothing is lost.

| | `readings_conflicts` |
|---|---|
| **tags** | `experiment_id`, `source`, `signal`, `discard_rank` (1 = the best of the discarded readings; makes a group of three keep two records) |
| **time** | the contested instant, so a query joins the conflict to the kept reading on `time` plus the three tags |
| **fields (text)** | `value_kept_raw`, `value_discarded_raw` (exactly as the file wrote them), `quality_kept`, `quality_discarded`, `reason` (`value_differs` or `quality_differs`), `resolution` (`better_quality`, `present_value`, `lower_value`, `alphabetical`) |
| **fields (int)** | `source_row_kept`, `source_row_discarded` (data-row numbers in the CSV, header excluded) |

Real file: 10 rows, every one `value_differs` / `lower_value`. An exact copy (same value, same
quality) is counted in the ingest summary, not stored here. An empty value is stored in the
readings table as a point with a `quality` field and no `value` field.

### The processed tables (M3, ADR-0015)

Three more tables, written by `python -m scripts.clean`, in the **same database** as the raw tables
(`dac_raw`), so they expire with raw. The raw tables are never written by cleaning. Every table has
the tags `experiment_id`, `source`, `signal` and `policy_version` (the rule set, `m3-v1`; a new rule
set writes new series beside the old ones). Time is the reading's own instant unless noted. The
rules and reasons are in [`cleaning_policy.md`](cleaning_policy.md).

| | `readings_processed` | `state_intervals` | `quality_intervals` |
|---|---|---|---|
| **what a row is** | one per numeric reading (dense: same count as `readings_numeric`) | one per state event, and how long it lasted | one per gap or stuck stretch |
| **tags** | `experiment_id`, `source`, `signal`, `policy_version` | same four | same four plus `kind` (`gap` or `flatline`) |
| **time** | the reading's instant | the event's instant | the interval's start |
| **fields (float)** | `value_raw` (absent when the raw point has no value), `value` (absent when excluded) | `seconds` | `seconds` |
| **fields (text)** | `quality` (acquisition flag), `verdict` (`accepted` or `excluded`), `reason` (empty when accepted), `flags` (comma-separated) | `value_raw`, `value` (absent when excluded), `quality`, `verdict`, `reason`, `flags` | none |
| **fields (int)** | none | `end_ns` (exclusive end of the interval) | `end_ns`, `points` (flatline: readings flagged; gap: 0) |

Rules that hold on all three:

- **Raw value and processed value sit side by side.** `value` equals `value_raw` when the reading is
  accepted and is absent when it is excluded. Nothing is clamped, filled or smoothed.
- **`reason` is empty exactly when the reading is accepted.** An accepted row stores `""`, which
  Core keeps as an empty string (measured, ADR-0015).
- **Counts balance per series:** a series has as many processed rows (in `readings_processed` or
  `state_intervals`) as raw readings. This is read back and checked on every run and written to
  `cleaning_summary.json`.
- **A gap or flatline row invents no reading.** State signals get no gap rows.

Real run (policy `m3-v1`): 519,906 rows in `readings_processed`, 74 in `state_intervals` and 34 in
`quality_intervals` (29 gaps, 5 flatline runs); 150 series, 519,980 readings = 514,443 accepted +
5,537 excluded.

### The metrics tables (M4, ADR-0016)

One more InfluxDB table and two Postgres tables, written by `python -m scripts.metrics` after
cleaning. The formulas, units and rules are in [`metrics.md`](metrics.md).

**InfluxDB `metrics_series`**, in the **same database** as the raw and processed tables
(`dac_raw`), so it expires with raw. One row per instant where the derived value exists.

| | `metrics_series` |
|---|---|
| **tags** | `experiment_id`, `metric` (`power_computed` W, `power_residual` W, `capture_efficiency` fraction, `capture_rate` kg/h), `metrics_version` (`m4-v1`), `policy_version` (the cleaning rule set the inputs came from, `m3-v1`) |
| **time** | the instant of the value |
| **fields (float)** | `value` |

**Postgres**, created by migration `0003_experiment_metrics.sql`. Both tables are upserted in one
transaction per run, so a rerun overwrites identical rows and a failed run leaves nothing partial.
They outlive raw retention on purpose: they are small summaries. Every `experiment_id` references
`experiment`, so a metric joins to the experiment metadata.

| | `experiment_metrics` | `signal_quality` |
|---|---|---|
| **what a row is** | one metric of one experiment (13 per experiment) | one signal of one experiment (25 per experiment) |
| **primary key** | `experiment_id, metrics_version, metric` | `experiment_id, metrics_version, source, signal` |
| **columns** | `policy_version`, `value` (null when status is `none`), `unit`, `coverage` (null for the four quality shares), `status` (`complete`, `partial` or `none`; null for the quality shares) | `policy_version`, `nominal_interval_s` (null for state signals), `present`, `expected` (null for state signals), `accepted`, `bad`, `uncertain`, `completeness`, `valid_fraction`, `bad_fraction`, `uncertain_fraction` (each null when its denominator is 0) |

Real run (metrics `m4-v1`): 121,167 points in `metrics_series` (24 series: 6 experiments x 4),
78 rows in `experiment_metrics` and 150 in `signal_quality`; the counts are read back after the
write and checked against what was written. The summary is `reports/metrics_summary.json`
(contract `contracts/metrics_summary.schema.json`).

### The comparison tables (M6, ADR-0018)

Three Postgres tables, created by migration `0004_comparison.sql` and written by
`python -m scripts.load_comparison` from the committed `reports/comparison_summary.json` (M5), so
Grafana can read the steady KPIs and the pair comparability. Values are copied from the summary
unchanged; nothing is computed in the database. The loader replaces all rows of one
`compare_version` in one transaction and reads the counts back, so a rerun writes identical rows and
rows of other versions are untouched. They are not in InfluxDB and do not expire with raw. The
statuses are explained in [`comparison.md`](comparison.md).

| | `comparison_kpi` | `comparison_pair` | `comparison_pair_kpi` |
|---|---|---|---|
| **what a row is** | one steady-state KPI of one experiment | one pair of experiments, `a` before `b` | one KPI of one pair |
| **primary key** | `experiment_id, compare_version, kpi` | `a, b, compare_version` | `a, b, compare_version, kpi` |
| **references** | `experiment_id` references `experiment` | `a` and `b` reference `experiment`; `CHECK (a < b)` | `(a, b, compare_version)` references `comparison_pair`, `ON DELETE CASCADE` |
| **columns** | `policy_version`, `metrics_version`, `value`, `unit`, `coverage`, `status` (`complete`, `partial` or `none`), `interval_low`, `interval_high` | `conditions_status` (`same_conditions`, `supported` or `confounded`), `differing` (factor names in factor order, comma-separated; empty when none differ) | `unit`, `difference` (b minus a), `interval_low`, `interval_high`, `excludes_zero`, `coverage_status` (`both_complete`, `partial_coverage` or `not_available`) |

Real run (compare `m5-v1`): 30 rows in `comparison_kpi` (6 experiments x 5), 15 in `comparison_pair`
and 75 in `comparison_pair_kpi` (15 pairs x 5). The loader's contract is
`contracts/comparison_summary.schema.json`. The dashboards read these tables with the other
Postgres tables of this section and `experiment`; see [`dashboard.md`](dashboard.md).

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
| **No-value count (M3)** | `count_no_value` | Points in the bucket that were saved without a value (an empty reading). Left out of every value column, so `count_all + count_no_value` is the number of points in the bucket. Added by the M3 addendum to ADR-0011; 0 on the real data. |
| **Provenance** | `policy_version` | Stamps which predicate generation sealed the bucket at the moment it froze (raw expiry) — needed because buckets across the table freeze under different policy generations over time, and that mixture is permanent (ADR-0011, Why). Since M3 it is the cleaning version (`m3-v1`). |

**Std is population std (denominator n), not sample std (n−1).** With sample std, an n=1 bucket has
undefined std and is unrecoverable — which happens for all four ambient signals at 1-minute
buckets — so the convention is fixed as population std (ADR-0011, Why).

`sum_all`/`sumsq_all` are stored even though `count + mean + std` is algebraically sufficient to
re-derive them, because pooling sums is associative addition with nothing to get wrong, whereas
pooling means/stds requires a weighted formula and an n-vs-n−1 convention that silently yields a
plausible wrong number if confused (ADR-0011, Why).

**Quality policy (changed at M3, ADR-0015):** the inclusion predicate is the cleaning verdict,
`verdict = 'accepted'`, read from `readings_processed` for one policy version. The M1 placeholder
(`quality == 'GOOD'`) is gone. The rollup is a separate command run after cleaning
(`python -m scripts.rollup`), an external Python job (U-04 closed). Its aggregation is done in
Python on a plain pull, not in SQL (ADR-0014, last-bit sums). `readings_state` and `state_intervals`
are never rolled up. Real run: 16,256 buckets in about 12 minutes.

**Stale-field limit.** A later write of the same key without a field keeps the field's old value
(measured on Core 3.11.2). A rerun over rows of the same policy version writes identical values, so
nothing is stale. If rows of one version were ever changed so a bucket's `count_included` fell to 0,
its old `mean`, `std` and `median` would stay. Rule changes bump the version, so this cannot happen
by construction; read `mean`, `std` and `median` only where `count_included > 0`.

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
- The table is tiny regardless (74 rows across all six experiments, counted in `dac_raw` after the M2 ingest; ADR-0011 said ~73: 7–19 `process_state` and 3–5
  `valve_state` rows each, per ADR-0011, Why) — size is not why it's exempt, but it does mean the
  exemption costs nothing in storage.
- Because they never expire and never roll up, `readings_state` rows become the permanent index
  into what happened on the plant (ADR-0011, Why).

## Sources cited

- ADR-0005 — PostgreSQL for experiment metadata
- ADR-0006 — Time-series data model: tags, fields, numeric/state split
- ADR-0011 — Retention, tiering, and the rollup schema
- ADR-0012 — Postgres migrations, `experiments.json` loader with per-field provenance
- ADR-0013 — Ingestion (the conflicts table)
- ADR-0015 — Cleaning and quality pipeline (the three processed tables, the rollup over the verdict)
- ADR-0016 — Derived metrics (`metrics_series`, `experiment_metrics`, `signal_quality`)
- ADR-0017 — Comparison and findings (the summary the comparison tables copy)
- ADR-0018 — Grafana dashboards (the three comparison tables, migration `0004`)
- `reports/pre_ingest_census.md` — measured row/series counts, quality distribution
- `task/DATA_DICTIONARY.md` — per-signal nominal sample rates
- `docs/plans/M1.md` — local retention values (T2 scope, "Three calls made in this phase")
