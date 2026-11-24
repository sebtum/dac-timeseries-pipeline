"""End-to-end metrics: the real CLIs against a live InfluxDB and Postgres (M4: S4.1, S4.2, S4.4,
S4.5, S4.7, S4.9, S4.12, S4.13, S4.16, S4.17, S4.18, S4.21).

The fixture `tests/fixtures/metrics/readings.csv` is built by `make_fixture.py` (one experiment,
EXP_001, 600 s). Every expected number below is a literal from the hand computation in
`tests/fixtures/metrics/README.md`, derived from the construction, not read from the pipeline:

  586 power_computed and 586 power_residual rows; 585 of 586 within tolerance, max residual 250 W.
  energy 2.433320575 kWh over 584 s; logged 2.445904612 kWh over 587 s; relative difference
  3.4532e-05 over the 584 s overlap. 297 capture_efficiency rows (mean 0.7500029228, 592 s).
  269 capture_rate rows (532 s): captured 0.1042968609 kg, inlet 0.1390624812 kg, mean
  0.7057682316 kg/h. Energy per kg 21.25323857 kWh/kg over 517 s. Completeness 2981 / 7360.

(The scenario text of S4.9 says 268 capture_rate rows; the construction gives 269, see the README.)

The last block recomputes every metric from plain `SELECT` pulls of `readings_processed`, with no
import from `pipeline/`, and compares the result with the summary and with `metrics_series`.

Throwaway state only: one InfluxDB database and one Postgres schema per module, both dropped in a
`finally`. Core allows five databases and three exist, so a test holds at most one extra one.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import jsonschema
import psycopg
import pytest

import scripts.init_influx as init_influx
import scripts.migrate as migrate
from pipeline.metadata_loader import load_experiments
from pipeline.metrics_run import render_report
from pipeline.pg_migrate import run_migrations
from tests.e2e.helpers import REPO_ROOT, database_names, query, run_ingest, tables

pytestmark = [pytest.mark.influx, pytest.mark.postgres]

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "metrics"
EXPERIMENTS = FIXTURES / "experiments.json"
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "metrics_summary.schema.json").read_text(encoding="utf-8")
)
START = datetime(2026, 5, 4, 8, 0, 0)
DURATION = 600
SERIES = ("power_computed", "power_residual", "capture_efficiency", "capture_rate")
INPUT_TABLES = (
    "readings_numeric",
    "readings_state",
    "readings_conflicts",
    "readings_processed",
    "state_intervals",
    "quality_intervals",
)

# ------------------------------------------------------------------ the hand computation

# Instants (seconds after 08:00:00) with no computed power, and where the logged power is off.
NO_COMPUTED_POWER = {100, *range(300, 311), 450, 451}
EVEN_VI, ODD_VI = 15026.26125, 14973.76125  # 100.075 x 150.15 and 99.925 x 149.85

# metric -> (value, coverage, status); coverage in seconds / 600, from README.md.
EXPECTED_METRICS = {
    "energy_kwh": (2.433320575, 584 / 600, "complete"),
    "energy_logged_kwh": (2.445904612152778, 587 / 600, "complete"),
    "energy_relative_difference": (3.453214452755687e-05, 584 / 600, "complete"),
    "mean_power_kw": (14.999921352739726, 584 / 600, "complete"),
    "capture_efficiency_mean": (0.7500029228344976, 592 / 600, "complete"),
    "co2_captured_kg": (0.10429686089186734, 532 / 600, "partial"),
    "co2_inlet_kg": (0.13906248118915645, 532 / 600, "partial"),
    "capture_rate_mean_kg_h": (0.7057682315991023, 532 / 600, "partial"),
    "sec_kwh_per_kg": (21.25323856585456, 517 / 600, "partial"),
    "completeness": (2981 / 7360, None, None),
    "valid_fraction": (2979 / 2983, None, None),
    "bad_fraction": (3 / 2983, None, None),
    "uncertain_fraction": (1 / 2983, None, None),
}
EXPECTED_SERIES_COUNTS = {
    "power_computed": 586,
    "power_residual": 586,
    "capture_efficiency": 297,
    "capture_rate": 269,
}
# (present, expected, accepted, bad, uncertain) of the signals that have rows in the fixture.
EXPECTED_SIGNALS = {
    "voltage": (589, 600, 589, 0, 0),
    "current": (587, 600, 586, 1, 0),
    "power": (589, 600, 589, 0, 0),
    "co2_in_ppm": (300, 300, 298, 2, 0),
    "co2_out_ppm": (300, 300, 299, 0, 1),
    "air_flow": (600, 600, 600, 0, 0),
    "ambient_temperature": (8, 10, 8, 0, 0),
    "ambient_pressure": (8, 10, 8, 0, 0),
    "process_state": (2, None, 2, 0, 0),
}
EXCLUDED_READINGS = {
    ("current", 100),
    ("co2_out_ppm", 400),
    ("co2_in_ppm", 500),
    ("co2_in_ppm", 502),
}


# ------------------------------------------------------------------ running the CLIs


def run_clean(database: str, report_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.clean",
            "--database",
            database,
            "--experiments",
            str(EXPERIMENTS),
            "--report-dir",
            str(report_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def run_metrics(
    database: str,
    report_dir: Path,
    schema: str,
    *extra: str,
    experiments: Path = EXPERIMENTS,
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.metrics",
            "--database",
            database,
            "--experiments",
            str(experiments),
            "--pg-schema",
            schema,
            "--report-dir",
            str(report_dir),
            *extra,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
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
    """A fresh Postgres schema, migrated and loaded with the fixture experiment, dropped after."""
    schema = f"m4_e2e_{uuid.uuid4().hex[:10]}"
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


def pg_rows(postgres_conn, schema: str, table: str) -> list[tuple]:
    """Every row of a Postgres table, in a stable order (a read, then the transaction ends)."""
    try:
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("SELECT * FROM {}.{} ORDER BY 1, 2, 3, 4, 5").format(
                    psycopg.sql.Identifier(schema), psycopg.sql.Identifier(table)
                )
            )
            return cur.fetchall()
    finally:
        postgres_conn.rollback()


def pg_columns(postgres_conn, schema: str, table: str) -> list[str]:
    try:
        with postgres_conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                (schema, table),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        postgres_conn.rollback()


@pytest.fixture(scope="module")
def pg_schema(postgres_conn):
    with throwaway_schema(postgres_conn) as schema:
        yield schema


# ------------------------------------------------------------------ dumps


def offset_of(text: str) -> int:
    return int((datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S") - START).total_seconds())


def input_dump(database: str) -> dict[str, list[dict]]:
    """Full dump of the six input tables (empty when a table does not exist)."""
    present = tables(database)
    orders = {
        "readings_numeric": "experiment_id, signal, time",
        "readings_state": "experiment_id, signal, time",
        "readings_conflicts": "experiment_id, signal, time, discard_rank",
        "readings_processed": "experiment_id, signal, time",
        "state_intervals": "experiment_id, signal, time",
        "quality_intervals": "experiment_id, signal, kind, time",
    }
    return {
        table: query(database, f"SELECT * FROM {table} ORDER BY {orders[table]}")
        if table in present
        else []
        for table in INPUT_TABLES
    }


def series_dump(database: str) -> list[dict]:
    if "metrics_series" not in tables(database):
        return []
    return query(database, "SELECT * FROM metrics_series ORDER BY metric, time")


def series_rows(database: str, metric: str) -> dict[int, float]:
    rows = query(
        database,
        f"SELECT time, value FROM metrics_series WHERE metric = '{metric}' ORDER BY time",
    )
    return {offset_of(r["time"]): r["value"] for r in rows}


def without_timing(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k != "timing"}


# ------------------------------------------------------------------ the module's runs


@pytest.fixture(scope="module")
def ran(module_db, pg_schema, postgres_conn, tmp_path_factory):
    ingested = run_ingest(fixture_files(), module_db, tmp_path_factory.mktemp("ingest"))
    assert ingested.returncode == 0, ingested.stderr + ingested.stdout
    cleaned = run_clean(module_db, tmp_path_factory.mktemp("clean"))
    assert cleaned.returncode == 0, cleaned.stderr + cleaned.stdout
    inputs_before = input_dump(module_db)
    tables_before = set(tables(module_db))

    first_dir = tmp_path_factory.mktemp("first")
    first = run_metrics(module_db, first_dir, pg_schema)
    assert first.returncode == 0, first.stderr + first.stdout
    inputs_after = input_dump(module_db)
    tables_after = set(tables(module_db))
    series_first = series_dump(module_db)
    metrics_first = pg_rows(postgres_conn, pg_schema, "experiment_metrics")
    quality_first = pg_rows(postgres_conn, pg_schema, "signal_quality")

    second_dir = tmp_path_factory.mktemp("second")
    second = run_metrics(module_db, second_dir, pg_schema)
    assert second.returncode == 0, second.stderr + second.stdout
    return {
        "db": module_db,
        "schema": pg_schema,
        "dir": first_dir,
        "stdout": first.stdout,
        "summary": json.loads((first_dir / "metrics_summary.json").read_text("utf-8")),
        "second_summary": json.loads((second_dir / "metrics_summary.json").read_text("utf-8")),
        "second_dir": second_dir,
        "inputs_before": inputs_before,
        "inputs_after": inputs_after,
        "inputs_after_second": input_dump(module_db),
        "tables_before": tables_before,
        "tables_after": tables_after,
        "series_first": series_first,
        "series_second": series_dump(module_db),
        "metrics_first": metrics_first,
        "metrics_second": pg_rows(postgres_conn, pg_schema, "experiment_metrics"),
        "quality_first": quality_first,
        "quality_second": pg_rows(postgres_conn, pg_schema, "signal_quality"),
    }


def experiment(ran) -> dict:
    (entry,) = ran["summary"]["experiments"]
    assert entry["experiment_id"] == "EXP_001"
    return entry


# ------------------------------------------------------------------ the fixture itself


def test_the_fixture_bytes_match_the_committed_checksum_and_use_unix_line_endings():
    data = (FIXTURES / "readings.csv").read_bytes()
    assert b"\r" not in data
    digest, name = (FIXTURES / "readings.sha256").read_text(encoding="utf-8").split()
    assert name == "readings.csv"
    assert hashlib.sha256(data).hexdigest() == digest
    assert len(data.splitlines()) == 2983 + 1


def test_cleaning_excludes_exactly_the_four_planted_readings(ran):
    excluded = query(
        ran["db"],
        "SELECT time, signal, quality, reason FROM readings_processed "
        "WHERE verdict = 'excluded' ORDER BY time",
    )
    assert {(r["signal"], offset_of(r["time"])) for r in excluded} == EXCLUDED_READINGS
    assert len(excluded) == 4
    accepted = query(
        ran["db"], "SELECT COUNT(*) AS n FROM readings_processed WHERE verdict = 'accepted'"
    )
    states = query(ran["db"], "SELECT COUNT(*) AS n FROM state_intervals")
    assert accepted[0]["n"] + states[0]["n"] == 2979


# ------------------------------------------------------------------ S4.1, S4.2: the power series


def test_s4_1_computed_power_exists_exactly_where_voltage_and_current_are_accepted(ran):
    rows = series_rows(ran["db"], "power_computed")
    assert len(rows) == 586
    assert set(rows) == set(range(DURATION)) - NO_COMPUTED_POWER
    for k in (100, 300, 305, 310, 450, 451):
        assert k not in rows
    for k, value in rows.items():
        assert value == pytest.approx(EVEN_VI if k % 2 == 0 else ODD_VI, rel=1e-12), k
    # and equal to voltage x current of the accepted pulls
    voltage, current = pull(ran["db"], "voltage"), pull(ran["db"], "current")
    for k, value in rows.items():
        assert value == pytest.approx(voltage[k] * current[k], rel=1e-12), k
    assert ran["summary"]["experiments"][0]["series_written"]["power_computed"] == 586


def test_s4_2_the_power_cross_check_counts_the_disagreeing_instants(ran):
    rows = series_rows(ran["db"], "power_residual")
    assert len(rows) == 586
    assert set(rows) == set(range(DURATION)) - NO_COMPUTED_POWER
    for k, value in rows.items():
        assert value == pytest.approx(250.0 if k == 200 else 0.0, abs=1e-8), k
    power = pull(ran["db"], "power")
    voltage, current = pull(ran["db"], "voltage"), pull(ran["db"], "current")
    for k, value in rows.items():
        assert value == pytest.approx(power[k] - voltage[k] * current[k], abs=1e-9), k
    check = experiment(ran)["power_check"]
    assert check["instants_compared"] == 586
    assert check["within_tolerance"] == 585
    assert check["within_tolerance_fraction"] == pytest.approx(585 / 586, rel=1e-8)
    assert check["residual_max_abs_w"] == pytest.approx(250.0, rel=1e-9)
    assert check["residual_median_w"] == pytest.approx(0.0, abs=1e-9)
    assert check["residual_p95_abs_w"] == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------------ S4.4, S4.5, S4.7, S4.9


def check_metric(entry: dict, name: str) -> None:
    value, coverage, status = EXPECTED_METRICS[name]
    metric = entry["metrics"][name]
    assert metric["value"] == pytest.approx(value, rel=1e-8), name
    if coverage is None:
        assert metric["coverage"] is None and metric["status"] is None, name
    else:
        assert metric["coverage"] == pytest.approx(coverage, rel=1e-8), name
        assert metric["status"] == status, name


def test_s4_4_energy_covers_only_bridged_time_and_is_not_scaled_up(ran):
    entry = experiment(ran)
    for name in ("energy_kwh", "mean_power_kw", "energy_logged_kwh"):
        check_metric(entry, name)
    assert entry["metrics"]["energy_kwh"]["coverage"] == pytest.approx(584 / 600, rel=1e-8)
    assert entry["metrics"]["energy_kwh"]["status"] == "complete"
    assert entry["metrics"]["energy_logged_kwh"]["coverage"] == pytest.approx(587 / 600, rel=1e-8)
    # 582 one-second spacings of 15000.01125 W s and one 2 s spacing of 2 x 14973.76125 W s
    by_hand = (582 * 15000.01125 + 2 * ODD_VI) / 3.6e6
    assert entry["metrics"]["energy_kwh"]["value"] == pytest.approx(by_hand, rel=1e-8)
    assert by_hand == pytest.approx(2.433320575, rel=1e-12)


def test_s4_5_logged_energy_is_compared_over_the_overlap_only(ran):
    entry = experiment(ran)
    check_metric(entry, "energy_relative_difference")
    # logged over the overlap = computed + 250 (the +250 W spike) + 52.5 (the point at +100)
    assert entry["metrics"]["energy_relative_difference"]["value"] == pytest.approx(
        302.5 / 8759954.07, rel=1e-8
    )
    checks = {p["check"]: p for p in entry["plausibility"]}
    assert checks["energy_agreement"]["passed"] is True
    assert checks["energy_agreement"]["limit"] == 0.01
    # the +450 and +451 logged readings exist but lie outside the overlap
    logged = pull(ran["db"], "power")
    assert 450 in logged and 451 in logged and 450 not in series_rows(ran["db"], "power_computed")


def test_s4_7_capture_efficiency_is_the_mean_over_instants_with_both_readings(ran):
    rows = series_rows(ran["db"], "capture_efficiency")
    assert len(rows) == 297
    assert set(rows) == set(range(0, DURATION, 2)) - {400, 500, 502}
    for k, value in rows.items():
        by_hand = 315.15 / 420.55 if (k // 2) % 2 == 0 else 314.85 / 419.45
        assert value == pytest.approx(by_hand, rel=1e-9), k
    entry = experiment(ran)
    check_metric(entry, "capture_efficiency_mean")
    assert entry["efficiency_check"] == {"instants": 297, "at_or_below_zero": 0}


def test_s4_9_capture_rate_and_captured_co2_match_the_hand_computation(ran):
    rows = series_rows(ran["db"], "capture_rate")
    assert len(rows) == 269
    assert set(rows) == set(range(0, 361, 2)) | set(range(420, 499, 2)) | set(range(504, 599, 2))
    for k in (400, 500, 502, 362, 364, 418):
        assert k not in rows
    # the rows at +0 and +2 and at +420 and +422, by hand (README.md)
    assert rows[0] == pytest.approx(0.7059805001781152, rel=1e-9)
    assert rows[2] == pytest.approx(0.7053084578171650, rel=1e-9)
    assert rows[420] == pytest.approx(0.7062572553656653, rel=1e-9)
    assert rows[422] == pytest.approx(0.7055849495537988, rel=1e-9)
    entry = experiment(ran)
    for name in ("co2_captured_kg", "co2_inlet_kg", "capture_rate_mean_kg_h"):
        check_metric(entry, name)
    assert entry["metrics"]["co2_captured_kg"]["coverage"] == pytest.approx(532 / 600, rel=1e-8)
    assert entry["metrics"]["co2_captured_kg"]["status"] == "partial"
    check_metric(entry, "sec_kwh_per_kg")
    assert entry["metrics"]["sec_kwh_per_kg"]["coverage"] == pytest.approx(517 / 600, rel=1e-8)


def test_the_four_plausibility_checks_pass_and_the_exit_code_is_0(ran):
    entry = experiment(ran)
    assert [p["check"] for p in entry["plausibility"]] == [
        "capture_below_inlet",
        "efficiency_in_unit_interval",
        "energy_agreement",
        "sec_above_floor",
    ]
    assert all(p["passed"] is True for p in entry["plausibility"])
    assert ran["summary"]["plausibility_failed"] == 0
    assert entry["series_written"] == EXPECTED_SERIES_COUNTS
    assert ran["summary"]["timing"]["points_written"] == sum(EXPECTED_SERIES_COUNTS.values())


# ------------------------------------------------------------------ S4.12, S4.13: data quality


def test_s4_12_data_quality_is_reported_for_all_25_signals(ran):
    signals = experiment(ran)["signals"]
    assert len(signals) == 25
    assert [(s["source"], s["signal"]) for s in signals] == sorted(
        (s["source"], s["signal"]) for s in signals
    )
    by_name = {s["signal"]: s for s in signals}
    for name, (present, expected, accepted, bad, uncertain) in EXPECTED_SIGNALS.items():
        s = by_name[name]
        assert (s["present"], s["expected"], s["accepted"], s["bad"], s["uncertain"]) == (
            present,
            expected,
            accepted,
            bad,
            uncertain,
        ), name
        if expected is None:
            assert s["completeness"] is None and s["nominal_interval_s"] is None, name
        else:
            assert s["completeness"] == pytest.approx(present / expected, rel=1e-8), name
    current = by_name["current"]
    assert (current["present"], current["expected"], current["accepted"], current["bad"]) == (
        587,
        600,
        586,
        1,
    )
    assert current["completeness"] == pytest.approx(587 / 600, rel=1e-8)
    assert by_name["co2_out_ppm"]["uncertain"] == 1
    assert (by_name["ambient_pressure"]["present"], by_name["ambient_pressure"]["expected"]) == (
        8,
        10,
    )
    assert by_name["process_state"]["present"] == 2
    flow = by_name["flow"]
    assert (flow["present"], flow["expected"], flow["completeness"]) == (0, 600, 0.0)
    assert flow["valid_fraction"] is flow["bad_fraction"] is flow["uncertain_fraction"] is None
    for name in set(by_name) - set(EXPECTED_SIGNALS):
        assert by_name[name]["present"] == 0, name


def test_s4_13_experiment_level_shares_add_up_over_the_signals(ran):
    entry = experiment(ran)
    for name in ("completeness", "valid_fraction", "bad_fraction", "uncertain_fraction"):
        check_metric(entry, name)
    signals = entry["signals"]
    assert sum(s["present"] for s in signals) == 2983
    assert sum(s["accepted"] for s in signals) == 2979
    assert sum(s["bad"] for s in signals) == 3
    assert sum(s["uncertain"] for s in signals) == 1
    assert sum(s["present"] for s in signals if s["expected"] is not None) == 2981
    assert sum(s["expected"] for s in signals if s["expected"] is not None) == 7360


def test_postgres_holds_one_row_per_metric_and_per_signal(ran):
    metrics_rows, quality_rows = ran["metrics_first"], ran["quality_first"]
    assert len(metrics_rows) == 13 and len(quality_rows) == 25
    assert {row[0] for row in metrics_rows} == {"EXP_001"}
    assert {row[1] for row in metrics_rows} == {"m4-v1"}
    assert {row[2] for row in metrics_rows} == {"m3-v1"}
    by_metric = {row[3]: row for row in metrics_rows}
    for name, (value, coverage, status) in EXPECTED_METRICS.items():
        _, _, _, _, got_value, _, got_coverage, got_status = by_metric[name]
        assert got_value == pytest.approx(value, rel=1e-9), name
        assert got_status == status, name
        if coverage is not None:
            assert got_coverage == pytest.approx(coverage, rel=1e-9), name


# ------------------------------------------------------------------ S4.16, S4.17: no side effects


def test_s4_16_a_rerun_changes_nothing(ran):
    assert ran["series_first"] == ran["series_second"]
    assert len(ran["series_first"]) == sum(EXPECTED_SERIES_COUNTS.values())
    assert ran["metrics_first"] == ran["metrics_second"]
    assert ran["quality_first"] == ran["quality_second"]
    assert without_timing(ran["summary"]) == without_timing(ran["second_summary"])
    first = (ran["dir"] / "metrics_report.md").read_text(encoding="utf-8")
    second = (ran["second_dir"] / "metrics_report.md").read_text(encoding="utf-8")
    assert first == second


def test_s4_17_the_run_touches_no_input_table(ran):
    for table in INPUT_TABLES:
        assert ran["inputs_before"][table] == ran["inputs_after"][table], table
        assert ran["inputs_before"][table] == ran["inputs_after_second"][table], table
    assert len(ran["inputs_before"]["readings_numeric"]) == 2981
    assert ran["tables_after"] - ran["tables_before"] == {"metrics_series"}
    assert ran["tables_before"] - ran["tables_after"] == set()
    recon = ran["summary"]["reconciliation"]
    assert recon["inputs_unchanged"] is True
    assert recon["balanced"] is True and recon["mismatches"] == []
    assert recon["influx_series_checked"] == 4 and recon["postgres_rows_checked"] == 38


# ------------------------------------------------------------------ S4.21: the files


def test_s4_21_the_summary_matches_the_contract_and_the_report_matches_the_summary(ran):
    text = (ran["dir"] / "metrics_summary.json").read_text(encoding="utf-8")
    summary = json.loads(text)
    jsonschema.validate(summary, SCHEMA)
    assert summary["metrics_version"] == "m4-v1"
    assert summary["policy_version"] == "m3-v1"
    assert summary["source"]["database"] == ran["db"]
    assert summary["source"]["pg_schema"] == ran["schema"]
    assert summary["source"]["experiments_file"] == "tests/fixtures/metrics/experiments.json"
    report = (ran["dir"] / "metrics_report.md").read_bytes().decode("utf-8")
    assert report == render_report(summary)
    assert "\r" not in report and "\r" not in text
    assert sorted(p.name for p in ran["dir"].iterdir()) == [
        "metrics_report.md",
        "metrics_summary.json",
    ]


def test_the_outputs_never_hold_the_credentials(ran):
    secrets = [
        v
        for k, v in init_influx.load_env().items()
        if k in ("INFLUX_TOKEN", "POSTGRES_PASSWORD") and v
    ]
    assert secrets
    for name in ("metrics_summary.json", "metrics_report.md"):
        text = (ran["dir"] / name).read_text(encoding="utf-8")
        for secret in secrets:
            assert secret not in text
    assert all(secret not in ran["stdout"] for secret in secrets)


# ------------------------------------------------------------------ S4.18: refusals


def snapshot(database: str, postgres_conn, schema: str) -> tuple:
    return (
        series_dump(database),
        pg_rows(postgres_conn, schema, "experiment_metrics"),
        pg_rows(postgres_conn, schema, "signal_quality"),
        set(tables(database)),
    )


def assert_refused(result, report_dir: Path, reason: str) -> None:
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"refused ({reason})" in result.stderr
    assert not report_dir.exists() or list(report_dir.iterdir()) == []


def test_s4_18_a_missing_database_is_refused_and_not_created(ran, postgres_conn, tmp_path):
    before = snapshot(ran["db"], postgres_conn, ran["schema"])
    result = run_metrics("dac_missing", tmp_path / "r", ran["schema"])
    assert_refused(result, tmp_path / "r", "database_missing")
    assert "dac_missing" not in database_names()
    assert snapshot(ran["db"], postgres_conn, ran["schema"]) == before


def test_s4_18_another_policy_version_is_refused(ran, postgres_conn, tmp_path):
    before = snapshot(ran["db"], postgres_conn, ran["schema"])
    result = run_metrics(ran["db"], tmp_path / "r", ran["schema"], "--policy-version", "m3-none")
    assert_refused(result, tmp_path / "r", "no_cleaned_readings")
    assert snapshot(ran["db"], postgres_conn, ran["schema"]) == before


def test_s4_18_an_unreadable_experiments_file_is_refused(ran, postgres_conn, tmp_path):
    before = snapshot(ran["db"], postgres_conn, ran["schema"])
    result = run_metrics(
        ran["db"], tmp_path / "r", ran["schema"], experiments=tmp_path / "missing.json"
    )
    assert_refused(result, tmp_path / "r", "experiments_unreadable")
    assert snapshot(ran["db"], postgres_conn, ran["schema"]) == before


def test_s4_18_a_schema_without_migration_0003_is_refused(ran, postgres_conn, tmp_path):
    before = snapshot(ran["db"], postgres_conn, ran["schema"])
    with throwaway_schema(postgres_conn) as schema:
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("DROP TABLE {}.experiment_metrics, {}.signal_quality").format(
                    psycopg.sql.Identifier(schema), psycopg.sql.Identifier(schema)
                )
            )
        postgres_conn.commit()
        result = run_metrics(ran["db"], tmp_path / "r", schema)
        assert_refused(result, tmp_path / "r", "postgres_not_migrated")
    assert snapshot(ran["db"], postgres_conn, ran["schema"]) == before


def test_s4_18_an_experiment_missing_from_postgres_is_refused(ran, postgres_conn, tmp_path):
    before = snapshot(ran["db"], postgres_conn, ran["schema"])
    with throwaway_schema(postgres_conn, load=False) as schema:
        result = run_metrics(ran["db"], tmp_path / "r", schema)
        assert_refused(result, tmp_path / "r", "experiment_missing_in_postgres")
        assert "EXP_001" in result.stderr
        assert pg_rows(postgres_conn, schema, "experiment_metrics") == []
        assert pg_rows(postgres_conn, schema, "signal_quality") == []
    assert snapshot(ran["db"], postgres_conn, ran["schema"]) == before


# ------------------------------------------------------------------ the recompute (no pipeline)
#
# Everything below uses only plain SELECT pulls of the accepted readings and arithmetic from the
# decisions, written out again here. Nothing from `pipeline/` is used to compute a value.


def pull(database: str, signal: str) -> dict[int, float]:
    rows = query(
        database,
        "SELECT time, value FROM readings_processed "
        f"WHERE signal = '{signal}' AND verdict = 'accepted' AND value IS NOT NULL ORDER BY time",
    )
    return {offset_of(r["time"]): r["value"] for r in rows}


def trapezoid(series: dict[int, float], max_spacing: int) -> tuple[float, int]:
    times = sorted(series)
    areas, covered = [], 0
    for a, b in zip(times, times[1:], strict=False):
        if b - a <= max_spacing:
            areas.append((series[a] + series[b]) / 2 * (b - a))
            covered += b - a
    return math.fsum(areas), covered


def bridged(series: dict[int, float], max_spacing: int) -> list[tuple[int, int]]:
    times = sorted(series)
    out: list[tuple[int, int]] = []
    for a, b in zip(times, times[1:], strict=False):
        if b - a <= max_spacing:
            if out and out[-1][1] == a:
                out[-1] = (out[-1][0], b)
            else:
                out.append((a, b))
    return out


def intersect(x: list[tuple[int, int]], y: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for a0, a1 in x:
        for b0, b1 in y:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                out.append((lo, hi))
    return sorted(out)


def interpolated(series: dict[int, float], t: int) -> float:
    if t in series:
        return series[t]
    before = max(k for k in series if k < t)
    after = min(k for k in series if k > t)
    return series[before] + (series[after] - series[before]) * (t - before) / (after - before)


def integral_over(series: dict[int, float], intervals: list[tuple[int, int]]) -> float:
    areas = []
    for lo, hi in intervals:
        points = [lo, *[t for t in sorted(series) if lo < t < hi], hi]
        for a, b in zip(points, points[1:], strict=False):
            areas.append((interpolated(series, a) + interpolated(series, b)) / 2 * (b - a))
    return math.fsum(areas)


def as_of(series: dict[int, float], t: int, max_age: int = 120) -> float | None:
    earlier = [k for k in series if k <= t]
    if not earlier or t - max(earlier) > max_age:
        return None
    return series[max(earlier)]


def recompute(database: str) -> dict:
    volt, cur, power = pull(database, "voltage"), pull(database, "current"), pull(database, "power")
    co2_in, co2_out = pull(database, "co2_in_ppm"), pull(database, "co2_out_ppm")
    flow = pull(database, "air_flow")
    temp, pres = pull(database, "ambient_temperature"), pull(database, "ambient_pressure")

    computed = {t: volt[t] * cur[t] for t in volt if t in cur}
    residual = {t: power[t] - computed[t] for t in computed if t in power}
    within = sum(1 for t, r in residual.items() if abs(r) <= 0.01 * abs(computed[t]) + 10)

    energy, e_s = trapezoid(computed, 2)
    logged, l_s = trapezoid(power, 2)
    computed_cover, logged_cover = bridged(computed, 2), bridged(power, 2)
    both = intersect(computed_cover, logged_cover)
    e_c, e_l = integral_over(computed, both), integral_over(power, both)

    efficiency = {t: (co2_in[t] - co2_out[t]) / co2_in[t] for t in co2_in if t in co2_out}
    _, eff_s = trapezoid(efficiency, 4)

    molar, gas = 0.04401, 8.314462618
    rate: dict[int, float] = {}
    inlet: dict[int, float] = {}
    for t in sorted(efficiency):
        if t not in flow:
            continue
        a_temp, a_pres = as_of(temp, t), as_of(pres, t)
        if a_temp is None or a_pres is None:
            continue
        density = a_pres * 100 * molar / (gas * (a_temp + 273.15))
        rate[t] = flow[t] * (co2_in[t] - co2_out[t]) * 1e-6 * density
        inlet[t] = flow[t] * co2_in[t] * 1e-6 * density
    cap_ws, cap_s = trapezoid(rate, 4)
    inl_ws, _ = trapezoid(inlet, 4)
    captured = cap_ws / 3600
    shared = intersect(computed_cover, bridged(rate, 4))
    sec = (integral_over(computed, shared) / 3.6e6) / (integral_over(rate, shared) / 3600)

    return {
        "computed": computed,
        "residual": residual,
        "efficiency": efficiency,
        "rate": rate,
        "within": within,
        "metrics": {
            "energy_kwh": (energy / 3.6e6, e_s / DURATION),
            "energy_logged_kwh": (logged / 3.6e6, l_s / DURATION),
            "energy_relative_difference": (
                (e_l - e_c) / e_c,
                sum(b - a for a, b in both) / DURATION,
            ),
            "mean_power_kw": (energy / 3.6e6 / (e_s / 3600), e_s / DURATION),
            "capture_efficiency_mean": (
                math.fsum(efficiency.values()) / len(efficiency),
                eff_s / DURATION,
            ),
            "co2_captured_kg": (captured, cap_s / DURATION),
            "co2_inlet_kg": (inl_ws / 3600, cap_s / DURATION),
            "capture_rate_mean_kg_h": (captured / (cap_s / 3600), cap_s / DURATION),
            "sec_kwh_per_kg": (sec, sum(b - a for a, b in shared) / DURATION),
        },
    }


def counts_by_signal(database: str) -> dict[str, tuple[int, int, int, int]]:
    """present, accepted, bad, uncertain per signal from plain GROUP BY pulls of both tables."""
    out: dict[str, list[int]] = {}
    for table in ("readings_processed", "state_intervals"):
        rows = query(
            database,
            f"SELECT signal, quality, verdict, COUNT(*) AS n FROM {table} "
            "GROUP BY signal, quality, verdict",
        )
        for r in rows:
            entry = out.setdefault(r["signal"], [0, 0, 0, 0])
            entry[0] += r["n"]
            entry[1] += r["n"] if r["verdict"] == "accepted" else 0
            entry[2] += r["n"] if r["quality"] == "BAD" else 0
            entry[3] += r["n"] if r["quality"] == "UNCERTAIN" else 0
    return {k: tuple(v) for k, v in out.items()}


def test_every_fixture_metric_equals_an_independent_recompute_from_plain_pulls(ran):
    mine = recompute(ran["db"])
    entry = experiment(ran)
    for name, (value, coverage) in mine["metrics"].items():
        metric = entry["metrics"][name]
        assert metric["value"] == pytest.approx(value, rel=1e-8), name
        assert metric["coverage"] == pytest.approx(coverage, rel=1e-8), name
        # and the recompute itself agrees with the hand computation in README.md
        assert value == pytest.approx(EXPECTED_METRICS[name][0], rel=1e-9), name
    assert entry["power_check"]["within_tolerance"] == mine["within"] == 585
    for series, key in (
        ("power_computed", "computed"),
        ("power_residual", "residual"),
        ("capture_efficiency", "efficiency"),
        ("capture_rate", "rate"),
    ):
        stored = series_rows(ran["db"], series)
        assert set(stored) == set(mine[key]), series
        for k, value in stored.items():
            assert value == pytest.approx(mine[key][k], rel=1e-9, abs=1e-9), (series, k)
    # quality shares from plain GROUP BY pulls
    counts = counts_by_signal(ran["db"])
    present = sum(c[0] for c in counts.values())
    assert present == 2983
    shares = {
        "valid_fraction": sum(c[1] for c in counts.values()) / present,
        "bad_fraction": sum(c[2] for c in counts.values()) / present,
        "uncertain_fraction": sum(c[3] for c in counts.values()) / present,
    }
    for name, value in shares.items():
        assert entry["metrics"][name]["value"] == pytest.approx(value, rel=1e-8), name
    for signal, (n_present, n_accepted, n_bad, n_uncertain) in counts.items():
        s = next(x for x in entry["signals"] if x["signal"] == signal)
        assert (s["present"], s["accepted"], s["bad"], s["uncertain"]) == (
            n_present,
            n_accepted,
            n_bad,
            n_uncertain,
        ), signal
