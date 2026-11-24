"""Integration tests for `pipeline.metrics_store` (M4 T2; S4.14 and S4.15).

Two kinds of throwaway, both created and dropped in a fixture's `finally`:

- one InfluxDB database per test (Core allows five databases and three already exist, so at most
  one extra exists at any moment), seeded with line protocol in the column layout the cleaning
  writes (`pipeline/cleaning_influx.py`: tags `experiment_id, source, signal, policy_version`;
  fields `value_raw`, `value` only when accepted, `quality`, `verdict`, `reason`, `flags`);
- one Postgres schema with the real `migrations/` applied and two `experiment` rows loaded.

Nothing here touches `dac_raw`, `dac_rollup` or `dac_pinned`.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

import scripts.init_influx as init_influx
import scripts.migrate as migrate
from pipeline.ingest import _tag, _text
from pipeline.ingest_influx import WriteFailed, list_databases
from pipeline.metrics_store import (
    INPUT_TABLES,
    DatabaseMissing,
    MetricsGateway,
    count_rows,
    missing_experiments,
    pg_check,
    pg_connect,
    upsert_metrics,
    upsert_quality,
    write_postgres,
)
from pipeline.pg_migrate import MIGRATIONS_DIR, run_migrations
from pipeline.signals import DECLARED_SIGNALS, STATE_SIGNALS

BASE = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)
BASE_NS = int(BASE.timestamp()) * 1_000_000_000
SECOND = 1_000_000_000
EXP = "EXP_T2"
OTHER_EXP = "EXP_T2_OTHER"
PV = "pv-test-1"
PV_OTHER = "pv-test-2"
MV = "mv-test-1"
END = BASE + timedelta(seconds=10)


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
def gateway(influx_client):  # noqa: ARG001 - influx_client: skip when InfluxDB is unreachable
    env = init_influx.load_env()
    host, token = env["INFLUX_HOST"], env["INFLUX_TOKEN"]
    name = f"t2_metrics_{uuid.uuid4().hex[:8]}"
    _http("POST", f"{host}/api/v3/configure/database", token, {"db": name})
    gw = MetricsGateway(host, token, name)
    try:
        yield gw
    finally:
        gw.close()
        _http("DELETE", f"{host}/api/v3/configure/database?db={name}", token)


def _processed_line(
    signal: str,
    t_ns: int,
    verdict: str = "accepted",
    quality: str = "GOOD",
    value: float | str | None = None,
    *,
    policy_version: str = PV,
    experiment_id: str = EXP,
    source: str = "hydrolyzer",
    table: str = "readings_processed",
) -> str:
    """One processed row as cleaning writes it: `value` only when accepted, always `verdict`."""
    tags = (
        f"{table},experiment_id={_tag(experiment_id)},source={_tag(source)},"
        f"signal={_tag(signal)},policy_version={_tag(policy_version)}"
    )
    fields = []
    if value is not None:
        literal = _text(value) if isinstance(value, str) else repr(float(value))
        fields.append(f"value_raw={literal}")
        if verdict == "accepted":
            fields.append(f"value={literal}")
    fields += [
        f"quality={_text(quality)}",
        f"verdict={_text(verdict)}",
        f"reason={_text('' if verdict == 'accepted' else 'spike')}",
        'flags=""',
    ]
    if table == "state_intervals":
        fields += ["end_ns=0i", "seconds=1.0"]
    return f"{tags} {','.join(fields)} {t_ns}"


def _write(gw: MetricsGateway, lines: list[str]) -> None:
    gw.write("\n".join(lines))


def _raw_line(table: str, t_ns: int, value: float | str = 1.0) -> str:
    literal = _text(value) if isinstance(value, str) else repr(float(value))
    return (
        f"{table},experiment_id={EXP},source=hydrolyzer,signal=voltage "
        f'value={literal},quality="GOOD" {t_ns}'
    )


def _at(seconds: int) -> int:
    return BASE_NS + seconds * SECOND


def test_a_missing_database_has_nothing_to_read(gateway):
    assert gateway.tables() == set()
    assert gateway.accepted_series(EXP, "voltage", BASE, END, PV) == []
    assert gateway.quality_counts(EXP, BASE, END, PV) == []
    assert gateway.has_policy_rows(PV) is False
    assert gateway.input_counts(BASE, END) == dict.fromkeys(INPUT_TABLES, 0)
    assert gateway.count_series(EXP, "power_computed", MV, BASE, END) == 0


def test_s4_15_accepted_series_reads_only_accepted_rows_of_one_version_in_time_order(gateway):
    """S4.15. Two policy versions, accepted and excluded rows, another experiment and signal,
    the window edges, and a row that was accepted and later excluded (Core keeps its old
    `value`, so the verdict must decide)."""
    sum_ = 0.1 + 0.2  # 0.30000000000000004: the read must give back the exact float
    _write(
        gateway,
        [
            # Out of time order on purpose.
            _processed_line("voltage", _at(3), value=sum_),
            _processed_line("voltage", _at(1), value=-0.0),
            _processed_line("voltage", _at(0), value=1.5),  # start is included
            _processed_line("voltage", _at(2), "excluded", "BAD", value=99.0),
            _processed_line("voltage", _at(5), "excluded", "UNCERTAIN"),  # no value at all
            _processed_line("voltage", _at(10), value=7.0),  # end is excluded
            _processed_line("voltage", _at(1), value=1000.0, policy_version=PV_OTHER),
            _processed_line("voltage", _at(1), value=2000.0, experiment_id=OTHER_EXP),
            _processed_line("current", _at(1), value=3000.0),
            _processed_line("voltage", _at(4), value=5.0),  # accepted first ...
        ],
    )
    _write(
        gateway, [_processed_line("voltage", _at(4), "excluded", "BAD", value=5.0)]
    )  # ... then not

    series = gateway.accepted_series(EXP, "voltage", BASE, END, PV)

    assert series == [(_at(0), 1.5), (_at(1), -0.0), (_at(3), sum_)]
    assert series[2][1] == sum_
    assert gateway.accepted_series(EXP, "voltage", BASE, END, PV_OTHER) == [(_at(1), 1000.0)]
    assert gateway.accepted_series(EXP, "voltage", BASE, END, "no-such-version") == []
    # A window that starts after the first row and ends exactly at the last accepted one.
    assert gateway.accepted_series(EXP, "voltage", BASE + timedelta(seconds=1), END, PV) == [
        (_at(1), -0.0),
        (_at(3), sum_),
    ]
    assert gateway.accepted_series(EXP, "voltage", BASE, BASE + timedelta(seconds=3), PV) == [
        (_at(0), 1.5),
        (_at(1), -0.0),
    ]


def test_accepted_series_is_empty_when_no_row_ever_carried_a_value(gateway):
    """Every reading excluded: the table has no `value` column at all, and that is not an error."""
    _write(gateway, [_processed_line("voltage", _at(1), "excluded", "BAD")])

    assert gateway.accepted_series(EXP, "voltage", BASE, END, PV) == []


def test_quality_counts_group_both_processed_tables_by_version_and_window(gateway):
    state = {"source": "plant", "table": "state_intervals"}
    _write(
        gateway,
        [
            _processed_line("voltage", _at(0), value=1.0),
            _processed_line("voltage", _at(1), value=2.0),
            _processed_line("voltage", _at(2), value=3.0),
            _processed_line("voltage", _at(3), "excluded", "BAD"),
            _processed_line("voltage", _at(4), "excluded", "UNCERTAIN", value=9.0),
            _processed_line("current", _at(0), value=1.0),
            _processed_line("current", _at(1), value=1.0),
            _processed_line("valve_state", _at(0), value="open", **state),
            _processed_line("valve_state", _at(1), value="open", **state),
            _processed_line("valve_state", _at(2), "excluded", "BAD", **state),
            # Not counted: another version, another experiment, exactly at the window end.
            _processed_line("voltage", _at(0), value=1.0, policy_version=PV_OTHER),
            _processed_line("voltage", _at(0), value=1.0, experiment_id=OTHER_EXP),
            _processed_line("voltage", _at(10), value=1.0),
        ],
    )

    counts = gateway.quality_counts(EXP, BASE, END, PV)

    assert [(r["source"], r["signal"], r["quality"], r["verdict"], r["count"]) for r in counts] == [
        ("hydrolyzer", "current", "GOOD", "accepted", 2),
        ("hydrolyzer", "voltage", "BAD", "excluded", 1),
        ("hydrolyzer", "voltage", "GOOD", "accepted", 3),
        ("hydrolyzer", "voltage", "UNCERTAIN", "excluded", 1),
        ("plant", "valve_state", "BAD", "excluded", 1),
        ("plant", "valve_state", "GOOD", "accepted", 2),
    ]
    assert all(set(row) == {"source", "signal", "quality", "verdict", "count"} for row in counts)
    assert all(isinstance(row["count"], int) for row in counts)


def test_has_policy_rows_tells_versions_apart(gateway):
    assert gateway.has_policy_rows(PV) is False  # no readings_processed table yet
    _write(gateway, [_processed_line("voltage", _at(0), value=1.0)])

    assert gateway.has_policy_rows(PV) is True
    assert gateway.has_policy_rows(PV_OTHER) is False


def test_input_counts_count_the_six_input_tables_in_the_window(gateway):
    _write(
        gateway,
        [
            _raw_line("readings_numeric", _at(0)),
            _raw_line("readings_numeric", _at(9)),
            _raw_line("readings_numeric", _at(10)),  # at the window end: not counted
            _raw_line("readings_state", _at(1), "open"),
            _processed_line("voltage", _at(1), value=1.0),
            _processed_line("voltage", _at(2), value=1.0),
            _processed_line("voltage", _at(3), value=1.0),
            _processed_line(
                "valve_state", _at(1), value="open", source="plant", table="state_intervals"
            ),
            (
                f"quality_intervals,experiment_id={EXP},source=hydrolyzer,signal=voltage,"
                f"policy_version={PV},kind=gap end_ns=1i,seconds=1.0,points=0i {_at(5)}"
            ),
            (
                f"quality_intervals,experiment_id={EXP},source=hydrolyzer,signal=voltage,"
                f"policy_version={PV},kind=flatline end_ns=1i,seconds=1.0,points=3i {_at(6)}"
            ),
        ],
    )  # fmt: skip

    counts = gateway.input_counts(BASE, END)

    assert counts == {
        "readings_numeric": 2,
        "readings_state": 1,
        "readings_conflicts": 0,  # the table does not exist
        "readings_processed": 3,
        "state_intervals": 1,
        "quality_intervals": 2,
    }
    assert {"readings_numeric", "readings_processed", "quality_intervals"} <= gateway.tables()


def test_s4_15_a_written_series_reads_back_with_the_same_count(gateway):
    """S4.15, second half. Written in batches of 3 (8 points); a rewrite changes nothing."""
    gateway.batch_size = 3
    series = [
        (_at(i), v) for i, v in enumerate([0.1 + 0.2, -0.0, 1e-300, 5e15, 2.5, -7.25, 0.0, 1.0])
    ]

    assert gateway.write_series(EXP, "power_computed", MV, PV, series) == 8
    assert gateway.count_series(EXP, "power_computed", MV, BASE, END) == len(series)
    gateway.write_series(EXP, "power_computed", MV, PV, series)  # same keys, same values
    assert gateway.count_series(EXP, "power_computed", MV, BASE, END) == len(series)

    stored = gateway._client.query(
        "SELECT time, value FROM metrics_series WHERE metric = 'power_computed' ORDER BY time",
        language="sql",
    )
    values = stored.column("value").to_pylist()
    assert values == [v for _, v in series]
    assert [math.copysign(1.0, v) for v in values] == [math.copysign(1.0, v) for _, v in series]
    # Tags, window edges and the other series are told apart.
    assert gateway.count_series(EXP, "power_computed", MV, BASE, BASE + timedelta(seconds=3)) == 3
    assert gateway.count_series(EXP, "power_computed", "other-version", BASE, END) == 0
    assert gateway.count_series(EXP, "capture_rate", MV, BASE, END) == 0
    assert gateway.count_series(OTHER_EXP, "power_computed", MV, BASE, END) == 0
    assert gateway.write_series(EXP, "capture_rate", MV, PV, []) == 0


def test_write_series_checks_every_value_before_sending_any(gateway):
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            gateway.write_series(EXP, "power_computed", MV, PV, [(_at(0), 1.0), (_at(1), bad)])
    with pytest.raises(ValueError, match="integer"):
        gateway.write_series(EXP, "power_computed", MV, PV, [(1.5, 1.0)])

    assert gateway.count_series(EXP, "power_computed", MV, BASE, END) == 0
    assert "metrics_series" not in gateway.tables()


def test_write_series_retries_a_connection_error_but_not_a_refused_line(gateway):
    gateway._sleep = lambda seconds: None
    real_write = gateway.write
    calls = []

    def flaky(body: str) -> None:
        calls.append(body)
        if len(calls) < 3:
            raise ConnectionError("reset")
        real_write(body)

    gateway.write = flaky
    series = [(_at(0), 1.0), (_at(1), 2.0)]
    gateway.write_series(EXP, "power_computed", MV, PV, series)
    assert len(calls) == 3
    assert gateway.count_series(EXP, "power_computed", MV, BASE, END) == 2

    class Refused(Exception):
        status = 400

    attempts = []

    def refuse(body: str) -> None:
        attempts.append(body)
        raise Refused("bad line")

    gateway.write = refuse
    with pytest.raises(WriteFailed) as failure:
        gateway.write_series(EXP, "capture_rate", MV, PV, series)
    assert failure.value.attempts == 1
    assert len(attempts) == 1
    assert gateway.count_series(EXP, "capture_rate", MV, BASE, END) == 0


def test_write_series_never_creates_a_missing_database(influx_client):  # noqa: ARG001
    env = init_influx.load_env()
    host, token = env["INFLUX_HOST"], env["INFLUX_TOKEN"]
    missing = f"t2_missing_{uuid.uuid4().hex[:8]}"
    gw = MetricsGateway(host, token, missing)
    try:
        with pytest.raises(DatabaseMissing):
            gw.write_series(EXP, "power_computed", MV, PV, [(_at(0), 1.0)])
    finally:
        gw.close()

    assert missing not in list_databases(host, token)


# --------------------------------------------------------------------------------- Postgres side

METRIC_NAMES = [
    ("energy_kwh", "kWh"),
    ("energy_logged_kwh", "kWh"),
    ("energy_relative_difference", "fraction"),
    ("mean_power_kw", "kW"),
    ("capture_efficiency_mean", "fraction"),
    ("co2_captured_kg", "kg"),
    ("co2_inlet_kg", "kg"),
    ("capture_rate_mean_kg_h", "kg/h"),
    ("sec_kwh_per_kg", "kWh/kg"),
    ("completeness", "fraction"),
    ("valid_fraction", "fraction"),
    ("bad_fraction", "fraction"),
    ("uncertain_fraction", "fraction"),
]
SHARES = {"completeness", "valid_fraction", "bad_fraction", "uncertain_fraction"}


def metric_rows(experiment_id: str = EXP, *, scale: float = 1.0, version: str = MV) -> list[dict]:
    """13 metric rows; `sec_kwh_per_kg` is null/'none' and the four shares have no coverage."""
    rows = []
    for i, (name, unit) in enumerate(METRIC_NAMES):
        null = name == "sec_kwh_per_kg"
        share = name in SHARES
        rows.append(
            {
                "experiment_id": experiment_id,
                "metrics_version": version,
                "policy_version": PV,
                "metric": name,
                "value": None if null else (i + 1) * 0.1 * scale,
                "unit": unit,
                "coverage": None if share else (0.0 if null else 0.5 + i / 100),
                "status": None if share else ("none" if null else "partial"),
            }
        )
    return rows


def quality_rows(experiment_id: str = EXP, *, scale: int = 1, version: str = MV) -> list[dict]:
    """25 signal rows (the declared pairs); state signals have no interval and no expectation."""
    rows = []
    for source, signals in DECLARED_SIGNALS.items():
        for signal in signals:
            state = signal in STATE_SIGNALS
            rows.append(
                {
                    "experiment_id": experiment_id,
                    "metrics_version": version,
                    "policy_version": PV,
                    "source": source,
                    "signal": signal,
                    "nominal_interval_s": None if state else 1.0,
                    "present": 10 * scale,
                    "expected": None if state else 12,
                    "accepted": 8 * scale,
                    "bad": 1,
                    "uncertain": 1,
                    "completeness": None if state else 10 * scale / 12,
                    "valid_fraction": 0.8,
                    "bad_fraction": 0.1,
                    "uncertain_fraction": 0.1,
                }
            )
    return rows


def _create_schema(postgres_conn) -> tuple[str, dict]:
    schema = f"test_metrics_store_{uuid.uuid4().hex[:12]}"
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


@pytest.fixture
def pg(postgres_conn):
    """A connection to a fresh, fully migrated schema with two `experiment` rows."""
    schema, kwargs = _create_schema(postgres_conn)
    conn = None
    try:
        assert run_migrations(kwargs) == ["0001", "0002", "0003"]
        conn = pg_connect(migrate.connect_kwargs(migrate.load_env()), schema)
        with conn.cursor() as cur:
            for experiment_id, setpoint in ((EXP, 12.5), (OTHER_EXP, 40.0)):
                cur.execute(
                    "INSERT INTO experiment (experiment_id, start_time, end_time, duration_s, "
                    "current_setpoint_nominal_a) VALUES (%s, %s, %s, 7200, %s)",
                    (experiment_id, BASE, BASE + timedelta(hours=2), setpoint),
                )
        yield conn
    finally:
        if conn is not None:
            conn.close()
        _drop_schema(postgres_conn, schema)


def _fetch(conn, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _stored_metrics(conn, experiment_id: str = EXP) -> list[tuple]:
    return _fetch(
        conn,
        "SELECT metric, value, unit, coverage, status FROM experiment_metrics "
        "WHERE experiment_id = %s AND metrics_version = %s ORDER BY metric",
        (experiment_id, MV),
    )


@pytest.mark.postgres
def test_s4_14_two_writes_leave_one_row_per_metric_and_per_signal(pg):
    """S4.14, first two parts: 13 and 25 rows after writing twice, with the values as written,
    and a join to `experiment` returning the setpoint beside each metric."""
    metrics, quality = metric_rows(), quality_rows()

    write_postgres(pg, metrics, quality)
    write_postgres(pg, metrics, quality)

    assert count_rows(pg, "experiment_metrics", MV) == {EXP: 13}
    assert count_rows(pg, "signal_quality", MV) == {EXP: 25}
    assert _stored_metrics(pg) == sorted(
        (m["metric"], m["value"], m["unit"], m["coverage"], m["status"]) for m in metrics
    )
    stored_quality = _fetch(
        pg,
        "SELECT source, signal, nominal_interval_s, present, expected, accepted, bad, uncertain, "
        "completeness, valid_fraction, bad_fraction, uncertain_fraction "
        "FROM signal_quality WHERE experiment_id = %s ORDER BY source, signal",
        (EXP,),
    )
    assert stored_quality == sorted(
        (
            q["source"], q["signal"], q["nominal_interval_s"], q["present"], q["expected"],
            q["accepted"], q["bad"], q["uncertain"], q["completeness"], q["valid_fraction"],
            q["bad_fraction"], q["uncertain_fraction"],
        )
        for q in quality
    )  # fmt: skip
    joined = _fetch(
        pg,
        "SELECT m.metric, e.current_setpoint_nominal_a FROM experiment_metrics m "
        "JOIN experiment e ON e.experiment_id = m.experiment_id WHERE m.experiment_id = %s",
        (EXP,),
    )
    assert len(joined) == 13
    assert {setpoint for _, setpoint in joined} == {12.5}
    assert {name for name, _ in joined} == {name for name, _ in METRIC_NAMES}


@pytest.mark.postgres
def test_s4_14_a_row_for_an_unknown_experiment_is_refused_and_nothing_of_the_call_is_kept(pg):
    write_postgres(pg, metric_rows(), quality_rows())
    before = (_stored_metrics(pg), count_rows(pg, "signal_quality", MV))

    # The unknown experiment's rows come last, after valid changed rows of a known one.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        write_postgres(
            pg,
            metric_rows(scale=2.0) + metric_rows("EXP_NOT_LOADED"),
            quality_rows(scale=2),
        )
    assert (_stored_metrics(pg), count_rows(pg, "signal_quality", MV)) == before

    # Same, with the failing row in the second table: the first table's changes are rolled back.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        write_postgres(
            pg, metric_rows(scale=3.0), quality_rows(scale=3) + quality_rows("EXP_NOT_LOADED")
        )
    assert (_stored_metrics(pg), count_rows(pg, "signal_quality", MV)) == before
    assert count_rows(pg, "experiment_metrics", MV) == {EXP: 13}

    # A first call that fails keeps nothing at all.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        write_postgres(pg, metric_rows(OTHER_EXP), quality_rows("EXP_NOT_LOADED"))
    assert count_rows(pg, "experiment_metrics", MV) == {EXP: 13}


@pytest.mark.postgres
def test_a_rerun_overwrites_by_key_and_other_versions_and_experiments_are_separate(pg):
    write_postgres(pg, metric_rows(), quality_rows())
    changed = metric_rows(scale=2.0)
    upsert_metrics(pg, changed)
    upsert_quality(pg, quality_rows(scale=2))
    write_postgres(pg, metric_rows(OTHER_EXP), quality_rows(OTHER_EXP))
    write_postgres(pg, metric_rows(version="mv-test-0"), quality_rows(version="mv-test-0"))

    assert _stored_metrics(pg) == sorted(
        (m["metric"], m["value"], m["unit"], m["coverage"], m["status"]) for m in changed
    )
    assert _fetch(pg, "SELECT DISTINCT present FROM signal_quality WHERE experiment_id = %s AND "
                  "metrics_version = %s", (EXP, MV)) == [(20,)]  # fmt: skip
    assert count_rows(pg, "experiment_metrics", MV) == {EXP: 13, OTHER_EXP: 13}
    assert count_rows(pg, "signal_quality", MV) == {EXP: 25, OTHER_EXP: 25}
    assert count_rows(pg, "experiment_metrics", "mv-test-0") == {EXP: 13}
    assert count_rows(pg, "experiment_metrics", "mv-none") == {}
    with pytest.raises(ValueError, match="unknown table"):
        count_rows(pg, "experiment", MV)


@pytest.mark.postgres
def test_the_status_check_and_row_shape_are_enforced(pg):
    bad_status = metric_rows()
    bad_status[0]["status"] = "bogus"
    with pytest.raises(psycopg.errors.CheckViolation):
        write_postgres(pg, bad_status, [])
    assert count_rows(pg, "experiment_metrics", MV) == {}

    missing_key = metric_rows()
    del missing_key[1]["unit"]
    with pytest.raises(ValueError, match="missing"):
        write_postgres(pg, missing_key, quality_rows())
    extra_key = quality_rows()
    extra_key[0]["surplus"] = 1
    with pytest.raises(ValueError, match="extra"):
        write_postgres(pg, metric_rows(), extra_key)
    assert count_rows(pg, "experiment_metrics", MV) == {}
    assert count_rows(pg, "signal_quality", MV) == {}


@pytest.mark.postgres
def test_missing_experiments_names_the_ids_without_a_row(pg):
    assert missing_experiments(pg, [EXP, "EXP_X", OTHER_EXP, "EXP_Y"]) == ["EXP_X", "EXP_Y"]
    assert missing_experiments(pg, [EXP, OTHER_EXP]) == []
    assert missing_experiments(pg, []) == []


@pytest.mark.postgres
def test_pg_check_accepts_a_migrated_schema_and_refuses_one_without_0003(
    pg, postgres_conn, tmp_path
):
    assert pg_check(pg) is None

    schema, kwargs = _create_schema(postgres_conn)
    conn = None
    try:
        directory = tmp_path / "migrations"
        directory.mkdir()
        for name in ("0001_experiment_table.sql", "0002_experiment_provenance.sql"):
            (directory / name).write_bytes((MIGRATIONS_DIR / name).read_bytes())
        conn = pg_connect(migrate.connect_kwargs(migrate.load_env()), schema)

        detail = pg_check(conn)  # nothing migrated yet
        assert detail is not None
        assert "experiment_metrics" in detail

        assert run_migrations(kwargs, directory=directory) == ["0001", "0002"]
        detail = pg_check(conn)  # 0001 and 0002 only
        assert detail is not None
        assert "experiment_metrics" in detail
        assert "signal_quality" in detail
        assert "0003" in detail
        assert detail.startswith("missing table(s) experiment_metrics, signal_quality:")

        assert run_migrations(kwargs) == ["0003"]  # the real directory adds the missing one
        assert pg_check(conn) is None
    finally:
        if conn is not None:
            conn.close()
        _drop_schema(postgres_conn, schema)


@pytest.mark.postgres
def test_pg_connect_refuses_a_schema_name_that_is_not_an_identifier():
    with pytest.raises(ValueError, match="identifier"):
        pg_connect({"host": "localhost"}, "public; DROP SCHEMA x")
