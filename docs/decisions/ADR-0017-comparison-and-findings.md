# ADR-0017 — Comparison and findings: one clock, block-bootstrap intervals, an evidence rule that can say "not resolved"

Status: Accepted
Milestone: M5   Deliverable: F   Date: 2026-11-24

This is the record of M5. Decisions 1 to 24 were made while planning and approved by Sebastian with
the plan on 2026-11-24. The section "Decided at execute" lists what execute added. The findings
themselves are a separate matter: they are a draft until Sebastian approves them
([`reports/findings.md`](../../reports/findings.md)).

## Context

In plain words: the brief asks for at least three findings, an evidenced answer on how flow and
pressure relate to cell voltage, and a list of comparisons the data cannot support. The data is six
runs of two hours on six different days, one run per condition, with different conditions in most
pairs. So the comparison has to put the runs on one clock, say which pairs may be compared, give an
answer to the flow and pressure question that admits when the data cannot decide, and never present
a difference between two runs as a cause.

Details: M4 stored 13 whole-run metrics per experiment and four derived series (ADR-0016). M5 reads
them and the accepted readings (ADR-0015), fits a voltage model per experiment, builds five
steady-state KPIs with intervals, and compares the experiments pair by pair. The rules, constants
and entries are in [`docs/comparison.md`](../comparison.md); this ADR records why they are what
they are. The 24 decisions below are numbered as in the milestone record. The single-query span
limit of Core (U-05) is respected by reading one experiment window per query: 219 queries, no span
error.

## Decision

Note on the `Rejected` column: where the plan recorded no rejected option, the cell says so. It does
not add one that was not weighed at the time.

### Scope and mode (decisions 1 to 4)

| # | Decision | Rejected |
|---|---|---|
| 1 | **Mode standard, judge verify, six tasks run by agents** (Sebastian asked for parallel agents in separate contexts). Wave 1: pure analysis (T1), reads (T2) and fixture (T3) in parallel; wave 2: command and end-to-end tests (T4); wave 3: real data (T5); wave 4: write-up and draft findings (T6). A bug found by a later task is reported back to the owner, not patched outside the finder's files. | One piece (Sebastian's request); full mode (the milestone is read-only and adds no new risk class). |
| 2 | **M4 accepted as done for starting M5.** Its newest Findings block reviewed the working tree that became the commit merged with Sebastian's approval. | None recorded. |
| 3 | **"Flow and pressure" means the hydrolyzer's electrolyte `flow` (L/min) and `pressure` (bar)** (Sebastian). Same subsystem as the cell voltage, and the data dictionary warns not to mix `flow` with other flows. The absorber's `air_flow` and `pressure_drop` get the same analysis as a second model, so the other reading of the brief is answered too. | Absorber only. |
| 4 | **Read-only.** M5 writes no InfluxDB or Postgres row and creates nothing; its outputs are files. | Storing aligned series now (M6 decides how the overlay works; storing them first is designing ahead). |

### Clock, phases, joins (decisions 5 to 7)

| # | Decision | Rejected |
|---|---|---|
| 5 | **Shared clock: `experiment_time_s = (t - start) / 1e9`**, start = the experiment's `start_time`. Ids and windows `[start, end)` come from the experiments file; metadata comes from Postgres `experiment`. A Postgres start or end that differs from the file refuses the run (exit 2, `window_mismatch`). | Aligning on the first `STEADY_STATE` event (phase offsets would be hidden). |
| 6 | **Phases from accepted `process_state` rows of `state_intervals`:** phase = `[event time, end_ns)`. Analysis window = `[start + settle_s, end)` when not empty. `settle_s = 60`, more than twice the measured 23 to 24 s current-to-setpoint lag. Steady windows are the windows of `STEADY_STATE` phases. | Whole phases (transients leak in). |
| 7 | **Instant join.** Hydrolyzer: the exact same instant of voltage, current, flow and pressure. Absorber: the exact instants of `pressure_drop` (0.5 Hz) where voltage, current and air flow also exist. `electrolyte_temperature` (0.2 Hz) as-of: the latest accepted reading at or before the instant, used when at most `temp_max_age_s = 10` s old. Only instants inside the analysis windows. | Resampling to a grid (invents values). |

### The model and its intervals (decisions 8 to 12)

