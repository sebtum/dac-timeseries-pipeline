"""The InfluxDB side of cleaning (M3, ADR-0015): pull one series, write the three tables, read back.

Reads `readings_numeric`, `readings_state` and `readings_conflicts`; writes only
`readings_processed`, `state_intervals` and `quality_intervals` (the raw tables are never
written, and no database is ever created). Everything is bounded to one experiment's window
`[start, end)`, and a series is pulled on its own, so memory is one series window at a time
(about 7,200 points at most).

Two behaviours of Core 3.11.2 were measured before relying on them (decision 15, ADR-0015):

- A later write of the same key **without** a field keeps the field's old value. So a re-run
  over unchanged raw data is identical, but a reading that was accepted and is now excluded
  would keep its old `value`. The read-back therefore also counts the rows that carry a value
  and compares that with the accepted count.
- An empty string field is stored and read back as `""`, so an accepted row has an empty
  `reason` and `flags`, not a placeholder.

`CleaningGateway` is the only thing that talks to InfluxDB; the unit tests give the run a fake
with the same methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

import pyarrow as pa

from pipeline.cleaning import Interval, RawPoint, Verdict
from pipeline.ingest import _tag, _text
from pipeline.ingest_influx import InfluxGateway as _WritingGateway
from pipeline.profiling_sql import QueryFailed
from pipeline.signals import CONFLICTS_TABLE, NUMERIC_TABLE, STATE_TABLE

PROCESSED_TABLE = "readings_processed"
STATE_INTERVALS_TABLE = "state_intervals"
QUALITY_INTERVALS_TABLE = "quality_intervals"

# The processed table that holds the rows of each raw table.
PROCESSED_FOR = {NUMERIC_TABLE: PROCESSED_TABLE, STATE_TABLE: STATE_INTERVALS_TABLE}

WINDOW = "experiment_id = $exp AND time >= $start AND time < $end"


class Gateway(Protocol):
    queries: int

    def tables(self) -> set[str]: ...

    def series_keys(
        self, table: str, experiment_id: str, start: datetime, end: datetime
    ) -> list[tuple[str, str]]: ...

    def pull(
        self,
        table: str,
        experiment_id: str,
        source: str,
        signal: str,
        start: datetime,
        end: datetime,
    ) -> list[RawPoint]: ...

    def conflict_instants(
        self, experiment_id: str, start: datetime, end: datetime
    ) -> set[tuple[str, str, int]]: ...

    def count_raw(
        self, table: str, experiment_id: str, start: datetime, end: datetime
    ) -> dict[tuple[str, str], int]: ...

    def count_processed(
        self, table: str, experiment_id: str, start: datetime, end: datetime, policy_version: str
    ) -> dict[tuple[str, str], tuple[int, int]]: ...

    def write(self, body: str) -> None: ...


def window_params(experiment_id: str, start: datetime, end: datetime) -> dict[str, str]:
    return {
        "exp": experiment_id,
        "start": start.astimezone(UTC).isoformat(),
        "end": end.astimezone(UTC).isoformat(),
    }


class CleaningGateway(_WritingGateway):
    """Reads the raw and processed tables of one database and writes the processed ones."""

    def __init__(self, host: str, token: str, database: str) -> None:
        super().__init__(host, token, database)
        self.queries = 0

    def _table(self, label: str, sql: str, params: Mapping[str, str] | None = None) -> pa.Table:
        self.queries += 1
        try:
            return self._client.query(sql, language="sql", query_parameters=dict(params or {}))
        except Exception as exc:
            raise QueryFailed(label, exc) from exc

    def tables(self) -> set[str]:
        result = self._table(
            "tables",
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'iox'",
        )
        return set(result.column("table_name").to_pylist())

    def series_keys(
        self, table: str, experiment_id: str, start: datetime, end: datetime
    ) -> list[tuple[str, str]]:
        sql = (
            f"SELECT DISTINCT source, signal FROM {table} WHERE {WINDOW} "  # noqa: S608 - fixed name
            "ORDER BY source, signal"
        )
        result = self._table(f"series:{table}", sql, window_params(experiment_id, start, end))
        return list(
            zip(
                result.column("source").to_pylist(),
                result.column("signal").to_pylist(),
                strict=True,
            )
        )

    def pull(
        self,
        table: str,
        experiment_id: str,
        source: str,
        signal: str,
        start: datetime,
        end: datetime,
    ) -> list[RawPoint]:
        sql = (
            f"SELECT time, value, quality FROM {table} "  # noqa: S608 - fixed table name
            f"WHERE {WINDOW} AND source = $src AND signal = $sig ORDER BY time"
        )
        params = {**window_params(experiment_id, start, end), "src": source, "sig": signal}
        result = self._table(f"pull:{experiment_id}/{source}/{signal}", sql, params)
        times = result.column("time").cast(pa.int64()).to_pylist()
        values = result.column("value").to_pylist()
        qualities = result.column("quality").to_pylist()
        return [RawPoint(t, v, q) for t, v, q in zip(times, values, qualities, strict=True)]

    def conflict_instants(
        self, experiment_id: str, start: datetime, end: datetime
    ) -> set[tuple[str, str, int]]:
        if CONFLICTS_TABLE not in self.tables():
            return set()
        sql = f"SELECT source, signal, time FROM {CONFLICTS_TABLE} WHERE {WINDOW}"  # noqa: S608
        result = self._table("conflicts", sql, window_params(experiment_id, start, end))
        return set(
            zip(
                result.column("source").to_pylist(),
                result.column("signal").to_pylist(),
                result.column("time").cast(pa.int64()).to_pylist(),
                strict=True,
            )
        )

    def count_raw(
        self, table: str, experiment_id: str, start: datetime, end: datetime
    ) -> dict[tuple[str, str], int]:
        sql = (
            f"SELECT source, signal, COUNT(*) AS n FROM {table} WHERE {WINDOW} "  # noqa: S608
            "GROUP BY source, signal"
        )
        result = self._table(f"count:{table}", sql, window_params(experiment_id, start, end))
        return {
            (s, g): int(n)
            for s, g, n in zip(
                result.column("source").to_pylist(),
                result.column("signal").to_pylist(),
                result.column("n").to_pylist(),
                strict=True,
            )
        }

    def has_column(self, table: str, column: str) -> bool:
        sql = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'iox' AND table_name = $tbl AND column_name = $col"
        )
        result = self._table(f"columns:{table}", sql, {"tbl": table, "col": column})
        return result.num_rows > 0

    def count_processed(
        self, table: str, experiment_id: str, start: datetime, end: datetime, policy_version: str
    ) -> dict[tuple[str, str], tuple[int, int]]:
        """`(rows, rows that carry a value)` per series, for one policy version.

        A table whose rows never carried a value (every reading excluded) has no `value`
        column at all, so asking for it would fail: that case counts 0 with a value.
        """
        with_value = "COUNT(value)" if self.has_column(table, "value") else "0"
        sql = (
            f"SELECT source, signal, COUNT(*) AS n, {with_value} AS v FROM {table} "  # noqa: S608
            f"WHERE {WINDOW} AND policy_version = $pv GROUP BY source, signal"
        )
        params = {**window_params(experiment_id, start, end), "pv": policy_version}
        result = self._table(f"readback:{table}", sql, params)
        return {
            (s, g): (int(n), int(v))
            for s, g, n, v in zip(
                result.column("source").to_pylist(),
                result.column("signal").to_pylist(),
                result.column("n").to_pylist(),
                result.column("v").to_pylist(),
                strict=True,
            )
        }

    def close(self) -> None:
        super().close()


# ---------------------------------------------------------------------------- line protocol


def _float(value: float) -> str:
    return repr(float(value))


def _tags(experiment_id: str, pair: tuple[str, str], policy_version: str) -> str:
    return (
        f"experiment_id={_tag(experiment_id)},source={_tag(pair[0])},signal={_tag(pair[1])},"
        f"policy_version={_tag(policy_version)}"
    )


def _verdict_fields(point: RawPoint, verdict: Verdict) -> list[str]:
    return [
        f"quality={_text(point.quality)}",
        f"verdict={_text(verdict.verdict)}",
        f"reason={_text(verdict.reason)}",
        f"flags={_text(verdict.flags_text)}",
    ]


def processed_line(
    experiment_id: str,
    pair: tuple[str, str],
    policy_version: str,
    point: RawPoint,
    verdict: Verdict,
) -> str:
    """One `readings_processed` row. The value is the raw value when accepted, absent otherwise."""
    fields = []
    if point.value is not None:
        fields.append(f"value_raw={_float(point.value)}")
        if verdict.accepted:
            fields.append(f"value={_float(point.value)}")
    fields += _verdict_fields(point, verdict)
    tags = _tags(experiment_id, pair, policy_version)
    return f"{PROCESSED_TABLE},{tags} {','.join(fields)} {point.time_ns}"


def state_line(
    experiment_id: str,
    pair: tuple[str, str],
    policy_version: str,
    point: RawPoint,
    verdict: Verdict,
    interval: Interval,
) -> str:
    """One `state_intervals` row: the event, and how long it lasted."""
    fields = []
    if point.value is not None:
        fields.append(f"value_raw={_text(point.value)}")
        if verdict.accepted:
            fields.append(f"value={_text(point.value)}")
    fields += _verdict_fields(point, verdict)
    fields += [f"end_ns={interval.end_ns}i", f"seconds={_float(interval.seconds)}"]
    tags = _tags(experiment_id, pair, policy_version)
    return f"{STATE_INTERVALS_TABLE},{tags} {','.join(fields)} {point.time_ns}"


def quality_interval_line(
    experiment_id: str,
    pair: tuple[str, str],
    policy_version: str,
    kind: str,
    interval: Interval,
) -> str:
    """One `quality_intervals` row (`kind` is `gap` or `flatline`)."""
    tags = _tags(experiment_id, pair, policy_version) + f",kind={_tag(kind)}"
    fields = (
        f"end_ns={interval.end_ns}i,seconds={_float(interval.seconds)},points={interval.points}i"
    )
    return f"{QUALITY_INTERVALS_TABLE},{tags} {fields} {interval.start_ns}"


def series_lines(
    experiment_id: str,
    pair: tuple[str, str],
    policy_version: str,
    points: list[RawPoint],
    verdicts: list[Verdict],
    state_spans: list[Interval] | None,
    gaps: list[Interval] | None,
    flatlines: list[Interval] | None,
) -> list[str]:
    """Every line for one series: its processed rows, then its gap and flatline intervals."""
    lines: list[str] = []
    if state_spans is None:
        lines += [
            processed_line(experiment_id, pair, policy_version, p, v)
            for p, v in zip(points, verdicts, strict=True)
        ]
    else:
        lines += [
            state_line(experiment_id, pair, policy_version, p, v, span)
            for p, v, span in zip(points, verdicts, state_spans, strict=True)
        ]
    lines += [
        quality_interval_line(experiment_id, pair, policy_version, "gap", g) for g in gaps or []
    ]
    lines += [
        quality_interval_line(experiment_id, pair, policy_version, "flatline", f)
        for f in flatlines or []
    ]
    return lines


def raw_counts(
    gateway: Gateway, windows: list[Any], tables: set[str]
) -> dict[tuple[str, str, str, str], int]:
    """`(table, experiment, source, signal) -> points` for the three raw tables."""
    counts: dict[tuple[str, str, str, str], int] = {}
    for table in (NUMERIC_TABLE, STATE_TABLE, CONFLICTS_TABLE):
        if table not in tables:
            continue
        for window in windows:
            found = gateway.count_raw(table, window.experiment_id, window.start, window.end)
            for (source, signal), n in found.items():
                counts[(table, window.experiment_id, source, signal)] = n
    return counts
