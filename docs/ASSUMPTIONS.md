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
| U-06 | How the Python pipeline handles data that outgrows RAM — chunking, per-experiment processing, or pushing aggregation into the database. | no (not at 520k rows), but it is the most predictable debrief challenge | Decide the strategy, then demonstrate it on a chunked run even though the sample doesn't require one. | open (created by ADR-0003) |
