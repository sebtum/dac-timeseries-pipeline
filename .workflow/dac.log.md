# dac: execute log

### M2

Status: implemented, not committed. Revision at start: `1c5b6ea` on `m1-data-model`; work is on a
new branch `m2-ingestion` cut from it (decision 16). Mode: standard, no `T<n>` task lines, so
worked directly with no subagents.

Changed (new): `scripts/verify_stack.py`, `pipeline/signals.py`, `pipeline/ingest.py`,
`pipeline/ingest_influx.py`, `scripts/ingest.py`, `tests/fixtures/ingest/{slice.csv,experiments.json,slice.sha256}`,
`.gitattributes`, `tests/e2e/{conftest,helpers,test_ingest_cli}.py`,
`tests/unit/test_ingest_{parse,resolve,retry}.py`, `tests/unit/test_verify_stack.py`,
`docs/decisions/ADR-0013-ingestion.md`, `reports/M2.md`, `reports/ingest_{summary.json,report.md,rejects.csv}`.
Changed (edited): `pipeline/collisions.py` (+`group_by_instant`, `find_collisions` built on it),
`docker-compose.yml` (container names overridable), `.env.example`, `.gitignore`
(`.env.pre-verify`), `requirements.txt` (+`check-jsonschema==0.39.0`, `jsonschema==4.26.0`),
`.github/workflows/ci.yml` (contract step in lint), `docs/{ROADMAP,ASSUMPTIONS,MISTAKES,schema}.md`,
ADR-0007 addendum, ADR index. Not touched: `generator/`, `contracts/`, existing tests.

Checks (revision `1c5b6ea` + uncommitted):

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean |
| `python -m pytest -q` (private stack, then dev stack) | 179 passed, 0 skipped (unit 123, integration 31, e2e 25) |
| `check-jsonschema --schemafile contracts/ingest_summary.schema.json contracts/examples/ingest_summary.example.json` | ok |
| `python -m scripts.ingest` on the real CSV, twice (dev `dac_raw`) | exit 0 both; 520005 = 519980 + 15 + 10 + 0; 150/150 balanced; readings and conflicts identical after run 2 |
| SHA-256 of `data/raw/dac_raw_timeseries.csv` after both runs | equals the committed value |
| S2.1 to S2.4 by hand (`up`, `health`, `down`, dev containers and volumes before/after, `docker compose config`) | pass |
| `node scripts/contract.js --static` | **did not run**: node's `spawnSync` of `C:\Program Files\Git\bin\bash.exe` returns ENOENT in this session (the file exists; a bare node spawn of it fails the same way). The one contract command in it was run directly and passes. |
| GitHub Actions | not run (nothing pushed) |

Decisions made during Execute, beyond the plan (all in ADR-0013 "Interpretations"):
- out-of-order = earlier than the previous row of the series (census definition);
- conflict-row file positions swap with row order, so the file-order scenario compares every other field and checks the swap;
- rows with no usable series key are counted under `("", "", "")`, garbage keys capped at 5000;
- table is `null` in the summary for rows of an unknown experiment;
- unexpected exceptions exit 70 with a traceback and no summary (the contract allows 0 to 4 only);
- `use_v2_api=False, accept_partial=False` set explicitly after the probe (v2 endpoint is always atomic).

Mistake logged: MISTAKES.md E-08 (`verify_stack up` lost the admin token on a second run).

Remaining gaps: CI run; the judge; rollup driver fails on a no-value point (parked in Spec Next
steps); no tuning of batch size.

State left behind: private stack `dac-verify-abc` is down; the dev stack was started to run the
committed real ingest and then stopped (volumes kept, dev `dac_raw` holds the real data for M2.5).
`.env` is the dev one again.

### M2.5

Status: implemented, not committed. Revision at start: `77b8516` on `m2-ingestion`; work is on a new
branch `m2.5-profiling` (decision 11). Mode: standard, no `T<n>` task lines, so worked directly with no
subagents. M2's done-rule note (newest Findings block at `1c5b6ea`, HEAD `77b8516`) was seen; Sebastian
invoked execute for M2.5 with the earlier M2.5 verify's "next step is /flow:execute M2.5" in the record.

Changed (new): `pipeline/profiling.py`, `pipeline/profiling_sql.py`, `scripts/post_ingest_profile.py`,
`tests/unit/test_profiling.py`, `tests/e2e/test_profile_cli.py`, `tests/fixtures/profile/{readings.csv,experiments.json,readings.sha256}`,
`docs/decisions/ADR-0014-post-ingest-profiling.md`, `reports/{post_ingest_profile.json,post_ingest_profile.md,M2.5.md}`.
Changed (edited): `pipeline/signals.py` (+`NOMINAL_INTERVAL_S`, `DOCUMENTED_RANGE`), `.github/workflows/ci.yml`
(contract step for the new schema), `.gitignore` (`.flow-tmp/`), `docs/{ROADMAP,ASSUMPTIONS}.md`, ADR index.
Not touched: `generator/`, `contracts/`, existing tests, raw CSV (SHA-256 re-checked equal).

Checks (revision `77b8516` + uncommitted):

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean (78 files) |
| `python -m pytest -q -rs` on a private stack (`dac-verify-m25`) | 238 passed, 0 skipped (unit 163, integration 31, e2e 44) |
| `check-jsonschema` on both contract examples and on the committed `reports/post_ingest_profile.json` | ok |
| `node contract.js --task .workflow/dac.md --static` | both contract rows PASS |
| `python -m scripts.post_ingest_profile` on dev `dac_raw`, 3 runs | exit 0 each; 150 series, 6 experiments, 24 relationships, 519,980 points, 188 queries, ~16 s; JSON identical except timing |
| Independent recomputation in Python from plain SELECT pulls, all 6 experiments | 150 series + 24 relationships, 0 mismatches at 9 digits (tolerance 6e-9 relative) |
| Fresh private stack: real CSV ingested, profile re-run | equals committed `reports/post_ingest_profile.json` except timing (S25.22) |
| Verdict-word grep on both outputs | no match |
| GitHub Actions | not run (nothing pushed) |

