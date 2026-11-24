"""Unit tests for `python -m scripts.compare` with a fake gateway and a fake Postgres (M5: the exit
codes and refusal paths of S5.18, and the shape checks of S5.19 that need no server).

No server here: `FakeGateway` answers the reads from small hand-made series and records every
call, the Postgres functions are injected through `Deps`. The fake gateway has no write method at
all, so a run that tried to write would fail. The live run on the fixture is
`tests/e2e/test_compare_cli.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jsonschema
import psycopg
import pytest

from pipeline import compare, compare_run
from pipeline.cleaning_influx import PROCESSED_TABLE
from pipeline.compare_run import Config, Deps, render_report, round_floats, run
from pipeline.compare_store import DatabaseMissing
from pipeline.ingest_influx import DatabaseCheckFailed
from pipeline.metrics import METRIC_UNITS
from pipeline.profiling_sql import QueryFailed
from scripts import compare as compare_cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "comparison_summary.schema.json").read_text(encoding="utf-8")
)

START = datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC)
START_NS = 1_777_881_600 * 10**9  # 2026-05-04T08:00:00Z
NS = 10**9
DURATION_S = 120
SECRET = "SECRET-TOKEN-VALUE"
ENV = {
    "INFLUX_HOST": "http://influx.invalid",
    "INFLUX_TOKEN": SECRET,
    "POSTGRES_HOST": "pg.invalid",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "dac",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "SECRET-PASSWORD-VALUE",
}


def at(seconds: int) -> int:
    return START_NS + seconds * NS


def good_series() -> dict[str, list[tuple[int, float]]]:
    """120 s of every signal: 1 Hz electrics and flows, 0.5 Hz CO2 and pressure drop."""
    every = range(DURATION_S)
    half = range(0, DURATION_S, 2)
    return {
        "voltage": [(at(k), 100.0 + k % 2) for k in every],
        "current": [(at(k), 150.0) for k in every],
        "flow": [(at(k), 40.0 + k % 3) for k in every],
        "pressure": [(at(k), 2.5 + 0.01 * (k % 5)) for k in every],
        "electrolyte_temperature": [(at(k), 35.0) for k in range(0, DURATION_S, 5)],
        "air_flow": [(at(k), 1200.0) for k in every],
        "fan_speed": [(at(k), 900.0) for k in every],
        "pressure_drop": [(at(k), 15.0) for k in half],
        "current_setpoint": [(at(k), 150.0) for k in every],
        "solvent_flow": [(at(k), 8.0) for k in half],
        "ambient_temperature": [(at(0), 15.0), (at(60), 15.0)],
        "relative_humidity": [(at(0), 50.0), (at(60), 50.0)],
        "co2_in_ppm": [(at(k), 400.0) for k in half],
        "co2_out_ppm": [(at(k), 100.0) for k in half],
        "power_computed": [(at(k), 15000.0) for k in every],
        "capture_rate": [(at(k), 0.7) for k in half],
        "capture_efficiency": [(at(k), 0.75) for k in half],
    }


# STARTUP [0, 30), STEADY_STATE [30, 120): the steady window is [90, 120) (settle margin 60 s).
EVENTS = [(at(0), at(30), "STARTUP"), (at(30), at(120), "STEADY_STATE")]


class FakeGateway:
    """Answers the reads from `inputs`, records every call and has no write method."""

    def __init__(self, inputs: dict[str, list[tuple[int, float]]]) -> None:
        self.inputs = inputs
        self.queries = 0
        self.closed = False
        self.calls: list[tuple[str, str, datetime, datetime]] = []
        self.policy_rows = True
        self.metrics_rows = True
        self.table_names = {PROCESSED_TABLE}
        self.fail_read = False
        self.database_missing = False
        self.events = list(EVENTS)

    def require_database(self) -> None:
        if self.database_missing:
            raise DatabaseMissing("dac_raw")

    def tables(self) -> set[str]:
        return self.table_names

    def has_policy_rows(self, policy_version):
        self.queries += 1
        return self.policy_rows

    def has_metrics_rows(self, metrics_version, policy_version):
        self.queries += 1
        return self.metrics_rows

    def _read(self, kind, experiment_id, name, start, end):
        self.queries += 1
        self.calls.append((kind, experiment_id, start, end))
        if self.fail_read:
            raise QueryFailed(f"{kind}:{experiment_id}/{name}", RuntimeError("boom"))

    def accepted_series(self, experiment_id, signal, start, end, policy_version):
        self._read("accepted", experiment_id, signal, start, end)
        return list(self.inputs.get(signal, []))

    def raw_series(self, experiment_id, signal, start, end, policy_version):
        self._read("raw", experiment_id, signal, start, end)
        return [(t, v) for t, v in self.inputs.get(signal, [])]

    def state_events(self, experiment_id, signal, start, end, policy_version):
        self._read("events", experiment_id, signal, start, end)
        return list(self.events)

    def metric_series(self, experiment_id, metric, metrics_version, policy_version, start, end):
        self._read("metric", experiment_id, metric, start, end)
        return list(self.inputs.get(metric, []))

    def close(self) -> None:
        self.closed = True


class FakePostgres:
    """Answers the three Postgres functions of `Deps` and records the connection."""

    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        self.connected: list[str] = []
        self.conn_closed = False
        self.check_result: str | None = None
        self.absent = False
        self.no_metrics = False
        self.connect_error: Exception | None = None
        self.read_error: Exception | None = None
        self.start_time = START
        self.end_time = START + timedelta(seconds=DURATION_S)

    def pg_connect(self, conninfo, schema):
        if self.connect_error is not None:
            raise self.connect_error
        self.connected.append(schema)
        outer = self

        class Conn:
            def close(self) -> None:
                outer.conn_closed = True

        return Conn()

    def pg_check(self, conn):
        return self.check_result

    def experiment_rows(self, conn, ids):
        if self.read_error is not None:
            raise self.read_error
        if self.absent:
            return {}
        return {
            self.experiment_id: {
                "experiment_id": self.experiment_id,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration_s": DURATION_S,
                "current_setpoint_nominal_a": 150.0,
                "air_flow_nominal_m3h": 1200.0,
                "solvent_flow_nominal_lmin": 8.0,
                "operator": "Op A",
                "sorbent_batch": None,
                "notes": None,
            }
        }

    def experiment_metric_rows(self, conn, metrics_version, ids):
        if self.no_metrics:
            return {}
        return {
            self.experiment_id: {
                name: {"value": 1.0, "unit": unit, "coverage": 1.0, "status": "complete"}
                for name, unit in METRIC_UNITS.items()
            }
        }


class Rig:
    """One run: the fakes, the config and the dependency bundle."""

    def __init__(self, tmp_path: Path, experiment_id: str = "EXP_001") -> None:
        self.tmp_path = tmp_path
        self.experiment_id = experiment_id
        self.report_dir = tmp_path / "report"
        self.experiments = tmp_path / "experiments.json"
        self.experiments.write_text(
            json.dumps(
                [
                    {
                        "experiment_id": experiment_id,
                        "start_time": "2026-05-04T08:00:00Z",
                        "end_time": "2026-05-04T08:02:00Z",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.gateway = FakeGateway(good_series())
        self.pg = FakePostgres(experiment_id)
        self.databases = ["dac_raw"]
        self.database_error: Exception | None = None
        self.factory_calls = 0
        self.env = dict(ENV)

    def list_databases(self, host, token):
        if self.database_error is not None:
            raise self.database_error
        return self.databases

    def gateway_factory(self, host, token, database):
        self.factory_calls += 1
        return self.gateway

    def config(self, **changes) -> Config:
        base = {
            "database": "dac_raw",
            "experiments_path": self.experiments,
            "report_dir": self.report_dir,
            "policy_version": "m3-v1",
            "metrics_version": "m4-v1",
            "pg_schema": "public",
        }
        return Config(**{**base, **changes})

    def deps(self) -> Deps:
        return Deps(
            list_databases=self.list_databases,
            gateway_factory=self.gateway_factory,
            pg_connect=self.pg.pg_connect,
            pg_check=self.pg.pg_check,
            experiment_rows=self.pg.experiment_rows,
            experiment_metric_rows=self.pg.experiment_metric_rows,
            env=self.env,
        )

    def run(self, **changes) -> int:
        return run(self.config(**changes), self.deps())

    def summary(self) -> dict:
        return json.loads((self.report_dir / "comparison_summary.json").read_text(encoding="utf-8"))

    def assert_nothing_written(self) -> None:
        assert not self.report_dir.exists() or list(self.report_dir.iterdir()) == []


@pytest.fixture
def rig(tmp_path) -> Rig:
    return Rig(tmp_path)


# ------------------------------------------------------------------------------------- exit 0


def test_a_clean_run_exits_0_and_writes_both_files(rig, capsys):
    assert rig.run() == 0
    summary = rig.summary()
    jsonschema.validate(summary, SCHEMA)
    assert sorted(p.name for p in rig.report_dir.iterdir()) == [
        "comparison_report.md",
        "comparison_summary.json",
    ]
    assert [e["experiment_id"] for e in summary["experiments"]] == ["EXP_001"]
    assert summary["compare_version"] == "m5-v1"
    assert (summary["policy_version"], summary["metrics_version"]) == ("m3-v1", "m4-v1")
    assert summary["source"]["database"] == "dac_raw"
    assert rig.gateway.closed and rig.pg.conn_closed
    assert rig.pg.connected == ["public"]
    assert summary["timing"]["queries"] == rig.gateway.queries > 0
    out = capsys.readouterr().out
    assert "compare:" in out and SECRET not in out


def test_the_short_experiment_has_its_phases_and_its_one_steady_window(rig):
    assert rig.run() == 0
    entry = rig.summary()["experiments"][0]
    assert [(p["state"], p["start_s"], p["end_s"]) for p in entry["phases"]] == [
        ("STARTUP", 0, 30),
        ("STEADY_STATE", 30, 120),
    ]
    assert [(p["window_start_s"], p["window_end_s"]) for p in entry["phases"]] == [
        (None, None),
        (90, 120),
    ]
    assert entry["steady_seconds"] == 30
    # the whole-run metrics are the 13 copied rows, in the order of METRIC_UNITS
    assert list(entry["whole_run_metrics"]) == list(METRIC_UNITS)
    assert entry["metadata"]["sorbent_batch"] is None  # nulls kept


def test_a_short_experiment_has_no_testable_fit_and_every_entry_is_still_listed(rig):
    assert rig.run() == 0
    summary = rig.summary()
    assert len(summary["voltage_models"]) == 2 * 2 * (1 + 1)
    assert not any(m["testable"] for m in summary["voltage_models"])
    assert [(m["model"], m["window"], m["scope"]) for m in summary["voltage_models"]] == [
        (model, window, scope)
        for model in ("absorber", "hydrolyzer")
        for window in ("steady", "whole_run")
        for scope in ("EXP_001", "pooled")
    ]
    assert len(summary["voltage_evidence"]) == 8
    assert {e["status"] for e in summary["voltage_evidence"]} == {"not_testable"}
    assert summary["comparisons"] == []  # one experiment, no pair


def test_the_airflow_check_is_null_unless_its_experiment_is_in_the_run(rig):
    assert rig.run() == 0
    assert rig.summary()["airflow_check"] is None
    assert not any(kind == "raw" for kind, *_ in rig.gateway.calls)


def test_the_airflow_check_lists_the_six_signals_of_the_airflow_experiment(tmp_path):
    rig = Rig(tmp_path, experiment_id="EXP_004")
    assert rig.run() == 0
    summary = rig.summary()
    jsonschema.validate(summary, SCHEMA)
    check = summary["airflow_check"]
    assert check["experiment_id"] == "EXP_004"
    assert check["boundary"] == "2026-03-02T09:00:00Z"
    assert [(s["signal"], s["source"]) for s in check["signals"]] == [
        ("air_flow", "raw"),
        ("fan_speed", "accepted"),
        ("pressure_drop", "accepted"),
        ("co2_in_ppm", "accepted"),
        ("co2_out_ppm", "accepted"),
        ("capture_efficiency", "metrics_series"),
    ]
    # the experiment lies after the boundary: everything is on the after side
    for signal in check["signals"]:
        assert signal["before_points"] == 0 and signal["before_median"] is None
        assert signal["after_points"] > 0 and signal["relative_change"] is None
    assert check["signals"][0]["after_points"] == DURATION_S
    assert [c for c in rig.gateway.calls if c[0] == "raw"][0][1] == "EXP_004"


def test_every_read_is_bounded_to_the_window_of_one_experiment(rig):
    assert rig.run() == 0
    window = (START, START + timedelta(seconds=DURATION_S))
    assert rig.gateway.calls
    assert {(start, end) for _, _, start, end in rig.gateway.calls} == {window}
    assert {experiment for _, experiment, _, _ in rig.gateway.calls} == {"EXP_001"}


def test_outputs_never_hold_the_credentials(rig):
    assert rig.run() == 0
    for name in ("comparison_summary.json", "comparison_report.md"):
        text = (rig.report_dir / name).read_text(encoding="utf-8")
        assert SECRET not in text
        assert "SECRET-PASSWORD-VALUE" not in text
        assert "influx.invalid" not in text


def test_the_report_is_the_rendering_of_the_written_summary_and_nothing_time_varying(rig):
    assert rig.run() == 0
    summary = rig.summary()
    report = (rig.report_dir / "comparison_report.md").read_text(encoding="utf-8")
    assert report == render_report(summary)
    assert "timing" not in report and "queries" not in report
    for heading in (
        "## EXP_001",
        "### Phases",
        "### Steady-state KPIs",
        "## Voltage models",
        "## Evidence for each term",
        "## Comparability of the experiment pairs",
        "## Pressure drop against air flow",
        "## Air-flow check",
        "## Parameters",
    ):
        assert heading in report, heading
    assert "\r" not in report


def test_a_rerun_gives_the_same_summary_except_timing_and_the_same_report(rig):
    assert rig.run() == 0
    first = rig.summary()
    first_report = (rig.report_dir / "comparison_report.md").read_text(encoding="utf-8")
    assert rig.run() == 0
    second = rig.summary()
    assert {k: v for k, v in first.items() if k != "timing"} == {
        k: v for k, v in second.items() if k != "timing"
    }
    assert first_report == (rig.report_dir / "comparison_report.md").read_text(encoding="utf-8")


def test_the_parameters_are_the_policy_table_exactly(rig):
    assert rig.run() == 0
    assert rig.summary()["parameters"] == compare.POLICY


def test_floats_are_rounded_to_nine_significant_digits_and_lists_are_kept():
    assert round_floats({"a": 1 / 3, "b": [2.0, 1e-12 / 3], "c": True, "d": None, "e": 7}) == {
        "a": 0.333333333,
        "b": [2.0, 3.33333333e-13],
        "c": True,
        "d": None,
        "e": 7,
    }


# ------------------------------------------------------------------------------------- exit 2


def test_database_missing_is_refused_and_the_gateway_is_never_opened(rig, capsys):
    rig.databases = ["dac_raw", "dac_rollup"]
    assert rig.run(database="dac_missing") == 2
    assert rig.factory_calls == 0
    rig.assert_nothing_written()
    err = capsys.readouterr().err
    assert "database_missing" in err and "never creates" in err


def test_a_database_that_vanishes_before_the_first_read_is_refused(rig, capsys):
    rig.gateway.database_missing = True
    assert rig.run() == 2
    rig.assert_nothing_written()
    assert "database_missing" in capsys.readouterr().err
    assert rig.gateway.closed and rig.gateway.calls == []


def test_a_policy_version_without_cleaned_rows_is_refused(rig, capsys):
    rig.gateway.policy_rows = False
    assert rig.run(policy_version="m3-none") == 2
    rig.assert_nothing_written()
    assert "no_cleaned_readings" in capsys.readouterr().err
    assert rig.gateway.closed and rig.gateway.calls == []


def test_a_database_without_the_processed_table_is_refused(rig):
    rig.gateway.table_names = set()
    assert rig.run() == 2
    rig.assert_nothing_written()


def test_a_metrics_version_without_series_rows_is_refused(rig, capsys):
    rig.gateway.metrics_rows = False
    assert rig.run(metrics_version="m4-none") == 2
    rig.assert_nothing_written()
    assert "no_metrics_rows" in capsys.readouterr().err
    assert rig.gateway.calls == []


def test_an_unreadable_experiments_file_is_refused(rig):
    assert rig.run(experiments_path=rig.tmp_path / "nope.json") == 2
    rig.assert_nothing_written()
    assert rig.factory_calls == 0


def test_a_malformed_experiments_file_is_refused(rig):
    broken = rig.tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert rig.run(experiments_path=broken) == 2
    rig.assert_nothing_written()


def test_a_schema_without_migration_0003_is_refused(rig, capsys):
    rig.pg.check_result = "missing table(s) experiment_metrics: migration 0003 is not applied"
    assert rig.run(pg_schema="no_0003") == 2
    rig.assert_nothing_written()
    assert "postgres_not_migrated" in capsys.readouterr().err
    assert rig.pg.conn_closed and rig.gateway.calls == []


def test_an_experiment_missing_from_postgres_is_refused(rig, capsys):
    rig.pg.absent = True
    assert rig.run() == 2
    rig.assert_nothing_written()
    err = capsys.readouterr().err
    assert "experiment_missing_in_postgres" in err and "EXP_001" in err
    assert rig.gateway.calls == []


def test_an_experiment_without_metrics_rows_for_the_version_is_refused(rig, capsys):
    rig.pg.no_metrics = True
    assert rig.run() == 2
    rig.assert_nothing_written()
    err = capsys.readouterr().err
    assert "experiment_metrics_missing" in err and "EXP_001" in err
    assert rig.gateway.calls == []


@pytest.mark.parametrize("column", ["start_time", "end_time"])
def test_a_postgres_window_that_differs_from_the_file_is_refused(rig, capsys, column):
    setattr(rig.pg, column, getattr(rig.pg, column) + timedelta(seconds=1))
    assert rig.run() == 2
    rig.assert_nothing_written()
    err = capsys.readouterr().err
    assert "window_mismatch" in err and "EXP_001" in err and column in err
    assert rig.gateway.calls == []


def test_postgres_not_reachable_is_refused(rig):
    rig.pg.connect_error = psycopg.OperationalError("connection refused")
    assert rig.run() == 2
    rig.assert_nothing_written()


def test_influx_not_configured_is_refused(rig):
    rig.env = {k: v for k, v in ENV.items() if not k.startswith("INFLUX_")}
    assert rig.run() == 2
    rig.assert_nothing_written()


def test_postgres_not_configured_is_refused(rig):
    rig.env = {k: v for k, v in ENV.items() if not k.startswith("POSTGRES_")}
    assert rig.run() == 2
    rig.assert_nothing_written()


def test_influx_not_reachable_is_refused(rig):
    rig.database_error = DatabaseCheckFailed("unreachable", "no route to host")
    assert rig.run() == 2
    rig.assert_nothing_written()
    assert rig.factory_calls == 0


# ------------------------------------------------------------------------------------- exit 3


def test_a_failed_query_exits_3_and_writes_nothing(rig, capsys):
    rig.gateway.fail_read = True
    assert rig.run() == 3
    rig.assert_nothing_written()
    assert "failed" in capsys.readouterr().err
    assert rig.gateway.closed and rig.pg.conn_closed


def test_a_failed_postgres_read_exits_3_and_writes_nothing(rig):
    rig.pg.read_error = psycopg.errors.OperationalError("server closed the connection")
    assert rig.run() == 3
    rig.assert_nothing_written()
    assert rig.pg.conn_closed


def test_a_failed_query_leaves_an_existing_report_directory_empty(rig):
    rig.report_dir.mkdir()
    rig.gateway.fail_read = True
    assert rig.run() == 3
    assert list(rig.report_dir.iterdir()) == []


# ------------------------------------------------------------------------------------ exit 70


def test_an_internal_error_exits_70(monkeypatch, capsys, tmp_path):
    def broken(config):
        raise RuntimeError("a bug")

    monkeypatch.setattr(compare_cli, "run", broken)
    assert compare_cli.main(["--report-dir", str(tmp_path / "r")]) == 70
    assert "a bug" in capsys.readouterr().err


# ------------------------------------------------------------------------------- the command line


def test_the_command_line_defaults_and_options():
    config = compare_cli.parse_args([])
    assert config.database == "dac_raw"
    assert config.policy_version == "m3-v1"
    assert config.metrics_version == "m4-v1"
    assert config.pg_schema == "public"
    assert config.experiments_path == compare_run.DEFAULT_EXPERIMENTS
    assert config.report_dir == compare_run.DEFAULT_REPORT_DIR
    custom = compare_cli.parse_args(
        [
            "--database",
            "x",
            "--experiments",
            "e.json",
            "--report-dir",
            "r",
            "--policy-version",
            "p",
            "--metrics-version",
            "m",
            "--pg-schema",
            "s",
        ]
    )
    assert (custom.database, custom.policy_version, custom.metrics_version, custom.pg_schema) == (
        "x",
        "p",
        "m",
        "s",
    )
    assert custom.experiments_path == Path("e.json") and custom.report_dir == Path("r")
