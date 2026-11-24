# ADR-0016 — Derived metrics: a batch job over accepted readings, labelled by coverage, never filled

Status: Accepted
Milestone: M4   Deliverable: E   Date: 2026-11-24

This is the record of M4. Decisions 1 to 20 were made while planning and approved by Sebastian
with the plan on 2026-11-24. The section "Decided at execute" lists what execute added.

## Context

In plain words: the brief asks for energy, capture rate, efficiency and energy per kilogram of CO2
for every experiment. The inputs have holes (a gap in the current, an hour of air flow that
cleaning excluded). So each number needs a rule for what it is made from, and a label that says how
much of the experiment it rests on. Nothing is filled in to hide a hole.

Details: M3 stored 519,980 readings with a verdict each (ADR-0015); 514,443 are accepted. M4 reads
the accepted ones for one policy version and derives 13 metrics and four series per experiment. Four
questions came from the brief: where each metric is computed, how energy is integrated, how an
excluded sample propagates into a derived value, and how a metric over incomplete data is labelled
(`docs/ROADMAP.md`, M4). The formulas, constants, entries and plausibility checks are in
[`docs/metrics.md`](../metrics.md); this ADR records why the job is built the way it is. The 20
decisions below are numbered as in the milestone record.

## Decision

Note on the `Rejected` column: where the plan recorded no rejected option, the cell says so. It
does not add one that was not weighed at the time.

### Where it runs, and what goes in (decisions 1 to 5)

| # | Decision | Rejected |
|---|---|---|
| 1 | **Mode standard, judge verify, five tasks run by agents** (Sebastian asked for tasks run in parallel where possible). Pure metric functions (T1) and storage (T2) in parallel; then fixture, CLI and end-to-end tests (T3); real data (T4); write-up (T5). A bug found by a later task is reported back to the owner, not patched outside the finder's files. | One piece (Sebastian's request); full mode (no new risk class; the formulas are pinned by hand-computed fixtures and an independent recompute). |
| 2 | **M3 accepted as done for starting M4.** Its newest Findings block is for commit `1dcd428`; HEAD `a7bade1` is the approved merge of `f020fc0`, which only renamed one test file. Accepted by Sebastian with the plan. | None recorded. |
| 3 | **Metrics are a Python batch job after cleaning** (`python -m scripts.metrics`), like the rollup. | Query-time SQL in Grafana: the formulas become untested dashboard text, and the gap rule and the energy-per-kg overlap are not plain SQL. A Processing Engine plugin: same reason as for the rollup (the rollup-location question, U-04). |
| 4 | **Inputs are accepted readings only; a derived value exists at an instant only when every input is accepted there.** Nothing is filled, clamped or smoothed; small negative currents stay (M3 decision 4), so power may be slightly negative. Missing inputs lower coverage. | Filling, clamping or smoothing missing inputs (the decision itself rules them out; no other option was weighed). |
| 5 | **Join on the exact same instant** for signals that share instants (voltage, current, power; `co2_in`, `co2_out`, `air_flow` at the 0.5 Hz instants: the profile found 0 unmatched). Ambient temperature and pressure (once a minute) are taken as-of: the latest accepted reading at or before the instant, used when its age is at most `AMBIENT_MAX_AGE_S = 120` (2 x nominal; 120 s used, 120 s + 1 ns not). | Resampling onto a grid (invents values); linear interpolation of ambient (filling). |

### Integration, power and energy (decisions 6 to 8)

| # | Decision | Rejected |
|---|---|---|
| 6 | **Integration is the trapezoid rule over consecutive derived points; a spacing above 2 x nominal of the derived series is a gap and is not bridged.** Power series (1 Hz): `POWER_MAX_SPACING_S = 2`. Capture series (0.5 Hz): `CAPTURE_MAX_SPACING_S = 4`. A spacing equal to the limit is bridged. Covered seconds = sum of bridged spacings. Sums use `math.fsum`. | Scaling an integral up to the full duration. |
| 7 | **Power: `power_computed = voltage x current` at instants where both are accepted. `power_residual = power - voltage x current` at instants where all three are accepted.** An instant agrees when `abs(residual) <= POWER_TOL_REL x abs(voltage x current) + POWER_TOL_W` (0.01, 10 W). The summary reports compared instants, residual median, p95 of the absolute residual, maximum absolute residual, count and fraction within tolerance. | None recorded. |
| 8 | **Energy twice:** `energy_kwh` from `power_computed`, `energy_logged_kwh` from the accepted logged `power`, each over its own covered time. `energy_relative_difference = (E_logged - E_computed) / E_computed`, both integrated over the overlap of their covered intervals, so a one-reading difference in coverage does not show as disagreement. `mean_power_kw = energy_kwh / covered hours`. | None recorded. |

