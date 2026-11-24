"""Integration tests for `pipeline.compare_store` (M5 T2; S5.10 and S5.11).

Throwaway state, created and dropped in fixtures' `finally`, as in `test_metrics_store.py`:

- one InfluxDB database per test (Core allows five databases, so at most one extra exists at any
  moment), seeded with line protocol in the layout the cleaning and the metrics write;
- one Postgres schema with the real `migrations/` applied and the experiments loaded through
  `pipeline.metadata_loader`.

Nothing here touches `dac_raw`, `dac_rollup` or `dac_pinned`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

import scripts.init_influx as init_influx
import scripts.migrate as migrate
from pipeline.compare_store import (
    CompareGateway,
    DatabaseMissing,
    experiment_metric_rows,
    experiment_rows,
    pg_check,
    pg_connect,
)
from pipeline.ingest import _tag, _text
from pipeline.ingest_influx import list_databases
from pipeline.metadata_loader import load_experiments
from pipeline.metrics_store import INPUT_TABLES, MetricsGateway, write_postgres
from pipeline.metrics_store import DatabaseMissing as MetricsDatabaseMissing
from pipeline.pg_migrate import run_migrations
from pipeline.profiling_sql import QueryFailed

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "metrics" / "experiments.json"

BASE = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)
BASE_NS = int(BASE.timestamp()) * 1_000_000_000
SECOND = 1_000_000_000
EXP = "EXP_T2"
OTHER_EXP = "EXP_T2_OTHER"
PV = "pv-test-1"
PV_OTHER = "pv-test-2"
MV = "mv-test-1"
MV_OTHER = "mv-test-2"
END = BASE + timedelta(seconds=10)


def _at(seconds: int) -> int:
    return BASE_NS + seconds * SECOND


# ------------------------------------------------------------------------------- InfluxDB side


def _http(method: str, url: str, token: str, body: dict | None = None) -> None:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            response.read()
    except urllib.error.HTTPError as exc:
        if not (method == "DELETE" and exc.code == 404):
            raise


@pytest.fixture
def stack(influx_client):  # noqa: ARG001 - influx_client: skip when InfluxDB is unreachable
    """`(host, token, name)` of one throwaway database, dropped afterwards."""
    env = init_influx.load_env()
    host, token = env["INFLUX_HOST"], env["INFLUX_TOKEN"]
    name = f"t2_compare_{uuid.uuid4().hex[:8]}"
    _http("POST", f"{host}/api/v3/configure/database", token, {"db": name})
    try:
        yield host, token, name
    finally:
        _http("DELETE", f"{host}/api/v3/configure/database?db={name}", token)


@pytest.fixture
def gateway(stack):
    host, token, name = stack
    gw = CompareGateway(host, token, name)
    try:
        yield gw
    finally:
        gw.close()


@pytest.fixture
def seeder(stack):
    """A separate `MetricsGateway` on the same database, used only to put the test rows in."""
    host, token, name = stack
    gw = MetricsGateway(host, token, name)
    try:
        yield gw
    finally:
        gw.close()


def _numeric_line(
    signal: str,
    t_ns: int,
    verdict: str = "accepted",
    raw: float | None = None,
    *,
    policy_version: str = PV,
    experiment_id: str = EXP,
) -> str:
    """One `readings_processed` row as cleaning writes it: `value` only when accepted."""
    tags = (
        f"readings_processed,experiment_id={_tag(experiment_id)},source=hydrolyzer,"
        f"signal={_tag(signal)},policy_version={_tag(policy_version)}"
    )
    fields = []
    if raw is not None:
        fields.append(f"value_raw={raw!r}")
        if verdict == "accepted":
            fields.append(f"value={raw!r}")
    quality = "GOOD" if verdict == "accepted" else "BAD"
    fields += [
        f"quality={_text(quality)}",
        f"verdict={_text(verdict)}",
        f"reason={_text('' if verdict == 'accepted' else 'flag_bad')}",
        'flags=""',
    ]
    return f"{tags} {','.join(fields)} {t_ns}"


def _state_line(
    signal: str,
    t_ns: int,
    verdict: str = "accepted",
    raw: str | None = None,
    end_ns: int = 0,
    *,
    policy_version: str = PV,
    experiment_id: str = EXP,
) -> str:
    """One `state_intervals` row: the event and its `end_ns`."""
    tags = (
        f"state_intervals,experiment_id={_tag(experiment_id)},source=plant,"
        f"signal={_tag(signal)},policy_version={_tag(policy_version)}"
    )
    fields = []
    if raw is not None:
        fields.append(f"value_raw={_text(raw)}")
        if verdict == "accepted":
            fields.append(f"value={_text(raw)}")
    quality = "GOOD" if verdict == "accepted" else "BAD"
    fields += [
        f"quality={_text(quality)}",
        f"verdict={_text(verdict)}",
        f"reason={_text('' if verdict == 'accepted' else 'flag_bad')}",
        'flags=""',
        f"end_ns={end_ns}i",
        "seconds=1.0",
    ]
    return f"{tags} {','.join(fields)} {t_ns}"


def _seed_everything(seeder: MetricsGateway) -> None:
    sum_ = 0.1 + 0.2  # 0.30000000000000004: a read must give back the exact float
    seeder.write(
        "\n".join(
            [
                # --- readings_processed, voltage of EXP, version PV (written out of order)
                _numeric_line("voltage", _at(3), raw=sum_),
                _numeric_line("voltage", _at(1), raw=2.5),
                _numeric_line("voltage", _at(0), raw=1.5),  # start is included
                _numeric_line("voltage", _at(2), "excluded", raw=99.0),  # excluded, with a raw
                _numeric_line("voltage", _at(5), "excluded"),  # excluded, no raw value at all
                _numeric_line("voltage", _at(10), raw=7.0),  # end is excluded
                # Not read: another version, another experiment, another signal.
                _numeric_line("voltage", _at(1), raw=1000.0, policy_version=PV_OTHER),
                _numeric_line("voltage", _at(1), raw=2000.0, experiment_id=OTHER_EXP),
                _numeric_line("current", _at(1), raw=3000.0),
                # --- state_intervals, process_state of EXP, version PV
                _state_line("process_state", _at(3), raw="STEADY_STATE", end_ns=_at(9)),
                _state_line("process_state", _at(0), raw="STARTUP", end_ns=_at(3)),
                _state_line("process_state", _at(5), "excluded", raw="LOAD_CHANGE", end_ns=_at(6)),
                _state_line("process_state", _at(9), raw="SHUTDOWN", end_ns=_at(12)),
                _state_line("process_state", _at(10), raw="OUTSIDE", end_ns=_at(11)),
                # Not read: another version, another experiment, another signal.
                _state_line("process_state", _at(1), raw="V2", policy_version=PV_OTHER),
                _state_line("process_state", _at(1), raw="OTHER", experiment_id=OTHER_EXP),
                _state_line("valve_state", _at(1), raw="open"),
            ]
        )
    )
    for metrics_version, policy_version, metric, offset in (
        (MV, PV, "power_computed", 100.0),
        (MV_OTHER, PV, "power_computed", 200.0),
        (MV, PV_OTHER, "power_computed", 300.0),
        (MV, PV, "capture_rate", 400.0),
    ):
        seeder.write_series(
            EXP,
            metric,
            metrics_version,
            policy_version,
            [(_at(i), offset + i) for i in (3, 1, 0)] + [(_at(10), offset + 10)],
        )
    seeder.write_series(OTHER_EXP, "power_computed", MV, PV, [(_at(1), 500.0)])


def test_s5_10_state_events_are_the_accepted_events_of_one_version_with_end_ns(gateway, seeder):
    _seed_everything(seeder)

    events = gateway.state_events(EXP, "process_state", BASE, END, PV)

    assert events == [
        (_at(0), _at(3), "STARTUP"),
        (_at(3), _at(9), "STEADY_STATE"),
        (_at(9), _at(12), "SHUTDOWN"),
    ]
    assert all(isinstance(t, int) and isinstance(e, int) for t, e, _ in events)
    assert gateway.state_events(EXP, "process_state", BASE, END, PV_OTHER) == [(_at(1), 0, "V2")]
    assert gateway.state_events(EXP, "process_state", BASE, END, "no-such-version") == []
    assert gateway.state_events(EXP, "no_such_signal", BASE, END, PV) == []
    assert gateway.state_events(EXP, "valve_state", BASE, END, PV) == [(_at(1), 0, "open")]
    assert gateway.state_events(OTHER_EXP, "process_state", BASE, END, PV) == [(_at(1), 0, "OTHER")]


def test_s5_10_raw_series_is_value_raw_of_every_row_of_the_version_excluded_ones_included(
    gateway, seeder
):
    _seed_everything(seeder)
    sum_ = 0.1 + 0.2

    series = gateway.raw_series(EXP, "voltage", BASE, END, PV)

    assert series == [(_at(0), 1.5), (_at(1), 2.5), (_at(2), 99.0), (_at(3), sum_), (_at(5), None)]
    assert series[3][1] == sum_
    assert gateway.raw_series(EXP, "voltage", BASE, END, PV_OTHER) == [(_at(1), 1000.0)]
    assert gateway.raw_series(EXP, "voltage", BASE, END, "no-such-version") == []
    assert gateway.raw_series(EXP, "current", BASE, END, PV) == [(_at(1), 3000.0)]
    assert gateway.raw_series(OTHER_EXP, "voltage", BASE, END, PV) == [(_at(1), 2000.0)]
    # Window edges: start included, end excluded.
    assert gateway.raw_series(EXP, "voltage", BASE + timedelta(seconds=2), END, PV) == [
        (_at(2), 99.0),
        (_at(3), sum_),
        (_at(5), None),
    ]
    assert gateway.raw_series(EXP, "voltage", BASE, BASE + timedelta(seconds=2), PV) == [
        (_at(0), 1.5),
        (_at(1), 2.5),
    ]
    assert gateway.raw_series(EXP, "voltage", BASE, BASE + timedelta(seconds=10), PV)[-1] == (
        _at(5),
        None,
    )
    # accepted_series (inherited) stays accepted-only on the same rows.
    assert gateway.accepted_series(EXP, "voltage", BASE, END, PV) == [
        (_at(0), 1.5),
        (_at(1), 2.5),
        (_at(3), sum_),
    ]


def test_s5_10_metric_series_filters_on_both_versions_in_time_order(gateway, seeder):
    _seed_everything(seeder)

    series = gateway.metric_series(EXP, "power_computed", MV, PV, BASE, END)

    assert series == [(_at(0), 100.0), (_at(1), 101.0), (_at(3), 103.0)]  # _at(10) is the end
    assert all(isinstance(t, int) and isinstance(v, float) for t, v in series)
    assert gateway.metric_series(EXP, "power_computed", MV_OTHER, PV, BASE, END) == [
        (_at(0), 200.0),
        (_at(1), 201.0),
        (_at(3), 203.0),
    ]
    assert gateway.metric_series(EXP, "power_computed", MV, PV_OTHER, BASE, END) == [
        (_at(0), 300.0),
        (_at(1), 301.0),
        (_at(3), 303.0),
    ]
    assert gateway.metric_series(EXP, "capture_rate", MV, PV, BASE, END)[0] == (_at(0), 400.0)
    assert gateway.metric_series(EXP, "capture_rate", MV_OTHER, PV, BASE, END) == []
    assert gateway.metric_series(EXP, "power_computed", MV, "no-such-version", BASE, END) == []
    assert gateway.metric_series(EXP, "no_such_metric", MV, PV, BASE, END) == []
    assert gateway.metric_series(OTHER_EXP, "power_computed", MV, PV, BASE, END) == [
        (_at(1), 500.0)
    ]
    # Window edges.
    assert gateway.metric_series(
        EXP, "power_computed", MV, PV, BASE + timedelta(seconds=1), BASE + timedelta(seconds=3)
    ) == [(_at(1), 101.0)]


def test_s5_10_has_metrics_rows_is_false_for_a_version_with_no_rows(gateway, seeder):
    assert gateway.has_metrics_rows(MV, PV) is False  # no metrics_series table yet
    _seed_everything(seeder)

    assert gateway.has_metrics_rows(MV, PV) is True
    assert gateway.has_metrics_rows(MV_OTHER, PV) is True
    assert gateway.has_metrics_rows(MV, PV_OTHER) is True
    assert gateway.has_metrics_rows("mv-none", PV) is False
    assert gateway.has_metrics_rows(MV, "pv-none") is False
    assert (
        gateway.has_metrics_rows(MV_OTHER, PV_OTHER) is False
    )  # each version exists, not the pair
    # The inherited reads still work.
    assert gateway.has_policy_rows(PV) is True
    assert gateway.has_policy_rows("pv-none") is False


def test_a_database_with_no_tables_reads_as_empty_not_as_an_error(gateway):
    assert gateway.tables() == set()
    assert gateway.raw_series(EXP, "voltage", BASE, END, PV) == []
    assert gateway.state_events(EXP, "process_state", BASE, END, PV) == []
    assert gateway.metric_series(EXP, "power_computed", MV, PV, BASE, END) == []
    assert gateway.has_metrics_rows(MV, PV) is False
    assert gateway.accepted_series(EXP, "voltage", BASE, END, PV) == []
    assert gateway.has_policy_rows(PV) is False


def test_columns_that_were_never_written_read_as_empty(gateway, seeder):
    """Every reading excluded with no raw value: the table has no `value` or `value_raw` column."""
    seeder.write(
        "\n".join(
            [
                _numeric_line("voltage", _at(1), "excluded"),
                _state_line("process_state", _at(1), "excluded"),
            ]
        )
    )

    assert gateway.raw_series(EXP, "voltage", BASE, END, PV) == []
    assert gateway.state_events(EXP, "process_state", BASE, END, PV) == []
    assert gateway.metric_series(EXP, "power_computed", MV, PV, BASE, END) == []


def test_empty_windows_and_a_window_with_no_rows_give_empty_lists(gateway, seeder):
    _seed_everything(seeder)
    later = BASE + timedelta(hours=1)

    assert gateway.raw_series(EXP, "voltage", later, later + timedelta(seconds=5), PV) == []
    assert gateway.state_events(EXP, "process_state", later, later + timedelta(seconds=5), PV) == []
    assert (
        gateway.metric_series(EXP, "power_computed", MV, PV, later, later + timedelta(seconds=5))
        == []
    )
    # An empty or inverted window [t, t) is answered without a query (Core refuses the filter).
    queries = gateway.queries
    assert gateway.raw_series(EXP, "voltage", BASE, BASE, PV) == []
    assert gateway.state_events(EXP, "process_state", END, BASE, PV) == []
    assert gateway.metric_series(EXP, "power_computed", MV, PV, BASE, BASE) == []
    assert gateway.queries == queries


def test_the_gateway_is_read_only_and_creates_nothing(gateway, seeder, stack):
    host, token, name = stack
    _seed_everything(seeder)
    own = {attr for attr in vars(CompareGateway) if not attr.startswith("__")}
    assert not any("write" in attr or "create" in attr or "delete" in attr for attr in own)

    databases = list_databases(host, token)
    tables = gateway.tables()
    counts = gateway.input_counts(BASE, END)
    assert set(counts) == set(INPUT_TABLES)

    gateway.raw_series(EXP, "voltage", BASE, END, PV)
    gateway.state_events(EXP, "process_state", BASE, END, PV)
    gateway.metric_series(EXP, "power_computed", MV, PV, BASE, END)
    gateway.has_metrics_rows(MV, PV)
    gateway.has_policy_rows(PV)
    gateway.accepted_series(EXP, "voltage", BASE, END, PV)

    assert list_databases(host, token) == databases
    assert gateway.tables() == tables
    assert gateway.input_counts(BASE, END) == counts
    assert gateway.queries > 0


def test_a_missing_database_raises_database_missing_and_is_never_created(influx_client):  # noqa: ARG001
    env = init_influx.load_env()
    host, token = env["INFLUX_HOST"], env["INFLUX_TOKEN"]
    missing = f"t2_cmp_missing_{uuid.uuid4().hex[:8]}"
    assert DatabaseMissing is MetricsDatabaseMissing
    gw = CompareGateway(host, token, missing)
    try:
        with pytest.raises(DatabaseMissing) as refusal:
            gw.require_database()
        assert refusal.value.database == missing
        # A read on a missing database fails loudly and creates nothing.
        with pytest.raises(QueryFailed):
            gw.raw_series(EXP, "voltage", BASE, END, PV)
        with pytest.raises(QueryFailed):
            gw.has_metrics_rows(MV, PV)
    finally:
        gw.close()

    assert missing not in list_databases(host, token)


def test_require_database_passes_for_an_existing_database(gateway):
    gateway.require_database()
    gateway.require_database()  # cached after the first check


# --------------------------------------------------------------------------------- Postgres side

SECOND_EXPERIMENT = {
    "experiment_id": "EXP_FIXTURE_2",
    "start_time": "2026-05-11T09:00:00+02:00",  # not UTC on purpose
    "end_time": "2026-05-11T09:10:00+02:00",
    "duration_s": 600,
    "current_setpoint_nominal_A": 200.0,
    "air_flow_nominal_m3h": None,
    "solvent_flow_nominal_Lmin": 8.0,
    "operator": None,
    "sorbent_batch": None,
    "notes": None,
}
METRIC_VALUES = [
    ("mean_power_kw", 12.5, "kW", 0.9, "partial"),
    ("capture_efficiency_mean", 0.8, "fraction", 1.0, "complete"),
    ("sec_kwh_per_kg", None, "kWh/kg", 0.0, "none"),
    ("completeness", 0.99, "fraction", None, None),
]


def _create_schema(postgres_conn) -> tuple[str, dict]:
    schema = f"test_compare_store_{uuid.uuid4().hex[:12]}"
    with postgres_conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    postgres_conn.commit()
    base = migrate.connect_kwargs(migrate.load_env())
    return schema, {**base, "options": f"-c search_path={schema}"}


def _drop_schema(postgres_conn, schema: str) -> None:
    with postgres_conn.cursor() as cur:
        cur.execute(
            psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                psycopg.sql.Identifier(schema)
            )
        )
    postgres_conn.commit()


def _metric_rows(experiment_id: str, version: str, scale: float = 1.0) -> list[dict]:
    return [
        {
            "experiment_id": experiment_id,
            "metrics_version": version,
            "policy_version": PV,
            "metric": metric,
            "value": None if value is None else value * scale,
            "unit": unit,
            "coverage": coverage,
            "status": status,
        }
        for metric, value, unit, coverage, status in METRIC_VALUES
    ]


@pytest.fixture
def pg(postgres_conn, tmp_path):
    """A connection to a fresh, fully migrated schema with the fixture experiments loaded.

    EXP_FIXTURE comes from `tests/fixtures/metrics/experiments.json`; `EXP_FIXTURE_2` is written
    to a temporary file with null setpoint, operator, batch and notes and a +02:00 offset.
    """
    schema, kwargs = _create_schema(postgres_conn)
    conn = None
    try:
        assert run_migrations(kwargs) == ["0001", "0002", "0003"]
        experiments = json.loads(EXPERIMENTS_FIXTURE.read_text(encoding="utf-8"))
        path = tmp_path / "experiments.json"
        path.write_text(json.dumps([*experiments, SECOND_EXPERIMENT]), encoding="utf-8")
        assert load_experiments(kwargs, path) == 2
        conn = pg_connect(migrate.connect_kwargs(migrate.load_env()), schema)
        yield conn
    finally:
        if conn is not None:
            conn.close()
        _drop_schema(postgres_conn, schema)


def _first_id() -> str:
    return json.loads(EXPERIMENTS_FIXTURE.read_text(encoding="utf-8"))[0]["experiment_id"]


@pytest.mark.postgres
def test_s5_11_experiment_rows_return_every_column_with_nulls_and_aware_utc_times(pg):
    first = json.loads(EXPERIMENTS_FIXTURE.read_text(encoding="utf-8"))[0]
    assert pg_check(pg) is None

    rows = experiment_rows(pg, [first["experiment_id"], "EXP_FIXTURE_2"])

    assert set(rows) == {first["experiment_id"], "EXP_FIXTURE_2"}
    expected_columns = {
        "experiment_id",
        "start_time",
        "end_time",
        "duration_s",
        "current_setpoint_nominal_a",
        "air_flow_nominal_m3h",
        "solvent_flow_nominal_lmin",
        "operator",
        "sorbent_batch",
        "notes",
    }
    assert all(set(row) == expected_columns for row in rows.values())

    one = rows[first["experiment_id"]]
    assert one["start_time"] == datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC)
    assert one["end_time"] == datetime(2026, 5, 4, 8, 10, 0, tzinfo=UTC)
    assert one["duration_s"] == 600
    assert one["current_setpoint_nominal_a"] == 150.0
    assert one["air_flow_nominal_m3h"] == 1200.0
    assert one["solvent_flow_nominal_lmin"] == 8.0
    assert one["operator"] == first["operator"]
    assert one["sorbent_batch"] == first["sorbent_batch"]
    assert one["notes"] == first["notes"]

    two = rows["EXP_FIXTURE_2"]
    assert two["start_time"] == datetime(2026, 5, 11, 7, 0, 0, tzinfo=UTC)
    assert two["end_time"] == datetime(2026, 5, 11, 7, 10, 0, tzinfo=UTC)
    assert two["current_setpoint_nominal_a"] == 200.0
    assert two["air_flow_nominal_m3h"] is None
    assert two["operator"] is None
    assert two["sorbent_batch"] is None
    assert two["notes"] is None
    for row in rows.values():
        for name in ("start_time", "end_time"):
            assert row[name].tzinfo is not None
            assert row[name].utcoffset() == timedelta(0)


@pytest.mark.postgres
def test_s5_11_times_are_utc_whatever_the_session_time_zone_is(pg):
    with pg.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Tokyo'")

    rows = experiment_rows(pg, ["EXP_FIXTURE_2"])

    start = rows["EXP_FIXTURE_2"]["start_time"]
    assert start == datetime(2026, 5, 11, 7, 0, 0, tzinfo=UTC)
    assert start.utcoffset() == timedelta(0)


@pytest.mark.postgres
def test_experiment_rows_leave_out_unknown_ids_and_take_an_empty_list(pg):
    assert experiment_rows(pg, ["EXP_NOT_LOADED"]) == {}
    assert experiment_rows(pg, []) == {}
    assert set(experiment_rows(pg, [_first_id(), "EXP_NOT_LOADED"])) == {_first_id()}


@pytest.mark.postgres
def test_s5_11_metric_rows_are_those_of_the_asked_version_only_nulls_kept(pg):
    first = _first_id()
    write_postgres(
        pg,
        _metric_rows(first, MV)
        + _metric_rows("EXP_FIXTURE_2", MV, scale=2.0)
        + _metric_rows(first, MV_OTHER, scale=10.0),
        [],
    )

    rows = experiment_metric_rows(pg, MV, [first, "EXP_FIXTURE_2"])

    assert set(rows) == {first, "EXP_FIXTURE_2"}
    assert set(rows[first]) == {name for name, *_ in METRIC_VALUES}
    assert rows[first]["mean_power_kw"] == {
        "value": 12.5,
        "unit": "kW",
        "coverage": 0.9,
        "status": "partial",
    }
    assert rows["EXP_FIXTURE_2"]["mean_power_kw"]["value"] == 25.0
    assert rows[first]["sec_kwh_per_kg"] == {
        "value": None,
        "unit": "kWh/kg",
        "coverage": 0.0,
        "status": "none",
    }
    assert rows[first]["completeness"] == {
        "value": 0.99,
        "unit": "fraction",
        "coverage": None,
        "status": None,
    }
    assert all(
        set(m) == {"value", "unit", "coverage", "status"} for e in rows.values() for m in e.values()
    )

    other = experiment_metric_rows(pg, MV_OTHER, [first, "EXP_FIXTURE_2"])
    assert set(other) == {first}  # the other version has rows for one experiment only
    assert other[first]["mean_power_kw"]["value"] == 125.0


@pytest.mark.postgres
def test_metric_rows_for_a_version_with_no_rows_or_no_ids_are_empty(pg):
    write_postgres(pg, _metric_rows(_first_id(), MV), [])

    assert experiment_metric_rows(pg, "mv-none", [_first_id()]) == {}
    assert experiment_metric_rows(pg, MV, []) == {}
    assert experiment_metric_rows(pg, MV, ["EXP_NOT_LOADED"]) == {}
    assert set(experiment_metric_rows(pg, MV, [_first_id(), "EXP_FIXTURE_2"])) == {_first_id()}


@pytest.mark.postgres
def test_the_postgres_reads_change_nothing(pg):
    write_postgres(pg, _metric_rows(_first_id(), MV), [])

    def dump() -> list[list[tuple]]:
        with pg.cursor() as cur:
            out = []
            for table in ("experiment", "experiment_metrics", "signal_quality"):
                cur.execute(f"SELECT * FROM {table} ORDER BY 1, 2")  # noqa: S608 - fixed names
                out.append(cur.fetchall())
            return out

    before = dump()
    experiment_rows(pg, [_first_id(), "EXP_FIXTURE_2"])
    experiment_metric_rows(pg, MV, [_first_id(), "EXP_FIXTURE_2"])

    assert dump() == before
