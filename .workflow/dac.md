# Task: dac

<!-- Spec: written by /flow:plan. Findings: appended by /flow:verify or /flow:verify-codex.
     The author's notes live in dac.log.md (execute, clean, harden, qa), never opened by the verifier.
     Keep it compact: link sources, don't copy them.
     Milestone ids follow docs/ROADMAP.md exactly. -->

## Spec

### Sources
- `task/TASK.md` (A–J), `task/DATA_DICTIONARY.md`, `docs/ROADMAP.md` (milestone board, ids)
- M2: `docs/discuss/M2.md`; ADR-0006, ADR-0007, ADR-0011; `reports/pre_ingest_census.md`
- Open questions closed by M2: U-01, U-02, U-07, U-08, U-11 (`docs/ASSUMPTIONS.md`)
- M2.5: `docs/ROADMAP.md` § M2.5; ADR-0010 (what to measure, where); ADR-0004 and U-05 (query span); `task/DATA_DICTIONARY.md` (nominal rates, typical ranges); MISTAKES.md C-01, C-02
- M3: `docs/ROADMAP.md` § M3; `task/TASK.md` C, D; ADR-0006 (U-09, U-10), ADR-0011 (rollup over the verdict, UNCERTAIN as BAD, U-04), ADR-0013 (conflicts table, empty values), ADR-0014 and `reports/post_ingest_profile.json` (the measured facts the rules are calibrated on); U-06, U-12; MISTAKES.md C-01, C-02, C-03; approved plan `C:\Users\sebas\.claude\plans\glittery-splashing-nebula-of-6edcf82e-3517-4393-95bf-5335ed2e2c92.md`
- M4: `docs/ROADMAP.md` § M4; `task/TASK.md` E; `task/DATA_DICTIONARY.md` (units, nominal rates, the power note); ADR-0005 (Postgres for metadata, Grafana reaches it by variable), ADR-0011 (tiers), ADR-0015 and `docs/cleaning_policy.md` (the verdict M4 consumes, the alignment rule it promised: polled signals as-of within 2 × nominal); `reports/cleaning_summary.json` and `reports/post_ingest_profile.json` (measured gaps, exclusions, shared instants); MISTAKES.md C-01, E-04, E-06; approved plan `C:\Users\sebas\.claude\plans\nested-twirling-book-of-20e84ac6-0afe-4726-bfcc-f29c4a1074b7.md`
- M5: `docs/ROADMAP.md` § M5; `task/TASK.md` F; `task/DATA_DICTIONARY.md` (process phases, the flow/solvent_flow note); ADR-0005 (metadata in Postgres), ADR-0012 (corrections live in Postgres), ADR-0015 and `docs/cleaning_policy.md` (accepted readings, state intervals with no expiry), ADR-0016 and `docs/metrics.md` (`metrics_series`, `experiment_metrics`, the integration and coverage rules M5 reuses); `reports/post_ingest_profile.json` (current lags setpoint by 23–24 s; pressure drop vs air flow R² < 0.17), `reports/metrics_summary.json`; A-07, U-05; MISTAKES.md E-09; approved plan `C:\Users\sebas\.claude\plans\frolicking-gliding-mango-of-945a74fa-e04e-4ece-aa19-1bfea04e10ae.md`

