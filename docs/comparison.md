# Experiment comparison: how the numbers are made, and what they cannot say

Compare version `m5-v1`, built from accepted readings of cleaning policy `m3-v1` and metrics
version `m4-v1`. Decisions and rejected options:
[ADR-0017](decisions/ADR-0017-comparison-and-findings.md). The numbers live in
[`pipeline/compare.py`](../pipeline/compare.py); a unit test (`tests/unit/test_comparison_doc.py`)
reads the tables below and fails if a parameter, a unit, a factor or a status differs from that
file.

## In short

The comparison puts the six experiments on one clock, fits a small model of cell voltage, compares
experiments only when their conditions allow it, and says "not resolved" when the data cannot
decide. It reads accepted readings only and writes files, not database rows. Every interval comes
from resampling blocks of the experiment's own readings, so it shows the noise inside one run. It
does not show the spread between days.

Details: the command is `python -m scripts.compare`. It reads `readings_processed`,
`state_intervals` and `metrics_series` from InfluxDB and `experiment` and `experiment_metrics`
from Postgres, one experiment window at a time. It writes `reports/comparison_summary.json`
(contract `contracts/comparison_summary.schema.json`) and `reports/comparison_report.md`, and only
when everything succeeded. Fingerprint of the parameter table: it begins `a0274e7e`
(`COMPARE_FINGERPRINT`, the SHA-256 of the canonical JSON of the 14 parameters). Draft findings
built on these numbers: [`reports/findings.md`](../reports/findings.md).

## 1. The parameters

Every number the rules read is one of these 14, in one declared table (`POLICY`). A changed number
is a new compare version, and a test fails if one changes without it. The meaning column says what
the number controls.

| Parameter | Value | Meaning |
|---|---|---|
| `settle_s` | 60 | Seconds skipped at the start of each phase before its readings count. More than twice the 23 to 24 s lag between a current setpoint and the current. |
| `bootstrap_block_s` | 120 | Length of one resampling block, in seconds. |
| `bootstrap_resamples` | 1000 | How many resamples one interval is made from. |
| `bootstrap_seed` | 20261124 | Seed of the random generator, so a rerun gives the same numbers. |
| `interval_level` | 0.95 | The intervals cover 95 percent of the resampled values. |
| `lag_max_s` | 60 | Longest lag tried in the lag search, in seconds. |
| `temp_max_age_s` | 10 | An electrolyte temperature reading is used at an instant when it is at most this old (2 x the 5 s nominal spacing). |
| `min_instants` | 300 | A fit needs at least this many rows to be testable. Also the least number of pairs a lag needs. |
| `vif_limit` | 10 | Two terms are separable when both variance inflation factors are below this. |
| `condition_tol_rel` | 0.05 | Two relative conditions differ when they are more than this fraction apart. |
| `ambient_tol_c` | 5 | Two ambient temperatures differ when they are more than this many degrees Celsius apart. |
| `humidity_tol_pct` | 15 | Two relative humidities differ when they are more than this many percentage points apart. |
| `airflow_check_experiment` | EXP_004 | The experiment whose air-flow hour is checked. |
| `airflow_check_boundary` | 2026-03-02T09:00:00Z | The instant that splits that experiment into before and after. |

Details: one more number is fixed in the code and is not a choice that changes results between
experiments. A fit is singular when a pivot of the elimination is at or below this fraction of the
largest diagonal entry of the centred cross-product matrix. It is not part of the fingerprint.

| Constant | Value | Meaning |
|---|---|---|
| `PIVOT_REL` | 1e-9 | Singular-fit limit (relative to the largest diagonal entry). |

## 2. One clock, and phases

Every instant is placed on the experiment's own clock: seconds since its `start_time`. The six
runs start on different days, so this is what lets them be set side by side. The phases of the
process (startup, steady state, load change, shutdown) are kept separate, and only the steady
state is used for the main results.

