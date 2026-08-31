# ADR-0001 — InfluxDB as the time-series store

Status: Given (constraint)
Milestone: —   Deliverable: A, B   Date: 2026-08-11

> Covers the *product* only, which the brief imposed. The version and query language were a
> real choice and are recorded separately in [ADR-0004](ADR-0004-influxdb3-core-sql.md).

## Context

`task/TASK.md` deliverable A opens with "Design how this data should live in InfluxDB". The
store was imposed by the brief, not selected — this ADR records that fact and the defence,
because "it was in the brief" is not an answer a reviewer will accept.

Workload facts that any candidate store would have to handle:

- Long-format sensor readings: `timestamp, experiment_id, source, signal, value, quality`.
- 520,005 data rows for six 2-hour pilot experiments (~32 MB CSV).
- Mixed sample rates: ~1 Hz down to ~1/60 Hz, plus event-based signals written only on change.
- Mostly float values, a few categorical strings (`valve_state`, `process_state`).
- The brief demands a retention/downsampling story for "months of high-resolution
  electrochemical data" — so the real target is far larger than the sample dataset.
- Read pattern: per-experiment range scans, cross-experiment overlays on a shifted time axis,
  aggregation into per-experiment KPIs.

## Options considered

### Option 1 — InfluxDB (the given)
Purpose-built TSDB. Line protocol ingest, tag-indexed series, retention policies and
downsampling tasks as first-class features, native Grafana datasource.
Advantages: retention/downsampling is configuration rather than code; ingest path is designed
for this shape of data; Grafana integration is the best-supported of any TSDB.
Caveats: schema design is unforgiving — tag choice determines series cardinality, and getting
it wrong degrades badly and is painful to undo. Two incompatible query languages in the wild
(InfluxQL, Flux) and a third era (3.x / SQL) — version choice has real consequences. Joins
and relational metadata are weak; anything relational tends to get bolted on beside it.

### Option 2 — PostgreSQL + TimescaleDB
Relational database with a time-series extension: hypertables, continuous aggregates,
compression.
Advantages: one store for both readings and experiment metadata, with real joins; SQL, which
every scientist and BI tool already speaks; continuous aggregates cover the downsampling
requirement; mature operationally.
Caveats: heavier to run; ingest throughput lower than a purpose-built TSDB at high
cardinality; Grafana support good but less idiomatic for time-series-specific panels;
compression and chunk tuning is its own learning curve.

### Option 3 — Prometheus
Metrics system with a pull model and its own TSDB.
Advantages: excellent for operational/system metrics; strong alerting story.
Caveats: fundamentally the wrong tool here — pull-based scraping of a live target, not
historical backfill of an archived CSV; float-only, no categorical values; deliberately lossy
and short-retention; no notion of a quality flag alongside a value.

### Option 4 — Columnar files (Parquet) + DuckDB / ClickHouse
Store raw as partitioned Parquet, query with an analytical engine.
Advantages: cheapest possible storage per byte; raw immutability is trivially satisfied;
excellent for whole-dataset analytical scans and experiment comparison; no server needed for
DuckDB.
Caveats: no built-in retention or downsampling lifecycle — you build it; live/streaming ingest
is not the model, so the upstream edge story (deliverable H) fits less naturally; Grafana
integration is weaker and more manual.

## Decision

InfluxDB, as imposed by the brief.

## Why

It's a defensible fit for the shape of this workload. The data is append-only sensor readings
keyed by time, read back as range scans and aggregations — the access pattern a TSDB is built
around. Two requirements in the brief point specifically at it rather than at a general-purpose
database: deliverable A demands a retention/downsampling/tiering answer for "months of
high-resolution electrochemical data", which is lifecycle management a TSDB treats as a
platform concern; and deliverable H puts a streaming edge device upstream, which is the ingest
model InfluxDB assumes. Grafana support settles the visualisation half (ADR-0002).

Where I'd argue against it: the moment the questions become predominantly relational. This
project already hit that boundary — the experiment metadata does not belong in InfluxDB and
went to Postgres instead (ADR-0005). If the workload were mostly whole-dataset analytical scans
over archived experiments with no live ingest, Parquet plus DuckDB would be cheaper and
simpler, and the retention lifecycle InfluxDB gives you would be machinery I wasn't using.

## Consequences

- Schema design becomes the highest-stakes decision in the project (M1), because cardinality
  mistakes are expensive to reverse after ingest.
- Experiment metadata (`experiments.json`) has no natural relational home in this store —
  where it lives is an open M1 question.
- Retention and downsampling are available as platform features rather than code, so the
  cost/scalability part of deliverable A can be demonstrated rather than described.

## Assumptions relied on

A-01

## Defense

InfluxDB was given in the brief, so I didn't choose it — but it fits: append-only sensor data
read back as range scans, with retention and downsampling as a platform concern rather than
something I write, which is what the cost question in deliverable A is really asking about.
Against Postgres/Timescale, the honest answer is that it's a closer call than it looks, and I
did split the difference — the readings are in InfluxDB, the experiment metadata is in Postgres,
because that half of the problem is relational.

The part I'd flag as a lesson: a product's feature list is version-specific, not
product-specific. I initially justified this on InfluxDB's built-in downsampling, which is true
of 2.x and false of the 3.x I chose. When a capability is load-bearing for a deliverable, it
has to be checked against the exact version being run, not the product name.
