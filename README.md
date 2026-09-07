# DAC Process Data Pipeline

A time-series data platform for a Direct Air Capture (DAC) pilot plant: ingest raw,
imperfect industrial sensor data into InfluxDB, make data quality a first-class,
queryable property rather than something silently cleaned away, derive process and
energy metrics per experiment, and compare experiments on a common time axis in
Grafana.

Built solo as a systems/data-engineering exercise against a brief that mirrors a real
plant-to-cloud problem: six pilot-scale experiments' worth of raw sensor data, with the
gaps, noise, quality flags, and timing quirks a real PLC/OPC-UA historian export would
have — see [`task/TASK.md`](task/TASK.md) for the full brief and
[`task/DATA_DICTIONARY.md`](task/DATA_DICTIONARY.md) for the per-signal reference.

## Why this project

Most portfolio data projects start from a clean CSV. This one deliberately doesn't: the
dataset generator injects the kind of defects a real acquisition system produces —
dropouts, stuck sensors, out-of-order and duplicate samples, mixed sample rates,
quality flags that are present but not exhaustive. The engineering problem is not
"load this into a database," it's *"design a system that tells a scientist which
numbers they can trust, and why."*

## Architecture

```
                 ┌──────────────────────┐
  data/raw/      │  Python ingestion &  │      ┌─────────────┐
  *.csv  ───────▶│  data-quality        │─────▶│ InfluxDB 3  │──▶ Grafana
  (immutable,    │  pipeline            │      │ Core (SQL)  │    dashboards
  gitignored)    └──────────────────────┘      └─────────────┘
                           │                           ▲
                           ▼                           │
                   ┌───────────────┐           rollups / tiers
                   │  PostgreSQL   │           (raw → 1‑min → pinned
                   │  (experiment  │            → cold/Parquet)
                   │   metadata)   │
                   └───────────────┘
```

- **InfluxDB 3 Core**, queried over SQL via `influxdb3-python`/Arrow Flight — the
  time-series store for sensor readings.
- **PostgreSQL** — experiment metadata (operator, setpoints, sorbent batch), which is
  relational, low-cardinality, and needs migrations, not a time series.
- **Grafana** — the comparison dashboard: experiment selector, KPI summary, aligned
  time-series overlays, and a data-quality layer that's visible rather than hidden.
- **Docker Compose**, provisioned as code — no manual click-ops setup step; every
  database, token, and retention policy is created by a script, not a human following
  a runbook.

Every non-trivial decision — schema shape, retention strategy, duplicate handling,
provisioning approach — is recorded as an ADR in [`docs/decisions/`](docs/decisions/),
each one stating the alternatives considered and why they were rejected.

## Engineering highlights

**Raw values are never silently altered.** The data model
([ADR-0006](docs/decisions/ADR-0006-timeseries-data-model.md)) splits storage into a
numeric table and a categorical-state table rather than coercing everything into one
shape — InfluxDB 3 fixes a column's type on first write, and encoding state signals
like `valve_state` as integers would let something like `mean(value)` silently return a
number that looks fine and means nothing. `quality` is stored as a field alongside the
value it describes, not used to fork a series in two, so "give me everything" and "give
me only what's trustworthy" are both a single `WHERE` clause away, never a schema
change.

**Retention has a monitored invariant, not just a TTL.**
[ADR-0011](docs/decisions/ADR-0011-retention-tiering-rollup.md) works out real volume
arithmetic (~387M points/plant-year from measured per-signal sample rates) and lands on
four tiers — full-resolution raw, 1-minute rollups, indefinitely-pinned intervals of
interest, and a Parquet cold tier — with an explicit invariant: rollup lag must stay
strictly below raw retention, or a bucket can freeze into a permanent, stale aggregate
with no recovery path once raw data expires. That's named as the specific failure mode
where every individual point still looks fine while the pipeline has silently stopped
moving data — the reason a rollup job needs a heartbeat, not just a schedule.

**Duplicate/collision detection at bounded memory.**
[`pipeline/collisions.py`](pipeline/collisions.py) detects same-series, same-timestamp
collisions via an external merge sort — sort in memory-bounded chunks, spill sorted
runs to disk, k-way merge with `heapq.merge` — so memory stays O(chunk size + run
count) regardless of file size, not O(rows). Written as a shared module by design so the
same logic backs both the pre-ingest census (its current caller) and the ingestion path,
rather than diverging into two implementations of the same problem.

**Auth-enabled local infra, bootstrapped non-interactively.** InfluxDB 3 Core has no
default admin token and no unauthenticated health endpoint by default;
[`scripts/bootstrap_influx_token.py`](scripts/bootstrap_influx_token.py) mints one
idempotently into a gitignored `.env`, and
[`scripts/init_influx.py`](scripts/init_influx.py) creates each tiered database with
its retention period read from the environment, never hardcoded. Local dev runs with
auth on, matching how the plant deployment would run it.

## Quick start

Requires Docker and Python 3.14.

```bash
git clone <this-repo>
cd dac
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt

python generator/generate_dataset.py             # writes data/raw/*.csv + experiments.json

docker compose up -d                             # InfluxDB 3 Core + PostgreSQL
python scripts/bootstrap_influx_token.py         # mints INFLUX_TOKEN into .env
python scripts/init_influx.py                    # creates raw/rollup/pinned databases

pytest                                            # unit tests always run;
                                                   # integration tests skip (not fail)
                                                   # if a container isn't reachable
```

## Repository layout

```
task/            The brief (TASK.md) and per-signal reference (DATA_DICTIONARY.md).
generator/       Deterministic, seeded synthetic dataset generator (stdlib only).
data/raw/        Generated raw dataset. Immutable — never edited in place; only its
                 SHA-256 checksum is committed.
pipeline/        Pure, I/O-free processing logic (rollup aggregation, collision
                 detection) — unit-testable without a database.
scripts/         Operational scripts: provisioning, token bootstrap, census/profiling.
docs/decisions/  ADRs — one per independent architectural decision, with alternatives
                 considered and rejected.
docs/schema.md   Compact reference for the InfluxDB schema, cardinality, and retention
                 tiers, citing the ADRs and measurements behind each figure.
reports/         Data profiling output, measured against the raw CSV.
tests/           Unit tests (no dependencies) and integration tests (skip cleanly
                 without a live InfluxDB/PostgreSQL).
```

## Documentation

- [`task/TASK.md`](task/TASK.md) — the project brief this was built against.
- [`docs/schema.md`](docs/schema.md) — the InfluxDB schema, measured cardinality, and
  retention tiers, with every figure traced to a source.
- [`docs/decisions/`](docs/decisions/) — the full architecture decision log.
- [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) — assumptions made where the brief was
  silent, kept current as the system evolves.
