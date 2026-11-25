"""The "Experiment detail" dashboard on the compare fixture (M6: S6.16, S6.17, S6.20).

S6.16 reads the dashboard from the running Grafana's API: it is provisioned from
`grafana/dashboards/experiment.json`, with its variables, the ten panels and the annotation.

S6.17 and S6.20 run the compare fixture (`tests/fixtures/compare`: three experiments of 1,200 s)
through ingest, clean, metrics, compare and load_comparison into a throwaway InfluxDB database
and a throwaway Postgres schema, point a temporary Grafana datasource at the database, and run
the committed dashboard JSON through the checker for each experiment over its window. The
fixture has no gap and no stuck stretch, and cleaning excludes exactly one reading (EXP_001
voltage at +300 s), so the two tables built on those (`Gaps and stuck stretches`, `Excluded
readings`) are the only panels allowed to be empty, and only where that holds.

Throwaway state only (no `dac_raw`, no write to the provisioned datasources); Core allows five
databases and four exist, so a module holds at most one extra database.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest

import scripts.migrate as migrate
from pipeline.grafana_check import (
    GrafanaClient,
    QueryResult,
    interpolate,
    load_dashboard,
    panel_targets,
    to_epoch_ms,
)
from tests.e2e.grafana_helpers import (
    REPO_ROOT,
    drop_pg_schema,
    prepare_pg_schema,
    run_checker,
    run_pipeline,
    temp_influx_datasource,
    write_line_protocol,
)
from tests.e2e.helpers import query

pytestmark = [pytest.mark.influx, pytest.mark.postgres, pytest.mark.grafana]

DASHBOARD = REPO_ROOT / "grafana" / "dashboards" / "experiment.json"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "compare"
EXPERIMENTS = FIXTURES / "experiments.json"
IDS = ("EXP_001", "EXP_002", "EXP_003")
PG_UID = "pg-dac"
PLACEHOLDER_INTERVAL = (
    "quality_intervals,experiment_id=EXP_NONE,source=hydrolyzer,signal=voltage,"
    "policy_version=m3-v1,kind=gap seconds=1.0,end_ns=1i,points=0i 0"
)

PANEL_TITLES = [
    "Experiment",
    "Process phases",
    "${signal}: accepted and excluded",
    "Electrical: voltage, current, power",
    "Power residual (logged − computed)",
    "Capture: CO2 in and out",
    "Capture efficiency and rate",
    "Signal quality",
    "Gaps and stuck stretches",
    "Excluded readings",
]
ANNOTATION = "Gaps and stuck stretches"
EMPTY_ALLOWED = ("Gaps and stuck stretches", "Excluded readings")
# Targets per panel title (D4 and D7 draw from two tables).
TARGETS_PER_PANEL = {
    "Experiment": 1,
    "Process phases": 1,
    "${signal}: accepted and excluded": 1,
    "Electrical: voltage, current, power": 2,
    "Power residual (logged − computed)": 1,
    "Capture: CO2 in and out": 1,
    "Capture efficiency and rate": 2,
    "Signal quality": 1,
    "Gaps and stuck stretches": 1,
    "Excluded readings": 1,
}


# ------------------------------------------------------------------ the dashboard and its targets


def dashboard() -> dict:
    return load_dashboard(DASHBOARD)


def constants(doc: dict) -> dict[str, str]:
    """The values of the dashboard's constant variables, as the JSON declares them."""
    return {v["name"]: v["query"] for v in doc["templating"]["list"] if v.get("type") == "constant"}


def variable(doc: dict, name: str) -> dict:
    return next(v for v in doc["templating"]["list"] if v["name"] == name)


def windows_ms(experiments_file: Path) -> dict[str, tuple[int, int]]:
    rows = json.loads(experiments_file.read_text(encoding="utf-8"))
    return {
        r["experiment_id"]: (to_epoch_ms(r["start_time"]), to_epoch_ms(r["end_time"])) for r in rows
    }


def resolve_values(
    grafana: GrafanaClient,
    doc: dict,
    *,
    influx_uid: str,
    schema: str,
    experiment: str,
    signal: str,
    window: tuple[int, int],
) -> dict[str, str]:
    """Variable values for one experiment, the hidden ones from the dashboard's own SQL on
    Postgres (through Grafana), so the variable queries are checked too."""
    values = {
        **constants(doc),
        "influx": influx_uid,
        "pg": PG_UID,
        "pg_schema": schema,
        "experiment": experiment,
        "signal": signal,
    }
    for name in ("windows", "span_from", "span_to", "from_ms", "to_ms"):
        result = grafana.query(
            PG_UID,
            {
                "refId": "A",
                "rawSql": interpolate(variable(doc, name)["query"], values),
                "format": "table",
                "rawQuery": True,
                "editorMode": "code",
            },
            *window,
        )
        assert result.error is None, f"variable {name}: {result.error}"
        assert result.columns and result.columns[0], f"variable {name} returned no row"
        value = result.columns[0][0]
        values[name] = str(int(value)) if isinstance(value, int | float) else str(value)
    return values


