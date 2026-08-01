# Schema & Dashboard Design

Driven build under time pressure — decisions made directly, reasoning kept short.
Architecture assumed (per working session): raw lands in InfluxDB untouched; Python pulls
windows for analysis; PostgreSQL holds experiment metadata and analysis-derived output
(summary KPIs, data-quality intervals).

## 1. InfluxDB schema

### Bucket `dac_raw` — immutable raw ingest

**Measurement:** `raw_reading`

**Tags** (indexed, series identity):
- `experiment_id` (EXP_001..EXP_006) — cardinality 6
- `source` (ambient/absorber/hydrolyzer/plant) — cardinality 4
- `signal` (~25 names) — cardinality ~25

Total series ≈ 150 → trivial cardinality, safe as tags.

**Fields** (unindexed, per-point values):
- `value` (float) — numeric signals only
- `value_str` (string) — categorical signals (`valve_state`, `process_state`), and any row
  that unexpectedly fails to parse as a number on a nominally-numeric signal
- `quality` (string: GOOD/UNCERTAIN/BAD) — the as-logged flag. This is a field, not a tag,
  because it varies point-to-point; tags are for series identity, not per-observation state.

Corrected from an earlier draft: InfluxDB enforces a single type per `(measurement, field
name)` across the **entire measurement**, not per series/tag-set. Writing `value=2.436`
(float) on one tag-set and `value="OPEN"` (string) on another, both under measurement
`raw_reading`, is a hard write-time conflict — confirmed by actually running the ingest.
Splitting numeric vs. categorical into separate field names (`value` / `value_str`) is what
avoids it.

```
raw_reading,experiment_id=EXP_001,source=hydrolyzer,signal=acid_pH value=2.436,quality="GOOD" 1780560000000000000
raw_reading,experiment_id=EXP_001,source=plant,signal=valve_state value_str="OPEN",quality="GOOD" 1780560000000000000
```

Timestamps normalized to UTC at ingest (sources mix `Z` and `+02:00` — normalize the instant,
never touch the numeric value).

**Why identity stays in tags, not the measurement name:** the data dictionary says as much
directly — one ingestion path handles all ~25 signals uniformly, and queries filter/group
generically (`source == "hydrolyzer"`) instead of needing near-duplicate queries per signal.

**Why long/narrow, not wide (one measurement per source with a field per signal):** the wide
form is a legitimate alternative and lets you read `current`+`voltage`+`power` off one point.
Not used here because signals within a source sample at different, independently-jittered
rates — forcing them into one row per timestamp means picking a resampling strategy at
*ingest* time, before quality has even been assessed. Raw stays exactly as sampled; alignment
happens downstream. Flag this trade-off if asked — "why long not wide" is a fair question.

### Bucket `dac_processed` — pipeline output, fully rebuildable from raw

**Measurement:** `reading_processed`

**Tags:** same as raw — `experiment_id`, `source`, `signal`

**Fields:**
- `value_raw` (float) / `value_raw_str` (string) — copy-through, split by type for the same
  reason `raw_reading` splits `value`/`value_str` (one type per field name per measurement)
- `value_clean` / `value_clean_str` — present only when a usable value exists after
  cleaning; absent if excluded with nothing to substitute
- `quality_raw` — the as-logged GOOD/UNCERTAIN/BAD
- `status` — pipeline verdict: `VALID` / `EXCLUDED_BAD` / `EXCLUDED_OUTLIER` / `STUCK`
- `reason` — populated whenever `status != VALID`, e.g. `"quality=BAD at source"`,
  `"|z|>4.0 vs rolling 60-sample window"`, `"identical value for >= 20 consecutive samples"`

This is the direct implementation of "raw value / processed value / quality flag / reason,
all visible, nothing silently dropped or fixed" — a consumer can always fall back to
`value_raw` and see exactly why `value_clean` differs or is missing.

**Gaps are not a point-level status.** A gap has no timestamp of its own to attach a status
to, so an interval that exceeds the max-trustable-gap threshold is written to
`data_quality_intervals` (`GAP_EXCEEDS_MAX`) instead of invented as a synthetic Influx point.
`status` only classifies points that actually exist.

**Per-signal-type handling** (differs deliberately):
- **Continuous numeric process variables** (pH, temperature, flow): interpolate across gaps
  under a max-gap threshold, else `GAP`; stuck-sensor check (flat too long); rolling
  z-score / rate-of-change for outliers.
- **Event-based categorical signals** (`valve_state`, `process_state`): never numerically
  interpolated — a "gap" just means "no change since last event." Processed value =
  forward-filled last known state, `status=VALID`, no reason. Treating this like a continuous
  signal's gap would be a real mistake, worth naming explicitly if it comes up.
