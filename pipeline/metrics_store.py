"""Storage for the derived metrics (M4, decision 14): InfluxDB reads and `metrics_series` writes,
and the two Postgres summary tables.

Nothing here computes a metric; this module only moves numbers in and out.

InfluxDB (`MetricsGateway`)
- **Reads** accepted readings, the quality counts and the row counts of the input tables. Every
  read is bounded to one window `[start, end)`, as in `pipeline/cleaning_influx.py`. The SQL
  avoids the three Core 3.11.2 quirks found in M2.5 (ADR-0014): no `COUNT(*) FILTER` (counts go
  through `GROUP BY`), no `PERCENTILE_CONT`, no equality on a float.
- **Writes** only `metrics_series`. It never creates a database (a write to a missing database
  creates one, with no retention, using one of Core's five slots), so the existence check runs
  before the first write. The writer is the synchronous, `accept_partial=False` one of
  `pipeline/ingest_influx.py`: a refused line saves nothing of its batch, and a batch that cannot
  be sent after the retries raises `WriteFailed`. Every value is checked before the first byte is
  sent, and a series of up to `BATCH_SIZE` points is one batch, so one `write_series` call is
  all-or-nothing for any real experiment (about 7,200 points per metric). A longer series is sent
  in several batches; a failure then raises, and the rerun overwrites what was saved (same key,
  same value).

Postgres
- `pg_connect` opens an autocommit connection with the given schema as `search_path`; the
  upserts use an explicit transaction, so `write_postgres` keeps both tables or neither.
- Row dicts carry exactly the table's columns (migration 0003). Floats are written as given.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import psycopg
import pyarrow as pa

from pipeline.cleaning_influx import (
    PROCESSED_TABLE,
    QUALITY_INTERVALS_TABLE,
    STATE_INTERVALS_TABLE,
    WINDOW,
    CleaningGateway,
    window_params,
)
from pipeline.ingest import _tag
from pipeline.ingest_influx import list_databases, send_with_retry
from pipeline.signals import CONFLICTS_TABLE, NUMERIC_TABLE, STATE_TABLE

SERIES_TABLE = "metrics_series"
ACCEPTED = "accepted"
BATCH_SIZE = 10_000

# The six tables the metrics read; their row counts must be the same before and after a run.
INPUT_TABLES = (
    NUMERIC_TABLE,
    STATE_TABLE,
    CONFLICTS_TABLE,
    PROCESSED_TABLE,
    STATE_INTERVALS_TABLE,
    QUALITY_INTERVALS_TABLE,
)

# Tables that carry `quality` and `verdict` for every reading (numeric and state signals).
_VERDICT_TABLES = (PROCESSED_TABLE, STATE_INTERVALS_TABLE)


class DatabaseMissing(Exception):
    """The target database does not exist; nothing was written (and none was created)."""

    def __init__(self, database: str) -> None:
        super().__init__(f"database {database!r} does not exist; refusing to write")
        self.database = database


class MetricsGateway(CleaningGateway):
    """Reads the processed tables of one database and writes `metrics_series` into it.

    `host` and `token` are the InfluxDB address and token (from `.env`), `database` the target
    raw database. The database must already exist (`DatabaseMissing` on the first write if not).
    `queries` counts the read queries, like the other gateways.
    """

    def __init__(
        self, host: str, token: str, database: str, *, batch_size: int = BATCH_SIZE
    ) -> None:
        super().__init__(host, token, database)
        self._host = host
        self._token = token
        self.batch_size = batch_size
        self._sleep: Callable[[float], None] = time.sleep
        self._database_checked = False

    # ------------------------------------------------------------------------------- reads

    def accepted_series(
        self, experiment_id: str, signal: str, start: datetime, end: datetime, policy_version: str
    ) -> list[tuple[int, float]]:
        """`(time_ns, value)` of the accepted rows of one signal and one policy version, ascending.

        Only rows whose verdict is `accepted` count. A row that was accepted and later excluded
        keeps its old `value` field on Core (a write without a field keeps the old one), so the
        verdict, not the presence of a value, decides.
        """
        if not self.has_column(PROCESSED_TABLE, "value"):
            return []  # no row of the table ever carried a value
        sql = (
            f"SELECT time, value FROM {PROCESSED_TABLE} "  # noqa: S608 - fixed table name
            f"WHERE {WINDOW} AND signal = $sig AND policy_version = $pv "
            "AND verdict = 'accepted' AND value IS NOT NULL ORDER BY time"
        )
        params = {**window_params(experiment_id, start, end), "sig": signal, "pv": policy_version}
        result = self._table(f"accepted:{experiment_id}/{signal}", sql, params)
        times = result.column("time").cast(pa.int64()).to_pylist()
        values = result.column("value").to_pylist()
        return [(t, float(v)) for t, v in zip(times, values, strict=True)]

    def quality_counts(
        self, experiment_id: str, start: datetime, end: datetime, policy_version: str
    ) -> list[dict]:
        """Rows per `(source, signal, quality, verdict)` from `readings_processed` and
        `state_intervals`, keys `source, signal, quality, verdict, count`; sorted by those four.
        """
        present = self.tables()
        rows: list[dict] = []
        for table in _VERDICT_TABLES:
            if table not in present:
                continue
            sql = (
                f"SELECT source, signal, quality, verdict, COUNT(*) AS n FROM {table} "  # noqa: S608
                f"WHERE {WINDOW} AND policy_version = $pv "
                "GROUP BY source, signal, quality, verdict"
            )
            params = {**window_params(experiment_id, start, end), "pv": policy_version}
            result = self._table(f"quality:{table}", sql, params)
            columns = [
                result.column(name).to_pylist()
                for name in ("source", "signal", "quality", "verdict", "n")
            ]
            rows += [
                {
                    "source": source,
                    "signal": signal,
                    "quality": quality,
                    "verdict": verdict,
                    "count": int(n),
                }
                for source, signal, quality, verdict, n in zip(*columns, strict=True)
            ]
        return sorted(rows, key=lambda r: (r["source"], r["signal"], r["quality"], r["verdict"]))

    def has_policy_rows(self, policy_version: str) -> bool:
        """True when `readings_processed` holds at least one row of this policy version."""
        if PROCESSED_TABLE not in self.tables():
            return False
        sql = (
            f"SELECT 1 AS found FROM {PROCESSED_TABLE} "  # noqa: S608 - fixed table name
            "WHERE policy_version = $pv LIMIT 1"
        )
        result = self._table("policy_rows", sql, {"pv": policy_version})
        return result.num_rows > 0

    def input_counts(self, start: datetime, end: datetime) -> dict[str, int]:
        """Row count of each of the six input tables with `start <= time < end` (0 if missing)."""
        present = self.tables()
        params = {
            "start": start.astimezone(UTC).isoformat(),
            "end": end.astimezone(UTC).isoformat(),
        }
        counts: dict[str, int] = {}
        for table in INPUT_TABLES:
            if table not in present:
                counts[table] = 0
                continue
            sql = (
                f"SELECT COUNT(*) AS n FROM {table} "  # noqa: S608 - fixed table name
                "WHERE time >= $start AND time < $end"
            )
            result = self._table(f"input_count:{table}", sql, params)
            counts[table] = int(result.column("n").to_pylist()[0])
        return counts

    def count_series(
        self, experiment_id: str, metric: str, metrics_version: str, start: datetime, end: datetime
    ) -> int:
        """Points of one `metrics_series` series (any policy version) with `start <= time < end`."""
        if SERIES_TABLE not in self.tables():
            return 0
        sql = (
            f"SELECT COUNT(*) AS n FROM {SERIES_TABLE} "  # noqa: S608 - fixed table name
            f"WHERE {WINDOW} AND metric = $metric AND metrics_version = $mv"
        )
        params = {
            **window_params(experiment_id, start, end),
            "metric": metric,
            "mv": metrics_version,
        }
        result = self._table(f"count_series:{experiment_id}/{metric}", sql, params)
        return int(result.column("n").to_pylist()[0])

    # ------------------------------------------------------------------------------ writes

    def write_series(
        self,
        experiment_id: str,
        metric: str,
        metrics_version: str,
        policy_version: str,
        series: Sequence[tuple[int, float]],
    ) -> int:
        """Write one derived series as `metrics_series` points; returns the number of points.

        Raises `DatabaseMissing` (nothing written, nothing created), `ValueError` (a value that is
        not a finite number or a time that is not an integer; nothing sent), or `WriteFailed`.
        """
        lines = series_lines(experiment_id, metric, metrics_version, policy_version, series)
        if not lines:
            return 0
        self._require_database()
        for first in range(0, len(lines), self.batch_size):
            body = "\n".join(lines[first : first + self.batch_size])
            send_with_retry(self.write, body, sleep=self._sleep)
        return len(lines)

    def _require_database(self) -> None:
        if self._database_checked:
            return
        if self.database not in list_databases(self._host, self._token):
            raise DatabaseMissing(self.database)
        self._database_checked = True


def series_lines(
    experiment_id: str,
    metric: str,
    metrics_version: str,
    policy_version: str,
    series: Sequence[tuple[int, float]],
) -> list[str]:
    """Line protocol for one series, checked as a whole before anything is sent."""
    tags = (
        f"{SERIES_TABLE},experiment_id={_tag(experiment_id)},metric={_tag(metric)},"
        f"metrics_version={_tag(metrics_version)},policy_version={_tag(policy_version)}"
    )
    lines = []
    for time_ns, value in series:
        if isinstance(time_ns, bool) or not isinstance(time_ns, int):
            raise ValueError(f"time must be an integer of nanoseconds, got {time_ns!r}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"value at {time_ns} is not a finite number: {value!r}")
        lines.append(f"{tags} value={number!r} {time_ns}")
    return lines


# ----------------------------------------------------------------------------------- Postgres

METRICS_TABLE = "experiment_metrics"
QUALITY_TABLE = "signal_quality"

METRIC_COLUMNS = (
    "experiment_id",
    "metrics_version",
    "policy_version",
    "metric",
    "value",
    "unit",
    "coverage",
    "status",
)
METRIC_KEY = ("experiment_id", "metrics_version", "metric")

QUALITY_COLUMNS = (
    "experiment_id",
    "metrics_version",
    "policy_version",
    "source",
    "signal",
    "nominal_interval_s",
    "present",
    "expected",
    "accepted",
    "bad",
    "uncertain",
    "completeness",
    "valid_fraction",
    "bad_fraction",
    "uncertain_fraction",
)
QUALITY_KEY = ("experiment_id", "metrics_version", "source", "signal")

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONNECT_TIMEOUT_S = 5


def pg_connect(conninfo: str | Mapping[str, Any], schema: str) -> psycopg.Connection:
    """An autocommit connection whose `search_path` is `schema`.

    `conninfo` is a psycopg conninfo string or a dict of `psycopg.connect` keyword arguments (the
    convention of `pipeline.pg_migrate`). Raises `ValueError` for a schema name that is not a plain
    identifier, and `psycopg.OperationalError` when the server cannot be reached.
    """
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"schema {schema!r} is not a plain identifier")
    options = f"-c search_path={schema}"
    if isinstance(conninfo, Mapping):
        kwargs = {"connect_timeout": CONNECT_TIMEOUT_S, **conninfo, "options": options}
        return psycopg.connect(**kwargs, autocommit=True)
    return psycopg.connect(
        conninfo, connect_timeout=CONNECT_TIMEOUT_S, options=options, autocommit=True
    )


def pg_check(conn: psycopg.Connection) -> str | None:
    """None when migration 0003 is applied; otherwise the detail of the refusal."""
    needed = ("experiment", METRICS_TABLE, QUALITY_TABLE)
    with conn.cursor() as cur:
        missing = []
        for table in needed:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
            (exists,) = cur.fetchone()
            if not exists:
                missing.append(table)
    if missing:
        return (
            f"missing table(s) {', '.join(missing)}: migration 0003 is not applied "
            "(run python -m scripts.migrate)"
        )
    return None


def missing_experiments(conn: psycopg.Connection, ids: Sequence[str]) -> list[str]:
    """The ids that have no row in `experiment`, in the order given."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT experiment_id FROM experiment WHERE experiment_id = ANY(%s)", (list(ids),)
        )
        found = {row[0] for row in cur.fetchall()}
    return [experiment_id for experiment_id in ids if experiment_id not in found]


