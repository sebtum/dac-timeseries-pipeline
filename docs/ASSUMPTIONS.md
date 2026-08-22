# Assumptions & open unknowns

Two registers. An **assumption** is something we're treating as true without having proved
it. An **unknown** is something we know we don't know.

Rules:
- Every assumption needs a way it could be shown false. If you can't write that column, it's
  not an assumption, it's a guess — say so.
- An unknown that gets resolved is closed with the fact *and* the evidence.
- An unknown we decide to live with is promoted to an assumption. That conversion is debrief
  material: "here's what I didn't know, and here's what I did about it."
- ADRs cite these by id.

---

## Assumptions

| id | assumption | why we need it | how it would be invalidated | status |
|----|-----------|----------------|-----------------------------|--------|
| A-01 | The exercise is untimed and all of A–J should reach a runnable/clickable state. | Sets milestone scope; `README.md` still says 60 minutes. | Sebastian re-imposes a clock. | held (source: commit `3693904`) |
| A-02 | InfluxDB 3 **Core** is adequate, rather than the free-for-at-home Enterprise build. | ADR-0004; Core lacks historical query capability, single-series indexing and Enterprise's query-time retention enforcement. | The ~72h query span makes the multi-experiment overlay unworkable (U-05), or the retention story can't be demonstrated on Core. | held |

## Open unknowns

| id | what I don't know | blocks? | how I'd find out | status |
|----|-------------------|---------|------------------|--------|
| U-01 | Whether timestamps across the four sources share a timezone convention. | blocks M2 | Compare per-source timestamp distributions against `experiments.json` start/end times. | open (flagged by `task/DATA_DICTIONARY.md`) |
| U-02 | What CI runs against: the raw CSV is gitignored, so a runner has no dataset unless it regenerates it, or a committed fixture slice is provided, or data-dependent tests stay local. | blocks the M0 CI increment | Decide in M0 Discuss; time the generator to see whether regenerating in CI is even viable. | open |
| U-03 | Whether any requirement in this project actually calls for a relational store. | no | Falls out of M1, when experiment metadata gets a home. | **resolved** — yes: experiment metadata is mutable (three of six experiments have null fields that get filled in later) and metadata in Influx tags can't be corrected without rewriting every point. Resolution: ADR-0005. |
| U-04 | How downsampling is actually implemented on InfluxDB 3 Core — a Processing Engine Python plugin, or an external scheduled job. | blocks M1 | Prototype both against one experiment; compare operational cost and testability. | open (created by ADR-0004) |
| U-05 | Whether the six-experiment overlay can be served within Core's ~72h single-query span, or needs one query per experiment, or a raised Parquet file limit. | blocks M5, M6 | Load two experiments months apart and try the overlay query both ways. | open (created by ADR-0004) |
| U-06 | How the Python pipeline handles data that outgrows RAM — chunking, per-experiment processing, or pushing aggregation into the database. | no (not at 520k rows), but it is the most predictable debrief challenge | Decide the strategy, then demonstrate it on a chunked run even though the sample doesn't require one. | open (created by ADR-0003) — **partially answered** for the duplicate-detection step by ADR-0007: sorting by series key then time makes duplicates adjacent, so detection is O(1) in memory rather than O(rows). The general pipeline question stands. |
| U-07 | The win-policy for conflicting duplicates — which of two readings claiming the same instant is kept. | blocks M2 | Run the M0 duplicate census first: the counts of exact vs conflicting collisions, and whether the conflicting pairs differ in `quality`, determine whether a quality-preference rule is even applicable. | open (created by ADR-0007). **Constrained, not free:** ADR-0007 requires the rule be content-based, since encounter-order rules stop being deterministic under parallel or streaming ingest. |
| U-08 | The definition of "same" when comparing two values for the exact-vs-conflicting duplicate split — raw CSV text or parsed float, and with what tolerance. | blocks M2 | Extract the actual colliding pairs in the M0 census and inspect them: if collisions are byte-identical in the source text, the question is moot. | open (created by ADR-0007). Both errors are silent: exact equality misclassifies round-tripped identical readings as conflicts; a tolerance misclassifies genuinely different readings as duplicates. |
| U-09 | Where processed values, pipeline quality verdicts and exclusion reasons live — extra columns on the readings tables, separate `*_clean` tables, or computed at query time. A second, independent axis from the numeric/state split in ADR-0006. | blocks M3 | Falls out of M3 Discuss, once the per-signal handling policy exists and the shape of a "reason" is known. | open (created by ADR-0006) |
| U-10 | Whether `quality` stays a dense field on every reading or becomes a sparse exceptions table where absence means good. | no | The M0 census gives the non-GOOD count per signal (currently 330 of 520,005 overall). Decide with M3, alongside U-09. | open (created by ADR-0006). Note: **not** a storage-size question — Parquet already dictionary- and RLE-encodes a column that is 99.94% one value. Interval/run-length representation earns its place as a *derived* artifact for annotating Grafana, which is M3/M6, not the storage layer. |
| U-11 | Whether conflicting duplicates ever occur on the two categorical signals, and therefore whether `readings_conflicts` needs string columns or a second table. | blocks M2 | The M0 duplicate census, broken down by signal. | open (created by ADR-0007) |
| U-12 | Whether the M3 cleaning pipeline reads from InfluxDB or re-reads the raw CSV. Determines whether ingestion is a one-shot bootstrap or a component the rest of the system depends on, and what "raw preserved unchanged" means operationally. | blocks M3 | Decide with U-09 in M3 Discuss; the answer partly falls out of whether processed data lands in the same store. | open |
