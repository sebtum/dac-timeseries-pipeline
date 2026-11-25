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
| [0000](ADR-0000-record-decisions.md) | Keep ADRs for this project | — | — | Accepted |
| [0001](ADR-0001-influxdb-timeseries-store.md) | InfluxDB as the time-series store | — | A, B | Given (constraint) |
| [0002](ADR-0002-grafana-visualisation.md) | Grafana as the visualisation layer | — | G | Given (constraint) |
| [0003](ADR-0003-python-pipeline-language.md) | Python for ingestion and processing | — | B–F | Accepted ⚠ |
| [0004](ADR-0004-influxdb3-core-sql.md) | InfluxDB 3 Core, queried with SQL | M0 | A, B | Accepted |
| [0005](ADR-0005-postgres-experiment-metadata.md) | PostgreSQL for experiment metadata | M1 | A, F | Accepted |
| [0006](ADR-0006-timeseries-data-model.md) | Tags, fields, and the numeric/state table split | M1 | A | Accepted |
| [0007](ADR-0007-duplicate-resolution-idempotency.md) | Same-timestamp duplicate resolution and ingest idempotency | M2 | B, C | Accepted |
| [0008](ADR-0008-local-runtime-docker-compose.md) | Docker Compose, pinned tags, services added progressively | M0 | A, B, G | Accepted ⚠ |
| [0009](ADR-0009-provisioning-as-code.md) | Provisioning as code, per milestone, with three exceptions (addendum: M6 replaces exception 2) | M0 | — | Accepted ⚠ |
| [0010](ADR-0010-profile-post-ingest-in-database.md) | Profile post-ingest in the database; pre-ingest only what the write destroys | M0 | C, D | Accepted |
| [0011](ADR-0011-retention-tiering-rollup.md) | Retention, tiering, and the rollup schema (addendum: M3 rollup over the verdict) | M1 | A | Accepted |
| [0012](ADR-0012-postgres-migrations-metadata-loader.md) | Postgres migrations, and a metadata loader with per-field provenance | M1 | A, F | Accepted |
| [0013](ADR-0013-ingestion.md) | Ingestion: timezone, precision, batching, rejects, conflict winner, exit codes | M2 | B | Accepted |
| [0014](ADR-0014-post-ingest-profiling.md) | Post-ingest profiling: what is measured, SQL versus Python, four engine quirks | M2.5 | C, D | Accepted |
| [0015](ADR-0015-cleaning-and-quality-pipeline.md) | Cleaning and quality pipeline: one verdict per reading beside the raw value, the rules, the rollup over the verdict | M3 | C, D | Accepted |
| [0016](ADR-0016-derived-metrics.md) | Derived metrics: a batch job over accepted readings, labelled by coverage, never filled | M4 | E | Accepted |
| [0017](ADR-0017-comparison-and-findings.md) | Comparison and findings: one clock, block-bootstrap intervals, an evidence rule that can say "not resolved" | M5 | F | Accepted |
| [0018](ADR-0018-grafana-dashboards.md) | Grafana dashboards: committed JSON provisioned read-only, one clock in the query, quality drawn not hidden | M6 | G | Accepted |

⚠ ADR-0003 carries one unresolved item: the rebuttal to the memory-scaling challenge (U-06).
The decision stands; the defence is incomplete.

⚠ ADR-0008 and ADR-0009 each stated one fact about InfluxDB 3 Core's live behaviour that turned
out to be wrong, corrected by T1's spike (`docs/spikes/U-13-core-token-bootstrap.md`,
2026-08-31; MISTAKES.md E-06). ADR-0008 claimed `influxdb:latest` "has pointed at 3 Core since 27
May 2026" — it currently resolves to InfluxDB 2.9.1. ADR-0009 claimed "Core mints its admin token
on first boot" — it does not; the token is created by an explicit non-interactive command
(`influxdb3 create token --admin`), and a second call 409s rather than succeeding idempotently.
Neither decision moves: ADR-0008's tag is pinned to an explicit version regardless of what
`latest` does, and ADR-0009's policy (auth on locally, scripted non-interactive bootstrap into a
gitignored `.env`) is exactly what the corrected mechanism still supports — only the evidence
cited for each was wrong, not the choice it justified.

