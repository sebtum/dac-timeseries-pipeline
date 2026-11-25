"""The dashboard checker without Grafana: interpolation, lint, summary, exit codes (S6.4, S6.5).

Everything that needs a server is in `tests/integration/test_grafana_stack.py`. Here a fake client
stands in for Grafana: it answers variable queries from a small table of experiments and answers
panel queries from rules the test sets, so the checker's own logic (selections, sweeps, time
ranges, totals, sorting, exit codes, refusals) is exercised on the real test dashboard
`tests/fixtures/grafana/dashboard.json`.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest

import scripts.check_dashboards as cli
from pipeline.grafana_check import (
    CheckError,
    QueryResult,
    exit_code,
    failures,
    format_instant,
    interpolate,
    lint,
    lint_uniqueness,
    load_dashboard,
    panel_targets,
    parse_time_range,
    provisioned_uids,
    run_check,
    to_epoch_ms,
    variables_used,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD = REPO_ROOT / "tests" / "fixtures" / "grafana" / "dashboard.json"
DATASOURCES = REPO_ROOT / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
CONTRACT = json.loads(
    (REPO_ROOT / "contracts" / "dashboard_check.schema.json").read_text(encoding="utf-8")
)
EXAMPLE = json.loads(
    (REPO_ROOT / "contracts" / "examples" / "dashboard_check.example.json").read_text("utf-8")
)
UIDS = {"influx-dac", "pg-dac"}
# EXP_001 and EXP_002 as epoch milliseconds (2026-05-04T08:00:00Z, 2026-05-11T09:00:00Z; 60 s each)
EXPERIMENT_MS = {
    "EXP_001": (1777881600000, 1777881660000),
    "EXP_002": (1778490000000, 1778490060000),
}


# ------------------------------------------------------------------------- S6.4 interpolation


def test_s6_4_each_format_gives_the_value_the_dashboards_need():
    values = {"experiment": ["EXP_001", "EXP_002"], "windows": "('EXP_001', 1, 2)"}
    assert interpolate("IN (${experiment:sqlstring})", values) == "IN ('EXP_001','EXP_002')"
    assert interpolate("VALUES ${windows:raw}", values) == "VALUES ('EXP_001', 1, 2)"
    assert interpolate("$__timeFilter(time)", values) == "$__timeFilter(time)"


def test_a_list_is_joined_by_commas_and_both_name_forms_are_replaced():
    values = {"a": ["x", "y"], "b": "z"}
    assert interpolate("$a|${a}|${a:csv}|${a:raw}|$b|${b}", values) == "x,y|x,y|x,y|x,y|z|z"


def test_sqlstring_doubles_a_single_quote():
    assert interpolate("${name:sqlstring}", {"name": "O'Brien"}) == "'O''Brien'"
    assert interpolate("${name:sqlstring}", {"name": ["a", "O'B"]}) == "'a','O''B'"


def test_s6_4_an_unknown_variable_or_format_raises_an_error_naming_it():
    with pytest.raises(CheckError, match="nope"):
        interpolate("SELECT ${nope}", {"experiment": "EXP_001"})
    with pytest.raises(CheckError, match="json"):
        interpolate("${experiment:json}", {"experiment": "EXP_001"})
    with pytest.raises(CheckError, match="nope"):
        interpolate("$nope", {})


def test_grafana_macros_and_builtin_variables_are_left_alone():
    text = "WHERE $__timeFilter(time) AND x = ${__from:date:iso} AND ${__data.fields.id}"
    assert interpolate(text, {}) == text


def test_a_dollar_that_names_nothing_is_not_a_variable():
    assert interpolate("price $5 and a regex /^a$/", {}) == "price $5 and a regex /^a$/"


def test_variables_used_gives_name_and_format_and_skips_macros():
    text = "$a ${b} ${c:sqlstring} $__timeFilter(time) ${__from} ${d:raw} ${d:raw}"
    assert variables_used(text) == {("a", None), ("b", None), ("c", "sqlstring"), ("d", "raw")}


# ------------------------------------------------------------------------------ lint (S6.5)


def dashboard(**changes) -> dict:
    doc = {
        "uid": "t",
        "title": "T",
        "templating": {
            "list": [
                {"name": "influx", "type": "datasource"},
                {"name": "pg", "type": "datasource"},
                {"name": "experiment", "type": "constant", "query": "EXP_001"},
            ]
        },
        "panels": [
            {
                "id": 1,
                "title": "P",
                "datasource": {"type": "influxdb", "uid": "${influx}"},
                "targets": [{"refId": "A", "rawSql": "SELECT '${experiment}'"}],
            }
        ],
    }
    doc.update(changes)
    return doc


def test_a_clean_dashboard_has_no_problems():
    assert lint(dashboard(), UIDS) == []


def test_s6_5_the_lint_reports_all_three_problems():
    doc = dashboard()
    doc["panels"] = [
        {
            "id": 1,
            "title": "Other source",
            "datasource": {"type": "influxdb", "uid": "other"},
            "targets": [{"refId": "A", "rawSql": "SELECT 1"}],
        },
        {
            "id": 2,
            "title": "Undeclared",
            "datasource": {"uid": "${pg}"},
            "targets": [{"refId": "A", "rawSql": "SELECT ${undeclared}"}],
        },
        {"id": 2, "title": "Same id", "type": "text"},
    ]
    problems = lint(doc, UIDS)
    assert len(problems) == 3, problems
    assert any("'other'" in p and "Other source" in p for p in problems)
    assert any("undeclared" in p for p in problems)
    assert any("panel id 2" in p for p in problems)


def test_provisioned_uids_and_the_variables_both_count_as_datasources():
    doc = dashboard()
    for ref in ({"uid": "influx-dac"}, {"uid": "$pg"}, "pg-dac"):
        doc["panels"][0]["datasource"] = ref
        assert lint(doc, UIDS) == [], ref


def test_a_target_datasource_is_checked_too_and_a_missing_one_is_a_problem():
    doc = dashboard()
    doc["panels"][0]["targets"][0]["datasource"] = {"uid": "other"}
    assert any("other" in p for p in lint(doc, UIDS))
    doc = dashboard()
    del doc["panels"][0]["datasource"]
    assert any("no datasource" in p for p in lint(doc, UIDS))


def test_an_annotation_datasource_is_checked_and_the_builtin_one_is_skipped():
    doc = dashboard()
    doc["annotations"] = {
        "list": [
            {"builtIn": 1, "name": "Annotations & Alerts", "datasource": {"uid": "-- Grafana --"}},
            {"name": "Gaps", "datasource": {"uid": "other"}, "target": {"rawSql": "SELECT 1"}},
        ]
    }
    problems = lint(doc, UIDS)
    assert len(problems) == 1 and "Gaps" in problems[0]


def test_a_format_outside_the_allowed_four_is_reported_once():
    doc = dashboard()
    doc["panels"][0]["targets"][0]["rawSql"] = "SELECT ${experiment:json} ${experiment:json}"
    problems = lint(doc, UIDS)
    assert len(problems) == 1 and "json" in problems[0]


def test_every_allowed_format_passes_the_lint():
    doc = dashboard()
    doc["panels"][0]["targets"][0]["rawSql"] = (
        "${experiment} ${experiment:raw} ${experiment:sqlstring} ${experiment:csv} ${__from:date}"
    )
    assert lint(doc, UIDS) == []


def test_a_variable_used_in_an_earlier_variable_is_reported():
    doc = dashboard()
    doc["templating"]["list"].insert(
        2,
        {
            "name": "early",
            "type": "query",
            "datasource": {"uid": "${pg}"},
            "query": "${experiment}",
        },
    )
    assert any("declared later" in p for p in lint(doc, UIDS))


def test_a_duplicate_variable_name_and_a_missing_dashboard_uid_are_reported():
    doc = dashboard()
    doc["templating"]["list"].append({"name": "pg", "type": "constant", "query": "x"})
    del doc["uid"]
    problems = lint(doc, UIDS)
    assert any("'pg'" in p and "more than once" in p for p in problems)
    assert any("no uid" in p for p in problems)


def test_panels_inside_rows_are_linted_and_their_ids_count():
    doc = dashboard()
    doc["panels"].append(
        {
            "id": 9,
            "type": "row",
            "title": "Row",
            "panels": [
                {
                    "id": 1,
                    "title": "Nested",
                    "datasource": {"uid": "nope"},
                    "targets": [{"refId": "A", "rawSql": "SELECT 1"}],
                }
            ],
        }
    )
    problems = lint(doc, UIDS)
    assert any("Nested" in p and "'nope'" in p for p in problems)
    assert any("panel id 1" in p for p in problems)


def test_a_target_without_ref_id_or_with_a_repeated_one_is_reported():
    doc = dashboard()
    doc["panels"][0]["targets"] = [{"rawSql": "SELECT 1"}, {"refId": "A"}, {"refId": "A"}]
    problems = lint(doc, UIDS)
    assert any("no refId" in p for p in problems)
    assert any("used twice" in p for p in problems)


def test_dashboard_uids_must_be_unique_across_files():
    assert lint_uniqueness({"a.json": {"uid": "x"}, "b.json": {"uid": "y"}}) == []
    problems = lint_uniqueness({"a.json": {"uid": "x"}, "b.json": {"uid": "x"}})
    assert len(problems) == 1 and "a.json" in problems[0] and "b.json" in problems[0]


def test_the_test_dashboard_is_clean_against_the_committed_provisioning():
    assert provisioned_uids(DATASOURCES) == UIDS
    assert lint(load_dashboard(DASHBOARD), provisioned_uids(DATASOURCES)) == []


def test_load_dashboard_refuses_a_missing_or_malformed_file(tmp_path):
    with pytest.raises(CheckError, match="cannot read"):
        load_dashboard(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CheckError, match="not valid JSON"):
        load_dashboard(tmp_path / "bad.json")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    with pytest.raises(CheckError, match="not a JSON object"):
        load_dashboard(tmp_path / "list.json")


# ----------------------------------------------------------------------------- panel_targets


def test_panel_targets_includes_rows_and_is_in_panel_id_order():
    doc = {
        "panels": [
            {"id": 5, "title": "five", "targets": [{"refId": "A"}, {"refId": "B"}]},
            {
                "id": 10,
                "type": "row",
                "title": "row",
                "panels": [{"id": 2, "title": "two", "targets": [{"refId": "A"}]}],
            },
            {"id": 3, "title": "text"},
        ]
    }
    got = [(p["id"], t["refId"]) for p, t in panel_targets(doc)]
    assert got == [(2, "A"), (5, "A"), (5, "B")]


def test_panel_targets_of_the_test_dashboard_are_its_four_panels():
    titles = [p["title"] for p, _ in panel_targets(load_dashboard(DASHBOARD))]
    assert titles == [
        "Experiments",
        "Readings: ${signal}",
        "Overlay: ${signal}",
        "Gaps and stuck stretches",
    ]


# ---------------------------------------------------------------------------- time handling


def test_instants_round_trip():
    assert to_epoch_ms("2026-05-04T08:00:00Z") == 1777881600000
    assert to_epoch_ms("2026-05-04T08:00:00.250Z") == 1777881600250
    assert to_epoch_ms("1777881600000") == 1777881600000
    assert format_instant(1777881600000) == "2026-05-04T08:00:00Z"
    assert format_instant(1777881600250) == "2026-05-04T08:00:00.250Z"
    with pytest.raises(CheckError):
        to_epoch_ms("yesterday")
    with pytest.raises(CheckError, match="time zone"):
        to_epoch_ms("2026-05-04T08:00:00")


def test_parse_time_range():
    assert parse_time_range("window") == ("window", None)
    assert parse_time_range("span") == ("span", None)
    mode, fixed = parse_time_range("2026-05-04T08:00:00Z,2026-05-04T09:00:00Z")
    assert mode == "fixed" and fixed == (1777881600000, 1777885200000)
    for bad in ("later", "2026-05-04T09:00:00Z,2026-05-04T08:00:00Z", "a,b,c"):
        with pytest.raises(CheckError):
            parse_time_range(bad)


# ---------------------------------------------------------------------------- a fake Grafana


class FakeClient:
    """Answers variable queries from `EXPERIMENT_MS` and panel queries from `panel_rows`."""

    def __init__(self, panel_rows=None, errors=None, only=None):
        self.panel_rows = panel_rows or {}  # substring of the SQL -> rows (default 3)
        self.errors = errors or {}  # substring of the SQL -> error text
        self.only = only  # experiments the fake knows (default all)
        self.calls: list[tuple[str, str, int, int]] = []

    @property
    def ids(self):
        return sorted(EXPERIMENT_MS if self.only is None else self.only)

    def health(self):
        return {"database": "ok", "version": "13.3.2"}

    def version(self):
        return "13.3.2"

    def datasource_kind(self, uid):
        return "pg" if uid.startswith("pg") else "influx"

    def query(self, uid, target, time_from, time_to):
        sql = target["rawSql"]
        self.calls.append((uid, sql, time_from, time_to))
        assert "${" not in sql and "$experiment" not in sql, f"uninterpolated: {sql}"
        if re.search(r"SELECT experiment_id FROM \w+\.experiment ORDER BY 1", sql):
            return QueryResult(len(self.ids), ["experiment_id"], None, [self.ids])
        if "MIN(start_time)" in sql:
            wanted = re.findall(r"'(EXP_\d+)'", sql) or self.ids
            starts = [EXPERIMENT_MS[e][0] for e in wanted]
            ends = [EXPERIMENT_MS[e][1] for e in wanted]
            return QueryResult(1, ["t0", "t1"], None, [[min(starts)], [max(ends)]])
        if "string_agg" in sql:
            return QueryResult(1, ["windows"], None, [["('EXP_001', 1, 2)"]])
        for needle, error in self.errors.items():
            if needle in sql:
                return QueryResult(0, [], error)
        for needle, rows in self.panel_rows.items():
            if needle in sql:
                return QueryResult(rows, ["a", "b"], None, [[0] * rows, [0] * rows])
        return QueryResult(3, ["a", "b"], None, [[0] * 3, [0] * 3])


@pytest.fixture
def loaded():
    return [(DASHBOARD, load_dashboard(DASHBOARD))]


def check(client, loaded, **kwargs):
    return run_check(client, loaded, repo_root=REPO_ROOT, **kwargs)


def test_every_experiment_alone_plus_all_together_each_with_its_own_window(loaded):
    summary = check(FakeClient(), loaded)
    jsonschema.validate(summary, CONTRACT)
    assert [r["selection"] for r in summary["runs"]] == [
        ["EXP_001"],
        ["EXP_001", "EXP_002"],
        ["EXP_002"],
    ]
    windows = [(r["time_from"], r["time_to"]) for r in summary["runs"]]
    assert windows == [
        ("2026-05-04T08:00:00Z", "2026-05-04T08:01:00Z"),
        ("2026-05-04T08:00:00Z", "2026-05-11T09:01:00Z"),
        ("2026-05-11T09:00:00Z", "2026-05-11T09:01:00Z"),
    ]
    assert summary["grafana_version"] == "13.3.2"
    assert summary["source"]["dashboards"] == ["tests/fixtures/grafana/dashboard.json"]
    assert summary["totals"] == {
        "runs": 3,
        "panel_targets": 12,
        "with_rows": 12,
        "empty": 0,
        "empty_allowed": 0,
        "errors": 0,
        "annotation_errors": 0,
    }
    assert exit_code(summary) == 0
    run = summary["runs"][0]
    assert [p["panel_id"] for p in run["panels"]] == [1, 2, 3, 4]
    assert run["panels"][1]["title"] == "Readings: ${signal}"  # raw title, not interpolated
    assert [(a["name"], a["datasource"]) for a in run["annotations"]] == [("Gaps", "influx")]
    assert run["panels"][0]["targets"][0]["datasource"] == "pg"


def test_the_queries_carry_the_interpolated_variables_and_the_runs_time_range(loaded):
    client = FakeClient()
    check(client, loaded, experiments=["EXP_002"])
    panel_calls = [c for c in client.calls if "readings_processed r JOIN" in c[1]]
    (uid, sql, time_from, time_to) = panel_calls[-1]
    assert uid == "influx-dac"
    assert "VALUES ('EXP_001', 1, 2)" in sql  # the windows variable, raw
    assert "r.signal = 'voltage'" in sql and "r.policy_version = 'm3-v1'" in sql
    assert (time_from, time_to) == EXPERIMENT_MS["EXP_002"]
    experiments_sql = next(c[1] for c in client.calls if "end_time FROM public.experiment" in c[1])
    assert "IN ('EXP_002')" in experiments_sql


def test_experiments_given_select_only_those_and_together_only_when_several(loaded):
    one = check(FakeClient(), loaded, experiments=["EXP_002"])
    assert [r["selection"] for r in one["runs"]] == [["EXP_002"]]
    both = check(FakeClient(), loaded, experiments=["EXP_002", "EXP_001"])
    assert [r["selection"] for r in both["runs"]] == [
        ["EXP_001"],
        ["EXP_001", "EXP_002"],
        ["EXP_002"],
    ]


def test_an_unknown_experiment_is_refused(loaded):
    with pytest.raises(CheckError, match="EXP_404"):
        check(FakeClient(), loaded, experiments=["EXP_404"])


def test_sweep_runs_each_selection_once_per_value_of_the_variable(loaded):
    summary = check(FakeClient(), loaded, sweep=["signal"], experiments=["EXP_001"])
    assert [(r["selection"], r["sweep"]) for r in summary["runs"]] == [
        (["EXP_001"], {"signal": "current"}),
        (["EXP_001"], {"signal": "voltage"}),
    ]
    assert summary["source"]["sweep"] == ["signal"]
    assert summary["totals"]["runs"] == 2


def test_the_swept_value_reaches_the_queries(loaded):
    client = FakeClient()
    check(client, loaded, sweep=["signal"], experiments=["EXP_001"])
    readings = [c[1] for c in client.calls if "SELECT time, value, value_raw" in c[1]]
    assert any("signal = 'current'" in s for s in readings)
    assert any("signal = 'voltage'" in s for s in readings)


def test_a_sweep_or_override_of_an_undeclared_variable_is_refused(loaded):
    with pytest.raises(CheckError, match="nope"):
        check(FakeClient(), loaded, sweep=["nope"])
    with pytest.raises(CheckError, match="nope"):
        check(FakeClient(), loaded, overrides={"nope": "1"})


def test_overrides_replace_variables_and_are_recorded(loaded):
    client = FakeClient()
    summary = check(
        client, loaded, experiments=["EXP_001"], overrides={"signal": "current", "pg_schema": "s1"}
    )
    assert summary["source"]["overrides"] == {"signal": "current", "pg_schema": "s1"}
    sql = [c[1] for c in client.calls if "end_time FROM" in c[1]]
    assert sql and all("s1.experiment" in s for s in sql)
    assert any("signal = 'current'" in c[1] for c in client.calls)


def test_a_datasource_override_picks_the_uid_the_queries_go_to(loaded):
    client = FakeClient()
    check(client, loaded, experiments=["EXP_001"], overrides={"influx": "tmp-uid"})
    assert {c[0] for c in client.calls if "readings_processed" in c[1]} == {"tmp-uid"}


def test_span_runs_from_the_earliest_start_to_the_latest_end_of_all_experiments(loaded):
    summary = check(FakeClient(), loaded, experiments=["EXP_001"], time_range="span")
    (run,) = summary["runs"]
    assert (run["time_from"], run["time_to"]) == ("2026-05-04T08:00:00Z", "2026-05-11T09:01:00Z")
    assert summary["source"]["time_range"] == "span"


def test_a_fixed_range_is_used_as_given_and_asks_postgres_nothing(loaded):
    client = FakeClient()
    summary = check(
        client,
        loaded,
        experiments=["EXP_001"],
        time_range="2026-05-04T08:00:00Z,2026-05-04T08:00:30Z",
    )
    (run,) = summary["runs"]
    assert (run["time_from"], run["time_to"]) == ("2026-05-04T08:00:00Z", "2026-05-04T08:00:30Z")
    assert summary["source"]["time_range"] == "fixed"
    assert not any("MIN(start_time)" in c[1] for c in client.calls)


def test_an_empty_panel_target_fails_the_run_and_is_named(loaded):
    summary = check(FakeClient(panel_rows={"FROM quality_intervals WHERE": 0}), loaded)
    assert exit_code(summary) == 1
    assert summary["totals"]["empty"] == 3
    lines = failures(summary)
    assert len(lines) == 3 and all("'Gaps and stuck stretches'" in line for line in lines)
    assert "no rows" in lines[0]


def test_allow_empty_by_exact_title_turns_the_same_run_green_and_counts_it(loaded):
    client = FakeClient(panel_rows={"FROM quality_intervals WHERE": 0})
    summary = check(client, loaded, allow_empty=["Gaps and stuck stretches"])
    assert exit_code(summary) == 0
    assert summary["totals"]["empty"] == 0
    assert summary["totals"]["empty_allowed"] == 3
    assert summary["source"]["allow_empty"] == ["Gaps and stuck stretches"]
    assert all(
        p["empty_allowed"] for r in summary["runs"] for p in r["panels"] if p["panel_id"] == 4
    )
    # not a prefix match
    summary = check(client, loaded, allow_empty=["Gaps"])
    assert exit_code(summary) == 1


def test_a_failing_query_counts_only_under_errors_with_the_servers_text(loaded):
    client = FakeClient(errors={"FROM quality_intervals WHERE": "No field named nope"})
    summary = check(client, loaded, allow_empty=["Gaps and stuck stretches"])
    assert exit_code(summary) == 1  # an error is not excused by --allow-empty
    totals = summary["totals"]
    assert totals["errors"] == 3 and totals["empty"] == 0 and totals["empty_allowed"] == 0
    assert totals["panel_targets"] == (
        totals["with_rows"] + totals["empty"] + totals["empty_allowed"] + totals["errors"]
    )
    target = summary["runs"][0]["panels"][3]["targets"][0]
    assert (target["rows"], target["fields"], target["error"]) == (0, [], "No field named nope")
    assert any("No field named nope" in line for line in failures(summary))
    jsonschema.validate(summary, CONTRACT)


def test_a_failing_annotation_exits_1_but_an_empty_one_does_not(loaded):
    summary = check(FakeClient(panel_rows={"SELECT time, to_timestamp_nanos": 0}), loaded)
    assert exit_code(summary) == 0
    assert all(
        a["rows"] == 0 and a["error"] is None for r in summary["runs"] for a in r["annotations"]
    )
    summary = check(FakeClient(errors={"SELECT time, to_timestamp_nanos": "boom"}), loaded)
    assert exit_code(summary) == 1
    assert summary["totals"]["annotation_errors"] == 3
    assert summary["totals"]["errors"] == 0
    assert any("annotation 'Gaps'" in line and "boom" in line for line in failures(summary))


def test_a_variable_query_that_fails_or_returns_nothing_is_a_refusal(loaded):
    with pytest.raises(CheckError, match="experiment"):
        check(FakeClient(only=[]), loaded)
    broken = copy.deepcopy(loaded[0][1])
    broken["templating"]["list"][4]["query"] = "SELECT broken"
    with pytest.raises(CheckError):
        check(FakeClient(errors={"SELECT broken": "no such table"}), [(DASHBOARD, broken)])


def test_a_dashboard_without_an_experiment_variable_is_refused(loaded):
    doc = copy.deepcopy(loaded[0][1])
    doc["templating"]["list"] = [v for v in doc["templating"]["list"] if v["name"] != "experiment"]
    with pytest.raises(CheckError, match="experiment"):
        check(FakeClient(), [(DASHBOARD, doc)])


def test_runs_are_sorted_and_two_runs_are_equal_except_timing(loaded):
    first = check(FakeClient(), loaded, sweep=["signal"])
    second = check(FakeClient(), loaded, sweep=["signal"])
    keys = [(r["dashboard_uid"], r["selection"], sorted(r["sweep"].items())) for r in first["runs"]]
    assert keys == sorted(keys)
    assert {k: v for k, v in first.items() if k != "timing"} == {
        k: v for k, v in second.items() if k != "timing"
    }
    assert first["timing"]["queries"] > 0
    jsonschema.validate(first, CONTRACT)


def test_the_committed_contract_example_is_valid_and_matches_the_summary_shape(loaded):
    jsonschema.validate(EXAMPLE, CONTRACT)
    assert set(EXAMPLE) == set(check(FakeClient(), loaded))


def test_a_hidden_target_is_not_run(loaded):
    doc = copy.deepcopy(loaded[0][1])
    doc["panels"][0]["targets"].append({"refId": "B", "rawSql": "SELECT 'hidden'", "hide": True})
    client = FakeClient()
    summary = check(client, [(DASHBOARD, doc)], experiments=["EXP_001"])
    assert not any("'hidden'" in c[1] for c in client.calls)
    assert [t["ref_id"] for t in summary["runs"][0]["panels"][0]["targets"]] == ["A"]


# ------------------------------------------------------------------------------ the CLI


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GRAFANA_URL", "http://grafana.invalid")
    monkeypatch.setenv("GRAFANA_ADMIN_USER", "admin")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "pw")


def run_cli(tmp_path, *args, client=None):
    fake = client or FakeClient()
    code = cli.main(
        ["--dashboard", str(DASHBOARD), "--report-dir", str(tmp_path / "out"), *args],
        client_factory=lambda *_: fake,
    )
    return code, tmp_path / "out" / "dashboard_check.json"


def test_exit_0_writes_the_file(tmp_path, env, capsys):
    code, path = run_cli(tmp_path, "--experiment", "EXP_001")
    assert code == 0
    jsonschema.validate(json.loads(path.read_text(encoding="utf-8")), CONTRACT)
    assert "1 runs" in capsys.readouterr().out


def test_exit_1_writes_the_file_and_names_the_panel(tmp_path, env, capsys):
    code, path = run_cli(
        tmp_path, client=FakeClient(panel_rows={"FROM quality_intervals WHERE": 0})
    )
    assert code == 1
    assert path.exists()
    assert "Gaps and stuck stretches" in capsys.readouterr().err


def test_exit_1_then_0_with_allow_empty(tmp_path, env):
    client = FakeClient(panel_rows={"FROM quality_intervals WHERE": 0})
    assert run_cli(tmp_path, client=client)[0] == 1
    assert run_cli(tmp_path, "--allow-empty", "Gaps and stuck stretches", client=client)[0] == 0


def test_exit_2_when_grafana_is_unreachable_and_no_file_is_written(tmp_path, env, capsys):
    class Down(FakeClient):
        def health(self):
            raise CheckError("Grafana not reachable at http://localhost:1: refused")

    code, path = run_cli(tmp_path, client=Down())
    assert code == 2
    assert not path.exists() and not path.parent.exists()
    assert "not reachable" in capsys.readouterr().err


def test_exit_2_for_a_refused_login(tmp_path, env):
    class Refused(FakeClient):
        def health(self):
            raise CheckError("Grafana login refused at http://x (HTTP 401)")

    assert run_cli(tmp_path, client=Refused())[0] == 2


def test_exit_2_for_an_unknown_experiment_a_bad_var_and_a_bad_time_range(tmp_path, env):
    for args in (
        ("--experiment", "EXP_404"),
        ("--var", "no-equals-sign"),
        ("--time-range", "later"),
        ("--sweep", "nope"),
    ):
        code, path = run_cli(tmp_path, *args)
        assert code == 2, args
        assert not path.parent.exists(), args


def test_exit_2_when_a_dashboard_fails_the_lint_or_cannot_be_read(tmp_path, env, capsys):
    doc = load_dashboard(DASHBOARD)
    doc["panels"][0]["datasource"] = {"uid": "other"}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    code = cli.main(
        ["--dashboard", str(bad), "--report-dir", str(tmp_path / "out")],
        client_factory=lambda *_: FakeClient(),
    )
    assert code == 2
    assert "lint failed" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
    code = cli.main(
        ["--dashboard", str(tmp_path / "missing.json"), "--report-dir", str(tmp_path / "out")],
        client_factory=lambda *_: FakeClient(),
    )
    assert code == 2


def test_exit_2_without_grafana_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAFANA_ADMIN_USER", raising=False)
    monkeypatch.delenv("GRAFANA_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(cli, "read_env", lambda *_: {})
    assert run_cli(tmp_path)[0] == 2


def test_exit_2_for_duplicate_dashboard_uids(tmp_path, env):
    copy_path = tmp_path / "copy.json"
    copy_path.write_text(DASHBOARD.read_text(encoding="utf-8"), encoding="utf-8")
    code = cli.main(
        ["--dashboard", str(DASHBOARD), str(copy_path), "--report-dir", str(tmp_path / "out")],
        client_factory=lambda *_: FakeClient(),
    )
    assert code == 2
