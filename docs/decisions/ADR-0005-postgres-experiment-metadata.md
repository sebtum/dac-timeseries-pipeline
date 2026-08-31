# ADR-0005 — PostgreSQL for experiment metadata

Status: Accepted
Milestone: M1   Deliverable: A, F   Date: 2026-08-12

## Context

`data/raw/experiments.json` holds per-experiment metadata: `experiment_id`, `start_time`,
`end_time`, `duration_s`, `current_setpoint_nominal_A`, `air_flow_nominal_m3h`,
`solvent_flow_nominal_Lmin`, `operator`, `sorbent_batch`, `notes`. Six rows, ~2.3 KB.

Size is not the reason this needs a store. Two properties of the data are:

- **It is mutable.** `task/DATA_DICTIONARY.md` states "not every field is populated for every
  experiment", and the file bears that out: `EXP_003` has a null `notes`, `EXP_005` a null
  `sorbent_batch`, `EXP_006` a null `operator`. Those gaps get filled in later — someone
  identifies which batch was used, an operator name gets corrected. Metadata written into
  InfluxDB tags cannot be corrected without rewriting every point carrying the tag.
- **It is the join key for comparison.** Deliverable F is cross-experiment comparison, and the
  questions are relational: which experiments share a `sorbent_batch`, which ran at the same
  `current_setpoint_nominal_A`, which are actually comparable to the baseline. Those are joins
  and filters over attributes, not time-series operations.

This resolves U-03, which recorded that no requirement had yet been identified for a relational
store.

## Options considered

### Option 1 — PostgreSQL alongside InfluxDB
Advantages: metadata is correctable with an `UPDATE` and no rewrite of time-series data;
nullable columns model the missing fields honestly; real joins and constraints; SQL, the same
language as InfluxDB 3 (ADR-0004); grows naturally as metadata does — batches, calibrations,
maintenance records — which is what a real plant accumulates.
Caveats: a third service to run for 2.3 KB of data; no referential integrity across two
databases; Grafana does not join across datasources in a normal panel; DataFusion SQL and
PostgreSQL SQL are different dialects.

### Option 2 — Metadata denormalised into InfluxDB tags
Advantages: no extra service; every point self-describing; filtering by nominal setpoint is a
tag filter with no join at all.
Caveats: **corrections require rewriting history**, which is the requirement that started
this; every added metadata field multiplies series cardinality, the one thing InfluxDB
punishes hardest; nulls have no honest representation in a tag; `notes` is free text and has
no business being an indexed tag.

### Option 3 — A metadata measurement inside InfluxDB
Advantages: single store; metadata updatable by writing a newer point.
Caveats: a time-series database used as a key-value store — no constraints, no joins, "current
value" means "latest point", which is a poor fit for facts that aren't time-varying; querying
it alongside real series is awkward in both SQL and Grafana.

### Option 4 — Keep reading `experiments.json` at query time
Advantages: zero infrastructure; the file is already the source of truth and is version
controlled.
Caveats: Grafana cannot read a local JSON file as a datasource, so the experiment selector and
any KPI needing nominal conditions would have to be hardcoded or generated; corrections mean
editing a file under `data/raw/`, which the ground rules forbid.

## Decision

Run PostgreSQL alongside InfluxDB as the store for experiment metadata, loaded from
`experiments.json`.

## Why

Metadata here is corrigible and time-series data is not. Anything written into InfluxDB tags
is effectively immutable in practice — fixing `EXP_005`'s missing `sorbent_batch` would mean
rewriting every point of that experiment, which is an absurd cost for a clerical correction.
Postgres makes that one `UPDATE`. The join semantics reinforce it: the comparison questions in
deliverable F are relational filters over experiment attributes, which is what a relational
database is for and what a TSDB is not. Option 2's cardinality cost seals it — nominal
parameters as tags multiply series count permanently for the convenience of avoiding a join.

The honest counter is that six rows do not need a database, and the answer is that the row
count is not the point: correctable, joinable, nullable rows do, and this is the shape the
metadata has even at pilot scale.

## Consequences

- **No referential integrity across the two stores.** InfluxDB can hold readings for an
  experiment that has no row in Postgres, and nothing will complain. Whatever reconciles them
  is something we build; it belongs with the ingestion checks in M2.
- **Grafana integration runs through template variables, not joins.** A Postgres-backed query
  variable populates the experiment selector and feeds `$experiment` into InfluxDB queries.
  Panels genuinely needing both sources at once require the `-- Mixed --` datasource plus join
  transformations, which is the fallback rather than the plan.
- **Two SQL dialects.** DataFusion SQL and PostgreSQL SQL are close but not identical — much
  closer than Flux would have been, not free.
- A third container in the local stack, and Postgres schema/provisioning becomes M1 scope.
- `experiments.json` stays the immutable source of truth under `data/raw/`; Postgres is loaded
  *from* it and is where corrections land.

**Left open for M1**, as a decision point and not an answer here: which fields, if any, are
duplicated into InfluxDB tags as well as living in Postgres, and the rule for deciding that.

## Assumptions relied on

A-01

## Defense

The time-series data is immutable, but the metadata isn't — two of the six experiments have
null fields that someone will fill in later, and one has no operator recorded. If that metadata
lives in InfluxDB tags, correcting it means rewriting every point of the experiment, and every
extra attribute inflates series cardinality permanently. In Postgres it's an `UPDATE`, and the
comparison questions the brief asks — which runs share a sorbent batch, which are comparable to
the baseline — are relational filters, which is what a relational store does well and a TSDB
does badly. The cost I take on is that nothing enforces referential integrity between the two,
so reconciliation is something I build into ingestion rather than something the database gives
me.