### CO2 capture and energy per kilogram (decisions 9 to 11)

| # | Decision | Rejected |
|---|---|---|
| 9 | **Capture rate (kg/h) = air_flow [m3/h] x (co2_in - co2_out) [ppm] x 1e-6 x p M / (R T)**, with p = ambient pressure x 100 Pa, T = ambient temperature + 273.15 K, M = 0.04401 kg/mol, R = 8.314462618 J/(mol K). The inlet CO2 rate is the same with `co2_in` alone. `co2_captured_kg` and `co2_inlet_kg` are integrals of those series (decision 6); `capture_rate_mean_kg_h = co2_captured_kg / covered hours`. Assumes air flow in actual m3/h at ambient conditions, ppm by volume, humidity ignored, outlet volume equal to inlet volume (new assumption A-08). Known cost: EXP_005's first 30 ambient-pressure readings are UNCERTAIN (06:00Z to 06:29Z), so its capture coverage is about 0.75. | A fixed standard density (12 % off across -5 to 30 degrees Celsius). Filling the barometer (under 0.1 % effect) was rejected as filling. |
| 10 | **Capture efficiency series = (co2_in - co2_out) / co2_in at instants where both are accepted; `capture_efficiency_mean` = plain mean of that series** (`math.fsum`). Values at or below 0 are kept and counted (`efficiency_check.at_or_below_zero`). Coverage uses the 4 s spacing rule on the efficiency series. | Air-flow weighting (ties efficiency to the air-flow sensor; flow is near constant within a run). |
| 11 | **Energy per kg CO2 (`sec_kwh_per_kg`) = energy of `power_computed` over the overlap of the power and capture covered intervals, divided by CO2 captured over the same overlap.** Each series is integrated over the overlap exactly: its piecewise-linear line on each covered interval, clipped to the overlap (interpolated endpoints). Coverage = overlap seconds / duration. Value null when the overlap is empty or captured CO2 over it is 0 or less. | Total energy divided by total CO2 over different covered times. |

### Labels, quality, storage, version, checks (decisions 12 to 16)

| # | Decision | Rejected |
|---|---|---|
| 12 | **Every metric object is `{value, unit, coverage, status}`.** Coverage = covered seconds / `duration_s`. Status `complete` when coverage is at least `COMPLETE_COVERAGE = 0.95`, `partial` below that, `none` exactly when the value is null. Values are always reported when computable; M5 decides comparability. Quality shares have coverage and status null. | None recorded. |
| 13 | **Data quality per signal**, for all 25 declared pairs of every experiment (a pair with no readings is listed with `present` 0): `present` = processed rows (`readings_processed` or `state_intervals`, any verdict), `accepted`, `bad` and `uncertain` (acquisition quality), `expected = floor(duration_s / nominal_s)` for polled signals, null for on-change state signals (the on-change staleness mistake, C-01). `completeness = present / expected`, `valid_fraction = accepted / present`, `bad_fraction`, `uncertain_fraction` (null when the denominator is 0). Experiment level: `completeness = sum(present) / sum(expected)` over polled pairs; the three fractions over all 25 pairs. Counts come from a SQL `GROUP BY` (no `FILTER`). | None recorded. |
| 14 | **Storage.** InfluxDB `metrics_series` in the target raw database (expires with raw, like M3 decision 2): tags `experiment_id`, `metric`, `metrics_version`, `policy_version`; field `value` float; time = the instant. Postgres (migration `0003_experiment_metrics.sql`): `experiment_metrics` (primary key `experiment_id, metrics_version, metric`; foreign key to `experiment`) and `signal_quality` (primary key `experiment_id, metrics_version, source, signal`; foreign key). Both upserted in one transaction per run, so a rerun overwrites identical rows and a failure leaves nothing partial. They outlive raw retention on purpose (small summaries). | One InfluxDB point per experiment at a made-up time (no join to metadata). |
| 15 | **Policy table and version.** All constants of decisions 5 to 12 and 16 sit in one declared mapping in `pipeline/metrics.py` with `METRICS_VERSION = "m4-v1"`; a unit test pins `METRICS_FINGERPRINT` (SHA-256 of its canonical JSON). A changed constant is a new version. | None recorded. |
| 16 | **Plausibility checks per experiment, in the summary:** `efficiency_in_unit_interval` (0 to 1 for `capture_efficiency_mean`), `capture_below_inlet` (`co2_captured_kg` at most `co2_inlet_kg`), `sec_above_floor` (`sec_kwh_per_kg` at least `SEC_FLOOR_KWH_PER_KG = 0.10`, below the minimum work of separating CO2 from air), `energy_agreement` (absolute `energy_relative_difference` at most `ENERGY_AGREEMENT_REL = 0.01`). `passed` is null when the metric is null. Any `false` gives exit 1, outputs still written. Raw-data estimates give 9 to 43 kWh/kg; the report states the numbers, not a finding. | None recorded. |

