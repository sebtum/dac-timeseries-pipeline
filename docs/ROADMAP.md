# Roadmap

Single source of truth for where the work stands. Update the phase column as each milestone
moves; don't rely on memory or chat history.

**Scope:** untimed, build everything in `task/TASK.md` A–J.

**Guardrail on this document:** it names *decision points, never their resolutions*. Every
question below is derivable from `task/TASK.md` or `task/DATA_DICTIONARY.md` alone. Answers
live in `decisions/`, written only after Sebastian has made the call.

---

## Milestone board

| M | Name | Deliverables | Phase | ADRs |
|---|------|--------------|-------|------|
| M0 | Environment & reconnaissance | (setup), CI | Done | [0008](decisions/ADR-0008-local-runtime-docker-compose.md), [0009](decisions/ADR-0009-provisioning-as-code.md), [0010](decisions/ADR-0010-profile-post-ingest-in-database.md) |
| M1 | Time-series data model | A | Done | [0006](decisions/ADR-0006-timeseries-data-model.md), [0011](decisions/ADR-0011-retention-tiering-rollup.md), [0012](decisions/ADR-0012-postgres-migrations-metadata-loader.md) |
| M2 | Ingestion | B | Verify | [0007](decisions/ADR-0007-duplicate-resolution-idempotency.md), [0013](decisions/ADR-0013-ingestion.md) |
| M2.5 | Post-ingest profiling | — | Verify | [0010](decisions/ADR-0010-profile-post-ingest-in-database.md), [0014](decisions/ADR-0014-post-ingest-profiling.md) |
| M3 | Quality & cleaning pipeline | C, D | Verify | [0015](decisions/ADR-0015-cleaning-and-quality-pipeline.md) |
| M4 | Derived metrics | E | Verify (built 2026-11-24, judge not run) | [0016](decisions/ADR-0016-derived-metrics.md) |
| M5 | Comparison & findings | F | Verify (built 2026-11-24, judge not run) | [0017](decisions/ADR-0017-comparison-and-findings.md) |
| M6 | Grafana dashboard | G | Not started | — |
| M7 | Edge, cloud, presentation | H, I, J | Not started | — |
| — | Retrospective (terminal) | — | Locked until session declared over | — |

Phase values: `Not started` → `Discuss` → `Plan` → `Execute` → `Verify` → `Done`.

## Deliverable coverage

Every letter in the brief must appear here with a live state. Nothing gets dropped silently.

| # | Deliverable | Milestone | State |
|---|-------------|-----------|-------|
| A | Time-series data model | M1 | **Done** (2026-09-22). Schema settled (ADR-0006); retention/tiering/rollup settled (ADR-0011); T1–T12 all run — V1–V10 all pass, evidence in the M1 verify-phase results below. Pushed to `origin/m1-data-model`; CI green on the branch, both jobs — [run 35779389919](https://github.com/sebtum/dac-timeseries-pipeline/actions/runs/35779389919) (`lint` 14s, `integration` 1m1s, InfluxDB 3 Core + Postgres both up in Actions for the first time). Rollup's execution locus stays open (U-04), by design. **Deferred, not dropped:** the T3/T8 decision-point walkthrough owed since MISTAKES.md E-05 — Sebastian's explicit call to push this pass through rather than fold it in here; still owed before those two files' design choices are considered reviewed. |
| B | Ingestion | M2 | **Built, awaiting the judge** (2026-11-23). Real file: 520,005 rows = 519,980 saved + 15 exact copies + 10 conflict losers + 0 rejected, all 150 series balanced against a count read back from InfluxDB; second run identical; raw SHA-256 unchanged. Report: [`reports/M2.md`](../reports/M2.md). Decisions: [ADR-0013](decisions/ADR-0013-ingestion.md). |
| C | Data quality pipeline | M3 | **Built, awaiting the judge** (2026-11-23). Real data: 150 series, 519,980 readings = 514,443 accepted + 5,537 excluded, every series balanced against a count read back from InfluxDB, raw tables unchanged. Each reading keeps its raw value, processed value, flag, verdict and reason. Report: [`reports/M3.md`](../reports/M3.md). Decisions: [ADR-0015](decisions/ADR-0015-cleaning-and-quality-pipeline.md). Schema: [`schema.md`](schema.md). |
| D | Cleaning and processing | M3 | **Built, awaiting the judge** (2026-11-23). Per-signal policy table, 25 rows, checked against the code by a test: [`cleaning_policy.md`](cleaning_policy.md). All nine defect kinds covered. Real data: 29 gaps, 5 stuck-sensor runs, 4 impossible values, 4 spikes, 100 BAD and 230 UNCERTAIN readings excluded; rollup rebuilt over the verdict (16,256 buckets). Report: [`reports/M3.md`](../reports/M3.md). Decisions: [ADR-0015](decisions/ADR-0015-cleaning-and-quality-pipeline.md). |
| E | Derived metrics | M4 | **Built, awaiting the judge** (2026-11-24). Real data: 13 metrics and 4 derived series for each of the 6 experiments, each metric with a coverage and a label (complete, partial or none); the formulas were recomputed independently in plain Python with 0 differences; energy from voltage times current agrees with the logged power to within 0.67 % in every experiment. These are numbers, not findings. Report: [`reports/M4.md`](../reports/M4.md). Decisions: [ADR-0016](decisions/ADR-0016-derived-metrics.md). Formulas: [`metrics.md`](metrics.md). Schema: [`schema.md`](schema.md). |
| F | Experiment comparison | M5 | **Built, awaiting the judge** (2026-11-24). Real data: all 6 experiments put on one experiment clock, 28 voltage fits (hydrolyzer and absorber, steady and whole run, each experiment and pooled), 8 evidence rows, 15 pair comparisons, the pressure-drop check and the EXP_004 air-flow check; an independent plain-Python recompute found 0 differences. The headline answer on flow and pressure against cell voltage is **not resolved in this run**: all 8 evidence rows are `not_resolved`, which is not evidence of no effect. Only one pair (EXP_001 against EXP_002, differing in current setpoint) is a supported comparison; the other 14 are confounded. Report: [`reports/M5.md`](../reports/M5.md). Draft findings: [`reports/findings.md`](../reports/findings.md); **the findings are a draft until Sebastian approves them.** Decisions: [ADR-0017](decisions/ADR-0017-comparison-and-findings.md). Method: [`comparison.md`](comparison.md). |
| G | Grafana dashboard | M6 | Not started |
| H | Edge ingestion & resilience (design) | M7 | Not started |
| I | Cloud scaling narrative (verbal) | M7 | Not started |
| J | Presentation walkthrough (verbal) | M7 | Not started |
| — | CI/CD *(added scope, not in the brief)* | cross-cutting, from M0 | M0 increment done ([ADR-0009](decisions/ADR-0009-provisioning-as-code.md)) — lint + format check green on GitHub Actions; next increment lands at M1 |
| — | Post-ingest profiling *(added scope, not in the brief)* | cross-cutting, M2.5 | **Built, awaiting the judge** (2026-11-23). Real data: 150 series, 6 experiments, 24 relationships, 519,980 points, 188 read-only queries in about 16 s; every series and relationship recomputed independently in Python from plain pulls, 0 mismatches. Report: [`reports/M2.5.md`](../reports/M2.5.md). Decisions: [ADR-0014](decisions/ADR-0014-post-ingest-profiling.md). |

---

## The four-phase protocol

> **Changed 2026-11-23, from M2 on.** Claude now makes the calls and Sebastian verifies them in
> milestone reports. Only major decisions need his approval (defined in `CLAUDE.md`). The loop
> below now runs lighter: Discuss and Plan shrink to one decision log and the verify criteria,
> both written before the code. Execute and Verify are unchanged. Each milestone ends with a
> report in `reports/M#.md`, opened in the doc viewer. M0 and M1 were run under the full
> protocol below.

Every milestone runs the same loop.

**1. Discuss.** Claude puts the decision points on the table and supplies *facts only* — what
the data shows, how InfluxDB/Grafana actually behave, what the brief demands. No
recommendation, no leading questions, no hinting at the shape of a good answer. Sebastian
proposes. The moment he does, Claude reacts plainly: right, wrong, or partially right, and
why — naming the actual problem first, then the principle behind it, so it transfers. If he's
right, say so and add the sharper thing he's missing (edge case, tradeoff, how it gets
attacked under review). Wrong or shaky calls go into `MISTAKES.md § Corrected design calls`
immediately.

