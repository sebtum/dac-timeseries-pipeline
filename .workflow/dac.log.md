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