| # | Decision | Rejected |
|---|---|---|
| 8 | **Voltage model (ordinary least squares):** `voltage ~ 1 + current + electrolyte_temperature + X1 + X2`, hydrolyzer X1, X2 = flow, pressure; absorber air_flow, pressure_drop. Predictors centred, normal equations by Gaussian elimination with partial pivoting, `math.fsum`. Testable at 300 rows or more and no singular pivot. Per term: coefficient, interval, `r2_drop`, `vif`, `plain_corr`, lag fields. Joint `r2_drop` and `separable` (both VIF below 10). When not separable, only the joint effect may be cited. | Plain correlation as the answer (voltage follows current first; it is reported, not concluded from). |
| 9 | **Fits:** each model x window (`steady`, `whole_run`) x scope (each experiment; `pooled` over the testable experiments, one intercept per experiment). | None recorded. |
| 10 | **Block bootstrap.** 120 s blocks inside each analysis window; a resample draws B blocks (B = non-empty blocks) with replacement; 1000 resamples; `random.Random(seed_key)` with `seed_key = "<seed>|<model>|<window>|<scope>"`, seed 20261124; per-block sums computed once. Pooled is stratified (each experiment draws its own blocks). A singular resample is counted and skipped. Interval = type 7 percentiles at 2.5 and 97.5. | Textbook standard errors (1 s readings are autocorrelated, so the intervals would be far too narrow). |
| 11 | **Lag search** for X1 and X2: the residual of the model without that term against the term `k` seconds earlier, `k` = 0 to 60 s; best = largest absolute Pearson, ties to the smaller `k`. | None recorded. |
| 12 | **Evidence rule** per (model, window, term) over the per-experiment fits: `supported` (2 or more testable, all exclude zero, one sign), `single_run`, `inconsistent` (opposite signs), `not_resolved`, `not_testable`. An interval excludes zero when `low > 0` or `high < 0`. The pooled fit is reported beside the status, not used by it. | Judging effect sizes by eye. |

### KPIs, comparability, checks (decisions 13 to 17)

| # | Decision | Rejected |
|---|---|---|
| 13 | **Five steady-state KPIs** per experiment (`voltage_mean_v`, `mean_power_kw`, `capture_rate_mean_kg_h`, `capture_efficiency_mean`, `sec_kwh_per_kg`), each with coverage, label and a block-bootstrap interval; resample value = ratio of summed block parts. Whole-run metrics are the 13 Postgres rows, copied unchanged. | None recorded. |
| 14 | **Comparability for all 15 pairs.** Seven factors measured from accepted readings in the steady windows where possible (and one from metadata): 5 percent on setpoints and flows, 5 degrees Celsius ambient, 15 percentage points humidity, profile and batch by equality; a missing value counts as differing. `same_conditions` (0 differ), `supported` (1), `confounded` (2 or more). The operator is listed beside, not a factor. Per KPI: `b - a` with an interval, and `both_complete`, `partial_coverage` or `not_available`. | Comparing pairs without the factor check. |
| 15 | **One run per condition.** Findings say "in this run" and name the confounders; no causal wording (new assumption A-09). | None recorded. |
| 16 | **Pressure drop against air flow** (the open question from M2.5): per experiment a straight-line and a quadratic fit plus the lag search; across experiments the steady medians and a line through them. Numbers only. | None recorded. |
| 17 | **Air-flow check** for EXP_004 at 09:00Z: medians and counts before and after for raw `air_flow` (from `value_raw`, all rows) and for `fan_speed`, `pressure_drop`, `co2_in_ppm`, `co2_out_ppm` and `capture_efficiency`. Numbers only; they set the status of A-07. | None recorded. |

### Version, findings, proof, housekeeping (decisions 18 to 24)