def find_target(doc: dict, title: str, ref_id: str = "A") -> tuple[dict, dict]:
    for panel, target in panel_targets(doc):
        if panel["title"] == title and target["refId"] == ref_id:
            return panel, target
    raise AssertionError(f"no target {ref_id} in a panel titled {title!r}")


def run_target(
    grafana: GrafanaClient,
    doc: dict,
    title: str,
    values: dict[str, str],
    window: tuple[int, int],
    ref_id: str = "A",
) -> tuple[str, QueryResult]:
    """Run one panel target as the dashboard writes it: the exact SQL, variables filled in,
    `$__timeFilter` left to Grafana. Returns the SQL (after interpolation) and the result."""
    panel, target = find_target(doc, title, ref_id)
    sql = interpolate(target["rawSql"], values)
    uid = values["influx"] if panel["datasource"]["uid"] == "${influx}" else PG_UID
    result = grafana.query(uid, {"refId": ref_id, "rawSql": sql, "format": "table"}, *window)
    assert result.error is None, f"{title} {ref_id}: {result.error}"
    return sql, result


def column(result: QueryResult, name: str) -> list:
    return result.columns[result.fields.index(name)]


# ------------------------------------------------------------------------- S6.16: provisioned


def test_s6_16_the_dashboard_is_provisioned_with_its_variables_and_panels(grafana):
    served = None
    for _ in range(40):  # provisioning rescans every 30 s (updateIntervalSeconds)
        status, body = grafana.api("GET", "/api/dashboards/uid/dac-experiment")
        if status == 200:
            served = body
            break
        time.sleep(3)
    assert served is not None, "Grafana does not serve dac-experiment (not provisioned yet?)"

    meta, dash = served["meta"], served["dashboard"]
    assert meta["folderTitle"] == "DAC"
    assert meta["provisioned"] is True
    assert dash["uid"] == "dac-experiment"
    assert dash["title"] == "Experiment detail"

    variables = {v["name"]: v for v in dash["templating"]["list"]}
    experiment = variables["experiment"]
    assert experiment["type"] == "query"
    assert not experiment.get("multi") and not experiment.get("includeAll")
    assert experiment["current"]["value"] == "EXP_001"
    assert variables["signal"]["type"] == "query"
    assert variables["signal"]["current"]["value"] == "voltage"
    assert {
        "influx",
        "pg",
        "pg_schema",
        "policy_version",
        "metrics_version",
        "compare_version",
        "experiment",
        "windows",
        "span_from",
        "span_to",
        "signal",
        "from_ms",
        "to_ms",
    } <= set(variables)
    assert variables["pg_schema"]["query"] == "public"
    assert variables["policy_version"]["query"] == "m3-v1"
    assert variables["metrics_version"]["query"] == "m4-v1"

    assert [p["title"] for p in sorted(dash["panels"], key=lambda p: p["id"])] == PANEL_TITLES
    assert [p["id"] for p in dash["panels"]] == list(range(1, 11))
    assert [a["name"] for a in dash["annotations"]["list"] if not a.get("builtIn")] == [ANNOTATION]
    # what Grafana serves is what the repository holds
    assert [p["title"] for p in dash["panels"]] == [p["title"] for p in dashboard()["panels"]]


def test_the_default_time_range_is_exp_001_and_the_jump_link_exists():
    doc = dashboard()
    assert doc["time"] == {"from": "2026-05-04T08:00:00.000Z", "to": "2026-05-04T10:00:00.000Z"}
    expected = "/d/dac-experiment?var-experiment=${experiment}&from=${from_ms}&to=${to_ms}"
    title = "Jump to this experiment's window"
    assert [(link["title"], link["url"]) for link in doc["links"]] == [(title, expected)]
    d1 = next(p for p in doc["panels"] if p["title"] == "Experiment")
    links = [
        prop["value"]
        for override in d1["fieldConfig"]["overrides"]
        for prop in override["properties"]
        if prop["id"] == "links"
    ]
    assert links == [[{"title": title, "url": expected, "targetBlank": False}]]


# ------------------------------------------------------------------------------ the fixture run


