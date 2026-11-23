# ADR-0013 — Ingestion: what the CSV-to-InfluxDB copy does, and what it refuses to do

Status: Accepted
Milestone: M2   Deliverable: B   Date: 2026-11-23

## Context

ADR-0006 fixed the schema and ADR-0007 fixed how same-instant duplicates are handled. What was
still open for M2 was everything between "a CSV file" and "points in InfluxDB": which timezone
to trust, how finely to store time, how to batch, what to do with a row that cannot be read,
which of two conflicting readings is stored, and how to prove nothing was lost. The nine
choices were made on 2026-11-23 and are written up in plain language in
[`docs/discuss/M2.md`](../discuss/M2.md) (D1-D9). Eleven more came up while planning and
building. This ADR records all of them in one place, with the rejected option each time, so each
one can be defended in review.

Two facts about InfluxDB 3 Core 3.11.2 shaped most of it. Both were observed on the running
container while building M2, not read from documentation (MISTAKES.md E-06):

- **A write to a database that does not exist creates it**, with no retention period, and uses
  one of Core's five slots.
- **`accept_partial`** decides what a batch with one refused line does. With `accept_partial=true`
  on the v3 `write_lp` endpoint the good lines are saved and the bad one is not. With `false` the
  whole batch is refused and nothing is saved. The Python client's default endpoint (v2) is
  all-or-nothing whatever the flag says.

## Decision

| # | Decision | Rejected |
|---|---|---|
| D1 | Trust the offset each timestamp states, store UTC. A timestamp with no offset is rejected (`missing_offset`). Checked against the experiment windows: right for every source in every experiment. | Assume UTC when no offset is given: a silent fix. |
| D2 | Store the exact instant at nanosecond precision. Reject finer than a microsecond (`precision_too_fine`) instead of truncating. | Write in seconds: works today, silently merges two readings the day a file has milliseconds. |
| D3 | Batches of 10,000 lines, sent one at a time, each answered before the next (`write_type=synchronous`, `no_sync=False`). | The client's background mode: failures arrive in callbacks, so "how many were saved" cannot be proved. |
| D4 | A row that cannot be read goes to `ingest_rejects.csv` with its row number and a named reason. The run saves the rest and exits 1. | Stop at the first bad row (loses good data); drop it silently. |
| D5 | Conflict winner: better quality flag, then a present value over an empty one, then the smaller number (or alphabetically first text). Content only, never file order. | "Closest to the neighbours": that is a cleaning judgement and belongs in M3 (C-04). |
| D6 | "Same value" means the same number once read, compared exactly (`250.0` equals `250.00`). Text compares as UTF-8 bytes. | Raw text (calls `250.0` and `250.00` a conflict); a tolerance (merges real differences, and the right tolerance differs per sensor). |
| D7 | `readings_conflicts` stores both readings as text, exactly as the file wrote them: `value_kept_raw`, `value_discarded_raw`. | Float columns: a text signal that conflicts would crash the write, because a column's type is fixed by its first write. |
| D8 | CI tests the ingest on a hand-made 36-row fixture whose answers were counted by hand. | Regenerating the dataset in CI: tests against data whose answers nobody wrote down. |
| D9 | Out-of-order rows are counted in the report and stored normally. | Treating arrival order as a quality flag: it describes transport, not the value. |
| 1 | Ingest never creates a database. It lists databases first and refuses (exit 2) if the target is missing. | Let the write create it. |
| 2 | Saved counts are read back from InfluxDB one experiment at a time, in one-day windows between the first and last instant ingest wrote for it. | One count over March-June: Core limits a single query to about 72 hours. |
| 3 | "Exact copy" means same value and same quality. Same value with a different flag is a conflict (`quality_differs`), because the flag would otherwise be lost. | Compare value only. |
| 4 | One `readings_conflicts` row per discarded reading, with a small tag `discard_rank`. | One row per instant: a group of three would overwrite its own record. Today all 25 groups are pairs. |
| 5 | Text tiebreak is byte order; a present value beats an empty one. | File order. |
| 6 | An empty value is saved as a point with no `value` field (only `quality`). "A row with no value" and "no row" are different defects (C-03); M3 needs to see the first. | Reject it. Today there are 0. |
| 7 | Three more reject reasons: `bad_quality`, `unknown_experiment`, `malformed_row`. | Fold them into other reasons: the win rule needs a known flag and the window check a known experiment. |
| 8 | A reading outside its experiment window is saved, counted, and makes the run exit 1. Window is start inclusive, end exclusive (matches all measured data). | Drop it: that is a cleaning call. |
| 9 | Experiment windows come from `data/raw/experiments.json`, as the retention guard in `scripts/init_influx.py` already does. | Read Postgres: would make ingest need two services. |
| 10 | Exit codes: 0 clean; 1 finished with findings; 2 refused, nothing written; 3 write failed; 4 counts do not balance; 70 internal error (a bug, no summary). | One non-zero code for everything. |
| 11 | Retry only connection errors and server 5xx: 3 retries after 1, 2 and 4 seconds (4 tries). A refused line (4xx) fails at once. | Retry everything: resending a refused line cannot help. |
| 12 | The client is built with `accept_partial=False` on the v3 endpoint (`use_v2_api=False`). Batches are atomic. Confirmed on 3.11.2, see Context. | Trust the documentation. |
| 13 | Fixture line endings are pinned with `.gitattributes` (`tests/fixtures/** -text`), so its SHA-256 holds on Windows and on the Linux runner. | Hope git does not convert them. |
| 14 | The private verify stack is a Python script (`scripts/verify_stack.py`) that runs on Windows and CI. Compose container names are overridable; defaults stay `dac-influxdb` / `dac-postgres`. | A shell script: not portable here. |