Calibration (decision 14), in order: first run on EXP_001 → 50 mismatches vs the Python pull, from
`COUNT(*) FILTER` (NULL counted), signed zero (`-0.0 < 0`) and `PERCENTILE_CONT` (float32-grade fraction);
fixed with `COUNT(CASE ...)`, `value + 0.0`, and rank-weighted percentiles in SQL. Then a second full run
differed in two `regr_intercept` values (9th digit): parallel sums vary in the last bits. Fits moved to
Python with `math.fsum`. All in ADR-0014.

Decisions made during Execute, beyond the plan (all in ADR-0014):
- fits (corr, slope, intercept, R squared) and the lag in Python; per-value measures stay in SQL (plan decision 4's fallback, per measure);
- exact percentiles by rank weights in SQL instead of `approx_percentile_cont` (plan's open assumption on p05/p95 stability);
- `instants_unmatched` = points of the first-named signal without a partner; relative residual is absolute; stddev is sample;
- runs and step-to-step change use only points with a value; intervals use all points.

Remaining gaps: CI run; the judge; S25.20 to S25.22 ran by hand here, the judge reruns them from QA steps 6 to 8.
Hand-edits to Spec: only two lines appended to Next steps.

State left behind: private stack `dac-verify-m25` removed; `.env` is the dev one; dev containers
`dac-influxdb` / `dac-postgres` were started for this milestone and stopped again (volumes kept; dev `dac_raw` holds the real data); `.flow-tmp/` holds scratch output (gitignored).

### M3

Status: **stopped at calibration, not finished, not committed.** Revision at start: `4888e32` on
`m2.5-profiling`; work is on a new branch `m3-cleaning` (decision 22), nothing committed yet. Mode:
standard, no `T<n>` task lines, so worked directly. Done-rule note: M2 and M2.5 have Findings only at
`1c5b6ea` / `77b8516 (+ uncommitted)`, HEAD was `4888e32` (the M2.5 work, committed unchanged). Sebastian
invoked execute M3 anyway, so I went ahead; the judges for M2 and M2.5 have not run at the commit.

Done so far (all new, untested beyond the calibration below):
`pipeline/cleaning_policy.py` (table, `POLICY_VERSION = "m3-v1"`, `policy_fingerprint()`),
`pipeline/cleaning.py` (pure rules, intervals, summary, samples, report), `pipeline/cleaning_influx.py`
(gateway, line protocol for the three tables), `scripts/clean.py` (CLI). `ruff check` / `ruff format` clean.
Not started: rollup changes (`rollup.py`, `rollup_run.py`, `scripts/rollup.py`), the clean fixture, every
test, ADR-0015, docs, the committed real outputs, `reports/M3.md`, CI contract step.

Decision 15 measured (dev InfluxDB, throwaway database, dropped):
(a) a later write of the same key without a field **keeps the old field value** (point at t1 written with
`value=2.5`, rewritten without `value` still reads 2.5); (b) an empty string field is stored and read
back as `""` (length 0). So accepted rows use `""`, not `none`. Consequence handled in the code: the
read-back also counts rows that carry a value and compares with the accepted count.

Calibration (decision 20), read-only on dev `dac_raw`, `.flow-tmp/calibrate.py`: EXP_001, then all six.
Every feature the plan pinned in S3.28 shows up with exactly the predicted counts (412.0, pH 27.4,
-50.0 outside limits; fan_speed, pump_speed, current spikes at the stated instants; 240 / 1350 / 3600 /
60 / 40 flatline readings; 200 and 30 UNCERTAIN; pressure -3.1 excluded; 10 conflict instants; gaps
per series as the profile's over-2x counts). **Four things are not in the pinned S3.29 list:**

| # | Where | What fired | What it is |
|---|---|---|---|
| 1 | EXP_001 solvent_pH 09:28:10, 09:28:15 | flatline, 2 readings | chance: steps 0.003 and 0.009 against a threshold of 0.0097, plus scattered small steps in the window of 13 (7 flat of 13) |
| 2 | EXP_005 ambient_pressure 07:40 to 07:44 | flatline, 5 readings | same cause: smooth signal, steps 0.01 / 0.00 against a threshold of 0.012 |
| 3 | EXP_005 available_solar_power 06:00 to 06:24 | flatline, 25 readings | the dawn ramp (steps 0.8 to 5) is slower than 0.2 x 12.255 = 2.45, the day-time step size |
| 4 | EXP_006 fan_speed 11:10:17 | `spike` in flags (primary reason stays `conflicting_duplicate`) | a real one: 839.2 among readings near 900; the kept value of a conflict pair |

Evidence for a fix (`.flow-tmp/variants.py`, same data): requiring the flagged step to sit in an unbroken
run of at least 5 flat steps removes #1 and #2 and keeps all five pinned flatline features with identical
counts (60 / 240 / 40 / 3600 / 1350); with 3 it leaves 3 readings of #2; with 8 it leaves 11 of #3. #3 is
not fixed by any run length: a smooth ramp is flat by this definition.

Stopped here because S3.29's note says an extra spike or flatline comes back to `/flow:plan M3`. Raw CSV
not touched, no write to any InfluxDB table (only the throwaway probe database, dropped).

State left behind: dev containers `dac-influxdb` / `dac-postgres` started for the calibration, stopped
again; `.env` unchanged; `.flow-tmp/` holds scratch scripts (gitignored).

#### M3 re-run after the re-plan (decisions 24-27), tasks in waves

Revision at start `4888e32` on `m3-cleaning`. Calibration stop above is resolved by the re-plan.

**W1 (T1, T2) done.** `lane.js check --wave W1` ok; `pytest tests/unit` 257 passed; ruff clean; `contract.js --static` 3 PASS.
- T1: `FLAT_MIN_RUN = 5` and solar exact-repeat rule in `cleaning_policy.py` / `cleaning.py`; `_ZERO_IS_IDLE` removed; fingerprint re-pinned (`2b004502...49358bb`, `m3-v1`); `tests/unit/test_cleaning.py`, `test_cleaning_policy.py` (78 tests). Notes: a short exact run (about 12 readings) in 1 Hz noise is not flagged (majority window h = 30); `.flow-tmp/variants.py` uses the removed `zero_is_idle` (T4 must not reuse it); real-data counts not re-run yet.
- T2: `Sample.value` may be None, `count_no_value`, `run_rollup` reads `readings_processed` (signature changed: `experiment_id` required), `scripts/rollup.py` new; unit 28, integration 10 pass against live Core. Choice: no rows of the current policy version -> exit 2. Dev `dac-influxdb` left running.

**W2 (T3) done.** `lane.js check --wave W2` ok; `pytest tests/unit` 290 passed; `pytest tests/e2e/test_clean_cli.py` 25 passed, 0 skipped (live dev Core, throwaway databases dropped); ruff clean; `contract.js --static` 3 PASS; raw SHA-256 OK.
- T3: fixture `tests/fixtures/clean/` (3667 rows, 3665 saved + 1 exact copy + 1 conflict loser); `cleaning_influx.py` fix (`has_column` before `COUNT(value)`, since a table with only excluded rows has no `value` column); `tests/unit/test_clean_cli.py` (33), `tests/e2e/test_clean_cli.py` (25, includes a SELECT-pull recompute of all 3665 verdicts). Fixture run: 12 series, 3368 accepted, 297 excluded, 1 gap, 2 flatline runs, re-run identical; rollup 08:02 bucket: 60 / 59 / min 99.925 / max 140.0 / mean 99.99872881.
- Notes: e2e rollup goes into the same throwaway database as the clean (`--rollup-database` = `--database`), since Core allows 5 databases and 4 exist; 140 V rows also carry `outside_typical_range` (typical voltage 60-130), so S3.14 flags read `flag_bad,spike,outside_typical_range`; flatline boundary at +360 s is tight (31 of 61 steps flat).

**W3 (T4) done.** `lane.js check --wave W3` ok; I re-checked: summary validates against the contract; 150 series, raw 519,980 = accepted 514,443 + excluded 5,537, balanced, raw_unchanged; raw SHA-256 OK; `.env` is the dev one.
- T4: calibration on EXP_001, EXP_004 and all six: 0 mismatches between `pipeline.cleaning` and an independent recompute (verdicts, gaps, flatline intervals). Spikes only in the four S3.29 places; flatline only in the five S3.29 series (60 / 40 / 240 / 3600 / 1350); the earlier chance hits are gone. excluded_by_reason: flag_bad 100, flag_uncertain 230, outside_physical_limits 4, conflicting_duplicate 10, spike 3, flatline 5190 (flags: spike 4, flatline 5290, outside_typical_range 10,242); 29 gaps = profile's over-2x counts; 5 flatline runs. Tables in dev `dac_raw`: readings_processed 519,906 + state_intervals 74; quality_intervals 34. Re-run on dev and fresh private stack (`m3t4`): summary identical except timing. Rollup: 16,256 buckets in about 12 min (about 2 min per experiment, silent until each finishes).
- State: private stack removed; dev `dac-influxdb` up; `.env` dev; `.flow-tmp/t4/` scratch.

**W4 (T5) done.** Write-up: `docs/cleaning_policy.md` (25 rows), `docs/decisions/ADR-0015-cleaning-and-quality-pipeline.md`, ADR-0011 addendum, `docs/schema.md`, `docs/ASSUMPTIONS.md` (closed U-04, U-09, U-10, U-12; narrowed U-06; added A-05, A-06, A-07), `docs/ROADMAP.md`, `docs/decisions/README.md`, `.github/workflows/ci.yml` (contract step), `reports/M3.md`, `tests/unit/test_policy_doc.py` (29 tests, mutation-checked). Four lines appended to Spec Next steps. `lane.js check --wave W4` flags only `.workflow/dac.md` (the allowed Next-steps append; the other diff in that file is the plan's).
- Lead edit: added a note to ADR-0015 that the `Rejected` cell for decisions 5, 8, 9, 11, 13, 14, 16, 17, 19-22 was written at the write-up (the plan recorded none).

### M3 final (revision `4888e32` + uncommitted, branch `m3-cleaning`)

Status: implemented and verified by me, **not committed, not pushed, judge not run**. Mode standard, tasks T1-T5 by agents (decision 27).

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean (94 files) |
| `python -m pytest tests/unit -q` | 319 passed |
| `python -m pytest tests/integration tests/e2e -q -rs` (dev stack, Postgres started for the run, stopped after) | 105 passed, 0 skipped. (First run without Postgres: 91 passed, 14 skipped, rerun after starting it.) |
| `node contract.js --static` | 3 PASS |
| `python -m scripts.clean --report-dir reports` on real data (T4) | exit 0, 150 series, 519,980 = 514,443 + 5,537, balanced, raw_unchanged; re-run and fresh private stack equal except timing |
| `python -m scripts.rollup` on real data (T4) | exit 0, 16,256 buckets, about 12 min |
| independent recompute vs `pipeline.cleaning` (T4, EXP_001, EXP_004, all six) | 0 mismatches |
| SHA-256 of raw CSV | OK |
| GitHub Actions, judge | not run |

Remaining gaps: judge (`/flow:verify M3`), judges for M2 and M2.5 at the commit, commit and push, CI run. Rollup speed (12 min) and the other Next-steps lines are in Spec.
State left behind: dev `dac-influxdb` running (holds processed tables and `readings_rollup`); `dac-postgres` stopped; `.env` dev; `.flow-tmp/` scratch.

### M4

Branch `m4-metrics` cut from `master` (`a7bade1`), uncommitted. Mode standard, tasks T1-T5 by agents (decision 1). Dev `dac-influxdb` and `dac-postgres` started for the run (they were stopped).

**W1 T2 done.** Migration 0003, `pipeline/metrics_store.py` (`MetricsGateway(host, token, database, *, batch_size)` subclasses `CleaningGateway`; `pg_connect`, `pg_check`, `missing_experiments`, `upsert_*`, `write_postgres`, `count_rows`), `tests/integration/test_metrics_store.py` (17) and `test_migrations.py` (+1). 23 passed, 0 skipped against live dev stack; ruff clean; no database leaked. Notes: `has_policy_rows` has no time window (T4 confirms it on real `dac_raw`, 72 h limit); `count_series` counts any `policy_version` for the same experiment, metric and `metrics_version`; `write_series` over 10,000 points goes in several batches; `pg_check` also requires `experiment`. Row-dict keys = table columns, missing or extra key raises `ValueError`.

**W1 T1 done.** `pipeline/metrics.py` (pure, stdlib) and `tests/unit/test_metrics.py` (72). Fingerprint `ac004cdd...b518b` pinned. POLICY has exactly the 10 keys the contract schema lists; `KELVIN_OFFSET` and unit scalings are module constants outside POLICY (not in the fingerprint). Choices: inlet series uses the capture series' instants (shared coverage); an efficiency instant with co2_in = 0 is skipped; coverage 0.0 with status none when no covered time; p95 of |residual| by linear interpolation. Contract doubt: `plausibility.limit` must be a number, so `capture_below_inlet` emits limit 0.0 with passed null when inlet is null (appended to Next steps).
**W1 check:** `lane.js check --wave W1` ok (7 files, all allowed); `pytest tests/unit` 391 passed; ruff check and format clean; `contract.js --static` 4 PASS.

**W2 T3 done.** `pipeline/metrics_run.py`, `scripts/metrics.py`, fixture `tests/fixtures/metrics/` (README with hand computations from plain decimal arithmetic), `tests/unit/test_metrics_exit_codes.py` (27), `tests/e2e/test_metrics_cli.py` (22, includes an independent recompute of every metric and series row). Fixture run: exit 0, balanced, plausibility_failed 0; cleaning of the fixture excludes exactly the four planted readings.
- **Spec inconsistency (I checked it by hand):** S4.9 pins 268 `capture_rate` rows; the construction gives 269. 297 efficiency instants, minus the 28 even seconds from +362 to +418 other than +400 (+400 is already outside the 297). The pinned coverage 532/600 matches 269. Tests, README and summary use 269. Spec text and the contract example (illustrative) still say 268; noted under Next steps, left for `/flow:plan`.
- `parameters` in the summary is not rounded to 9 digits (the gas constant has 10 and must equal `POLICY`). Fixture "even seconds" noise rule is applied by reading index for 0.5 Hz and per-minute signals (by second, the CO2 noise would be constant and cleaning would call it a flatline). `residual_p95_abs_w` in the fixture run is about 1.8e-12 (decimal representation), the test allows 1e-9. A missing processed table or no rows for the policy version is refusal `no_cleaned_readings`.
- Fixture numbers: energy_kwh 2.43332058 (584/600), energy_logged_kwh 2.44590461 (587/600), difference 3.45e-05, mean power 14.9999214 kW, efficiency mean 0.750002923 (592/600), CO2 captured 0.104296861 kg, inlet 0.139062481 kg (532/600), capture rate 0.705768232 kg/h, sec 21.2532386 kWh/kg (517/600). Series written 586 / 586 / 297 / 269.
**W2 check:** `lane.js check --wave W2` ok (9 files, all allowed); unit + new e2e + integration (metrics store, migrations) 463 passed, 0 skipped; ruff clean; `contract.js --static` 4 PASS; raw SHA-256 matches. Databases back to `_internal, dac_pinned, dac_raw, dac_rollup`.

**W3 T4 stopped (no write to `reports/`).** Calibration is done and clean; steps 4 and 5 (final run into `reports/`, rerun, fresh private stack) are not.
- Calibration (scratch `.flow-tmp/t4m/`, independent recompute with no pipeline imports): EXP_001, EXP_004 and all six, 0 differences at 9 digits (13 metrics, coverages, power_check, efficiency_check, 25 signals, plausibility, stored `metrics_series`). S4.24 labels all match. Plausibility: 0 failed, `energy_agreement` passes (largest 0.0067, EXP_001). S4.27: 150 series equal the cleaning summary. S4.26 passes. `has_policy_rows` works on real `dac_raw` without a time window. Raw SHA-256 matches; `.env` is dev. Full `pytest -q -rs` on dev stack: 563 passed, 0 skipped.
- **Stop 1, S4.25:** EXP_001 `within_tolerance_fraction` = 0.983158 (7005 of 7125), under 0.99. Cause: 120 consecutive instants 09:23:20 to 09:25:19 on 2026-05-04 where logged `power` is about 6 kW above voltage x current; all three signals accepted by cleaning, no spike or flatline. Other five experiments 1.0. Energy still agrees (0.67 %). A narrow question for `/flow:plan M4` (threshold, report as a cross-check finding, or a cleaning rule that reopens M3). No code or constant changed. Logged as E-09.
- **Stop 2, dev Postgres cannot take migration 0003:** `python -m scripts.migrate` refuses: migration 0001 recorded checksum 52d6ff5d (the LF bytes), working-tree file is CRLF (`core.autocrlf=true`, index is LF; `.gitattributes` only pins `tests/fixtures/**`). A fresh private stack and Linux CI migrate fine. Not patched by me. Options: pin `migrations/*.sql` to LF in `.gitattributes` and re-checkout, or hash with line endings normalised in `pipeline/pg_migrate.py`. Calibration used a throwaway schema `t4m_calib` (dropped).
- State: dev `dac-influxdb` and `dac-postgres` up; `.env` dev; dev `dac_raw` now holds `metrics_series` (121,167 points from the calibration run; the real run rewrites the same keys); dev Postgres `public` has no 0003 tables.
- Open design note: `residual_median_w` is the median of the signed residual (not absolute); worth one line in `docs/metrics.md`.

### M4 interim status (revision `a7bade1` + uncommitted, branch `m4-metrics`)
T1, T2, T3 done and checked; T4 stopped on S4.25 and the dev-Postgres checksum; T5 (write-up) not started. Not committed, not pushed, judge not run.

**Decisions after the T4 stop (Sebastian, 2026-11-24: "follow your recommendations").** (1) S4.25 keeps 0.99; EXP_001's 0.983 is reported as a cross-check result in the M4 report (recorded in Spec Next steps, S4.25 reworded at the next plan). (2) `.gitattributes` gets `migrations/*.sql -text`; I recreated `migrations/0001`, `0002` from the index (LF, checksum `52d6ff5d` matches the recorded one) and converted `0003` to LF; `python -m scripts.migrate` then applied 0003 on dev Postgres. T4 resumes at its steps 4-6.

**W3 T4 done (second pass).** `reports/metrics_summary.json`, `reports/metrics_report.md` written by `python -m scripts.metrics --report-dir reports` on dev: exit 0, 6 experiments, 121,167 points, 228 Postgres rows (78 + 150), balanced, inputs unchanged, 0 plausibility failures. Independent recompute: 0 differences at 9 digits (13 metrics, power_check, efficiency_check, 150 signals, stored series). Schema valid; S4.27 150 of 150 series; rerun on dev identical except timing; fresh private stack (`m4t4`, ingest, clean, metrics) equal to the committed summary without timing, reports byte-equal; stack down, `.env` dev again. Full `pytest -q -rs` on dev: 563 passed, 0 skipped. Raw SHA-256 matches.
- S4.25 as restated by Sebastian: experiments 2-6 are 1.0; EXP_001 0.983157895 (7005 of 7125); all four energy_agreement checks pass (EXP_001 relative difference 0.00675, which the 120 s block explains).
- **S4.24 does not match in one cell** (the T4 agents reported all labels matching; I compared the summary myself): EXP_002 `sec_kwh_per_kg` is partial (0.9329), not complete. Cause: its coverage is the overlap of power (0.9331) and capture (0.9997). Everything else matches. Recorded in E-09 and Spec Next steps; not a constant change.
- Lead cleanup: the fresh-stack `python -m scripts.ingest` wrote to the default `reports/` and changed the timing lines of the committed M2 ingest outputs; restored from git (timing only).
- Not recorded by the agents' claim: the Postgres password default appears in `docker-compose.yml`, `.env.example`, `ci.yml` and a handoff doc, all pre-M4 files.

**W4 T5 done.** `docs/metrics.md`, `docs/decisions/ADR-0016-derived-metrics.md` (20 decisions + 12 "decided at execute"), `docs/schema.md`, `docs/ASSUMPTIONS.md` (A-08, U-06 note), `docs/decisions/README.md`, `docs/ROADMAP.md`, `.github/workflows/ci.yml` (metrics contract step), `tests/unit/test_metrics_doc.py` (44, 12 mutation checks), `reports/M4.md`. `lane.js check --wave W4` ok (9 files, all allowed).

### M4 final (revision `a7bade1` + uncommitted, branch `m4-metrics`)

Status: implemented and verified by me; **not committed, not pushed, judge not run, CI not run**. Mode standard, tasks T1-T5 by agents.

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean (109 files) |
| `python -m pytest tests/unit -q` | 462 passed |
| `python -m pytest -q -rs` (dev stack, T4) | 563 passed, 0 skipped (before the T5 doc test; unit rerun after: 462 passed) |
| `node contract.js --static` | 4 PASS |
| `python -m scripts.metrics --report-dir reports` on real data | exit 0, 6 experiments, 121,167 points, 228 Postgres rows, balanced, inputs unchanged, 0 plausibility failures |
| independent recompute (no pipeline imports) vs summary | 0 differences at 9 digits, all six |
| re-run on dev; fresh private stack (ingest, clean, metrics) | summary equal except timing, report byte-equal |
| SHA-256 of raw CSV | OK |
| GitHub Actions, judge | not run |

Remaining gaps (all in `reports/M4.md`): S4.25 met as Sebastian restated it (EXP_001 0.983 reported, 0.99 kept for the rest); S4.24 EXP_002 `sec_kwh_per_kg` partial, not complete; S4.9 fixture count 269 not 268 (spec text and contract example not edited, Next steps); `plausibility.limit` null workaround; `count_series` ignores the policy version. Judge `/flow:verify M4`, commit and push `m4-metrics`, CI, merge approval.
State left behind: dev `dac-influxdb` and `dac-postgres` running; dev Postgres has 0003 applied; dev `dac_raw` holds `metrics_series`; `.env` dev; `.flow-tmp/t4m/` scratch.

### M5

Branch `m5-comparison` cut from `master` (`262fb1f`), uncommitted. Mode standard, tasks T1-T6 by agents (decision 1). Dev `dac-influxdb` and `dac-postgres` are up; `.env` is dev.

**W1 T2 done.** `pipeline/compare_store.py` (`CompareGateway(MetricsGateway)`: `raw_series`, `state_events`, `metric_series`, `has_metrics_rows`, plus `require_database()`; `experiment_rows`, `experiment_metric_rows`; re-exports `DatabaseMissing`, `pg_check`, `pg_connect`), `tests/integration/test_compare_store.py` (16). 16 passed, 0 skipped on the dev stack; ruff clean; no database or schema leaked. Choices: a plain read on a missing database raises `QueryFailed`, so T4 calls `require_database()` first; an empty or inverted window returns `[]` without a query (Core refuses `start == end`); reads on never-written tables or columns return `[]`; `state_events` and `raw_series` filter on signal only (like `accepted_series`); `metric_series` also drops NULL values; S5.11 uses the metrics fixture's experiments file plus a second experiment built in the test.

**W1 T3 done.** `tests/fixtures/compare/` (`make_fixture.py`, `readings.csv` 33,315 rows, `experiments.json`, `readings.sha256`, `README.md`). Generator run twice: byte-identical, sha256 `c537793f...e7711`. S5.12 run on a throwaway database: 33,314 accepted, 1 excluded (EXP_001 voltage +300 s, `flag_bad`), 0 gap, 0 flatline, 0 spike, no typical-range notes; first construction passed. Plain OLS on the CSV (hydrolyzer steady, 839 / 840 / 840 instants): flow -0.1997, pressure 3.005, temperature -0.0999, current 0.297; VIFs 1.03 to 1.10. Steady KPIs (coverage 838/840, complete): voltage_mean_v 80.7271 / 95.7270 / 80.7270 V, mean_power_kw 12.1090 / 19.1454 / 12.1091 kW; EXP_002 - EXP_001 = 14.9999 V. Comparability as planned (S5.16). Database list back to the original.
- **Absorber fits are not testable on this fixture by construction.** The spec's "+ at even reading index" noise makes current and air_flow constant at the 0.5 Hz pressure_drop instants, so the absorber normal matrix is singular (steady and whole run); absorber evidence is `not_testable` and the per-experiment pressure-drop fit is degenerate. S5.14 only needs the entries to exist. T4 should expect it; the absorber model's testable path is covered by T1's unit tests, not the fixture. Not changed (a plan matter). Candidate follow-up: a note in the M5 report.
- Other choices: pressure_drop uses the nominal air flow in 15 x (air_flow/1200)^2 (15 / 15 / 60); triangle waves start at 0 and rise first; decimals written current 3, flow 3, pressure 4, temperature 3, voltage 6.
- Process note: `lane.js claim` must be run bare (no `cd ... &&` prefix) or the hook does not record it.

**W1 T1 done.** `pipeline/compare.py` (pure, stdlib; imports `as_of`, `covered_intervals`, `overlap`, `integrate_over`, `status_for`, `POLICY` from `pipeline.metrics`), `tests/unit/test_compare.py` (105). Fingerprint `a0274e7e...3db36` pinned; `POLICY` keys equal the schema's `parameters` keys. Extra public names: `lag_search`, `recorded_differences`, `percentile`, `median`, `pearson`, `simple_fit`, `Rows` (t, window_index, window_start, voltage, columns), `Phase`, `KpiResult`, `STEADY_STATE`. Interpretations: the singular test is on the centred cross-product matrix (not scale-free); not testable also covers flat voltage; pooled uses only individually testable experiments and plain_corr over all pooled rows; blocks keyed (window_index, k) and empty blocks left out of the draw; a resample with a non-positive KPI denominator gives samples `[]` and a null interval; `measured_conditions` uses readings inside windows only; instant-mean KPIs take the plain mean of all instants in the windows with coverage from covered intervals; `split_check` skips None, before is t < boundary; for the pressure-drop lag the "residual" is the pressure drop itself.
**W1 check:** `lane.js check --wave W1` ok (10 files, all allowed); `pytest tests/unit` 567 passed; ruff check and format clean (115 files); `contract.js --static` 5 PASS. Integration (T2) 16 passed on the dev stack when T2 ran.

**W2 T4 done.** `pipeline/compare_run.py`, `scripts/compare.py`, `tests/unit/test_compare_exit_codes.py` (32), `tests/e2e/test_compare_cli.py` (34). Fixture run: 16 voltage_models (hydrolyzer fits testable: steady instants 839 / 840 / 840 / pooled 2519, flow about -0.19974, pressure about 3.0051, all 1000 resamples used, 0 singular; absorber fits all `testable: false` as T3 predicted), 8 evidence statuses (hydrolyzer flow supported negative, pressure supported positive, whole run and steady; absorber `not_testable`), 15 comparisons as planted; EXP_002 - EXP_001 voltage_mean_v 14.9999 [14.738, 15.264]. About 2.3 s and 110 queries per run. Refusal reasons: `database_missing`, `no_cleaned_readings`, `no_metrics_rows`, `experiments_unreadable`, `postgres_not_configured`, `postgres_unreachable`, `postgres_not_migrated`, `experiment_missing_in_postgres`, `window_mismatch`, `experiment_metrics_missing` (any of the 13 names missing), `influx_*`.
- **Routine choice (mine, recorded for ADR-0017):** `steady_kpis` gets `voltage`, `power_computed`, `capture_rate` and `capture_efficiency` restricted to instants inside the steady windows. Reading decision 13 literally (covered intervals of the whole series, then clipped) bridges the last second of each window with the first load-step reading, giving coverage 840/840 and `mean_power_kw` 12.1106 kW; the restricted reading gives 838/840 and 12.1090 kW, which is what the T3 hand computation and S5.15 pin, and keeps transient readings out of the steady KPIs. Effect: 1 s per window edge (about 0.2 %). T5's independent recompute must use the same restriction.
**W2 check:** `lane.js check --wave W2` ok (4 files, all allowed); full `python -m pytest -q -rs` on the dev stack 794 passed, 0 skipped; ruff clean (119 files); `contract.js --static` 5 PASS; raw SHA-256 matches; database list back to `_internal, dac_pinned, dac_raw, dac_rollup`.

**W3 T5 done.** `reports/comparison_summary.json` and `reports/comparison_report.md` written by `python -m scripts.compare --report-dir reports` on dev: exit 0, 6 experiments, 28 voltage_models (all testable, 0 singular of 1000 each), 8 evidence rows, 15 comparisons, 6 pressure-drop entries, airflow_check for EXP_004; about 53 s and 219 queries. Independent recompute (`.flow-tmp/t5m5/recompute.py`, no pipeline imports): 0 differences at 9 digits, EXP_001 (347 values) and all six (3,497 values); 4 near-misses on `r2_drop` around 1e-8 (difference of two R squared near 0.99, 9th digit noise). One ambiguity resolved by reading the code's way: a covered pair or segment is split at the 120 s block boundaries (affects only capture rate and SEC intervals). S5.23 counts equal a plain COUNT (3600/3600 air_flow and fan_speed, 1800/1800 the other four). Stores unchanged; rerun equal except timing; fresh private stack (`m5t5`) equal, report byte-equal; `.env` restored, dev containers healthy; raw SHA-256 matches. I re-checked the schema, counts, `.env` and checksum myself afterwards.
- **Results (numbers, not yet findings):** all 8 evidence rows are `not_resolved`. Hydrolyzer steady: flow excludes zero in 0 of 6, pressure 0 of 6; pooled steady flow -0.00677 [-0.0328, 0.0156] V per L/min, pressure 0.200 [-0.0438, 0.455] V per bar (VIF 5.74 / 1.53, separable); pooled whole run not separable (flow VIF 18.0). Absorber: air_flow 1 and 0 of 6, pressure_drop 2 and 1 of 6. Pressure drop vs air flow: R squared at most 0.0018 within an experiment, best lags 17 to 58 s; across experiments slope 0.0381, R squared 0.999998 on two air-flow levels only (1200 and 2400). EXP_004 air flow: median 1200.1 before 09:00Z, 20.0 after (-98.3 %), while fan_speed (+0.02 %), pressure_drop (+1.5 %), co2_out (-0.85 %), capture_efficiency (+0.24 %) stay put. Comparisons: only EXP_001 vs EXP_002 is `supported` (setpoint); the other 14 are `confounded`. Coverage: EXP_002 steady voltage/power/SEC partial (0.923); EXP_004 capture and SEC partial (0.475); EXP_005 (0.735); EXP_006 capture, efficiency and SEC (0.266).
- **EXP_001 residual block correlation** (lag-1, 120 s blocks, hydrolyzer steady): EXP_001 -0.15 (small, independence holds); EXP_002 -0.04, EXP_003 0.12, EXP_004 -0.03, EXP_005 **0.87**, EXP_006 0.12. EXP_005's block-bootstrap intervals are probably too narrow (T6: say so in the report and findings).
**W3 check:** independently re-verified by me (schema valid, counts, `git status`, `.env` equals backup, checksum, containers).

**W4 T6 done.** `reports/findings.md` (draft, status line exact; five findings: hydrolyzer flow and pressure, absorber air flow and pressure drop, the EXP_004 air-flow check, pressure drop vs air flow, comparability and coverage; plus the section on comparisons the data does not support), `reports/M5.md`, `docs/comparison.md`, `docs/decisions/ADR-0017-comparison-and-findings.md`, `docs/decisions/README.md`, `docs/ASSUMPTIONS.md` (A-07 status, A-09, U-05 note), `docs/ROADMAP.md`, `.github/workflows/ci.yml` (comparison contract step), `tests/unit/test_findings_doc.py` (42, 17 mutation tests), `tests/unit/test_comparison_doc.py` (38, 13 mutation tests). Every number in the findings carries a ref comment generated from the summary. The residual autocorrelation (EXP_005 0.87) is cited from this log, outside the ref test (Next steps). I fixed one garbled sentence in the absorber finding by hand.
**W4 check:** `lane.js check --wave W4` ok (10 files, all allowed).

### M5 final (revision `262fb1f` + uncommitted, branch `m5-comparison`)

Status: implemented and verified by me; judge not run, CI not run. Mode standard, tasks T1-T6 by agents.

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean (126 files) |
| `python -m pytest -q -rs` (whole suite, dev stack) | 874 passed, 0 skipped |
| `node contract.js --static` | 5 PASS |
| `python -m scripts.compare --report-dir reports` on real data | exit 0, 6 experiments, 28 fits (all testable), 219 queries, about 53 s |
| independent recompute (no pipeline imports) vs summary | 0 differences at 9 digits (EXP_001: 347 values; all six: 3,497), 4 r2_drop rounding near-misses |
| rerun; fresh private stack (ingest, clean, metrics, compare) | summary equal except timing, report byte-equal |
| stores unchanged by the command | row counts and database list equal before and after |
| SHA-256 of raw CSV | OK |
| GitHub Actions, judge | not run |

Result to read first: all 8 evidence rows are `not_resolved`; the flow and pressure answer for this run is "no effect shown that the data can separate from noise", which is not evidence of no effect. The findings stay a draft; the merge to `master` waits for Sebastian's approval of them. Remaining gaps are in `reports/M5.md` and Spec Next steps.
State left behind: dev `dac-influxdb` and `dac-postgres` running, `.env` dev, `.flow-tmp/t5m5/` scratch (gitignored).

### M6 (branch `m6-dashboard`, cut from `c4b599d`; first commit `3e61ff6` carries the plan record, verify env and dashboard check contract)

Docker came up after the first attempt (earlier note: execute stopped before W1 because Docker Desktop was off). Tasks T1-T6 by agents (decision 3).

**W1 T1 done.** Spike (decision 11) passed on all four items, nothing swapped. Grafana `13.3.2` against Core 3.11.2: (a) provisioned `influx-dac` and `pg-dac` health OK, `/api/ds/query` accepts `{refId, rawSql, format: "table"}`; (b) the `WITH w(...) AS (VALUES ...)` join and `CAST(r.time AS BIGINT)` arithmetic run unchanged; (c) region annotation works with `to_timestamp_nanos(end_ns) AS timeend` (`CAST(end_ns AS TIMESTAMP)` overflows); (d) `$__timeFilter(time)` expands to RFC 3339 literals, inclusive end, also with an alias. Images: `grafana/grafana:13.3.2` (`sha256:81556409ba48b2b922e0adb69a2511337d8ba7578f11962eefa6149a2d815101`), `grafana/grafana-image-renderer:v5.12.11` (`sha256:cfa6c8f63e6d626f90208f2880f15bd5facc279daec1b9bb642af07aa850d95e`). For ADR-0018: 13.x chosen over the untested 12.4.16; Grafana 13 refuses the default renderer token (`GF_RENDERING_RENDERER_TOKEN` and renderer `AUTH_TOKEN` from `GRAFANA_RENDERER_TOKEN`); Postgres datasource type `grafana-postgresql-datasource`; private Grafana base + 2 (18102), `down` runs with `--profile render`; dashboards mount nested in the `grafana-data` volume path; lint extras (no use before declaration, refId unique, duplicate variable names, dashboard uids unique across files); `GRAFANA_*` process variables override `.env`; CI starts Grafana with `docker run --network host`, tag read from docker-compose.yml (CI steps not run on GitHub).
**W1 T2 done.** `migrations/0004_comparison.sql` (pinned DDL), `pipeline/comparison_loader.py`, `scripts/load_comparison.py`; 20 unit, 19 integration (S6.8-S6.10), exit codes 0/2/3/4. The loader also refuses `a >= b` and duplicate keys with exit 2.
**Lead edits (tests lane, not weakening):** `tests/integration/test_compare_store.py:482` and `test_metrics_store.py:458,633` expected the migration list `0001-0003`; now `0001-0004`. `pyproject.toml` (T1) got `--import-mode=importlib` and `pythonpath` because two `test_comparison_loader.py` files share a basename.
**W1 check:** `lane.js check --wave W1` lists only my two test-file edits; ruff clean (137 files); `pytest tests/unit tests/integration` (without the grafana integration file) 855 passed; `contract.js --static` 6 PASS; dev Postgres has no 0004 (tests used throwaway schemas). Private stack up for W2 (`.env` points at it; dev copy in `.env.pre-verify`).

**W2 T4 done.** `grafana/dashboards/experiment.json` (uid `dac-experiment`, schemaVersion 41), `tests/e2e/test_dashboard_experiment.py` (10), `tests/e2e/test_dashboard_quality.py` (8); S6.16-S6.20. Choices for ADR-0018: every InfluxDB query uses the half-open window `time >= span_from AND time < span_to` plus `$__timeFilter`; D3 one target with `accepted` and `excluded (raw value)` columns (red points); D2 one target with `process_state` and `valve_state` columns; D10 newest 1,000 excluded rows ascending; D1 jump link as field link and dashboard link. **Deviation from decision 12:** Grafana 13 has no per-event annotation colour, so the annotation "Gaps and stuck stretches" is one orange entry limited to D3 (kind in text and tags); gap grey and flatline orange are applied in D9's `kind` column only. **Finding:** a database with no gap or flatline at all has no `quality_intervals` table (Core creates a table with its first row), so D9 and the annotation return an error there instead of empty; the compare fixture is such a case, and the test writes one row for a non-existent experiment `EXP_NONE` so D9 is empty rather than failing. Real data has 34 intervals and is unaffected (Next steps: have `scripts.clean` write nothing special, but D9 on a zero-interval database shows an error).
**W2 T3 done.** `grafana/dashboards/compare.json` (uid `dac-compare`), `tests/e2e/test_dashboard_compare.py` (22); S6.11-S6.15. Choices for ADR-0018: XY overlay uses `options.mapping: "auto"` with `series: []` (the `seriesMapping`/`dims` keys make Grafana 13 migrate to one manual series and only the first experiment draws; found in a rendered screenshot, pinned by a test); legend through a `${__field.labels.experiment_id}` display-name override; C9 is a bar chart over a `groupingToMatrix` transform; C8 bad and uncertain fractions use mirrored thresholds (green below 0.05, amber below 0.5, red above), which is my reading since decision 12 names only completeness and valid; C8 completeness is sum present over sum expected of the polled signals; `windows` uses `(extract(epoch FROM t) * 1000000)::bigint * 1000`. The checker returns counts, so tests resolve variables and run the SQL through `GrafanaClient.query`. Fixture caveat: EXP_001 and EXP_003 have identical hydrolyzer signals, so their voltage lines overlap in C6.
**Process notes:** the shared database lock directory was removed by an agent that did not hold it once or twice; harmless (no leftovers).
**W2 check:** `lane.js check --wave W2` ok (5 files); full `python -m pytest -q -rs` on the private stack 1030 passed, 0 skipped; ruff clean (140 files); `contract.js --static` 6 PASS; leftovers none (databases `_internal, dac_pinned, dac_raw, dac_rollup`; datasources the two provisioned). Private stack brought down afterwards; `.env` back to dev.
**W3 T5 done** (on dev, then a fresh private stack). Dev data matched the cleaning summary (519,906 `readings_processed` rows, 34 `quality_intervals`); 0004 applied on dev Postgres; `load_comparison` 30/15/75, three runs, tables identical. Dev Grafana 13.3.2 up. `check_dashboards --sweep signal --allow-empty "Gaps and stuck stretches"`: exit 0, runs 299, panel_targets 3105, with_rows 3082, empty 0, empty_allowed 23 (all D9 of EXP_005, plain COUNT 0), errors 0, annotation_errors 0; committed as `reports/dashboard_check.json`. Span run (`--time-range span`, sweep): 1794 entries compared with the window run, 0 differences (U-05). S6.22 recompute with no pipeline imports: 160,648 rows, 0 differences. S6.23: EXP_004 air_flow excluded 3600 = plain COUNT 3600, all `flatline`, all inside the one flatline region 09:00:00Z-09:59:59Z. Fresh private stack (run id t5): ingest 520005, clean, metrics, compare, load_comparison, checker: equal to the committed file except timing; Grafana 13.3.2 in both. Screenshots: four PNGs, 1600 px wide; `screenshot_dashboards` exits 2 with nothing saved when the renderer is stopped. Raw SHA-256 OK; `.env` equals dev (`.env.pre-m6` plus four GRAFANA_* lines).
**What the screenshots show (I looked at them):** C6 draws all six runs on one axis; EXP_005 voltage drifts up from 80 V to 97 V while the others sit at 100-110 V; the EXP_004 air-flow view shows the orange band 09:00-10:00 and the red excluded points along the bottom edge. The red points sit at about 20 (raw value), the accepted line at about 1200: that is the data (the M5 check found median air flow 20.0 after 09:00Z), not a unit mix-up as T5 guessed; zooming the picker separates them. Compare screenshot: C1 clipped to 4 of 6 rows at h=6; **I raised C1 to h=8 and shifted the panels below by 2** in `compare.json` (layout only, no query change) and re-rendered the PNGs. Tables clip on a static render (no scroll), which the click-through covers.
**W4 T6 done.** `docs/decisions/ADR-0018-grafana-dashboards.md`, ADR-0009 addendum, `docs/decisions/README.md`, `docs/dashboard.md`, `docs/ASSUMPTIONS.md` (U-05 closed for this data, plant-scale caveat), `docs/ROADMAP.md`, `docs/schema.md`, `README.md`, `reports/M6.md`, `tests/unit/test_dashboard_doc.py` (23, 16 mutation); S6.26. T6 took the 1,794 / 160,648 / screenshot facts from this log without re-checking; I checked the C1 layout change and the PNGs myself.

### M6 final (revision `3e61ff6` + uncommitted, branch `m6-dashboard`)

Status: implemented and verified by me; judge not run, CI not run. Mode standard, tasks T1-T6 by agents.

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean (145 files) |
| `python -m pytest -q -rs` (whole suite, dev stack with Grafana 13.3.2) | 1053 passed, 0 skipped |
| `node contract.js --static` | 6 PASS |
| `python -m scripts.check_dashboards --sweep signal --allow-empty "Gaps and stuck stretches" --report-dir reports` on real data | exit 0; runs 299, panel_targets 3105, with_rows 3082, empty 0, empty_allowed 23 (D9 of EXP_005), errors 0 |
| span run vs window run | 1794 entries, 0 differences |
| independent recompute of the overlay (no pipeline imports) | 160,648 rows, 0 differences |
| fresh private stack (ingest to checker) | `dashboard_check.json` equal to the committed one except timing |
| four screenshots | saved, 1600 px wide, looked at by me |
| SHA-256 of raw CSV | OK |
| GitHub Actions (including the new Grafana CI steps), judge | not run |

Remaining gaps (all in `reports/M6.md`): single orange annotation instead of grey gaps and orange flatlines (Grafana 13 has no per-event colour); a database with no intervals at all shows an error on D9; static renders clip long tables; click-through by hand is Sebastian's. Judge `/flow:verify M6`, then commit, push `m6-dashboard`, CI, merge approval.
State left behind: dev `dac-influxdb`, `dac-postgres`, `dac-grafana` (:3000) and `dac-renderer` running; dev Postgres has 0004 and the comparison tables loaded; `.env` is dev plus four GRAFANA_* lines; `.flow-tmp/` scratch (gitignored); `.env.pre-m6` removed.
