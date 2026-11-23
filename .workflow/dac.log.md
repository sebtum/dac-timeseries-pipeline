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