### Goal
Build everything in `task/TASK.md` A–J, one roadmap milestone at a time. Current milestone, M5:
put the six experiments on a shared clock (seconds since start), split each into its process
phases, answer with evidence how hydrolyzer flow and pressure relate to cell voltage at fixed
current and temperature, say which experiment pairs can fairly be compared and which cannot, and
draft at least three findings for Sebastian's approval. Read-only; outputs are files.
M4 (built, merged): compute power, energy, capture efficiency, capture rate, energy per kg CO2 and
data-quality shares per experiment from accepted readings only, label each number with its
coverage, store time series in InfluxDB and experiment numbers in Postgres, and cross-check power
and energy independently.
M3 (built, merged): decide for every stored reading whether it can be trusted, write raw value, processed value, flag,
decision and reason side by side, record gaps and stuck stretches as intervals, rebuild the rollup
over that decision, and prove by counts that nothing was dropped or quietly changed.
M2.5 (built): measure the stored data and write the numbers to a file, without judging any reading.
M2 (built): copy the raw CSV into InfluxDB without losing or quietly changing anything, and prove it with counts.
- Scope (M5): comparison command `scripts.compare`, pure analysis functions with a versioned policy table, read layer over InfluxDB and Postgres, summary contract, hand-built three-experiment fixture with a planted voltage relationship, real run with committed outputs, independent recompute, draft findings with a findings-vs-summary regression test, `docs/comparison.md`, ADR-0017, M5 report.
- Non-goals (M5): writing any InfluxDB or Postgres row (aligned series or results for Grafana are M6's call); new cleaning rules or metric formulas; filling any input; causal claims (one run per condition); the dashboard (M6); fixing the M4 read-back count (Next steps).
- Scope (M4): metrics command `scripts.metrics`, pure metric functions with a versioned policy table, InfluxDB table `metrics_series` in `dac_raw`, Postgres migration 0003 (`experiment_metrics`, `signal_quality`), summary contract, hand-built fixture with hand-computed answers, real run with committed outputs, `docs/metrics.md`, ADR-0016, M4 report.
- Non-goals (M4): `experiment_time` alignment, process-phase segmentation, cross-experiment comparison and findings (M5); dashboard (M6); rolling up the derived series; changing any raw or processed table or the cleaning rules; filling any input; time-chunked processing for continuous data; scheduling (H).
- Scope (M3): cleaning command, three processed tables in `dac_raw`, summary contract, rollup command over the verdict, policy document, hand-built fixture, real run with committed outputs, ADR-0015, M3 report.
- Non-goals (M3): changing any raw value or raw table; cross-signal exclusion rules (M4 does the power cross-check); alignment to a common time grid (M4); time-chunked processing for continuous data; scheduling, plugins (H); dashboard (M6).
- Scope (M2): private test stack, ingest command, rejects file, conflicts table, summary + report, CI fixture test, full real run, M2 report.
- Non-goals (M2): cleaning or judging values (M3); profiling (M2.5); cross-run duplicate detection; parallel ingest.
- Scope (M2.5): profiling command, output contract, hand-built fixture with planted defects, real profile committed, ADR-0014, M2.5 report.
- Non-goals (M2.5): any verdict, threshold-as-rule or cleaning (M3); outlier detection; cross-experiment comparison (M5); Grafana span question (M6).
- Time budget: untimed (ROADMAP scope line).

### Mode and lanes
- Mode: standard
- Fix rounds: 2
- Test paths: `tests/**`
- QA path: none
- Contract path: `contracts/**`

### Baseline
- Revision: `1c5b6eaa689ccdb768059bc54ed67a5021e5ce08` (branch `m1-data-model`)
- Pre-existing changes: ` M CLAUDE.md`, ` M docs/ROADMAP.md`, `?? docs/discuss/M2.md`
- M2.5 baseline: `77b851678fc9b1cc901df21ad0cb1277c7e4f30e` (branch `m2-ingestion`), clean
- M3 baseline (planning, 2026-11-23): `77b851678fc9b1cc901df21ad0cb1277c7e4f30e` on branch `m2.5-profiling`, with all of M2.5 uncommitted: ` M .github/workflows/ci.yml`, ` M .gitignore`, ` M .workflow/dac.log.md`, ` M .workflow/dac.md`, ` M docs/ASSUMPTIONS.md`, ` M docs/ROADMAP.md`, ` M docs/decisions/README.md`, ` M pipeline/signals.py`, `?? contracts/examples/post_ingest_profile.example.json`, `?? contracts/post_ingest_profile.schema.json`, `?? docs/decisions/ADR-0014-post-ingest-profiling.md`, `?? pipeline/profiling.py`, `?? pipeline/profiling_sql.py`, `?? reports/M2.5.md`, `?? reports/post_ingest_profile.json`, `?? reports/post_ingest_profile.md`, `?? scripts/post_ingest_profile.py`, `?? tests/e2e/test_profile_cli.py`, `?? tests/fixtures/profile/`, `?? tests/unit/test_profiling.py`. M3 execute starts from the M2.5 commit, on a new branch `m3-cleaning`.
- M4 baseline (planning, 2026-11-24): `a7bade12486f58fabf3ee5fede4fd67d6b22cee7` on `master` (the M3 merge), clean. M4 execute starts on a new branch `m4-metrics` cut from it; the first commit carries this record and the M4 contract files.
- M5 baseline (planning, 2026-11-24): `262fb1fd0124e4da1d158933139f23aca781911c` on `master` (the M4 merge). Pre-existing: `?? docs/project-overview.html` (not M5's; leave it uncommitted). M5 execute starts on a new branch `m5-comparison` cut from it; the first commit carries this record and the M5 contract files.

### Constraints
- Milestone ids follow `docs/ROADMAP.md`. Only `/flow:plan <id>` details a milestone.
- InfluxDB `3.11.2-core`, `influxdb3-python==0.21.0`, Python 3.14, native Windows plus Linux CI.
- Raw CSV read-only; its committed SHA-256 must match after every run.
- No ingest time, run id or file-order logic in any point (ADR-0007).
- `generator/` untouched. Core allows 5 databases; test databases must be dropped.
- Working contract in `CLAUDE.md`: major decisions need Sebastian's approval; one report per milestone.
- M2.5 is read-only against InfluxDB: no write, no database created, no change to `dac_raw`.
- Profile outputs carry no verdict words (C-02): `grep -inE "stuck|suspicious|anomal|outlier|invalid|corrupt|error|wrong|fail|noise"` finds nothing in them.
- M3 never writes `readings_numeric`, `readings_state` or `readings_conflicts`, and never creates a database. It writes only `readings_processed`, `state_intervals`, `quality_intervals` (in the target raw database) and `readings_rollup` (in the rollup database).
- M3 SQL avoids the Core 3.11.2 quirks in ADR-0014: no `COUNT(*) FILTER` after a window function, no `PERCENTILE_CONT`, no equality on `-0.0`, no reliance on last-bit-stable server sums. The rules themselves run in Python on pulled series.
- The verdict-word ban (C-02) applied to M2.5 outputs only. M3 is where verdicts live, so its reason codes are verdicts on purpose.
- M4 never writes `readings_numeric`, `readings_state`, `readings_conflicts`, `readings_processed`, `state_intervals`, `quality_intervals` or `dac_rollup`, and never creates a database. In InfluxDB it writes only `metrics_series` (target raw database); in Postgres only `experiment_metrics` and `signal_quality`. It never changes the `experiment` table.
- M4 reads only rows with `verdict = 'accepted'` for one cleaning `policy_version` as metric inputs; it reads counts of all rows for the quality shares. Same Core 3.11.2 SQL quirks to avoid as M3 (ADR-0014); integrals and sums are done in Python with `math.fsum`.
- M4 outputs are not findings. Comparisons between experiments and the flow/pressure-vs-voltage answer are M5 and need Sebastian's approval (CLAUDE.md).
- M5 writes nothing to InfluxDB or Postgres and creates no database or schema. It reads `readings_processed` (accepted rows, plus `value_raw` for the air-flow check), `state_intervals` and `metrics_series` of one cleaning `policy_version` (and, for `metrics_series`, one `metrics_version`), and Postgres `experiment` and `experiment_metrics`. Every InfluxDB query is bounded to one experiment window (U-05).
- M5 analysis is stdlib Python (`math.fsum`, `random.Random`, no numpy), like M3 and M4; it may import `pipeline.metrics` for `as_of`, `covered_intervals`, `overlap`, `integrate_over`, `status_for` and `POLICY`, and must not change that module.
- M5 findings are a draft until Sebastian approves them (CLAUDE.md, headline claims). `reports/findings.md` says so in its status line; the merge to `master` waits for that approval.

### Decisions
- M0, M1 accepted as done under the old method (Sebastian, 2026-11-23).
- M2: the nine in `docs/discuss/M2.md` (D1–D9), plus these, made while planning (2026-11-23):

  1. **Ingest never creates a database.** Writing to a missing one auto-creates it with no retention and uses one of Core's 5 slots. Rejected: let the write create it.
  2. **Count back one experiment at a time**, between the first and last instant ingest saw for it (~2 h each), far under Core's ~72 h single-query limit. Rejected: one count over March–June.
  3. **"Exact copy" means same value and same quality.** Same value with a different flag loses the flag, so it is a conflict (`quality_differs`). Rejected: value only.
  4. **Conflicts table: one row per discarded reading**, with a small tag `discard_rank`, so a group of 3 can't overwrite its own record. Today all 25 groups are pairs. Rejected: one row per instant.
  5. **Text tiebreak is byte (alphabetical) order; a present value beats an empty one.** Content-only, like "smaller number wins". Rejected: file order.
  6. **An empty value is saved as a point with no value**, not rejected. "Row with no value" and "no row" are different defects (C-03); M3 needs to see the first. Today there are 0.
  7. **Three more reject reasons**: `bad_quality`, `unknown_experiment`, `malformed_row`. The win rule needs a known flag; the window check needs a known experiment.
  8. **A reading outside its experiment window is saved, counted, and makes the run exit 1.** Dropping it would be a cleaning call. Window = start inclusive, end exclusive, which matches all measured data.
  9. **Experiment windows come from `data/raw/experiments.json`**, as the retention guard in `scripts/init_influx.py` already does, so ingest needs only InfluxDB. Rejected: read Postgres.
  10. **Exit codes**: 0 clean; 1 finished with findings; 2 refused, nothing written; 3 write failed after retries; 4 counts don't balance.
  11. **Retry only connection errors and server 5xx** (3 retries, 1/2/4 s). A refused line (4xx) fails at once; resending can't help.
  12. **If the Python client can't switch off partial accept**, ingest posts to `/api/v3/write_lp?accept_partial=false` itself. A real test decides.
  13. **Fixture line endings pinned** (`.gitattributes`), so its checksum matches on Windows and the Linux CI runner.
  14. **Private stack script in Python** (runs on Windows and CI). Compose container names become overridable; dev defaults stay `dac-influxdb` / `dac-postgres`.
  15. **Flagged:** conflicts fields are `value_kept_raw` / `value_discarded_raw` (text), where ADR-0007 sketched `value_kept` / `value_discarded` (float). ADR-0007 left this open, so it is an addendum, not a reversal.
  16. **Flagged:** M2 goes on a new branch `m2-ingestion`, cut from `m1-data-model` (not yet merged). The three uncommitted files (CLAUDE.md, ROADMAP.md, discuss/M2.md) become its first commit.
  17. **M0 and M1 count as done** although they have no flow Findings block: they were verified under the old method, with evidence in `docs/ROADMAP.md`. Accepted by Sebastian.
- M2.5, made while planning (2026-11-23); plan approved by Sebastian:

  1. **Mode standard, judge verify, one piece (no tasks).** About 6 files, tightly coupled. Rejected: full mode (read-only, low risk); parallel tasks.
  2. **Every profiling query is bounded to one experiment's window** `[start, end)` from `experiments.json` (2 h each). Rejected: one query over March–June.
  3. **One span probe**: `SELECT COUNT(*) FROM readings_numeric` from the earliest start to the latest end, recorded either way (succeeded, count, equals the per-experiment sum). A refusal's server message goes to `post_ingest_profile_span_probe.txt` (outside the grep scope) and never changes the exit code. It turns the unverified ~72 h claim (ADR-0004) into a measurement for this data; U-05 then stays open only for Grafana's wide time picker (M6). Rejected: assume the limit; raise the file limit blindly.
  4. **SQL for ranges, intervals, gaps, runs, differences, relationships; a Python pull only for the current-vs-setpoint lag** (ADR-0010 split). Lag: shift setpoint 0–60 s in 1 s steps, highest correlation wins, ties go to the smaller shift. If a window query does not work on 3.11.2, that measure moves to a per-series pull (one series of one experiment, ≤ 7,200 rows), recorded in ADR-0014; the output shape does not change. Rejected: pandas over the table.
  5. **Relationships join on the exact same instant**, reporting `instants_matched` / `instants_unmatched`, so clock drift shows as a number. Rejected: nearest-neighbour join (hides drift).
  6. **Nominal interval and documented range are a declared table in `pipeline/signals.py`**, copied from the data dictionary (1 / 2 / 5 / 60 s; on-change → none; "typical range" bounds). A unit test checks it covers the 23 numeric pairs and none of the 2 text pairs. Rejected: parsing the dictionary at run time.
  7. **Gaps are measured, not judged**: intervals over 2× and over 10× nominal, seconds spent in over-2× intervals, the 5 longest. Not applied to on-change signals (C-01). Rejected: one threshold that labels readings.
  8. **No verdict words**; the noise check is named "step-to-step change" (`differences`), since the M0 grep includes "noise" (C-02).
  9. **Floats rounded to 9 significant digits, output sorted**, so a re-run is byte-identical except `timing`. Rejected: raw floats.
  10. **Outputs written only at the end.** Any query failure other than the probe writes nothing and exits 3. Exit 2 = refused (database missing — never created —, no readings, experiments file unreadable).
  11. **Branch `m2.5-profiling`, cut from `m2-ingestion`** (M2 not merged).
  12. **The Checks Directory column is `.`** for every row. Fixes the M2 verify open question (`contract.js` read `repo root` as a folder name).
  13. **Scenario ids use `S25.n`** (settles the open question below).
  14. **Validate before scaling**: execute runs each query on one experiment first and compares it with a plain SELECT pull measured in Python, before the full run.
  15. **Recorded after the build (M2.5 judge, plan note):** correlation, slope, intercept and R squared are computed in Python on pulled pairs (`math.fsum`), not in SQL, because server sums differ in the last bits from run to run and broke the identical re-run (ADR-0014 decision 4). Residuals, ratios and differences stay in SQL. No contract change.
  16. **Recorded after the build (M2.5 judge, plan note):** p05 / p95 come from an exact rank-weighted SQL (`percentile_sql`), not `approx_percentile_cont`, because `PERCENTILE_CONT` is only about 7 digits accurate on 3.11.2 (ADR-0014). No contract change.
  17. **S25.16 means "no profile from this run".** A failed run leaves an earlier file in the report directory as it was (keeping the committed profile is intended). Reworded below; no code change.
- M3, made while planning (2026-11-23); plan approved by Sebastian. Full reasoning goes into ADR-0015 at execute.

  1. **Mode standard, judge verify, one piece (no tasks).** About 15 files, but the rules, the writer and the summary are tightly coupled, and Execute stays in-session (memory: no subagents for Execute). Rejected: full mode (cosmic-ray on Windows for a first cut of thresholds that calibration will still move); parallel tasks.
  2. **Processed data lives in new tables inside the raw database; raw tables are never written.** Processed data can only be rebuilt while raw exists, so it must expire with raw; sharing the database makes that structural and keeps Core's 5th slot free (A-04). Rejected: a fourth database `dac_processed`. Closes U-09. The name `dac_raw` now also holds derived tables; recorded as a known wart.
  3. **Dense: one processed row per raw reading, raw value and acquisition flag copied alongside.** Count equality per series is the proof nothing was dropped, and one query shows raw, processed, flag and reason. Rejected: sparse exceptions table ("no row" = good). Closes U-10.
  4. **Processed value = raw value when accepted, absent when excluded.** No clamping, filling, smoothing or signed-zero normalisation. Rejected: clamping small negative currents (down to −0.69 A) to 0; they are accepted with the `outside_typical_range` note.
  5. **Cleaning reads InfluxDB, not the CSV** (the surface the profile measured). Closes U-12.
  6. **One series of one experiment at a time.** Memory bounded by one series window (≤ 7,200 points). Narrows U-06; time-chunked processing with a one-window overlap for continuous data is a next step.
  7. **`policy_version` is a tag on all three processed tables.** A new rule set writes new series beside the old ones instead of partly overwriting them (see 15a). A unit test pins a fingerprint (SHA-256 of the canonical JSON of the declared policy table) to the version string. Rejected: version as a field.
  8. **Reason codes, in priority order:** `no_value`, `flag_bad`, `flag_uncertain`, `outside_physical_limits`, `unknown_state`, `conflicting_duplicate`, `spike`, `flatline`. The first that fires is `reason`; every code that fires (plus the note `outside_typical_range`) goes in `flags`, comma-separated, in that order, note last. UNCERTAIN is excluded because ADR-0011 already treats it as BAD.
  9. **Physical limits are declared per signal and always contain the documented typical range** (unit-tested). Values: ambient_temperature [−40, 60]; relative_humidity [0, 100]; ambient_pressure [900, 1100]; available_solar_power [0, 1000]; air_flow [0, 5000]; co2_in_ppm, co2_out_ppm [0, 5000]; solvent_flow [0, 50]; solvent_temperature [−10, 100]; pH signals [0, 14]; pressure_drop [0, 200]; current_setpoint [0, 500]; current [−2, 500]; voltage [0, 200]; power [−100, 60000]; conductivity [0, 1000]; electrolyte_temperature [−10, 100]; flow [0, 200]; pressure [0, 10]; pump_speed [0, 2000]; fan_speed [0, 3000]. Inclusive bounds. They stand in for instrument spans we don't have (new A-05).
  10. **Typical-range violations are a note, never an exclusion.** EXP_002's 350 A is the experiment's design. Rejected: excluding outside-typical values.
  11. **Spike = Hampel:** neighbours = up to 5 readings on each side in time order (truncated at series ends), taken from readings with a value inside physical limits; median `m` and MAD of the neighbours plus the reading (up to 11 values). Fires when `|x − m| > max(5 × 1.4826 × MAD, 10 × step)`, where `step` is the signal's declared normal step size. Only readings with a value inside physical limits are tested, so a reading already outside them never also carries `spike`. Not applied to `current_setpoint` or state signals. A median preserves steps; a burst longer than 5 readings is not caught (documented limit).
  12. **Flatline = variability collapse, defined on steps** so its boundaries are exact. Over readings with a value inside physical limits, in time order, step `j` (reading `j` to `j+1`) is *flat* when `|Δ| < 0.2 × step`. Step `j` is *flagged* when it is flat and more than half of the steps `j−h … j+h` that exist are flat, with `h = max(5, ceil(30 / nominal_s))` (1 Hz: 30, 0.5 Hz: 15, 0.2 Hz: 6, 1/60 Hz: 5; about one minute, at least 11 steps). A reading is `flatline` when it is an end of a flagged step. An exact run of n readings bounded by normal steps therefore flags exactly those n readings; a run of 3 flags none. Catches exact repeats and noise collapse (EXP_004 air flow, steps of about 0.4 against a normal 7.55). Not applied to `current_setpoint` or state signals; for `available_solar_power` a step between two readings of exactly 0 is never flat (night). Rejected: a median-of-window statistic (ambiguous by one reading at each end of a run); a plain exact-run length (misses noise collapse).
  13. **Normal step size per signal = median over the six experiments of the profile's `differences.median_abs`**, declared in `pipeline/cleaning_policy.py` and checked by a unit test against `reports/post_ingest_profile.json` (9 significant digits), so one degraded experiment cannot move it.
  14. **Gaps:** a spacing over 2 × nominal between consecutive points of a polled series becomes one `quality_intervals` row (`kind = gap`, from the earlier point to the later one). Never filled. On-change signals get none (C-01). A run of consecutive `flatline` readings becomes one row `kind = flatline` (first to last flagged reading).
  15. **Two InfluxDB behaviours are measured at execute before relying on them** (E-06): (a) does a later write of the same key without a field keep the old field value; (b) is an empty string field stored and read back as `""`. If (b) fails, accepted rows use the literal `none` instead of `""` for `reason` and `flags`; contract and scenarios read "empty" as that value. Both results go in ADR-0015.
  16. **State signals:** each event row becomes one `state_intervals` row lasting until the next event of that series, the last one until the experiment end (exclusive), with no expiry (C-01). Value not in the declared set → `unknown_state`. Excluded events keep their interval with no processed value.
  17. **Conflicting duplicates:** every instant that has a row in `readings_conflicts` is excluded as `conflicting_duplicate` (the kept value was chosen by rule, not by evidence; ADR-0013 / U-07). Exact copies are only counted at ingest, never stored there, so they are unaffected.
  18. **Rollup = separate command after cleaning, external Python job.** Reads `readings_processed` for one policy version; `_all` columns over points with a raw value; included columns over `verdict = accepted`; a point with no value is counted in a new column `count_no_value` and never crashes (ADR-0011 addendum, not a reversal). `policy_version` field = the cleaning version. Rejected: Processing Engine plugin (needs a plugin-enabled server to test; scheduling is H). Closes U-04.
  19. **Expected real-data results are pinned before the rules run** (S3.27–S3.29). An extra spike or flatline found at calibration comes back to `/flow:plan M3` as a narrow question; thresholds are not tuned silently.
  20. **Calibrate before scaling:** EXP_001, then EXP_004, then all six, each compared with a plain-Python recompute from a SELECT pull before anything is written.
  21. **Exit codes (clean):** 0 written and balanced; 2 refused, nothing written (database missing — never created —, raw tables missing, experiments file unreadable); 3 a query or write failed; 4 written but the read-back counts don't balance. Rollup: 0, 2, 3 with the same meaning.
  22. **Branch `m3-cleaning`, cut from `m2.5-profiling` after the M2.5 commit.** Commit and push at the end of M3; merge waits for approval.
  23. **M2 and M2.5 accepted as done for starting M3** (Sebastian, 2026-11-23, approving the plain M3 explainer). Their newest Findings predate HEAD `4888e32` but list no defects. `/flow:verify M2` and `/flow:verify M2.5` re-run before the merge to `master`.
- M3 re-plan after the calibration stop (2026-11-23, narrow question from execute; plan approved by Sebastian, `C:\Users\sebas\.claude\plans\distributed-scribbling-cake-of-7fc4517e-391c-4cb7-b461-8c072471b45f.md`). Calibration found four spike/flatline hits outside S3.29 (execute log, M3): chance flat steps in EXP_001 solvent_pH and EXP_005 ambient_pressure, the EXP_005 solar dawn ramp, and a real spike at EXP_006 fan_speed 11:10:17.

  24. **A flagged flat step must sit in an unbroken run of at least 5 flat steps** (`FLAT_MIN_RUN = 5`), on top of decision 12's majority rule. Scattered small steps on a smooth signal are chance. Measured at execute: removes the pH and ambient-pressure hits; the five pinned flatline features keep identical counts (60 / 240 / 40 / 3600 / 1350); a run of 3 readings still flags none. Rejected: raising `FLAT_FRACTION` (would also weaken noise-collapse detection). Amends decision 12.
  25. **For `available_solar_power`, a step is flat only when its change is exactly 0 and the two values are not both 0.0.** The step size of solar grows with its level (EXP_005 starts at 0 kW: steps of about 1 kW per minute at 08:00, 20 to 30 by 09:30), while the declared normal step, 12.255, is the median over six runs that mostly start at 100 to 400 kW; a fixed fraction of it is the wrong yardstick at low power. A frozen sensor repeats one value. Limit: a solar sensor frozen with a little added noise would not be caught. Replaces the night-zero special case (`_ZERO_IS_IDLE`). No run length fixes the dawn hit (execute measured 3, 5, 8). Rejected: exempt solar from flatline (misses a frozen sensor); accept the dawn hit (excludes good data).
  26. **EXP_006 fan_speed 839.2 at 11:10:17 is a real spike and joins S3.29.** Its primary reason stays `conflicting_duplicate`; `spike` is in its flags, as decision 8 requires. `POLICY_VERSION` stays `m3-v1` (nothing written under it yet); the fingerprint is re-pinned to the amended table.
  27. **M3 runs as 5 tasks, each by its own agent** (Sebastian's request, to keep each context short). Replaces decision 1's "one piece, no tasks" and, for M3, the no-subagents-for-Execute default. Pure rules (T1) and rollup (T2) in parallel; then fixture, Influx layer, CLI and e2e (T3); then real data (T4); then the write-up (T5). T1 keeps the names and signatures `scripts/clean.py` and `pipeline/cleaning_influx.py` import from `pipeline/cleaning.py`. A rule bug found by T3 or T4 is reported back, not patched outside the owner's files. T4 stops without changing thresholds if any spike or flatline appears outside S3.29. S3.26 is reworded so T2 proves it without the fixture.
- M4, made while planning (2026-11-24); plan approved by Sebastian (`C:\Users\sebas\.claude\plans\nested-twirling-book-of-20e84ac6-0afe-4726-bfcc-f29c4a1074b7.md`). Full reasoning goes into ADR-0016 at execute.

  1. **Mode standard, judge verify, 5 tasks run by agents** (Sebastian asked for tasks run in parallel where possible). Pure metric functions (T1) and storage (T2) in parallel; then fixture, CLI and e2e (T3); real data (T4); write-up (T5). A bug found by a later task is reported back to the owner, not patched outside the finder's files. Rejected: one piece (Sebastian's request); full mode (no new risk class; the formulas are pinned by hand-computed fixtures and an independent recompute).
  2. **M3 accepted as done for starting M4.** Its newest Findings block is `@ 1dcd428`; HEAD `a7bade1` is the approved merge of `f020fc0`, which only renamed one test file (verify correction block). Accepted by Sebastian with this plan.
  3. **Metrics are a Python batch job after cleaning** (`python -m scripts.metrics`), like the rollup. Rejected: query-time SQL in Grafana (formulas become untested dashboard text; the gap rule and the energy-per-kg overlap are not plain SQL); a Processing Engine plugin (same reason as U-04).
  4. **Inputs are accepted readings only; a derived value exists at an instant only when every input is accepted there.** Nothing is filled, clamped or smoothed; small negative currents stay (M3 decision 4), so power may be slightly negative. Missing inputs lower coverage.
  5. **Join on the exact same instant** for signals that share instants (voltage, current, power; co2_in, co2_out, air_flow at the 0.5 Hz instants — profile `instants_unmatched` 0). Ambient temperature and pressure (1/60 Hz) are taken as-of: the latest accepted reading at or before the instant, used when its age is at most `AMBIENT_MAX_AGE_S = 120` (2 × nominal; 120 s used, 120 s + 1 ns not). Rejected: resampling onto a grid (invents values); linear interpolation of ambient (filling).
  6. **Integration is the trapezoid rule over consecutive derived points; a spacing above `2 × nominal` of the derived series is a gap and is not bridged.** Power series (1 Hz): `POWER_MAX_SPACING_S = 2`. Capture series (0.5 Hz): `CAPTURE_MAX_SPACING_S = 4`. A spacing equal to the limit is bridged. Covered seconds = sum of bridged spacings. Sums with `math.fsum`. Rejected: scaling an integral up to the full duration.
  7. **Power: `power_computed = voltage × current` at instants where both are accepted. `power_residual = power − voltage × current` at instants where all three are accepted.** An instant agrees when `|residual| ≤ POWER_TOL_REL × |voltage × current| + POWER_TOL_W` (0.01, 10 W). The summary reports compared instants, residual median, p95 of |residual|, max |residual|, count and fraction within tolerance.
  8. **Energy twice:** `energy_kwh` from `power_computed`, `energy_logged_kwh` from the accepted logged `power`, each over its own covered time. `energy_relative_difference = (E_logged − E_computed) / E_computed`, both integrated over the overlap of their covered intervals (decision 11's overlap integration), so a one-reading difference in coverage does not show as disagreement. `mean_power_kw = energy_kwh / covered hours`.
  9. **Capture rate (kg/h) = air_flow [m³/h] × (co2_in − co2_out) [ppm] × 1e-6 × p·M / (R·T)**, p = ambient_pressure × 100 Pa, T = ambient_temperature + 273.15 K, M = 0.04401 kg/mol, R = 8.314462618 J/(mol·K). Inlet CO2 rate likewise with co2_in alone. `co2_captured_kg` and `co2_inlet_kg` are integrals of those series (decision 6); `capture_rate_mean_kg_h = co2_captured_kg / covered hours`. Assumes air flow in actual m³/h at ambient conditions, ppm by volume, humidity ignored, outlet volume = inlet volume (new assumption A-08). Rejected: a fixed standard density (12 % off across −5…30 °C). Known cost: EXP_005's first 30 ambient-pressure readings are UNCERTAIN (06:00Z–06:29Z), so its capture coverage is about 0.75; filling the barometer (under 0.1 % effect) was rejected as filling.
  10. **Capture efficiency series = (co2_in − co2_out) / co2_in at instants where both are accepted; `capture_efficiency_mean` = plain mean of that series** (`math.fsum`). Values ≤ 0 are kept and counted (`efficiency_check.at_or_below_zero`). Coverage uses the 4 s spacing rule on the efficiency series. Rejected: air-flow weighting (ties efficiency to the air-flow sensor; flow is near constant within a run).
  11. **Energy per kg CO2 (`sec_kwh_per_kg`) = energy of `power_computed` over the overlap of the power and capture covered intervals ÷ CO2 captured over the same overlap.** Each series is integrated over the overlap exactly: its piecewise-linear interpolant on each covered interval, clipped to the overlap (interpolated endpoints). Coverage = overlap seconds / duration. Value null when the overlap is empty or captured CO2 over it is ≤ 0. Rejected: total energy ÷ total CO2 over different covered times.
  12. **Every metric object is `{value, unit, coverage, status}`.** Coverage = covered seconds / `duration_s`. Status `complete` when coverage ≥ `COMPLETE_COVERAGE = 0.95`, `partial` when below, `none` exactly when value is null. Values are always reported when computable; M5 decides comparability. Quality shares have coverage and status null.
  13. **Data quality per signal**, for all 25 declared pairs of every experiment (a pair with no readings is listed with present 0): `present` = processed rows (`readings_processed` or `state_intervals`, any verdict), `accepted`, `bad` and `uncertain` (acquisition `quality`), `expected = floor(duration_s / nominal_s)` for polled signals, null for on-change state signals (C-01). `completeness = present / expected`, `valid_fraction = accepted / present`, `bad_fraction`, `uncertain_fraction` (null when the denominator is 0). Experiment level: `completeness = Σpresent / Σexpected` over polled pairs; the three fractions over all 25 pairs. Counts come from a SQL `GROUP BY` (no `FILTER`).
  14. **Storage.** InfluxDB `metrics_series` in the target raw database (expires with raw, like M3 decision 2): tags `experiment_id`, `metric` (`power_computed` W, `power_residual` W, `capture_efficiency` fraction, `capture_rate` kg/h), `metrics_version`, `policy_version`; field `value` float; time = the instant. Postgres (migration `0003_experiment_metrics.sql`): `experiment_metrics` (PK `experiment_id, metrics_version, metric`; FK to `experiment`) and `signal_quality` (PK `experiment_id, metrics_version, source, signal`; FK). Both upserted in one transaction per run, so a rerun overwrites identical rows and a failure leaves nothing partial. They outlive raw retention on purpose (small summaries). Rejected: one InfluxDB point per experiment at a made-up time (no join to metadata).
  15. **Policy table and version.** All constants of decisions 5–12 and 16 sit in one declared mapping in `pipeline/metrics.py` with `METRICS_VERSION = "m4-v1"`; a unit test pins `METRICS_FINGERPRINT` (SHA-256 of its canonical JSON). A changed constant is a new version.
  16. **Plausibility checks per experiment, in the summary:** `efficiency_in_unit_interval` (0 ≤ `capture_efficiency_mean` ≤ 1), `capture_below_inlet` (`co2_captured_kg` ≤ `co2_inlet_kg`), `sec_above_floor` (`sec_kwh_per_kg` ≥ `SEC_FLOOR_KWH_PER_KG = 0.10`, below the minimum work of separating CO2 from air), `energy_agreement` (|`energy_relative_difference`| ≤ `ENERGY_AGREEMENT_REL = 0.01`). `passed` is null when the metric is null. Any `false` → exit 1, outputs still written. Raw-data estimates give 9–43 kWh/kg; the report states the numbers, not a finding.
  17. **Exit codes:** 0 written and read back; 1 written and read back, a plausibility check failed; 2 refused, nothing written (database missing — never created —, `readings_processed` missing or holding no rows for the policy version, experiments file unreadable, Postgres unreachable, migration 0003 not applied, an experiment missing from Postgres `experiment`); 3 a query or write failed; 4 written but read-back counts differ. Outputs written on 0, 1, 4; none on 2, 3. Order: compute everything, write InfluxDB, write Postgres (one transaction), read back, write outputs.
  18. **Expected real-data labels pinned before the real run** (S4.24). A different label stops T4 and comes back as a narrow question; constants are not tuned silently.
  19. **Calibrate before scaling:** EXP_001 first, compared with an independent plain-Python recompute from SELECT pulls (no pipeline imports), then EXP_004 (air-flow hour), then all six.
  20. **Branch `m4-metrics`, cut from `master`.** Commit and push at the end of M4; merge waits for approval.
  21. **Recorded at the M5 plan (judge note):** the inlet CO2 rate uses the captured series' instants (where co2_in, co2_out, air flow and ambient are all usable), with ppm = co2_in. "Likewise with co2_in alone" in decision 9 meant the formula, not the instants. Keeps `capture_below_inlet` like for like. ADR-0016 item 24 records it. No code or contract change.
- M5, made while planning (2026-11-24); plan approved by Sebastian (`C:\Users\sebas\.claude\plans\frolicking-gliding-mango-of-945a74fa-e04e-4ece-aa19-1bfea04e10ae.md`). Full reasoning goes into ADR-0017 at execute.

  1. **Mode standard, judge verify, 6 tasks run by agents** (Sebastian asked for parallel agents in separate contexts). W1: pure analysis (T1) ∥ reads (T2) ∥ fixture (T3); W2: command and e2e (T4); W3: real data (T5); W4: write-up and draft findings (T6). A bug found by a later task is reported back to the owner, not patched outside the finder's files. Rejected: one piece (Sebastian's request); full mode (read-only, no new risk class).
  2. **M4 accepted as done for starting M5** (Sebastian, with this plan). Its newest Findings block (`@ a7bade1 (+ uncommitted)`, no defects) reviewed the working tree that became commit `9ad21eb`, merged as `262fb1f` with his approval.
  3. **"Flow and pressure" = the hydrolyzer's electrolyte `flow` (L/min) and `pressure` (bar)** (Sebastian, with this plan): same subsystem as the cell voltage; the data dictionary warns not to conflate `flow` with other flows. The absorber's `air_flow` and `pressure_drop` get the same analysis as a second model, so the other reading of the brief is answered too. Rejected: absorber only.
  4. **Read-only.** M5 writes no InfluxDB or Postgres row and creates nothing; its outputs are files. Rejected: storing aligned series now (M6 decides how the overlay works; storing them before that is designing ahead).
  5. **Shared clock: `experiment_time_s = (t_ns − start_ns) / 1e9`**, start = the experiment's `start_time`. Ids and windows `[start, end)` come from the experiments file, as in M2–M4; metadata comes from Postgres `experiment` (corrections live there, ADR-0012). If Postgres `start_time` or `end_time` differs from the file for an experiment, the run refuses (exit 2, `window_mismatch`). Rejected: aligning on the first STEADY_STATE event (phases are reported separately, in experiment time, so phase offsets stay visible).
  6. **Phases from accepted `process_state` rows of `state_intervals`:** phase = `[event time, end_ns)`. Analysis window = `[start + settle_s, end)` when `start + settle_s < end`, otherwise none. `settle_s = 60` (more than twice the measured 23–24 s current-to-setpoint lag). Steady windows = the windows of STEADY_STATE phases. Rejected: whole phases (transients leak in).
  7. **Instant join.** Hydrolyzer model: exact same instant of voltage, current, flow, pressure (all 1 Hz). Absorber model: exact instants of pressure_drop (0.5 Hz) where voltage, current and air_flow also exist. `electrolyte_temperature` (0.2 Hz) as-of: latest accepted reading at or before the instant, used when at most `temp_max_age_s = 10` s old (2 × nominal; reuses `pipeline.metrics.as_of`). Only instants inside the analysis windows. Rejected: resampling to a grid (invents values).
  8. **Voltage model (OLS):** `voltage ~ 1 + current + electrolyte_temperature + X1 + X2`, hydrolyzer `X1, X2 = flow, pressure`, absorber `air_flow, pressure_drop`. Predictors centred at the fit's own means; normal equations solved by Gaussian elimination with partial pivoting; sums with `math.fsum`. A fit is **testable** when it has at least `min_instants = 300` rows and no pivot is at or below `1e-9 ×` the largest diagonal entry of the normal matrix. Per term: `coefficient` (V per unit of the term), its interval (decision 10), `r2_drop` (R² of the full model minus R² without that term), `vif` (1 / (1 − R² of the term on the other predictors)), `plain_corr` (Pearson of voltage with the term over the fit rows). For X1 and X2 also the lag fields (decision 11). Joint: `r2_drop` without both X1 and X2; `separable` = both VIFs below `vif_limit = 10`. When not separable, findings may cite only the joint effect. Rejected: plain correlation as the answer (voltage follows current first; it is reported, not concluded from).
  9. **Fits:** each model × window (`steady`, `whole_run` = `[start, end)`) × scope (each experiment; `pooled` over the testable experiments of that model and window, with one intercept per experiment instead of the common one).
  10. **Block bootstrap.** Blocks: within each analysis window, block `k` = rows with `floor((t − window_start) / bootstrap_block_s) = k` (`bootstrap_block_s = 120`). A resample draws B blocks with replacement (B = number of non-empty blocks) by `rng.randrange(B)`, B draws per resample, `bootstrap_resamples = 1000` resamples, `rng = random.Random(seed_key)` with `seed_key = f"{bootstrap_seed}|{model}|{window}|{scope}"` and `bootstrap_seed = 20261124`. Each block's sufficient statistics (sums of the centred cross-products) are computed once and summed per resample (same centring constants as the full fit). Pooled: stratified, for each experiment in id order draw its own B_e blocks, one rng. A singular resample is counted (`resamples_singular`) and skipped. Interval = percentiles at `(1 − interval_level) / 2` and `(1 + interval_level) / 2` (`interval_level = 0.95`) of the coefficient over the used resamples, linear interpolation between order statistics (type 7). Rejected: textbook standard errors (1 s readings are autocorrelated; intervals would be far too narrow).
  11. **Lag search** for X1 and X2: residual of the model without that term (the other three predictors) at instant t against the term at the exact instant `t − k s`, k = 0 … `lag_max_s = 60`; a k with fewer than `min_instants` pairs is skipped. Best = highest |Pearson|, ties to the smaller k. Reported: `best_lag_s`, `corr_at_best_lag`, `corr_at_zero`.
  12. **Evidence rule** per (model, window, term), over the per-experiment fits. An interval *excludes zero* when `low > 0` or `high < 0` (an endpoint of exactly 0 does not). `supported`: at least 2 testable fits, all exclude zero, all the same sign. `single_run`: exactly 1 testable fit and it excludes zero. `inconsistent`: two testable fits exclude zero with opposite signs. `not_resolved`: any other case with at least 1 testable fit. `not_testable`: none. The pooled fit is reported beside the status, not used by it. Rejected: judging effect sizes by eye.
  13. **Steady-state KPIs** per experiment over the steady windows: `voltage_mean_v` (V, mean of accepted voltage instants), `mean_power_kw` (kW, trapezoid integral of `power_computed` over its covered intervals ∩ steady windows ÷ covered seconds ÷ 1000), `capture_rate_mean_kg_h` (kg/h, same with `capture_rate`), `capture_efficiency_mean` (fraction, plain mean of `capture_efficiency` values at instants in the steady windows, as M4 decision 10), `sec_kwh_per_kg` (kWh/kg, energy of `power_computed` over power-covered ∩ capture-covered ∩ steady, ÷ CO2 captured over the same, as M4 decision 11). Covered intervals use `pipeline.metrics.covered_intervals` with the M4 spacing limits (`POLICY` of `pipeline.metrics`: 2 s for voltage and power, 4 s for capture and efficiency). Coverage = covered steady seconds ÷ steady seconds; status by `pipeline.metrics.status_for`. Intervals: the same block layout as decision 10 over the steady windows, each block contributing its partial sums (integral and covered seconds, or sum and count, or energy and captured), a resample KPI = ratio of the summed parts; seed key `f"{bootstrap_seed}|kpi|{kpi}|{experiment_id}"`. The 1,000 resample values are kept in memory for decision 14. Whole-run metrics are the 13 Postgres `experiment_metrics` rows, copied unchanged.
  14. **Comparability** for all 15 pairs (a < b by id). Seven factors, measured from accepted readings in the steady windows where possible: `current_setpoint` (median), `current_setpoint_profile` (`varying` when p95 − p05 of the setpoint exceeds `condition_tol_rel` × its median, else `constant`), `air_flow` (median), `solvent_flow` (median), `ambient_temperature` (median), `relative_humidity` (median), `sorbent_batch` (metadata). Relative factors differ when `|a − b| > condition_tol_rel × max(|a|, |b|)` (`condition_tol_rel = 0.05`); ambient temperature when `|a − b| > ambient_tol_c = 5`; humidity when `|a − b| > humidity_tol_pct = 15`; profile and batch when not equal. A missing value (null batch, no readings) makes `differs` null, which counts as differing. Status: `same_conditions` (0 differing), `supported` (exactly 1), `confounded` (2 or more), with the differing factors named. `operator` is listed under `recorded_differences` only (setpoints are automated; not a factor). Per KPI: `difference = b − a`, interval from the element-wise differences of the two resample arrays (type 7), `excludes_zero`, and `coverage_status` = `both_complete` (both KPI statuses complete), `partial_coverage` (both have a value, one or both partial), `not_available` (either value null; difference and interval null). Rejected: comparing pairs without the factor check.
  15. **One run per condition.** Findings say "in this run" and name the confounders; no causal wording. New assumption A-09 (T6).
  16. **Pressure drop vs air flow** (the M2.5 next step): per experiment, over the steady windows at pressure_drop instants with air_flow at the same instant, fits `pressure_drop ~ air_flow` and `~ air_flow²` (slope, intercept, R²) and the lag search of decision 11 on air_flow; across experiments, the steady medians of air_flow and pressure_drop and a line through them (slope, R²). Numbers only.
  17. **Air-flow check (A-07)** for `airflow_check_experiment = "EXP_004"`, boundary `airflow_check_boundary = "2026-03-02T09:00:00Z"`: median and count before and after the boundary within the experiment window for `air_flow` (from `value_raw`, all rows, since cleaning excluded the second hour), and `fan_speed`, `pressure_drop`, `co2_in_ppm`, `co2_out_ppm` (accepted) and `capture_efficiency` (`metrics_series`); relative change = (after − before) / before. `airflow_check` is null when that experiment is not in the run. Numbers only; T6 writes A-07's status from them.
  18. **Policy table and version.** All constants of decisions 6–17 in one declared mapping `POLICY` in `pipeline/compare.py` (keys exactly the `parameters` keys of the contract) with `COMPARE_VERSION = "m5-v1"`; a unit test pins `COMPARE_FINGERPRINT` (SHA-256 of its canonical JSON). A changed constant is a new version.
  19. **No finding is pinned in a scenario** (MISTAKES E-09). Real-data scenarios pin completeness, the independent recompute and reproducibility. T5 stops and reports back (narrow question to `/flow:plan M5`) when the analysis cannot run as specified on the real data, e.g. no testable fit for a model; it never changes a constant.
  20. **Draft findings** in `reports/findings.md`: status line `Status: draft, awaiting Sebastian's approval`; at least three findings, each with claim, the command and the SQL of the pulls behind it, and the numbers; a section answering flow and pressure against voltage (hydrolyzer model first, absorber model second); a section naming the comparisons the data does not support, with the reason. Every number cited carries a reference comment `<!-- ref: <path> -->` right after it; the path addresses `reports/comparison_summary.json` with `/` between keys and `key=value[,key=value]` selecting a list item (e.g. `voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient`). The written number equals the referenced value rounded to the digits written. `tests/unit/test_findings_doc.py` checks every reference (the M5 CI increment in ROADMAP). Changing the status line after approval is a one-line edit by execute.
  21. **Exit codes:** 0 outputs written; 2 refused, nothing written (database missing — never created —, `readings_processed` with no rows for the policy version, `metrics_series` with no rows for the metrics and policy version, experiments file unreadable, Postgres unreachable or migration 0003 not applied, an experiment missing from Postgres `experiment` or without `experiment_metrics` rows for the metrics version, `window_mismatch`); 3 a query failed. Outputs written only on 0, at the end.
  22. **Calibrate before scaling:** EXP_001 first against an independent plain-Python recompute from SELECT pulls (no pipeline imports, the bootstrap re-implemented from decision 10's text), then all six.
  23. **Branch `m5-comparison`, cut from `master` at `262fb1f`.** The first commit carries this record and the M5 contract files. Commit and push at the end of M5; merge waits for Sebastian's approval of the findings.
  24. **Housekeeping:** S4.9, S4.24 and S4.25 reworded to what the build gives and Sebastian ruled (Next steps entries of 2026-11-24, judge block `@ a7bade1`); M4 decision 21 added; the M4 contract example's `series_written.capture_rate` changed from 268 to 269 (example only; the schema is unchanged and no caller reads the example's numbers). No code change.

### Assumptions and open questions
- Partial accept on 3.11.2 behaves as documented — a real test in M2 decides (Claude).
- `influxdb3-python` writes synchronously when told to — confirmed in M2 (Claude).
- The flow verify harness can run `python` here — confirmed at M2's first verify (Claude).
- ~~Later scenario ids for M2.5 need a numeric form~~ — settled: `S25.n` (M2.5 decision 13).
- M2 is not done by the done rule: its newest Findings block is `@ 1c5b6ea (+ uncommitted)`, HEAD is `77b8516`. `/flow:verify M2` should run before `/flow:execute M2.5` (Claude recommends; Sebastian runs).
- DataFusion in Core 3.11.2 supports the window functions (`LAG`, running `SUM`), `median`, `approx_percentile_cont`, `corr` and `regr_*` the SQL needs — checked at execute's first calibration; fallback is M2.5 decision 4 (Claude).
- ~~`p05` / `p95` come from `approx_percentile_cont`~~ — superseded: exact rank-weighted SQL (M2.5 decision 16).
- M2.5 is not done by the done rule: its newest Findings block is `@ 77b8516 (+ uncommitted)`. Commit and push M2.5, then `/flow:verify M2` and `/flow:verify M2.5` at that commit (or Sebastian accepts them) before `/flow:execute M3` (Claude recommends; Sebastian runs).
- M3: Core's merge behaviour for a write without a field, and empty-string fields — measured at execute (M3 decision 15).
- M3: the thresholds (5 × robust sd, floor 10 × step, flatline 0.2 × step, windows) are a first calibration on six 2-hour runs; a longer or noisier data set may need them re-set, which is a policy-version change (Claude).
- M3: EXP_004 air flow 09:00–10:00 is treated as a sensor fault (fan speed, pressure drop and outlet CO2 unchanged while the reading drops 60×). That is a cleaning call, not an M5 finding; M5 may revisit it (Claude decides; Sebastian reviews in the M3 report).
- M3: `FLAT_MIN_RUN = 5` and the solar exact-repeat rule (decisions 24, 25) are a first calibration on the same six runs; a changed value is a policy-version change (Claude).
- M4: air flow is actual m³/h at ambient conditions, ppm is by volume, humidity is ignored, outlet volume equals inlet volume (new A-08; Claude decides, Sebastian reviews in the M4 report). Wrong if the meter reports normal m³/h: capture rate would then be off by the ambient-to-standard density ratio (up to about 12 %).
- M4: the expected labels in S4.24 come from the M3 cleaning summary and the raw ambient file (EXP_005 ambient pressure UNCERTAIN 06:00Z–06:29Z, contiguous). Coverages are approximate (±0.01) until T4 measures them (Claude).
- M4: `SEC_FLOOR_KWH_PER_KG = 0.10` is a lower bound below the minimum work to separate CO2 from 400 ppm air (about 0.12 kWh/kg at 25 °C, RT·ln(1/x) in the small-capture limit). It catches unit errors, not inefficiency (Claude).
- M5: one run per condition, so a difference between two runs cannot be separated from day-to-day variation (sorbent batch, date, ambient). Findings are worded "in this run" (new A-09 at T6; Claude decides, Sebastian approves the findings).
- M5: the comparability tolerances (5 % on setpoints and flows, 5 °C ambient, 15 %RH humidity) are judgement, not calibration; the measured condition values are reported beside each factor so a reader can disagree (Claude).
- M5: the block length (120 s) is longer than the measured current lag (23–24 s) and short enough for about 60 blocks per whole run and 7 per steady window on the fixture; a much longer correlation time in the real residuals would make the intervals too narrow. T5 reports the lag-1 block correlation of the residuals for EXP_001 in the execute log so the judge can see it (Claude).
- M5: the fixture's planted coefficients (T3) must be recoverable by OLS: flow and pressure patterns independent (VIF well under 10), voltage generated from the exact values the join pairs (temperature as-of), and every planted reading accepted by cleaning; if cleaning excludes anything unplanned, T3 changes the construction, not the rules (Claude).
- M3: EXP_004 pressure −3.1 bar: its acquisition flag decides whether the reason is `flag_uncertain` or `outside_physical_limits`; either way it is excluded (Claude, at execute).

### Next steps (not in this budget)
- Cross-run duplicate detection — out of scope per ADR-0007; belongs with deliverable H — medium.
- Parallel ingest by experiment — not needed at 520k rows — small.
- Multi-pass merge in the external sort — only needed past the OS open-file limit — small.
- M2 verify's three low findings (offset minutes over 59 accepted, signed-zero tie on file order, second `up` overwrites `.env`) belong to M2, not M2.5 — fix before the M2 merge or record as accepted — small.
- Core 3.11.2 gets four things wrong that M3's cleaning SQL must avoid or work around: `COUNT(*) FILTER` counts NULL conditions produced by a window function such as `LAG` (at least; a NULL from a plain row is not counted — M2.5 judge), `-0.0` is not equal to `0.0`, `PERCENTILE_CONT` is only about 7 digits accurate, and parallel sums vary in the last bits (ADR-0014). Found 2026-11-23 in M2.5; the rollup driver uses none of the first three (grep) but its sums have the last property — small.
- The profile measures pressure drop against air flow at the same instant: R squared below 0.17 in all six experiments, although the data dictionary says it scales with air flow. M5 should check whether a lag or another definition changes that before anyone cites it — small, found 2026-11-23. **Taken into M5** (decision 16).
- The rollup driver (`pipeline/rollup_run.py`) raises `TypeError` on a stored point with no value, because `compute_rollup` takes `min()` and `sum()` over a `None`. M2 stores an empty value as exactly such a point (decision 6). The real file has 0 of them, so nothing fails today; M3 must decide whether the rollup skips them or counts them as missing — small, found 2026-11-23 while writing the M2 report. **Taken into M3** (decision 18: `count_no_value`).
- Time-chunked cleaning for continuous plant data: process fixed time windows with an overlap of one flatline window on each side, carry nothing else across — remainder of U-06 — medium.
- Cross-signal exclusion rules (power against voltage × current, air flow against fan speed): M4 does the power cross-check as a metric check; flatline already catches the EXP_004 air-flow case — medium.
- Rollup rebuild after a policy change: if M3 decision 15a shows Core keeps an old field when a later write omits it, a bucket whose included count drops to 0 keeps its old `mean`/`std`/`median`. Fix options: write the rollup per policy version (schema change to ADR-0011, needs approval) or rebuild into a fresh table — small to medium, size known after execute.
- Bursts of more than 5 bad readings look like a step to the Hampel rule and are not caught as `spike` (limits or flatline may still catch them) — documented limit — small.
- M2.5 judge low findings: `InfluxGateway` has no query timeout (a hung span probe stalls the run) — small.
- Rollup speed (M3): `python -m scripts.rollup` takes about 12 minutes for 16,256 buckets on the real data, about 2 minutes per experiment, and prints only when an experiment finishes (no timing, no progress). The streaming read of `readings_processed` is the likely cost; profile it, then add a per-experiment timing line — small to medium, found 2026-11-23.
- Rollup end-to-end test shares one database (M3): `tests/e2e/test_clean_cli.py` writes the rollup into the same throwaway database as the cleaning, because Core allows 5 databases and 4 exist while it runs. A second throwaway would fail the 5-database limit. Fine until a test needs two at once — small, found 2026-11-23.
- Old policy versions pile up (M3): bumping `POLICY_VERSION` writes new rows beside the old ones in `dac_raw`, and nothing removes the old version's rows (they expire with raw). A cleanup command, or a note in the operations story for deliverable H — small, found 2026-11-23 while writing ADR-0015.
- No test validates the committed `reports/cleaning_summary.json` against `contracts/cleaning_summary.schema.json` (the profile has one in `tests/unit/test_profiling.py`); only the fixture run's output and the example are validated. Checked by hand at write-up — small, found 2026-11-23.
- Rolling up `metrics_series` into `dac_rollup` (M4 non-goal): not needed for 7,200 points per experiment; needed once runs are long — small.
- Filling short ambient gaps for the gas density (M4 decision 9's rejected option): would raise EXP_005 capture coverage from about 0.75 to 1.0 at under 0.1 % error; a policy-version change if wanted — small.
- A commanded-vs-measured current check (current against current_setpoint with the measured 23–24 s lag) as a metric: belongs with M5's analysis if needed — small.
- Old metrics versions pile up in `metrics_series` and the Postgres tables, like M3's old policy versions — note for H — small.
- S4.9 pins 268 `capture_rate` rows for the fixture; the construction gives 269 (297 efficiency instants minus the 28 even seconds from +362 to +418 other than +400, which is already outside the 297; the pinned coverage 532/600 fits 269). The scenario text and the contract example's `series_written` say 268. Fix both at the next `/flow:plan M4` — small, found 2026-11-24 in M4 T3, hand-checked by the lead.
- **Sebastian's decision, 2026-11-24 (given to execute, not via `/flow:plan`):** S4.25's 0.99 stays unchanged. EXP_001's 0.983158 (120 s of logged power about 6 kW above voltage x current, 09:23:20 to 09:25:19 on 2026-05-04, all three accepted by cleaning) is reported in `reports/M4.md` as a cross-check result, not a failure of the build and not hidden; no cleaning rule is added and M3 is not reopened. The judge should read S4.25 as: every other experiment is at least 0.99, and EXP_001's shortfall is explained and reported. Reword S4.25 at the next `/flow:plan M4` — small.
- `.gitattributes` now has `migrations/*.sql -text`, so Windows checkouts keep the LF bytes whose checksums `schema_migrations` recorded (M4 execute, Sebastian agreed 2026-11-24). Without it the runner refused 0001 on any CRLF checkout.
- S4.24 pins `sec_kwh_per_kg` complete for EXP_002; the real run gives partial (coverage 0.9329), because the value's coverage is the overlap of power and capture and EXP_002's power coverage is 0.9331. The other pinned labels match. Not a constant change; the plan's prediction missed the overlap. Reword S4.24 at the next `/flow:plan M4`; Sebastian reviews it in the M4 report — small, found 2026-11-24 by the lead after T4.
- `plausibility[].limit` is required to be a number in the contract, so `capture_below_inlet` writes limit 0.0 (with `passed` null) when the inlet total is null. Allow null in the schema at the next contract change — small, found 2026-11-24 in M4 T1.
- The S4.9, S4.24 and S4.25 rewordings above: **done** at the M5 plan (M5 decision 24).
- M4 read-back ignores the cleaning policy version (M4 judge, medium): `count_series` in `pipeline/metrics_store.py` filters on experiment, metric and metrics version only, so once `metrics_series` holds a second policy version every later metrics run exits 4. Fix: add `policy_version` to `count_series` and its call in `pipeline/metrics_run.py`, with the judge's proposed test `test_count_series_counts_only_the_given_policy_version`. M5 reads `metrics_series` with the policy version, so it is not affected. Also: the Postgres key `(experiment_id, metrics_version, metric)` has no policy version, so a run under a second policy overwrites the first one's rows — a design point for whoever adds a second policy version — small.
- Storing aligned series (experiment time) or comparison results where Grafana can read them: M6 decides how the overlay works (M5 decision 4) — small to medium.
- Replicate runs per condition: the only way to turn "in this run" into a claim about a condition (M5 decision 15) — needs new experiments, not code.
- Residual autocorrelation is not in `comparison_summary.json` (M5 execute): T5 measured the lag-1 correlation of 120 s block means of the hydrolyzer steady residuals (EXP_005 0.87, the others -0.15 to 0.12) in a scratch script; the findings cite it from the log, outside the reference test. Add it to the summary and contract so the finding can carry a reference, and measure it for the absorber model too — small, found 2026-11-24.
- The compare fixture cannot test the absorber voltage model (M5 execute): the "+ at even reading index" noise makes current and air flow constant at the 0.5 Hz pressure-drop instants, so the normal matrix is singular and absorber fits are `not_testable` there. T1's unit tests cover the testable path. Change the fixture noise phase for 0.5 Hz joins at the next `/flow:plan M5` if an end-to-end absorber fit is wanted — small, found 2026-11-24.
- M5 decision 13 text vs build (M5 execute): steady KPI series are restricted to instants inside the steady windows before covered intervals are taken (fixture coverage 838/840), where the literal text (covered intervals of the whole series, then clipped) gives 840/840. The build matches the fixture README and S5.15; reword decision 13 at the next `/flow:plan M5` (ADR-0017 records it) — small, found 2026-11-24.
- Partial-sum blocks split covered pairs at the 120 s block edges (M5 execute, matches the independent recompute); decision 13's text says "each block contributing its partial sums" without saying how a pair that straddles an edge is split. Reword at the next plan — small.

### Checks
Services: `.workflow/verify-env.json` (private InfluxDB + Postgres; `up` writes the worktree
`.env` with `INFLUX_HOST=http://localhost:$FLOW_PORT_BASE`, Postgres on `$FLOW_PORT_BASE+1`).

| Kind | Command | Directory | Prerequisites | Source |
|---|---|---|---|---|
| lint | `ruff check .` | . | `pip install -r requirements.txt` | ci.yml |
| lint | `ruff format --check .` | . | same | ci.yml |
| unit | `python -m pytest tests/unit -v` | . | none | pyproject |
| integration | `python -m pytest tests/integration -v` | . | stack up; any skip counts as a failure | ci.yml |
| e2e | `python -m pytest tests/e2e -v` | . | stack up; any skip counts as a failure | new in M2 |
| e2e | `python -m scripts.ingest` | . | stack up; real CSV copied in | new in M2 |
| contract | `check-jsonschema --schemafile contracts/ingest_summary.schema.json contracts/examples/ingest_summary.example.json` | . | `check-jsonschema` added to requirements.txt in M2 (not installed today) | new in M2 |
| e2e | `python -m scripts.post_ingest_profile --report-dir .flow-tmp/profile` | . | stack up; `python -m scripts.ingest` ran on the real CSV first; `.flow-tmp/` gitignored | new in M2.5 |
| contract | `check-jsonschema --schemafile contracts/post_ingest_profile.schema.json contracts/examples/post_ingest_profile.example.json` | . | requirements installed | new in M2.5 |
| e2e | `python -m scripts.clean --report-dir .flow-tmp/clean` | . | stack up; `python -m scripts.ingest` ran on the real CSV first | new in M3 |
| e2e | `python -m scripts.rollup` | . | stack up; `python -m scripts.clean` ran first | new in M3 |
| contract | `check-jsonschema --schemafile contracts/cleaning_summary.schema.json contracts/examples/cleaning_summary.example.json` | . | requirements installed | new in M3 |
| integration | `python -m pytest -v` | . | stack up; the whole suite in one session (catches basename clashes, M3 verify correction); any skip counts as a failure | ci.yml (new row in M4) |
| e2e | `python -m scripts.metrics --report-dir .flow-tmp/metrics` | . | stack up; `python -m scripts.ingest` then `python -m scripts.clean --report-dir .flow-tmp/clean` ran first on the real CSV; Postgres migrated (0003) and experiments loaded (`verify_stack.py up` does both) | new in M4 |
| contract | `check-jsonschema --schemafile contracts/metrics_summary.schema.json contracts/examples/metrics_summary.example.json` | . | requirements installed | new in M4 |
| e2e | `python -m scripts.compare --report-dir .flow-tmp/compare` | . | stack up; `python -m scripts.ingest`, `python -m scripts.clean --report-dir .flow-tmp/clean` and `python -m scripts.metrics --report-dir .flow-tmp/metrics` ran first on the real CSV | new in M5 |
| contract | `check-jsonschema --schemafile contracts/comparison_summary.schema.json contracts/examples/comparison_summary.example.json` | . | requirements installed | new in M5 |

`.workflow/verify-env.json`:
```json
{ "requires": ["docker"], "network": true,
  "up": "python scripts/verify_stack.py up",
  "health": "python scripts/verify_stack.py health",
  "down": "python scripts/verify_stack.py down",
  "copy": ["data/raw/dac_raw_timeseries.csv"],
  "ports": 2, "timeoutSeconds": 900 }
```

### Milestones

#### M0: Environment and reconnaissance
- Done before this record (old method). Evidence: `docs/ROADMAP.md` § M0. Accepted by Sebastian.

#### M1: Time-series data model (A)
- Done before this record (old method). Evidence: `docs/ROADMAP.md` § M1, CI run 35779389919. Accepted by Sebastian. Owed: review of the schema doc and rollup function, carried into the M2 report.

#### M2: Ingestion (B)
- Depends on: M1
- Judge: verify · Touches: data, infra, local secrets (`.env` per stack)
- Gates: —
- Contract: `contracts/ingest_summary.schema.json` (shape of `ingest_summary.json`), example in `contracts/examples/`.
- Order of work: private stack (S2.1–S2.4) → ingest on the fixture (S2.5–S2.27) → full real run and report (S2.28–S2.33).
- Command: `python -m scripts.ingest [--csv PATH] [--experiments PATH] [--sha256 PATH] [--database NAME] [--report-dir DIR] [--batch-size N]`. Defaults: the real CSV, `data/raw/experiments.json`, the committed `.sha256`, `dac_raw`, `reports/`, 10000.
- Outputs in `--report-dir`: `ingest_summary.json`, `ingest_report.md`, `ingest_rejects.csv` (columns `row_number,reason,detail,timestamp,experiment_id,source,signal,value,quality`; header only when empty). Tables: `readings_numeric`, `readings_state`, `readings_conflicts` (tags `experiment_id, source, signal, discard_rank`; fields `value_kept_raw, quality_kept, value_discarded_raw, quality_discarded, source_row_kept, source_row_discarded, reason, resolution`).
- Example map (rule → one example; failure cases included):

  | Rule | Example |
  |---|---|
  | Private stack is isolated | run id `abc`, port base 18100 → own containers; dev stack keeps running |
  | Offset honoured | ambient `10:00:00+02:00` → stored `08:00:00Z` |
  | No offset → reject | `2026-05-04T08:00:00` → `missing_offset` |
  | Exact instant kept | `.300Z` and `.700Z` → two points |
  | Finer than µs → reject | `.1234567Z` → `precision_too_fine` |
  | Bad row → reject, run exits 1 | `abc` as a number → `bad_number` |
  | Exact copy collapses | `250.0` / `250.00`, both GOOD → one point |
  | Better flag wins | 15.06 UNCERTAIN vs 16.00 GOOD → 16.00 kept |
  | Equal flags → smaller wins | 1209.4 vs 1223.4 → 1209.4 kept |
  | File order never matters | swap the two rows → same database |
  | Text conflicts kept as text | OPEN vs CLOSED → CLOSED kept, both as text |
  | Out-of-order counted only | 08:00:05 after 08:00:09 → count 1, stored normally |
  | Outside window → saved, exit 1 | reading 2 h after the end → counted |
  | Counts balance | rows = saved + copies + losers + rejected, per series |
  | Re-run converges | second run → identical counts and conflicts |
  | Wrong fingerprint → nothing written | one changed byte → exit 2 |
  | Real file | 520,005 rows → 519,980 saved, 15 copies, 10 losers, 0 rejected |

- Scenarios:
  ```gherkin
  Scenario: S2.1 Up starts a ready private stack on the given ports
    Given FLOW_RUN_ID=abc and FLOW_PORT_BASE=18100
    When "python scripts/verify_stack.py up" runs
    Then InfluxDB answers /health on port 18100 and Postgres accepts logins on port 18101
    And .env names those ports and a token that authenticates
    And databases dac_raw, dac_rollup, dac_pinned exist and 6 experiments are loaded

  Scenario: S2.2 The dev stack is untouched
    Given the dev containers dac-influxdb and dac-postgres are running
    When up and then down run for run id abc
    Then both dev containers still run with the same container ids, and their volumes still exist

  Scenario: S2.3 Health fails when no stack is up
    Given no stack exists for run id xyz
    When "python scripts/verify_stack.py health" runs with FLOW_RUN_ID=xyz
    Then it exits non-zero

  Scenario: S2.4 Down removes the private stack, and plain compose keeps the dev names
    Given a private stack is up for run id abc
    When "python scripts/verify_stack.py down" runs
    Then no container and no volume of compose project dac-verify-abc remains
    And "docker compose config" with no overrides still names dac-influxdb and dac-postgres

  Scenario: S2.5 A stated offset is honoured
    Given an ambient row stamped "2026-05-04T10:00:00+02:00"
    When the ingest runs
    Then readings_numeric holds that reading at 2026-05-04T08:00:00Z

  Scenario: S2.6 A timestamp without an offset is rejected
    Given a row stamped "2026-05-04T08:00:00"
    When the ingest runs
    Then ingest_rejects.csv lists that row number with reason "missing_offset"
    And no point exists for it

  Scenario: S2.7 Sub-second instants are stored exactly
    Given two rows for one sensor at "08:00:00.300Z" and "08:00:00.700Z"
    When the ingest runs
    Then two points exist, at .300 and .700 seconds

  Scenario: S2.8 A timestamp finer than a microsecond is rejected
    Given a row stamped "2026-05-04T08:00:00.1234567Z"
    When the ingest runs
    Then the row is rejected with reason "precision_too_fine"

  Scenario Outline: S2.9 Unreadable rows are rejected with a named reason
    Given a row with <defect>
    When the ingest runs
    Then ingest_rejects.csv lists it with reason "<reason>"
    Examples:
      | defect                                   | reason             |
      | value "abc" on a numeric signal          | bad_number         |
      | signal "voltage" under source "absorber" | unknown_signal     |
      | experiment "EXP_999"                     | unknown_experiment |
      | quality "OK"                             | bad_quality        |
      | five columns instead of six              | malformed_row      |

  Scenario: S2.10 Rejected rows do not stop good rows
    Given 1 rejected row and 9 good rows
    When the ingest runs
    Then the 9 good rows are saved and the command exits 1

  Scenario: S2.11 An exact copy collapses into one point
    Given "250.0" GOOD and "250.00" GOOD for one sensor and instant
    When the ingest runs
    Then one point with value 250.0 exists
    And the summary counts 1 exact copy for that series
    And readings_conflicts has no row for that instant

  Scenario: S2.12 With equal flags the smaller value is kept
    Given "1209.4" GOOD and "1223.4" GOOD for one sensor and instant
    When the ingest runs
    Then the stored value is 1209.4
    And readings_conflicts holds value_kept_raw "1209.4", value_discarded_raw "1223.4", reason "value_differs", resolution "lower_value"

  Scenario: S2.13 The better quality flag wins over the smaller value
    Given "15.06" UNCERTAIN and "16.00" GOOD for one sensor and instant
    When the ingest runs
    Then the stored value is 16.0 with quality GOOD, and the conflicts row has resolution "better_quality"

  Scenario: S2.14 Same value with different flags is a conflict
    Given "7.755" GOOD and "7.755" BAD for one sensor and instant
    When the ingest runs
    Then the stored quality is GOOD and the conflicts row has reason "quality_differs"

  Scenario: S2.15 File order never changes the result
    Given file A and file B, identical except the two conflicting rows swap places
    When each is ingested into its own empty database
    Then both databases hold identical readings and identical conflicts rows

  Scenario: S2.16 A text-signal conflict is stored as text
    Given valve_state "OPEN" GOOD and "CLOSED" GOOD at one instant
    When the ingest runs
    Then readings_state holds "CLOSED"
    And the conflicts row holds the text "CLOSED" kept and "OPEN" discarded

  Scenario: S2.17 An empty value is saved as a reading with no value
    Given a row with an empty value and quality BAD
    When the ingest runs
    Then a point exists at that instant with quality BAD and no value

  Scenario: S2.18 Out-of-order rows are counted, then stored normally
    Given a sensor's rows at 08:00:09 and then 08:00:05 in file order
    When the ingest runs
    Then the summary counts 1 out-of-order row for that series, and both points are stored

  Scenario: S2.19 A reading outside its experiment window is saved and flagged
    Given an ambient row 2 hours after its experiment's end_time
    When the ingest runs
    Then the point is stored
    And the summary counts 1 outside-window reading for that experiment and source
    And the command exits 1

  Scenario: S2.20 The summary records offsets and window edges per source
    Given the fixture with Z and +02:00 timestamps
    When the ingest runs
    Then the summary lists offset "Z" for absorber and "+02:00" for ambient
    And gives, per experiment and source, first and last reading relative to the window

  Scenario: S2.21 The counts balance, counted back from InfluxDB
    Given the fixture file
    When the ingest runs
    Then for every series, csv_rows = saved + exact_copies + conflict_losers + rejected
    And saved equals a COUNT queried from InfluxDB
    And the totals match the numbers written in the test before the run

  Scenario: S2.22 A second run changes nothing
    Given the fixture was ingested once
    When the ingest runs again
    Then the per-series counts, the conflicts rows and the exit code are identical

  Scenario: S2.23 A wrong fingerprint stops the run before any write
    Given a CSV whose SHA-256 differs from the --sha256 file
    When the ingest runs
    Then it exits 2 and the target database holds no points

  Scenario: S2.24 A missing database is refused, not created
    Given database "dac_missing" does not exist
    When the ingest runs with --database dac_missing
    Then it exits 2 and "dac_missing" still does not exist

  Scenario: S2.25 A refused line fails the whole batch
    Given a database whose readings_numeric.value column is already text
    When the ingest writes numeric readings to it
    Then it exits 3 and none of that batch's readings were saved

  Scenario: S2.26 Lost connections are retried, then the run stops
    Given a writer that fails with a connection error every time
    When the ingest sends a batch
    Then it tries 4 times in total and exits 3

  Scenario: S2.27 The summary matches the contract
    Given any ingest run, including a refused one
    When it ends
    Then ingest_summary.json validates against contracts/ingest_summary.schema.json
    And it records rows per second, batch size and batch count

  Scenario: S2.28 The real file ingests and balances
    Given the real CSV with its committed SHA-256
    When "python -m scripts.ingest" runs against dac_raw
    Then it exits 0
    And totals are csv_rows 520005, rejected 0, exact_copies 15, conflict_losers 10, saved 519980
    And all 150 series balance

  Scenario: S2.29 Ten conflicts in the real file, all decided by the tiebreak
    When readings_conflicts is queried after the real run
    Then it holds 10 rows, each with resolution "lower_value"

  Scenario: S2.30 Thirty out-of-order rows in the real file are counted
    Then the real-run summary reports 30 out-of-order rows

  Scenario: S2.31 Every source sits inside its experiment window
    Then for all 6 experiments the first reading is 0 s after start
    And the last is 1 s before end for absorber, hydrolyzer, plant and 60 s before end for ambient
    And 0 readings fall outside

  Scenario: S2.32 A second full run changes nothing
    When the real ingest runs a second time
    Then the series counts and all readings_conflicts rows are identical to the first run

  Scenario: S2.33 The raw file is unchanged
    After both real runs, the CSV's SHA-256 still equals data/raw/dac_raw_timeseries.sha256
  ```
- QA procedure:
  1. Dev stack up (`docker compose up -d`), note `docker ps` ids → `FLOW_RUN_ID=abc FLOW_PORT_BASE=18100 python scripts/verify_stack.py up` → exit 0; `curl http://localhost:18100/health` ok; `.env` shows 18100/18101; `health` exits 0 (S2.1).
  2. → `python scripts/verify_stack.py down` → `docker ps -a` and `docker volume ls` filtered by label `com.docker.compose.project=dac-verify-abc` are empty; dev ids unchanged; `docker compose config` names `dac-influxdb`/`dac-postgres`; `FLOW_RUN_ID=xyz ... health` exits non-zero (S2.2–S2.4).
  3. Private stack up. Throwaway database `qa_m2` via `POST /api/v3/configure/database` → `python -m scripts.ingest --csv tests/fixtures/ingest/slice.csv --experiments tests/fixtures/ingest/experiments.json --sha256 tests/fixtures/ingest/slice.sha256 --database qa_m2 --report-dir <tmp>` → exit 1; `ingest_rejects.csv` lists each defect with its reason (S2.6, S2.8–S2.10).
  4. → SQL on `qa_m2`: `SELECT time, value, quality FROM readings_numeric ORDER BY signal, time` shows UTC instants, sub-second points, the empty-value point (S2.5, S2.7, S2.17).
  5. → `SELECT * FROM readings_conflicts ORDER BY time` shows kept/discarded text, reason and resolution (S2.11–S2.14, S2.16).
  6. → `ingest_summary.json`: out-of-order, outside-window, offsets per source, every series balanced, totals equal the test's written numbers (S2.18–S2.21, S2.27).
  7. Re-run step 3 → identical counts and conflicts (S2.22).
  8. Copy the fixture, change one byte, run with the original `.sha256` into a fresh database → exit 2, no `readings_numeric` table (S2.23). `--database dac_missing` → exit 2; `GET /api/v3/configure/database?format=json` doesn't list it (S2.24). Drop throwaway databases.
  9. `python -m pytest tests/unit -k retry` and `python -m pytest tests/e2e -k "refused or order"` → pass (S2.15, S2.25, S2.26).
  10. Real CSV (copied in by verify-env): `python -m scripts.ingest` → exit 0, totals as S2.28; `SELECT resolution, COUNT(*) FROM readings_conflicts GROUP BY resolution` → `lower_value` 10; summary out-of-order 30 and window table as S2.31 (S2.28–S2.31).
  11. Save summary counts and `SELECT * FROM readings_conflicts ORDER BY time, signal`; run again; compare → identical. Recompute the CSV's SHA-256 with Python's `hashlib` → equals the committed one (S2.32, S2.33).
- Expected changes:
  - Stack: `scripts/verify_stack.py` (new); `docker-compose.yml` (overridable container names); `.env.example` (document overrides).
  - Ingest: `pipeline/collisions.py` (grouping pass over every instant; `find_collisions` built on it); `pipeline/signals.py` (new, 25 declared pairs and their table); `pipeline/ingest.py` (new, pure: parse, validate, resolve, reconcile); `pipeline/ingest_influx.py` (new: database check, synchronous batched writes with retry, count-back per experiment); `scripts/ingest.py` (new CLI).
  - Test data and CI: `tests/fixtures/ingest/` (~40 rows, experiments.json, .sha256), `.gitattributes`, `requirements.txt` (+ pinned `check-jsonschema`), `ci.yml` (contract step in lint job; `tests/e2e` in the integration job).
  - Reports: committed `reports/ingest_summary.json`, `reports/ingest_report.md`, `reports/ingest_rejects.csv` from the real run; `reports/M2.md` (two-layer milestone report: counts, measured throughput, partial-accept finding, owed review of the schema doc and rollup function).
  - Docs: ADR-0013 (ingestion: D1–D9 + decisions above), ADR-0007 addendum, `docs/schema.md` (conflicts table), `docs/ASSUMPTIONS.md` (close U-01, U-02, U-07, U-08, U-11), `docs/ROADMAP.md` (M2 phase and results). The dev `dac_raw` loaded for M2.5.
- Tests: `tests/unit/test_ingest_parse.py`, `test_ingest_resolve.py`, `test_ingest_retry.py`; `tests/e2e/test_ingest_cli.py` (CLI as a subprocess against a throwaway database, marked `influx`). Fixture counts written in the test before the code.
- After the judge: commit, push `m2-ingestion`, CI green, open `reports/M2.md` in the doc viewer. Merge to `master` waits for approval.

#### M2.5: Post-ingest profiling
- Depends on: M2 (see the done-rule note under Assumptions)
- Judge: verify · Touches: data (read-only)
- Gates: —
- Contract: `contracts/post_ingest_profile.schema.json` (shape of `post_ingest_profile.json`), example in `contracts/examples/post_ingest_profile.example.json`.
- Order of work: signal tables → SQL per measure, calibrated on one experiment against a SELECT pull (decision 14) → fixture and e2e → real run, committed outputs → ADR-0014, ASSUMPTIONS (U-05), ROADMAP, `reports/M2.5.md`.
- Command: `python -m scripts.post_ingest_profile [--database NAME] [--experiments PATH] [--report-dir DIR]`. Defaults: `dac_raw`, `data/raw/experiments.json`, `reports/`. Host and token from `.env`, as ingest. Exit 0 written; 2 refused (database missing, no readings, experiments file unreadable); 3 a profiling query failed, nothing written.
- Outputs in `--report-dir`: `post_ingest_profile.json` (contract), `post_ingest_profile.md` (same numbers as tables), and `post_ingest_profile_span_probe.txt` only when the span probe was refused.
- Output shape (the contract pins it):
  - `source` {database, experiments_file}; `experiments[]` {experiment_id, start, end}.
  - `span_probe` {start, end, succeeded, count|null, sum_of_per_experiment_counts, message_file|null}.
  - `series[]`, one per experiment × source × signal: identity, table, `nominal_interval_s`, `documented_min`, `documented_max`, `unit` (null where undefined); `points`, `points_without_value`, `quality` {GOOD, UNCERTAIN, BAD}; `values` {min, max, mean, stddev, median, p05, p95, below_documented_min, above_documented_max} (null for text); `states` {value: count} (text only, else null); `intervals_s` {count, min, median, p95, max, over_2x_nominal, over_10x_nominal, seconds_in_over_2x, longest[≤5] {start, end, seconds}} (the three nominal fields null for on-change signals); `runs` {count, median_samples, max_samples, max_seconds, longest[≤5] {start, end, samples, seconds, value}}; `differences` {count, mean, stddev, median_abs, p95_abs, max_abs} (null for text).
  - `relationships[]`, 4 per experiment, each with `experiment_id`, `kind`, `instants_matched`, `instants_unmatched`, `corr`, plus: `power_vs_voltage_x_current` → residual (power − V·I) mean, stddev, median, p05, p95, max_abs; relative residual median and p95 (power > 0 only); `power_zero_instants`; slope, intercept, r2. `co2_out_vs_co2_in` → ratio (out/in) median, p05, p95; `out_at_or_above_in`. `current_vs_current_setpoint` → difference (current − setpoint) mean, stddev, median, max_abs; `best_lag_s`; `corr_at_best_lag`. `pressure_drop_vs_air_flow` → slope, intercept, r2 against air_flow and against air_flow².
  - `timing` {seconds, queries} — the only part allowed to differ between runs.
- Example map (rule → one example; failure cases included):

  | Rule | Example |
  |---|---|
  | Intervals vs nominal | 1 Hz voltage with 10 s missing → median 1 s, max 11 s, 1 over 2× |
  | On-change signals not gap-counted | process_state, 3 rows → interval count 2, over_2x null |
  | Offset already applied | ambient +02:00 every 60 s → median 60 s |
  | Runs measured | 81.0 for 10 readings → max_samples 10, max_seconds 9 |
  | Range counted, not labelled | voltage 140.0 → above_documented_max 1 |
  | Empty value counted | one current, no value, BAD → points_without_value 1 |
  | Step-to-step change | pH 7.00 / 7.02 alternating → median_abs 0.02 |
  | Power cross-check | one instant +500 W → residual max_abs 500, median 0 |
  | CO2 ratio | out = 0.25 × in, one out > in → median 0.25, count 1 |
  | Lag found | current = setpoint delayed 3 s → best_lag_s 3 |
  | Pressure drop fit | ∝ air_flow² → r2 1.0 on air_flow², < 1.0 on air_flow |
  | Per-experiment bounding | EXP_004 two months earlier → only its own points |
  | Probe refused → recorded | server refuses → exit 0, succeeded false, message saved |
  | Missing database → refused | `dac_missing` → exit 2, not created |
  | Failed query → nothing written | → exit 3, no profile file |
  | Re-run identical | second run → same JSON except timing |
  | Real data covered | 150 series, 6 experiments, 24 relationships, 519,980 points |

- Fixture `tests/fixtures/profile/` (`readings.csv`, `experiments.json`, `readings.sha256`): hand-built, two experiments two months apart — EXP_001 2026-05-04T08:00:00Z–08:02:00Z and EXP_004 2026-03-02T08:00:00Z–08:02:00Z — with the defects below planted on purpose. It is ingested with `python -m scripts.ingest` into a throwaway database, then profiled. Every expected number is written into the test before the code. `.gitattributes` already pins `tests/fixtures/**`.
- Scenarios:
  ```gherkin
  Scenario: S25.1 Real sample intervals are measured against the nominal rate
    Given EXP_001 voltage at 1 s steps from 08:00:00 to 08:01:59 with 08:00:50 to 08:00:59 missing
    When the profile runs
    Then voltage intervals_s has median 1 and max 11
    And over_2x_nominal is 1, over_10x_nominal is 1 and seconds_in_over_2x is 11
    And intervals_s.longest[0] runs from 08:00:49 to 08:01:00

  Scenario: S25.2 On-change signals get interval stats but no nominal-based counts
    Given EXP_001 process_state with 3 rows
    When the profile runs
    Then its intervals_s.count is 2 and over_2x_nominal is null
    And states lists the 3 values with their counts

  Scenario: S25.3 Ambient readings stamped +02:00 show 60 s intervals
    Given EXP_001 ambient_temperature every 60 s, stamped +02:00
    When the profile runs
    Then its intervals_s.median is 60

  Scenario: S25.4 Runs of identical values are measured
    Given EXP_001 voltage holds 81.0 for 10 consecutive readings from 08:00:20
    When the profile runs
    Then voltage runs.max_samples is 10 and runs.max_seconds is 9
    And runs.longest[0] starts at 08:00:20 with value 81.0

  Scenario: S25.5 Values outside the documented range are counted, not labelled
    Given one EXP_001 voltage reading of 140.0 (documented max 130)
    When the profile runs
    Then voltage values.above_documented_max is 1 and values.max is 140.0

  Scenario: S25.6 Readings with no value and quality flags are counted
    Given one EXP_001 current point with no value and quality BAD
    When the profile runs
    Then current points_without_value is 1 and quality.BAD is 1

  Scenario: S25.7 Step-to-step change is measured
    Given EXP_001 solvent_pH alternating 7.00 and 7.02 every 5 s
    When the profile runs
    Then its differences.median_abs is 0.02 and differences.max_abs is 0.02

  Scenario: S25.8 Power is checked against voltage times current
    Given EXP_001 power equals voltage × current at every instant except one, where it is 500 W higher
    When the profile runs
    Then power_vs_voltage_x_current has residual median 0 and residual max_abs 500
    And instants_matched and instants_unmatched equal the counts written in the test

  Scenario: S25.9 Outlet CO2 is compared with inlet CO2
    Given EXP_001 co2_out_ppm = 0.25 × co2_in_ppm at every instant except one where out > in
    When the profile runs
    Then co2_out_vs_co2_in has ratio median 0.25 and out_at_or_above_in 1

  Scenario: S25.10 The lag of current behind its setpoint is found
    Given EXP_001 current equals current_setpoint delayed by 3 s
    When the profile runs
    Then current_vs_current_setpoint has best_lag_s 3 and corr_at_best_lag 1.0

  Scenario: S25.11 Pressure drop is compared with air flow and air flow squared
    Given EXP_001 pressure_drop = 0.00001 × air_flow² at every matched instant, with air_flow varying
    When the profile runs
    Then pressure_drop_vs_air_flow has r2 1.0 against air_flow² and r2 below 1.0 against air_flow

  Scenario: S25.12 Each experiment is profiled on its own
    Given the fixture's two experiments, two months apart
    When the profile runs
    Then every EXP_004 series' points equal the EXP_004 counts written in the test

  Scenario: S25.13 The full-span probe is recorded when it succeeds
    Given the fixture ingested
    When the profile runs
    Then span_probe.succeeded is true and span_probe.count equals sum_of_per_experiment_counts

  Scenario: S25.14 A refused span probe is recorded and the profile still completes
    Given a server that refuses the full-span query
    When the profile runs
    Then the command exits 0, span_probe.succeeded is false and span_probe.count is null
    And post_ingest_profile_span_probe.txt holds the server's message

  Scenario: S25.15 A missing database is refused, not created
    Given database "dac_missing" does not exist
    When the profile runs with --database dac_missing
    Then it exits 2, writes no profile file, and "dac_missing" still does not exist

  Scenario: S25.16 A failed query writes nothing
    Given a profiling query that fails and an empty report directory
    When the profile runs
    Then it exits 3 and no profile file exists in the report directory
    And a profile file already in the directory before the run is left as it was

  Scenario: S25.17 No verdict words in the output
    Given any finished profile
    Then grep -inE "stuck|suspicious|anomal|outlier|invalid|corrupt|error|wrong|fail|noise" on post_ingest_profile.json and post_ingest_profile.md finds nothing

  Scenario: S25.18 A second run gives the same profile
    Given a profile was written
    When the profile runs again on the same database
    Then post_ingest_profile.json is identical except the timing block

  Scenario: S25.19 The output matches the contract
    Given any finished profile
    Then post_ingest_profile.json validates against contracts/post_ingest_profile.schema.json

  Scenario: S25.20 The real data is fully covered
    Given the real CSV ingested into the target database
    When "python -m scripts.post_ingest_profile" runs
    Then it exits 0 with 150 series, 6 experiments and 4 relationships per experiment
    And the series points sum to 519980

  Scenario: S25.21 The real profile agrees with an independent pull
    Given the real profile
    When EXP_001 voltage is pulled with a plain SELECT and measured in Python
    Then points, values.min, values.max, intervals_s.median and runs.max_samples equal the profile's

  Scenario: S25.22 The committed real profile reproduces on a fresh stack
    Given a private stack with the real CSV freshly ingested
    When the profile runs into a temporary report directory
    Then its post_ingest_profile.json equals the committed reports/post_ingest_profile.json except timing
  ```
- QA procedure:
  1. Private stack up (`.workflow/verify-env.json`). Create throwaway database `qa_m25` via `POST /api/v3/configure/database`. `python -m scripts.ingest --csv tests/fixtures/profile/readings.csv --experiments tests/fixtures/profile/experiments.json --sha256 tests/fixtures/profile/readings.sha256 --database qa_m25 --report-dir <tmp1>` → exit 0.
  2. `python -m scripts.post_ingest_profile --database qa_m25 --experiments tests/fixtures/profile/experiments.json --report-dir <tmp2>` → exit 0. In `<tmp2>/post_ingest_profile.json` check the `series` entries in S25.1–S25.7 and S25.12, the `relationships` entries in S25.8–S25.11, and `span_probe` as S25.13.
  3. The grep in S25.17 on both output files → no match. `check-jsonschema --schemafile contracts/post_ingest_profile.schema.json <tmp2>/post_ingest_profile.json` → ok (S25.17, S25.19).
  4. Repeat step 2 into `<tmp3>`; compare both JSON files with `timing` removed → identical (S25.18).
  5. `--database dac_missing` → exit 2, report dir empty; `GET /api/v3/configure/database?format=json` does not list it (S25.15). `python -m pytest tests/unit -k "probe or failing_query"` → pass (S25.14, S25.16). Drop `qa_m25`.
  6. Real CSV (copied in by verify-env): `python -m scripts.ingest` → exit 0; `python -m scripts.post_ingest_profile --report-dir <tmp4>` → exit 0; 150 series, 6 experiments, 24 relationships, points sum 519,980 (S25.20).
  7. `SELECT time, value FROM readings_numeric WHERE experiment_id = 'EXP_001' AND signal = 'voltage' AND time >= '2026-05-04T08:00:00Z' AND time < '2026-05-04T10:00:00Z' ORDER BY time`; in plain Python compute count, min, max, median interval and longest run of equal values → equal to the profile (S25.21).
  8. Compare `<tmp4>/post_ingest_profile.json` with the committed `reports/post_ingest_profile.json`, `timing` removed → identical (S25.22).
- Expected changes:
  - `pipeline/signals.py`: `NOMINAL_INTERVAL_S` and `DOCUMENTED_RANGE` (low, high, unit), from `task/DATA_DICTIONARY.md`.
  - `pipeline/profiling.py` (new, pure): rounding, result shaping, lag search, Markdown rendering.
  - `pipeline/profiling_sql.py` (new): the SQL per measure and its runner; reuses `list_databases` from `pipeline/ingest_influx.py`.
  - `scripts/post_ingest_profile.py` (new CLI, mirrors `scripts/ingest.py`: config, refuse, run, write at end).
  - `tests/fixtures/profile/` (new). `.gitignore`: `.flow-tmp/` (the real-run Checks row writes there, so the worktree stays clean). CI: contract step for the new schema in the lint job (e2e already runs in the integration job).
  - Committed outputs from the dev `dac_raw`: `reports/post_ingest_profile.json`, `reports/post_ingest_profile.md`; `reports/M2.5.md` (two-layer milestone report).
  - Docs: ADR-0014 (profiling method: decisions 2–10, plus any SQL-to-pull fallback); `docs/ASSUMPTIONS.md` (U-05 narrowed with the probe result, open only for M6); `docs/ROADMAP.md` (M2.5 phase and results).
- Tests: `tests/unit/test_profiling.py` (tables cover the 23 numeric pairs and not the 2 text pairs; rounding; lag search on a synthetic 3 s shift and the tie rule; refused probe and failing query with a fake client — S25.14, S25.16); `tests/e2e/test_profile_cli.py` (fixture ingest + profile as a subprocess into a throwaway database, marked `influx`: S25.1–S25.13, S25.15, S25.17–S25.19, plus a SELECT-pull cross-check on the fixture). S25.20–S25.22 run on the real data (Checks row and QA steps 6–8).
- After the judge: commit, push `m2.5-profiling`, CI green, open `reports/M2.5.md` in the doc viewer. Merge waits for approval.

#### M3: Quality and cleaning pipeline (C, D)
- Depends on: M2, M2.5 (see the done-rule notes under Assumptions)
- Judge: verify · Touches: data (writes new tables in `dac_raw`, rebuilds `dac_rollup`; raw tables read-only)
- Gates: —
- Contract: `contracts/cleaning_summary.schema.json` (shape of `cleaning_summary.json`), example in `contracts/examples/cleaning_summary.example.json`. The three InfluxDB tables are documented in `docs/schema.md` (their shape is checked by the e2e tests, not by a schema file).
- Order of work: measure Core behaviours (decision 15) → policy table + fingerprint + step-size test → pure rules, unit-tested → fixture and e2e → calibrate on EXP_001, EXP_004, then all six (decision 20) → real run, committed outputs → rollup over the verdict, rebuild `dac_rollup` → policy doc, ADR-0015, schema doc, ASSUMPTIONS, ROADMAP, `reports/M3.md`.
- Commands:
  - `python -m scripts.clean [--database NAME] [--experiments PATH] [--report-dir DIR]`. Defaults `dac_raw`, `data/raw/experiments.json`, `reports/`. Host and token from `.env`. Exit codes: decision 21. Outputs in `--report-dir`: `cleaning_summary.json` (contract), `cleaning_report.md` (same numbers as tables, plus the hand-check samples). Written only after the read-back balances or fails (exit 0 or 4); nothing written on exit 2 or 3.
  - `python -m scripts.rollup [--database NAME] [--rollup-database NAME] [--experiments PATH]`. Defaults `dac_raw`, `dac_rollup`, `data/raw/experiments.json`. Reads `readings_processed` for the current `POLICY_VERSION`, one experiment window at a time. Prints buckets written per experiment.
- Tables (all in the raw database, tags `experiment_id`, `source`, `signal`, `policy_version`; time = the reading's instant unless noted):
  - `readings_processed`: fields `value_raw` float (absent when the raw point has no value), `value` float (absent when excluded), `quality` string (acquisition flag), `verdict` string (`accepted` | `excluded`), `reason` string (empty when accepted), `flags` string.
  - `state_intervals`: time = the event's instant; fields `value_raw` string, `value` string (absent when excluded), `quality`, `verdict`, `reason`, `flags`, `end_ns` int (exclusive end), `seconds` float.
  - `quality_intervals`: extra tag `kind` (`gap` | `flatline`); time = interval start; fields `end_ns` int, `seconds` float, `points` int (flatline: readings flagged; gap: 0).
  - `readings_rollup` (rollup database): ADR-0011 columns plus `count_no_value` int.
- Summary shape (the contract pins it):
  - `schema_version` 1; `policy_version`; `source` {database, experiments_file}; `experiments[]` {experiment_id, start, end}.
  - `series[]`, one per experiment × source × signal: identity, `table` (`readings_numeric` | `readings_state`), `raw_points`, `processed_points`, `accepted`, `excluded`, `excluded_by_reason` {code: count} (primary reason, every code present with 0), `flags` {code: count} (all codes that fired, plus `outside_typical_range`), `gaps` {count, seconds, longest[≤5] {start, end, seconds}} (null for state signals), `flatline_intervals` {count, seconds} (null for state signals and `current_setpoint`).
  - `totals` {raw_points, processed_points, accepted, excluded, excluded_by_reason, flags, gap_intervals, gap_seconds, flatline_intervals}.
  - `reconciliation` {balanced, series_checked, unbalanced[] {experiment_id, source, signal, raw_points, processed_points}, raw_unchanged (bool: raw table counts before = after)}.
  - `samples[]` per reason code that fired: up to 3 readings (first, middle, last by time) with `experiment_id, source, signal, time, value_raw, reason, neighbours[]` (up to 5 raw points each side: time, value_raw, verdict).
  - `timing` {seconds, queries, points_written} — the only part allowed to differ between runs.
- Example map (rule → one example; failure and boundary cases included):

  | Rule | Example |
  |---|---|
  | One row per reading | 600 raw voltage points → 600 processed rows |
  | Raw copied unchanged | accepted 100.73 → value_raw 100.73, value 100.73 |
  | Excluded has no value, has reason | BAD conductivity → value absent, reason `flag_bad` |
  | No value | empty current point → `no_value` |
  | UNCERTAIN | one pressure point UNCERTAIN → `flag_uncertain` |
  | Physical limit | solvent pH 27.4 → `outside_physical_limits`; pH exactly 14.0 → inside (bounds inclusive; unit test) |
  | Typical range is a note | current −0.5 A → accepted, flags `outside_typical_range` |
  | Spike | one voltage 140 among ~100 → `spike`, its neighbours accepted |
  | Step is not a spike | voltage 100 → 110 and holds → no `spike` |
  | Ramp is not a spike | current 150 → 210 at 4 A/s → no `spike` |
  | Exact run | solvent temperature 30.22 × 40 → `flatline`; a run of 3 → not |
  | Chance flat steps | pH, 7 of 13 steps small but never 5 in a row → no `flatline`; 4 in a row → none; 5 in a row in a mostly flat window → `flatline` |
  | Solar slow ramp | dawn ramp, 25 readings rising 0.8 to 5 kW per step → no `flatline` |
  | Solar frozen | solar 312.4 × 12 → `flatline` |
  | Noise collapse | air flow noise drops to 5 % of normal → `flatline`, boundary within 1 reading |
  | Setpoint exempt | current_setpoint 150 × 300 → accepted |
  | Solar night exempt | solar 0.0 × 20 → accepted |
  | Conflict | conflicting instant → `conflicting_duplicate`; exact-copy instant → accepted |
  | Priority | BAD and outside limits → reason `flag_bad`, flags both |
  | Gap | 10 s hole in 1 Hz voltage → one gap row, 11 s; no rows invented |
  | On-change no gap | process_state 3 events → no gap rows |
  | State carried forward | STARTUP 08:00, STEADY_STATE 08:02 → first interval 120 s, last to experiment end |
  | Unknown state | `WARMUP` → `unknown_state` |
  | Raw untouched | raw table dumps before = after |
  | Re-run identical | second run → same tables, same summary except timing |
  | Missing database | `dac_missing` → exit 2, not created |
  | Failures | write fails → exit 3; read-back short → exit 4 |
  | Rollup | one bucket hand-computed; a no-value point → `count_no_value` 1 |
  | Real data | 150 series balanced, 519,980 numeric+state points |

- Fixture `tests/fixtures/clean/` (`readings.csv`, `experiments.json`, `readings.sha256`, `make_fixture.py`): one experiment `EXP_001`, 2026-05-04T08:00:00Z–08:10:00Z, built by a deterministic stdlib script with the defects planted at stated instants. Noise is a fixed alternating pattern of ± half the signal's declared step size (so every normal step equals the step size and is never flat), not random, so the expected verdicts follow from the construction alone. The CSV and its checksum are committed; the script is kept for review, not run in CI. It is ingested with `python -m scripts.ingest` into a throwaway database, then cleaned. Every expected verdict is written into the test from the construction, before the cleaning code exists. Planted (instants relative to 08:00:00):
  - voltage 1 Hz around 100 V: spike 140.0 at +120 s; step to 110 V from +300 s; hole +400 s to +409 s (points at +399 and +410); one point at 140 V that is also BAD at +500 s (priority).
  - current 1 Hz: near 0 A from 0 to +99 s, with −0.5 A at +30 s; one point with no value at +60 s; step to 150 A at +100 s; ramp 150 → 210 A at 4 A/s from +200 s to +215 s; 210 A after.
  - current_setpoint 1 Hz: 0 to +99 s, 150 from +100 s, 210 from +200 s (holds 400 s).
  - solvent_temperature 0.2 Hz around 31 °C: 30.22 for 40 readings from +100 s to +295 s; one value 3 times at +20, +25, +30 s.
  - air_flow 1 Hz around 1,200 m³/h: from +360 s around 20 m³/h with steps of 5 % of normal.
  - solvent_pH 0.2 Hz around 7.6: 27.4 at +250 s.
  - pressure 1 Hz: one UNCERTAIN at +45 s.
  - conductivity 0.2 Hz: 10 BAD readings from +150 s.
  - available_solar_power 1/60 Hz: 0.0 for all 10 readings.
  - co2_in_ppm 0.5 Hz: one conflicting duplicate pair at +80 s and one exact copy at +90 s.
  - process_state: STARTUP at 0, STEADY_STATE at +120 s, `WARMUP` at +400 s, SHUTDOWN at +540 s. valve_state: OPEN at 0.
- Scenarios:
  ```gherkin
  Scenario: S3.1 Every raw reading gets exactly one processed row
    Given the clean fixture ingested
    When the cleaning runs
    Then for every series the readings_processed (or state_intervals) row count equals the raw row count
    And the summary's raw_points and processed_points match those counts

  Scenario: S3.2 Raw values are copied unchanged and accepted values are not altered
    Given the clean fixture cleaned
    Then for every processed row value_raw equals the raw value at that instant
    And for every accepted row value equals value_raw

  Scenario: S3.3 An excluded reading has no processed value and a reason
    Given the clean fixture cleaned
    Then every excluded row has no value and a non-empty reason
    And every accepted row has an empty reason

  Scenario: S3.4 Acquisition flags BAD and UNCERTAIN exclude a reading
    Given conductivity is BAD for 10 readings from +150 s and pressure is UNCERTAIN at +45 s
    When the cleaning runs
    Then those conductivity rows have reason flag_bad and the pressure row has reason flag_uncertain

  Scenario: S3.5 A point without a value is excluded
    Given current has a point with no value at +60 s
    When the cleaning runs
    Then that row has no value_raw, no value and reason no_value

  Scenario: S3.6 A value outside physical limits is excluded
    Given solvent_pH is 27.4 at +250 s
    When the cleaning runs
    Then the +250 s row has reason outside_physical_limits and its flags do not contain spike
    And the solvent_pH rows at +245 s and +255 s are accepted

  Scenario: S3.7 Outside the typical range but physically possible is kept with a note
    Given current is -0.5 A at +30 s among readings near 0 A
    When the cleaning runs
    Then that row is accepted with value -0.5 and flags outside_typical_range

  Scenario: S3.8 A single spike is excluded and its neighbours are kept
    Given voltage is 140.0 at +120 s among readings around 100 V
    When the cleaning runs
    Then the +120 s row has reason spike
    And the rows from +115 s to +125 s other than +120 s are accepted

  Scenario: S3.9 A step and a ramp are not spikes
    Given voltage steps from 100 V to 110 V at +300 s, current steps from 0 A to 150 A at +100 s and ramps from 150 A to 210 A from +200 s
    When the cleaning runs
    Then no voltage row from +290 s to +310 s and no current row from +95 s to +105 s or from +195 s to +220 s has spike in flags

  Scenario: S3.10 An exact repeat run is a flatline, a short run is not
    Given solvent_temperature holds 30.22 for 40 readings from +100 s and repeats one value 3 times at +20 s
    When the cleaning runs
    Then exactly those 40 rows have flatline in flags, and the readings at +20 s to +30 s do not
    And quality_intervals holds one flatline row for solvent_temperature from +100 s to +295 s with points 40

  Scenario: S3.11 Collapsed noise is a flatline with a sharp boundary
    Given air_flow noise falls to 5 percent of normal from +360 s
    When the cleaning runs
    Then every air_flow row from +360 s to the end has reason flatline
    And no air_flow row before +360 s has flatline in flags

  Scenario: S3.12 A setpoint hold and solar zeros are not flatlines
    Given current_setpoint holds 210 for 400 s and available_solar_power is 0.0 for all 10 readings
    When the cleaning runs
    Then every current_setpoint and available_solar_power row is accepted

  Scenario: S3.13 A conflicting duplicate instant is excluded, an exact copy is not
    Given co2_in_ppm had a conflicting pair at +80 s and an exact copy at +90 s at ingest
    When the cleaning runs
    Then the +80 s row has reason conflicting_duplicate and the +90 s row is accepted

  Scenario: S3.14 Priority picks the first reason and flags list them all
    Given voltage at +500 s is 140 V and BAD
    When the cleaning runs
    Then its reason is flag_bad and its flags contain flag_bad and spike

  Scenario: S3.15 A gap is recorded as an interval and nothing is invented
    Given voltage has no points from +400 s to +409 s
    When the cleaning runs
    Then quality_intervals holds one gap row for voltage from +399 s to +410 s with seconds 11
    And no processed voltage row exists between +400 s and +409 s
    And no gap row exists for process_state or valve_state

  Scenario: S3.16 State events are carried forward to the next event without expiry
    Given process_state events STARTUP at 0, STEADY_STATE at +120 s, WARMUP at +400 s, SHUTDOWN at +540 s
    When the cleaning runs
    Then state_intervals holds 4 process_state rows with seconds 120, 280, 140 and 60
    And the WARMUP row has reason unknown_state and no value

  Scenario: S3.17 The summary reconciles every series
    Given the clean fixture cleaned
    Then for every summary series raw_points = accepted + excluded and excluded = the sum of excluded_by_reason
    And reconciliation.balanced is true and reconciliation.raw_unchanged is true

  Scenario: S3.18 The raw tables are not changed by cleaning
    Given dumps of readings_numeric, readings_state and readings_conflicts before cleaning
    When the cleaning runs
    Then the same dumps after cleaning are identical

  Scenario: S3.19 A second run gives the same result
    Given the cleaning ran once
    When it runs again on the same database
    Then dumps of the three processed tables are identical and cleaning_summary.json differs only in timing

  Scenario: S3.20 A missing database is refused, not created
    Given database "dac_missing" does not exist
    When the cleaning runs with --database dac_missing
    Then it exits 2, writes no summary, and "dac_missing" still does not exist

  Scenario: S3.21 A failed write or query exits 3 and writes no summary
    Given a gateway that fails on a write
    When the cleaning runs
    Then it exits 3 and no cleaning_summary.json exists in an empty report directory

  Scenario: S3.22 A short read-back exits 4
    Given a gateway that reads back one processed point fewer than was written for one series
    When the cleaning runs
    Then it exits 4, the summary is written, reconciliation.balanced is false and that series is listed in unbalanced

  Scenario: S3.23 The summary matches the contract
    Given any finished cleaning run
    Then cleaning_summary.json validates against contracts/cleaning_summary.schema.json

  Scenario: S3.24 The policy table is complete, consistent and versioned
    Given pipeline/cleaning_policy.py
    Then it declares a policy for all 25 signal pairs, physical limits that contain each typical range, and a step size equal to the median of the profile's differences.median_abs per signal
    And the fingerprint of the table equals the one pinned for POLICY_VERSION

  Scenario: S3.25 The rollup aggregates over the verdict
    Given the clean fixture cleaned
    When "python -m scripts.rollup" runs into a throwaway rollup database
    Then the voltage bucket at 08:02:00 has count_all, min_all, max_all over all 60 raw values, count_included = accepted rows, mean over accepted rows only, and policy_version = POLICY_VERSION, equal to the numbers written in the test

  Scenario: S3.26 The rollup counts a point with no value instead of failing
    Given readings_processed rows for one current bucket in a throwaway database, one of them without value_raw
    When the rollup runs over that database
    Then it exits 0 and that bucket has count_no_value 1 and count_all over the other rows

  Scenario: S3.27 The real data is fully covered and balanced
    Given the real CSV ingested
    When "python -m scripts.clean" runs
    Then it exits 0 with 150 series, raw_points summing to 519980, reconciliation.balanced true and raw_unchanged true

  Scenario: S3.28 The known features of the real data are excluded with the named reason
    Given the real data cleaned
    Then EXP_001 voltage 412.0, EXP_003 solvent_pH 27.4 and EXP_005 electrolyte_temperature -50.0 have reason outside_physical_limits
    And EXP_003 fan_speed 0.0, EXP_004 pump_speed 0.0 and EXP_002 current 0.0 at 2026-05-11T09:33:20Z have reason spike
    And EXP_003 solvent_temperature's 240 readings of 30.22 and EXP_006 co2_out_ppm's 1350 readings of 38.0 have flatline in flags
    And EXP_004 air_flow's 3600 readings below 1000 m³/h have flatline in flags and none of its readings at or above 1000 does
    And EXP_001 conductivity's 60 BAD and EXP_003 acid_pH's 40 BAD readings have reason flag_bad
    And EXP_004 pressure's 200 and EXP_005 ambient_pressure's 30 UNCERTAIN readings have reason flag_uncertain
    And EXP_004 pressure -3.1 is excluded
    And every instant with a readings_conflicts row has conflicting_duplicate in flags
    And the gap rows per series equal that series' intervals_s.over_2x_nominal in reports/post_ingest_profile.json

  Scenario: S3.29 No spike or flatline outside the known features
    Given the real data cleaned
    Then spike appears in flags only in EXP_003 fan_speed, EXP_004 pump_speed, EXP_002 current and EXP_006 fan_speed, one reading each
    And the EXP_006 fan_speed reading is at 11:10:17 with reason conflicting_duplicate
    And flatline appears only in EXP_003 solvent_temperature, EXP_006 co2_out_ppm, EXP_004 air_flow, EXP_001 conductivity and EXP_003 acid_pH

  Scenario: S3.30 The report carries hand-check samples
    Given the real data cleaned
    Then cleaning_report.md lists, for every reason code that fired, its first, middle and last excluded reading with up to 5 raw neighbours on each side

  Scenario: S3.31 The real cleaning reproduces on a fresh stack
    Given a private stack with the real CSV freshly ingested
    When the cleaning runs into a temporary report directory
    Then its cleaning_summary.json equals the committed reports/cleaning_summary.json except timing

  Scenario: S3.32 Scattered or short stretches of small steps are not a flatline
    Given a 0.2 Hz solvent_pH series with the normal step size where 7 of 13 consecutive steps are below 0.2 × step but never 5 in a row
    When the rules run
    Then no reading has flatline in flags
    And with 4 small steps in a row inside a mostly flat window no reading has flatline
    And with 5 small steps in a row inside a mostly flat window exactly those 6 readings have flatline

  Scenario: S3.33 Solar counts only an exactly repeated value as a flatline
    Given available_solar_power rising for 25 readings in steps of 0.8 to 5 kW
    And elsewhere a value of 312.4 held for 12 readings, and 0.0 held for 20 readings
    When the rules run
    Then no reading of the ramp or of the zeros has flatline in flags
    And exactly the 12 readings of 312.4 have flatline in flags

  Scenario: S3.34 The policy document matches the policy table
    Given docs/cleaning_policy.md and pipeline/cleaning_policy.py
    Then the document has one row per signal pair, 25 in all
    And each row's physical limits, step size and the rules that apply equal the declared table
  ```
  Note on S3.29: the list is the plan's prediction from the profile, written before any rule ran (decision 19), plus the EXP_006 fan_speed spike accepted at the re-plan (decision 26). If calibration finds a spike or flatline elsewhere, execute stops and raises it as a narrow question; the list is changed only through `/flow:plan M3`.
- QA procedure:
  1. Private stack up (`.workflow/verify-env.json`). Create throwaway database `qa_m3` via `POST /api/v3/configure/database`. `python -m scripts.ingest --csv tests/fixtures/clean/readings.csv --experiments tests/fixtures/clean/experiments.json --sha256 tests/fixtures/clean/readings.sha256 --database qa_m3 --report-dir <tmp1>` → exit 0.
  2. Dump `readings_numeric`, `readings_state`, `readings_conflicts` of `qa_m3` (`SELECT * … ORDER BY` tags, time) to files A.
  3. `python -m scripts.clean --database qa_m3 --experiments tests/fixtures/clean/experiments.json --report-dir <tmp2>` → exit 0. Query `readings_processed`, `state_intervals`, `quality_intervals` of `qa_m3` and check the rows named in S3.1–S3.16; check `<tmp2>/cleaning_summary.json` as S3.17; `check-jsonschema --schemafile contracts/cleaning_summary.schema.json <tmp2>/cleaning_summary.json` → ok (S3.23).
  4. Dump the raw tables again → identical to A (S3.18). Run step 3 again into `<tmp3>`; dump the processed tables before and after → identical; summaries equal without `timing` (S3.19).
  5. `--database dac_missing` → exit 2, `<tmp4>` empty, `GET /api/v3/configure/database?format=json` does not list it (S3.20). `python -m pytest tests/unit -k "exit_3 or exit_4 or policy"` → pass (S3.21, S3.22, S3.24).
  6. Create `qa_m3_rollup`; `python -m scripts.rollup --database qa_m3 --rollup-database qa_m3_rollup --experiments tests/fixtures/clean/experiments.json` → exit 0; check the buckets in S3.25 and S3.26. Drop `qa_m3` and `qa_m3_rollup`.
  7. Real CSV (copied in by verify-env): `python -m scripts.ingest` → exit 0; `python -m scripts.clean --report-dir <tmp5>` → exit 0; check S3.27–S3.30 against `<tmp5>` and the `readings_processed` / `quality_intervals` tables of `dac_raw`; for S3.28's gap line compare with `reports/post_ingest_profile.json`.
  8. Compare `<tmp5>/cleaning_summary.json` with the committed `reports/cleaning_summary.json`, `timing` removed → identical (S3.31). `python -m scripts.rollup` → exit 0.
- Expected changes:
  - `pipeline/cleaning_policy.py` (new): `POLICY_VERSION`, `POLICY_FINGERPRINT`, per-signal class (measured / commanded / state), physical limits, step size, exemptions, window constants, reason codes and order.
  - `pipeline/cleaning.py` (new, pure): rules, verdicts, gap and flatline intervals, state intervals, summary shaping, sample selection, Markdown rendering.
  - `pipeline/cleaning_influx.py` (new): series pulls per experiment window, conflicts lookup, line protocol for the three tables (reusing the escaping in `pipeline/ingest.py`), batched writes with `send_with_retry` and `list_databases` from `pipeline/ingest_influx.py`, read-back counts, raw-table counts.
  - `scripts/clean.py`, `scripts/rollup.py` (new CLIs, mirror `scripts/post_ingest_profile.py`: config, refuse, run, write at end).
  - `pipeline/rollup.py` (`Sample.value` may be `None`; `count_no_value`), `pipeline/rollup_run.py` (source `readings_processed`, predicate `verdict = accepted`, one policy version).
  - `contracts/cleaning_summary.schema.json` + example (written at plan time). CI lint job: contract step for it.
  - `tests/fixtures/clean/` (new).
  - Committed real outputs: `reports/cleaning_summary.json`, `reports/cleaning_report.md`; `reports/M3.md` (two-layer milestone report).
  - Docs: `docs/cleaning_policy.md` (per-signal table line by line; the nine defect kinds; why pH, a plant state and an integrated energy value are handled differently; the alignment rule M4 will use: polled signals as-of within 2 × nominal, states carried forward), ADR-0015, `docs/schema.md` (three tables, rollup column), `docs/ASSUMPTIONS.md` (close U-04, U-09, U-10, U-12; narrow U-06; add A-05), `docs/decisions/README.md`, `docs/ROADMAP.md` (M3 phase, results).
- Tests: `tests/unit/test_cleaning.py` (every rule on synthetic series, including the must-not-fire cases, priority, state intervals, gap intervals, summary reconciliation, sample selection; fake gateway for S3.21, S3.22), `tests/unit/test_cleaning_policy.py` (S3.24), `tests/unit/test_rollup.py` (no-value point, `count_no_value`), `tests/integration/test_rollup_run.py` (rewritten for the processed source; the hand-computed bucket stays), `tests/e2e/test_clean_cli.py` (fixture ingest + clean + rollup as subprocesses into throwaway databases, marked `influx`: S3.1–S3.20, S3.23, S3.25, S3.26, plus a SELECT-pull recompute of every verdict on the fixture). S3.27–S3.31 run on the real data (Checks rows, QA steps 7–8). Added at the re-plan: S3.32, S3.33 in `tests/unit/test_cleaning.py`; S3.21, S3.22 in `tests/unit/test_clean_cli.py` (fake gateway); S3.26 in `tests/integration/test_rollup_run.py`; S3.34 in `tests/unit/test_policy_doc.py`.
- Tasks (decision 27; checked with `lane.js tasks`):
  - T1 [W1] Amend the flatline rule (decisions 24, 25), re-pin the fingerprint, unit-test every rule including the must-not-fire cases, priority, gap, flatline and state intervals, summary reconciliation and sample selection. Owns: `pipeline/cleaning.py`, `pipeline/cleaning_policy.py`, `tests/unit/test_cleaning.py`, `tests/unit/test_cleaning_policy.py`. Scenarios: S3.24, S3.32, S3.33.
  - T2 [W1] Rollup over the verdict: source `readings_processed`, one policy version, included columns over `verdict = accepted`, `count_no_value`, the `scripts.rollup` CLI and exit codes. Owns: `pipeline/rollup.py`, `pipeline/rollup_run.py`, `scripts/rollup.py`, `tests/unit/test_rollup.py`, `tests/integration/test_rollup_run.py`. Scenarios: S3.26.
  - T3 [W2] Clean fixture, InfluxDB layer and `scripts.clean` CLI finished, end-to-end tests of clean and rollup on the fixture, fake-gateway tests for exit 3 and 4. Owns: `pipeline/cleaning_influx.py`, `scripts/clean.py`, `tests/fixtures/clean/**`, `tests/e2e/test_clean_cli.py`, `tests/unit/test_clean_cli.py`. Scenarios: S3.1, S3.2, S3.3, S3.4, S3.5, S3.6, S3.7, S3.8, S3.9, S3.10, S3.11, S3.12, S3.13, S3.14, S3.15, S3.16, S3.17, S3.18, S3.19, S3.20, S3.21, S3.22, S3.23, S3.25. After: T1, T2.
  - T4 [W3] Real data: calibrate EXP_001, EXP_004, then all six against a plain-Python recompute (decision 20); stop without changing thresholds on any hit outside S3.29; full run into `reports/`; reproduce on a fresh private stack; rebuild `dac_rollup`. Owns: `reports/cleaning_summary.json`, `reports/cleaning_report.md`, `.flow-tmp/**`. Scenarios: S3.27, S3.28, S3.29, S3.30, S3.31. After: T3.
  - T5 [W4] Write-up: `docs/cleaning_policy.md`, ADR-0015, `docs/schema.md`, `docs/ASSUMPTIONS.md`, `docs/decisions/README.md`, `docs/ROADMAP.md`, `reports/M3.md`, CI contract step, doc-vs-table test. Owns: `docs/**`, `reports/M3.md`, `.github/workflows/ci.yml`, `tests/unit/test_policy_doc.py`. Scenarios: S3.34. After: T4.
- After the judge: commit, push `m3-cleaning`, CI green, open `reports/M3.md` in the doc viewer. Merge waits for approval.

#### M4: Derived metrics (E)
- Depends on: M3 (accepted as done, M4 decision 2)
- Judge: verify · Touches: data (writes `metrics_series` in `dac_raw` and two new Postgres tables; every other table read-only)
- Gates: —
- Contract: `contracts/metrics_summary.schema.json` (shape of `metrics_summary.json`), example `contracts/examples/metrics_summary.example.json` (shaped like the fixture run; its counts and coverages follow the fixture construction, its metric values are illustrative and are not the expected test values). `parameters` keys are exactly the keys of `POLICY` in `pipeline/metrics.py`. The InfluxDB table and the Postgres tables are pinned below and in `docs/schema.md`; their shape is checked by the integration and e2e tests, not by a schema file.
- Order of work: T1 ∥ T2 → T3 → T4 (calibrate EXP_001, EXP_004, then all six; decision 19) → T5.
- Command: `python -m scripts.metrics [--database NAME] [--experiments PATH] [--report-dir DIR] [--policy-version V] [--pg-schema NAME]`. Defaults `dac_raw`, `data/raw/experiments.json`, `reports/`, `pipeline.cleaning_policy.POLICY_VERSION`, `public`. InfluxDB host/token and `POSTGRES_*` from `.env`. `--pg-schema` sets the Postgres `search_path` (tests use a throwaway schema, like `tests/integration/test_metadata_loader.py`). Exit codes: decision 17. Outputs in `--report-dir`: `metrics_summary.json` (contract) and `metrics_report.md` (rendered from the summary: one table of metrics per experiment with value, unit, coverage, status; the power check; plausibility; per-signal quality).
- Stores (decision 14):
  - InfluxDB `metrics_series` (target raw database): tags `experiment_id`, `metric`, `metrics_version`, `policy_version`; field `value` float; time = the instant. Metrics and units: `power_computed` W, `power_residual` W, `capture_efficiency` fraction, `capture_rate` kg/h. Only instants where the value exists are written.
  - Postgres `experiment_metrics`: `experiment_id text REFERENCES experiment`, `metrics_version text`, `policy_version text NOT NULL`, `metric text`, `value double precision NULL`, `unit text NOT NULL`, `coverage double precision NULL`, `status text NULL CHECK (status IN ('complete','partial','none'))`; PK `(experiment_id, metrics_version, metric)`.
  - Postgres `signal_quality`: `experiment_id text REFERENCES experiment`, `metrics_version text`, `policy_version text NOT NULL`, `source text`, `signal text`, `nominal_interval_s double precision NULL`, `present integer`, `expected integer NULL`, `accepted integer`, `bad integer`, `uncertain integer`, `completeness`, `valid_fraction`, `bad_fraction`, `uncertain_fraction` (double precision NULL); PK `(experiment_id, metrics_version, source, signal)`.
- Metric names (fixed set of 13, every experiment has all of them): `energy_kwh` kWh, `energy_logged_kwh` kWh, `energy_relative_difference` fraction, `mean_power_kw` kW, `capture_efficiency_mean` fraction, `co2_captured_kg` kg, `co2_inlet_kg` kg, `capture_rate_mean_kg_h` kg/h, `sec_kwh_per_kg` kWh/kg, `completeness`, `valid_fraction`, `bad_fraction`, `uncertain_fraction` (fraction). Coverage per metric: the energy and mean-power metrics use their own series' covered time; `energy_relative_difference` and `sec_kwh_per_kg` the overlap; the CO2 metrics the capture series; efficiency its own series; the four quality shares have null coverage and status.
- Summary shape (the contract pins it): `schema_version` 1; `metrics_version`; `policy_version`; `source` {database, experiments_file, pg_schema}; `parameters` {the policy table of decision 15}; `experiments[]` {experiment_id, start, end, duration_s, `metrics` {name: {value, unit, coverage, status}}, `power_check` {instants_compared, within_tolerance, within_tolerance_fraction, residual_median_w, residual_p95_abs_w, residual_max_abs_w}, `efficiency_check` {instants, at_or_below_zero}, `series_written` {power_computed, power_residual, capture_efficiency, capture_rate}, `signals[]` (25 per experiment: source, signal, nominal_interval_s, present, expected, accepted, bad, uncertain, completeness, valid_fraction, bad_fraction, uncertain_fraction), `plausibility[]` {check, passed, value, limit}}; `plausibility_failed` (count of `passed = false`); `reconciliation` {balanced, influx_series_checked, postgres_rows_checked, mismatches[] {store, experiment_id, name, written, read_back}, inputs_unchanged}; `timing` {seconds, queries, points_written} — the only part allowed to differ between runs. Floats rounded to 9 significant digits; lists sorted (experiments by id, signals by source then signal, plausibility by check name).
- Interfaces between tasks (pinned so T1 and T2 can run in parallel):
  - T1, `pipeline/metrics.py` (pure; stdlib only): `METRICS_VERSION`, `METRICS_FINGERPRINT`, `POLICY` (the decision 15 mapping), `METRIC_UNITS` (name → unit, the 13 names), `SERIES_UNITS` (the 4 series names → unit). Series are `list[tuple[int, float]]` (ns, value), ascending. Functions: `power_series(voltage, current) -> list[tuple[int, float]]`; `residual_series(power, voltage, current)`; `within_tolerance(residual, ui) -> bool`; `efficiency_series(co2_in, co2_out)`; `capture_series(co2_in, co2_out, air_flow, temperature, pressure, *, inlet=False)`; `as_of(series, t_ns, max_age_ns) -> float | None`; `covered_intervals(series, max_spacing_s) -> list[tuple[int, int]]`; `integrate(series, max_spacing_s) -> tuple[float, float]` (integral in value·s, covered seconds); `overlap(a, b) -> list[tuple[int, int]]`; `integrate_over(series, intervals) -> float`; `status_for(value, coverage) -> str`; `experiment_metrics(inputs: ExperimentInputs, duration_s) -> ExperimentResult` (dataclasses defined in T1, holding the 13 metric objects, power_check, efficiency_check and the four series); `signal_quality(counts, duration_s) -> list[dict]` and `experiment_quality(rows) -> dict`; `plausibility(result) -> list[dict]`. T3 may rely only on these names.
  - T2, `pipeline/metrics_store.py`: `MetricsGateway` (InfluxDB): `tables() -> set[str]`, `accepted_series(experiment_id, signal, start, end, policy_version) -> list[tuple[int, float]]`, `quality_counts(experiment_id, start, end, policy_version) -> list[dict]` (keys `source, signal, quality, verdict, count`; both processed tables), `has_policy_rows(policy_version) -> bool`, `input_counts(start, end) -> dict[str, int]` (row counts of the six input tables, for `inputs_unchanged`), `write_series(experiment_id, metric, metrics_version, policy_version, series)`, `count_series(experiment_id, metric, metrics_version, start, end) -> int`, `close()`. Postgres: `pg_connect(conninfo, schema) `, `pg_check(conn) -> str | None` (refusal detail when 0003 is not applied), `missing_experiments(conn, ids) -> list[str]`, `upsert_metrics(conn, rows: list[dict])` and `upsert_quality(conn, rows: list[dict])` in one transaction (`write_postgres(conn, metric_rows, quality_rows)`), `count_rows(conn, table, metrics_version) -> dict[str, int]` (by experiment). Row dict keys = the table columns above. T2 does not import `pipeline/metrics.py`.
- Example map (rule → one example; boundaries included):

  | Rule | Example |
  |---|---|
  | Power only where both accepted | BAD current at +100 s → no `power_computed` at +100 s |
  | Residual tolerance | logged power +250 W at +200 s on 15,000 W → outside (limit 160 W); +150 W → inside (unit) |
  | Spacing rule | 2 s spacing at 1 Hz bridged; 2 s + 1 ns not; 3 s not (unit); 4 s at 0.5 Hz bridged, 6 s not |
  | No scaling | 600 s run with 16 s unbridged → energy over 584 s, coverage 0.9733 |
  | Energy twice | logged power present where current is missing → difference taken over the overlap only |
  | Ambient as-of | latest reading 120 s old → used; 122 s old → no capture value |
  | Efficiency ≤ 0 kept | co2_out ≥ co2_in → value ≤ 0 stored, counted (unit) |
  | Energy per kg over overlap | power covered 0–299 s, capture covered 0–360 s → only 0–299 s counts |
  | Labels | coverage 0.95 → complete; 0.9499 → partial; no value → none (unit) |
  | Quality shares | current 587 present of 600 expected, 586 accepted, 1 BAD |
  | On-change | process_state → expected and completeness null |
  | Plausibility | efficiency mean 1.2 → check false, exit 1, outputs written (fake) |
  | Idempotent | second run → identical `metrics_series`, Postgres rows and summary except timing |
  | Refusal | `dac_missing` → exit 2, not created, nothing written |
  | Real data | six experiments, labels as pinned in S4.24 |

- Fixture `tests/fixtures/metrics/` (`readings.csv`, `experiments.json`, `readings.sha256`, `make_fixture.py`, `README.md` with the hand computations): one experiment `EXP_001`, 2026-05-04T08:00:00Z–08:10:00Z (600 s), built by a deterministic stdlib script like the M3 fixture. Noise is a fixed alternation of ± half the signal's declared step size (`pipeline/cleaning_policy.py`), `+` at even seconds (or even reading index for slower signals), so cleaning accepts every normal reading. All timestamps `Z`, all `GOOD` unless stated. Instants relative to 08:00:00:
  - voltage 1 Hz 100 ± 0.075 V; current 1 Hz 150 ± 0.15 A; power 1 Hz = voltage × current exactly (written with enough decimals), except +250 W at +200 s.
  - No voltage, current or power rows from +300 to +310 s (points at +299 and +311). No current rows at +450 and +451 s. Current at +100 s is `BAD`.
  - co2_in_ppm and co2_out_ppm 0.5 Hz at even seconds, 420 ± 0.55 and 105 ± 0.4; co2_out at +400 s `UNCERTAIN`; co2_in at +500 and +502 s `BAD`.
  - air_flow 1 Hz 1200 ± 3.775 m³/h.
  - ambient_temperature 15 ± 0.065 °C and ambient_pressure 1013.25 ± 0.03 hPa at whole minutes, except no rows at +300 and +360 s (8 readings each).
  - process_state `STARTUP` at 0, `STEADY_STATE` at +60 s. No other signal has rows.
  - T3 checks first that cleaning this fixture excludes exactly the four planted readings (current +100, co2_out +400, co2_in +500, +502) and nothing else; if not, the construction is changed, not the rules.
- Scenarios:
  ```gherkin
  Scenario: S4.1 Computed power exists exactly where voltage and current are both accepted
    Given the metrics fixture ingested and cleaned into a throwaway database
    When python -m scripts.metrics runs on it with a throwaway Postgres schema
    Then the exit code is 0
    And metrics_series holds 586 power_computed rows for EXP_001, each equal to voltage × current at its instant
    And there is no power_computed row at +100 s, +300 s to +310 s, +450 s or +451 s

  Scenario: S4.2 The power cross-check counts disagreeing instants
    Given the same run
    Then metrics_series holds 586 power_residual rows, each equal to power − voltage × current
    And power_check reports instants_compared 586, within_tolerance 585 and residual_max_abs_w 250

  Scenario: S4.3 A spacing at the limit is bridged and one past it is not
    Given a 1 Hz power series with spacings of 1 s, 2 s, 2 s + 1 ns and 3 s
    When integrate runs with max spacing 2 s
    Then only the 1 s and 2 s spacings count towards covered seconds and the integral
    And a 0.5 Hz series with spacings 4 s and 6 s under max spacing 4 s counts only the 4 s spacing

  Scenario: S4.4 Energy covers only bridged time and is not scaled up
    Given the fixture run
    Then energy_kwh equals the trapezoid sum of the power_computed rows over bridged spacings ÷ 3.6e6, hand-computed from the construction
    And its coverage is 584 / 600 and its status is complete
    And energy_logged_kwh has coverage 587 / 600

  Scenario: S4.5 Energy from logged power is compared over the overlap only
    Given the fixture run, where logged power exists at +450 s and +451 s but computed power does not
    Then energy_relative_difference equals (E_logged − E_computed) / E_computed with both integrated over the overlap of their covered intervals, hand-computed
    And the energy_agreement plausibility check passes

  Scenario: S4.6 Efficiency at or below zero is kept and counted
    Given co2_in 400 and co2_out 400 at one instant and co2_out 410 at another
    When efficiency_series runs
    Then the values 0.0 and −0.025 are in the series, unclamped
    And efficiency_check.at_or_below_zero counts 2

  Scenario: S4.7 Capture efficiency is the mean over instants with both CO2 readings accepted
    Given the fixture run
    Then metrics_series holds 297 capture_efficiency rows, none at +400, +500 or +502 s
    And capture_efficiency_mean equals the hand-computed mean of (in − out) / in over those instants
    And its coverage is 592 / 600 and its status is complete

  Scenario: S4.8 Ambient readings are used up to 120 s old and not beyond
    Given ambient readings at +240 s and +420 s and none between
    When capture_series runs on CO2 instants +360 s, +362 s and +420 s
    Then +360 s has a capture value (age 120 s), +362 s has none (age 122 s) and +420 s has one

  Scenario: S4.9 Capture rate and captured CO2 match the hand computation
    Given the fixture run
    Then metrics_series holds 269 capture_rate rows, none from +362 s to +418 s and none at +400, +500, +502 s
    And each row equals air_flow × (co2_in − co2_out) × 1e-6 × p·0.04401 / (8.314462618 · T) with p and T from the as-of ambient readings
    And co2_captured_kg, co2_inlet_kg and capture_rate_mean_kg_h equal the hand computation, coverage 532 / 600, status partial

  Scenario: S4.10 Energy per kg CO2 uses only the overlap of power and capture time
    Given power covered on [0, 299], [311, 449], [452, 599] s and capture covered on [0, 360], [420, 498], [504, 598] s
    When the energy per kg is computed
    Then both integrals run over [0, 299], [311, 360], [420, 449], [452, 498], [504, 598] (517 s) with interpolated endpoints
    And the value equals the hand computation and the coverage is 517 / 600
    And with an empty overlap the value is null and the status is none

  Scenario: S4.11 Labels follow the coverage at the 0.95 boundary
    Given coverages 0.95, 0.9499999 and 0, and a null value
    Then status_for gives complete, partial and partial for the values, and none for the null value

  Scenario: S4.12 Data quality is reported for all 25 signals
    Given the fixture run
    Then signals lists 25 entries for EXP_001
    And current shows present 587, expected 600, accepted 586, bad 1, completeness 587 / 600
    And co2_out_ppm shows uncertain 1; ambient_pressure present 8 of 10 expected
    And process_state shows present 2 with expected and completeness null
    And flow shows present 0, expected 600, completeness 0 and the three fractions null

  Scenario: S4.13 Experiment-level quality shares add up over the signals
    Given the fixture run
    Then completeness equals 2981 / 7360 and valid_fraction, bad_fraction, uncertain_fraction equal the signal sums (2979 accepted, 3 BAD, 1 UNCERTAIN of 2983 present)

  Scenario: S4.14 Postgres holds one row per metric and per signal, joinable to the experiment
    Given migration 0003 applied in a throwaway schema with the experiment rows loaded
    When write_postgres writes 13 metric rows and 25 signal rows for one experiment, twice
    Then experiment_metrics holds 13 rows and signal_quality 25 rows for that experiment and version, with the values written
    And a join of experiment_metrics to experiment on experiment_id returns current_setpoint_nominal_a beside each metric
    And a row for an experiment not in the experiment table is refused by the foreign key, and nothing of that call is kept

  Scenario: S4.15 Reading and writing metrics_series round-trips and reads only accepted rows
    Given a throwaway database with readings_processed rows of two policy versions, accepted and excluded
    When accepted_series reads one signal for one policy version
    Then it returns only the accepted rows of that version, in time order
    And a series written with write_series reads back with count_series equal to its length

  Scenario: S4.16 A rerun changes nothing
    Given the fixture run done once
    When it runs again
    Then metrics_series, experiment_metrics and signal_quality are identical to the first run
    And the summaries are equal except timing

  Scenario: S4.17 The metrics run touches no input table
    Given the fixture ingested and cleaned
    Then the six input tables hold the same rows before and after the metrics run (full dumps equal)
    And reconciliation.inputs_unchanged is true and the only new InfluxDB table is metrics_series

  Scenario: S4.18 Refusals write nothing
    When the command runs with --database dac_missing, or on a database cleaned under another policy version, or with an unreadable experiments file, or with a schema without migration 0003, or with an experiment missing from Postgres
    Then the exit code is 2, the report directory is empty, no metrics_series or Postgres row is written, and dac_missing is not created

  Scenario: S4.19 Failures and mismatches have their own exit codes
    Given a fake gateway
    When a query or write fails, the command exits 3 and writes no outputs
    When the read-back count differs from what was written, the command exits 4, writes the outputs and lists the mismatch

  Scenario: S4.20 A failed plausibility check exits 1 and still writes everything
    Given a fake gateway whose inputs give a capture efficiency mean above 1
    Then the exit code is 1, the outputs are written, plausibility_failed is 1 and efficiency_in_unit_interval has passed false

  Scenario: S4.21 The summary matches the contract and the report matches the summary
    Given the fixture run
    Then metrics_summary.json validates against contracts/metrics_summary.schema.json
    And metrics_report.md equals the report rendered from that summary

  Scenario: S4.22 The metrics policy is pinned by a fingerprint
    Given pipeline/metrics.py
    Then METRICS_FINGERPRINT equals the SHA-256 of the canonical JSON of POLICY and METRICS_VERSION is m4-v1

  Scenario: S4.23 The metrics document matches the code
    Given docs/metrics.md
    Then it has one entry per metric name and per series name, with the unit and the constants equal to METRIC_UNITS, SERIES_UNITS and POLICY

  Scenario: S4.24 The real run gives the pinned labels
    Given the real CSV ingested and cleaned on a private stack
    When python -m scripts.metrics runs
    Then the exit code is 0, six experiments are reported, each with all 13 metrics
    And energy_kwh is partial only for EXP_002 (coverage about 0.93), complete for the other five
    And co2_captured_kg and capture_rate_mean_kg_h are partial for EXP_004 (about 0.50), EXP_005 (about 0.75) and EXP_006 (about 0.36), complete for EXP_001–EXP_003
    And sec_kwh_per_kg is partial for EXP_002 (about 0.93, the power ∩ capture overlap), EXP_004, EXP_005 and EXP_006, complete for EXP_001 and EXP_003
    And capture_efficiency_mean is partial only for EXP_006 (about 0.36)

  Scenario: S4.25 Computed and logged power agree on real accepted data
    Given the real run
    Then within_tolerance_fraction is at least 0.99 for every experiment except EXP_001
    And EXP_001's shortfall (0.983, one 120 s stretch of logged power about 6 kW above voltage × current) is reported in reports/M4.md as a cross-check result (Sebastian's ruling, 2026-11-24)
    And every energy_agreement check passes

  Scenario: S4.26 An independent recompute gives the same numbers
    Given plain SELECT pulls of the accepted inputs and a script that imports no pipeline code
    When it recomputes every metric, coverage, power_check and efficiency_check of all six experiments
    Then all equal the summary to 9 significant digits

  Scenario: S4.27 Real quality counts equal the cleaning summary
    Given the real run and reports/cleaning_summary.json
    Then for every series present equals raw_points and accepted equals accepted
    And bad and uncertain equal the acquisition-flag counts in readings_processed and state_intervals

  Scenario: S4.28 Real plausibility holds and the run reproduces
    Given the real run
    Then every plausibility check passes
    And a second run on a fresh private stack gives a summary equal to the committed reports/metrics_summary.json except timing
  ```
  Note on S4.24: the labels are the plan's prediction from the M3 summary and the raw ambient file (decision 18). A different label stops T4 and comes back as a narrow question to `/flow:plan M4`.
- QA procedure:
  1. Private stack up (`.workflow/verify-env.json`; it migrates Postgres including 0003 and loads the six experiments). Create throwaway database `qa_m4` (`POST /api/v3/configure/database`) and Postgres schema `qa_m4` (run `pipeline.pg_migrate.run_migrations` and `pipeline.metadata_loader.load_experiments` with `tests/fixtures/metrics/experiments.json` against it, `search_path=qa_m4`). `python -m scripts.ingest --csv tests/fixtures/metrics/readings.csv --experiments tests/fixtures/metrics/experiments.json --sha256 tests/fixtures/metrics/readings.sha256 --database qa_m4 --report-dir <tmp1>` → exit 0. `python -m scripts.clean --database qa_m4 --experiments tests/fixtures/metrics/experiments.json --report-dir <tmp2>` → exit 0; its summary excludes exactly the four planted readings.
  2. Dump the six input tables of `qa_m4` to files A. `python -m scripts.metrics --database qa_m4 --experiments tests/fixtures/metrics/experiments.json --pg-schema qa_m4 --report-dir <tmp3>` → exit 0. Query `metrics_series` of `qa_m4` and check S4.1, S4.2, S4.7, S4.9; check `<tmp3>/metrics_summary.json` for S4.4, S4.5, S4.9, S4.12, S4.13; `SELECT … FROM qa_m4.experiment_metrics JOIN qa_m4.experiment USING (experiment_id)` returns 13 rows (S4.14); `check-jsonschema --schemafile contracts/metrics_summary.schema.json <tmp3>/metrics_summary.json` → ok (S4.21).
  3. Dump the input tables again → equal to A (S4.17). Run step 2 again into `<tmp4>`; `metrics_series` and both Postgres tables identical; summaries equal without `timing` (S4.16).
  4. `--database dac_missing` → exit 2, `<tmp5>` empty, not in `GET /api/v3/configure/database?format=json`; `--policy-version m3-none` → exit 2; `--pg-schema` of a schema without 0003 → exit 2 (S4.18). `python -m pytest tests/unit -k "metrics"` → pass (S4.3, S4.6, S4.8, S4.10, S4.11, S4.19, S4.20, S4.22, S4.23). Drop `qa_m4` and the schema.
  5. Real CSV (copied in by verify-env): `python -m scripts.ingest` → exit 0; `python -m scripts.clean --report-dir <tmp6>` → exit 0; `python -m scripts.metrics --report-dir <tmp7>` → exit 0; check S4.24, S4.25, S4.28's plausibility in `<tmp7>/metrics_summary.json`; compare quality counts with `<tmp6>/cleaning_summary.json` (S4.27).
  6. Independent recompute from plain `SELECT time, value FROM readings_processed WHERE verdict = 'accepted' …` pulls, no pipeline imports (S4.26). Compare `<tmp7>/metrics_summary.json` with the committed `reports/metrics_summary.json` without `timing` (S4.28).
- Expected changes:
  - `pipeline/metrics.py` (new, pure, stdlib): policy table, version, fingerprint, the formulas, coverage, overlap integration, labels, quality shares, plausibility, summary shaping helpers.
  - `pipeline/metrics_store.py` (new): InfluxDB reads (reuse `pipeline/cleaning_influx.py` patterns: `window_params`, `_WritingGateway`, `send_with_retry`, `list_databases` from `pipeline/ingest_influx.py`, line-protocol escaping from `pipeline/ingest.py`), `metrics_series` writes and counts, Postgres connect/check/upsert/count (psycopg, like `pipeline/metadata_loader.py`).
  - `migrations/0003_experiment_metrics.sql` (new): the two tables.
  - `pipeline/metrics_run.py` + `scripts/metrics.py` (new): orchestration, refusals, exit codes, summary, report rendering; mirror `scripts/clean.py` (Config, Deps, refuse, run, write at end).
  - `contracts/metrics_summary.schema.json` + example (written at plan time). CI lint job: contract step.
  - Committed real outputs: `reports/metrics_summary.json`, `reports/metrics_report.md`; `reports/M4.md` (two-layer milestone report).
  - Docs: `docs/metrics.md` (each metric: formula, inputs, unit, alignment, gap rule, label; why an integrated energy value is treated differently from pH and states), ADR-0016, `docs/schema.md` (`metrics_series`, the Postgres tables), `docs/ASSUMPTIONS.md` (A-08; U-06 note), `docs/decisions/README.md`, `docs/ROADMAP.md` (M4 phase, results, deliverable E row).
- Tests: `tests/unit/test_metrics.py` (every formula on hand-built series; the boundaries of S4.3, S4.8, S4.11; S4.6; S4.10 including empty overlap and clipped endpoints; fingerprint S4.22; quality shares with zero denominators; plausibility with null values), `tests/integration/test_metrics_store.py` (S4.14, S4.15; throwaway InfluxDB database and Postgres schema), `tests/integration/test_migrations.py` (expects `0001, 0002, 0003`), `tests/unit/test_metrics_exit_codes.py` (fake gateway: S4.19, S4.20, refusal paths), `tests/e2e/test_metrics_cli.py` (fixture ingest + clean + metrics as subprocesses, marked `influx` and `postgres`: S4.1, S4.2, S4.4, S4.5, S4.7, S4.9, S4.12, S4.13, S4.16, S4.17, S4.18, S4.21, plus a recompute of every fixture metric from plain pulls), `tests/unit/test_metrics_doc.py` (S4.23). S4.24–S4.28 run on the real data (Checks rows, QA steps 5–6).
- Tasks (decision 1; checked with `lane.js tasks`):
  - T1 [W1] Pure metric functions, policy table, version and fingerprint, with unit tests for every formula and boundary. Owns: `pipeline/metrics.py`, `tests/unit/test_metrics.py`. Scenarios: S4.3, S4.6, S4.8, S4.10, S4.11, S4.22.
  - T2 [W1] Storage: migration 0003, InfluxDB reads and `metrics_series` writes and counts, Postgres connect, check, upsert and counts, integration tests. Owns: `migrations/0003_experiment_metrics.sql`, `pipeline/metrics_store.py`, `tests/integration/test_metrics_store.py`, `tests/integration/test_migrations.py`. Scenarios: S4.14, S4.15.
  - T3 [W2] Fixture, `scripts.metrics` CLI and orchestration, summary and report, exit codes, end-to-end tests on the fixture, fake-gateway tests. Owns: `pipeline/metrics_run.py`, `scripts/metrics.py`, `tests/fixtures/metrics/**`, `tests/e2e/test_metrics_cli.py`, `tests/unit/test_metrics_exit_codes.py`. Scenarios: S4.1, S4.2, S4.4, S4.5, S4.7, S4.9, S4.12, S4.13, S4.16, S4.17, S4.18, S4.19, S4.20, S4.21. After: T1, T2.
  - T4 [W3] Real data: calibrate EXP_001, EXP_004, then all six against an independent plain-Python recompute (decision 19); stop on any label outside S4.24; full run into `reports/`; reproduce on a fresh private stack. Owns: `reports/metrics_summary.json`, `reports/metrics_report.md`, `.flow-tmp/**`. Scenarios: S4.24, S4.25, S4.26, S4.27, S4.28. After: T3.
  - T5 [W4] Write-up: `docs/metrics.md`, ADR-0016, `docs/schema.md`, `docs/ASSUMPTIONS.md`, `docs/decisions/README.md`, `docs/ROADMAP.md`, `reports/M4.md`, CI contract step, doc-vs-code test. Owns: `docs/**`, `reports/M4.md`, `.github/workflows/ci.yml`, `tests/unit/test_metrics_doc.py`. Scenarios: S4.23. After: T4.
- After the judge: commit, push `m4-metrics`, CI green, open `reports/M4.md` in the doc viewer. Merge waits for approval.

#### M5: Comparison and findings (F)
- Depends on: M4 (accepted as done, M5 decision 2)
- Judge: verify · Touches: — (read-only against both stores; writes files only)
- Gates: —
- Contract: `contracts/comparison_summary.schema.json` (shape of `comparison_summary.json`), example `contracts/examples/comparison_summary.example.json` (shaped like a fixture run; its numbers are illustrative, not expected test values). `parameters` keys are exactly the keys of `POLICY` in `pipeline/compare.py`.
- Order of work: T1 ∥ T2 ∥ T3 → T4 → T5 (calibrate EXP_001, then all six; decision 22) → T6.
- Command: `python -m scripts.compare [--database NAME] [--experiments PATH] [--report-dir DIR] [--policy-version V] [--metrics-version V] [--pg-schema NAME]`. Defaults `dac_raw`, `data/raw/experiments.json`, `reports/`, `pipeline.cleaning_policy.POLICY_VERSION`, `pipeline.metrics.METRICS_VERSION`, `public`. InfluxDB host/token and `POSTGRES_*` from `.env`, as `scripts.metrics`. Exit codes: decision 21. Outputs in `--report-dir`: `comparison_summary.json` (contract) and `comparison_report.md` (rendered from the summary: per experiment the phases in experiment time, the measured conditions and the steady KPIs; the voltage models as tables per model and window; the evidence statuses; the 15-pair comparability matrix with per-KPI differences; the pressure-drop check; the air-flow check).
- Summary shape (the contract pins it; floats rounded to 9 significant digits; lists sorted as stated):
  - `schema_version` 1; `compare_version`; `policy_version`; `metrics_version`; `source` {database, experiments_file, pg_schema}; `parameters` {the `POLICY` table}.
  - `experiments[]` by id: {experiment_id, start, end, duration_s, `metadata` {current_setpoint_nominal_a, air_flow_nominal_m3h, solvent_flow_nominal_lmin, operator, sorbent_batch, notes} (from Postgres, nulls kept), `conditions` {current_setpoint_a, current_setpoint_profile, air_flow_m3h, solvent_flow_lmin, ambient_temperature_c, relative_humidity_pct} (measured, decision 14; null when no readings), `phases[]` in time order {index, state, start_s, end_s, window_start_s, window_end_s} (experiment time; both window fields null when the phase is too short), `steady_seconds`, `kpis` {5 names: {value, unit, coverage, status, interval_low, interval_high}}, `whole_run_metrics` {13 names: {value, unit, coverage, status}} (copied from `experiment_metrics`)}.
  - `voltage_models[]` sorted by model, window, scope (experiment ids, then `pooled`): {model (`hydrolyzer` \| `absorber`), window (`steady` \| `whole_run`), scope, testable, instants, r2 (null when not testable), resamples_used, resamples_singular, `terms[]` in predictor order {name, unit, coefficient, interval_low, interval_high, r2_drop, vif, plain_corr, best_lag_s, corr_at_best_lag, corr_at_zero} (lag fields null for current and electrolyte_temperature, and every number null when not testable), `joint` {terms (the two names), r2_drop, separable}}.
  - `voltage_evidence[]` sorted by model, window, term (the X1 and X2 terms only): {model, window, term, status (`supported` \| `single_run` \| `not_resolved` \| `inconsistent` \| `not_testable`), sign (`positive` \| `negative` \| null), experiments_testable, experiments_excluding_zero, pooled_coefficient, pooled_interval_low, pooled_interval_high}.
  - `comparisons[]` sorted by (a, b): {a, b, conditions_status (`same_conditions` \| `supported` \| `confounded`), differing (factor names, in factor order), `factors[]` in factor order {factor, a, b, differs (bool \| null)}, `recorded_differences[]` {field, a, b} (operator, when different), `kpis[]` in KPI order {name, unit, difference, interval_low, interval_high, excludes_zero (bool \| null), coverage_status (`both_complete` \| `partial_coverage` \| `not_available`)}}.
  - `pressure_drop_check` {`per_experiment[]` {experiment_id, instants, slope_air_flow, intercept_air_flow, r2_air_flow, slope_air_flow_sq, intercept_air_flow_sq, r2_air_flow_sq, best_lag_s, corr_at_best_lag, corr_at_zero}, `across` {points[] {experiment_id, air_flow_median, pressure_drop_median}, slope, intercept, r2}}.
  - `airflow_check` (null when the experiment is not in the run) {experiment_id, boundary, `signals[]` in the order air_flow, fan_speed, pressure_drop, co2_in_ppm, co2_out_ppm, capture_efficiency {signal, source (`raw` \| `accepted` \| `metrics_series`), before_points, before_median, after_points, after_median, relative_change}}.
  - `timing` {seconds, queries} — the only part allowed to differ between runs.
- Names (fixed): models and predictors `hydrolyzer`: current (A), electrolyte_temperature (°C), flow (L/min), pressure (bar); `absorber`: current, electrolyte_temperature, air_flow (m³/h), pressure_drop (mbar); coefficient unit = `V per <unit>`. KPIs: voltage_mean_v (V), mean_power_kw (kW), capture_rate_mean_kg_h (kg/h), capture_efficiency_mean (fraction), sec_kwh_per_kg (kWh/kg). Factors: current_setpoint, current_setpoint_profile, air_flow, solvent_flow, ambient_temperature, relative_humidity, sorbent_batch. `POLICY` keys: settle_s 60, bootstrap_block_s 120, bootstrap_resamples 1000, bootstrap_seed 20261124, interval_level 0.95, lag_max_s 60, temp_max_age_s 10, min_instants 300, vif_limit 10, condition_tol_rel 0.05, ambient_tol_c 5, humidity_tol_pct 15, airflow_check_experiment "EXP_004", airflow_check_boundary "2026-03-02T09:00:00Z".
- Interfaces between tasks (pinned so T1, T2 and T3 can run in parallel; T4 may rely only on these names):
  - T1, `pipeline/compare.py` (pure; stdlib plus read-only use of `pipeline.metrics`): `COMPARE_VERSION`, `COMPARE_FINGERPRINT`, `POLICY`, `policy_fingerprint()`, `MODELS` (model → tuple of 4 predictor names), `PREDICTOR_UNITS`, `KPI_UNITS`, `FACTORS`. Series are `list[tuple[int, float]]` (ns, value), ascending; windows `list[tuple[int, int]]` (ns, `[start, end)`). Functions: `experiment_time_s(t_ns, start_ns) -> float`; `phases(events: list[tuple[int, int, str]], settle_s) -> list[Phase]` (dataclass: index, state, start_ns, end_ns, window `tuple[int, int] | None`); `steady_windows(phases) -> list[tuple[int, int]]`; `model_rows(model, series: dict[str, Series], windows) -> Rows` (dataclass of aligned instants, their window index and window start, voltage and predictor columns; decision 7); `analyse_model(rows, model, window, scope, lag_series: dict[str, Series], policy=POLICY) -> dict` (one `voltage_models` entry; decisions 8, 10, 11); `analyse_pooled(rows_by_experiment: dict[str, Rows], model, window, policy=POLICY) -> dict` (the `pooled` entry; lag fields null); `evidence(entries: list[dict], pooled: dict) -> list[dict]` (`voltage_evidence` entries for one model and window); `measured_conditions(series: dict[str, Series], windows) -> dict` (the `conditions` object); `compare_factors(meta_a, cond_a, meta_b, cond_b, policy=POLICY) -> list[dict]`; `conditions_status(factors) -> tuple[str, list[str]]`; `steady_kpis(series: dict[str, Series], windows, experiment_id, policy=POLICY) -> KpiResult` (dataclass: `entries` = the `kpis` object, `samples` = KPI name → 1,000 resample values or empty when the value is null); `kpi_differences(a: KpiResult, b: KpiResult, policy=POLICY) -> list[dict]`; `pressure_drop_fit(air_flow, pressure_drop, windows, policy=POLICY) -> dict` (one `per_experiment` entry without the id); `across_line(points: list[tuple[float, float]]) -> dict` (slope, intercept, r2); `split_check(series: Series, boundary_ns) -> dict` (points and medians before/after, relative change). Signal keys in `series` are the plain signal names (`voltage`, `current`, `flow`, …) plus the `metrics_series` names (`power_computed`, `capture_rate`, `capture_efficiency`).
  - T2, `pipeline/compare_store.py`: `CompareGateway(MetricsGateway)` (inherits `tables`, `has_policy_rows`, `accepted_series`, `close`; never writes) adds `raw_series(experiment_id, signal, start, end, policy_version) -> list[tuple[int, float | None]]` (`value_raw` of every `readings_processed` row of that version, ascending), `state_events(experiment_id, signal, start, end, policy_version) -> list[tuple[int, int, str]]` (accepted `state_intervals` rows: time, `end_ns`, `value`; ascending), `metric_series(experiment_id, metric, metrics_version, policy_version, start, end) -> list[tuple[int, float]]` (filters on both versions), `has_metrics_rows(metrics_version, policy_version) -> bool`. Postgres (reusing `pg_connect` and `pg_check` from `pipeline/metrics_store.py`): `experiment_rows(conn, ids) -> dict[str, dict]` (every column of `experiment`, `start_time`/`end_time` as aware UTC datetimes, nulls as None), `experiment_metric_rows(conn, metrics_version, ids) -> dict[str, dict[str, dict]]` (id → metric → {value, unit, coverage, status}). T2 does not import `pipeline/compare.py`.
  - T3, `tests/fixtures/compare/`: `readings.csv`, `experiments.json`, `readings.sha256`, `make_fixture.py` (stdlib, deterministic), `README.md` with the construction and every hand-computed expected number S5.13–S5.16 use.
- Example map (rule → one example; boundaries included):

  | Rule | Example |
  |---|---|
  | Experiment time | instant 08:05:00Z of an experiment starting 08:00:00Z → 300.0 s; same offset on another date → same value |
  | Settle margin | phase [600, 660) s with margin 60 → no window; [600, 661) → window [660, 661) |
  | Exact join, as-of | temperature 10 s old → used; 10 s + 1 ns → instant dropped |
  | Testable | 299 rows → not testable; 300 → testable |
  | Excludes zero | interval [0.0, 0.4] → does not; [0.001, 0.4] → does |
  | Evidence | (0.1, 0.5), (0.2, 0.9) → supported positive; (0.1, 0.5), (−0.9, −0.2) → inconsistent; (0.1, 0.5), (−0.3, 0.4) → not_resolved; one testable (0.1, 0.5) → single_run |
  | Collinear | pressure = 0.05 × flow + tiny noise → VIF ≥ 10, separable false |
  | Relative factor | setpoint 150 vs 157.5 → same (7.5 ≤ 7.875); 150 vs 158 → differs |
  | Absolute factor | ambient 10 °C vs 15 °C → same; 10 vs 15.01 → differs |
  | Unknown factor | batch null vs "SB-2026-014" → differs null, counted as differing |
  | Lag tie | equal |corr| at 3 s and 7 s → 3 s |
  | KPI coverage | one KPI partial → coverage_status partial_coverage; one null → not_available, difference null |
  | Read-only | dumps of every table before and after are equal |
  | Refusal | `--metrics-version m4-none` → exit 2, nothing written |

- Fixture `tests/fixtures/compare/` (built by a deterministic stdlib script like the M4 fixture). Three experiments of 1,200 s: EXP_001 2026-05-04T08:00:00Z, EXP_002 2026-05-11T09:00:00Z, EXP_003 2026-05-18T07:30:00Z. Metadata: setpoint nominal 150 / 200 / 150 A, air flow nominal 1200 / 1200 / 2400 m³/h, solvent flow 8.0 for all, sorbent batch `SB-A` / `SB-A` / `SB-B`, operator `Op A` / `Op A` / `Op B`, notes null. All timestamps `Z`, all `GOOD` unless stated. Normal noise is a fixed alternation of ± half the signal's declared step (`pipeline/cleaning_policy.py`), `+` at even reading index, so cleaning accepts every normal reading. Instants relative to each start:
  - process_state `STARTUP` 0, `STEADY_STATE` +120, `LOAD_CHANGE` +600, `STEADY_STATE` +660, `SHUTDOWN` +1140.
  - Hydrolyzer 1 Hz: current_setpoint = nominal, + 20 A from +600 to +659 (no noise); current = setpoint ± noise (no lag); flow = 40 + triangle wave (period 300 s, amplitude 2 L/min) ± noise; pressure = 2.5 + triangle wave (period 420 s, amplitude 0.1 bar) ± noise; voltage = 40 + 0.3 × current − 0.2 × flow + 3.0 × pressure − 0.1 × T + e, where T is the electrolyte temperature reading the as-of join pairs with that instant and e is an independent deterministic sequence (`random.Random("compare-fixture").uniform(-0.05, 0.05)`, same sequence in each experiment); power = voltage × current. Every input value is rounded to the decimals written before voltage is computed from it; voltage written with 6 decimals.
  - Hydrolyzer 0.2 Hz: electrolyte_temperature = 35 + 0.005 °C per s ± noise.
  - Absorber: air_flow 1 Hz = nominal ± noise; pressure_drop 0.5 Hz = 15 × (air_flow / 1200)² ± noise; co2_in_ppm 420 ± noise and co2_out_ppm 105 ± noise at 0.5 Hz; solvent_flow 0.5 Hz 8.0 ± noise.
  - Ambient 1/60 Hz: ambient_temperature 15, ambient_pressure 1013.25, relative_humidity 50, each ± noise.
  - Planted exclusion: EXP_001 voltage at +300 s is `BAD`.
  - T3 checks first that cleaning this fixture excludes exactly that one reading and nothing else (S5.12); if not, the construction changes, not the rules. T3 also records in the README: phases and windows; the fit instants per model and window (hydrolyzer steady 839 / 840 / 840 expected from the construction); the planted coefficients; `voltage_mean_v` and `mean_power_kw` of each experiment over the steady windows and their coverage, computed in plain arithmetic from the CSV; the expected comparability statuses.
- Scenarios:
  ```gherkin
  Scenario: S5.1 Experiment time is seconds since the experiment's start
    Given an experiment starting 2026-05-04T08:00:00Z and another starting 2026-05-11T09:00:00Z
    When experiment_time_s runs on 2026-05-04T08:05:00Z and on 2026-05-11T09:05:00Z
    Then both give 300.0

  Scenario: S5.2 Phase windows come from process_state, trimmed by the settle margin
    Given state events STARTUP [0, 120), STEADY_STATE [120, 600), LOAD_CHANGE [600, 660), STEADY_STATE [660, 1140), SHUTDOWN [1140, 1200) s
    When phases runs with settle_s 60
    Then the windows are [60, 120), [180, 600), none, [720, 1140), none
    And steady_windows gives [180, 600) and [720, 1140)
    And a phase of 61 s gives a window of 1 s

  Scenario: S5.3 The regression recovers planted coefficients and each term's drop in R squared
    Given rows where voltage = 40 + 0.3 current − 0.2 flow + 3.0 pressure − 0.1 temperature exactly, with independent predictor patterns
    When analyse_model runs
    Then each coefficient equals the planted value to 1e-9, r2 is 1 to 1e-9
    And r2_drop of each term equals 1 minus the R squared of the model without it
    And a set of 299 rows is not testable and 300 rows is

  Scenario: S5.4 Flow and pressure too collinear to separate give only a joint effect
    Given rows where pressure = 0.05 × flow plus a perturbation of 1e-4
    When analyse_model runs
    Then the vif of flow and pressure is at least 10 and joint.separable is false
    And joint.r2_drop is reported

  Scenario: S5.5 The block bootstrap is deterministic for its seed and covers the planted value
    Given rows with planted coefficients and independent noise
    When analyse_model runs twice with the same policy
    Then the intervals are identical
    And each interval contains its coefficient estimate
    And a resample whose normal matrix is singular is counted in resamples_singular and skipped

  Scenario: S5.6 The evidence rule gives its five statuses at their boundaries
    Given per-experiment intervals (0.1, 0.5) and (0.2, 0.9)
    Then the status is supported with sign positive
    And (0.1, 0.5) with (−0.9, −0.2) is inconsistent; (0.1, 0.5) with (−0.3, 0.4) is not_resolved; (0.0, 0.5) with (0.2, 0.9) is not_resolved
    And a single testable (0.1, 0.5) is single_run; no testable fit is not_testable

  Scenario: S5.7 The comparability rule gives supported, confounded or same conditions
    Given two experiments that differ only in setpoint 150 against 158 A
    Then conditions_status is supported and differing is [current_setpoint]
    And 150 against 157.5 A does not differ; ambient 10 against 15 °C does not differ, 10 against 15.01 does
    And a null sorbent batch gives differs null and counts as differing
    And two differing factors give confounded, naming both; none gives same_conditions
    And a KPI partial on one side gives coverage_status partial_coverage, a null KPI gives not_available with a null difference

  Scenario: S5.8 The lag search picks the strongest shift, ties to the smaller one
    Given a residual that equals the term shifted by 7 s
    Then best_lag_s is 7
    And with equal |corr| at 3 s and 7 s, best_lag_s is 3
    And a shift with fewer than min_instants pairs is skipped

  Scenario: S5.9 The comparison policy is pinned by a fingerprint
    Given pipeline/compare.py
    Then COMPARE_FINGERPRINT equals the SHA-256 of the canonical JSON of POLICY and COMPARE_VERSION is m5-v1

  Scenario: S5.10 Reads return only accepted rows and phases of one policy version, in time order
    Given a throwaway database with readings_processed and state_intervals rows of two policy versions, accepted and excluded, and metrics_series rows of two metrics versions
    When the CompareGateway reads one experiment window
    Then state_events returns only the accepted events of that policy version with their end_ns, ascending
    And raw_series returns value_raw of every row of that version, including excluded ones
    And metric_series returns only rows of the given metrics and policy version
    And has_metrics_rows is false for a version with no rows

  Scenario: S5.11 Metadata and M4 metrics are read from Postgres, nulls kept
    Given migrations 0001–0003 in a throwaway schema, the fixture experiments loaded and experiment_metrics rows written
    When experiment_rows and experiment_metric_rows run
    Then every experiment column is returned with nulls as None and start_time as aware UTC
    And each experiment has its metric rows for the asked metrics version only

  Scenario: S5.12 Cleaning the compare fixture excludes exactly the planted reading
    Given the compare fixture ingested into a throwaway database
    When python -m scripts.clean runs on it
    Then exactly one reading is excluded: EXP_001 voltage at +300 s, reason flag_bad
    And no gap or flatline interval is recorded

  Scenario: S5.13 The fixture run reports each experiment's phases in experiment time
    Given the fixture ingested, cleaned and its metrics computed into a throwaway database and Postgres schema
    When python -m scripts.compare runs on it
    Then the exit code is 0
    And every experiment lists 5 phases with windows [60, 120), [180, 600), none, [720, 1140), none and steady_seconds 840

  Scenario: S5.14 The fixture run recovers the planted flow and pressure effects
    Given the same run
    Then the hydrolyzer steady fits have 839, 840 and 840 instants
    And each experiment's flow coefficient is within 0.02 of −0.2 and its pressure coefficient within 0.3 of 3.0, both intervals excluding zero
    And voltage_evidence for hydrolyzer steady gives supported, negative for flow and positive for pressure
    And voltage_models has entries for both models, both windows, every experiment and pooled

  Scenario: S5.15 Steady-state KPIs on the fixture equal the hand computation
    Given the same run
    Then voltage_mean_v and mean_power_kw of each experiment equal the README's hand computation to 9 significant digits, with the README's coverage and status
    And the EXP_002 minus EXP_001 voltage_mean_v difference is within 0.1 V of 15.0 and excludes zero

  Scenario: S5.16 The fixture's comparability matrix names the planted differing factors
    Given the same run
    Then EXP_001–EXP_002 is supported with differing [current_setpoint]
    And EXP_001–EXP_003 is confounded with differing [air_flow, sorbent_batch] and recorded_differences naming operator
    And EXP_002–EXP_003 is confounded with differing [current_setpoint, air_flow, sorbent_batch]

  Scenario: S5.17 The command changes no store and a rerun is identical except timing
    Given the fixture run
    Then full dumps of every InfluxDB table of the throwaway database and of the Postgres tables are equal before and after, and the database list is unchanged
    And a second run gives a summary equal to the first except timing, and an equal report

  Scenario: S5.18 Refusals exit 2 and a failing query exits 3, writing nothing
    When the command runs with --database dac_missing, --policy-version m3-none, --metrics-version m4-none, an unreadable experiments file, a Postgres schema without migration 0003, an experiment missing from Postgres, or Postgres start_time differing from the file
    Then the exit code is 2, the report directory is empty and dac_missing is not created
    And with a fake gateway whose query fails the exit code is 3 and no output is written

  Scenario: S5.19 The summary matches the contract and the report matches the summary
    Given the fixture run
    Then comparison_summary.json validates against contracts/comparison_summary.schema.json
    And comparison_report.md equals the report rendered from that summary

  Scenario: S5.20 The real run covers six experiments, all pairs and both readings of flow and pressure
    Given the real CSV ingested, cleaned and its metrics computed on a private stack
    When python -m scripts.compare runs
    Then the exit code is 0, six experiments are reported, each with its phases, conditions, 5 steady KPIs and 13 whole-run metrics
    And voltage_models has 28 entries (2 models × 2 windows × (6 experiments + pooled))
    And voltage_evidence has 8 entries and comparisons has 15
    And pressure_drop_check has six per-experiment entries and airflow_check is present for EXP_004

  Scenario: S5.21 An independent recompute equals the real summary
    Given plain SELECT pulls of the accepted inputs, state_intervals and metrics_series, and a script that imports no pipeline code
    When it recomputes phases, conditions, every fit, interval, lag, evidence status, KPI, comparison, the pressure-drop check and the air-flow check
    Then all equal the summary to 9 significant digits

  Scenario: S5.22 A fresh private stack reproduces the committed summary
    Given a fresh private stack with ingest, clean and metrics run on the real CSV
    When python -m scripts.compare runs
    Then its summary equals the committed reports/comparison_summary.json except timing and its report equals reports/comparison_report.md

  Scenario: S5.23 The EXP_004 air-flow hour is compared against the other signals
    Given the real run
    Then airflow_check lists air_flow from raw values and fan_speed, pressure_drop, co2_in_ppm, co2_out_ppm and capture_efficiency, each with points and medians before and after 09:00Z
    And the before/after counts of each equal a plain COUNT over the same rows

  Scenario: S5.24 The draft findings hold at least three claims, the flow and pressure answer and the unsupported comparisons
    Given reports/findings.md
    Then its status line reads "Status: draft, awaiting Sebastian's approval"
    And it has at least three findings, each with a claim, the command and SQL behind it, and numbers
    And it has a section on flow and pressure against voltage with the hydrolyzer model first and the absorber model second
    And it has a section naming the comparisons the data does not support, with the reason for each

  Scenario: S5.25 Every number in the findings equals the committed summary
    Given reports/findings.md and reports/comparison_summary.json
    Then every ref comment resolves to a value in the summary
    And the number written before it equals that value rounded to the digits written
    And a finding with no ref comment fails the test

  Scenario: S5.26 The method document matches the code's policy table
    Given docs/comparison.md
    Then it lists every POLICY key with its value, every KPI with its unit, every factor and every evidence status, equal to pipeline/compare.py
  ```
- QA procedure:
  1. Private stack up (`.workflow/verify-env.json`; it migrates Postgres including 0003 and loads the six experiments). Create throwaway database `qa_m5` (`POST /api/v3/configure/database`) and Postgres schema `qa_m5` (run `pipeline.pg_migrate.run_migrations` and `pipeline.metadata_loader.load_experiments` with `tests/fixtures/compare/experiments.json` against it, `search_path=qa_m5`). `python -m scripts.ingest --csv tests/fixtures/compare/readings.csv --experiments tests/fixtures/compare/experiments.json --sha256 tests/fixtures/compare/readings.sha256 --database qa_m5 --report-dir <tmp1>` → exit 0. `python -m scripts.clean --database qa_m5 --experiments tests/fixtures/compare/experiments.json --report-dir <tmp2>` → exit 0; its summary excludes exactly EXP_001 voltage +300 s (S5.12). `python -m scripts.metrics --database qa_m5 --experiments tests/fixtures/compare/experiments.json --pg-schema qa_m5 --report-dir <tmp3>` → exit 0 or 1 (plausibility is not what M5 tests).
  2. Dump every table of `qa_m5` (InfluxDB) and the four Postgres tables of schema `qa_m5` to files A; save the database list. `python -m scripts.compare --database qa_m5 --experiments tests/fixtures/compare/experiments.json --pg-schema qa_m5 --report-dir <tmp4>` → exit 0. Check `<tmp4>/comparison_summary.json` for S5.13–S5.16 against `tests/fixtures/compare/README.md`; `check-jsonschema --schemafile contracts/comparison_summary.schema.json <tmp4>/comparison_summary.json` → ok (S5.19).
  3. Dump again → equal to A, database list unchanged (S5.17). Run step 2 again into `<tmp5>`; summaries equal without `timing`, reports equal (S5.17).
  4. `--database dac_missing` → exit 2, `<tmp6>` empty, not in `GET /api/v3/configure/database?format=json`; `--policy-version m3-none` → exit 2; `--metrics-version m4-none` → exit 2; `--pg-schema` of a schema without 0003 → exit 2; an experiments file whose EXP_001 start differs by 1 s → exit 2 (S5.18). `python -m pytest tests/unit -k "compare"` → pass (S5.1–S5.9, S5.18's exit 3). Drop `qa_m5` and the schema.
  5. Real CSV (copied in by verify-env): `python -m scripts.ingest` → exit 0; `python -m scripts.clean --report-dir <tmp7>` → exit 0; `python -m scripts.metrics --report-dir <tmp8>` → exit 0; `python -m scripts.compare --report-dir <tmp9>` → exit 0; check S5.20 and S5.23 in `<tmp9>/comparison_summary.json` (S5.23's counts with a plain `SELECT COUNT(*)` per signal and side of 09:00Z).
  6. Independent recompute from plain `SELECT time, value FROM readings_processed WHERE verdict = 'accepted' …`, `SELECT time, end_ns, value FROM state_intervals …` and `SELECT time, value FROM metrics_series …` pulls, no pipeline imports (S5.21). Compare `<tmp9>` with the committed `reports/comparison_summary.json` without `timing` and the reports byte for byte (S5.22). `python -m pytest tests/unit/test_findings_doc.py tests/unit/test_comparison_doc.py` → pass; read `reports/findings.md` for S5.24.
- Expected changes:
  - `pipeline/compare.py` (new, pure, stdlib): policy table, version, fingerprint, alignment, phases, instant join, OLS with centring and pivoting, block sufficient statistics and bootstrap, lag search, evidence rule, measured conditions, factors, steady KPIs with bootstrap samples, KPI differences, pressure-drop fits, split check.
  - `pipeline/compare_store.py` (new): `CompareGateway` reads (reuse `pipeline/metrics_store.py` and `pipeline/cleaning_influx.py` patterns: `window_params`, `WINDOW`, `_table`), Postgres reads (psycopg, `pg_connect`, `pg_check`).
  - `pipeline/compare_run.py` + `scripts/compare.py` (new): orchestration, refusals, exit codes, summary, report rendering; mirror `pipeline/metrics_run.py` (Config, Deps, Refused, run, write at end; `round_floats`).
  - `contracts/comparison_summary.schema.json` + example (written at plan time). CI lint job: contract step.
  - Committed real outputs: `reports/comparison_summary.json`, `reports/comparison_report.md`; `reports/findings.md` (draft); `reports/M5.md` (two-layer milestone report).
  - Docs: `docs/comparison.md` (alignment, phases, the two models, the bootstrap, the evidence rule, the factors, the KPIs, what the data cannot support and why), ADR-0017, `docs/ASSUMPTIONS.md` (A-07 status from the air-flow check, new A-09, U-05 note), `docs/decisions/README.md`, `docs/ROADMAP.md` (M5 phase, results, deliverable F row).
- Tests: `tests/unit/test_compare.py` (S5.1–S5.9, every boundary in the example map, the bootstrap re-derived by hand on a 4-block example, KPI ratio-of-sums on a hand example, pressure-drop fit and `across_line` on exact lines, `split_check` with an empty side), `tests/integration/test_compare_store.py` (S5.10, S5.11; throwaway InfluxDB database and Postgres schema), `tests/unit/test_compare_exit_codes.py` (fake gateway: S5.18's exit 3 and every refusal path that needs no live service), `tests/e2e/test_compare_cli.py` (fixture ingest + clean + metrics + compare as subprocesses, marked `influx` and `postgres`: S5.12–S5.19, plus a plain-pull recompute of the fixture's phases, KPIs and hydrolyzer coefficients), `tests/unit/test_findings_doc.py` (S5.25, and S5.24's status line and sections), `tests/unit/test_comparison_doc.py` (S5.26). S5.20–S5.23 run on the real data (Checks row, QA steps 5–6).
- Tasks (decision 1; checked with `lane.js tasks`):
  - T1 [W1] Pure analysis functions, policy table, version and fingerprint, with unit tests for every rule and boundary. Owns: `pipeline/compare.py`, `tests/unit/test_compare.py`. Scenarios: S5.1, S5.2, S5.3, S5.4, S5.5, S5.6, S5.7, S5.8, S5.9.
  - T2 [W1] Read layer: `CompareGateway` over InfluxDB and the Postgres reads, with integration tests. Owns: `pipeline/compare_store.py`, `tests/integration/test_compare_store.py`. Scenarios: S5.10, S5.11.
  - T3 [W1] Compare fixture: generator, CSV, checksum, experiments file, README with the hand computations; check that cleaning excludes exactly the planted reading. Owns: `tests/fixtures/compare/**`. Scenarios: S5.12.
  - T4 [W2] `scripts.compare` command and orchestration, summary and report, exit codes, end-to-end tests on the fixture, fake-gateway tests. Owns: `pipeline/compare_run.py`, `scripts/compare.py`, `tests/e2e/test_compare_cli.py`, `tests/unit/test_compare_exit_codes.py`. Scenarios: S5.13, S5.14, S5.15, S5.16, S5.17, S5.18, S5.19. After: T1, T2, T3.
  - T5 [W3] Real data: calibrate EXP_001, then all six, against an independent plain-Python recompute (decision 22); stop and report on any case decision 19 names; full run into `reports/`; reproduce on a fresh private stack; record the EXP_001 residual block correlation in the execute log. Owns: `reports/comparison_summary.json`, `reports/comparison_report.md`, `.flow-tmp/**`. Scenarios: S5.20, S5.21, S5.22, S5.23. After: T4.
  - T6 [W4] Write-up: draft findings (decision 20), `docs/comparison.md`, ADR-0017, `docs/ASSUMPTIONS.md`, `docs/decisions/README.md`, `docs/ROADMAP.md`, `reports/M5.md`, CI contract step, the findings and method-document tests. Owns: `docs/**`, `reports/findings.md`, `reports/M5.md`, `.github/workflows/ci.yml`, `tests/unit/test_findings_doc.py`, `tests/unit/test_comparison_doc.py`. Scenarios: S5.24, S5.25, S5.26. After: T5.
- After the judge: commit, push `m5-comparison`, CI green, open `reports/M5.md` in the doc viewer. The findings stay a draft and the merge waits until Sebastian approves them.

#### M6: Grafana dashboard (G)
- Not yet detailed. Scope: `docs/ROADMAP.md` § M6.

#### M7: Edge, cloud, presentation (H, I, J)
- Not yet detailed. Scope: `docs/ROADMAP.md` § M7.

## Findings

<!-- The verifier appends one block per run:
### M2 — verify <date> @ <revision>
Defects / Open questions / Optional, each: severity, requirement, file:line, scenario, evidence.
Scenarios: S2.1 → pass / fail / Blocked, with the evidence.
Blocked: checks that couldn't run, and why. Checks run: command → result. -->

### M2 — verify 2026-11-23 @ 1c5b6ea (+ uncommitted)
Defects:        none
Open questions:
- [plan] The contract runner fails on this record's Checks table, not on the contract. `contract.js --task .workflow/dac.md --root <WORKTREE>` → exit 3, `spawnSync C:\Program Files\Git\bin\bash.exe ENOENT`. Cause: Directory column says `repo root`, which `contract.js` resolves as a folder named "repo root" (contract.js:87). The same command run by hand from the worktree root passes (`ok -- validation done`). Fix in `/flow:plan`: write `.` in the Directory column.
- Teardown reported `Worktree changed: (file contents changed)`. Expected: the Checks row `python -m scripts.ingest` writes to the default `reports/` in the worktree. Those files match the committed `reports/ingest_summary.json` except for `timing`.
Optional:
- [low] An offset with impossible minutes is accepted and moves the instant instead of being rejected. `pipeline/ingest.py:149-152` builds `timedelta(minutes=int(offset[4:6]))` without checking the range. Probe: `parse_instant("2026-05-04T08:00:00+00:99")` → `06:21:00Z` (shifted 1 h 39 min). `+02:60` → `05:00Z`. The real file has none of these. Proposed test `test_offset_minutes_over_59_is_bad_timestamp`: `parse_instant` on `+00:99` and `+02:60` raises `RowError` with reason `bad_timestamp`.
- [low] For exact copies `0.0` / `-0.0`, file order decides which zero is stored. `value_key` treats them as equal, so the tie goes to row number (`pipeline/ingest.py:359`). Live probe on the private stack: order A stored `0.0`, swapped order B stored `-0.0`, both exit 0. The real file has one `-0.00` (row 111) and it is not in a collision, so nothing changes today. Proposed test `test_signed_zero_copies_store_the_same_point_in_either_order`: `reading_line(resolve_group(g).kept)` is the same for `g` and `reversed(g)`. Fix: break the tie on the raw text bytes, not row number.
- [low] Running `up` for a second run id in the same tree overwrites the first stack's `.env`. The old token is not backed up because the file is "ours" (`scripts/verify_stack.py:133-148`). After that the first stack can no longer be reached from that tree. The dev `.env` backup is unaffected. Found by reading the code, not by a probe. Not exercised by any scenario.
Scenarios:      S2.1 → pass (abc/18100 in a scratch copy: up exit 0; /health 200; .env names 18100/18101; a 92-char token lists `dac_raw, dac_rollup, dac_pinned`, a wrong token gets 401; psycopg login on 18101 works; `experiment` holds 6 rows) · S2.2 → pass (dev `dac-influxdb`/`dac-postgres` were started for the test; their container ids were the same before up, during, and after down; volumes `dac_influxdb-data`/`dac_postgres-data` still exist; dev containers stopped again afterwards, as found) · S2.3 → pass (xyz health exit 1, "container … not running") · S2.4 → pass (down exit 0; label filter `dac-verify-abc` shows no containers, volumes or networks; plain `docker compose config` names `dac-influxdb`/`dac-postgres`) · S2.5–S2.14, S2.16–S2.27 → pass (tests/e2e 25 passed and tests/unit 123 passed, each test tagged with its scenario; S2.10, S2.15, S2.19 also have their own small-input e2e tests) · S2.15 → pass (e2e `test_file_order_never_changes_the_result`; see the signed-zero note under Optional) · S2.28 → pass (real run exit 0: 520005 = 519980 + 15 + 10 + 0; 150 series, 0 unbalanced. Independent checks: Python counts 519980 distinct series-instants in the CSV, and my own COUNT per experiment ±12 h finds 519980 points. A full point-by-point comparison of all 519980 stored values and flags against the CSV win rule found 0 mismatches and 0 extra points) · S2.29 → pass (`GROUP BY resolution, reason` → `lower_value`/`value_differs` 10) · S2.30 → pass (out_of_order.total 30) · S2.31 → pass (all 24 experiment×source rows: first 0 s; last −1 s, ambient −60 s; outside 0) · S2.32 → pass (second run exit 0; series and totals identical; full `readings_conflicts` dump byte-identical) · S2.33 → pass (hashlib SHA-256 of the CSV, in the worktree and in the repo, = `9f791b42…553f` = committed)
Blocked:        none
Checks run:
- `verify-env.js up` → env 212acb55, ports 34560-34561, healthy
- `ruff check .` → All checks passed
- `ruff format --check .` → 70 files already formatted
- `python -m pytest tests/unit -v` → 123 passed
- `python -m pytest tests/integration -v -rs` → 31 passed, 0 skipped
- `python -m pytest tests/e2e -v -rs` → 25 passed, 0 skipped
- `python -m scripts.ingest` (twice) → exit 0 both times, 66 s, 7903 rows/s, 52 batches
- `check-jsonschema --schemafile contracts/ingest_summary.schema.json contracts/examples/ingest_summary.example.json` → ok. The committed `reports/ingest_summary.json` also validates.
- `contract.js --task .workflow/dac.md --root <WORKTREE>` → exit 3, caused by the Directory column (see Open questions)
- Probes: offset parsing; signed zero; text round trip (quotes, backslash, comma, `=`, leading space, non-ASCII → identical); number forms (`1e2`, `+5`, `.5`, `5.`, `-1.5E-3` → exact float); a real client on a closed port → `NewConnectionError`, retried, 4 attempts, sleeps [1, 2, 4]
- Test changes since baseline: no tracked test was modified or deleted; all M2 tests are new
- `verify-env.js down 212acb55` → removed; "Worktree changed" (see Open questions)

### M2.5 — verify 2026-11-23 @ 77b8516 (+ uncommitted)
Defects:        none raised. There is no implementation to judge (see Blocked).
Open questions:
- M2.5 has not been executed. HEAD is still the M2.5 baseline `77b8516` on `m2-ingestion`. Branch `m2.5-profiling` does not exist. `git diff 77b8516` touches only this record. Untracked files are just `contracts/post_ingest_profile.schema.json` and its example. None of the expected changes exist: `pipeline/profiling.py`, `pipeline/profiling_sql.py`, `scripts/post_ingest_profile.py`, the `signals.py` tables, `tests/fixtures/profile/`, `tests/unit/test_profiling.py`, `tests/e2e/test_profile_cli.py`, the committed profile outputs, ADR-0014 and `reports/M2.5.md`. The next step is `/flow:execute M2.5`, not a fix round.
- The M2 done-rule note under Assumptions still applies. The newest M2 Findings block is `@ 1c5b6ea`, while HEAD is `77b8516`.
Optional:       none
Scenarios:      S25.1–S25.22 → Blocked (no profiling command exists to exercise)
Blocked:
- Every Spec → Checks row, plus the QA procedure, is blocked because there is nothing to run. The private stack was not started.
Checks run:
- `check-jsonschema --schemafile contracts/post_ingest_profile.schema.json contracts/examples/post_ingest_profile.example.json` → ok (the plan-time contract files only)
- The S25.17 verdict-word grep on the contract example → no match

### M2.5 — verify 2026-11-23 @ 77b8516 (+ uncommitted)
Defects:        none
Open questions:
- [plan] Spec → Decisions and Assumptions do not record two changes from the plan that ADR-0014 does record: (a) correlation, slope, intercept and R squared are computed in Python on pulled pairs, not in SQL (ADR-0014 decision 4); (b) p05/p95 come from an exact rank-weighted SQL (`percentile_sql`), not `approx_percentile_cont` as the Assumptions line says. Neither changes the contract (schema and example mtimes 16:02, before any implementation file, 16:55 onwards). ADR-0010 allows Python pulls "for anything SQL cannot express"; (a) stretches that to "SQL expresses it but not reproducibly". Worth a line under Decisions so the record matches the build.
- The M2 done-rule note under Assumptions still applies (newest M2 block `@ 1c5b6ea`, HEAD `77b8516`). M2.5 depends on M2.
- `pump_speed` and `fan_speed` sit under the dictionary's "Plant (event-based)" heading but also in its "~1 Hz" list. `signals.py` gives them 1 s. The real data supports that (median interval 1 s, 7,200 points in every experiment), so the over-2× counts on them are not the C-01 mistake. The dictionary contradicts itself; noting it, not a finding against the code.
Optional:
- [low] ADR-0014 quirk 1 and `reports/M2.5.md` ("Four things", item 1) blame `COUNT(*) FILTER` for "`below` 20 against 19". That difference is signed zero (quirk 2), not FILTER. Probe on the real `dac_raw`, EXP_001 current (7,126 points, 7,126 with a value, so no NULL value to miscount): `value < 0` → FILTER 20, CASE 20; `value + 0.0 < 0` → FILTER 19, CASE 19. The FILTER quirk itself is real but narrower than written: after `LAG` it counts the NULL first interval (fixture, `dt > 2e9`: FILTER 1, CASE 0 on every 1 Hz series; solvent_pH FILTER 24, CASE 23), while a NULL from a plain `VALUES` row is not counted (`NULL, 0.5, 2.0`, `x > 1` → 1). The Next-steps line for M3 ("`COUNT(*) FILTER` counts NULL conditions") should say "NULLs produced by a window function such as `LAG`, at least" so M3 does not over- or under-avoid it. The code is unaffected: it uses `COUNT(CASE …)` everywhere.
- [low] S25.16 holds only for an empty report directory. A failed run (exit 3) leaves an earlier `post_ingest_profile.json` in place. Probe: report dir holding `{"old": true}`, live database whose `readings_numeric.value` is text → exit 3, the old file is still there. With the default `--report-dir reports/` that is the committed profile, so keeping it is arguably right (decision 10: "writes nothing"). If the scenario means "no profile from this run", reword it in `/flow:plan`; otherwise state it in the CLI docstring.
- [low] QA step 5's selector `pytest tests/unit -k "probe or query_fails"` does not select the S25.16 test, `test_a_failing_query_writes_nothing_and_exits_3` (no "query_fails" in its name). It selects `test_a_failing_probe_is_the_only_query_that_may_fail`, which in fact fails the `differences` query, not the probe. Rename that test (e.g. `test_any_failing_query_but_the_probe_exits_3`) and fix the selector to `-k "probe or failing_query"`.
- [low] `InfluxGateway` sets no query timeout, so a hung span probe would stall the run instead of being recorded as refused. Not exercised; the real probe answered in well under a second of the 16 s run.
Scenarios:      S25.1–S25.13, S25.15, S25.17–S25.19 → pass (e2e `tests/e2e/test_profile_cli.py`, each test tagged with its scenario, 19 profile tests passed. Also walked QA steps 1–5 by hand on `qa_m25`: fixture ingest exit 0 (857 saved); profile exit 0 twice, identical except timing; voltage median 1/max 11/over-2× 1/over-10× 1/11 s in over-2×, longest 08:00:49→08:01:00; process_state count 2, over_2x null, 3 states; ambient median 60; run 10 samples/9 s of 81.0 from 08:00:20; above_documented_max 1, max 140; current no-value 1, BAD 1; pH median_abs/max_abs 0.02; power residual median 0/max_abs 500, matched 106/unmatched 14; CO2 ratio median 0.25, out ≥ in 1; best_lag 3, corr 1.0; r2 1.0 on air_flow², 0.986 on air_flow; EXP_004 points 60/2/1; probe succeeded, 853 = 853; grep no match; schema ok; `dac_missing` exit 2, no report dir, not in the database list) · S25.14 → pass (unit `test_a_refused_span_probe_is_recorded_and_the_profile_still_completes`; a real refusal cannot be provoked on this data, the real probe was answered) · S25.16 → pass (unit `test_a_failing_query_writes_nothing_and_exits_3`, plus a live probe: database whose `readings_numeric.value` is text → exit 3, "Cannot coerce arithmetic expression Utf8 + Float64", no report dir created; see Optional for a pre-filled dir) · S25.20 → pass (real run on a fresh private stack: exit 0, 150 series, 6 experiments, 24 relationships, 4 per experiment, points 519980, 188 queries) · S25.21 → pass (plain SELECT of EXP_001 voltage measured in Python: 7126 points, min 68.19, max 412.0, median interval 1.0, longest run 3 = profile. Beyond that, my own recompute of every measure of all 150 series and 24 relationships from plain pulls, including percentiles, five-longest lists, state counts and the 61-step lag search: 5,064 numbers compared, 0 mismatches) · S25.22 → pass (fresh-stack profile equals committed `reports/post_ingest_profile.json` except timing; `post_ingest_profile.md` equal up to the Timing section; a second run equal too)
Blocked:        none
Checks run:
- `verify-env.js up` → env 54bf10b5, ports 37620-37621, healthy
- `ruff check .` → All checks passed
- `ruff format --check .` → 78 files already formatted
- `python -m pytest tests/unit -v` → 163 passed
- `python -m pytest tests/integration -v -rs` → 31 passed, 0 skipped
- `python -m pytest tests/e2e -v -rs` → 44 passed, 0 skipped (25 ingest, 19 profile)
- `python -m scripts.ingest` (real CSV, to `.flow-tmp/ingest`) → exit 0, 520005 = 519980 + 15 + 10 + 0
- `python -m scripts.post_ingest_profile --report-dir .flow-tmp/profile` (and again to `.flow-tmp/profile2`) → exit 0 both, outputs identical except timing
- `check-jsonschema --schemafile contracts/post_ingest_profile.schema.json contracts/examples/post_ingest_profile.example.json` → ok; also ok on the committed and the fresh real profile
- `contract.js --task .workflow/dac.md --root <WORKTREE>` → exit 0, both contract rows PASS (the M2 Directory-column issue is fixed)
- S25.17 grep on committed, fresh and fixture outputs → no match
- Probes: window bounds (point at `end` and 1 s before `start` excluded; 6 of 8 counted), signed zero (`-0.00` not below 0, joins a run of `0.00`, min 0.0), experiment with no data (no series, no relationships; span probe 7 vs per-experiment 6, as defined), refusals (empty experiments list, missing file, database without tables → exit 2, nothing written), live failing query → exit 3, engine quirks 1–3 on Core 3.11.2 (quirk 2 and 3 reproduce as written; quirk 1 see Optional); real `dac_raw` holds still only its three tables after profiling
- Raw CSV SHA-256 in repo and worktree = `9f791b42…553f` = committed
- Contract files: untracked since plan; mtimes predate every implementation file, so unchanged by execute. Test changes since baseline: no tracked test modified or deleted; all M2.5 tests are new
- `verify-env.js down 54bf10b5` → removed, no worktree changes reported

### M3 — verify 2026-11-24 @ 4888e32 (+ uncommitted)
Defects:        none
Open questions:
- The M2 and M2.5 done-rule note still applies (their newest Findings blocks predate this branch's base `4888e32`). Spec decision 23 defers re-verifying both to before the merge to `master`.
- CI was not run (nothing pushed). The Spec's "After the judge" step covers it; the new `ci.yml` contract step passes locally through `contract.js`.
Optional:
- [low] Spec Next steps already lists that no test validates the committed `reports/cleaning_summary.json` against the contract. I checked it by hand (`check-jsonschema` on the committed and the fresh real summary: ok). Proposed test `test_committed_cleaning_summary_matches_the_contract`: load `reports/cleaning_summary.json`, validate with `jsonschema.Draft202012Validator(contracts/cleaning_summary.schema.json)`.
- [low] Test changes since baseline, all justified by the Spec: `tests/integration/test_rollup_run.py` rewritten for the processed source (Spec: "rewritten for the processed source; the hand-computed bucket stays"; the bucket's numbers still match the M1 hand computation, with `count_good` 3 because quality is independent of the verdict); `test_no_readings_state_data_reaches_the_rollup` replaced by `test_only_the_asked_experiment_and_window_are_rolled_up` (state rows are no longer in the source table); `tests/unit/test_rollup.py` `sample()` helper gained a `verdict` argument, 279 lines added, none of the old assertions loosened or removed. No test skipped or deleted.
- [info] Contract files unchanged since baseline (`git log` shows them only in `4888e32`, `git status` shows no change).
- [info] The dev `dac_rollup` (16,256 buckets, `m3-v1`): 0 buckets with `count_included = 0` and a leftover `mean`; 0 rows without `count_no_value`.
Scenarios:      S3.1–S3.3 → pass (e2e `test_s3_1`..`test_s3_3`, 3,665 fixture rows; real run: 150 series, processed = raw for all) · S3.4–S3.16 → pass (e2e tests tagged with each id, plus `test_every_verdict_matches_the_construction` over all 3,665 rows; my own boundary probes: spike on the first and last reading flagged, 40-reading flat run at start, middle and end flags exactly 40, limits 0.0 and 200.0 inclusive and ±0.0001 outside, 2 s spacing at 1 Hz not a gap while 2 s + 1 ns is) · S3.17–S3.19, S3.23 → pass (e2e; second run identical; committed and fresh real summaries validate with `check-jsonschema`) · S3.20 → pass (e2e: exit 2, empty report dir, `dac_missing` not listed) · S3.21, S3.22 → pass (unit `-k "exit_3 or exit_4 or policy"` 54 passed) · S3.24 → pass (unit policy tests) · S3.25, S3.26 → pass (e2e `test_s3_25_*`, integration `test_s3_26_*`) · S3.27 → pass (fresh private stack, real CSV ingested exit 0 = 519980 + 15 + 10 + 0; clean exit 0: 150 series, 519,980 raw, 514,443 accepted, 5,537 excluded, balanced true, raw_unchanged true) · S3.28 → pass (queried `readings_processed`: EXP_001 voltage 412.0, EXP_003 pH 27.4, EXP_005 electrolyte −50.0, EXP_004 pressure −3.1 all `outside_physical_limits`; EXP_002 current 0.0 at 09:33:20 `spike`; EXP_006 fan 839.2 `conflicting_duplicate`, flags include `spike`; EXP_004 air_flow: 0 readings at or above 1000 with flatline, 0 below 1000 without; flatline run counts 60/240/40/3600/1350; gap rows equal the profile's over-2×-nominal count for every series) · S3.29 → pass (independent recompute: spike flags only EXP_002 current, EXP_003 fan_speed, EXP_004 pump_speed, EXP_006 fan_speed, one each; flatline flags only EXP_001 conductivity, EXP_003 solvent_temperature and acid_pH, EXP_004 air_flow, EXP_006 co2_out_ppm) · S3.30 → pass (committed report has 18 samples, 3 for each of the 6 reasons that fired, each with 10 neighbours; the report equals `render_report(summary)` byte for byte) · S3.31 → pass (fresh-stack summary equals committed `reports/cleaning_summary.json` except `timing`) · S3.32–S3.33 → pass (unit tests in `test_cleaning.py`) · S3.34 → pass (unit `test_policy_doc.py`)
Blocked:        none
Checks run:
- `verify-env.js up` → env 366b8415, ports 35420-35421, healthy
- `ruff check .` → All checks passed; `ruff format --check .` → 93 files already formatted
- `python -m pytest tests/unit -q` → 319 passed
- `python -m pytest tests/integration -v -rs` → 36 passed, 0 skipped
- `python -m pytest tests/e2e -v -rs` → 69 passed, 0 skipped
- `python -m scripts.ingest` (real CSV, to `.flow-tmp/ingest`) → exit 0
- `python -m scripts.clean --report-dir .flow-tmp/clean` → exit 0; `check-jsonschema` on its summary → ok
- `python -m scripts.rollup` → exit 0, 16,256 buckets in 12 m 0 s; all 16,256 buckets equal the dev `dac_rollup` (counts, min, max, mean, median, std, policy_version); count_all + count_no_value = 519,906 numeric rows, count_included = 514,369 = 514,443 accepted − 74 state events
- `contract.js --task .workflow/dac.md --root <WORKTREE>` → exit 0, 3 of 3 PASS
- Independent recompute (scratch script, imports no pipeline code; limits from Spec decision 9, steps and nominals from the profile): all 519,980 stored rows' value_raw, value, quality, verdict, reason, flags equal; all gap and flatline interval rows equal; state intervals equal; 0 mismatches. A first run showed 48 "profile" mismatches caused by my own script keying the profile by signal without experiment; fixed and rerun, 0.
- Raw CSV SHA-256 in repo and worktree = `9f791b42…553f` = committed
- `verify-env.js down 366b8415` → removed, no worktree changes reported

### M3 — verify correction 2026-11-24 @ 1dcd428
Defects:        [fixed in the follow-up commit] CI `integration` job failed at collection: `tests/unit/test_clean_cli.py` and `tests/e2e/test_clean_cli.py` share a basename, so `python -m pytest` from the repo root stops with "import file mismatch" (GitHub Actions run 45400042405; reproduced locally with `python -m pytest --collect-only`: 391 collected, 1 error).
Why the first verify block missed it: it ran `tests/unit`, `tests/integration` and `tests/e2e` as three separate commands. The CI job (and the Spec's Checks table, by listing them separately) never ran the whole suite in one session. The first block's "Defects: none" was wrong for the full-suite command.
Fix: renamed the unit file to `tests/unit/test_clean_exit_codes.py` (content unchanged); updated the one doc reference in `reports/M3.md`. The Spec still names the old path in its Tests and T3 lines (historical).
Optional:
- [low] Add a Checks row `python -m pytest -v` (whole suite, stack up) so a basename clash is caught by verify, not only by CI.
Checks run after the fix: `python -m pytest --collect-only -q` → 424 collected, 0 errors; no duplicate test basenames under `tests/`; `ruff check .` and `ruff format --check .` pass; `python -m pytest tests/unit -q` → 319 passed. CI result: see the next block if recorded.

### M4 — verify 2026-11-24 @ a7bade1 (+ uncommitted) — INCOMPLETE, stopped at the usage limit
Defects:        none raised (no check finished, so this is not a clean result)
Open questions:
- Nothing of M4 is committed yet: `m4-metrics` HEAD is still the baseline `a7bade1`; all M4 work is uncommitted or untracked.
- `capture_series(..., inlet=True)` uses only instants where co2_out is also accepted (`pipeline/metrics.py:212`). Decision 9 says "likewise with co2_in alone"; this reads it as "ppm = co2_in" on the captured series' instants. Probably intended (keeps `capture_below_inlet` like for like), but the Spec doesn't say so.
- `count_series` counts every policy version under one metrics version (`pipeline/metrics_store.py:187-192`). Reading the code, after a run under a second policy version the read-back would count both sets and report a mismatch (exit 4). Not probed.
Optional:       none yet
Scenarios:      S4.1–S4.28 → Blocked (not exercised; see Blocked)
Blocked:
- Every Spec → Checks row, the contract runner, the QA procedure and the probes. The verify stopped at the usage limit. Code read so far: `pipeline/metrics.py`, `pipeline/metrics_store.py`, `pipeline/metrics_run.py`, `migrations/0003_experiment_metrics.sql`. Not read yet: `scripts/metrics.py`, every test file, the fixture, the contract, the docs, the committed reports.
Checks run:
- `verify-env.js up` → env b6d3da2d, ports 34340-34341, healthy
- Real ingest → clean → metrics run in the worktree: no usable result. `scripts.ingest` exited 3 after 35 s with `PermissionError [WinError 32]` while deleting a temp file (`tmp…\run_1.csv`) in the external-sort cleanup on Windows (not investigated: it may be an M2 issue, or the file may have been held by my own concurrent calls). `clean` and `metrics` then exited 2 (`influx_not_configured`) because the stack's `.env` was gone after the failed teardown. Treat as Blocked, not as a defect.
- `verify-env.js down b6d3da2d` → run at the end of this session

### M4 — verify 2026-11-24 @ a7bade1 (+ uncommitted)
Supersedes the INCOMPLETE block above. All M4 work is still uncommitted or untracked on `m4-metrics`; this block reviews the working tree (the verify-env worktree copies it).
Defects:        none
Open questions:
- Three scenario texts disagree with the build, all already listed under Next steps for the next `/flow:plan M4`, so not defects here: S4.9 says 268 `capture_rate` rows, the construction gives 269 (I re-derived it: 297 − 28 = 269, consistent with the pinned 532 s coverage); S4.24 pins `sec_kwh_per_kg` complete for EXP_002, the run gives partial at 0.932916667, because its value covers the power ∩ capture overlap and EXP_002 power coverage is 0.933; S4.25's 0.99 fails for EXP_001 (0.983157895), read as Sebastian decided (Next steps): the other five are 1.0 and the 120 s shortfall is explained in `reports/M4.md`.
- Inlet CO2 on the captured series' instants (open question of the incomplete block): ADR-0016 item 24 records it; the Spec's decision 9 still says "co2_in alone". Add one line to Spec → Decisions at the next plan.
- Nothing is committed or pushed, so CI has not run on M4. The Spec's "After the judge" step covers it.
Optional:
- [medium] Read-back counts ignore the cleaning policy version. `count_series` filters on experiment, metric and metrics version only (`pipeline/metrics_store.py:187-192`), while `write_series` tags each point with `policy_version` too. Once `metrics_series` holds a second policy version, every later run exits 4. Probe on the real run: wrote one point `policy_version=m3-probe` for EXP_001 `power_computed` at 08:00:00Z, reran `python -m scripts.metrics` → exit 4, mismatch `{influx, EXP_001, power_computed, written 7125, read_back 7126}`. Same cause: if a cleaning rerun under the same policy version accepts fewer readings, the old points stay and the read-back exceeds the write. Fix: add `policy_version` to `count_series` (and its call in `pipeline/metrics_run.py:558`). Proposed test `test_count_series_counts_only_the_given_policy_version` (integration, `tests/integration/test_metrics_store.py`): write 3 points under `pv-a` and 2 at other instants under `pv-b`, same experiment, metric and metrics version; assert `count_series(..., policy_version="pv-a") == 3`. Note also that the Postgres key `(experiment_id, metrics_version, metric)` has no policy version, so a run under a second policy overwrites the first one's Postgres rows while both stay in InfluxDB. That is a design point for `/flow:plan`, not a bug in this milestone.
- [low] `has_policy_rows` runs over the whole table with no time bound (`pipeline/metrics_store.py:158-160`). It worked on the real data (six 2 h windows). Over long continuous data it may run into Core's file limit (ADR-0004, U-05). Bound it to the experiments' span when U-06 is taken up.
- [info] Test changes since baseline: `tests/integration/test_migrations.py` expects `0001, 0002, 0003` (was `0001, 0002`), checks the two new tables exist, and adds `test_migration_0003_pins_the_keys_foreign_keys_and_status_check`. The Spec's Tests line asks for this. No test deleted, skipped or loosened.
- [info] Contract files are new in M4 (untracked, written at plan time). With nothing committed there is no baseline to diff against. Their content matches the Spec's summary shape (13 metric names, 4 series, 25 signals, 4 checks, `parameters` = `POLICY` keys, which a unit test checks).
Scenarios:      S4.1, S4.2, S4.4, S4.5, S4.7, S4.9 (at 269), S4.12, S4.13, S4.16, S4.17, S4.18 (all five refusals), S4.21 → pass (e2e `tests/e2e/test_metrics_cli.py`, every test passed, including the plain-pull recompute of every fixture metric and series) · S4.3, S4.6, S4.8, S4.10, S4.11, S4.22 → pass (unit `tests/unit/test_metrics.py`; plus my own probe: 3,000 random series, `overlap`, `covered_intervals`, `integrate` and `integrate_over` against brute force, 0 mismatches; `as_of` at 120 s used and at 120 s + 1 ns not) · S4.14, S4.15 → pass (integration `tests/integration/test_metrics_store.py`; on the real run, the Postgres `public` join gives 13 rows per experiment with `current_setpoint_nominal_a` 150/250/150/150/150/150, and `signal_quality` has 25 rows per experiment) · S4.19, S4.20 → pass (unit `tests/unit/test_metrics_exit_codes.py`) · S4.23 → pass (unit `tests/unit/test_metrics_doc.py`) · S4.24 → pass apart from the recorded EXP_002 `sec_kwh_per_kg` label (Open questions): exit 0, six experiments with 13 metrics each; `energy_kwh` partial only for EXP_002 (0.933055556); capture metrics partial for EXP_004 0.4997, EXP_005 0.7497, EXP_006 0.3575, complete for EXP_001–003; `capture_efficiency_mean` partial only for EXP_006 (0.3575) · S4.25 → pass as Sebastian ruled: EXP_002–006 1.0; EXP_001 0.983157895 = 7,005 of 7,125. I queried the 120 out-of-tolerance instants: one run from 09:23:20 to 09:25:19, residual 5,997–6,063 W, as `reports/M4.md` states; all six `energy_agreement` checks pass · S4.26 → pass (scratch script `recompute_m4.py`, imports no pipeline code, plain `SELECT` pulls of accepted rows: all 9 computed metrics with their coverage, `power_check`, `efficiency_check` and `series_written` of all six experiments equal the summary at 9 significant digits, and every stored `metrics_series` instant and value matches; 0 mismatches) · S4.27 → pass (150 of 150 series: `present` = `raw_points` and `accepted` = `accepted` of the fresh `cleaning_summary.json`; `bad` and `uncertain` equal a `GROUP BY quality` on `readings_processed` and `state_intervals`; pairs with no series have present 0) · S4.28 → pass (24 of 24 plausibility checks pass; the fresh-stack summary equals the committed `reports/metrics_summary.json` except `timing`; the fresh report equals the committed one byte for byte; the committed report equals `render_report` of the committed summary)
Blocked:        none
Checks run:
- `verify-env.js up` → env 8b9b6be9, ports 36280-36281, healthy
- `ruff check .` → All checks passed; `ruff format --check .` → 108 files already formatted
- `python -m pytest -v -rs` (whole suite, stack up) → 607 passed, 0 skipped (unit 462, integration 54, e2e 91). This one session covers the separate unit, integration and e2e rows.
- `python -m pytest tests/unit -q` (before the stack runs) → 462 passed
- `python -m scripts.ingest --report-dir .flow-tmp/ingest` (real CSV, run alone) → exit 0: 520,005 rows = 519,980 saved + 15 copies + 10 losers + 0 rejected (the Windows temp-file error of the last attempt did not recur)
- `python -m scripts.clean --report-dir .flow-tmp/clean` → exit 0: 150 series, 519,980 raw, 514,443 accepted, 5,537 excluded, balanced
- `python -m scripts.metrics --report-dir .flow-tmp/metrics` → exit 0: 6 experiments, 121,167 points, 228 Postgres rows, balanced, 0 plausibility failures; `check-jsonschema` on it → ok; rerun into `.flow-tmp/metrics2` → exit 0, summary equal except timing
- `check-jsonschema` metrics example and committed `reports/metrics_summary.json` → ok
- `contract.js --task .workflow/dac.md --root <WORKTREE>` → exit 0, 4 of 4 PASS
- Database list after the runs: `_internal, dac_pinned, dac_raw, dac_rollup` (nothing created); `dac_raw` tables: the six inputs plus `metrics_series`
- Raw CSV SHA-256 in repo and worktree = `9f791b42…553f` = committed
- `verify-env.js down 8b9b6be9` → removed; no worktree changes reported; `docker ps -a` and `docker volume ls` show no verify containers or volumes left (the earlier env b6d3da2d is gone too)

### M5 — verify 2026-11-24 @ fdb427d
Defects:        none
Open questions:
- S5.14, S5.20 and the draft findings agree with the build, but one Limits-section number has no reference test: the lag-1 block correlation of EXP_005's residuals (0.87; others -0.15 to 0.12). I re-measured it from plain pulls (EXP_001 -0.153, EXP_002 -0.037, EXP_003 0.124, EXP_004 -0.030, EXP_005 0.873, EXP_006 0.123), so the number is right. Already a Next step (add it to the summary and contract).
- The Spec still lists the absorber model as untestable end to end on the fixture and decision 13's wording as out of date; both are already under Next steps, so not defects.
Optional:
- [low] `reports/comparison_report.md` is checked in with LF endings, but `.gitattributes` has no rule for `reports/`. On this Windows checkout (`core.autocrlf=true`) the fresh worktree copy had CRLF (880 lines), so S5.22's "report equals the committed report byte for byte" fails on a raw byte compare (equal after LF normalisation; the summary is equal except timing). Fix: add `reports/*.md -text` and `reports/*.json -text` to `.gitattributes` (as done for `migrations/*.sql`), or compare with normalised endings in any future test. Proposed test: `test_committed_comparison_report_has_lf_endings` (unit): read `reports/comparison_report.md` as bytes and assert `b"\r\n" not in bytes`.
- [info] My independent recompute differs from the summary by relative 3.4e-8 on one `r2_drop` (absorber steady EXP_002 air_flow, 6.4e-9, absolute 2e-16): floating-point cancellation between two R² values near 1, not a logic difference. Seven more values differ only in the 9th digit, all `r2_drop` or `corr_at_zero` below 1e-6.
- [info] Test changes since baseline: no existing test modified, deleted or skipped. All 11 test files under `tests/` in the diff are new. Only existing non-test file changed: `contracts/examples/metrics_summary.example.json` (`capture_rate` 268 to 269), recorded in Decisions item 24. Contract files are new in M5 and match the Spec's summary shape (28 voltage fits, 8 evidence rows, 15 comparisons).
Scenarios:      S5.1–S5.9 → pass (unit `tests/unit/test_compare.py`, `tests/unit/test_comparison_doc.py`) · S5.10, S5.11 → pass (integration `tests/integration/test_compare_store.py`) · S5.12–S5.19 → pass (e2e `tests/e2e/test_compare_cli.py`, including the plain-pull recompute of fixture phases, KPIs and hydrolyzer coefficients; refusals all exit 2 with an empty report dir; `unit/test_compare_exit_codes.py` covers exit 3 and 70) · S5.20 → pass (real run exit 0: 6 experiments, each with 7 to 19 phases, 5 steady KPIs and 13 whole-run metrics; 28 voltage fits, all testable, 0 singular resamples; 8 evidence rows; 15 comparisons, 1 supported (EXP_001–EXP_002) and 14 confounded; 6 pressure-drop entries; `airflow_check` present for EXP_004) · S5.21 → pass (scratch `recompute_m5.py`, no pipeline imports, OLS by numpy lstsq with per-experiment dummy intercepts, bootstrap re-implemented from decision 10's text: 3,541 values, 3,533 equal at 9 digits, 7 differ only in the 9th digit, 1 `r2_drop` of 6.4e-9 differs at relative 3.4e-8 from float cancellation; all statuses, signs, flags, lags and counts equal) · S5.22 → pass with the line-ending note above (fresh private stack, ingest, clean, metrics and compare on the real CSV: summary equal to committed `reports/comparison_summary.json` except `timing`; report equal after LF normalisation) · S5.23 → pass (plain `COUNT` per signal and side of 09:00Z for EXP_004: air_flow 3600/3600 from `value_raw`, fan_speed 3600/3600, pressure_drop, co2_in_ppm, co2_out_ppm and capture_efficiency 1800/1800, equal to the summary) · S5.24, S5.25 → pass (`tests/unit/test_findings_doc.py`, incl. the mutation tests; I also checked the unreferenced claims in the text against the summary: all 8 evidence rows `not_resolved`; per-experiment steady hydrolyzer intervals all include zero; whole-run flow excludes zero only in EXP_005; absorber steady air_flow excludes zero only in EXP_001 and pressure_drop only in EXP_003 and EXP_005, pooled pressure_drop positive; whole-run hydrolyzer flow VIF 14.3 to 28.7; 14 confounded pairs; status line reads "draft, awaiting Sebastian's approval") · S5.26 → pass (`tests/unit/test_comparison_doc.py`)
Blocked:        none
Checks run:
- `verify-env.js up` → env 42a90ddc, ports 38370-38371, healthy
- `ruff check .` → All checks passed; `ruff format --check .` → 125 files already formatted
- `python -m pytest tests/unit` → 679 passed
- `python -m pytest -v -rs` (whole suite, stack up) → 874 passed, 0 skipped. Covers the unit, integration and e2e rows.
- `check-jsonschema` on the comparison example and on the committed `reports/comparison_summary.json` → ok; `contract.js --task .workflow/dac.md --root <WORKTREE>` → exit 0, 5 of 5 PASS
- `python -m scripts.ingest` (real CSV) → exit 0: 520,005 rows = 519,980 saved + 15 copies + 10 losers + 0 rejected
- `python -m scripts.clean --report-dir .flow-tmp/clean` → exit 0: 150 series, 514,443 accepted, 5,537 excluded, balanced
- `python -m scripts.metrics --report-dir .flow-tmp/metrics` → exit 0: 6 experiments, 121,167 points, 228 Postgres rows, 0 plausibility failures
- `python -m scripts.compare --report-dir .flow-tmp/compare` → exit 0, 219 queries, 43 s
- Database list after all runs: `_internal, dac_pinned, dac_raw, dac_rollup` (nothing created or left behind)
- `verify-env.js down 42a90ddc` → removed; no worktree changes reported; no verify containers or volumes left
