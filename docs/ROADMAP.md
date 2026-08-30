# Roadmap

Single source of truth for where the work stands. Update the phase column as each milestone
moves; don't rely on memory or chat history.

**Scope:** untimed, build everything in `task/TASK.md` A–J. (`README.md` still mentions a
60-minute clock — superseded by commit `3693904`.)

**Guardrail on this document:** it names *decision points, never their resolutions*. Every
question below is derivable from `task/TASK.md` or `task/DATA_DICTIONARY.md` alone. Answers
live in `decisions/`, written only after Sebastian has made the call.

---

## Milestone board

| M | Name | Deliverables | Phase | ADRs |
|---|------|--------------|-------|------|
| M0 | Environment & reconnaissance | (setup), CI | Done | [0008](decisions/ADR-0008-local-runtime-docker-compose.md), [0009](decisions/ADR-0009-provisioning-as-code.md), [0010](decisions/ADR-0010-profile-post-ingest-in-database.md) |
| M1 | Time-series data model | A | Plan | [0006](decisions/ADR-0006-timeseries-data-model.md) |
| M2 | Ingestion | B | Discuss | [0007](decisions/ADR-0007-duplicate-resolution-idempotency.md) |
| M2.5 | Post-ingest profiling | — | Not started | [0010](decisions/ADR-0010-profile-post-ingest-in-database.md) |
| M3 | Quality & cleaning pipeline | C, D | Not started | — |
| M4 | Derived metrics | E | Not started | — |
| M5 | Comparison & findings | F | Not started | — |
| M6 | Grafana dashboard | G | Not started | — |
| M7 | Edge, cloud, presentation | H, I, J | Not started | — |
| — | Debrief (terminal) | — | Locked until session declared over | — |

Phase values: `Not started` → `Discuss` → `Plan` → `Execute` → `Verify` → `Done`.

## Deliverable coverage

Every letter in the brief must appear here with a live state. Nothing gets dropped silently.

| # | Deliverable | Milestone | State |
|---|-------------|-----------|-------|
| A | Time-series data model | M1 | Schema settled (ADR-0006); retention/downsampling not started |
| B | Ingestion | M2 | Duplicate handling & idempotency settled (ADR-0007); rest not started |
| C | Data quality pipeline | M3 | Not started |
| D | Cleaning and processing | M3 | Not started |
| E | Derived metrics | M4 | Not started |
| F | Experiment comparison | M5 | Not started |
| G | Grafana dashboard | M6 | Not started |
| H | Edge ingestion & resilience (design) | M7 | Not started |
| I | Cloud scaling narrative (verbal) | M7 | Not started |
| J | Presentation walkthrough (verbal) | M7 | Not started |
| — | CI/CD *(added scope, not in the brief)* | cross-cutting, from M0 | M0 increment done ([ADR-0009](decisions/ADR-0009-provisioning-as-code.md)) — lint + format check green on GitHub Actions; next increment lands at M1 |
| — | Post-ingest profiling *(added scope, not in the brief)* | cross-cutting, M2.5 | Not started — placement settled (U-16); scope from [ADR-0010](decisions/ADR-0010-profile-post-ingest-in-database.md) |

---

## The four-phase protocol

Every milestone runs the same loop.

**1. Discuss.** Claude puts the decision points on the table and supplies *facts only* — what
the data shows, how InfluxDB/Grafana actually behave, what the brief demands. No
recommendation, no leading questions, no hinting at the shape of a good answer. Sebastian
proposes. The moment he does, Claude reacts plainly: right, wrong, or partially right, and
why — naming the actual problem first, then the principle behind it, so it transfers. If he's
right, say so and add the sharper thing he's missing (edge case, tradeoff, how it gets
attacked in the debrief). Wrong or shaky calls go into `MISTAKES.md § Corrected design calls`
immediately.

**2. Plan.** The settled decision becomes an ADR in `decisions/` (options, caveats, why,
debrief answer). New assumptions and unknowns are registered in `ASSUMPTIONS.md`. The verify
criteria for the milestone are written **now, before any code exists** — deciding what "done"
means after seeing the output is how you fool yourself.

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
| M1 | Schema/config validation — database and retention definitions checked, not assumed; Postgres metadata schema migration runs clean; downsampling job tested against a known aggregate. |
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
- CI green on the branch ([run 33302720981](https://github.com/sebtum/phlair/actions/runs/33302720981),
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

**Decide**
- ~~Measurement / tag / field layout; how experiment, source and sensor identity are
  represented.~~ *(settled: [ADR-0006](decisions/ADR-0006-timeseries-data-model.md))*
- ~~Where raw values live unchanged.~~ *(settled: ADR-0006)*
- ~~Tag cardinality budget.~~ *(settled: ADR-0006 — 150 series, measured not estimated)*
- Where processed values, pipeline quality verdicts and exclusion reasons live — a second axis,
  independent of the numeric/state split (U-09, U-10). Deferred to M3.
- Retention, downsampling, tiering — what stays full-resolution, what rolls up, when.

**Execute**
- Databases and retention periods; the schema written up as ADRs plus a compact schema
  reference.
- **Build the downsampling mechanism.** InfluxDB 3 Core has no task engine, so this is code —
  a Processing Engine plugin or an external job (U-04). Not configuration
  ([ADR-0004](decisions/ADR-0004-influxdb3-core-sql.md)).
- Postgres schema for experiment metadata, loaded from `experiments.json`
  ([ADR-0005](decisions/ADR-0005-postgres-experiment-metadata.md)).

**Verify**
- Cardinality estimated from the *actual* dataset, not guessed.
- "Raw preserved unchanged" is demonstrable by query, not asserted.
- Downsampling actually runs and produces a rolled-up series that matches a hand-computed
  aggregate.
- The retention/downsampling story survives the "months of 1 Hz electrochemical data"
  question with arithmetic behind it.
- Metadata queryable from Postgres; the null fields in `EXP_003`, `EXP_005` and `EXP_006`
  survive the load as nulls rather than being silently defaulted.

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

## Terminal step — debrief

Only once Sebastian declares the working session over: open `_debrief/`, score against the
answer key, and write a final retrospective comparing his calls to the defects that were
actually injected. Nothing before that point reads `_debrief/`.
