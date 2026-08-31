# ADR-0004 — InfluxDB 3 Core, queried with SQL

Status: Accepted
Milestone: M0   Deliverable: A, B   Date: 2026-08-12

## Context

ADR-0001 records that InfluxDB itself was imposed by the brief. *Which* InfluxDB was not —
and the versions differ enough that treating them as one product is a mistake. This ADR
covers the version and query-language choice, which is ours.

Facts established before deciding:

- Since **27 May 2026 the `influxdb:latest` Docker tag points at InfluxDB 3 Core**, so a
  version gets chosen whether or not anyone decides one. Pinning the tag is mandatory.
- **InfluxDB 3 (Core and Enterprise) supports SQL and InfluxQL; it does not support Flux.**
  InfluxDB 2.x is the reverse: Flux and InfluxQL, no SQL.
- **InfluxDB 3 Core has no task engine.** 2.x downsampling is a Flux task writing from a
  source bucket to a destination bucket with a different retention period. Core replaces that
  with an embedded Python Processing Engine that runs plugins on triggers — capable, but the
  downsampling logic becomes something you write.
- **Core caps the span of a single query.** A query plan is limited to 432 Parquet files,
  which at the default 10-minute gen1 block size is roughly a **72-hour range**. Historical
  *writes* are unrestricted — that limitation was explicitly lifted — but the query-span limit
  was not. The file limit is a configuration option and can be raised.
- Core's own documentation lists **"historical query capability and single series indexing"**
  among the features Enterprise *adds* to Core. Enterprise also enforces retention periods at
  query time and routinely deletes expired data.
- Grafana's **official** InfluxDB datasource absorbed the v3 Flight SQL plugin; selecting SQL
  as the query language uses the Flight SQL backend directly. The standalone
  `grafana-flightsql-datasource` plugin is no longer actively developed.

Workload shape that interacts with the above: six experiments of 2 hours each, spread across
March–June 2026. Per-experiment queries span 2 hours. A naive cross-experiment overlay spans
~3.5 months.

## Options considered

### Option 1 — InfluxDB 3 Core
Advantages: SQL, so one query language is shared with Postgres (ADR-0005) instead of
context-switching into Flux; Flight SQL is the first-class path in Grafana's official
datasource; Parquet/DataFusion foundation is the direction the product is actually going;
free and open source.
Caveats: **downsampling is not built in** — it must be written as a Processing Engine plugin
or an external job; ~72h single-query span at default settings; retention enforcement is
weaker than Enterprise; requires the `influxdb3-python` client (Flight/Arrow), not the 2.x
`influxdb_client` already installed.

### Option 2 — InfluxDB 2.x
Advantages: downsampling and retention genuinely *are* built in — a Flux task from source
bucket to destination bucket, configured in the UI, which is exactly what deliverable A asks
for; no query-span limit; uses the already-installed `influxdb_client`; the most
documented-and-blogged version, so fewer unknowns.
Caveats: Flux as the query language — a language InfluxData has moved away from, diverging
from the SQL used for metadata; new work built on it is built on a dead end; InfluxQL as the
alternative is weaker than SQL for the analytical joins and window functions the comparison
work needs.

### Option 3 — InfluxDB 3 Enterprise (free for at-home use)
Advantages: keeps SQL; adds historical query capability and single-series indexing, removing
the span problem; compaction and query-time retention enforcement, so the retention story is
demonstrable rather than hand-built.
Caveats: the free tier is licensed for at-home/non-commercial use, which is a poor fit for a
design presented as a plant architecture — a reviewer may reasonably ask what it costs in
production; heavier to run; makes the design depend on a commercial tier.

## Decision

InfluxDB 3 Core, queried with SQL, image tag pinned explicitly.

## Why

The compatibility argument decides it. This design already commits to PostgreSQL for
experiment metadata (ADR-0005), so choosing 3 Core means the whole system is queried in SQL —
one language across both stores, in the pipeline, in Grafana, and in review. Option 2
would buy built-in downsampling at the price of writing the analytical half of the project in
Flux, a language the vendor has moved on from; that's paying in the currency of the future to
save work today. Option 3 fixes Core's real limitations, but licensing it for at-home use and
then presenting it as a plant architecture is a weaker position to defend than accepting
Core's constraints openly.

The costs are accepted with eyes open rather than discovered later: downsampling gets built,
and the 72h span is designed around. Both are visible in Consequences and tracked as U-04 and
U-05.

## Consequences

- **Downsampling is now build-work, not configuration.** It becomes real execute-and-verify
  scope in M1 rather than a checkbox. Mechanism is open (U-04).
- **The ~72h query span constrains the overlay.** Per-experiment queries are 2 hours and fit
  comfortably; a single query spanning all six experiments does not. Either the overlay issues
  one query per experiment and aligns them, or the Parquet file limit is raised — a decision
  for M5/M6 (U-05). The same limit applies to any Grafana panel with a wide time picker.
- **Client library changes** to `influxdb3-python` over Flight/Arrow. The installed
  `influxdb_client` is the 2.x client and is not what this design uses (ADR-0003).
- The image tag must be pinned in the compose file; `latest` now moves between major versions.
- Retention enforcement is Core-grade, not Enterprise-grade — worth stating in the
  cost/scalability answer rather than glossing.

## Assumptions relied on

A-01, A-02

## Defense

The brief gave me InfluxDB but not a version, and the versions aren't interchangeable — 3
dropped Flux and the task engine, 2.x has no SQL. I took 3 Core specifically for SQL, because
the metadata lives in Postgres and I'd rather have one query language across the system than
write half the project in a language the vendor has stopped investing in. That costs me the
built-in downsampling task 2.x would have given me, so downsampling is something I build, and
Core caps a single query at roughly 72 hours, which is why the multi-experiment overlay queries
per experiment rather than over one wide range. If this were production rather than a laptop,
that 72-hour cap and the weaker retention enforcement are exactly what I'd be paying Enterprise
to remove.