ADR-0011 carried a warning too: *where* the rollup executes (U-04) was unresolved, because the
stated preference for a Processing Engine plugin conflicted with the decision to aggregate over
M3's verdict. **Resolved 2026-11-23** by M3 (ADR-0015, and an addendum to ADR-0011): the verdict
lands in InfluxDB, and the rollup is an external Python job that reads it. The retention and rollup
design stands; the only change is one added column, `count_no_value`.

Note that 0001 and 0004 split deliberately: the brief imposed *InfluxDB*, but *which version,
queried in which language* was our choice, and the versions differ enough that conflating them
caused a factual error — see ADR-0001's Defense section.

0006 and 0007 split for the same reason: 0006 decides what a point *is*, 0007 decides what
happens when two points claim the same instant. Either could have been decided differently
without forcing the other, and 0007 exists precisely because 0006's "store raw, unchanged" is
necessary but not sufficient — InfluxDB will still discard a duplicate silently.

0008 and 0009 split because the runtime and what configures it are independent: the same compose
file could have been paired with hand-configured databases, and the same as-code policy could have
been applied to native installs. 0010 is a third decision entirely — it changes *where analysis
runs*, not what the stack is, and it was reached by overturning an assumption neither of the
others touched.

0006 and 0011 split along the same seam as 0006/0007: 0006 decides what a point *is*, 0011 decides
how long it lives and what replaces it afterwards. The tag/field layout would be unchanged under
infinite retention, and the tiering would be unchanged had the categorical signals been encoded as
integers — neither forces the other. 0012 is separable again: the metadata store was already chosen
in 0005, and *how its schema arrives and how corrections survive a reload* could have been answered
any number of ways without touching 0005's reasoning. 0015 is separable from 0006 and 0013 for the
same reason: those decide what is stored and how it got there, 0015 decides how each stored reading
is judged, and a different set of rules would not change either. 0016 is separable from 0015 in
turn: 0015 decides which readings are accepted, 0016 decides what is computed from them and how a
hole in them is labelled. 0017 is separable from 0016 again: 0016 decides what is
computed per experiment, 0017 decides how experiments are put side by side, which pairs may be
compared, and what evidence a claim needs. The metrics would be the same under any comparison
rule, and the comparison rule would be the same under another metric formula. 0018 is separable
from 0017 in turn: 0017 decides what is claimed from the runs, 0018 decides how the numbers and the
excluded readings are put in front of a reader. The dashboards would be the same under another
comparison rule, and 0018 also changes one exception of 0009 (dashboards are committed JSON from
the start), which is recorded as an addendum there and not as a new reversal here.

## Status values

- `Proposed` — decided in Discuss, not yet defended in writing.
- `Accepted` — chosen by us, with the reasoning written down.
- `Given (constraint)` — imposed by the brief, not chosen. Still needs a defence: "it was in
  the brief" is not an answer a reviewer accepts. Never let the record imply you chose
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

## Defense
2–4 sentences: how to defend this out loud when a reviewer pushes back.
```

The **Defense** field is the point of writing these down at all. It is not optional, and it
is not a summary of the Why section — it's the version you'd say under pressure.

## Rules

- Write the ADR when the decision is settled, before or alongside the code — not afterwards
  as documentation of what happened to get built.
- Options that were considered and rejected stay in the record. An ADR with one option is a
  note, not a decision.
- Superseding, not editing: if a decision is reversed later, the old ADR gets
  `Superseded by ADR-nnnn` and stays. Reversals are the most interesting thing in the record.