@dataclass
class Run:
    database: str
    schema: str
    influx_uid: str
    doc: dict
    grafana: GrafanaClient


@pytest.fixture(scope="module")
def run(grafana, module_db, tmp_path_factory):
    schema = f"m6_e2e_{uuid.uuid4().hex[:10]}"
    try:
        prepare_pg_schema(schema, EXPERIMENTS)
        run_pipeline(FIXTURES, module_db, schema, tmp_path_factory.mktemp("work"))
        # Core creates a table with its first row, and cleaning found no gap and no stuck
        # stretch in this fixture, so `quality_intervals` would not exist and the interval
        # table and the annotation would fail with "table not found" instead of being empty.
        # One row of an experiment the fixture does not have makes the table exist.
        write_line_protocol(module_db, [PLACEHOLDER_INTERVAL])
        with temp_influx_datasource(module_db) as uid:
            yield Run(module_db, schema, uid, dashboard(), grafana)
    finally:
        drop_pg_schema(schema)


def pg_count(schema: str, sql: str, *params) -> int:
    with psycopg.connect(**migrate.connect_kwargs(migrate.load_env())) as conn:
        return conn.execute(sql.replace("{s}", schema), params).fetchone()[0]


@pytest.fixture(scope="module")
def checked(run):
    """One checker run: the dashboard, each experiment alone, over its window."""
    allow = [arg for title in EMPTY_ALLOWED for arg in ("--allow-empty", title)]
    code, report = run_checker(
        "--dashboard",
        str(DASHBOARD),
        "--var",
        f"influx={run.influx_uid}",
        "--var",
        f"pg_schema={run.schema}",
        *allow,
    )
    detail = getattr(run_checker, "last", None)
    message = f"{detail.stdout}\n{detail.stderr}" if detail is not None else ""
    return code, report, message


def runs_by_experiment(report: dict) -> dict[str, dict]:
    return {r["selection"][0]: r for r in report["runs"]}


def target_rows(run_entry: dict, title: str) -> list[int]:
    panel = next(p for p in run_entry["panels"] if p["title"] == title)
    return [t["rows"] for t in panel["targets"]]


# ------------------------------------------------------------------------------------- S6.17


def test_s6_17_every_panel_target_returns_rows_for_every_fixture_experiment(checked):
    code, report, message = checked
    assert code == 0, message
    assert report is not None
    totals = report["totals"]
    assert totals["runs"] == 3
    assert totals["errors"] == 0 and totals["annotation_errors"] == 0, message
    assert totals["empty"] == 0, message
    assert totals["panel_targets"] == 3 * sum(TARGETS_PER_PANEL.values()) == 36

    runs = runs_by_experiment(report)
    assert sorted(runs) == list(IDS)
    for experiment, entry in runs.items():
        assert entry["dashboard_uid"] == "dac-experiment"
        assert [p["title"] for p in entry["panels"]] == PANEL_TITLES
        assert {p["title"]: len(p["targets"]) for p in entry["panels"]} == TARGETS_PER_PANEL
        assert [a["name"] for a in entry["annotations"]] == [ANNOTATION]
        for panel in entry["panels"]:
            for target in panel["targets"]:
                assert target["error"] is None, (experiment, panel["title"])
                if panel["title"] in EMPTY_ALLOWED:
                    continue
                assert target["rows"] > 0, (experiment, panel["title"], target["ref_id"])


def test_s6_17_only_the_two_interval_tables_are_empty_and_only_where_the_fixture_has_none(checked):
    _code, report, _message = checked
    runs = runs_by_experiment(report)
    for experiment in IDS:
        # no gap and no flatline anywhere in the fixture
        assert target_rows(runs[experiment], "Gaps and stuck stretches") == [0], experiment
        # one excluded reading in EXP_001 (voltage at +300 s), none in the others
        expected = [1] if experiment == "EXP_001" else [0]
        assert target_rows(runs[experiment], "Excluded readings") == expected, experiment
    assert report["totals"]["empty_allowed"] == 3 + 2
    assert report["totals"]["with_rows"] == 36 - 5


def test_s6_17_a_target_with_no_allowance_would_fail_on_the_empty_tables(run):
    """Without --allow-empty the two tables are empty targets, so the checker exits 1."""
    code, report = run_checker(
        "--dashboard",
        str(DASHBOARD),
        "--experiment",
        "EXP_002",
        "--var",
        f"influx={run.influx_uid}",
        "--var",
        f"pg_schema={run.schema}",
    )
    assert code == 1
    assert report["totals"]["empty"] == 2  # D9 and D10 of EXP_002
    assert report["totals"]["errors"] == 0