Details: `experiment_time_s = (t - start) / 1e9` with `t` in nanoseconds. The experiment window is
`[start, end)` from the experiments file. If Postgres holds a different start or end for an
experiment, the run refuses (exit 2, `window_mismatch`). A phase is
`[event time, end of the interval)` taken from the accepted `process_state` rows of
`state_intervals`. The analysis window of a phase is `[phase start + settle_s, phase end)` when that
is not empty, otherwise none (EXP_005 has several phases shorter than the settle margin). The
steady windows are the analysis windows of the `STEADY_STATE` phases. The whole-run window is the
whole experiment. Rejected: aligning every experiment on its first steady-state event (the phase
offsets would be hidden).

## 3. Which readings are joined

| Model | Instants | Rule |
|---|---|---|
| Hydrolyzer | The 1 Hz instants of voltage, current, flow and pressure. | Join on the exact same instant. |
| Absorber | The 0.5 Hz instants of `pressure_drop`. | Join on the exact same instant where voltage, current and air flow also exist. |
| Electrolyte temperature (0.2 Hz) | As-of. | The latest accepted reading at or before the instant, used when it is at most `temp_max_age_s` old. |

Details: only instants inside the analysis windows count. The as-of rule is the one of the
metrics step (`pipeline.metrics.as_of`). Rejected: resampling onto a grid (it invents values).

## 4. The two voltage models

For each experiment the model is `voltage ~ 1 + current + electrolyte_temperature + X1 + X2`,
fitted by ordinary least squares. For the hydrolyzer X1 and X2 are electrolyte flow and pressure.
For the absorber they are air flow and pressure drop. Current and electrolyte temperature are in
the same regression, so the flow and pressure terms are what is left after the voltage's
dependence on those two is taken out.

| Model | Predictors, in order |
|---|---|
| `hydrolyzer` | current, electrolyte_temperature, flow, pressure |
| `absorber` | current, electrolyte_temperature, air_flow, pressure_drop |

| Predictor | Unit |
|---|---|
| `current` | A |
| `electrolyte_temperature` | °C |
| `flow` | L/min |
| `pressure` | bar |
| `air_flow` | m³/h |
| `pressure_drop` | mbar |

Details: each fit is made for two windows (`steady`, `whole_run`) and for each experiment and a
`pooled` scope. The pooled fit uses only the experiments that are testable on their own, with one
intercept per experiment instead of a common one. Predictors are centred at the fit's own means
and the normal equations are solved by Gaussian elimination with partial pivoting; sums use
`math.fsum`. A fit is testable when it has at least `min_instants` rows and no pivot is at or
below `PIVOT_REL` times the largest diagonal entry. A flat voltage is also not testable. Per term
the summary holds: the coefficient (volts per unit), its interval, `r2_drop` (the model's R squared
minus the R squared without that term), `vif` (the variance inflation factor, 1 divided by 1 minus
the R squared of the term on the other predictors), `plain_corr` (the plain correlation with the
voltage, reported but never concluded from), and, for X1 and X2, the lag fields. The joint entry
gives the `r2_drop` without X1 and X2 together, and `separable`: both VIF below `vif_limit`. When
the two are not separable, only their joint effect may be cited. Rejected: judging by the plain
correlation (voltage follows current first).

## 5. The block bootstrap

Readings at 1 s are not independent of the neighbours, so textbook standard errors would be far
too narrow. Instead the readings are cut into 120 s blocks, blocks are drawn with replacement, the
model is refitted, and this is repeated 1000 times. The 2.5th and 97.5th percentiles of the
coefficient are the interval.

Details: within each analysis window, block `k` holds the rows with
`floor((t - window start) / bootstrap_block_s) = k`. A resample draws B blocks with replacement,
where B is the number of non-empty blocks (empty blocks are left out of the draw). The generator is
`random.Random(seed_key)` with `seed_key = "<bootstrap_seed>|<model>|<window>|<scope>"`. Each
block's sums of cross-products are computed once and added per resample, using the centring
constants of the full fit. The pooled scope draws each experiment's own blocks (stratified), in id
order, from one generator. A singular resample is counted (`resamples_singular`) and skipped. The
interval is the type 7 percentile (linear interpolation between order statistics) at
`(1 - interval_level) / 2` and `(1 + interval_level) / 2`. The bootstrap assumes blocks are close
to independent. If the residuals are correlated across blocks, the intervals are too narrow (see
section 12).

## 6. The lag search