- **Integrated/cumulative quantities** (energy from power): errors compound — one bad power
  sample corrupts every cumulative value downstream of it. The cumulative series needs its
  own `status`/`reason` tracking whether *every* input sample feeding it was `VALID`, not just
  a flag on the instantaneous point.

## 2. PostgreSQL schema

```sql
-- experiment-level metadata, one row per experiment (from experiments.json)
CREATE TABLE experiments (
    experiment_id              TEXT PRIMARY KEY,
    start_time                 TIMESTAMPTZ NOT NULL,
    end_time                   TIMESTAMPTZ,
    duration_s                 NUMERIC,
    current_setpoint_nominal_a NUMERIC,
    air_flow_nominal_m3h       NUMERIC,
    solvent_flow_nominal_lmin  NUMERIC,
    operator                   TEXT,
    sorbent_batch               TEXT,
    notes                       TEXT
);

-- scalar per-experiment KPIs, computed by the analysis pipeline (rebuildable)
CREATE TABLE experiment_summary_metrics (
    experiment_id               TEXT REFERENCES experiments(experiment_id),
    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_energy_kwh            NUMERIC,
    avg_capture_efficiency      NUMERIC,
    avg_capture_rate_kg_h       NUMERIC,
    specific_energy_kwh_per_kg  NUMERIC,
    data_completeness_pct       NUMERIC,
    valid_sample_pct            NUMERIC,
    bad_quality_pct             NUMERIC,
    PRIMARY KEY (experiment_id, computed_at)
);

-- interval-level data quality findings
CREATE TABLE data_quality_intervals (
    id              SERIAL PRIMARY KEY,
    experiment_id   TEXT REFERENCES experiments(experiment_id),
    source          TEXT NOT NULL,
    signal          TEXT NOT NULL,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    interval_type   TEXT NOT NULL,  -- GAP_EXCEEDS_MAX / INTERPOLATED / STUCK_SENSOR / EXCLUDED_BAD / EXCLUDED_OUTLIER
    reason          TEXT,
    method          TEXT            -- e.g. "linear interpolation", "forward-fill", "z-score>4"
);
```

`data_quality_intervals` is the bridge between per-point `status` in Influx and
human-scannable, queryable intervals — and it's what feeds Grafana annotations below.

## 3. Grafana dashboard sketch

**Data sources:** InfluxDB (`raw_reading`, `reading_processed`) + PostgreSQL (`experiments`,
`experiment_summary_metrics`, `data_quality_intervals`), both wired into one dashboard.

**Template variables:**
- `$experiment` — multi-select, values from `experiments.experiment_id` (Postgres) or an
  Influx tag-values query. Multi-select is what makes the overlay row possible.
- `$source` / `$signal` — cascading dropdowns (Influx tag-values queries).

**Row 1 — KPI summary.** Postgres, Stat/Table panels, one column per selected `$experiment`:
total energy, avg capture efficiency, specific energy consumption, data completeness %,
bad-quality % — straight from `experiment_summary_metrics`.

**Row 2 — Overlaid process trends.** InfluxDB `reading_processed`, time-series panel:
`value_clean` for the selected `$signal`, colored/split by `experiment_id`. Experiments start
at different wall-clock times, so this needs a common axis — shift `_time` at query time in
Flux by subtracting each experiment's `start_time` (joined from `experiments`), so every
series visually starts at the same origin while storage keeps real timestamps everywhere.
(Alternative: precompute `experiment_time_s` as a stored field at ingest — simpler queries,
but bakes a start-time assumption into the processed layer permanently. Kept the shift at
query time instead.)

**Row 3 — Data quality visibility.**
- **State timeline panel** on `reading_processed.status` per selected signal — a colored
  strip (VALID / INTERPOLATED / EXCLUDED_BAD / STUCK / GAP) under each trend, so bad
  stretches are visible at a glance instead of hidden inside a smoothed line.
- **Annotations** on the trend panels, queried from `data_quality_intervals` — shaded
  vertical regions marking gaps/exclusions directly on the process trend, `reason` as the
  tooltip.

**Row 4 — Cross-experiment comparison table.** Postgres table panel joining
`experiment_summary_metrics` across selected experiments, sortable (e.g. by specific energy
consumption) — gives the "concrete findings" ask a ready-made ranking instead of eyeballed
plots.

This is a sketch, not a built dashboard, given the time budget — noting that explicitly per
the task's own guidance that a clear next-step note beats a rushed half-build.
