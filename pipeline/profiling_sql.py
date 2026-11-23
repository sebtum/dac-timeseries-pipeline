"""The SQL side of the post-ingest profile (M2.5, ADR-0014): one query per measure.

Read-only. Every query is bounded to one experiment's window `[start, end)` (M2.5 decision 2), so
none comes near Core's single-query span limit (U-05). The one exception is the span probe, which
asks for everything at once on purpose and is allowed to be refused.

What runs where (ADR-0010): ranges, intervals, runs, differences and the four relationships are
SQL aggregations on the server. Only the lag of `current` behind `current_setpoint` is pulled
into Python (two series of one experiment, at most about 7,200 rows each), because a 61-step
shifted correlation is not a window query.

`Gateway` is the only thing that talks to InfluxDB; tests give `run_profile` a fake with the same
`rows(label, sql, params)` method.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from influxdb_client_3 import InfluxDBClient3

from pipeline import profiling
from pipeline.signals import (
    DOCUMENTED_RANGE,
    NOMINAL_INTERVAL_S,
    NUMERIC_TABLE,
    STATE_TABLE,
)

WINDOW = "experiment_id = $exp AND time >= $start AND time < $end"
NS = profiling.NS
LONGEST = profiling.LONGEST


class QueryFailed(Exception):
    """A profiling query that could not be answered. `label` names the measure."""

    def __init__(self, label: str, cause: BaseException) -> None:
        super().__init__(f"query {label!r} failed: {cause}")
        self.label = label
        self.cause = cause


class Gateway(Protocol):
    queries: int

    def rows(self, label: str, sql: str, params: Mapping[str, str] | None = None) -> list[dict]: ...


class InfluxGateway:
    """Read-only access to one database. Counts the queries it runs."""

    def __init__(self, host: str, token: str, database: str) -> None:
        self._client = InfluxDBClient3(host=host, token=token, database=database)
        self.queries = 0

    def rows(self, label: str, sql: str, params: Mapping[str, str] | None = None) -> list[dict]:
        self.queries += 1
        try:
            result = self._client.query(sql, language="sql", query_parameters=dict(params or {}))
            return result.to_pylist()
        except Exception as exc:
            raise QueryFailed(label, exc) from exc

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------- SQL text


def _case(values: Mapping[str, float | int]) -> str:
    """`CASE signal WHEN 'x' THEN 1 ... END`, from a declared table (never from user input)."""
    arms = " ".join(f"WHEN '{signal}' THEN {value}" for signal, value in sorted(values.items()))
    return f"CASE signal {arms} END"


def _by_signal(pairs: Mapping[tuple[str, str], Any], pick) -> dict[str, Any]:
    return {signal: pick(value) for (_source, signal), value in pairs.items()}


def _count_if(condition: str) -> str:
    """Count the rows where `condition` is true.

    Not `COUNT(*) FILTER (WHERE ...)`: on Core 3.11.2 (DataFusion 51) that counts a row whose
    condition is NULL (a missing value, the first interval of a series). Found by the M2.5
    calibration against a plain SELECT pull; recorded in ADR-0014.
    """
    return f"COUNT(CASE WHEN {condition} THEN 1 END)"


def _norm(table: str) -> str:
    """The stored value as a number comparable with `=`/`<`: `value + 0.0` turns -0.0 into 0.0.

    This engine orders -0.0 before 0.0, so `-0.0 < 0` is true and `-0.0 = 0` is false. The real
    file has one `-0.00` reading; a profile that counted it below zero would be counting a sign.
    """
    return "value + 0.0" if table == NUMERIC_TABLE else "value"


def percentile_sql(
    source_cte: str, percentiles: Mapping[str, float], by: tuple[str, ...], ctes: str = ""
) -> str:
    """Exact percentiles with linear interpolation, in double precision.

    `source_cte` is the body of a CTE named `s` with the columns `by` and `x` (no nulls);
    `ctes` is any CTE text it needs, ending in a comma. The
    engine's own `PERCENTILE_CONT` interpolates in roughly float32 precision (0.95 of
    `0.0, 0.39, 0.41` gives 0.40799998, not 0.408; found by the M2.5 calibration, ADR-0014), so
    the two neighbouring ranks of each percentile are weighted here instead. Same definition
    as NumPy's default: position `p * (n - 1)`, counted from zero.
    """
    group = ", ".join(by)
    partition = f"PARTITION BY {group} " if by else ""
    lead = f"{group}, " if by else ""
    measures = []
    for alias, p in percentiles.items():
        position = f"({p!r} * m)"
        low = f"FLOOR{position}"
        measures.append(
            f"SUM(x * (CASE WHEN CAST(rn AS DOUBLE) = {low} + 1.0 THEN 1.0 - ({position} - {low}) "
            f"WHEN CAST(rn AS DOUBLE) = {low} + 2.0 THEN {position} - {low} ELSE 0.0 END)) "
            f"AS {alias}"
        )
    return (
        f"WITH {ctes}s AS ({source_cte}), "
        f"rk AS (SELECT {lead}x, ROW_NUMBER() OVER ({partition}ORDER BY x) AS rn, "
        f"CAST(COUNT(*) OVER ({partition.strip()}) AS DOUBLE) - 1.0 AS m FROM s) "
        f"SELECT {lead}{', '.join(measures)} FROM rk" + (f" GROUP BY {group}" if by else "")
    )


def basics_sql(table: str) -> str:
    quality = ", ".join(
        _count_if("quality = '" + flag + "'") + f" AS q_{flag.lower()}"
        for flag in profiling.QUALITY_FLAGS
    )
    head = (
        "SELECT source, signal, COUNT(*) AS points, "
        f"COUNT(*) - COUNT(value) AS points_without_value, {quality}"
    )
    if table == NUMERIC_TABLE:
        low = _case(_by_signal(DOCUMENTED_RANGE, lambda r: r[0]))
        high = _case(_by_signal(DOCUMENTED_RANGE, lambda r: r[1]))
        head += (
            ", MIN(value + 0.0) AS v_min, MAX(value + 0.0) AS v_max, AVG(value) AS v_mean"
            ", STDDEV(value) AS v_stddev, MEDIAN(value) AS v_median"
            f", {_count_if(f'value + 0.0 < {low}')} AS below"
            f", {_count_if(f'value + 0.0 > {high}')} AS above"
        )
    return f"{head} FROM {table} WHERE {WINDOW} GROUP BY source, signal"  # noqa: S608


def values_percentiles_sql() -> str:
    return percentile_sql(
        f"SELECT source, signal, value AS x FROM {NUMERIC_TABLE} "  # noqa: S608
        f"WHERE {WINDOW} AND value IS NOT NULL",
        {"v_p05": 0.05, "v_p95": 0.95},
        ("source", "signal"),
    )


def states_sql() -> str:
    return (
        f"SELECT source, signal, value, COUNT(*) AS n FROM {STATE_TABLE} "  # noqa: S608
        f"WHERE {WINDOW} AND value IS NOT NULL GROUP BY source, signal, value"
    )


def intervals_sql(table: str) -> str:
    if table == NUMERIC_TABLE:
        nominal = _case(_by_signal(NOMINAL_INTERVAL_S, lambda s: int(round(s * NS))))
        counts = (
            f", {_count_if(f'dt > 2 * ({nominal})')} AS over2"
            f", {_count_if(f'dt > 10 * ({nominal})')} AS over10"
            f", COALESCE(SUM(CASE WHEN dt > 2 * ({nominal}) THEN dt END), 0) AS secs2"
        )
    else:
        counts = ""
    return (
        "WITH iv AS (SELECT source, signal, CAST(time AS BIGINT) - "
        "LAG(CAST(time AS BIGINT)) OVER (PARTITION BY source, signal ORDER BY time) AS dt "
        f"FROM {table} WHERE {WINDOW}) "  # noqa: S608
        "SELECT source, signal, COUNT(dt) AS n, MIN(dt) AS dt_min, "
        "MEDIAN(CAST(dt AS DOUBLE)) AS dt_median, MAX(dt) AS dt_max"
        f"{counts} FROM iv GROUP BY source, signal"
    )


def intervals_percentile_sql(table: str) -> str:
    return percentile_sql(
        "SELECT source, signal, CAST(dt AS DOUBLE) AS x FROM (SELECT source, signal, "
        "CAST(time AS BIGINT) - LAG(CAST(time AS BIGINT)) OVER "
        "(PARTITION BY source, signal ORDER BY time) AS dt "
        f"FROM {table} WHERE {WINDOW}) WHERE dt IS NOT NULL",  # noqa: S608
        {"dt_p95": 0.95},
        ("source", "signal"),
    )


def intervals_longest_sql(table: str) -> str:
    return (
        "WITH iv AS (SELECT source, signal, CAST(time AS BIGINT) AS t1, "
        "LAG(CAST(time AS BIGINT)) OVER (PARTITION BY source, signal ORDER BY time) AS t0 "
        f"FROM {table} WHERE {WINDOW}), "  # noqa: S608
        "ranked AS (SELECT source, signal, t0, t1, ROW_NUMBER() OVER "
        "(PARTITION BY source, signal ORDER BY t1 - t0 DESC, t0) AS rn FROM iv "
        "WHERE t0 IS NOT NULL) "
        f"SELECT source, signal, t0, t1 FROM ranked WHERE rn <= {LONGEST} "
        "ORDER BY source, signal, rn"
    )


def _runs_cte(table: str) -> str:
    """One row per streak of identical consecutive values (points with a value only)."""
    norm = _norm(table)
    return (
        f"WITH v AS (SELECT source, signal, time, {norm} AS value, "
        f"CASE WHEN {norm} IS DISTINCT FROM LAG({norm}) OVER "
        "(PARTITION BY source, signal ORDER BY time) THEN 1 ELSE 0 END AS flag "
        f"FROM {table} WHERE {WINDOW} AND value IS NOT NULL), "  # noqa: S608
        "r AS (SELECT source, signal, CAST(time AS BIGINT) AS t, value, "
        "SUM(flag) OVER (PARTITION BY source, signal ORDER BY time "
        "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS run_id FROM v), "
        "g AS (SELECT source, signal, run_id, COUNT(*) AS samples, MIN(t) AS t0, MAX(t) AS t1, "
        "MIN(value) AS value FROM r GROUP BY source, signal, run_id)"
    )


def runs_sql(table: str) -> str:
    return (
        f"{_runs_cte(table)} SELECT source, signal, COUNT(*) AS n, "
        "MEDIAN(CAST(samples AS DOUBLE)) AS median_samples, MAX(samples) AS max_samples, "
        "MAX(t1 - t0) AS max_ns FROM g GROUP BY source, signal"
    )


def runs_longest_sql(table: str) -> str:
    return (
        f"{_runs_cte(table)}, ranked AS (SELECT source, signal, samples, t0, t1, value, "
        "ROW_NUMBER() OVER (PARTITION BY source, signal ORDER BY samples DESC, t0) AS rn FROM g) "
        f"SELECT source, signal, samples, t0, t1, value FROM ranked WHERE rn <= {LONGEST} "
        "ORDER BY source, signal, rn"
    )


def differences_sql() -> str:
    return (
        "WITH d AS (SELECT source, signal, value - LAG(value) OVER "
        "(PARTITION BY source, signal ORDER BY time) AS d "
        f"FROM {NUMERIC_TABLE} WHERE {WINDOW} AND value IS NOT NULL) "  # noqa: S608
        "SELECT source, signal, COUNT(d) AS n, AVG(d) AS d_mean, STDDEV(d) AS d_stddev, "
        "MEDIAN(ABS(d)) AS d_median_abs, MAX(ABS(d)) AS d_max_abs FROM d GROUP BY source, signal"
    )


def differences_percentile_sql() -> str:
    return percentile_sql(
        "SELECT source, signal, ABS(d) AS x FROM (SELECT source, signal, value - LAG(value) OVER "
        "(PARTITION BY source, signal ORDER BY time) AS d "
        f"FROM {NUMERIC_TABLE} WHERE {WINDOW} AND value IS NOT NULL) WHERE d IS NOT NULL",  # noqa: S608
        {"d_p95_abs": 0.95},
        ("source", "signal"),
    )


def _signal_cte(alias: str, source: str, signal: str) -> str:
    return (
        f"{alias} AS (SELECT time, value FROM {NUMERIC_TABLE} "  # noqa: S608
        f"WHERE {WINDOW} AND source = '{source}' AND signal = '{signal}' AND value IS NOT NULL)"
    )


def _power_ctes() -> str:
    return (
        ", ".join(
            [
                _signal_cte("p", "hydrolyzer", "power"),
                _signal_cte("v", "hydrolyzer", "voltage"),
                _signal_cte("i", "hydrolyzer", "current"),
            ]
        )
        + ", j AS (SELECT p.value AS y, v.value * i.value AS x FROM p "
        "JOIN v ON p.time = v.time JOIN i ON p.time = i.time)"
    )


def power_sql() -> str:
    return (
        f"WITH {_power_ctes()} "
        "SELECT COUNT(*) AS matched, AVG(y - x) AS r_mean, "
        "STDDEV(y - x) AS r_stddev, MEDIAN(y - x) AS r_median, MAX(ABS(y - x)) AS r_max_abs, "
        "MEDIAN(CASE WHEN y > 0 THEN ABS(y - x) / y END) AS rel_median, "
        f"{_count_if('y + 0.0 = 0')} AS zero FROM j"
    )


def power_percentile_sqls() -> list[str]:
    ctes = _power_ctes() + ", "
    return [
        percentile_sql("SELECT y - x AS x FROM j", {"r_p05": 0.05, "r_p95": 0.95}, (), ctes=ctes),
        percentile_sql(
            "SELECT ABS(y - x) / y AS x FROM j WHERE y > 0", {"rel_p95": 0.95}, (), ctes=ctes
        ),
    ]


def _co2_ctes() -> str:
    return (
        ", ".join(
            [
                _signal_cte("o", "absorber", "co2_out_ppm"),
                _signal_cte("n", "absorber", "co2_in_ppm"),
            ]
        )
        + ", j AS (SELECT o.value AS out_ppm, n.value AS in_ppm FROM o JOIN n ON o.time = n.time)"
    )


def co2_sql() -> str:
    return (
        f"WITH {_co2_ctes()} "
        "SELECT COUNT(*) AS matched, MEDIAN(out_ppm / NULLIF(in_ppm, 0)) AS ratio_median, "
        f"{_count_if('out_ppm >= in_ppm')} AS at_or_above FROM j"
    )


def co2_percentile_sqls() -> list[str]:
    return [
        percentile_sql(
            "SELECT out_ppm / in_ppm AS x FROM j WHERE in_ppm <> 0",
            {"ratio_p05": 0.05, "ratio_p95": 0.95},
            (),
            ctes=_co2_ctes() + ", ",
        )
    ]


def current_sql() -> str:
    return (
        "WITH "
        + ", ".join(
            [
                _signal_cte("c", "hydrolyzer", "current"),
                _signal_cte("s", "hydrolyzer", "current_setpoint"),
            ]
        )
        + ", j AS (SELECT c.value AS cur, s.value AS sp FROM c JOIN s ON c.time = s.time) "
        "SELECT COUNT(*) AS matched, AVG(cur - sp) AS d_mean, "
        "STDDEV(cur - sp) AS d_stddev, MEDIAN(cur - sp) AS d_median, "
        "MAX(ABS(cur - sp)) AS d_max_abs FROM j"
    )


def pressure_drop_sql() -> str:
    return (
        "WITH "
        + ", ".join(
            [
                _signal_cte("d", "absorber", "pressure_drop"),
                _signal_cte("a", "absorber", "air_flow"),
            ]
        )
        + ", j AS (SELECT d.value AS dp FROM d JOIN a ON d.time = a.time) "
        "SELECT COUNT(*) AS matched FROM j"
    )


def series_pull_sql(source: str, signal: str) -> str:
    return (
        f"SELECT CAST(time AS BIGINT) AS t, value FROM {NUMERIC_TABLE} "  # noqa: S608
        f"WHERE {WINDOW} AND source = '{source}' AND signal = '{signal}' "
        "AND value IS NOT NULL ORDER BY time"
    )


SPAN_PROBE_SQL = f"SELECT COUNT(*) AS n FROM {NUMERIC_TABLE} WHERE time >= $start AND time < $end"  # noqa: S608
TABLES_SQL = (
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'iox' "
    "ORDER BY table_name"
)

# The series each relationship's Python part needs.
PULLS: dict[str, list[tuple[str, str]]] = {
    "power_vs_voltage_x_current": [
        ("hydrolyzer", "power"),
        ("hydrolyzer", "voltage"),
        ("hydrolyzer", "current"),
    ],
    "co2_out_vs_co2_in": [("absorber", "co2_out_ppm"), ("absorber", "co2_in_ppm")],
    "current_vs_current_setpoint": [("hydrolyzer", "current"), ("hydrolyzer", "current_setpoint")],
    "pressure_drop_vs_air_flow": [("absorber", "pressure_drop"), ("absorber", "air_flow")],
}

# kind -> (queries, (source, signal) of the dependent signal whose points
# `instants_unmatched` counts)
RELATIONSHIPS: dict[str, tuple[list[str], tuple[str, str]]] = {
    "power_vs_voltage_x_current": (
        [power_sql(), *power_percentile_sqls()],
        ("hydrolyzer", "power"),
    ),
    "co2_out_vs_co2_in": ([co2_sql(), *co2_percentile_sqls()], ("absorber", "co2_out_ppm")),
    "current_vs_current_setpoint": ([current_sql()], ("hydrolyzer", "current")),
    "pressure_drop_vs_air_flow": ([pressure_drop_sql()], ("absorber", "pressure_drop")),
}


# ---------------------------------------------------------------------------- running


@dataclass(frozen=True)
class Window:
    experiment_id: str
    start: datetime
    end: datetime

    def params(self) -> dict[str, str]:
        return {
            "exp": self.experiment_id,
            "start": self.start.astimezone(UTC).isoformat(),
            "end": self.end.astimezone(UTC).isoformat(),
        }


def tables_present(gateway: Gateway) -> set[str]:
    rows = gateway.rows("tables", TABLES_SQL)
    return {row["table_name"] for row in rows} & {NUMERIC_TABLE, STATE_TABLE}


def span_probe(gateway: Gateway, start: datetime, end: datetime) -> tuple[int | None, str | None]:
    """One COUNT over the whole span. Returns `(count, None)` or `(None, server message)`."""
    window = Window("", start, end).params()
    try:
        rows = gateway.rows(
            "span_probe", SPAN_PROBE_SQL, {"start": window["start"], "end": window["end"]}
        )
    except QueryFailed as exc:
        return None, str(exc.cause)
    return int(rows[0]["n"]), None


def merge_rows(base: list[dict], extra: list[dict]) -> list[dict]:
    """Add the columns of `extra` to the `base` row with the same `(source, signal)`."""
    by_key = {(r["source"], r["signal"]): r for r in extra}
    return [{**row, **by_key.get((row["source"], row["signal"]), {})} for row in base]


def profile_table(gateway: Gateway, window: Window, table: str) -> list[dict[str, Any]]:
    """The series of one experiment held in one table."""
    params = window.params()
    basics = gateway.rows(f"basics {table}", basics_sql(table), params)
    if not basics:
        return []
    numeric = table == NUMERIC_TABLE
    if numeric:
        basics = merge_rows(
            basics, gateway.rows("value percentiles", values_percentiles_sql(), params)
        )
    intervals = merge_rows(
        gateway.rows(f"intervals {table}", intervals_sql(table), params),
        gateway.rows(f"interval percentiles {table}", intervals_percentile_sql(table), params),
    )
    differences: list[dict] = []
    if numeric:
        differences = merge_rows(
            gateway.rows("differences", differences_sql(), params),
            gateway.rows("difference percentiles", differences_percentile_sql(), params),
        )
    return profiling.shape_series(
        window.experiment_id,
        table,
        basics,
        [] if numeric else gateway.rows("states", states_sql(), params),
        intervals,
        gateway.rows(f"longest intervals {table}", intervals_longest_sql(table), params),
        gateway.rows(f"runs {table}", runs_sql(table), params),
        gateway.rows(f"longest runs {table}", runs_longest_sql(table), params),
        differences,
    )


def pull_series(gateway: Gateway, window: Window, source: str, signal: str) -> dict[int, float]:
    """`{instant in ns: value}` for one numeric series of one experiment, points with a value."""
    rows = gateway.rows(f"series {signal}", series_pull_sql(source, signal), window.params())
    return {int(row["t"]): row["value"] for row in rows}


def profile_relationships(
    gateway: Gateway, window: Window, series: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The four relationships of one experiment (empty if it has no numeric points).

    SQL measures each pair's per-value numbers (residuals, ratios, differences). The correlation,
    the fitted lines and the lag are computed in Python on the pulled pairs: the engine's parallel
    sums differ in the last bits between runs, and a fitted intercept is a small difference of
    large numbers, so the same data gave a different 9th digit on a second run (ADR-0014).
    """
    if not any(s["table"] == NUMERIC_TABLE for s in series):
        return []
    params = window.params()
    points = {(s["source"], s["signal"]): s["points"] for s in series}
    pulled: dict[str, dict[int, float]] = {}
    out = []
    for kind, (queries, dependent) in RELATIONSHIPS.items():
        row: dict[str, Any] = {}
        for number, sql in enumerate(queries):
            rows = gateway.rows(kind if number == 0 else f"{kind} percentiles", sql, params)
            row |= rows[0] if rows else {}
        for source, signal in PULLS[kind]:
            if signal not in pulled:
                pulled[signal] = pull_series(gateway, window, source, signal)
        fits = profiling.relationship_fits(kind, pulled)
        out.append(
            profiling.shape_relationship(
                kind, window.experiment_id, row, points.get(dependent, 0), fits
            )
        )
    return out


def profile_experiment(
    gateway: Gateway, window: Window, tables: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """All series and relationships of one experiment: `(series, relationships)`."""
    series: list[dict[str, Any]] = []
    for table in (NUMERIC_TABLE, STATE_TABLE):
        if table in tables:
            series += profile_table(gateway, window, table)
    return series, profile_relationships(gateway, window, series)