def test_the_experiment_and_signal_quality_panels_match_plain_postgres_counts(run, checked):
    _code, report, _message = checked
    runs = runs_by_experiment(report)
    for experiment in IDS:
        assert target_rows(runs[experiment], "Experiment") == [1]
        plain = pg_count(
            run.schema,
            "SELECT COUNT(*) FROM {s}.signal_quality WHERE experiment_id = %s "
            "AND metrics_version = 'm4-v1' AND policy_version = 'm3-v1'",
            experiment,
        )
        assert plain > 0
        assert target_rows(runs[experiment], "Signal quality") == [plain], experiment


def test_the_signal_variable_lists_the_numeric_signals(run):
    doc = run.doc
    window = windows_ms(EXPERIMENTS)["EXP_001"]
    values = {**constants(doc), "pg_schema": run.schema}
    result = run.grafana.query(
        PG_UID,
        {
            "refId": "A",
            "rawSql": interpolate(variable(doc, "signal")["query"], values),
            "format": "table",
            "rawQuery": True,
            "editorMode": "code",
        },
        *window,
    )
    assert result.error is None
    signals = result.columns[0]
    assert "voltage" in signals and "air_flow" in signals
    assert "process_state" not in signals and "valve_state" not in signals
    assert signals == sorted(signals)


def test_the_excluded_voltage_reading_of_exp_001_is_drawn_beside_the_accepted_line(run):
    """D3 on the fixture: 1,199 accepted values and the one excluded one at its raw value."""
    window = windows_ms(EXPERIMENTS)["EXP_001"]
    values = resolve_values(
        run.grafana,
        run.doc,
        influx_uid=run.influx_uid,
        schema=run.schema,
        experiment="EXP_001",
        signal="voltage",
        window=window,
    )
    assert values["span_from"] == "2026-05-04T08:00:00Z"
    assert values["span_to"] == "2026-05-04T08:20:00Z"
    _sql, result = run_target(
        run.grafana, run.doc, "${signal}: accepted and excluded", values, window
    )
    assert result.fields == ["time", "accepted", "excluded (raw value)"]
    accepted = [v for v in column(result, "accepted") if v is not None]
    excluded = [v for v in column(result, "excluded (raw value)") if v is not None]
    assert len(accepted) == 1199
    assert excluded == [80.641757]
    # one row per reading, so a signal without exclusions is not an empty target
    assert result.rows == 1200


# ------------------------------------------------------------------------------------- S6.20


def test_s6_20_phases_are_returned_as_state_events_with_their_raw_value(run):
    window = windows_ms(EXPERIMENTS)["EXP_001"]
    values = resolve_values(
        run.grafana,
        run.doc,
        influx_uid=run.influx_uid,
        schema=run.schema,
        experiment="EXP_001",
        signal="voltage",
        window=window,
    )
    sql, result = run_target(run.grafana, run.doc, "Process phases", values, window)
    assert result.fields == ["time", "process_state", "valve_state"]

    times = column(result, "time")
    states = column(result, "process_state")
    events = [(t, s) for t, s in zip(times, states, strict=True) if s is not None]
    start = window[0]
    assert [(round((t - start) / 1000), s) for t, s in events] == [
        (0, "STARTUP"),
        (120, "STEADY_STATE"),
        (600, "LOAD_CHANGE"),
        (660, "STEADY_STATE"),
        (1140, "SHUTDOWN"),
    ]
    # the same events from a plain query of the table, as written by the cleaning run
    plain = query(
        run.database,
        "SELECT value_raw FROM state_intervals WHERE experiment_id = 'EXP_001' "
        "AND signal = 'process_state' AND policy_version = 'm3-v1' ORDER BY time",
    )
    assert [s for _t, s in events] == [r["value_raw"] for r in plain]
    assert "$__timeFilter" in find_target(run.doc, "Process phases")[1]["rawSql"]
    assert "'EXP_001'" in sql


def test_s6_20_each_experiment_has_its_own_phase_times(run):
    windows = windows_ms(EXPERIMENTS)
    for experiment in IDS:
        values = resolve_values(
            run.grafana,
            run.doc,
            influx_uid=run.influx_uid,
            schema=run.schema,
            experiment=experiment,
            signal="voltage",
            window=windows[experiment],
        )
        _sql, result = run_target(
            run.grafana, run.doc, "Process phases", values, windows[experiment]
        )
        states = [
            (round((t - windows[experiment][0]) / 1000), s)
            for t, s in zip(column(result, "time"), column(result, "process_state"), strict=True)
            if s is not None
        ]
        assert [offset for offset, _s in states] == [0, 120, 600, 660, 1140], experiment
