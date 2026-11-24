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

### Goal
Build everything in `task/TASK.md` A–J, one roadmap milestone at a time. Current milestone, M3:
decide for every stored reading whether it can be trusted, write raw value, processed value, flag,
decision and reason side by side, record gaps and stuck stretches as intervals, rebuild the rollup
over that decision, and prove by counts that nothing was dropped or quietly changed.
M2.5 (built): measure the stored data and write the numbers to a file, without judging any reading.
M2 (built): copy the raw CSV into InfluxDB without losing or quietly changing anything, and prove it with counts.
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
- M3: EXP_004 pressure −3.1 bar: its acquisition flag decides whether the reason is `flag_uncertain` or `outside_physical_limits`; either way it is excluded (Claude, at execute).

### Next steps (not in this budget)
- Cross-run duplicate detection — out of scope per ADR-0007; belongs with deliverable H — medium.
- Parallel ingest by experiment — not needed at 520k rows — small.
- Multi-pass merge in the external sort — only needed past the OS open-file limit — small.
- M2 verify's three low findings (offset minutes over 59 accepted, signed-zero tie on file order, second `up` overwrites `.env`) belong to M2, not M2.5 — fix before the M2 merge or record as accepted — small.
- Core 3.11.2 gets four things wrong that M3's cleaning SQL must avoid or work around: `COUNT(*) FILTER` counts NULL conditions produced by a window function such as `LAG` (at least; a NULL from a plain row is not counted — M2.5 judge), `-0.0` is not equal to `0.0`, `PERCENTILE_CONT` is only about 7 digits accurate, and parallel sums vary in the last bits (ADR-0014). Found 2026-11-23 in M2.5; the rollup driver uses none of the first three (grep) but its sums have the last property — small.
- The profile measures pressure drop against air flow at the same instant: R squared below 0.17 in all six experiments, although the data dictionary says it scales with air flow. M5 should check whether a lag or another definition changes that before anyone cites it — small, found 2026-11-23.
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
- Not yet detailed. Scope: `docs/ROADMAP.md` § M4.

#### M5: Comparison and findings (F)
- Not yet detailed. Scope: `docs/ROADMAP.md` § M5. Headline findings need Sebastian's approval.

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
