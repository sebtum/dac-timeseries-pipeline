"""The "Compare experiments" dashboard against a live Grafana, InfluxDB and Postgres (M6: S6.11 to
S6.15).

S6.11 reads the provisioned dashboard from the private stack's Grafana. S6.12 to S6.15 run the
compare fixture (`tests/fixtures/compare`, three experiments of 1,200 s) through ingest, clean,
metrics, compare and load_comparison into a throwaway InfluxDB database and a throwaway Postgres
schema, point a temporary Grafana datasource at the database, and then run the dashboard's own
queries: the checker for "every target returns rows" and the same interpolated SQL through Grafana
for the numbers, which are compared with plain queries (psycopg for Postgres, `SELECT` through the
InfluxDB client for InfluxDB) with no import from `pipeline/`.

`dac_raw` is never touched. Core allows five databases and four exist, so this module holds one.
Every expected count comes from the fixture's construction (`tests/fixtures/compare/README.md`):
EXP_001's voltage at +300 s is the only excluded reading.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

import scripts.migrate as migrate
from pipeline.grafana_check import interpolate
from tests.e2e.grafana_helpers import (
    drop_pg_schema,
    prepare_pg_schema,
    run_checker,
    run_pipeline,
    temp_influx_datasource,
)
from tests.e2e.helpers import REPO_ROOT, query

pytestmark = pytest.mark.grafana

DASHBOARD_PATH = REPO_ROOT / "grafana" / "dashboards" / "compare.json"
DASHBOARD = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "compare"
IDS = ("EXP_001", "EXP_002", "EXP_003")
POLICY, METRICS, COMPARE = "m3-v1", "m4-v1", "m5-v1"
C9 = "Excluded readings by reason"
NS_PER_MIN = 60_000_000_000

PANEL_TITLES = {
    1: "Experiments",
    2: "Whole-run KPIs",
    3: "Steady-state KPIs (95 % interval)",
    4: "Which pairs can be compared",
    5: "Steady KPI differences by pair",
    6: "Overlay: ${signal} in minutes since start",
    7: "Overlay: ${metric} in minutes since start",
    8: "Data quality per experiment",
    9: C9,
}
VARIABLES = (
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
    "metric",
)
HIDDEN = {
    "influx",
    "pg",
    "pg_schema",
    "policy_version",
    "metrics_version",
    "compare_version",
    "windows",
    "span_from",
    "span_to",
}
# decision 12: status colours (amber is Grafana's "orange")
STATUS_COLORS = {"complete": "green", "partial": "orange", "none": "red"}
CONDITION_COLORS = {"same_conditions": "green", "supported": "green", "confounded": "orange"}
HIGH_GOOD = [("red", None), ("orange", 0.5), ("green", 0.95)]  # completeness, valid
LOW_GOOD = [("green", None), ("orange", 0.05), ("red", 0.5)]  # bad, uncertain


# ------------------------------------------------------------------ reading the dashboard JSON


def panel(doc: dict, panel_id: int) -> dict:
    return next(p for p in doc["panels"] if p["id"] == panel_id)


def override_props(pan: dict, field: str) -> dict[str, object]:
    for entry in pan["fieldConfig"]["overrides"]:
        if entry["matcher"] == {"id": "byName", "options": field}:
            return {prop["id"]: prop["value"] for prop in entry["properties"]}
    raise AssertionError(f"panel {pan['title']!r} has no override for {field!r}")


def mapping_colors(pan: dict, field: str) -> dict[str, str]:
    (block,) = override_props(pan, field)["mappings"]
    return {key: value["color"] for key, value in block["options"].items()}


def threshold_steps(pan: dict, field: str) -> list[tuple[str, float | None]]:
    steps = override_props(pan, field)["thresholds"]["steps"]
    return [(step["color"], step["value"]) for step in steps]


# ------------------------------------------------------------------ S6.11 (provisioned dashboard)


@pytest.fixture(scope="module")
def provisioned(grafana):
    status, body = grafana.api("GET", "/api/dashboards/uid/dac-compare")
    assert status == 200, body
    return body


def test_s6_11_dashboard_is_provisioned_in_folder_dac(provisioned):
    assert provisioned["meta"]["folderTitle"] == "DAC"
    assert provisioned["meta"]["provisioned"] is True
    assert provisioned["dashboard"]["uid"] == "dac-compare"
    assert provisioned["dashboard"]["title"] == "Compare experiments"


def test_s6_11_variables_and_panel_titles_match_the_inventory(provisioned):
    doc = provisioned["dashboard"]
    variables = {v["name"]: v for v in doc["templating"]["list"]}
    assert tuple(variables) == VARIABLES
    for name, variable in variables.items():
        assert (variable["hide"] == 2) == (name in HIDDEN), name
    assert {n: variables[n]["query"] for n in ("pg_schema", "policy_version")} == {
        "pg_schema": "public",
        "policy_version": POLICY,
    }
    assert variables["metrics_version"]["query"] == METRICS
    assert variables["compare_version"]["query"] == COMPARE
    experiment = variables["experiment"]
    assert experiment["multi"] is True
    assert experiment["includeAll"] is True
    assert experiment["current"]["value"] == ["$__all"]
    assert variables["signal"]["current"]["value"] == "voltage"
    assert variables["metric"]["query"] == (
        "power_computed,power_residual,capture_efficiency,capture_rate"
    )
    assert variables["metric"]["current"]["value"] == "capture_efficiency"
    assert [(p["id"], p["title"]) for p in doc["panels"]] == list(PANEL_TITLES.items())


def test_s6_11_provisioned_copy_equals_the_committed_file(provisioned):
    served = provisioned["dashboard"]
    assert [p["id"] for p in served["panels"]] == [p["id"] for p in DASHBOARD["panels"]]
    assert [p["targets"][0]["rawSql"] for p in served["panels"]] == [
        p["targets"][0]["rawSql"] for p in DASHBOARD["panels"]
    ]


# ------------------------------------------------------------------ static rules of the JSON


def test_every_query_is_versioned_and_schema_qualified():
    influx_panels = {6, 7, 9}
    for pan in DASHBOARD["panels"]:
        sql = pan["targets"][0]["rawSql"]
        if pan["id"] in influx_panels:
            assert "policy_version = '${policy_version}'" in sql, pan["title"]
            assert "VALUES ${windows:raw}" in sql, pan["title"]
            assert "r.time >= '${span_from}' AND r.time < '${span_to}'" in sql, pan["title"]
            assert "w.t0" in sql
            assert "w.t1" in sql
        else:
            assert "${pg_schema}." in sql, pan["title"]
            for table in re.findall(r"(?<!epoch )\b(?:FROM|JOIN)\s+(\S+)", sql):
                assert table.startswith("${pg_schema}."), (pan["title"], table)
    assert "metrics_version = '${metrics_version}'" in panel(DASHBOARD, 7)["targets"][0]["rawSql"]
    for forbidden in ("PERCENTILE_CONT", "COUNT(*) FILTER"):
        assert all(forbidden not in p["targets"][0]["rawSql"] for p in DASHBOARD["panels"])


def test_no_panel_states_a_finding_or_a_voltage_evidence_status():
    text = json.dumps(DASHBOARD).lower()
    for word in ("evidence", "finding", "hydrolyzer", "absorber", "supported by the data"):
        assert word not in text, word


def test_overlay_panels_are_xy_charts_partitioned_by_experiment():
    for panel_id in (6, 7):
        pan = panel(DASHBOARD, panel_id)
        assert pan["type"] == "xychart"
        (transform,) = pan["transformations"]
        assert transform == {"id": "partitionByValues", "options": {"fields": ["experiment_id"]}}
        # `mapping` is the current option; the old `seriesMapping` / `dims` make Grafana migrate
        # the panel to one manual series on the first frame, which draws one experiment only
        assert pan["options"]["mapping"] == "auto"
        assert "seriesMapping" not in pan["options"]
        assert "dims" not in pan["options"]


def test_status_and_fraction_colours_are_in_the_json():
    for panel_id in (2, 3):
        assert mapping_colors(panel(DASHBOARD, panel_id), "status") == STATUS_COLORS
    assert mapping_colors(panel(DASHBOARD, 4), "conditions_status") == CONDITION_COLORS
    quality = panel(DASHBOARD, 8)
    for field in ("completeness", "valid_fraction"):
        assert threshold_steps(quality, field) == HIGH_GOOD
    for field in ("bad_fraction", "uncertain_fraction"):
        assert threshold_steps(quality, field) == LOW_GOOD


def test_experiment_table_links_to_the_detail_dashboard():
    props = override_props(panel(DASHBOARD, 1), "experiment_id")
    (link,) = props["links"]
    assert link["title"] == "Open detail"
    assert link["url"].startswith("/d/dac-experiment?var-experiment=${__value.raw}")
    assert "&from=${__data.fields.start_ms}&to=${__data.fields.end_ms}" in link["url"]
    sql = panel(DASHBOARD, 1)["targets"][0]["rawSql"]
    assert "AS start_ms" in sql
    assert "AS end_ms" in sql


# ------------------------------------------------------------------ the fixture run


@pytest.fixture(scope="module")
def ran(grafana, module_db, tmp_path_factory):
    """Fixture pipeline into a throwaway database and schema, plus a temporary datasource."""
    schema = f"m6_cmp_{uuid.uuid4().hex[:10]}"
    work = tmp_path_factory.mktemp("pipeline")
    prepare_pg_schema(schema, FIXTURE / "experiments.json")
    try:
        run_pipeline(FIXTURE, module_db, schema, work)
        with temp_influx_datasource(module_db) as uid:
            yield {
                "client": grafana,
                "database": module_db,
                "schema": schema,
                "datasource": uid,
                "work": work,
                "starts": experiment_starts(schema),
            }
    finally:
        drop_pg_schema(schema)


def pg_connection(schema: str) -> psycopg.Connection:
    kwargs = migrate.connect_kwargs(migrate.load_env())
    kwargs["options"] = f"-c search_path={schema}"
    return psycopg.connect(**kwargs)


def pg_rows(schema: str, sql: str, params: tuple = ()) -> list[tuple]:
    with pg_connection(schema) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def experiment_starts(schema: str) -> dict[str, int]:
    """Start of each experiment in epoch nanoseconds, from Postgres."""
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    rows = pg_rows(schema, "SELECT experiment_id, start_time FROM experiment")
    return {eid: (start - epoch) // timedelta(microseconds=1) * 1000 for eid, start in rows}


class Resolver:
    """Resolves the dashboard variables for a selection the way the checker does, then runs one
    panel target through Grafana and returns `(fields, columns)` of its first frame."""

    FROM, TO = 0, 4_102_444_800_000  # epoch ms; the compare dashboard has no time filter

    def __init__(self, run: dict):
        self.run = run
        self.client = run["client"]

    def values(self, selection: list[str], **forced: str) -> dict:
        values: dict = {"influx": self.run["datasource"], "pg_schema": self.run["schema"]}
        for var in DASHBOARD["templating"]["list"]:
            name = var["name"]
            if name in values:
                continue
            if name in forced:
                values[name] = forced[name]
            elif var["type"] == "datasource":
                values[name] = var["current"]["value"]
            elif var["type"] == "constant":
                values[name] = var["query"]
            elif name == "experiment":
                values[name] = list(selection)
            elif var["type"] == "custom":
                values[name] = var["current"]["value"]
            else:
                sql = interpolate(var["query"], values)
                result = self.client.query(values["pg"], self.target(sql), self.FROM, self.TO)
                assert result.error is None, (name, result.error)
                options = [str(v) for v in result.columns[0]]
                current = var["current"].get("value")
                values[name] = current if current in options else options[0]
        return values

    @staticmethod
    def target(sql: str) -> dict:
        return {"refId": "A", "rawSql": sql, "format": "table", "rawQuery": True}

    def rows(self, panel_id: int, selection: list[str], **forced: str) -> list[dict]:
        values = self.values(selection, **forced)
        pan = panel(DASHBOARD, panel_id)
        sql = interpolate(pan["targets"][0]["rawSql"], values)
        uid = values["influx"] if pan["datasource"]["uid"] == "${influx}" else values["pg"]
        result = self.client.query(uid, self.target(sql), self.FROM, self.TO)
        assert result.error is None, (pan["title"], result.error)
        if not result.columns:
            return []
        return [
            dict(zip(result.fields, row, strict=True)) for row in zip(*result.columns, strict=True)
        ]


@pytest.fixture(scope="module")
def resolver(ran):
    return Resolver(ran)


def columns_of(rows: list[dict], *names: str) -> list[tuple]:
    return [tuple(row[name] for name in names) for row in rows]


def assert_same_rows(got: list[tuple], expected: list[tuple]) -> None:
    assert len(got) == len(expected), (len(got), len(expected))
    for index, (got_row, expected_row) in enumerate(zip(got, expected, strict=True)):
        for g, e in zip(got_row, expected_row, strict=True):
            if isinstance(e, float):
                assert g == pytest.approx(e, rel=1e-12, abs=1e-12), (index, got_row, expected_row)
            else:
                assert g == e, (index, got_row, expected_row)


# ------------------------------------------------------------------ S6.12


def test_s6_12_every_panel_returns_rows_for_every_fixture_experiment(ran):
    exit_code, report = run_checker(
        "--dashboard",
        str(DASHBOARD_PATH),
        "--var",
        f"influx={ran['datasource']}",
        "--var",
        f"pg_schema={ran['schema']}",
        "--allow-empty",
        C9,
    )
    assert exit_code == 0, run_checker.last.stdout + run_checker.last.stderr
    assert report is not None
    selections = [run["selection"] for run in report["runs"]]
    assert selections == [["EXP_001"], ["EXP_001", "EXP_002", "EXP_003"], ["EXP_002"], ["EXP_003"]]
    for run in report["runs"]:
        assert run["dashboard_uid"] == "dac-compare"
        assert [p["title"] for p in run["panels"]] == list(PANEL_TITLES.values())
        for pan in run["panels"]:
            for target in pan["targets"]:
                assert target["error"] is None, (run["selection"], pan["title"], target)
                if pan["title"] == C9 and run["selection"] in (["EXP_002"], ["EXP_003"]):
                    assert target["rows"] == 0, (run["selection"], target)
                else:
                    assert target["rows"] > 0, (run["selection"], pan["title"], target)
    totals = report["totals"]
    assert totals["runs"] == 4
    assert totals["panel_targets"] == 4 * 9
    assert totals["errors"] == 0
    assert totals["empty"] == 0
    assert totals["empty_allowed"] == 2


def test_s6_12_exclusions_are_counted_for_the_one_experiment_that_has_them(resolver):
    rows = resolver.rows(9, list(IDS))
    assert columns_of(rows, "experiment_id", "reason", "readings") == [("EXP_001", "flag_bad", 1)]


# ------------------------------------------------------------------ S6.13 and S6.15


def plain_points(ran: dict, sql: str) -> dict[str, list[tuple[int, float]]]:
    """`(time as epoch ns, value)` per experiment from a plain SELECT, in time order."""
    out: dict[str, list[tuple[int, float]]] = {eid: [] for eid in IDS}
    for row in query(ran["database"], sql):
        out[row["experiment_id"]].append((int(row["t"]), row["value"]))
    return out


def overlay_by_experiment(rows: list[dict]) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = {eid: [] for eid in IDS}
    for row in rows:
        out[row["experiment_id"]].append((row["experiment_time_min"], row["value"]))
    return out


def expected_overlay(ran: dict, points: dict[str, list[tuple[int, float]]]) -> dict:
    return {
        eid: [((t - ran["starts"][eid]) / NS_PER_MIN, value) for t, value in series]
        for eid, series in points.items()
    }


def assert_overlay(got: dict, expected: dict) -> None:
    for eid in IDS:
        assert len(got[eid]) == len(expected[eid]), eid
        for (gx, gv), (ex, ev) in zip(got[eid], expected[eid], strict=True):
            assert gx == pytest.approx(ex, abs=1e-9), eid
            assert gv == ev, eid


def test_s6_13_overlay_puts_wall_clock_starts_on_one_axis(ran, resolver):
    rows = resolver.rows(6, list(IDS), signal="voltage")
    assert [f for f in rows[0]] == ["experiment_id", "experiment_time_min", "value"]
    got = overlay_by_experiment(rows)
    points = plain_points(
        ran,
        "SELECT experiment_id, CAST(time AS BIGINT) AS t, value FROM readings_processed "
        f"WHERE signal = 'voltage' AND policy_version = '{POLICY}' AND verdict = 'accepted' "
        "ORDER BY experiment_id, time",
    )
    assert_overlay(got, expected_overlay(ran, points))
    # three different wall-clock days, one axis starting at 0.0
    assert len({ran["starts"][eid] // (24 * 3600 * 10**9) for eid in IDS}) == 3
    for eid in IDS:
        assert min(x for x, _ in got[eid]) == 0.0
        assert max(x for x, _ in got[eid]) < 20.0
    # counts: the accepted voltage readings of the clean summary, EXP_001 one fewer
    summary = json.loads((ran["work"] / "clean" / "cleaning_summary.json").read_text("utf-8"))
    accepted = {
        s["experiment_id"]: s["accepted"] for s in summary["series"] if s["signal"] == "voltage"
    }
    assert {eid: len(got[eid]) for eid in IDS} == accepted
    assert accepted["EXP_001"] == accepted["EXP_002"] - 1 == accepted["EXP_003"] - 1


def test_s6_13_overlay_of_one_experiment_alone_is_the_same_series(ran, resolver):
    rows = resolver.rows(6, ["EXP_002"], signal="voltage")
    assert {row["experiment_id"] for row in rows} == {"EXP_002"}
    together = overlay_by_experiment(resolver.rows(6, list(IDS), signal="voltage"))["EXP_002"]
    assert overlay_by_experiment(rows)["EXP_002"] == together


def test_s6_15_metric_overlay_uses_the_metrics_series_on_the_same_axis(ran, resolver):
    rows = resolver.rows(7, list(IDS), metric="capture_efficiency")
    got = overlay_by_experiment(rows)
    points = plain_points(
        ran,
        "SELECT experiment_id, CAST(time AS BIGINT) AS t, value FROM metrics_series "
        f"WHERE metric = 'capture_efficiency' AND metrics_version = '{METRICS}' "
        f"AND policy_version = '{POLICY}' ORDER BY experiment_id, time",
    )
    assert all(points[eid] for eid in IDS)
    assert_overlay(got, expected_overlay(ran, points))
    for eid in IDS:
        assert 0.0 <= min(x for x, _ in got[eid]) < 1.0


# ------------------------------------------------------------------ S6.14


def pg_expected(ran: dict, sql: str, ids: list[str]) -> list[tuple]:
    return pg_rows(ran["schema"], sql, (ids,))


@pytest.mark.parametrize("selection", [list(IDS), ["EXP_001", "EXP_003"], ["EXP_002"]])
def test_s6_14_kpi_panels_return_the_stored_rows(ran, resolver, selection):
    whole = resolver.rows(2, selection)
    assert_same_rows(
        columns_of(whole, "experiment_id", "metric", "value", "unit", "coverage", "status"),
        pg_expected(
            ran,
            "SELECT experiment_id, metric, value, unit, coverage, status FROM experiment_metrics "
            f"WHERE metrics_version = '{METRICS}' AND experiment_id = ANY(%s) "
            "ORDER BY experiment_id, metric",
            selection,
        ),
    )
    assert len(whole) == 13 * len(selection)

    steady = resolver.rows(3, selection)
    assert_same_rows(
        columns_of(
            steady,
            "experiment_id",
            "kpi",
            "value",
            "unit",
            "interval_low",
            "interval_high",
            "coverage",
            "status",
        ),
        pg_expected(
            ran,
            "SELECT experiment_id, kpi, value, unit, interval_low, interval_high, coverage, status "
            f"FROM comparison_kpi WHERE compare_version = '{COMPARE}' "
            "AND experiment_id = ANY(%s) ORDER BY experiment_id, kpi",
            selection,
        ),
    )
    assert len(steady) == 5 * len(selection)
    assert {row["status"] for row in whole + steady} - {None} <= set(STATUS_COLORS)


@pytest.mark.parametrize(
    ("selection", "pairs"),
    [
        (list(IDS), 3),
        (["EXP_001"], 2),  # with a selected end: 001-002 and 001-003
        (["EXP_002"], 2),
        (["EXP_002", "EXP_003"], 3),
    ],
)
def test_s6_14_pair_panels_return_pairs_with_a_selected_end(ran, resolver, selection, pairs):
    comparable = resolver.rows(4, selection)
    expected = pg_rows(
        ran["schema"],
        "SELECT a, b, conditions_status, differing FROM comparison_pair "
        f"WHERE compare_version = '{COMPARE}' AND (a = ANY(%s) OR b = ANY(%s)) ORDER BY a, b",
        (selection, selection),
    )
    assert_same_rows(columns_of(comparable, "a", "b", "conditions_status", "differing"), expected)
    assert len(comparable) == pairs

    differences = resolver.rows(5, selection)
    expected_kpis = pg_rows(
        ran["schema"],
        "SELECT a, b, kpi, unit, difference, interval_low, interval_high, excludes_zero, "
        f"coverage_status FROM comparison_pair_kpi WHERE compare_version = '{COMPARE}' "
        "AND (a = ANY(%s) OR b = ANY(%s)) ORDER BY a, b, kpi",
        (selection, selection),
    )
    assert_same_rows(
        columns_of(
            differences,
            "a",
            "b",
            "kpi",
            "unit",
            "difference",
            "interval_low",
            "interval_high",
            "excludes_zero",
            "coverage_status",
        ),
        expected_kpis,
    )
    assert len(differences) == 5 * pairs
    pair_ids = {(r["a"], r["b"]) for r in differences}
    assert pair_ids == {(r["a"], r["b"]) for r in comparable}


def test_s6_14_pair_conditions_are_the_fixture_ones(resolver):
    rows = resolver.rows(4, list(IDS))
    got = {
        (r["a"], r["b"]): (r["conditions_status"], set(filter(None, r["differing"].split(","))))
        for r in rows
    }
    assert got == {
        ("EXP_001", "EXP_002"): ("supported", {"current_setpoint"}),
        ("EXP_001", "EXP_003"): ("confounded", {"air_flow", "sorbent_batch"}),
        ("EXP_002", "EXP_003"): ("confounded", {"current_setpoint", "air_flow", "sorbent_batch"}),
    }
    # the panel's colour mapping covers every status the table can hold
    assert {status for status, _ in got.values()} <= set(
        mapping_colors(panel(DASHBOARD, 4), "conditions_status")
    )


def test_s6_14_experiments_and_quality_panels(ran, resolver):
    experiments = resolver.rows(1, ["EXP_001", "EXP_003"])
    assert [r["experiment_id"] for r in experiments] == ["EXP_001", "EXP_003"]
    starts = ran["starts"]
    assert [r["start_ms"] for r in experiments] == [
        starts[e] // 10**6 for e in ("EXP_001", "EXP_003")
    ]
    assert [r["end_ms"] - r["start_ms"] for r in experiments] == [1_200_000, 1_200_000]

    quality = resolver.rows(8, list(IDS))
    expected = pg_rows(
        ran["schema"],
        "SELECT experiment_id, "
        "SUM(present) FILTER (WHERE nominal_interval_s IS NOT NULL)::float8 "
        "/ SUM(expected)::float8, "
        "SUM(accepted)::float8 / SUM(present), SUM(bad)::float8 / SUM(present), "
        "SUM(uncertain)::float8 / SUM(present) "
        f"FROM signal_quality WHERE metrics_version = '{METRICS}' GROUP BY experiment_id "
        "ORDER BY experiment_id",
    )
    assert_same_rows(
        columns_of(
            quality,
            "experiment_id",
            "completeness",
            "valid_fraction",
            "bad_fraction",
            "uncertain_fraction",
        ),
        expected,
    )
    by_id = {r["experiment_id"]: r for r in quality}
    assert by_id["EXP_002"]["valid_fraction"] == 1.0
    assert by_id["EXP_001"]["valid_fraction"] < 1.0
