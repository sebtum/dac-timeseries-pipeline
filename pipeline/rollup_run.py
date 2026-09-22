"""Rollup driver: `dac_raw` -> `pipeline.rollup.compute_rollup` -> `dac_rollup`.

The thin half of the rollup U-04 splits in two (docs/plans/M1.md T8/T9). Everything
interesting — the aggregation math, the quality-policy handling — lives in
`pipeline/rollup.py` and is unit-tested there with no I/O. This module only queries,
buckets, calls that function, and writes. It contains no scheduling, no trigger
registration, no cron wiring: **who calls `run_rollup` and how often is U-04, still
open, deferred to M3** (docs/plans/M1.md, "Three calls made in this phase").

Only `readings_numeric` is read — `readings_state` is never rolled up (ADR-0011,
Decision: event-based signals, an empty bucket means "no change", not "no data").

**Memory shape, per row group above the pure function (E-03, MISTAKES.md — a
streaming claim has to hold at every stage, not just the overall shape):**
- The raw query is read with `mode="reader"`, a genuine Arrow `RecordBatchReader`,
  not `mode="all"` which materializes the entire result before returning it.
- The query is `ORDER BY time`, and a 1-minute bucket floor is a non-decreasing step
  function of time — so as rows arrive in order, at most **one bucket-minute is ever
  open at once** across every `(experiment_id, source, signal)` series combined. That
  count is bounded by the measured 150-series cardinality (ADR-0006), not by the
  number of rows in `[start, end)`.
- Buckets are flushed — aggregated via `compute_rollup` and written — the moment the
  bucket boundary advances, so a range spanning months of data never holds more than
  one minute's worth of samples, nor accumulates every output point before writing.

Re-running `run_rollup` over the same `[start, end)` range does not duplicate rows.
Each written point's tag set (`experiment_id`, `source`, `signal`) plus its timestamp
(the bucket's floored start) is exactly the key InfluxDB deduplicates on
last-write-wins — the same mechanism C-05 (MISTAKES.md) established as a guarantee for
idempotent ingest is reused here for idempotent re-rollup, not rebuilt.

At M1 the inclusion predicate is a stated placeholder (`quality == 'GOOD'`); the
`policy_version` passed through to every written row is what keeps that placeholder
from being silently read later as M3's real verdict (ADR-0011, Why).

Core's single-query span limit (U-05, ADR-0004) is not pre-checked here — the ~72h
figure is stated as approximate, not verified against this build. If a range is too
wide, the query raises during iteration and that error is left to propagate unchanged
rather than caught and silently retried or truncated.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from influxdb_client_3 import InfluxDBClient3, Point

from pipeline.rollup import InclusionPredicate, RollupRow, Sample, compute_rollup

ROLLUP_MEASUREMENT = "readings_rollup"
RAW_MEASUREMENT = "readings_numeric"
BUCKET_WIDTH = timedelta(minutes=1)

_RAW_QUERY = (
    f"SELECT experiment_id, source, signal, time, value, quality "  # noqa: S608 - fixed table name, no user input
    f"FROM {RAW_MEASUREMENT} "
    f"WHERE time >= $start AND time < $end "
    f"ORDER BY time"
)

_RawRow = tuple[str, str, str, datetime, float, str]


@dataclass(frozen=True)
class SeriesBucketKey:
    """One `(experiment_id, source, signal, bucket_start)` group — the unit
    `compute_rollup` aggregates and `run_rollup` writes one point for.
    """

    experiment_id: str
    source: str
    signal: str
    bucket_start: datetime


def _floor_to_bucket(ts: datetime) -> datetime:
    """Floor a timestamp to its 1-minute bucket start (ADR-0011: 1-minute buckets)."""
    return ts.replace(second=0, microsecond=0)


def _iter_raw_rows(client: InfluxDBClient3, start: datetime, end: datetime) -> Iterator[_RawRow]:
    """Yield `(experiment_id, source, signal, time, value, quality)` rows in
    `[start, end)`, ordered by time, one Arrow record batch at a time.

    `mode="reader"` is what makes this streaming: each `batch.column(...).to_pylist()`
    call below converts only that batch, never the full result set, however wide
    `[start, end)` is.
    """
    reader = client.query(
        _RAW_QUERY,
        language="sql",
        mode="reader",
        # query_parameters is JSON-encoded by the client before it reaches Flight SQL,
        # so a datetime has to be passed as its ISO-8601 string, not the object itself.
        query_parameters={"start": start.isoformat(), "end": end.isoformat()},
    )
    for batch in reader:
        experiment_ids = batch.column("experiment_id").to_pylist()
        sources = batch.column("source").to_pylist()
        signals = batch.column("signal").to_pylist()
        times = batch.column("time").to_pylist()
        values = batch.column("value").to_pylist()
        qualities = batch.column("quality").to_pylist()
        yield from zip(experiment_ids, sources, signals, times, values, qualities, strict=True)


def _row_to_point(key: SeriesBucketKey, row: RollupRow) -> Point:
    """`mean`/`std`/`median` are `None` when every sample in the bucket is excluded
    (ADR-0011: verdict-dependent columns null in that case). `Point.field(name, None)`
    silently drops the field from the point rather than writing a sentinel — verified
    directly (`p.field("y", None)` produces no `y=...` in the line protocol) rather
    than assumed, so this passes them through unconditionally instead of branching.

    Consequence worth knowing (found writing T9's test, not in any ADR): a column
    that has *never* been written for this measurement isn't just null, it does not
    exist in the table's schema at all — `SELECT mean FROM readings_rollup` raises a
    schema error rather than returning nulls if no row in the table's whole history
    ever had an included sample. Only bites if the *entire* table never once wrote
    the field; a real `dac_rollup` with any GOOD data anywhere is unaffected.
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

    Called every time the bucket boundary advances, not once at the end — the point
    of the whole design is that `open_buckets` never holds more than one minute's
    worth of series at a time.
    """
    if not open_buckets:
        return 0
    points = [
        _row_to_point(key, compute_rollup(samples, include, policy_version))
        for key, samples in open_buckets.items()
    ]
    rollup_client.write(record=points)
    open_buckets.clear()
    return len(points)


def run_rollup(
    raw_client: InfluxDBClient3,
    rollup_client: InfluxDBClient3,
    start: datetime,
    end: datetime,
    include: InclusionPredicate,
    policy_version: str,
) -> int:
    """Roll up `readings_numeric` samples in `[start, end)` from `raw_client`'s
    database into 1-minute buckets, writing them to `rollup_client`'s database.

    Returns the number of buckets written. Two separate clients are required
    because `InfluxDBClient3` binds to one database at construction and raw/rollup
    are necessarily different databases (ADR-0011: retention is per-database).
    """
    open_buckets: dict[SeriesBucketKey, list[Sample]] = {}
    current_bucket_start: datetime | None = None
    written = 0

    for experiment_id, source, signal, ts, value, quality in _iter_raw_rows(raw_client, start, end):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        bucket_start = _floor_to_bucket(ts)

        if current_bucket_start is not None and bucket_start != current_bucket_start:
            written += _flush(open_buckets, include, policy_version, rollup_client)
        current_bucket_start = bucket_start

        key = SeriesBucketKey(experiment_id, source, signal, bucket_start)
        open_buckets.setdefault(key, []).append(Sample(timestamp=ts, value=value, quality=quality))

    written += _flush(open_buckets, include, policy_version, rollup_client)
    return written
