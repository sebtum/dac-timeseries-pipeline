"""Rollup driver: `readings_processed` -> `pipeline.rollup.compute_rollup` -> `dac_rollup`.

The thin half of the rollup (M1 plan T8/T9, reworked at M3, decision 18). Everything
interesting - the aggregation math - lives in `pipeline/rollup.py` and is unit-tested there
with no I/O. This module only queries, buckets, calls that function, and writes. It contains
no scheduling and no trigger registration: the rollup is a separate command run after
cleaning (`python -m scripts.rollup`); how often it runs is a later concern (H).

**Source (M3):** the `readings_processed` table of the raw database, not `readings_numeric`.
Only rows of **one policy version** are read (`policy_version` tag = the cleaning version),
so rows left by an older rule set are never mixed in. The inclusion predicate is the cleaning
verdict: a point is included when `verdict = 'accepted'`. A point without `value_raw` (the raw
reading was empty) is counted in `count_no_value` and never crashes the run
(`pipeline/rollup.py` documents how each column treats it). `readings_state` and
`state_intervals` are never rolled up (ADR-0011: an empty bucket means "no change", not "no data").

**One experiment window at a time:** `run_rollup` takes one `[start, end)` and one
`experiment_id`; the CLI loops over the windows of `experiments.json` (each about 2 h, far below
Core's single-query limit).

**Memory shape, per row group above the pure function (E-03, MISTAKES.md - a streaming claim
has to hold at every stage, not just the overall shape):**
- The query is read with `mode="reader"`, a genuine Arrow `RecordBatchReader`, not
  `mode="all"` which materializes the entire result before returning it.
- The query is `ORDER BY time`, and a 1-minute bucket floor is a non-decreasing step function
  of time - so as rows arrive in order, at most **one bucket-minute is ever open at once**
  across every `(experiment_id, source, signal)` series combined. That count is bounded by the
  measured series cardinality (ADR-0006), not by the number of rows in `[start, end)`.
- Buckets are flushed - aggregated via `compute_rollup` and written - the moment the bucket
  boundary advances.

Aggregation is done in Python on a plain SELECT pull, not in SQL: Core 3.11.2 sums differ in
the last bits between runs and `PERCENTILE_CONT` is only about 7 digits accurate (ADR-0014).

**Re-runs.** Each written point's tag set (`experiment_id`, `source`, `signal`) plus its
timestamp (the bucket's floored start) is the key InfluxDB deduplicates on, last write wins (the
same mechanism C-05 established for idempotent ingest). Re-running over unchanged
`readings_processed` rows of the same policy version writes the same values, so nothing
duplicates and nothing changes.

**Known limit (measured on Core, M3 execute log; parked in Spec Next steps):** a later write of
the same key *without* a field keeps the old field value, and a point cannot carry a null field.
So if the rows of a bucket under the *same* policy version changed so that its `count_included`
drops to 0 (or `min_all`/`max_all` become absent), a re-run would write the new counts but leave
the old `mean`/`std`/`median` (or `min_all`/`max_all`) in place. The design avoids this
by construction rather than by code: cleaning is deterministic and any rule change must bump
`POLICY_VERSION`, so the rows of one policy version never change after they are written, and
the bucket's counts always agree with its stored statistics. Consumers should read `mean` /
`std` / `median` only where `count_included > 0`. `tests/integration/test_rollup_run.py` pins
what the code does today: a bucket with no included point on first write has no `mean`/`std`/
`median`; a bucket without a raw value at all has no `min_all`/`max_all`.

The query is bounded to one experiment window, so Core's single-query span limit (U-05,
ADR-0004) cannot be hit by a normal run. A query or write error is wrapped in `RollupFailed`
(the CLI exits 3 on it); nothing is retried or truncated.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from influxdb_client_3 import InfluxDBClient3, Point

from pipeline.rollup import InclusionPredicate, RollupRow, Sample, compute_rollup

ROLLUP_MEASUREMENT = "readings_rollup"
PROCESSED_MEASUREMENT = "readings_processed"
ACCEPTED = "accepted"
BUCKET_WIDTH = timedelta(minutes=1)

_PROCESSED_QUERY = (
    "SELECT experiment_id, source, signal, time, value_raw, quality, verdict "
    f"FROM {PROCESSED_MEASUREMENT} "  # noqa: S608 - fixed table name, no user input
    "WHERE experiment_id = $experiment_id AND policy_version = $policy_version "
    "AND time >= $start AND time < $end "
    "ORDER BY time"
)

_ProcessedRow = tuple[str, str, str, datetime, float | None, str, str | None]


class RollupFailed(Exception):
    """A query or a write failed; `stage` is `"query"` or `"write"`."""

    def __init__(self, stage: str, cause: BaseException) -> None:
        super().__init__(f"rollup {stage} failed: {cause}")
        self.stage = stage
        self.cause = cause


@dataclass(frozen=True)
class SeriesBucketKey:
    """One `(experiment_id, source, signal, bucket_start)` group - the unit
    `compute_rollup` aggregates and `run_rollup` writes one point for.
    """

    experiment_id: str
    source: str
    signal: str
    bucket_start: datetime


def is_accepted(sample: Sample) -> bool:
    """The M3 inclusion predicate: the cleaning verdict is `accepted`."""
    return sample.verdict == ACCEPTED


def _floor_to_bucket(ts: datetime) -> datetime:
    """Floor a timestamp to its 1-minute bucket start (ADR-0011: 1-minute buckets)."""
    return ts.replace(second=0, microsecond=0)


def _iter_processed_rows(
    client: InfluxDBClient3,
    experiment_id: str,
    policy_version: str,
    start: datetime,
    end: datetime,
) -> Iterator[_ProcessedRow]:
    """Yield `(experiment_id, source, signal, time, value_raw, quality, verdict)` rows of one
    experiment and one policy version in `[start, end)`, ordered by time, one Arrow record
    batch at a time. `value_raw` is `None` for a point with no value.

    `mode="reader"` is what makes this streaming: each `batch.column(...).to_pylist()` call
    below converts only that batch, never the full result set.
    """
    try:
        reader = client.query(
            _PROCESSED_QUERY,
            language="sql",
            mode="reader",
            # query_parameters is JSON-encoded by the client before it reaches Flight SQL, so a
            # datetime has to be passed as its ISO-8601 string, not the object itself.
            query_parameters={
                "experiment_id": experiment_id,
                "policy_version": policy_version,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        for batch in reader:
            experiment_ids = batch.column("experiment_id").to_pylist()
            sources = batch.column("source").to_pylist()
            signals = batch.column("signal").to_pylist()
            times = batch.column("time").to_pylist()
            values = batch.column("value_raw").to_pylist()
            qualities = batch.column("quality").to_pylist()
            verdicts = batch.column("verdict").to_pylist()
            yield from zip(
                experiment_ids, sources, signals, times, values, qualities, verdicts, strict=True
            )
    except Exception as exc:
        raise RollupFailed("query", exc) from exc


def _row_to_point(key: SeriesBucketKey, row: RollupRow) -> Point:
    """`mean`/`std`/`median` are `None` when no sample of the bucket is included, and
    `min_all`/`max_all` are `None` when no point of it has a raw value. `Point.field(name,
    None)` silently drops the field from the point rather than writing a sentinel - verified
    directly (`p.field("y", None)` produces no `y=...` in the line protocol) rather than
    assumed, so this passes them through unconditionally instead of branching.

    Consequence worth knowing: a column that has *never* been written for this measurement is
    not just null, it does not exist in the table's schema at all - `SELECT mean FROM
    readings_rollup` raises a schema error rather than returning nulls if no row in the
    table's whole history ever had an included sample. Only bites if the *entire* table never
    once wrote the field; a real `dac_rollup` with any accepted data anywhere is unaffected.
    See the module docstring for the stale-field limit on re-runs.
    """
    return (
        Point(ROLLUP_MEASUREMENT)
        .tag("experiment_id", key.experiment_id)
        .tag("source", key.source)
        .tag("signal", key.signal)
        .field("count_all", row.count_all)
        .field("min_all", row.min_all)
        .field("max_all", row.max_all)
        .field("sum_all", row.sum_all)
        .field("sumsq_all", row.sumsq_all)
        .field("count_no_value", row.count_no_value)
        .field("count_included", row.count_included)
        .field("mean", row.mean)
        .field("std", row.std)
        .field("median", row.median)
        .field("count_good", row.count_good)
        .field("count_uncertain", row.count_uncertain)
        .field("count_bad", row.count_bad)
        .field("policy_version", row.policy_version)
        .time(key.bucket_start)
    )


def _flush(
    open_buckets: dict[SeriesBucketKey, list[Sample]],
    include: InclusionPredicate,
    policy_version: str,
    rollup_client: InfluxDBClient3,
) -> int:
    """Aggregate and write every currently-open bucket, then clear them.

    Called every time the bucket boundary advances, not once at the end - the point of the
    whole design is that `open_buckets` never holds more than one minute's worth of series at
    a time.
    """
    if not open_buckets:
        return 0
    points = [
        _row_to_point(key, compute_rollup(samples, include, policy_version))
        for key, samples in open_buckets.items()
    ]
    try:
        rollup_client.write(record=points)
    except Exception as exc:
        raise RollupFailed("write", exc) from exc
    open_buckets.clear()
    return len(points)


def run_rollup(
    raw_client: InfluxDBClient3,
    rollup_client: InfluxDBClient3,
    start: datetime,
    end: datetime,
    policy_version: str,
    *,
    experiment_id: str,
    include: InclusionPredicate = is_accepted,
) -> int:
    """Roll up the `readings_processed` rows of one experiment and one policy version in
    `[start, end)` from `raw_client`'s database into 1-minute buckets, writing them to
    `rollup_client`'s database.

    Returns the number of buckets written. Raises `RollupFailed` on a query or write error.
    Two separate clients are required because `InfluxDBClient3` binds to one database at
    construction and raw/rollup are necessarily different databases (ADR-0011: retention is
    per-database).
    """
    open_buckets: dict[SeriesBucketKey, list[Sample]] = {}
    current_bucket_start: datetime | None = None
    written = 0

    rows = _iter_processed_rows(raw_client, experiment_id, policy_version, start, end)
    for exp_id, source, signal, ts, value_raw, quality, verdict in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        bucket_start = _floor_to_bucket(ts)

        if current_bucket_start is not None and bucket_start != current_bucket_start:
            written += _flush(open_buckets, include, policy_version, rollup_client)
        current_bucket_start = bucket_start

        key = SeriesBucketKey(exp_id, source, signal, bucket_start)
        open_buckets.setdefault(key, []).append(
            Sample(timestamp=ts, value=value_raw, quality=quality, verdict=verdict)
        )

    written += _flush(open_buckets, include, policy_version, rollup_client)
    return written
