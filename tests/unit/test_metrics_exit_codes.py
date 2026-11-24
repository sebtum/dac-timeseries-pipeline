"""Unit tests for `python -m scripts.metrics` with a fake gateway and a fake Postgres (M4: S4.19,
S4.20 and the refusal paths of S4.18).

No server here: `FakeGateway` answers the reads from small hand-made series and keeps what the run
writes, the Postgres functions are injected through `Deps`. So every exit code (0, 1, 2, 3, 4, 70)
can be reached and the "writes nothing" claims can be checked by looking at what was recorded.
The live run on the fixture is `tests/e2e/test_metrics_cli.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import psycopg
import pytest

from pipeline import metrics, metrics_run
from pipeline.cleaning_influx import PROCESSED_TABLE
from pipeline.ingest_influx import DatabaseCheckFailed, WriteFailed
from pipeline.metrics_run import Config, Deps, render_report, round_floats, run
from pipeline.metrics_store import METRICS_TABLE, QUALITY_TABLE
from pipeline.profiling_sql import QueryFailed
from scripts import metrics as metrics_cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "metrics_summary.schema.json").read_text(encoding="utf-8")
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


def good_inputs() -> dict[str, list[tuple[int, float]]]:
    """120 s: 1 Hz electrics (100 V, 150 A, 15 kW), 0.5 Hz CO2 400 -> 100 ppm, 1 Hz air flow."""
    seconds = range(DURATION_S)
    return {
        "voltage": [(at(k), 100.0) for k in seconds],
        "current": [(at(k), 150.0) for k in seconds],
        "power": [(at(k), 15000.0) for k in seconds],
        "co2_in_ppm": [(at(k), 400.0) for k in range(0, DURATION_S, 2)],
        "co2_out_ppm": [(at(k), 100.0) for k in range(0, DURATION_S, 2)],
        "air_flow": [(at(k), 1200.0) for k in seconds],
        "ambient_temperature": [(at(0), 15.0)],
        "ambient_pressure": [(at(0), 1013.25)],
    }


def high_efficiency_inputs() -> dict[str, list[tuple[int, float]]]:
    """Capture efficiency mean above 1 while captured CO2 stays below the inlet CO2.

    From +40 s co2_out is -100 ppm (efficiency 1.25) where there is no air flow, so those
    instants are in the efficiency series but not in the capture series: 20 instants at 0.75 and
    40 at 1.25 give a mean of 1.083, and the CO2 totals (over the first 40 s only) stay ordered.
    """
    inputs = good_inputs()
    inputs["co2_out_ppm"] = [(at(k), 100.0 if k < 40 else -100.0) for k in range(0, DURATION_S, 2)]
    inputs["air_flow"] = [(at(k), 1200.0) for k in range(40)]
    return inputs


def quality_counts() -> list[dict]:
    """Counts of the accepted readings above, every verdict accepted, every quality GOOD."""
    sizes = {
        ("hydrolyzer", "voltage"): DURATION_S,
        ("hydrolyzer", "current"): DURATION_S,
        ("hydrolyzer", "power"): DURATION_S,
        ("absorber", "co2_in_ppm"): DURATION_S // 2,
        ("absorber", "co2_out_ppm"): DURATION_S // 2,
        ("absorber", "air_flow"): DURATION_S,
        ("ambient", "ambient_temperature"): 1,
        ("ambient", "ambient_pressure"): 1,
    }
    return [
        {"source": s, "signal": g, "quality": "GOOD", "verdict": "accepted", "count": n}
        for (s, g), n in sizes.items()
    ]


class FakeGateway:
    """Answers the reads from `inputs` and records every write."""

    def __init__(self, inputs: dict[str, list[tuple[int, float]]]) -> None:
        self.inputs = inputs
        self.queries = 0
        self.closed = False
        self.written: dict[tuple[str, str], list[tuple[int, float]]] = {}
        self.policy_rows = True
        self.table_names = {PROCESSED_TABLE}
        self.fail_read = False
        self.fail_write = False
        self.count_offset = 0  # added to every read-back count
        self.input_totals = {"readings_numeric": 10}
        self.input_drift = False

    def tables(self) -> set[str]:
        return self.table_names

    def has_policy_rows(self, policy_version: str) -> bool:
        self.queries += 1
        return self.policy_rows

    def accepted_series(self, experiment_id, signal, start, end, policy_version):
        self.queries += 1
        if self.fail_read:
            raise QueryFailed(f"accepted:{experiment_id}/{signal}", RuntimeError("boom"))
        return list(self.inputs.get(signal, []))

    def quality_counts(self, experiment_id, start, end, policy_version):
        self.queries += 1
        return quality_counts()

    def input_counts(self, start, end):
        self.queries += 1
        counts = dict(self.input_totals)
        if self.input_drift and self.written:
            counts["readings_numeric"] += 1  # an input table moved during the run
        return counts

    def write_series(self, experiment_id, metric, metrics_version, policy_version, series):
        if self.fail_write:
            raise WriteFailed(3, RuntimeError("write boom"))
        self.written[(experiment_id, metric)] = list(series)
        return len(series)

    def count_series(self, experiment_id, metric, metrics_version, start, end):
        self.queries += 1
        return len(self.written.get((experiment_id, metric), [])) + self.count_offset

    def close(self) -> None:
        self.closed = True


class FakePostgres:
    """Records `write_postgres` and answers `count_rows` from what was written."""

    def __init__(self) -> None:
        self.connected: list[str] = []
        self.conn_closed = False
        self.check_result: str | None = None
        self.absent: list[str] = []
        self.connect_error: Exception | None = None
        self.write_error: Exception | None = None
        self.writes: list[tuple[list[dict], list[dict]]] = []
        self.row_offset = 0

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

    def missing_experiments(self, conn, ids):
        return [i for i in ids if i in self.absent]

    def write_postgres(self, conn, metric_rows, quality_rows):
        if self.write_error is not None:
            raise self.write_error
        self.writes.append((metric_rows, quality_rows))

    def count_rows(self, conn, table, metrics_version):
        counts: dict[str, int] = {}
        if self.writes:  # an upsert: the latest call defines the rows
            metric_rows, quality_rows = self.writes[-1]
            for row in metric_rows if table == METRICS_TABLE else quality_rows:
                counts[row["experiment_id"]] = counts.get(row["experiment_id"], 0) + 1
        return {k: v + self.row_offset for k, v in counts.items()}


class Rig:
    """One run: the fakes, the config and the dependency bundle."""

    def __init__(self, tmp_path: Path, inputs=None) -> None:
        self.tmp_path = tmp_path
        self.report_dir = tmp_path / "report"
        self.experiments = tmp_path / "experiments.json"
        self.experiments.write_text(
            json.dumps(
                [
                    {
                        "experiment_id": "EXP_001",
                        "start_time": "2026-05-04T08:00:00Z",
                        "end_time": "2026-05-04T08:02:00Z",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.gateway = FakeGateway(inputs if inputs is not None else good_inputs())
        self.pg = FakePostgres()
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
            "pg_schema": "public",
        }
        return Config(**{**base, **changes})

    def deps(self) -> Deps:
        return Deps(
            list_databases=self.list_databases,
            gateway_factory=self.gateway_factory,
            pg_connect=self.pg.pg_connect,
            pg_check=self.pg.pg_check,
            missing_experiments=self.pg.missing_experiments,
            write_postgres=self.pg.write_postgres,
            count_rows=self.pg.count_rows,
            env=self.env,
        )

    def run(self, **changes) -> int:
        return run(self.config(**changes), self.deps())

    def summary(self) -> dict:
        return json.loads((self.report_dir / "metrics_summary.json").read_text(encoding="utf-8"))

    def assert_nothing_written(self) -> None:
        assert not self.report_dir.exists() or list(self.report_dir.iterdir()) == []
        assert self.gateway.written == {}
        assert self.pg.writes == []


@pytest.fixture
def rig(tmp_path) -> Rig:
    return Rig(tmp_path)


# ------------------------------------------------------------------------------- exit 0 and 1


def test_a_clean_run_exits_0_and_writes_everything(rig, capsys):
    assert rig.run() == 0
    summary = rig.summary()
    jsonschema.validate(summary, SCHEMA)
    assert summary["plausibility_failed"] == 0
    assert summary["reconciliation"] == {
        "balanced": True,
        "influx_series_checked": 4,
        "postgres_rows_checked": 38,
        "mismatches": [],
        "inputs_unchanged": True,
    }
    entry = summary["experiments"][0]
    assert entry["series_written"] == {
        "power_computed": 120,
        "power_residual": 120,
        "capture_efficiency": 60,
        "capture_rate": 60,
    }
    assert set(rig.gateway.written) == {
        ("EXP_001", name)
        for name in (
            "power_computed",
            "power_residual",
            "capture_efficiency",
            "capture_rate",
        )  # fmt: skip
    }
    metric_rows, quality_rows = rig.pg.writes[0]
    assert (len(metric_rows), len(quality_rows)) == (13, 25)
    assert rig.gateway.closed and rig.pg.conn_closed
    assert summary["timing"]["points_written"] == 120 + 120 + 60 + 60
    out = capsys.readouterr().out
    assert "balanced" in out and SECRET not in out


def test_outputs_never_hold_the_credentials(rig):
    assert rig.run() == 0
    for name in ("metrics_summary.json", "metrics_report.md"):
        text = (rig.report_dir / name).read_text(encoding="utf-8")
        assert SECRET not in text
        assert "SECRET-PASSWORD-VALUE" not in text
        assert "influx.invalid" not in text


def test_s4_20_a_failed_plausibility_check_exits_1_and_still_writes_everything(rig):
    rig.gateway.inputs = high_efficiency_inputs()
    assert rig.run() == 1
    summary = rig.summary()
    jsonschema.validate(summary, SCHEMA)
    assert summary["plausibility_failed"] == 1
    checks = {p["check"]: p for p in summary["experiments"][0]["plausibility"]}
    assert checks["efficiency_in_unit_interval"]["passed"] is False
    assert checks["efficiency_in_unit_interval"]["value"] > 1
    assert [name for name, p in checks.items() if p["passed"] is False] == [
        "efficiency_in_unit_interval"
    ]
    assert (rig.report_dir / "metrics_report.md").is_file()
    assert rig.gateway.written and rig.pg.writes
    assert summary["reconciliation"]["balanced"] is True


# ------------------------------------------------------------------------------- exit 2


def test_s4_18_database_missing_is_refused_and_the_gateway_is_never_opened(rig, capsys):
    rig.databases = ["dac_raw", "dac_rollup"]
    assert rig.run(database="dac_missing") == 2
    assert rig.factory_calls == 0
    rig.assert_nothing_written()
    err = capsys.readouterr().err
    assert "database_missing" in err and "never creates" in err


def test_s4_18_a_policy_version_without_cleaned_rows_is_refused(rig):
    rig.gateway.policy_rows = False
    assert rig.run(policy_version="m3-none") == 2
    rig.assert_nothing_written()
    assert rig.gateway.closed


def test_s4_18_a_database_without_the_processed_table_is_refused(rig):
    rig.gateway.table_names = set()
    assert rig.run() == 2
    rig.assert_nothing_written()


def test_s4_18_an_unreadable_experiments_file_is_refused(rig):
    assert rig.run(experiments_path=rig.tmp_path / "nope.json") == 2
    rig.assert_nothing_written()
    assert rig.factory_calls == 0


def test_s4_18_a_malformed_experiments_file_is_refused(rig):
    broken = rig.tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert rig.run(experiments_path=broken) == 2
    rig.assert_nothing_written()


def test_s4_18_a_schema_without_migration_0003_is_refused(rig, capsys):
    rig.pg.check_result = "missing table(s) experiment_metrics: migration 0003 is not applied"
    assert rig.run(pg_schema="no_0003") == 2
    rig.assert_nothing_written()
    assert "postgres_not_migrated" in capsys.readouterr().err
    assert rig.pg.conn_closed


def test_s4_18_an_experiment_missing_from_postgres_is_refused(rig, capsys):
    rig.pg.absent = ["EXP_001"]
    assert rig.run() == 2
    rig.assert_nothing_written()
    assert "EXP_001" in capsys.readouterr().err


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


# ------------------------------------------------------------------------------- exit 3


def test_s4_19_a_failed_query_exits_3_and_writes_nothing(rig, capsys):
    rig.gateway.fail_read = True
    assert rig.run() == 3
    rig.assert_nothing_written()
    assert "failed" in capsys.readouterr().err
    assert rig.gateway.closed and rig.pg.conn_closed


def test_s4_19_a_failed_influx_write_exits_3_and_writes_no_outputs(rig):
    rig.gateway.fail_write = True
    assert rig.run() == 3
    assert not rig.report_dir.exists() or list(rig.report_dir.iterdir()) == []
    assert rig.pg.writes == []  # Postgres is only written after every series is in


def test_s4_19_a_failed_postgres_write_exits_3_and_writes_no_outputs(rig):
    rig.pg.write_error = psycopg.errors.OperationalError("server closed the connection")
    assert rig.run() == 3
    assert not rig.report_dir.exists() or list(rig.report_dir.iterdir()) == []
    assert rig.pg.conn_closed


# ------------------------------------------------------------------------------- exit 4


def test_s4_19_an_influx_read_back_mismatch_exits_4_writes_outputs_and_lists_it(rig):
    rig.gateway.count_offset = -1
    assert rig.run() == 4
    summary = rig.summary()
    jsonschema.validate(summary, SCHEMA)
    recon = summary["reconciliation"]
    assert recon["balanced"] is False
    assert recon["influx_series_checked"] == 4
    assert recon["mismatches"] == [
        {
            "store": "influx",
            "experiment_id": "EXP_001",
            "name": name,
            "written": n,
            "read_back": n - 1,
        }  # fmt: skip
        for name, n in (
            ("power_computed", 120),
            ("power_residual", 120),
            ("capture_efficiency", 60),
            ("capture_rate", 60),
        )
    ]
    assert "mismatch in influx for EXP_001, power_computed: written 120, read back 119" in (
        rig.report_dir / "metrics_report.md"
    ).read_text(encoding="utf-8")


def test_s4_19_a_postgres_read_back_mismatch_exits_4_and_lists_it(rig):
    rig.pg.row_offset = -1
    assert rig.run() == 4
    mismatches = rig.summary()["reconciliation"]["mismatches"]
    assert mismatches == [
        {
            "store": "postgres",
            "experiment_id": "EXP_001",
            "name": METRICS_TABLE,
            "written": 13,
            "read_back": 12,
        },  # fmt: skip
        {
            "store": "postgres",
            "experiment_id": "EXP_001",
            "name": QUALITY_TABLE,
            "written": 25,
            "read_back": 24,
        },  # fmt: skip
    ]


def test_an_input_table_that_moved_exits_4_and_says_so(rig):
    rig.gateway.input_drift = True
    assert rig.run() == 4
    recon = rig.summary()["reconciliation"]
    assert recon["inputs_unchanged"] is False
    assert recon["balanced"] is True


def test_exit_4_takes_precedence_over_exit_1(rig):
    rig.gateway.inputs = high_efficiency_inputs()
    rig.gateway.count_offset = 1
    assert rig.run() == 4
    assert rig.summary()["plausibility_failed"] == 1


# ------------------------------------------------------------------------------- exit 70


def test_an_internal_error_exits_70(monkeypatch, capsys, tmp_path):
    def broken(config):
        raise RuntimeError("a bug")

    monkeypatch.setattr(metrics_cli, "run", broken)
    assert metrics_cli.main(["--report-dir", str(tmp_path / "r")]) == 70
    assert "a bug" in capsys.readouterr().err


# ------------------------------------------------------------------------------- the files


def test_the_command_line_defaults_and_options():
    config = metrics_cli.parse_args([])
    assert config.database == "dac_raw"
    assert config.policy_version == "m3-v1"
    assert config.pg_schema == "public"
    assert config.report_dir == metrics_run.DEFAULT_REPORT_DIR
    custom = metrics_cli.parse_args(
        ["--database", "x", "--policy-version", "v", "--pg-schema", "s", "--report-dir", "r"]
    )
    assert (custom.database, custom.policy_version, custom.pg_schema) == ("x", "v", "s")


def test_the_report_is_the_rendering_of_the_written_summary_and_nothing_time_varying(rig):
    assert rig.run() == 0
    summary = rig.summary()
    report = (rig.report_dir / "metrics_report.md").read_text(encoding="utf-8")
    assert report == render_report(summary)
    assert "timing" not in report and "seconds" not in report.split("## EXP_001")[0]
    assert "## EXP_001" in report and "energy_kwh" in report


def test_a_rerun_gives_the_same_summary_except_timing(rig):
    assert rig.run() == 0
    first = rig.summary()
    assert rig.run() == 0
    second = rig.summary()
    assert {k: v for k, v in first.items() if k != "timing"} == {
        k: v for k, v in second.items() if k != "timing"
    }


def test_the_parameters_are_the_policy_table_exactly(rig):
    assert rig.run() == 0
    assert rig.summary()["parameters"] == metrics.POLICY


def test_floats_are_rounded_to_nine_significant_digits_and_lists_are_kept():
    assert round_floats({"a": 1 / 3, "b": [2.0, 1e-12 / 3], "c": True, "d": None, "e": 7}) == {
        "a": 0.333333333,
        "b": [2.0, 3.33333333e-13],
        "c": True,
        "d": None,
        "e": 7,
    }
