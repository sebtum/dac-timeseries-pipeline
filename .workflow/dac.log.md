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