A change in flow or pressure might act on the voltage a little later. For X1 and X2 the search
takes the residual of the model without that term and correlates it with the term's value `k`
seconds earlier, for `k` from 0 to `lag_max_s`. The best lag has the largest absolute correlation.

Details: a `k` with fewer than `min_instants` pairs is skipped; ties go to the smaller `k`. Reported:
`best_lag_s`, `corr_at_best_lag`, `corr_at_zero`. Picking the best of 61 candidates always finds
some lag, so a best lag is a number to look at, not a finding. For the pressure-drop fit
(section 10) the "residual" is the pressure drop itself.

## 7. The evidence rule

For each model, window and term, the per-experiment intervals are read together. An interval
excludes zero when its low end is above 0 or its high end is below 0 (an end of exactly 0 does not
exclude it). The status says how many experiments agree.

| Evidence status | Rule |
|---|---|
| `supported` | At least 2 testable fits, all exclude zero, all with the same sign. |
| `single_run` | Exactly 1 testable fit, and it excludes zero. |
| `inconsistent` | Two testable fits exclude zero with opposite signs. |
| `not_resolved` | Any other case with at least 1 testable fit. |
| `not_testable` | No testable fit. |

Details: the pooled fit is reported next to the status and is not used by it. `sign` is set for
`supported` and `single_run` only. Rejected: judging effect sizes by eye.

## 8. Factors and comparability

Two experiments can be compared when they differ in at most one condition that matters. Each of
seven factors is measured and checked.

| Factor | Differs when |
|---|---|
| `current_setpoint` | The medians in the steady windows are more than `condition_tol_rel` of the larger apart. |
| `current_setpoint_profile` | One is `varying` and the other `constant`. A setpoint is `varying` when its 5th to 95th percentile spread is more than `condition_tol_rel` of its median. |
| `air_flow` | The medians are more than `condition_tol_rel` of the larger apart. |
| `solvent_flow` | The medians are more than `condition_tol_rel` of the larger apart. |
| `ambient_temperature` | The medians are more than `ambient_tol_c` degrees Celsius apart. |
| `relative_humidity` | The medians are more than `humidity_tol_pct` percentage points apart. |
| `sorbent_batch` | The recorded batches are not equal. |

| Conditions status | Rule |
|---|---|
| `same_conditions` | No factor differs. |
| `supported` | Exactly one factor differs. |
| `confounded` | Two or more factors differ. |

Details: a missing value (a null batch, no readings) makes `differs` null, and a null counts as
differing. Each pair lists the differing factors and, beside them, `recorded_differences`: the
operator, which is listed but not a factor (setpoints are automated). All 15 pairs (a before b by
id) are covered. The tolerances are judgement, not calibration, so the measured condition values
are reported beside each factor and a reader can disagree.

## 9. The steady-state KPIs

For each experiment five numbers are made over the steady windows only. Each has a value, a unit,
a coverage (the share of the steady seconds it rests on), a label and a 95 percent interval from
the same block layout as section 5.

| KPI | Unit | What it is |
|---|---|---|
| `voltage_mean_v` | V | Mean of the accepted voltage instants. |
| `mean_power_kw` | kW | The trapezoid integral of `power_computed` over covered seconds, divided by covered seconds. |
| `capture_rate_mean_kg_h` | kg/h | The same for `capture_rate`. |
| `capture_efficiency_mean` | fraction | Plain mean of `capture_efficiency` at instants in the steady windows. |
| `sec_kwh_per_kg` | kWh/kg | Energy of `power_computed` over the time both power and capture are covered, divided by the CO2 captured over that time. |

Details: covered intervals use the M4 spacing limits (2 s for voltage and power, 4 s for capture and
efficiency). Coverage is covered steady seconds divided by steady seconds, and the label is the one
of the metrics step (`complete`, `partial`, `none`). An interval comes from resampling blocks, each
block contributing its partial sums, and a resample value is the ratio of the summed parts. The
comparison of two experiments takes `difference = b - a` and the interval of the element-wise
differences of the two resample arrays.

| Coverage status | Rule |
|---|---|
| `both_complete` | Both KPI values are complete. |
| `partial_coverage` | Both have a value, and one or both are partial. |
| `not_available` | Either value is null. The difference and its interval are null. |

