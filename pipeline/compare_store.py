"""Read layer of the M5 comparison (decisions 4, 5 and 21 of M5): InfluxDB and Postgres reads.

Nothing here computes anything and nothing here writes: M5 is read-only against both stores.

InfluxDB (`CompareGateway`)
- Extends `MetricsGateway`, which already reads accepted series, counts and policy rows, and
  keeps its `tables`, `has_policy_rows`, `accepted_series` and `close`. It adds four reads and
  defines no write method of its own (the inherited `write` is never called by it).
- Every read is bounded to one experiment's window `[start, end)` (Core 3.11.2 cannot answer a
  query that spans about 72 h), and uses the SQL that the M2.5 profiling found safe (ADR-0014):
  no `COUNT(*) FILTER`, no `PERCENTILE_CONT`, no equality on a float. Rows are sorted by `ORDER
  BY time`; no value is compared in SQL.
- An empty or inverted window (`end <= start`) reads as empty without a query: Core refuses a
  time filter that has no valid boundaries.
- A table or column that was never written (for example `value` after a run where every reading
  was excluded) reads as an empty result, not an error.
- A read on a database that does not exist fails with `QueryFailed`. `require_database` gives the
  clean refusal first: it raises `DatabaseMissing` after one HTTP listing, so a caller can refuse
  before the first query. No call here can create a database.

Postgres
- `experiment_rows` and `experiment_metric_rows` read `experiment` and `experiment_metrics`
  (migrations 0001 and 0003) over a connection from `pipeline.metrics_store.pg_connect`; use
  `pg_check` on that connection first to refuse a schema without migration 0003.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import psycopg
import pyarrow as pa

from pipeline.cleaning_influx import (
    PROCESSED_TABLE,
    STATE_INTERVALS_TABLE,
    WINDOW,
    window_params,
)
from pipeline.metrics_store import (
    ACCEPTED,
    METRICS_TABLE,
    SERIES_TABLE,
    DatabaseMissing,
    MetricsGateway,
    pg_check,
    pg_connect,
)

__all__ = [
    "CompareGateway",
    "DatabaseMissing",
    "experiment_metric_rows",
    "experiment_rows",
    "pg_check",
    "pg_connect",
]

_TIME_COLUMNS = ("start_time", "end_time")


class CompareGateway(MetricsGateway):
    """Read-only view of one database for the comparison (see the module docstring)."""

    def require_database(self) -> None:
        """Raise `DatabaseMissing` when the database does not exist (one HTTP listing).

        This only lists databases; it never creates one.
        """
        self._require_database()

    def raw_series(
        self, experiment_id: str, signal: str, start: datetime, end: datetime, policy_version: str
    ) -> list[tuple[int, float | None]]:
        """`(time_ns, value_raw)` of every `readings_processed` row of one signal and one policy
        version, ascending: accepted and excluded rows alike. `None` where the row has no raw
        value (a reading that arrived without one).
        """
        if end <= start or not self.has_column(PROCESSED_TABLE, "value_raw"):
            return []  # no row of the table ever carried a raw value
        sql = (
            f"SELECT time, value_raw FROM {PROCESSED_TABLE} "  # noqa: S608 - fixed table name
            f"WHERE {WINDOW} AND signal = $sig AND policy_version = $pv ORDER BY time"
        )
        params = {**window_params(experiment_id, start, end), "sig": signal, "pv": policy_version}
        result = self._table(f"raw:{experiment_id}/{signal}", sql, params)
        times = result.column("time").cast(pa.int64()).to_pylist()
        values = result.column("value_raw").to_pylist()
        return [(t, None if v is None else float(v)) for t, v in zip(times, values, strict=True)]

    def state_events(
        self, experiment_id: str, signal: str, start: datetime, end: datetime, policy_version: str
    ) -> list[tuple[int, int, str]]:
        """`(time_ns, end_ns, value)` of the accepted `state_intervals` rows of one state signal
        and one policy version, ascending. The phase is `[time, end_ns)`.

        Only rows whose verdict is `accepted` count (a row accepted earlier and excluded later
        keeps its old `value` on Core, so the verdict decides, as in `accepted_series`).
        """
        if end <= start or not (
            self.has_column(STATE_INTERVALS_TABLE, "value")
            and self.has_column(STATE_INTERVALS_TABLE, "end_ns")
        ):
            return []
        sql = (
            f"SELECT time, end_ns, value FROM {STATE_INTERVALS_TABLE} "  # noqa: S608 - fixed name
            f"WHERE {WINDOW} AND signal = $sig AND policy_version = $pv "
            f"AND verdict = '{ACCEPTED}' AND value IS NOT NULL ORDER BY time"
        )
        params = {**window_params(experiment_id, start, end), "sig": signal, "pv": policy_version}
        result = self._table(f"events:{experiment_id}/{signal}", sql, params)
        times = result.column("time").cast(pa.int64()).to_pylist()
        ends = result.column("end_ns").to_pylist()
        values = result.column("value").to_pylist()
        return [(t, int(e), str(v)) for t, e, v in zip(times, ends, values, strict=True)]

    def metric_series(
        self,
        experiment_id: str,
        metric: str,
        metrics_version: str,
        policy_version: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[int, float]]:
        """`(time_ns, value)` of one `metrics_series` series for one metrics version AND one
        policy version, ascending.
        """
        if end <= start or not self.has_column(SERIES_TABLE, "value"):
            return []
        sql = (
            f"SELECT time, value FROM {SERIES_TABLE} "  # noqa: S608 - fixed table name
            f"WHERE {WINDOW} AND metric = $metric AND metrics_version = $mv "
            "AND policy_version = $pv AND value IS NOT NULL ORDER BY time"
        )
        params = {
            **window_params(experiment_id, start, end),
            "metric": metric,
            "mv": metrics_version,
            "pv": policy_version,
        }
        result = self._table(f"metric:{experiment_id}/{metric}", sql, params)
        times = result.column("time").cast(pa.int64()).to_pylist()
        values = result.column("value").to_pylist()
        return [(t, float(v)) for t, v in zip(times, values, strict=True)]

    def has_metrics_rows(self, metrics_version: str, policy_version: str) -> bool:
        """True when `metrics_series` holds at least one row of this metrics and policy version."""
        if SERIES_TABLE not in self.tables():
            return False
        sql = (
            f"SELECT 1 AS found FROM {SERIES_TABLE} "  # noqa: S608 - fixed table name
            "WHERE metrics_version = $mv AND policy_version = $pv LIMIT 1"
        )
        result = self._table("metrics_rows", sql, {"mv": metrics_version, "pv": policy_version})
        return result.num_rows > 0


# ----------------------------------------------------------------------------------- Postgres


def experiment_rows(conn: psycopg.Connection, ids: Sequence[str]) -> dict[str, dict]:
    """`experiment_id -> {column: value}` for every asked id that has a row in `experiment`.

    Every column of the table is returned, nulls as `None`; `start_time` and `end_time` are
    timezone-aware UTC datetimes whatever the session's time zone is. An id with no row is left
    out (the caller refuses).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM experiment WHERE experiment_id = ANY(%s)", (list(ids),))
        names = [column.name for column in cur.description]
        fetched = cur.fetchall()
    rows: dict[str, dict] = {}
    for values in fetched:
        row = dict(zip(names, values, strict=True))
        for name in _TIME_COLUMNS:
            if row.get(name) is not None:
                row[name] = row[name].astimezone(UTC)
        rows[row["experiment_id"]] = row
    return rows


def experiment_metric_rows(
    conn: psycopg.Connection, metrics_version: str, ids: Sequence[str]
) -> dict[str, dict[str, dict]]:
    """`experiment_id -> metric -> {value, unit, coverage, status}` of one metrics version.

    Only the asked ids that have rows appear; nulls stay `None`.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT experiment_id, metric, value, unit, coverage, status "
            f"FROM {METRICS_TABLE} WHERE metrics_version = %s AND experiment_id = ANY(%s) "
            "ORDER BY experiment_id, metric",  # noqa: S608 - fixed table name
            (metrics_version, list(ids)),
        )
        fetched = cur.fetchall()
    rows: dict[str, dict[str, dict]] = {}
    for experiment_id, metric, value, unit, coverage, status in fetched:
        rows.setdefault(experiment_id, {})[metric] = {
            "value": value,
            "unit": unit,
            "coverage": coverage,
            "status": status,
        }
    return rows