**2. Plan.** Four outputs, all written before any code exists.

- **The Discuss record** goes to `discuss/M#.md` — the decision points as tabled, the facts
  supplied, how each call moved across the round-trips, the corrections, and what was still open
  on exit. Not a transcript and not a summary of the ADRs: it is the *route* to the decision,
  which is what gets attacked in review and is not recoverable from an ADR afterwards.
- **Each settled decision becomes an ADR** in `decisions/` (options, caveats, why, consequences,
  the defense). New assumptions and unknowns are registered in `ASSUMPTIONS.md`.
- **The verify criteria for the milestone are written now** — deciding what "done" means after
  seeing the output is how you fool yourself.
- **The milestone is broken into tangible tasks with acceptance criteria**, each executable by an
  agent that has not seen the conversation. A task that only makes sense to someone who was
  present is not yet planned. Acceptance criteria are checkable statements rather than
  intentions, and they trace back to the verify criteria above instead of inventing a second
  standard.

A milestone does not enter Execute until all four exist. An open decision does not block the
milestone as a whole — it is recorded as open in `ASSUMPTIONS.md` and the tasks depending on it
are marked blocked, so the independent work can still be handed off.

**3. Execute.** Claude writes the code. The decisions are already made; mechanical
implementation is not the thing being practiced. Sebastian reviews. Anything that turns out
to need a *new* decision bounces back to Discuss rather than getting quietly decided inside
an implementation.

**4. Verify.** Run the criteria from phase 2. Record pass/fail here. A failed criterion is
either fixed or recorded as a known limitation with a reason — never silently dropped.
Milestone flips to `Done`; Claude proposes a commit (`M#: <name>`) for approval.

**Standing rule, all phases:** sample and calibrate against a targeted pull before running
any cleaning or transform logic at full scale.

---

## Cross-cutting: CI/CD

Not in the brief — deliberately added scope. Built **incrementally from M0**: a minimal
pipeline exists from the start, and each milestone adds its own check as it lands, while the
code is fresh. A milestone is not `Done` until its CI increment is green.

| M | CI increment added |
|---|--------------------|
| M0 | Pipeline skeleton: lint + format check, dependency install from a pinned manifest. |
| M1 | Schema/config validation — retention checked **behaviourally** (write past the window, assert it is filtered), not by reading the configuration back; Postgres migration runs clean and re-runs as a no-op; loader cannot revert a manual correction; downsampling job tested against a known aggregate under a stated predicate. |
| M2 | Ingest smoke test against a fixture slice using the v3 client; reconciliation assertion on row counts. |
| M3 | Unit tests for each per-signal handling rule; the "nothing silently dropped" reconciliation runs as a test. |
| M4 | Metric correctness tests, including the power cross-check against the logged `power` signal. |
| M5 | Regression test pinning the headline findings, so later pipeline changes can't silently move them. |
| M6 | Dashboard JSON lint/validation; datasource references resolve. |
| M7 | Docs build/link check only — H, I, J produce no runnable code. |