def _upsert_sql(table: str, columns: Sequence[str], key: Sequence[str]) -> str:
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in key)
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) "  # noqa: S608 - fixed names
        f"VALUES ({', '.join(f'%({c})s' for c in columns)}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
    )


_UPSERT_METRICS_SQL = _upsert_sql(METRICS_TABLE, METRIC_COLUMNS, METRIC_KEY)
_UPSERT_QUALITY_SQL = _upsert_sql(QUALITY_TABLE, QUALITY_COLUMNS, QUALITY_KEY)


def _params(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> list[dict[str, Any]]:
    """Each row restricted to the table's columns; a missing or an extra key is an error."""
    expected = set(columns)
    params = []
    for row in rows:
        if set(row) != expected:
            missing, extra = sorted(expected - set(row)), sorted(set(row) - expected)
            raise ValueError(
                f"row keys differ from the table columns: missing {missing}, extra {extra}"
            )
        params.append({c: row[c] for c in columns})
    return params


def upsert_metrics(conn: psycopg.Connection, rows: Sequence[Mapping[str, Any]]) -> None:
    """Upsert `experiment_metrics` rows in one transaction (a failing row keeps none)."""
    params = _params(rows, METRIC_COLUMNS)
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(_UPSERT_METRICS_SQL, params)


def upsert_quality(conn: psycopg.Connection, rows: Sequence[Mapping[str, Any]]) -> None:
    """Upsert `signal_quality` rows in one transaction (a failing row keeps none)."""
    params = _params(rows, QUALITY_COLUMNS)
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(_UPSERT_QUALITY_SQL, params)


def write_postgres(
    conn: psycopg.Connection,
    metric_rows: Sequence[Mapping[str, Any]],
    quality_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Both upserts in ONE transaction: if any row fails, nothing of this call is kept."""
    metric_params = _params(metric_rows, METRIC_COLUMNS)
    quality_params = _params(quality_rows, QUALITY_COLUMNS)
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(_UPSERT_METRICS_SQL, metric_params)
        cur.executemany(_UPSERT_QUALITY_SQL, quality_params)


def count_rows(conn: psycopg.Connection, table: str, metrics_version: str) -> dict[str, int]:
    """Rows of `experiment_metrics` or `signal_quality` per experiment, for one metrics version."""
    if table not in (METRICS_TABLE, QUALITY_TABLE):
        raise ValueError(f"unknown table {table!r}")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT experiment_id, COUNT(*) FROM {table} "  # noqa: S608 - checked name
            "WHERE metrics_version = %s GROUP BY experiment_id",
            (metrics_version,),
        )
        return {experiment_id: int(n) for experiment_id, n in cur.fetchall()}