### What the counts mean

```
CSV rows = saved + exact copies + conflict losers + rejected        per series, and in total
```

`saved` is **counted back from InfluxDB**, not counted on write. A series is `balanced` only if
that identity holds with the database's number. A retention window that hides points, a write
that was acknowledged but lost, or a leftover point from an older file all show up as an
unbalanced series and exit 4.

### Interpretations that were not spelled out in the brief

- **Out-of-order** uses the census's definition: a row earlier than the previous row of the same
  series in file order (30 on the real file, as in the census). D9 said "earlier than a reading
  already seen", which differs only for sequences like 10:59, 10:23, 10:40.
- **`source_row_kept` / `source_row_discarded`** record file positions, so they swap when two
  conflicting rows swap places. "Identical conflicts rows" for file-order independence therefore
  means identical in every field except those two, which are checked to swap.
- **Rows that cannot be attributed to a series** (wrong column count) are counted under an empty
  series key `("", "", "")`, so the totals still balance. Garbage keys from rejected rows are
  capped at 5,000 distinct series; past that they share the same bucket, so memory cannot grow
  with the number of bad rows.
- **`row_number`** is the data-row number, header excluded, 1-based. A blank line counts as a
  (malformed) row.
- **After a failed write** (exit 3) the summary has `totals: null` and no series: the run never
  reached the count-back, so it claims nothing about balance.

### Memory, stage by stage (E-03)

| Stage | Holds | Bound |
|---|---|---|
| Parse and validate | one row | O(1) |
| Counters (rejects by reason, offsets, window, out-of-order, per series) | a few numbers per series | O(series), 150 real |
| External sort (`pipeline/collisions.sorted_external`) | one chunk of 50,000 rows, then one row per spilled file | O(chunk + files) |
| Group by instant, resolve | one group | O(1) |
| Batch | at most 10,000 lines | O(batch) |
| Rejects file | streamed to disk | O(1) |

## Why

The common thread is that ingest lands data and proves it, and never judges it (C-04). Every
choice above either keeps something the file said (both readings, the empty value, the exact
instant, the offset in the report) or refuses loudly instead of repairing quietly (no offset,
too fine, unknown signal, wrong fingerprint, missing database). Where a choice had to be made
that is arbitrary, such as the smaller number winning, it is content-only so the result cannot
depend on file order (ADR-0007), and every conflict is recorded so M3 can mark the instant
instead of trusting the winner.

## Consequences

- Re-running is safe: the same file gives the same points, because nothing in a point comes from
  the run (ADR-0007). Verified on the real file: a second run left every reading and conflict
  row identical.
- The raw CSV is only read. Its SHA-256 is checked before any write and was re-checked after both
  real runs.
- Cross-run duplicates (the same instant in two different files) are still out of scope.
- Throughput on the real file, native Windows, local Docker: about 7,200 rows per second, 72 s
  for 520,005 rows (about 16 s reading, validating and sorting, about 54 s resolving and
  writing 52 batches, 2 s counting back). Not tuned; batch size 10,000 is a starting value.
- Retention: ingest does not set it. `dac_raw` is created by `scripts/init_influx.py` with
  `INFLUX_RAW_RETENTION` (365 days locally). If a retention window ever hides points, the
  count-back catches it as an unbalanced series.

## Assumptions relied on

U-01, U-02, U-07, U-08, U-11 (all closed by this ADR, see `docs/ASSUMPTIONS.md`).

## Related

ADR-0004 (Core, SQL), ADR-0006 (schema), ADR-0007 (duplicates; addendum records the conflicts
columns), ADR-0011 (retention), MISTAKES.md C-03, C-04, E-03, E-06.

## Defense

Ingest copies the file in and proves the copy. Every row ends up in exactly one of four places
per series: saved, an exact copy of a saved row, a discarded loser in the conflicts table, or the
rejects file, and the saved number is read back from the database, so a lost write cannot hide
behind a count I made myself. The file's SHA-256 is checked before anything is written, and the
database must already exist, because a write to a missing one creates it without retention. I do
not clean: a reading outside its window is stored and flagged, the conflict winner is chosen by
content only and both readings are kept, and an empty value is kept as a point with no value.
Batches are atomic and synchronous, so a refused line fails the batch loudly instead of leaving
a half-written one.
