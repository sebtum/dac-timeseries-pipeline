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

### Goal
Build everything in `task/TASK.md` A–J, one roadmap milestone at a time. Current milestone, M2:
copy the raw CSV into InfluxDB without losing or quietly changing anything, and prove it with counts.
- Scope (M2): private test stack, ingest command, rejects file, conflicts table, summary + report, CI fixture test, full real run, M2 report.
- Non-goals (M2): cleaning or judging values (M3); profiling (M2.5); cross-run duplicate detection; parallel ingest.
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

### Constraints
- Milestone ids follow `docs/ROADMAP.md`. Only `/flow:plan <id>` details a milestone.
- InfluxDB `3.11.2-core`, `influxdb3-python==0.21.0`, Python 3.14, native Windows plus Linux CI.
- Raw CSV read-only; its committed SHA-256 must match after every run.
- No ingest time, run id or file-order logic in any point (ADR-0007).
- `generator/` untouched. Core allows 5 databases; test databases must be dropped.
- Working contract in `CLAUDE.md`: major decisions need Sebastian's approval; one report per milestone.

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

### Assumptions and open questions
- Partial accept on 3.11.2 behaves as documented — a real test in M2 decides (Claude).
- `influxdb3-python` writes synchronously when told to — confirmed in M2 (Claude).
- The flow verify harness can run `python` here — confirmed at M2's first verify (Claude).
- Later scenario ids for M2.5 need a numeric form (for example `S25.n`), since the record parser expects `S<digits>.<digits>` — settled at `/flow:plan M2.5`.

### Next steps (not in this budget)
- Cross-run duplicate detection — out of scope per ADR-0007; belongs with deliverable H — medium.
- Parallel ingest by experiment — not needed at 520k rows — small.
- Multi-pass merge in the external sort — only needed past the OS open-file limit — small.
- The rollup driver (`pipeline/rollup_run.py`) raises `TypeError` on a stored point with no value, because `compute_rollup` takes `min()` and `sum()` over a `None`. M2 stores an empty value as exactly such a point (decision 6). The real file has 0 of them, so nothing fails today; M3 must decide whether the rollup skips them or counts them as missing — small, found 2026-11-23 while writing the M2 report.

### Checks
Services: `.workflow/verify-env.json` (private InfluxDB + Postgres; `up` writes the worktree
`.env` with `INFLUX_HOST=http://localhost:$FLOW_PORT_BASE`, Postgres on `$FLOW_PORT_BASE+1`).

| Kind | Command | Directory | Prerequisites | Source |
|---|---|---|---|---|
| lint | `ruff check .` | repo root | `pip install -r requirements.txt` | ci.yml |
| lint | `ruff format --check .` | repo root | same | ci.yml |
| unit | `python -m pytest tests/unit -v` | repo root | none | pyproject |
| integration | `python -m pytest tests/integration -v` | repo root | stack up; any skip counts as a failure | ci.yml |
| e2e | `python -m pytest tests/e2e -v` | repo root | stack up; any skip counts as a failure | new in M2 |
| e2e | `python -m scripts.ingest` | repo root | stack up; real CSV copied in | new in M2 |
| contract | `check-jsonschema --schemafile contracts/ingest_summary.schema.json contracts/examples/ingest_summary.example.json` | repo root | `check-jsonschema` added to requirements.txt in M2 (not installed today) | new in M2 |

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
- Not yet detailed. Scope: `docs/ROADMAP.md` § M2.5. Next: `/flow:plan M2.5`.

#### M3: Quality and cleaning pipeline (C, D)
- Not yet detailed. Scope: `docs/ROADMAP.md` § M3.

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