### How it is run and proven (decisions 17 to 20)

| # | Decision | Rejected |
|---|---|---|
| 17 | **Exit codes:** 0 written and read back; 1 written and read back, a plausibility check failed; 2 refused, nothing written (database missing and never created, `readings_processed` missing or holding no rows for the policy version, experiments file unreadable, Postgres unreachable, migration 0003 not applied, an experiment missing from Postgres `experiment`); 3 a query or write failed; 4 written but read-back counts differ. Outputs are written on 0, 1 and 4, none on 2 and 3. Order: compute everything, write InfluxDB, write Postgres (one transaction), read back, write outputs. | None recorded. |
| 18 | **Expected real-data labels pinned before the real run.** A different label stops the real-data task and comes back as a narrow question; constants are not tuned silently. | None recorded. |
| 19 | **Calibrate before scaling:** EXP_001 first, compared with an independent plain-Python recompute from SELECT pulls (no pipeline imports), then EXP_004 (the air-flow hour), then all six. | None recorded. |
| 20 | **Branch `m4-metrics`, cut from `master`.** Commit and push at the end of M4; merge waits for approval. | None recorded. |

Details: decision 19 puts EXP_004 second on purpose: it holds the excluded air-flow hour (A-07), the
case most likely to expose a wrong coverage rule. Decision 5's "profile found 0 unmatched" is
`instants_unmatched` in `reports/post_ingest_profile.json`.

## Decided at execute

These calls were made while building and running M4. Each can be overturned. Per the working
contract, none reverses an existing decision.