The whole-run metrics next to the KPIs are the 13 rows of Postgres `experiment_metrics`, copied
unchanged.

## 10. The pressure-drop check and the air-flow check

Two small checks answer questions left open earlier.

- **Pressure drop against air flow.** The data dictionary says the pressure drop scales with air
  flow. Within one experiment, over the steady windows, `pressure_drop ~ air_flow` and
  `pressure_drop ~ air_flow²` are fitted (slope, intercept, R squared), with the lag search of
  section 6. Across experiments, the steady medians of the two are put on a line (slope, R squared).
  Numbers only; a reader decides what they mean. Only two air-flow levels exist, so the across line
  rests on one contrast.
- **The air-flow hour of EXP_004.** The median and the count of the raw `air_flow` (every row,
  because cleaning excluded the second hour), and of `fan_speed`, `pressure_drop`, `co2_in_ppm`,
  `co2_out_ppm` and `capture_efficiency`, before and after `airflow_check_boundary` inside the
  window of `airflow_check_experiment`. The relative change is (after - before) / before. It is
  null when that experiment is not in the run.

## 11. Reading choices made at build

These calls were made while building. Each can be overturned (ADR-0017, "Decided at execute").

| Choice | Effect |
|---|---|
| Steady KPIs use only instants inside the steady windows. Reading the plan literally (covered intervals of the whole series, then clipped) bridges the last second of each window with the first reading of the next phase. | Coverage on the test fixture is 838 of 840 seconds instead of 840 of 840, and about 1 s per window edge (about 0.2 percent) on real data. Transient readings stay out. |
| A covered pair or segment is split at the 120 s block boundaries. | Affects only the capture-rate and energy-per-kilogram intervals. |
| The pooled fit uses only the experiments that are testable on their own. | A pooled scope never includes a fit that could not be made alone. |
| The singular test is on the centred cross-product matrix, not on a scaled one. | A predictor with a tiny scale next to the others is judged against the largest diagonal entry, not against itself. |
| A flat voltage is not testable. | A correlation or a line through a constant is not defined. |
| Empty blocks are left out of the draw. | B is the number of non-empty blocks. |

## 12. What the data cannot support, and why

| Cannot be said | Why |
|---|---|
| That a condition caused a difference between two runs. | One run per condition. A difference cannot be separated from day-to-day variation, sorbent batch or operator. Findings say "in this run". |
| Anything about the pairs marked `confounded`. | Two or more factors differ, so a gap cannot be assigned to one. |
| An effect of flow or pressure from a whole-run fit. | Flow follows current through the load changes, so the two are not separable (VIF above the limit). |
| An effect read from a result with `not_resolved`. | The intervals include zero or the experiments disagree. That is not evidence of no effect. |
| Tight intervals for an experiment with correlated residuals. | The bootstrap assumes blocks are nearly independent. EXP_005's residuals are strongly correlated between blocks, so its intervals are probably too narrow. |
| A precise value for a KPI with `partial` status. | It rests on a smaller part of the experiment. |
| A pressure-drop law from the across-experiment line. | Two air-flow levels only. |
| A second opinion on the air-flow sensor fault. | One instrument. The check supports the assumption, it does not close it. |

## 13. How to read the outputs

| File | What it holds |
|---|---|
| `reports/comparison_summary.json` | Every number: parameters, experiments (phases, conditions, KPIs, whole-run metrics), `voltage_models`, `voltage_evidence`, `comparisons`, `pressure_drop_check`, `airflow_check`, `timing`. |
| `reports/comparison_report.md` | The same numbers as tables, one section per experiment, then the models. |
| `reports/findings.md` | The draft findings. Each number carries a reference into the summary, checked by a test. |

Exit codes: 0 outputs written; 2 refused, nothing written (database missing and never created, no
cleaned readings or no metrics rows for the versions, experiments file unreadable, Postgres
unreachable or not migrated, an experiment missing in Postgres or without its metrics rows,
`window_mismatch`); 3 a query failed. Outputs are written at the end, and only on 0. The command
changes no database row.

Details: the real run is 6 experiments, 28 fits, 8 evidence rows, 15 comparisons and 219 queries
(about 53 s). The numbers are in the summary; this document states the rules, not the results.