**CD** here is not deployment — there is no environment to ship to. It means the stack as
code: the compose file, Influx buckets/retention/tasks provisioned on startup, and Grafana
datasources and dashboards loaded from committed files rather than clicked into existence.
That last part has value independent of CI: a dashboard that exists only inside a container
volume can't be handed to anyone.

**Settled** ([ADR-0009](decisions/ADR-0009-provisioning-as-code.md)): CI runs in GitHub Actions;
the M0 increment lands **before** any profiling or ingest code, so that code is written under lint
discipline from line one and any committed profile number is reproducible against a pinned
dependency set. It is unblocked by U-02 because lint, format and dependency install never read the
dataset — *what CI runs data tests against* becomes live at M2, not now.

---

## M0 — Environment & reconnaissance

Setup, plus the data discovery every later decision depends on.

**Decide**
- ~~Which checks to run against the raw data.~~ *(settled: `MISTAKES.md` C-03 — his list plus the
  two categories it missed.)* **Where** each check runs is settled separately:
  [ADR-0010](decisions/ADR-0010-profile-post-ingest-in-database.md).
- ~~How Influx, Postgres and Grafana get run locally.~~ *(settled:
  [ADR-0008](decisions/ADR-0008-local-runtime-docker-compose.md) — Docker Compose, pinned tags,
  services added at the milestone that needs them. Version and query language were already settled
  by [ADR-0004](decisions/ADR-0004-influxdb3-core-sql.md).)*
- ~~Where CI runs, and what it runs against.~~ *(settled:
  [ADR-0009](decisions/ADR-0009-provisioning-as-code.md) — GitHub Actions, M0 increment first;
  U-02 narrowed to M2.)*
- ~~Which parts of the stack are provisioned as code, and from when.~~ *(settled: ADR-0009 — all
  of it, added per milestone, with three exceptions: secrets, Grafana dashboards, migrations.)*

**Settled** — U-15 (how the pre-ingest census is packaged) and U-16 (where post-ingest SQL
profiling sits on this board); see `ASSUMPTIONS.md`. M0's Execute below covers only the
pre-ingest half; the post-ingest half now has its own milestone, M2.5.

**Correction mechanism.** Sebastian names the checks. Once his list is exhausted, Claude
names the *categories* he didn't check — the brief itself names gaps, sensor noise, quality
flags and timing quirks; deliverable D adds duplicates, out-of-order samples, outliers, stuck
sensors and differing sample rates. What those checks *find* is Sebastian's to interpret, not
Claude's to pre-empt.

**Execute**
- **CI increment first** (ADR-0009): pinned `requirements.txt`, ruff config, Actions workflow
  running install + lint + format check. No data-dependent step; the comment in the workflow points
  at U-02.
- **The pre-ingest pass** — and *only* the pre-ingest pass. Per
  [ADR-0010](decisions/ADR-0010-profile-post-ingest-in-database.md), it measures what the write to
  InfluxDB destroys or what ingest needs as input, nothing else:
  - **Duplicate census** — a dependency rather than one check among many. Exact vs conflicting
    same-timestamp collisions per experiment and signal, under *every* candidate definition of
    "same" rather than a chosen one; whether conflicting pairs differ in `quality`; whether the two
    categorical signals collide at all; verbatim sample pairs. U-07, U-08 and U-11 are blocked on
    these numbers, and last-write-wins deletes the evidence the moment ingest runs.
  - Out-of-order arrivals (file order, erased by time-sorted storage).
  - Timestamp string-format variants per source — the U-01 evidence, erased by parsing to instants.
  - Row counts per experiment and signal, plus SHA-256 — the left side of ADR-0007's reconciliation
    identity.
  - Empty / non-parseable values and which signals are non-numeric, confirming the declared
    categorical list ADR-0006:117 requires.
- *Not here:* no Docker, no containers. Nothing needs a running service until M1 (ADR-0008), and
  the rest of the profiling runs post-ingest, at M2.5 (ADR-0010).

