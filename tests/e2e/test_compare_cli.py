"""End-to-end comparison: the real CLIs against a live InfluxDB and Postgres (M5: S5.13 to S5.19).

The fixture `tests/fixtures/compare/readings.csv` is built by `make_fixture.py` (three experiments
of 1,200 s). Every expected number below is a literal from the hand computation in
`tests/fixtures/compare/README.md`, derived from the construction, not read from the pipeline.
The last block recomputes the phases, the steady KPIs and the hydrolyzer coefficients from plain
`SELECT` pulls with no import from `pipeline/`, and compares them with the summary.

Throwaway state only: one InfluxDB database and one Postgres schema per module (plus short-lived
schemas for the refusals), all dropped in a `finally`. Core allows five databases and four exist
(`_internal`, `dac_pinned`, `dac_raw`, `dac_rollup`), so a test holds at most one extra one, and no
test ever writes to the three project databases.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import uuid
from calendar import timegm
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import psycopg
import pytest

import scripts.init_influx as init_influx
import scripts.migrate as migrate
from pipeline.compare_run import render_report
from pipeline.metadata_loader import load_experiments
from pipeline.pg_migrate import run_migrations
from tests.e2e.helpers import REPO_ROOT, database_names, query, run_ingest, tables

pytestmark = [pytest.mark.influx, pytest.mark.postgres]

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "compare"
EXPERIMENTS = FIXTURES / "experiments.json"
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "comparison_summary.schema.json").read_text(encoding="utf-8")
)
IDS = ("EXP_001", "EXP_002", "EXP_003")
DURATION = 1200
PROTECTED_DATABASES = ["_internal", "dac_pinned", "dac_raw", "dac_rollup"]

# ------------------------------------------------------------------ the hand computation

EXPECTED_PHASES = [
    (0, "STARTUP", 0, 120, 60, 120),
    (1, "STEADY_STATE", 120, 600, 180, 600),
    (2, "LOAD_CHANGE", 600, 660, None, None),
    (3, "STEADY_STATE", 660, 1140, 720, 1140),
    (4, "SHUTDOWN", 1140, 1200, None, None),
]
EXPECTED_STEADY_INSTANTS = {"EXP_001": 839, "EXP_002": 840, "EXP_003": 840, "pooled": 2519}
EXPECTED_WHOLE_INSTANTS = {"EXP_001": 1199, "EXP_002": 1200, "EXP_003": 1200, "pooled": 3599}
# experiment -> (voltage_mean_v, mean_power_kw), 9 significant digits, from the README.
EXPECTED_KPIS = {
    "EXP_001": (80.7271068, 12.1090305),
    "EXP_002": (95.7270052, 19.1454324),
    "EXP_003": (80.7270052, 12.1090761),
}
EXPECTED_COVERAGE = 838 / 840  # covered seconds / steady seconds, every experiment


# ------------------------------------------------------------------ running the CLIs


def run_cli(module: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", module, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def run_compare(
    database: str,
    report_dir: Path,
    schema: str,
    *extra: str,
    experiments: Path = EXPERIMENTS,
) -> subprocess.CompletedProcess:
    return run_cli(
        "scripts.compare",
        "--database",
        database,
        "--experiments",
        str(experiments),
        "--pg-schema",
        schema,
        "--report-dir",
        str(report_dir),
        *extra,
    )


def fixture_files() -> dict:
    return {
        "csv": FIXTURES / "readings.csv",
        "sha256": FIXTURES / "readings.sha256",
        "experiments": EXPERIMENTS,
    }


# ------------------------------------------------------------------ throwaway Postgres schemas


@contextmanager
def throwaway_schema(postgres_conn, *, migrate_up: bool = True, load: bool = True):
    """A fresh Postgres schema, migrated and loaded with the fixture experiments, dropped after."""
    schema = f"m5_e2e_{uuid.uuid4().hex[:10]}"
    with postgres_conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    postgres_conn.commit()
    try:
        kwargs = {
            **migrate.connect_kwargs(migrate.load_env()),
            "options": f"-c search_path={schema}",
        }
        if migrate_up:
            run_migrations(kwargs)
        if migrate_up and load:
            load_experiments(kwargs, EXPERIMENTS)
        yield schema
    finally:
        postgres_conn.rollback()
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    psycopg.sql.Identifier(schema)
                )
            )
        postgres_conn.commit()


def schema_exists(postgres_conn, schema: str) -> bool:
    try:
        with postgres_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,))
            return cur.fetchone() is not None
    finally:
        postgres_conn.rollback()


def pg_dump(postgres_conn, schema: str) -> dict[str, list[tuple]]:
    """Every row of every table of the schema, sorted (a read, then the transaction ends)."""
    try:
        with postgres_conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
                (schema,),
            )
            names = [row[0] for row in cur.fetchall()]
            out = {}
            for name in names:
                cur.execute(
                    psycopg.sql.SQL("SELECT * FROM {}.{}").format(
                        psycopg.sql.Identifier(schema), psycopg.sql.Identifier(name)
                    )
                )
                out[name] = sorted(cur.fetchall(), key=repr)
            return out
    finally:
        postgres_conn.rollback()


@pytest.fixture(scope="module")
def pg_schema(postgres_conn):
    with throwaway_schema(postgres_conn) as schema:
        yield schema


# ------------------------------------------------------------------ dumps


def influx_dump(database: str) -> dict[str, list[dict]]:
    """Every row of every table of the database, sorted."""
    return {
        table: sorted(query(database, f"SELECT * FROM {table}"), key=repr)  # noqa: S608
        for table in tables(database)
    }


def without_timing(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k != "timing"}


# ------------------------------------------------------------------ the module's runs


@pytest.fixture(scope="module")
def ran(module_db, pg_schema, postgres_conn, tmp_path_factory):
    ingested = run_ingest(fixture_files(), module_db, tmp_path_factory.mktemp("ingest"))
    assert ingested.returncode == 0, ingested.stderr + ingested.stdout
    cleaned = run_cli(
        "scripts.clean",
        "--database",
        module_db,
        "--experiments",
        str(EXPERIMENTS),
        "--report-dir",
        str(tmp_path_factory.mktemp("clean")),
    )
    assert cleaned.returncode == 0, cleaned.stderr + cleaned.stdout
    metrics = run_cli(
        "scripts.metrics",
        "--database",
        module_db,
        "--experiments",
        str(EXPERIMENTS),
        "--pg-schema",
        pg_schema,
        "--report-dir",
        str(tmp_path_factory.mktemp("metrics")),
    )
    assert metrics.returncode in (0, 1), metrics.stderr + metrics.stdout

    influx_before = influx_dump(module_db)
    pg_before = pg_dump(postgres_conn, pg_schema)
    databases_before = database_names()

    first_dir = tmp_path_factory.mktemp("first")
    first = run_compare(module_db, first_dir, pg_schema)
    assert first.returncode == 0, first.stderr + first.stdout
    influx_after = influx_dump(module_db)
    pg_after = pg_dump(postgres_conn, pg_schema)
    databases_after = database_names()

    second_dir = tmp_path_factory.mktemp("second")
    second = run_compare(module_db, second_dir, pg_schema)
    assert second.returncode == 0, second.stderr + second.stdout
    return {
        "db": module_db,
        "schema": pg_schema,
        "dir": first_dir,
        "stdout": first.stdout,
        "summary": json.loads((first_dir / "comparison_summary.json").read_text("utf-8")),
        "second_summary": json.loads((second_dir / "comparison_summary.json").read_text("utf-8")),
        "second_dir": second_dir,
        "influx_before": influx_before,
        "influx_after": influx_after,
        "influx_after_second": influx_dump(module_db),
        "pg_before": pg_before,
        "pg_after": pg_after,
        "pg_after_second": pg_dump(postgres_conn, pg_schema),
        "databases_before": databases_before,
        "databases_after": databases_after,
        "databases_after_second": database_names(),
    }


def experiment(ran, experiment_id: str) -> dict:
    return next(e for e in ran["summary"]["experiments"] if e["experiment_id"] == experiment_id)


def model_entry(ran, model: str, window: str, scope: str) -> dict:
    (entry,) = (
        m
        for m in ran["summary"]["voltage_models"]
        if (m["model"], m["window"], m["scope"]) == (model, window, scope)
    )
    return entry


def term(entry: dict, name: str) -> dict:
    return next(t for t in entry["terms"] if t["name"] == name)


def sig9(value: float) -> float:
    return float(f"{value:.9g}")


# ------------------------------------------------------------------ the fixture itself


def test_the_fixture_bytes_match_the_committed_checksum():
    data = (FIXTURES / "readings.csv").read_bytes()
    assert b"\r" not in data
    digest, name = (FIXTURES / "readings.sha256").read_text(encoding="utf-8").split()
    assert name == "readings.csv"
    assert hashlib.sha256(data).hexdigest() == digest


# ------------------------------------------------------------------ S5.13: phases


def test_s5_13_every_experiment_lists_five_phases_with_the_same_windows(ran):
    assert [e["experiment_id"] for e in ran["summary"]["experiments"]] == list(IDS)
    for experiment_id in IDS:
        entry = experiment(ran, experiment_id)
        got = [
            (
                p["index"],
                p["state"],
                p["start_s"],
                p["end_s"],
                p["window_start_s"],
                p["window_end_s"],
            )
            for p in entry["phases"]
        ]
        assert got == EXPECTED_PHASES, experiment_id
        assert entry["steady_seconds"] == 840, experiment_id
        assert entry["duration_s"] == DURATION


def test_s5_13_the_experiment_entries_carry_the_postgres_metadata_and_the_13_metrics(ran):
    meta = {
        "EXP_001": (150.0, 1200.0, 8.0, "Op A", "SB-A", None),
        "EXP_002": (200.0, 1200.0, 8.0, "Op A", "SB-A", None),
        "EXP_003": (150.0, 2400.0, 8.0, "Op B", "SB-B", None),
    }
    for experiment_id, values in meta.items():
        entry = experiment(ran, experiment_id)
        assert tuple(entry["metadata"].values()) == values
        assert len(entry["whole_run_metrics"]) == 13
        assert entry["whole_run_metrics"]["energy_kwh"]["unit"] == "kWh"
    assert experiment(ran, "EXP_001")["start"] == "2026-05-04T08:00:00Z"
    assert experiment(ran, "EXP_001")["end"] == "2026-05-04T08:20:00Z"


# ------------------------------------------------------------------ S5.14: the planted effects


def test_s5_14_the_hydrolyzer_steady_fits_have_the_expected_instants(ran):
    for scope, instants in EXPECTED_STEADY_INSTANTS.items():
        entry = model_entry(ran, "hydrolyzer", "steady", scope)
        assert entry["testable"] is True
        assert entry["instants"] == instants, scope
        assert entry["resamples_used"] == 1000 and entry["resamples_singular"] == 0
    for scope, instants in EXPECTED_WHOLE_INSTANTS.items():
        assert model_entry(ran, "hydrolyzer", "whole_run", scope)["instants"] == instants


def test_s5_14_flow_and_pressure_are_recovered_with_intervals_that_exclude_zero(ran):
    for window in ("steady", "whole_run"):
        for scope in (*IDS, "pooled"):
            entry = model_entry(ran, "hydrolyzer", window, scope)
            flow, pressure = term(entry, "flow"), term(entry, "pressure")
            assert flow["coefficient"] == pytest.approx(-0.2, abs=0.02), (window, scope)
            assert pressure["coefficient"] == pytest.approx(3.0, abs=0.3), (window, scope)
            assert flow["interval_high"] < 0 < pressure["interval_low"], (window, scope)
            assert flow["interval_low"] <= flow["coefficient"] <= flow["interval_high"]
            assert pressure["interval_low"] <= pressure["coefficient"] <= pressure["interval_high"]
            assert flow["unit"] == "V per L/min" and pressure["unit"] == "V per bar"
            assert entry["joint"]["separable"] is True
            assert entry["r2"] > 0.99
            assert [t["name"] for t in entry["terms"]] == [
                "current",
                "electrolyte_temperature",
                "flow",
                "pressure",
            ]


def test_s5_14_the_hydrolyzer_evidence_is_supported_negative_for_flow_positive_for_pressure(ran):
    rows = {
        (e["model"], e["window"], e["term"]): e
        for e in ran["summary"]["voltage_evidence"]
        if e["model"] == "hydrolyzer"
    }
    assert set(rows) == {
        ("hydrolyzer", window, name)
        for window in ("steady", "whole_run")
        for name in ("flow", "pressure")
    }
    for window in ("steady", "whole_run"):
        flow, pressure = (
            rows[("hydrolyzer", window, "flow")],
            rows[("hydrolyzer", window, "pressure")],
        )
        assert (flow["status"], flow["sign"]) == ("supported", "negative")
        assert (pressure["status"], pressure["sign"]) == ("supported", "positive")
        for row in (flow, pressure):
            assert row["experiments_testable"] == 3 and row["experiments_excluding_zero"] == 3
    pooled = model_entry(ran, "hydrolyzer", "steady", "pooled")
    assert (
        rows[("hydrolyzer", "steady", "flow")]["pooled_coefficient"]
        == term(pooled, "flow")["coefficient"]
    )


def test_s5_14_there_is_one_voltage_model_entry_per_model_window_and_scope(ran):
    models = ran["summary"]["voltage_models"]
    assert len(models) == 2 * 2 * (3 + 1) == 16
    assert [(m["model"], m["window"], m["scope"]) for m in models] == [
        (model, window, scope)
        for model in ("absorber", "hydrolyzer")
        for window in ("steady", "whole_run")
        for scope in (*IDS, "pooled")
    ]
    assert len(ran["summary"]["voltage_evidence"]) == 8
    assert [(e["model"], e["window"], e["term"]) for e in ran["summary"]["voltage_evidence"]] == [
        (model, window, name)
        for model, names in (
            ("absorber", ("air_flow", "pressure_drop")),
            ("hydrolyzer", ("flow", "pressure")),
        )
        for window in ("steady", "whole_run")
        for name in names
    ]


def test_the_absorber_fits_are_not_testable_on_the_fixture_by_construction(ran):
    """Current and air flow are constants at the 0.5 Hz pressure-drop instants (README)."""
    for window in ("steady", "whole_run"):
        for scope in (*IDS, "pooled"):
            entry = model_entry(ran, "absorber", window, scope)
            assert entry["testable"] is False
            assert entry["r2"] is None and entry["resamples_used"] == 0
            assert [t["name"] for t in entry["terms"]] == [
                "current",
                "electrolyte_temperature",
                "air_flow",
                "pressure_drop",
            ]
            for t in entry["terms"]:
                assert all(v is None for k, v in t.items() if k not in ("name", "unit"))
            assert entry["joint"]["r2_drop"] is None
    assert model_entry(ran, "absorber", "steady", "EXP_001")["instants"] == 419
    assert model_entry(ran, "absorber", "steady", "EXP_002")["instants"] == 420
    for e in ran["summary"]["voltage_evidence"]:
        if e["model"] == "absorber":
            assert e["status"] == "not_testable" and e["sign"] is None
            assert e["experiments_testable"] == 0 and e["pooled_coefficient"] is None


# ------------------------------------------------------------------ S5.15: KPIs


def test_s5_15_voltage_and_power_equal_the_hand_computation_to_nine_digits(ran):
    for experiment_id, (voltage, power) in EXPECTED_KPIS.items():
        kpis = experiment(ran, experiment_id)["kpis"]
        assert list(kpis) == [
            "voltage_mean_v",
            "mean_power_kw",
            "capture_rate_mean_kg_h",
            "capture_efficiency_mean",
            "sec_kwh_per_kg",
        ]
        assert kpis["voltage_mean_v"]["value"] == voltage, experiment_id
        assert kpis["mean_power_kw"]["value"] == power, experiment_id
        for name in ("voltage_mean_v", "mean_power_kw"):
            assert kpis[name]["coverage"] == pytest.approx(EXPECTED_COVERAGE, rel=1e-8)
            assert kpis[name]["status"] == "complete"
            low, high = kpis[name]["interval_low"], kpis[name]["interval_high"]
            assert low < kpis[name]["value"] < high
        assert kpis["voltage_mean_v"]["unit"] == "V" and kpis["mean_power_kw"]["unit"] == "kW"


def test_s5_15_the_voltage_difference_between_exp_002_and_exp_001_is_the_planted_15_v(ran):
    pair = next(
        c for c in ran["summary"]["comparisons"] if (c["a"], c["b"]) == ("EXP_001", "EXP_002")
    )
    voltage = next(k for k in pair["kpis"] if k["name"] == "voltage_mean_v")
    assert voltage["difference"] == pytest.approx(15.0, abs=0.1)
    assert voltage["difference"] == pytest.approx(14.99989839, abs=1e-6)  # README
    assert voltage["interval_low"] > 0
    assert voltage["excludes_zero"] is True
    assert voltage["coverage_status"] == "both_complete"
    other = next(
        c for c in ran["summary"]["comparisons"] if (c["a"], c["b"]) == ("EXP_001", "EXP_003")
    )
    same = next(k for k in other["kpis"] if k["name"] == "voltage_mean_v")
    assert same["difference"] == pytest.approx(-0.00010161, abs=1e-6)  # README
    assert same["excludes_zero"] is False


# ------------------------------------------------------------------ S5.16: comparability


def test_s5_16_the_comparability_matrix_names_the_planted_differing_factors(ran):
    pairs = {(c["a"], c["b"]): c for c in ran["summary"]["comparisons"]}
    assert list(pairs) == [("EXP_001", "EXP_002"), ("EXP_001", "EXP_003"), ("EXP_002", "EXP_003")]
    one_two = pairs[("EXP_001", "EXP_002")]
    assert one_two["conditions_status"] == "supported"
    assert one_two["differing"] == ["current_setpoint"]
    assert one_two["recorded_differences"] == []
    one_three = pairs[("EXP_001", "EXP_003")]
    assert one_three["conditions_status"] == "confounded"
    assert one_three["differing"] == ["air_flow", "sorbent_batch"]
    assert one_three["recorded_differences"] == [{"field": "operator", "a": "Op A", "b": "Op B"}]
    two_three = pairs[("EXP_002", "EXP_003")]
    assert two_three["conditions_status"] == "confounded"
    assert two_three["differing"] == ["current_setpoint", "air_flow", "sorbent_batch"]
    assert [f["factor"] for f in one_two["factors"]] == [
        "current_setpoint",
        "current_setpoint_profile",
        "air_flow",
        "solvent_flow",
        "ambient_temperature",
        "relative_humidity",
        "sorbent_batch",
    ]


def test_the_measured_conditions_are_the_readme_medians(ran):
    expected = {
        "EXP_001": (150.0, "constant", 1200.0, 8.0, 15.0, 50.0),
        "EXP_002": (200.0, "constant", 1200.0, 8.0, 15.0, 50.0),
        "EXP_003": (150.0, "constant", 2400.0, 8.0, 15.0, 50.0),
    }
    for experiment_id, values in expected.items():
        assert tuple(experiment(ran, experiment_id)["conditions"].values()) == values


def test_the_pressure_drop_check_and_the_missing_airflow_check_on_the_fixture(ran):
    summary = ran["summary"]
    assert summary["airflow_check"] is None  # EXP_004 is not in the fixture
    check = summary["pressure_drop_check"]
    assert [p["experiment_id"] for p in check["per_experiment"]] == list(IDS)
    for entry in check["per_experiment"]:
        # 0.5 Hz instants in the two steady windows; air flow is constant there, so no line
        assert entry["instants"] == 420
        assert entry["slope_air_flow"] is None and entry["r2_air_flow"] is None
        assert entry["slope_air_flow_sq"] is None and entry["best_lag_s"] is None
    across = check["across"]
    assert [
        (p["experiment_id"], p["air_flow_median"], p["pressure_drop_median"])
        for p in across["points"]
    ] == [
        ("EXP_001", 1200.0, 15.0),
        ("EXP_002", 1200.0, 15.0),
        ("EXP_003", 2400.0, 60.0),
    ]
    assert across["slope"] == pytest.approx(45 / 1200, rel=1e-9)
    assert across["intercept"] == pytest.approx(-30.0, rel=1e-9)
    assert across["r2"] == pytest.approx(1.0, rel=1e-9)


# ------------------------------------------------------------------ S5.17: read-only and rerun


def test_s5_17_the_run_changes_no_influxdb_table_and_no_postgres_table(ran):
    present = set(ran["influx_before"])
    assert {
        "readings_numeric",
        "readings_state",
        "readings_processed",
        "state_intervals",
        "metrics_series",
    } <= present
    assert len(ran["influx_before"]["readings_numeric"]) == 33315 - 3 * 5  # 5 states each
    assert len(ran["influx_before"]["readings_state"]) == 3 * 5
    for table, rows in ran["influx_before"].items():
        assert ran["influx_after"][table] == rows, table
        assert ran["influx_after_second"][table] == rows, table
    assert set(ran["influx_after"]) == set(ran["influx_before"])
    assert ran["pg_after"] == ran["pg_before"] == ran["pg_after_second"]
    assert len(ran["pg_before"]["experiment"]) == 3
    assert len(ran["pg_before"]["experiment_metrics"]) == 39


def test_s5_17_the_database_list_is_unchanged(ran):
    assert ran["databases_before"] == ran["databases_after"] == ran["databases_after_second"]
    assert ran["db"] in ran["databases_before"]
    assert "dac_missing" not in ran["databases_after"]


def test_s5_17_a_rerun_gives_the_same_summary_except_timing_and_the_same_report(ran):
    assert without_timing(ran["summary"]) == without_timing(ran["second_summary"])
    first = (ran["dir"] / "comparison_report.md").read_bytes()
    second = (ran["second_dir"] / "comparison_report.md").read_bytes()
    assert first == second
    assert set(ran["summary"]["timing"]) == {"seconds", "queries"}
    assert ran["summary"]["timing"]["queries"] > 0


# ------------------------------------------------------------------ S5.19: the files


def test_s5_19_the_summary_matches_the_contract_and_the_report_matches_the_summary(ran):
    text = (ran["dir"] / "comparison_summary.json").read_text(encoding="utf-8")
    summary = json.loads(text)
    jsonschema.validate(summary, SCHEMA)
    assert summary["compare_version"] == "m5-v1"
    assert summary["metrics_version"] == "m4-v1"
    assert summary["policy_version"] == "m3-v1"
    assert summary["source"]["database"] == ran["db"]
    assert summary["source"]["pg_schema"] == ran["schema"]
    assert summary["source"]["experiments_file"] == "tests/fixtures/compare/experiments.json"
    report = (ran["dir"] / "comparison_report.md").read_bytes().decode("utf-8")
    assert report == render_report(summary)
    assert "\r" not in report and "\r" not in text
    assert sorted(p.name for p in ran["dir"].iterdir()) == [
        "comparison_report.md",
        "comparison_summary.json",
    ]


def test_s5_19_the_parameters_are_the_policy_table_and_the_floats_have_nine_digits(ran):
    from pipeline import compare

    assert ran["summary"]["parameters"] == compare.POLICY

    def walk(value):
        if isinstance(value, float):
            assert value == sig9(value), value
        elif isinstance(value, dict):
            for key, item in value.items():
                if key != "parameters":
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(ran["summary"])


def test_the_outputs_never_hold_the_credentials(ran):
    secrets = [
        v
        for k, v in init_influx.load_env().items()
        if k in ("INFLUX_TOKEN", "POSTGRES_PASSWORD") and v
    ]
    assert secrets
    for name in ("comparison_summary.json", "comparison_report.md"):
        text = (ran["dir"] / name).read_text(encoding="utf-8")
        for secret in secrets:
            assert secret not in text
    assert all(secret not in ran["stdout"] for secret in secrets)


# ------------------------------------------------------------------ S5.18: refusals


def snapshot(ran, postgres_conn) -> tuple:
    return (influx_dump(ran["db"]), pg_dump(postgres_conn, ran["schema"]), database_names())


def assert_refused(result, report_dir: Path, reason: str) -> None:
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"refused ({reason})" in result.stderr
    assert not report_dir.exists() or list(report_dir.iterdir()) == []


def test_s5_18_a_missing_database_is_refused_and_not_created(ran, postgres_conn, tmp_path):
    result = run_compare("dac_missing", tmp_path / "r", ran["schema"])
    assert_refused(result, tmp_path / "r", "database_missing")
    assert "dac_missing" not in database_names()
    assert database_names() == ran["databases_before"]


def test_s5_18_another_policy_version_is_refused(ran, tmp_path):
    result = run_compare(ran["db"], tmp_path / "r", ran["schema"], "--policy-version", "m3-none")
    assert_refused(result, tmp_path / "r", "no_cleaned_readings")


def test_s5_18_another_metrics_version_is_refused(ran, tmp_path):
    result = run_compare(ran["db"], tmp_path / "r", ran["schema"], "--metrics-version", "m4-none")
    assert_refused(result, tmp_path / "r", "no_metrics_rows")


def test_s5_18_an_unreadable_experiments_file_is_refused(ran, tmp_path):
    result = run_compare(
        ran["db"], tmp_path / "r", ran["schema"], experiments=tmp_path / "missing.json"
    )
    assert_refused(result, tmp_path / "r", "experiments_unreadable")


def test_s5_18_a_schema_without_migration_0003_is_refused(ran, postgres_conn, tmp_path):
    with throwaway_schema(postgres_conn) as schema:
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("DROP TABLE {}.experiment_metrics, {}.signal_quality").format(
                    psycopg.sql.Identifier(schema), psycopg.sql.Identifier(schema)
                )
            )
        postgres_conn.commit()
        result = run_compare(ran["db"], tmp_path / "r", schema)
        assert_refused(result, tmp_path / "r", "postgres_not_migrated")


def test_s5_18_an_experiment_missing_from_postgres_is_refused(ran, postgres_conn, tmp_path):
    with throwaway_schema(postgres_conn, load=False) as schema:
        result = run_compare(ran["db"], tmp_path / "r", schema)
        assert_refused(result, tmp_path / "r", "experiment_missing_in_postgres")
        assert "EXP_001" in result.stderr


def test_s5_18_an_experiment_without_metrics_rows_is_refused(ran, postgres_conn, tmp_path):
    with throwaway_schema(postgres_conn) as schema:  # loaded, but `scripts.metrics` never ran here
        result = run_compare(ran["db"], tmp_path / "r", schema)
        assert_refused(result, tmp_path / "r", "experiment_metrics_missing")


@pytest.mark.parametrize("column", ["start_time", "end_time"])
def test_s5_18_a_postgres_window_that_differs_from_the_file_is_refused(
    ran, postgres_conn, tmp_path, column
):
    with throwaway_schema(postgres_conn) as schema:
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL(
                    "UPDATE {}.experiment SET {} = {} + interval '1 second' "
                    "WHERE experiment_id = 'EXP_001'"
                ).format(
                    psycopg.sql.Identifier(schema),
                    psycopg.sql.Identifier(column),
                    psycopg.sql.Identifier(column),
                )
            )
        postgres_conn.commit()
        result = run_compare(ran["db"], tmp_path / "r", schema)
        assert_refused(result, tmp_path / "r", "window_mismatch")
        assert "EXP_001" in result.stderr and column in result.stderr


def test_s5_18_a_start_time_in_the_file_that_differs_from_postgres_is_refused(ran, tmp_path):
    shifted = json.loads(EXPERIMENTS.read_text(encoding="utf-8"))
    shifted[0]["start_time"] = "2026-05-04T08:00:01Z"
    path = tmp_path / "shifted.json"
    path.write_text(json.dumps(shifted), encoding="utf-8")
    result = run_compare(ran["db"], tmp_path / "r", ran["schema"], experiments=path)
    assert_refused(result, tmp_path / "r", "window_mismatch")


def test_s5_18_the_refusals_changed_no_store(ran, postgres_conn):
    assert influx_dump(ran["db"]) == ran["influx_before"]
    assert pg_dump(postgres_conn, ran["schema"]) == ran["pg_before"]
    assert database_names() == ran["databases_before"]
    assert sorted(set(database_names()) - {ran["db"]}) == PROTECTED_DATABASES


def test_no_throwaway_schema_is_left_behind(ran, postgres_conn):
    try:
        with postgres_conn.cursor() as cur:
            cur.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'm5_e2e_%' ORDER BY nspname"
            )
            names = [row[0] for row in cur.fetchall()]
    finally:
        postgres_conn.rollback()
    assert names == [ran["schema"]]


# ------------------------------------------------------------------ the recompute (no pipeline)
#
# Everything below uses only plain SELECT pulls of the accepted readings and of `state_intervals`
# and arithmetic from the decisions, written out again here. Nothing from `pipeline/` is used to
# compute a value.


def start_of(experiment_id: str) -> datetime:
    for entry in json.loads(EXPERIMENTS.read_text(encoding="utf-8")):
        if entry["experiment_id"] == experiment_id:
            return datetime.strptime(entry["start_time"], "%Y-%m-%dT%H:%M:%SZ")
    raise KeyError(experiment_id)


def bounds(experiment_id: str) -> str:
    """The time filter of one experiment's window `[start, end)` (every read is bounded)."""
    first = timegm(start_of(experiment_id).timetuple())
    lo, hi = (
        datetime.fromtimestamp(first + offset, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        for offset in (0, DURATION)
    )
    return f"time >= '{lo}' AND time < '{hi}'"


def pull(database: str, experiment_id: str, signal: str) -> dict[int, float]:
    start = start_of(experiment_id)
    rows = query(
        database,
        "SELECT time, value FROM readings_processed "
        f"WHERE experiment_id = '{experiment_id}' AND signal = '{signal}' "
        f"AND verdict = 'accepted' AND value IS NOT NULL AND {bounds(experiment_id)} ORDER BY time",
    )
    return {
        int((datetime.strptime(r["time"][:19], "%Y-%m-%d %H:%M:%S") - start).total_seconds()): r[
            "value"
        ]
        for r in rows
    }


def pull_phases(database: str, experiment_id: str) -> list[tuple[str, int, int]]:
    start_s = timegm(start_of(experiment_id).timetuple())
    rows = query(
        database,
        "SELECT time, end_ns, value FROM state_intervals "
        f"WHERE experiment_id = '{experiment_id}' AND signal = 'process_state' "
        f"AND verdict = 'accepted' AND {bounds(experiment_id)} ORDER BY time",
    )
    out = []
    for r in rows:
        begin = timegm(datetime.strptime(r["time"][:19], "%Y-%m-%d %H:%M:%S").timetuple()) - start_s
        out.append((r["value"], begin, round(r["end_ns"] / 1e9) - start_s))
    return out


def as_of(series: dict[int, float], t: int, max_age: int = 10) -> float | None:
    earlier = [k for k in series if k <= t]
    if not earlier or t - max(earlier) > max_age:
        return None
    return series[max(earlier)]


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    p = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(c + 1, p):
            f = m[r][c] / m[c][c]
            for k in range(c, p + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * p
    for i in range(p - 1, -1, -1):
        x[i] = (m[i][p] - sum(m[i][k] * x[k] for k in range(i + 1, p))) / m[i][i]
    return x


def ols(columns: list[list[float]], y: list[float]) -> list[float]:
    n = len(y)
    means = [math.fsum(c) / n for c in columns]
    my = math.fsum(y) / n
    xc = [[v - m for v in c] for c, m in zip(columns, means, strict=True)]
    yc = [v - my for v in y]
    sxx = [[math.fsum(a * b for a, b in zip(ci, cj, strict=True)) for cj in xc] for ci in xc]
    sxy = [math.fsum(a * b for a, b in zip(ci, yc, strict=True)) for ci in xc]
    return solve(sxx, sxy)


def recompute_fit(database: str, experiment_id: str, windows: list[tuple[int, int]]):
    volt, cur = pull(database, experiment_id, "voltage"), pull(database, experiment_id, "current")
    flow, pres = pull(database, experiment_id, "flow"), pull(database, experiment_id, "pressure")
    temp = pull(database, experiment_id, "electrolyte_temperature")
    columns: list[list[float]] = [[], [], [], []]
    y: list[float] = []
    for t in sorted(volt):
        if not any(lo <= t < hi for lo, hi in windows):
            continue
        if t not in cur or t not in flow or t not in pres:
            continue
        temperature = as_of(temp, t)
        if temperature is None:
            continue
        for column, value in zip(columns, (cur[t], temperature, flow[t], pres[t]), strict=True):
            column.append(value)
        y.append(volt[t])
    return len(y), ols(columns, y)


def recompute_kpis(database: str, experiment_id: str, windows: list[tuple[int, int]]):
    volt, cur = pull(database, experiment_id, "voltage"), pull(database, experiment_id, "current")

    def inside(t: int) -> bool:
        return any(lo <= t < hi for lo, hi in windows)

    mean_voltage = math.fsum(v for t, v in volt.items() if inside(t)) / sum(
        1 for t in volt if inside(t)
    )
    power = {t: volt[t] * cur[t] for t in sorted(volt) if t in cur and inside(t)}
    times = sorted(power)
    areas, covered = [], 0
    for a, b in zip(times, times[1:], strict=False):
        if b - a <= 2:
            areas.append((power[a] + power[b]) / 2 * (b - a))
            covered += b - a
    return mean_voltage, math.fsum(areas) / covered / 1000, covered


def test_the_phases_of_every_experiment_equal_a_plain_pull_of_state_intervals(ran):
    for experiment_id in IDS:
        phases = pull_phases(ran["db"], experiment_id)
        assert [(s, a, b) for s, a, b in phases] == [
            (state, start, end) for _, state, start, end, _, _ in EXPECTED_PHASES
        ]
        got = experiment(ran, experiment_id)["phases"]
        assert [(p["state"], p["start_s"], p["end_s"]) for p in got] == phases
        for (_state, start, end), p in zip(phases, got, strict=True):
            assert (p["window_start_s"], p["window_end_s"]) == (
                (start + 60, end) if start + 60 < end else (None, None)
            )


def test_the_steady_kpis_equal_an_independent_recompute_from_plain_pulls(ran):
    for experiment_id in IDS:
        phases = pull_phases(ran["db"], experiment_id)
        windows = [(a + 60, b) for state, a, b in phases if state == "STEADY_STATE" and a + 60 < b]
        assert windows == [(180, 600), (720, 1140)]
        voltage, power, covered = recompute_kpis(ran["db"], experiment_id, windows)
        kpis = experiment(ran, experiment_id)["kpis"]
        assert kpis["voltage_mean_v"]["value"] == pytest.approx(voltage, rel=1e-8), experiment_id
        assert kpis["mean_power_kw"]["value"] == pytest.approx(power, rel=1e-8), experiment_id
        assert covered == 838
        assert kpis["mean_power_kw"]["coverage"] == pytest.approx(covered / 840, rel=1e-8)
        # and the recompute itself agrees with the hand computation in README.md
        assert sig9(voltage) == EXPECTED_KPIS[experiment_id][0]
        assert sig9(power) == EXPECTED_KPIS[experiment_id][1]


def test_the_hydrolyzer_coefficients_equal_an_independent_ols_from_plain_pulls(ran):
    names = ("current", "electrolyte_temperature", "flow", "pressure")
    for window_name, windows in (
        ("steady", [(180, 600), (720, 1140)]),
        ("whole_run", [(0, DURATION)]),
    ):
        for experiment_id in IDS:
            instants, beta = recompute_fit(ran["db"], experiment_id, windows)
            entry = model_entry(ran, "hydrolyzer", window_name, experiment_id)
            assert entry["instants"] == instants, (window_name, experiment_id)
            for name, value in zip(names, beta, strict=True):
                assert term(entry, name)["coefficient"] == pytest.approx(
                    value, rel=1e-6, abs=1e-9
                ), (
                    window_name,
                    experiment_id,
                    name,
                )
            # the planted values, within the README's tolerances
            assert beta[2] == pytest.approx(-0.2, abs=0.02)
            assert beta[3] == pytest.approx(3.0, abs=0.3)
