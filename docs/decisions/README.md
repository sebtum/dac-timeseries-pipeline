# Architecture decision records

One ADR per **decision**, not per milestone — M1 alone will likely produce several. If two
things could plausibly have been decided differently and independently of each other, they're
two ADRs.

Filename: `ADR-nnnn-<kebab-slug>.md`, numbered in the order decisions are *made*.

A decision is worth an ADR if changing it later would mean reworking code or re-running the
pipeline. Trivia (variable naming, file layout) is not.

## Index

| ADR | Decision | M | Deliverable | Status |
|-----|----------|---|-------------|--------|
| [0000](ADR-0000-record-decisions.md) | Keep ADRs for this exercise | — | — | Accepted |
| [0001](ADR-0001-influxdb-timeseries-store.md) | InfluxDB as the time-series store | — | A, B | Given (constraint) |
| [0002](ADR-0002-grafana-visualisation.md) | Grafana as the visualisation layer | — | G | Given (constraint) |
| [0003](ADR-0003-python-pipeline-language.md) | Python for ingestion and processing | — | B–F | Accepted ⚠ |
| [0004](ADR-0004-influxdb3-core-sql.md) | InfluxDB 3 Core, queried with SQL | M0 | A, B | Accepted |
| [0005](ADR-0005-postgres-experiment-metadata.md) | PostgreSQL for experiment metadata | M1 | A, F | Accepted |
| [0006](ADR-0006-timeseries-data-model.md) | Tags, fields, and the numeric/state table split | M1 | A | Accepted |
| [0007](ADR-0007-duplicate-resolution-idempotency.md) | Same-timestamp duplicate resolution and ingest idempotency | M2 | B, C | Accepted |

⚠ ADR-0003 carries one unresolved item: the rebuttal to the memory-scaling challenge (U-06).
The decision stands; the defence is incomplete.

Note that 0001 and 0004 split deliberately: the brief imposed *InfluxDB*, but *which version,
queried in which language* was our choice, and the versions differ enough that conflating them
caused a factual error — see ADR-0001's debrief answer.

0006 and 0007 split for the same reason: 0006 decides what a point *is*, 0007 decides what
happens when two points claim the same instant. Either could have been decided differently
without forcing the other, and 0007 exists precisely because 0006's "store raw, unchanged" is
necessary but not sufficient — InfluxDB will still discard a duplicate silently.

**Pending, to be added by Sebastian:**
- Docker / local runtime — currently an open M0 decision point, so not yet an ADR.

## Status values

- `Proposed` — decided in Discuss, not yet defended in writing.
- `Accepted` — chosen by us, with the reasoning written down.
- `Given (constraint)` — imposed by the brief, not chosen. Still needs a defence: "it was in
  the brief" is not an answer an interviewer accepts. Never let the record imply you chose
  something that was handed to you.
- `Superseded by ADR-nnnn` — reversed later. The old file stays.

---

## Template

```markdown
# ADR-nnnn — <decision>

Status: Proposed | Accepted | Superseded by ADR-nnnn
Milestone: M#   Deliverable: <letter>   Date: YYYY-MM-DD

## Context
What forced a decision. The facts from the data that constrain it — with the query or the
number, not "the data seemed noisy".

## Options considered
### Option 1 — <name>
Advantages: …
Caveats: …
### Option 2 — <name>
Advantages: …
Caveats: …

## Decision
What we chose, in one sentence.

## Why
Why this beat the alternatives *for this problem*. Not generic praise of the option — the
specific property of this dataset or this requirement that tipped it.

## Consequences
What this makes easy. What it makes hard. What it forecloses.

## Assumptions relied on
A-nn, A-nn (see ../ASSUMPTIONS.md)

## Debrief answer
2–4 sentences: how to defend this out loud when an interviewer pushes back.
```

The **Debrief answer** field is the point of the whole exercise. It is not optional, and it
is not a summary of the Why section — it's the version you'd say under pressure.

## Rules

- Write the ADR when the decision is settled, before or alongside the code — not afterwards
  as documentation of what happened to get built.
- Options that were considered and rejected stay in the record. An ADR with one option is a
  note, not a decision.
- Superseding, not editing: if a decision is reversed later, the old ADR gets
  `Superseded by ADR-nnnn` and stays. Reversals are the most interesting thing in the record.