**Verify** — all pass.
- CI green on the branch ([run 33302720981](https://github.com/sebtum/dac-timeseries-pipeline/actions/runs/33302720981),
  `lint` job, 13s); `pip install -r requirements.txt` succeeds from clean; `generator/` untouched
  (`git diff --stat -- generator/` empty — excluded from ruff rather than reformatted, since
  reformatting would violate this criterion).
- Every pre-ingest measurement produces a number, saved to
  [`reports/pre_ingest_census.md`](../reports/pre_ingest_census.md).
- U-07, U-08, U-11 each have numbers behind them from the census: 25 collision groups total: 15
  agree under all three candidate "same" definitions (raw string / float-exact / float-tolerant —
  U-08 barely matters on this data, they never disagree with each other), 0 groups differ in
  `quality` (U-07: a quality-preference win-rule has no signal to act on here), 0 groups on the
  declared categorical signals (U-11: `readings_conflicts` doesn't need string columns unless a
  future run's data differs). U-07/U-08/U-11 themselves stay `open` in `ASSUMPTIONS.md` — this
  satisfies "evidence exists to decide at M2," not the M2 decision itself.
- `data/raw/dac_raw_timeseries.sha256` still verifies: computed checksum equals committed, pass is
  read-only (script only opens the CSV for reading).
- **No verdict labels**: `grep -inE "stuck|suspicious|anomal|outlier|invalid|corrupt|error|wrong|fail|noise"
  reports/pre_ingest_census.md` returns nothing.
- Not in the original criteria, surfaced during Execute: the collision-detection module
  (`pipeline/collisions.py`) had to be corrected mid-session from an in-memory sort to a genuine
  bounded-memory external merge sort, since the former contradicted ADR-0007's O(1) framing and
  the U-06 memory-scaling defense ADR-0003 already flags as incomplete. See MISTAKES.md E-03.
  Verified deterministic across chunk sizes (50000 vs 20000 → byte-identical report modulo the
  chunk-size line in the header).

## M1 — Time-series data model (A)

Discuss record: [`discuss/M1.md`](discuss/M1.md). Task breakdown: [`plans/M1.md`](plans/M1.md).

**Plan-phase status:** all four Plan outputs exist — Discuss record, ADRs, the verify criteria
below, and the task breakdown in [`plans/M1.md`](plans/M1.md) (T1–T12, four waves, acceptance
criteria tracing to the criteria below). Milestone entered `Execute` on 2026-08-31.

Three calls made while writing the breakdown, recorded there rather than in an ADR because none
of them changes an architecture decision: **U-04 is neutralised, not resolved** — the rollup
splits into a pure aggregation function and a thin driver, so the execution locus becomes a
wrapper question deferred to M3 and no M1 task is blocked; **the M1 CI increment runs both
services in GitHub Actions**, since ADR-0009's "comes up from a clean checkout" claim is otherwise
as untested as the configuration ADR-0008 refused to stub; and **local raw retention is 1 year**
against the 9-month plant policy, which is the local value ADR-0011 already required to be
committed with its reason (all six experiments clear it — `EXP_004`, the earliest, would not reach
the boundary until 2027-03-02, where 9 months locally would silently expire it around 2026-12-02).

**Execute-phase status (2026-09-22):** T1–T10 are built (Waves 0–3); this task, T11, is
transcribing their handoffs into these tracking files. T12 (Wave 4 — the verify pass) has not
run. Nothing from M1 has been pushed to `origin/m1-data-model` yet (branch is 4 commits ahead:
T6, T7, T9, T10), so T10's CI integration job has **not** actually executed anywhere — it exists
and was reasoned through against T1/T4/T5/T6/T7/T9's already-live-verified command sequences
(per its own handoff), but "green on the branch, with the run URL" is a T12 criterion, not yet
satisfied. T2/T3/T8 (Wave 1) were originally built by parallel subagents dispatched without being
asked (MISTAKES.md E-05); T2's four decisions were walked through with Sebastian afterward and
both agreed fixes are applied on disk (bootstrap idempotency now verifies the token rather than
trusting a 409; `.env.example`'s local rollup retention raised to 5y so it outlives raw, and its
plant-policy ratio arithmetic corrected — MISTAKES.md E-07). **T3 and T8 have not yet had that
same walkthrough** — flagging one live discrepancy found while writing this: `docs/schema.md`'s
retention table (§3) still lists the rollup tier's local value as "1 year (365d)", which predates
the T2 fix above and is now stale against `.env.example`'s actual 5y. Left uncorrected here since
`docs/schema.md` is T3's file and T3 hasn't had its decision-point review yet — worth raising in
that walkthrough rather than silently patched.

**Decide**
- ~~Measurement / tag / field layout; how experiment, source and sensor identity are
  represented.~~ *(settled: [ADR-0006](decisions/ADR-0006-timeseries-data-model.md))*
- ~~Where raw values live unchanged.~~ *(settled: ADR-0006)*
- ~~Tag cardinality budget.~~ *(settled: ADR-0006 — 150 series, measured not estimated)*
- Where processed values, pipeline quality verdicts and exclusion reasons live — a second axis,
  independent of the numeric/state split (U-09, U-10). Deferred to M3.
- ~~Retention, downsampling, tiering — what stays full-resolution, what rolls up, when.~~
  *(settled: [ADR-0011](decisions/ADR-0011-retention-tiering-rollup.md) — three databases, since
  Core fixes retention per-database at creation: raw 9 months, 1-minute rollups 1 year, pinned
  intervals unbounded, then Parquet in object storage. Numbers are defaults standing in for a
  stakeholder conversation (A-03) and are parameters of the init script, not constants in it.)*
- ~~How the Postgres schema arrives and how `experiments.json` is loaded.~~ *(settled:
  [ADR-0012](decisions/ADR-0012-postgres-migrations-metadata-loader.md) — versioned SQL + small
  Python runner; loader with per-field provenance so a re-run cannot revert a correction. Resolves
  U-14, and answers ADR-0005's "which metadata fields become Influx tags" with **none**.)*
- **Still open:** where the rollup executes (U-04). The plugin preference conflicts with the
  decision to aggregate over M3's verdict; see the U-04 entry in `ASSUMPTIONS.md`. **No longer
  blocks M1** — [`plans/M1.md`](plans/M1.md) splits the rollup into a pure aggregation function
  (T8) and a thin driver (T9), leaving only *what calls the driver* open, at M3.

**Execute** — broken into T1–T12 in [`plans/M1.md`](plans/M1.md); the summary below is the scope
that breakdown covers.
- **Verify U-13 first**, before the compose file: start the pinned image and observe the actual
  first-boot admin-token behaviour rather than trusting ADR-0008's assertion.
- Compose file, then the three databases and their retention periods via an idempotent init
  script (no declarative config exists in Core — CLI or HTTP only).
- **Build the downsampling mechanism.** InfluxDB 3 Core has no task engine, so this is code —
  a Processing Engine plugin or an external job (U-04). Not configuration
  ([ADR-0004](decisions/ADR-0004-influxdb3-core-sql.md)).
- Postgres migration runner, versioned schema, and the `experiments.json` loader
  ([ADR-0012](decisions/ADR-0012-postgres-migrations-metadata-loader.md)). The runner needs
  deterministic ordering, a Postgres advisory lock, and a per-migration checksum.
- A compact schema reference (`docs/schema.md`): tables, tags, fields, databases, retention.

**Verify**
- Cardinality estimated from the *actual* dataset, not guessed.
- "Raw preserved unchanged" is demonstrable by query, not asserted.
- Downsampling actually runs against a **stated predicate** and produces a rolled-up series that
  matches a hand-computed aggregate. The predicate at M1 is a placeholder (`quality = 'GOOD'`);
  M3 replaces it with the pipeline verdict and the rollup is rebuilt. Machinery is verified here,
  policy at M3 — the criterion is not satisfiable any other way, since the verdict does not exist
  until M3 ([ADR-0011](decisions/ADR-0011-retention-tiering-rollup.md)).
- **The retention window is checked against the data's own timestamp span**, not merely declared.
  The experiments run 2026-03-02 … 2026-06-15; any configured window that excludes one of them is
  a failure, and it fails *silently* because Core filters expired points at query time
  (MISTAKES.md C-06).
- **Retention is proven behaviourally, not by configuration.** Create a throwaway database with a
  1-hour retention period, write one point at `now - 2h` and one at `now - 5m`, query both back,
  assert the first is absent and the second present, drop the database. Deliberately behavioural:
  `influxdb3 show databases` and `GET /api/v3/configure/database` reported no retention period on
  Core 3.7.0 ([influxdb#27082](https://github.com/influxdata/influxdb/issues/27082)), so asserting
  on the configuration could silently assert nothing. This also satisfies ADR-0008/0009's rule
  that unexercised configuration is untested configuration, without putting the demo dataset near
  an expiry boundary.
- The retention/downsampling story survives the "months of 1 Hz electrochemical data"
  question with arithmetic behind it — 1,059,840 points/day ≈ 387 M points/plant-year, and the
  60:1 rollup ratio.
- **Rollup lag below raw retention** is recorded as an operational invariant: if the rollup job
  stalls, buckets cross the expiry boundary carrying a stale or missing aggregate and there is no
  recovery. Not monitored at M1, but stated here and carried into deliverable H.
- Metadata queryable from Postgres; the null fields in `EXP_003`, `EXP_005` and `EXP_006`
  survive the load as nulls rather than being silently defaulted.
- **The loader cannot revert a correction.** Set a value manually, re-run the loader, assert the
  manual value survives — both for a field the JSON holds as null and for one where the JSON holds
  a different non-null value ([ADR-0012](decisions/ADR-0012-postgres-migrations-metadata-loader.md)).
- Migrations run clean against an empty database, and a second run is a no-op.

**Verify-phase results (2026-09-22, T12) — V1–V10 all pass.**

| # | Criterion | Result | Evidence |
|---|---|---|---|
| V1 | Cardinality from the actual dataset | Pass | `docs/schema.md` §2 — 150 series, cited to `reports/pre_ingest_census.md:19` (150 distinct `(experiment_id, source, signal)`), not estimated. |
| V2 | Raw preserved unchanged, by query | Pass | `tests/integration/test_raw_preservation.py::test_numeric_value_round_trips_at_full_precision_including_negative` and `::test_categorical_state_round_trips_as_a_literal_string_not_an_integer`, both against a live Core. |
| V3 | Downsampling matches a hand-computed aggregate under a stated predicate | Pass | Unit half: `tests/unit/test_rollup.py` (12 tests, hand-built buckets). End-to-end half: `tests/integration/test_rollup_run.py::test_rollup_matches_hand_computed_aggregate_and_distinguishes_a_gap`; `policy_version` stamped on every row per `::test_policy_version_is_stamped_on_every_written_row`. |
| V4 | Retention checked against the data's own timestamp span | Pass | `tests/integration/test_influx_init.py::test_90d_retention_refuses_and_names_experiments_oldest_first` and `::test_365d_local_retention_clears_all_six_experiments`. |
| V5 | Retention proven behaviourally (throwaway 1-hour database) | Pass | `tests/integration/test_retention.py::test_retention_hides_expired_points_but_keeps_fresh_ones`, teardown in a fixture. |
| V6 | The "months of data" question, with arithmetic behind it | Pass | `docs/schema.md` §5 — 1,059,840 points/day, 387M/plant-year, 60:1 rollup ratio; recomputed by hand while verifying (777,600+172,800+103,680+5,760=1,059,840; ×365=386,841,600). |
| V7 | Rollup lag below raw retention, recorded as an operational invariant | Pass | `docs/schema.md` §6; also carried into deliverable H per M7's scope. |
| V8 | Metadata queryable; nulls survive as nulls | Pass | `tests/integration/test_metadata_loader.py::test_load_populates_all_six_experiments`, `::test_null_fields_survive_as_null_not_defaulted`; re-confirmed live via `scripts/load_experiments.py` against a freshly migrated database ("loaded 6 experiment(s)"). |
| V9 | The loader cannot revert a correction (null **and** wrong-non-null) | Pass | `::test_rerun_cannot_revert_a_manual_null_correction`, `::test_rerun_cannot_revert_a_manual_wrong_non_null_correction`. |
| V10 | Migrations run clean; a second run is a no-op | Pass | `tests/integration/test_migrations.py::test_real_migrations_apply_clean_and_rerun_is_noop`; re-confirmed live: `python -m scripts.migrate` → `applied: 0001, 0002`, second run → `up to date, nothing to apply`. |

**T12's own acceptance criteria, beyond the V-table:**
- Full from-scratch cycle run deliberately once: `docker compose down -v` → `up -d` → both containers healthy (~15s) → `scripts/bootstrap_influx_token.py` (fresh token, non-interactive) → `python -m scripts.migrate` → `scripts/init_influx.py` (three databases created) → `scripts/load_experiments.py` (6 experiments loaded) → `python -m pytest -v` → **43 passed, 0 skipped, 0 failed**.
- `data/raw/dac_raw_timeseries.sha256` still verifies against a freshly computed SHA-256 of the CSV — M1 touched no raw data.
- `ruff check .` and `ruff format --check .` both clean; `docker compose config` validates with no `latest` image tag.
- One stale fact was caught and fixed while assembling this table, not a design decision: `docs/schema.md` §3's rollup local-retention row still read "1 year (365d)" from before the T2 walkthrough raised it to 5y (MISTAKES.md, flagged in this file's 2026-09-22 status note above) — corrected to `5y` with the same reasoning `.env.example` already carries.
- **CI green on the branch:** pushed to `origin/m1-data-model`; both jobs passed on the first run against this branch — [run 35779389919](https://github.com/sebtum/dac-timeseries-pipeline/actions/runs/35779389919) (`lint` 14s, `integration` 1m1s). This is the first time InfluxDB 3 Core has actually come up inside a GitHub Actions runner rather than being reasoned about from local behaviour.
- **Deferred by Sebastian's explicit call, not resolved here:** the T3/T8 decision-point walkthrough owed since MISTAKES.md E-05. M1 flips to `Done` below with this named as an open item rather than silently closed.

**M1: Done (2026-09-22).**

## M2 — Ingestion (B)

**Decide** — batching; timestamp precision; error handling; how the timezone question raised in
the data dictionary is resolved (U-01). Still open from
[ADR-0007](decisions/ADR-0007-duplicate-resolution-idempotency.md): the win-policy for
conflicting duplicates (U-07, constrained to be content-based) and the definition of "same" for
float comparison (U-08).

*Settled:* type handling for the categorical signals
([ADR-0006](decisions/ADR-0006-timeseries-data-model.md)); duplicate resolution and
idempotency / re-run behaviour (ADR-0007).

**Execute** — the ingestion script, against the M1 schema.

**Verify**
- Row counts reconcile CSV → Influx per experiment and signal; any deliberate discrepancy is
  explained, not hidden.
- Re-running is safe.
- Raw CSV checksum unchanged.
- Ingest throughput noted.

**Execute-phase status (2026-11-23).** Built on branch `m2-ingestion` under the new working
model: the milestone record is `.workflow/dac.md` (scenarios S2.1-S2.33), the decisions are in
[ADR-0013](decisions/ADR-0013-ingestion.md), and the report for review is
[`reports/M2.md`](../reports/M2.md). Committed and pushed on `m2-ingestion` (2026-11-23); CI
green: lint and integration, including the e2e ingest run
([run 45193161554](https://github.com/sebtum/dac-timeseries-pipeline/actions/runs/45193161554)).
Merge to `master` waits for approval (normal merge, no squash).
Results so far:

- Real run (`python -m scripts.ingest`, dev `dac_raw`): exit 0, 520,005 rows = 519,980 + 15 + 10 + 0,
  150 of 150 series balanced, 30 out-of-order rows, 0 outside the experiment windows, 72 s
  (about 7,200 rows per second). A second run left every reading and conflict row identical.
- Tests: 179 pass, 0 skipped (unit 123, integration 31, end-to-end 25), against a private stack.
- Findings that were not in the plan: a write to a missing database creates it, so ingest checks
  first (S2.24); partial accept behaves as documented on the v3 endpoint and is always off on the
  client's default endpoint; the private verify stack must not overwrite a dev `.env`
  (MISTAKES.md E-08).
- Closed: U-01, U-02, U-07, U-08, U-11.

## M2.5 — Post-ingest profiling *(added scope, not in the brief)*

Inserted between M2 and M3 to resolve U-16. Runs the profiling ADR-0010 already scoped as
"everything ingestion doesn't destroy" — this milestone exists to give that work a place on
the board, not to decide new checks.

**Decide** — nothing; placement was the only open question (U-16), now settled.

**Execute** — SQL aggregations against InfluxDB, plus targeted Python pulls for anything SQL
can't express (per ADR-0010):
- Value ranges against the documented ranges.
- Actual sample intervals against nominal rates.
- Gaps.
- Run-lengths of identical consecutive values.
- Noise characterisation (distribution of consecutive differences, kept separate from outlier
  detection).
- Physical relationships: `power` vs `voltage × current`, `co2_out_ppm` vs `co2_in_ppm`,
  `current` vs `current_setpoint`, `pressure_drop` vs `air_flow`.
- U-05 (Core's ~72h single-query span) is a live constraint here, not just at M5/M6, since
  profiling spans March–June 2026 — resolve it here or explicitly state the workaround
  (per-experiment queries, etc.).

**Execute-phase status (2026-11-23).** Built on branch `m2.5-profiling` (cut from `m2-ingestion`):
the milestone record is `.workflow/dac.md` (scenarios S25.1-S25.22), the decisions are in
[ADR-0014](decisions/ADR-0014-post-ingest-profiling.md), the committed output is
`reports/post_ingest_profile.json` and `.md`, and the report for review is
[`reports/M2.5.md`](../reports/M2.5.md). Merge to `master` waits for approval.
Results so far:

- Real run (`python -m scripts.post_ingest_profile`, dev `dac_raw`): exit 0, 150 series, 6
  experiments, 24 relationships, 519,980 points, 188 queries, about 16 s. Three runs gave
  identical JSON except the timing block.
- All 150 series and 24 relationships were recomputed in Python from plain `SELECT` pulls: 0
  mismatches to the 9th digit.
- U-05: a single 105-day span query was answered (519,906 points). Narrowed, still open for M6.
- Findings that were not in the plan: four engine quirks on Core 3.11.2 (conditional counts,
  signed zero, percentile precision, last-bit instability of fitted lines), each found by the
  calibration and worked around (ADR-0014). The verdict-word search finds nothing.

**Verify**
- Every check above produces a number or distribution he can cite, saved to a file.
- **No verdict labels** — counts, distributions and samples only, same constraint as M0
  (C-02). Grep-checkable.
- U-05 is either not a blocker for this span or the workaround is stated and demonstrated.

## M3 — Quality & cleaning pipeline (C, D)

**Decide**
- How raw value, processed value, quality flag and reason coexist; how a questionable reading
  stays present but excludable.
- Per-signal handling policy for: missing values, gaps, duplicates, out-of-order samples,
  flagged-bad data, outliers, sensor noise, stuck sensors, differing sample rates.
- The justification for why a pH signal, a plant state signal and an integrated energy value
  are not treated alike.

**Execute** — the pipeline; calibrated on a sample first, then run at full scale.

**Execute-phase status (2026-11-23).** Built on branch `m3-cleaning` (cut from `m2.5-profiling`):
the milestone record is `.workflow/dac.md` (scenarios S3.1-S3.34), the decisions are in
[ADR-0015](decisions/ADR-0015-cleaning-and-quality-pipeline.md) (with an addendum to ADR-0011), the
policy table is [`cleaning_policy.md`](cleaning_policy.md), the committed outputs are
`reports/cleaning_summary.json` and `reports/cleaning_report.md`, and the report for review is
[`reports/M3.md`](../reports/M3.md). Merge to `master` waits for approval. Nothing is committed or
pushed yet, and the judge has not run.
Results so far:

- Real run (`python -m scripts.clean`, dev `dac_raw`): exit 0, 150 series balanced, 519,980 readings
  = 514,443 accepted + 5,537 excluded, 29 gaps (18,519 s), 5 flatline runs, raw tables unchanged,
  about 41 s. Re-run on the dev stack and on a fresh private stack: summary identical except timing.
- Rollup over the verdict (`python -m scripts.rollup`): 16,256 buckets in about 12 minutes.
- Calibration: 0 mismatches against an independent plain-Python recompute on all six experiments.
  The first calibration found four hits outside the pre-pinned list; the re-plan resolved them
  (ADR-0015, decisions 24 to 26).
- Tests: unit 319 pass (290 before the policy-document test, 29 in it); the new end-to-end file
  `tests/e2e/test_clean_cli.py` 25 pass, 0 skipped, run in this session against the dev InfluxDB.
  The rest of the end-to-end and integration suites were last run in the earlier waves (rollup
  integration 10 pass) and were not re-run for the write-up.
- Closed: U-04, U-09, U-10, U-12. Narrowed: U-06 (time-chunking for continuous data remains).
  Added: A-05, A-06, A-07.
- Not run: the judge, GitHub Actions. The real-data rollup is not in CI (about 12 minutes).

**Verify**
- Nothing silently dropped or silently fixed — provable by count reconciliation, raw vs
  processed.
- Every exclusion carries a machine-readable reason.
- Sampled hand-checks of each rule.
- The per-signal policy table is defensible line by line.

## M4 — Derived metrics (E)

**Decide** — where each metric is computed (write-time task vs query-time vs Python);
integration method for energy; how quality-excluded samples propagate into a derived value;
how a metric computed over incomplete data is labelled.

**Execute** — metric computation and storage.

**Execute-phase status (2026-11-24).** Built on branch `m4-metrics` (cut from `master`): the
milestone record is `.workflow/dac.md` (scenarios S4.1-S4.28), the decisions are in
[ADR-0016](decisions/ADR-0016-derived-metrics.md), the formulas are in [`metrics.md`](metrics.md),
the committed outputs are `reports/metrics_summary.json` and `reports/metrics_report.md`, and the
report for review is [`reports/M4.md`](../reports/M4.md). Merge to `master` waits for approval.
Nothing is committed or pushed yet, the judge has not run, and GitHub Actions has not run.
Results so far:

- Real run (`python -m scripts.metrics`, dev `dac_raw`): exit 0, 6 experiments, 121,167 points in
  `metrics_series`, 228 Postgres rows (78 + 150), counts read back and balanced, input tables
  unchanged, 0 plausibility failures, about 26 s. Re-run on the dev stack and on a fresh private
  stack: summary identical except timing.
- Calibration: 0 differences at 9 digits against an independent plain-Python recompute on EXP_001,
  EXP_004 and all six (13 metrics, power check, efficiency check, 150 signals, stored series).
- Power cross-check: 5 of 6 experiments within tolerance at every instant. EXP_001 is 0.983 (7,005
  of 7,125): 120 s of logged power about 6 kW above voltage times current. Reported as a result; the
  0.99 threshold was kept. Energy still agrees (0.67 %).
- Tests: unit pass, including the metrics-document test (`tests/unit/test_metrics_doc.py`); the
  end-to-end, integration and exit-code suites passed in the earlier waves (see the execute log).
- Added: A-08. Noted: U-06 (metrics are per-experiment batch jobs).
- Not run: the judge, GitHub Actions. Not committed or pushed. The real-data metrics run is not in
  CI.

**Verify**
- Computed power cross-checked against the independently logged `power` signal (the data
  dictionary explicitly invites this).
- Energy checked against an independent integration.
- Efficiency and capture rate sanity-checked for physical plausibility.
- Completeness / valid-sample / bad-quality percentages present per experiment.

## M5 — Comparison & findings (F)

**Decide** — the alignment model (`experiment_time`); whether and how process phases segment
the analysis; which cross-experiment comparisons the data actually supports and which it
doesn't; what evidence standard a "finding" has to meet.

**Constraint to satisfy:** the experiments span March–June 2026, but InfluxDB 3 Core caps a
single query's span at ~72h by default (U-05). Whatever the comparison approach, it has to
work within that or explicitly change it.

**Execute** — the comparison queries and analysis.

**Execute-phase status (2026-11-24).** Built on branch `m5-comparison` (cut from `master`): the
milestone record is `.workflow/dac.md` (scenarios S5.1-S5.26), the decisions are in
[ADR-0017](decisions/ADR-0017-comparison-and-findings.md), the method is in
[`comparison.md`](comparison.md), the committed outputs are `reports/comparison_summary.json` and
`reports/comparison_report.md`, the draft findings are in
[`reports/findings.md`](../reports/findings.md), and the report for review is
[`reports/M5.md`](../reports/M5.md). Merge to `master` waits for Sebastian's approval of the
findings. Nothing is committed or pushed yet, the judge has not run, and GitHub Actions has not run.
Results so far:

- Real run (`python -m scripts.compare`, dev `dac_raw`): exit 0, 6 experiments, 28 voltage fits
  (all testable, 0 singular resamples of 1000 in each), 8 evidence rows, 15 comparisons, 219
  queries, about 53 s. It writes files only; no database row changed.
- Calibration: 0 differences at 9 digits against an independent plain-Python recompute (no
  pipeline imports) on EXP_001 (347 values) and on all six (3,497 values). Four `r2_drop` values
  near 1e-8 differ in the 9th digit (a difference of two R squared near 0.99), not counted.
- Reproducibility: a rerun on the dev stack and a run on a fresh private stack give the same
  summary except timing, and the report is byte-equal.
- Answer: all 8 evidence rows are `not_resolved`. Hydrolyzer steady: the flow and pressure
  intervals include zero in 6 of 6 experiments and pooled. Whole-run fits are not separable (flow
  VIF 14 to 29). EXP_005's residuals are strongly autocorrelated (block lag-1 correlation 0.87), so
  its intervals are probably too narrow.
- Also: EXP_004's raw air flow falls 98.3 % after 09:00Z while fan speed, pressure drop, outlet CO2
  and capture efficiency stay put (supports A-07 without closing it). Pressure drop does not follow
  air flow within an experiment (R squared at most 0.002); across experiments it follows two
  air-flow levels only. Comparability: 1 supported pair, 14 confounded. Partial coverage: EXP_002
  voltage, power and energy per kilogram; EXP_004, EXP_005 and EXP_006 capture and energy per
  kilogram.
- Tests: unit pass, including the findings test (`tests/unit/test_findings_doc.py`, every number
  checked against the summary) and the method-document test (`tests/unit/test_comparison_doc.py`).
  The end-to-end, integration and exit-code suites passed in the earlier waves (see the execute
  log).
- Added: A-09, the A-07 status from the air-flow check, the U-05 note (219 queries, no span error;
  still open for the Grafana time picker). Contract step added to CI.
- Not run: the judge, GitHub Actions. Not committed or pushed. The real-data comparison is not in
  CI.

**Verify**
- At least three findings, each stated as claim + the query and numbers behind it.
- **A specific, evidenced answer for how flow and pressure relate to cell voltage** — the
  brief singles this one out.
- Comparisons the data can't support are explicitly named as such.

## M6 — Grafana dashboard (G)

**Decide** — panel inventory and layout; variables/templating for the experiment selector;
how multi-experiment overlay on a common time axis is achieved; how data quality is made
visible rather than hidden.

**Constraints to satisfy:** the ~72h single-query span (U-05) applies to any panel with a wide
time picker. Grafana does not join datasources in a normal panel, so metadata from Postgres
reaches the dashboard through a template variable rather than a join
([ADR-0005](decisions/ADR-0005-postgres-experiment-metadata.md)).

**Execute** — build it; export the JSON model into the repo.

**Verify**
- Clicked through end to end; every panel returns data for every experiment.
- Overlay works across experiments with different wall-clock starts.
- A quality-degraded window is visibly degraded on screen.
- Screenshots committed.

## M7 — Edge, cloud, presentation (H, I, J)

**Decide**
- The edge architecture: control system → edge device → onward; store-and-forward behaviour
  under connectivity loss; how the link is secured.
- System health as a concern separate from per-value quality — including naming the failure
  mode where every point still looks individually fine but the pipeline has stopped moving
  data.
- The AWS mapping per layer: managed vs custom, and what changes about failure handling once
  it's cloud/multi-tenant.
- The walkthrough narrative.

**Execute** — written design docs plus a diagram; walkthrough notes.

**Verify**
- The design is specific — protocols, buffering, backpressure, retry, auth — not a component
  list.
- Each question the brief poses has a direct answer.
- The walkthrough traces one voltage spike from raw telemetry to cross-experiment comparison
  without the scientist aligning anything by hand.

---

## Terminal step — self-review

Only once Sebastian declares the working session over: open `_debrief/`, check his calls
against the list of defects that were deliberately built into the dataset, and write a final
retrospective. Nothing before that point reads `_debrief/`.