| # | What was decided | Why |
|---|---|---|
| 21 | **The capture-rate row count of the fixture is 269, not 268.** The plan arithmetic was wrong (the planned row count mistake, E-09 in `MISTAKES.md`). | 297 efficiency instants, minus the 28 even seconds from +362 to +418 other than +400; the plan subtracted +400 twice. The planned coverage 532/600 matches 269. Tests, the fixture README and the summary use 269; the plan text and the contract example (illustrative) still say 268. |
| 22 | **`parameters` in the summary is not rounded to 9 digits.** | The gas constant has 10 digits and must equal `POLICY` exactly. The metric values are rounded to 9 significant digits; the parameters are copied as they are. |
| 23 | **`POLICY` has exactly the 10 keys the contract lists.** `KELVIN_OFFSET` (273.15), the hPa to Pa and ppm conversions and the unit scalings are module constants outside the fingerprint. | They are physical facts, not choices. A test reads the schema and compares its keys with `POLICY`. |
| 24 | **The inlet series uses the capture series' instants.** | Both totals then cover the same time, so `capture_below_inlet` compares like with like. |
| 25 | **An efficiency instant with `co2_in` = 0 is skipped.** | The ratio is undefined at 0. The declared limit for CO2 in is 0 to 5000 ppm, so this is a guard and not an expected case. |
| 26 | **Coverage is 0.0 with status `none` when no time is covered.** | A metric object always carries a coverage number; null is used only for the four quality shares. |
| 27 | **The p95 of the absolute residual uses linear interpolation** between order statistics (numpy's default method). | It is numpy's default method, so an independent recompute can match it. |
| 28 | **Fixture noise alternation is applied by reading index for 0.5 Hz and once-a-minute signals** (by second for 1 Hz signals). | Alternating by second would give a constant at the even seconds of a 0.5 Hz signal, and cleaning calls a constant a flatline. |
| 29 | **`.gitattributes` gets `migrations/*.sql -text`.** | `core.autocrlf=true` checked the migration files out with CRLF, and the migration runner (which records a SHA-256 of the file bytes) refused 0001 because the recorded checksum is of the LF bytes. A fresh stack and Linux CI were not affected. The two files were recreated from the index; 0003 was written in LF. |
| 30 | **`plausibility.limit` must be a number in the contract**, so `capture_below_inlet` reports limit 0.0 with `passed` null when the inlet total is null. | A workaround for the contract, noted under Limits. |
| 31 | **The power cross-check threshold was handled as Sebastian decided (2026-11-24): 0.99 is kept, and EXP_001's 0.983 is reported as a cross-check result.** | The planned expectation was "within tolerance at least 0.99 for every experiment". EXP_001 gets 0.983157895 (7,005 of 7,125); the other five get 1.0. The cause is 120 seconds, from 09:23:20 to 09:25:19 on 2026-05-04, where logged power is about 6 kW above voltage times current, all three signals accepted by cleaning. Energy still agrees (0.67 %). No constant and no cleaning rule was changed (E-09). |
| 32 | **The plan said `sec_kwh_per_kg` is complete for EXP_002; the real run gives partial (0.933).** | Its coverage is the overlap of the power covered time (0.9331, because of the 481 to 485 s gap on the hydrolyzer signals) and the capture covered time (0.9997). The expected label in the plan was wrong; no constant changed. |

## Why

The brief says to derive metrics from the stored data and to label a metric computed over
incomplete data. A batch job over accepted readings gives each formula a hand-computed fixture and
an independent recompute, which a dashboard query could not. Reporting a number together with
its coverage keeps two things apart that would otherwise blur: what the rule computes, and how much
of the experiment it rests on. Filling a gap would remove the label's reason to exist. The
integral needs covered time because it adds every reading into one total; a pH or an efficiency mean
is a level at instants and needs no bridging (see `docs/metrics.md` section 8).

## Consequences

- One run takes about 26 seconds and 179 queries on the real data. It wrote 121,167 points to
  `metrics_series` and 228 rows to Postgres (78 metric rows and 150 signal rows). A second run
  gives identical series, rows and summary except `timing`.
- A metric can be `partial`. Real data: EXP_002 power (0.933); capture in EXP_004 (0.50), EXP_005
  (0.75) and EXP_006 (0.36). The reasons are cleaning calls and gaps already recorded in M3: the
  excluded EXP_004 air-flow hour, EXP_005's first 30 UNCERTAIN pressure readings, EXP_006's 1,350
  stuck outlet-CO2 readings and its absorber gap.
- Postgres now holds metrics beside the experiment metadata (a join on `experiment_id`), and they
  outlive raw retention.
- Changing a constant changes the fingerprint test; the version must be bumped; rows for the new
  version sit beside the old ones.

## Limits

- **Assumption A-08.** Capture rate assumes air flow in actual cubic metres per hour at ambient
  conditions and ignores humidity. If the meter reports normal cubic metres, the capture rate and
  everything built on it is off by the ambient-to-standard density ratio, up to about 12 %.
- **One window at a time.** A run holds the accepted series of one experiment (at most 7,200 points
  per series, eight input series). Continuous data needs time-chunking (rest of U-06).
- **`count_series` ignores the policy version.** It counts any `policy_version` for the same
  experiment, metric and metrics version (noted by the storage task). Series of two policy versions
  under one metrics version would be counted together in the read-back.
- **Contract workaround.** `plausibility.limit` is 0.0 where the inlet total is null (decision 30).
- **The cross-check threshold is data-dependent.** EXP_001's 120 s block is a result, not a fault
  the rules can see: all three signals were accepted. It is reported and not filtered (decision 31).
- **Metrics inherit the cleaning calls**, for example the excluded EXP_004 air-flow hour (A-07).

## Assumptions relied on

A-05 (physical limits stand in for instrument spans), A-07 (EXP_004 air flow is a sensor fault),
and the new A-08 (air flow in actual m3/h, humidity ignored). Narrows U-06, the memory question (see `../ASSUMPTIONS.md`).

## Related

ADR-0006 (tables and tags), ADR-0011 (rollup, retention), ADR-0012 (migrations), ADR-0014
(profile, engine quirks), ADR-0015 (verdict, the accepted readings this reads). MISTAKES.md C-01
(on-change signals), E-09 (the planned row count and the planned pass threshold). Formulas and
entries: [`docs/metrics.md`](../metrics.md). Schema: [`docs/schema.md`](../schema.md).

## Defense

"I do not fill holes. A metric is computed from accepted readings only, at the instants where every
input exists, and it is reported with the share of the experiment it covers and a label:
complete, partial or none. Energy is added up only over spacings of at most twice the sampling
interval, so a gap lowers the coverage and never the plausibility of the total. I check the
energy twice, from voltage times current and from the logged power, and I check every formula
against a hand-computed fixture and an independent recompute from plain SELECT pulls: 0 differences
on all six experiments. One cross-check is not clean: on EXP_001, 120 seconds of logged power sit
about 6 kW above voltage times current. I kept the 0.99 threshold, reported 0.983 as a result, and
changed nothing to make it pass. The honest limits are the air-flow assumption, which could move
the capture numbers by up to 12 %, and that three experiments have partial capture coverage
because of cleaning calls I made."