| # | Decision | Rejected |
|---|---|---|
| 18 | **Policy table and version.** All constants of decisions 6 to 17 in one declared mapping `POLICY` in `pipeline/compare.py`, keys equal to the contract's `parameters`, `COMPARE_VERSION = "m5-v1"`; a unit test pins `COMPARE_FINGERPRINT`. A changed constant is a new version. | None recorded. |
| 19 | **No finding is pinned in a scenario** (the planned row count mistake, E-09 in `MISTAKES.md`, was a number fixed before it was measured). Real-data scenarios pin completeness, the independent recompute and reproducibility. | None recorded. |
| 20 | **Draft findings** in `reports/findings.md`: status line `Status: draft, awaiting Sebastian's approval`; at least three findings, each with claim, command, SQL and numbers; a flow and pressure section (hydrolyzer first); a section on comparisons the data does not support. Every number carries a reference comment into the committed summary, checked by `tests/unit/test_findings_doc.py`. | None recorded. |
| 21 | **Exit codes:** 0 outputs written; 2 refused, nothing written; 3 a query failed. Outputs are written only on 0, at the end. | None recorded. |
| 22 | **Calibrate before scaling:** EXP_001 first against an independent plain-Python recompute (no pipeline imports, the bootstrap re-implemented from decision 10's text), then all six. | None recorded. |
| 23 | **Branch `m5-comparison`, cut from `master`.** Commit and push at the end of M5; merge waits for Sebastian's approval of the findings. | None recorded. |
| 24 | **Housekeeping:** three M4 scenarios reworded to what the build gives and Sebastian ruled; one example number in the M4 contract example corrected. No code change. | None recorded. |

Details: decision 3 means the headline answer has two parts, and the hydrolyzer part comes first.
Decision 12 is the reason the answer can be "not resolved": the rule needs agreement between
experiments, and with one run per condition and wide intervals it does not get it. Decision 19 is
why [`reports/findings.md`](../../reports/findings.md) was written after the numbers existed, and
why its numbers are checked against the summary and not typed in.

## Decided at execute

These calls were made while building and running M5. Each can be overturned. Per the working
contract, none reverses an existing decision, but the first (the KPI instants) changes a number
slightly, and the findings are a headline claim, so they wait for Sebastian's approval.

| # | What was decided | Why |
|---|---|---|
| 25 | **Steady KPI series are restricted to instants inside the steady windows.** Reading decision 13 literally (covered intervals of the whole series, then clipped) bridges the last second of each window with the first reading of the next phase. The restricted reading is used. | Keeps transient readings out of the steady KPIs. The test fixture's coverage is 838 of 840 seconds instead of 840 of 840 and `mean_power_kw` is 12.1090 kW instead of 12.1106; on real data the effect is about 1 s per window edge (about 0.2 percent). The hand computation and the scenario pin 838 of 840. |
| 26 | **A covered pair or segment is split at the 120 s block boundaries.** | Each block contributes its own partial sums (decision 13), so a pair that crosses a boundary is cut there. Affects only the capture-rate and energy-per-kilogram intervals. The independent recompute reads it the same way (an ambiguity resolved by following the code's reading). |
| 27 | **The singular test is on the centred cross-product matrix, not on a scaled one.** A pivot at or below `PIVOT_REL = 1e-9` times the largest diagonal entry makes a fit singular. | The simplest rule that fits the specification. Not scale-free: a predictor measured in tiny units could look singular next to one in large units. Not seen on this data (all 28 real fits testable, 0 singular resamples of 1000 in each). |
| 28 | **The pooled scope uses only the experiments that are testable on their own.** `plain_corr` is taken over all pooled rows. | A pooled fit that included a fit which cannot be made alone would hide the reason. On the real data all six are testable. |
| 29 | **A flat voltage is not testable.** | A correlation or a line through a constant is not defined. |
| 30 | **Empty blocks are left out of the draw.** B is the number of non-empty blocks. | An empty block has no rows to draw; B counts the non-empty blocks, as decision 10 says. |
| 31 | **Refusal reasons (exit 2):** `database_missing`, `no_cleaned_readings`, `no_metrics_rows`, `experiments_unreadable`, `postgres_not_configured`, `postgres_unreachable`, `postgres_not_migrated`, `experiment_missing_in_postgres`, `window_mismatch`, `experiment_metrics_missing` (any of the 13 names missing), and `influx_*` for a failed start. A plain read on a missing database fails as a query, so the command checks first (`require_database()`) and never creates one. | Each reason names one thing to fix. Nothing is written on a refusal. |
| 32 | **The absorber fits are not testable on the test fixture, by construction.** The fixture's noise rule makes current and air flow constant at the 0.5 Hz pressure-drop instants, so the absorber normal matrix is singular. The absorber path is covered by unit tests in `tests/unit/test_compare.py`, not by the fixture's end-to-end run. | A known limit of the fixture, found at its build and left as it is (changing it is a plan matter). On the real data the absorber fits are all testable. |
| 33 | **For the pressure-drop lag search the "residual" is the pressure drop itself.** | The pressure-drop fit has one predictor and no model without it; the lag is searched on the series, as the specification's wording allows. |
| 34 | **The findings reference rule.** A written number equals the referenced value rounded half away from zero to the digits written; scientific notation uses `format(value, '.Ne')`; a number followed by ` %` equals the value times 100; a decimal number with no reference fails the test. | One rule, in `tests/unit/test_findings_doc.py`, that a reviewer can read in a minute. A number typed by hand cannot drift from the summary unnoticed. |

## Consequences

What this makes easy: rerunning the comparison gives the same numbers (fixed seed, same order);
every number in the findings can be traced to a summary field; a pair of experiments is either
comparable or named as not. What it makes hard: with one run per condition, the answer to the
brief's flow and pressure question is "not resolved in this run", which is honest and less
satisfying. What it forecloses: any causal statement. Replicate runs per condition are the only way
to turn "in this run" into a claim about a condition.

## Assumptions relied on

A-07 (EXP_004 air flow hour is a sensor fault; its status is updated from the air-flow check), A-08
(air flow is actual m3/h; the capture KPIs inherit it), A-09 (one run per condition) and U-05 (one
query per experiment window; still open for the Grafana time picker). See
[`../ASSUMPTIONS.md`](../ASSUMPTIONS.md).

## Defense

When asked "so what does flow do to voltage": "In this run the data cannot say. I fitted voltage on
current, temperature, flow and pressure in every experiment, with intervals that allow for
autocorrelation, and the flow and pressure intervals include zero in all six. That is not evidence
of no effect; it is not enough data to see one." When asked why not just correlate: voltage follows
current first, and flow follows current through the load changes, so a plain correlation would
credit flow with current's effect. When asked about the intervals: they come from resampling
2-minute blocks of the run's own readings, so they show noise inside one run and nothing about
day-to-day spread, which is why every claim says "in this run".
