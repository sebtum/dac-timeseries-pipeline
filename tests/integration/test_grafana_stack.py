"""Grafana against the real stack: provisioned datasources and the checker (S6.1, S6.6, S6.7).

These need a running Grafana (`python scripts/verify_stack.py up`, or `docker compose up -d
grafana` on the dev stack) and skip, never fail, when it is unreachable; CI treats a skip as a
failure. The checker tests run the test dashboard in `tests/fixtures/grafana` against a throwaway
InfluxDB database holding `data.lp`, a throwaway Postgres schema with `experiments.json` and a
temporary Grafana datasource on that database, all removed afterwards. `dac_raw` is never touched.
Core allows five databases and four exist, so a test holds at most one extra one.

S6.2 (`up` twice) and S6.3 (the private project, ports, dev containers untouched) are QA steps
that start and stop real containers; their pure parts are in `tests/unit/test_verify_stack.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import jsonschema
import pytest

from tests.e2e.grafana_helpers import (
    GRAFANA_FIXTURE,
    REPO_ROOT,
    drop_pg_schema,
    prepare_pg_schema,
    require_grafana,
    run_checker,
    temp_influx_datasource,
    write_line_protocol,
)
from tests.e2e.helpers import create_database, drop_database, query
from tests.fixtures.grafana.make_fixture import lines

pytestmark = pytest.mark.grafana


@pytest.fixture(scope="module")
def grafana():
    return require_grafana()


DASHBOARD = GRAFANA_FIXTURE / "dashboard.json"
CONTRACT = json.loads(
    (REPO_ROOT / "contracts" / "dashboard_check.schema.json").read_text(encoding="utf-8")
)
WINDOWS = {
    "EXP_001": ("2026-05-04T08:00:00Z", "2026-05-04T08:01:00Z"),
    "EXP_002": ("2026-05-11T09:00:00Z", "2026-05-11T09:01:00Z"),
}
PANELS = ("Experiments", "Readings: ${signal}", "Overlay: ${signal}", "Gaps and stuck stretches")


# ----------------------------------------------------------------------------- S6.1


def test_s6_1_grafana_is_ok_and_serves_exactly_the_two_provisioned_datasources(grafana):
    health = grafana.health()
    assert health["database"] == "ok"
    assert grafana.version() == health["version"]

    assert sorted(d["uid"] for d in grafana.datasources()) == ["influx-dac", "pg-dac"]
    for uid in ("influx-dac", "pg-dac"):
        assert grafana.datasource_health(uid)["status"] == "OK", uid


def test_the_provisioned_datasources_use_the_pinned_types_and_are_read_only(grafana):
    by_uid = {d["uid"]: d for d in grafana.datasources()}
    assert by_uid["influx-dac"]["type"] == "influxdb"
    assert by_uid["influx-dac"]["jsonData"]["version"] == "SQL"
    assert by_uid["influx-dac"]["jsonData"]["dbName"] == "dac_raw"
    assert by_uid["pg-dac"]["type"] == "grafana-postgresql-datasource"
    assert by_uid["influx-dac"]["readOnly"] and by_uid["pg-dac"]["readOnly"]


def test_the_token_is_not_readable_through_the_api(grafana):
    for datasource in grafana.datasources():
        assert "apiv3_" not in json.dumps(datasource)


# ----------------------------------------------------------------------------- S6.7 refusal


def test_s6_7_the_checker_refuses_when_nothing_listens_and_writes_no_file(tmp_path):
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.check_dashboards",
            "--dashboard",
            str(DASHBOARD),
            "--report-dir",
            str(tmp_path / "out"),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "GRAFANA_URL": "http://localhost:1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 2, result.stderr
    assert "not reachable" in result.stderr
    assert not (tmp_path / "out").exists()


# ----------------------------------------------------------------------------- the checker


@contextmanager
def scratch_stack(interval_experiment: str = "EXP_001"):
    """A throwaway InfluxDB database with the fixture data, a Postgres schema with its two
    experiments and a temporary datasource on the database. Yields (database, uid, schema)."""
    database = f"m6_t1_{uuid.uuid4().hex[:10]}"
    schema = f"m6_t1_{uuid.uuid4().hex[:10]}"
    create_database(database)
    try:
        write_line_protocol(database, lines(interval_experiment=interval_experiment))
        prepare_pg_schema(schema, GRAFANA_FIXTURE / "experiments.json")
        with temp_influx_datasource(database) as uid:
            yield database, uid, schema
    finally:
        drop_pg_schema(schema)
        drop_database(database)


def checker(uid: str, schema: str, *extra: str, dashboard: Path = DASHBOARD):
    code, report = run_checker(
        "--dashboard",
        str(dashboard),
        "--var",
        f"influx={uid}",
        "--var",
        f"pg_schema={schema}",
        *extra,
    )
    return code, report, run_checker.last


def sql_list(ids: list[str]) -> str:
    return ", ".join(f"'{i}'" for i in ids)


def expected_rows(database: str, selection: list[str], signal: str) -> dict[str, int]:
    """Rows each panel must return, from plain SELECTs written for this test."""
    ids = sql_list(selection)
    start = min(WINDOWS[e][0] for e in selection)
    end = max(WINDOWS[e][1] for e in selection)
    bounds = f"time >= '{start}' AND time <= '{end}'"
    readings = query(
        database,
        f"SELECT time FROM readings_processed WHERE experiment_id IN ({ids}) "  # noqa: S608
        f"AND signal = '{signal}' AND {bounds}",
    )
    accepted = query(
        database,
        f"SELECT time FROM readings_processed WHERE experiment_id IN ({ids}) "  # noqa: S608
        f"AND signal = '{signal}' AND verdict = 'accepted'",
    )
    gaps = query(
        database,
        f"SELECT time FROM quality_intervals WHERE experiment_id IN ({ids}) AND {bounds}",  # noqa: S608
    )
    return {
        "Experiments": len(selection),
        "Readings: ${signal}": len(readings),
        "Overlay: ${signal}": len(accepted),
        "Gaps and stuck stretches": len(gaps),
    }


def panel_rows(run: dict) -> dict[str, int]:
    return {p["title"]: p["targets"][0]["rows"] for p in run["panels"]}


def test_s6_6_every_target_returns_the_rows_of_the_same_sql_run_directly(grafana):
    with scratch_stack() as (database, uid, schema):
        # EXP_002 has no gap row by construction, so that panel may be empty for it
        code, report, proc = checker(
            uid, schema, "--sweep", "signal", "--allow-empty", "Gaps and stuck stretches"
        )
        assert code == 0, proc.stderr + proc.stdout

        assert [r["selection"] for r in report["runs"]] == [
            ["EXP_001"],
            ["EXP_001"],
            ["EXP_001", "EXP_002"],
            ["EXP_001", "EXP_002"],
            ["EXP_002"],
            ["EXP_002"],
        ]
        assert report["source"]["sweep"] == ["signal"]
        for run in report["runs"]:
            assert run["dashboard_uid"] == "dac-test"
            assert [p["title"] for p in run["panels"]] == list(PANELS)
            want = expected_rows(database, run["selection"], run["sweep"]["signal"])
            assert panel_rows(run) == want, (run["selection"], run["sweep"])
        # the construction of the data, not the pipeline: 19 accepted EXP_001 voltage readings
        first = report["runs"][0]
        assert (first["selection"], first["sweep"]) == (["EXP_001"], {"signal": "current"})
        voltage = next(
            r
            for r in report["runs"]
            if r["selection"] == ["EXP_001"] and r["sweep"]["signal"] == "voltage"
        )
        assert panel_rows(voltage) == {
            "Experiments": 1,
            "Readings: ${signal}": 20,
            "Overlay: ${signal}": 19,
            "Gaps and stuck stretches": 1,
        }
        # the gap annotation is one region for EXP_001 voltage, none for the other cases
        annotations = {
            (tuple(r["selection"]), r["sweep"]["signal"]): r["annotations"][0]["rows"]
            for r in report["runs"]
        }
        assert annotations[(("EXP_001",), "voltage")] == 1
        assert annotations[(("EXP_001",), "current")] == 0
        assert annotations[(("EXP_002",), "voltage")] == 0
        assert report["totals"] == {
            "runs": 6,
            "panel_targets": 24,
            "with_rows": 22,
            "empty": 0,
            "empty_allowed": 2,
            "errors": 0,
            "annotation_errors": 0,
        }
        jsonschema.validate(report, CONTRACT)


def test_s6_6_a_panel_without_rows_fails_the_run_and_allow_empty_excuses_it(grafana):
    with scratch_stack(interval_experiment="EXP_999") as (_database, uid, schema):
        code, report, proc = checker(uid, schema)
        assert code == 1, proc.stderr + proc.stdout
        assert "Gaps and stuck stretches" in proc.stderr
        for run in report["runs"]:
            by_title = {p["title"]: p["targets"][0]["rows"] for p in run["panels"]}
            assert by_title["Gaps and stuck stretches"] == 0
            assert all(rows > 0 for t, rows in by_title.items() if t != "Gaps and stuck stretches")
        assert report["totals"]["empty"] == 3
        assert report["totals"]["errors"] == 0

        code, report, proc = checker(uid, schema, "--allow-empty", "Gaps and stuck stretches")
        assert code == 0, proc.stderr + proc.stdout
        assert report["totals"]["empty"] == 0
        assert report["totals"]["empty_allowed"] == 3
        assert report["source"]["allow_empty"] == ["Gaps and stuck stretches"]


def test_s6_6_a_failing_query_exits_1_and_records_the_servers_error(grafana, tmp_path):
    broken = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    readings = next(p for p in broken["panels"] if p["id"] == 2)
    readings["targets"][0]["rawSql"] = readings["targets"][0]["rawSql"].replace(
        "value_raw", "no_such_column"
    )
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with scratch_stack() as (_database, uid, schema):
        code, report, proc = checker(uid, schema, "--experiment", "EXP_001", dashboard=path)
    assert code == 1, proc.stderr + proc.stdout
    (run,) = report["runs"]
    target = next(p for p in run["panels"] if p["title"] == "Readings: ${signal}")["targets"][0]
    assert target["rows"] == 0
    assert "no_such_column" in target["error"]
    assert "Readings" in proc.stderr and "no_such_column" in proc.stderr
    assert report["totals"]["errors"] == 1
    # an error counts only under errors, not also under empty
    assert report["totals"]["panel_targets"] == (
        report["totals"]["with_rows"]
        + report["totals"]["empty"]
        + report["totals"]["empty_allowed"]
        + report["totals"]["errors"]
    )
    jsonschema.validate(report, CONTRACT)


def test_s6_7_two_runs_on_the_same_data_are_equal_except_timing(grafana):
    with scratch_stack() as (_database, uid, schema):
        _, first, _ = checker(uid, schema, "--sweep", "signal")
        _, second, _ = checker(uid, schema, "--sweep", "signal")
    jsonschema.validate(first, CONTRACT)
    jsonschema.validate(second, CONTRACT)
    assert {k: v for k, v in first.items() if k != "timing"} == {
        k: v for k, v in second.items() if k != "timing"
    }
    assert first["timing"]["queries"] > 0


def test_time_range_span_and_a_fixed_range_give_the_same_rows_for_data_inside_it(grafana):
    with scratch_stack() as (_database, uid, schema):
        _, window, _ = checker(uid, schema, "--experiment", "EXP_001")
        _, span, _ = checker(uid, schema, "--experiment", "EXP_001", "--time-range", "span")
        _, fixed, proc = checker(
            uid,
            schema,
            "--experiment",
            "EXP_001",
            "--time-range",
            "2026-05-04T08:00:00Z,2026-05-04T08:01:00Z",
        )
    assert span["source"]["time_range"] == "span"
    assert fixed["source"]["time_range"] == "fixed"
    assert span["runs"][0]["time_to"] == "2026-05-11T09:01:00Z"
    assert (fixed["runs"][0]["time_from"], fixed["runs"][0]["time_to"]) == WINDOWS["EXP_001"]
    assert panel_rows(span["runs"][0]) == panel_rows(window["runs"][0])
    assert panel_rows(fixed["runs"][0]) == panel_rows(window["runs"][0])


def test_the_checker_refuses_an_unknown_experiment_and_writes_nothing(grafana, tmp_path):
    with scratch_stack() as (_database, uid, schema):
        code, report = run_checker(
            "--dashboard",
            str(DASHBOARD),
            "--var",
            f"influx={uid}",
            "--var",
            f"pg_schema={schema}",
            "--experiment",
            "EXP_404",
            "--report-dir",
            str(tmp_path / "out"),
        )
    assert code == 2
    assert report is None
    assert not (tmp_path / "out").exists()
