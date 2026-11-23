"""End-to-end profile: the real CLI against a live InfluxDB (M2.5 scenarios S25.1-S25.19).

The fixture `tests/fixtures/profile/readings.csv` is hand-built, with defects planted on purpose:
two experiments two months apart, each with a 2-minute window. The numbers below were worked out
from how the file was built, before any profile was looked at:

EXP_001, seconds k = 0..119 after 08:00:00Z:
  voltage        k = 0..119 except 50..59 (10 missing) -> 110 points. 100 + (k % 7), except
                 k = 20..29 = 81.0 (a run of 10) and k = 90 = 140.0. k = 100 is UNCERTAIN.
  current_setpoint  all 120, random integers 140..160 (seeded).
  current        k = 3..119 (117 points), equal to the setpoint of k - 3, i.e. delayed 3 s.
                 k = 70 has no value and quality BAD.
  power          all 120. V x I where voltage and current both have a value (106 instants, k = 80
                 is 500 higher); 1000.0 at the other 14.
  air_flow       k = 0..119 except 10 and 12 -> 118 points, 1000 + 100 * (k % 16).
  co2_in_ppm / co2_out_ppm / pressure_drop   every 2 s, 60 points each. out = 0.25 x in except
                 the 31st (450.0 > in 400.0). pressure_drop = 0.00001 x air_flow(t)^2.
  solvent_pH     every 5 s, 24 points, 7.00 / 7.02 alternating.
  process_state  3 rows (STARTUP 0 s, STEADY_STATE 40 s, SHUTDOWN 90 s).
  ambient_temperature  10:00:00 and 10:01:00 stamped +02:00 -> 08:00:00Z and 08:01:00Z.
EXP_004 (2026-03-02): voltage 60 points (1 Hz), ambient_temperature 2, process_state 1.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime

import jsonschema
import pytest

from tests.e2e.helpers import (
    REPO_ROOT,
    database_names,
    dump,
    query,
    run_ingest,
    tables,
)

pytestmark = pytest.mark.influx

PROFILE_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "profile"
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "post_ingest_profile.schema.json").read_text(encoding="utf-8")
)
VERDICT_WORDS = re.compile(
    r"stuck|suspicious|anomal|outlier|invalid|corrupt|error|wrong|fail|noise", re.IGNORECASE
)

EXPECTED_POINTS_EXP_001 = {
    ("hydrolyzer", "current_setpoint"): 120,
    ("hydrolyzer", "voltage"): 110,
    ("hydrolyzer", "current"): 117,
    ("hydrolyzer", "power"): 120,
    ("absorber", "air_flow"): 118,
    ("absorber", "co2_in_ppm"): 60,
    ("absorber", "co2_out_ppm"): 60,
    ("absorber", "pressure_drop"): 60,
    ("absorber", "solvent_pH"): 24,
    ("plant", "process_state"): 3,
    ("ambient", "ambient_temperature"): 2,
}
EXPECTED_POINTS_EXP_004 = {
    ("hydrolyzer", "voltage"): 60,
    ("ambient", "ambient_temperature"): 2,
    ("plant", "process_state"): 1,
}


def profile_files() -> dict:
    return {
        "csv": PROFILE_FIXTURES / "readings.csv",
        "sha256": PROFILE_FIXTURES / "readings.sha256",
        "experiments": PROFILE_FIXTURES / "experiments.json",
    }


def fixture_pairs_power() -> tuple[list[float], list[float]]:
    """`(voltage x current, power)` at every EXP_001 instant where all three have a value."""
    by_signal: dict[str, dict[str, float]] = {"voltage": {}, "current": {}, "power": {}}
    with (PROFILE_FIXTURES / "readings.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["experiment_id"] == "EXP_001" and row["signal"] in by_signal and row["value"]:
                by_signal[row["signal"]][row["timestamp"]] = float(row["value"])
    instants = sorted(set.intersection(*(set(d) for d in by_signal.values())))
    x = [by_signal["voltage"][t] * by_signal["current"][t] for t in instants]
    return x, [by_signal["power"][t] for t in instants]


def run_profile(database, report_dir, *extra) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.post_ingest_profile",
            "--database",
            database,
            "--experiments",
            str(PROFILE_FIXTURES / "experiments.json"),
            "--report-dir",
            str(report_dir),
            *extra,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def without_timing(profile: dict) -> dict:
    return {k: v for k, v in profile.items() if k != "timing"}


@pytest.fixture(scope="module")
def profiled(module_db, tmp_path_factory):
    ingest_dir = tmp_path_factory.mktemp("ingest")
    ingested = run_ingest(profile_files(), module_db, ingest_dir)
    assert ingested.returncode == 0, ingested.stderr + ingested.stdout
    before = dump(module_db)
    first_dir = tmp_path_factory.mktemp("first")
    first = run_profile(module_db, first_dir)
    assert first.returncode == 0, first.stderr + first.stdout
    return {
        "db": module_db,
        "dir": first_dir,
        "stdout": first.stdout,
        "before": before,
        "profile": json.loads((first_dir / "post_ingest_profile.json").read_text("utf-8")),
        "tmp": tmp_path_factory,
    }


def series(profiled, experiment, signal) -> dict:
    found = [
        s
        for s in profiled["profile"]["series"]
        if s["experiment_id"] == experiment and s["signal"] == signal
    ]
    assert len(found) == 1, f"{experiment} {signal}: {len(found)} series"
    return found[0]


def relation(profiled, experiment, kind) -> dict:
    found = [
        r
        for r in profiled["profile"]["relationships"]
        if r["experiment_id"] == experiment and r["kind"] == kind
    ]
    assert len(found) == 1
    return found[0]


def test_intervals_are_measured_against_the_nominal_rate(profiled):  # S25.1
    voltage = series(profiled, "EXP_001", "voltage")
    intervals = voltage["intervals_s"]
    assert voltage["points"] == 110 and voltage["nominal_interval_s"] == 1
    assert (intervals["count"], intervals["min"], intervals["median"], intervals["max"]) == (
        109,
        1,
        1,
        11,
    )
    assert intervals["p95"] == 1
    assert (intervals["over_2x_nominal"], intervals["over_10x_nominal"]) == (1, 1)
    assert intervals["seconds_in_over_2x"] == 11
    assert intervals["longest"][0] == {
        "start": "2026-05-04T08:00:49Z",
        "end": "2026-05-04T08:01:00Z",
        "seconds": 11,
    }
    assert len(intervals["longest"]) == 5


def test_on_change_signals_get_interval_stats_but_no_nominal_counts(profiled):  # S25.2
    state = series(profiled, "EXP_001", "process_state")
    intervals = state["intervals_s"]
    assert state["table"] == "readings_state" and state["nominal_interval_s"] is None
    assert intervals["count"] == 2 and (intervals["min"], intervals["max"]) == (40, 50)
    assert intervals["median"] == 45
    assert intervals["over_2x_nominal"] is None
    assert intervals["over_10x_nominal"] is None and intervals["seconds_in_over_2x"] is None
    assert state["states"] == {"SHUTDOWN": 1, "STARTUP": 1, "STEADY_STATE": 1}
    assert state["values"] is None and state["differences"] is None


def test_an_offset_stamp_shows_the_60_second_interval(profiled):  # S25.3
    ambient = series(profiled, "EXP_001", "ambient_temperature")
    assert ambient["points"] == 2 and ambient["nominal_interval_s"] == 60
    assert ambient["intervals_s"]["count"] == 1 and ambient["intervals_s"]["median"] == 60
    assert ambient["intervals_s"]["longest"][0]["start"] == "2026-05-04T08:00:00Z"
    assert ambient["intervals_s"]["over_2x_nominal"] == 0


def test_runs_of_identical_values_are_measured(profiled):  # S25.4
    runs = series(profiled, "EXP_001", "voltage")["runs"]
    # 110 points, one 10-point run: 110 - 9 = 101 runs; the other 100 are single readings.
    assert runs["count"] == 101 and runs["median_samples"] == 1
    assert (runs["max_samples"], runs["max_seconds"]) == (10, 9)
    assert runs["longest"][0] == {
        "start": "2026-05-04T08:00:20Z",
        "end": "2026-05-04T08:00:29Z",
        "samples": 10,
        "seconds": 9,
        "value": 81.0,
    }


def test_values_outside_the_documented_range_are_counted_not_labelled(profiled):  # S25.5
    voltage = series(profiled, "EXP_001", "voltage")
    values = voltage["values"]
    assert (voltage["documented_min"], voltage["documented_max"], voltage["unit"]) == (60, 130, "V")
    assert values["max"] == 140.0 and values["min"] == 81.0
    assert values["above_documented_max"] == 1 and values["below_documented_min"] == 0
    assert voltage["quality"] == {"GOOD": 109, "UNCERTAIN": 1, "BAD": 0}
    co2_out = series(profiled, "EXP_001", "co2_out_ppm")["values"]
    assert co2_out["max"] == 450.0 and co2_out["above_documented_max"] == 1


def test_a_reading_with_no_value_is_counted(profiled):  # S25.6
    current = series(profiled, "EXP_001", "current")
    assert current["points"] == 117 and current["points_without_value"] == 1
    assert current["quality"] == {"GOOD": 116, "UNCERTAIN": 0, "BAD": 1}
    assert current["differences"]["count"] == 115  # 116 valued points -> 115 steps


def test_step_to_step_change_is_measured(profiled):  # S25.7
    ph = series(profiled, "EXP_001", "solvent_pH")
    assert ph["points"] == 24 and ph["nominal_interval_s"] == 5
    assert ph["intervals_s"]["median"] == 5 and ph["intervals_s"]["over_2x_nominal"] == 0
    differences = ph["differences"]
    assert differences["count"] == 23
    assert differences["median_abs"] == 0.02 and differences["max_abs"] == 0.02
    assert differences["p95_abs"] == 0.02
    # 12 steps of +0.02 and 11 of -0.02 (the series starts low and ends high).
    assert differences["mean"] == pytest.approx(0.02 / 23, rel=1e-6)


def test_power_is_checked_against_voltage_times_current(profiled):  # S25.8
    power = relation(profiled, "EXP_001", "power_vs_voltage_x_current")
    # Voltage and current both have a value at 106 of the 120 power instants; 14 do not.
    assert (power["instants_matched"], power["instants_unmatched"]) == (106, 14)
    assert power["residual_median"] == 0 and power["residual_max_abs"] == 500
    assert power["residual_p05"] == 0 and power["residual_p95"] == 0
    assert power["residual_mean"] == pytest.approx(500 / 106, rel=1e-6)
    assert power["relative_residual_median"] == 0 and power["power_zero_instants"] == 0
    # The fit, recomputed from the CSV itself with the standard library.
    x, y = fixture_pairs_power()
    slope, intercept = statistics.linear_regression(x, y)
    assert len(x) == 106
    assert power["corr"] == pytest.approx(statistics.correlation(x, y), rel=1e-8)
    assert power["slope"] == pytest.approx(slope, rel=1e-8)
    assert power["intercept"] == pytest.approx(intercept, rel=1e-6, abs=1e-6)
    assert power["r2"] == pytest.approx(statistics.correlation(x, y) ** 2, rel=1e-8)


def test_outlet_co2_is_compared_with_inlet_co2(profiled):  # S25.9
    co2 = relation(profiled, "EXP_001", "co2_out_vs_co2_in")
    assert (co2["instants_matched"], co2["instants_unmatched"]) == (60, 0)
    assert co2["ratio_median"] == 0.25 and co2["ratio_p05"] == 0.25
    assert co2["ratio_p95"] == 0.25
    assert co2["out_at_or_above_in"] == 1


def test_the_lag_of_current_behind_its_setpoint_is_found(profiled):  # S25.10
    current = relation(profiled, "EXP_001", "current_vs_current_setpoint")
    assert current["best_lag_s"] == 3 and current["corr_at_best_lag"] == 1.0
    # 116 valued current points all have a setpoint at the same instant; one point has no value.
    assert (current["instants_matched"], current["instants_unmatched"]) == (116, 1)
    assert 0 <= current["difference_max_abs"] <= 20
    assert abs(current["corr"]) < 0.5  # at zero shift the two are not the same curve


def test_pressure_drop_follows_air_flow_squared(profiled):  # S25.11
    drop = relation(profiled, "EXP_001", "pressure_drop_vs_air_flow")
    # 60 pressure_drop points; air_flow is missing at two of those instants.
    assert (drop["instants_matched"], drop["instants_unmatched"]) == (58, 2)
    assert drop["r2_air_flow_sq"] == 1.0
    assert drop["r2_air_flow"] < 0.99
    assert drop["slope_air_flow_sq"] == pytest.approx(1e-5, rel=1e-8)
    assert drop["intercept_air_flow_sq"] == pytest.approx(0, abs=1e-8)


def test_each_experiment_is_profiled_on_its_own(profiled):  # S25.12
    found = {
        (s["experiment_id"], s["source"], s["signal"]): s["points"]
        for s in profiled["profile"]["series"]
    }
    expected = {("EXP_001", *pair): n for pair, n in EXPECTED_POINTS_EXP_001.items()}
    expected |= {("EXP_004", *pair): n for pair, n in EXPECTED_POINTS_EXP_004.items()}
    assert found == expected
    for experiment in ("EXP_001", "EXP_004"):
        for kind in (
            "power_vs_voltage_x_current",
            "co2_out_vs_co2_in",
            "current_vs_current_setpoint",
            "pressure_drop_vs_air_flow",
        ):
            relation(profiled, experiment, kind)  # four per experiment
    empty = relation(profiled, "EXP_004", "power_vs_voltage_x_current")
    assert (empty["instants_matched"], empty["instants_unmatched"], empty["corr"]) == (0, 0, None)
    assert series(profiled, "EXP_004", "voltage")["runs"]["max_samples"] == 1


def test_the_full_span_probe_is_recorded_when_it_succeeds(profiled):  # S25.13
    probe = profiled["profile"]["span_probe"]
    # numeric points: EXP_001 794 - 3 text = 791, EXP_004 60 + 2 = 62
    assert probe["succeeded"] is True and probe["count"] == 853
    assert probe["sum_of_per_experiment_counts"] == 853 and probe["message_file"] is None
    assert (probe["start"], probe["end"]) == ("2026-03-02T08:00:00Z", "2026-05-04T08:02:00Z")
    assert not (profiled["dir"] / "post_ingest_profile_span_probe.txt").exists()


def test_a_missing_database_is_refused_and_not_created(profiled, tmp_path):  # S25.15
    result = run_profile("dac_missing_m25", tmp_path / "out")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "database_missing" in result.stderr
    assert not (tmp_path / "out").exists()
    assert "dac_missing_m25" not in database_names()


def test_no_verdict_words_in_the_output(profiled):  # S25.17
    for name in ("post_ingest_profile.json", "post_ingest_profile.md"):
        text = (profiled["dir"] / name).read_text(encoding="utf-8")
        assert not VERDICT_WORDS.search(text), VERDICT_WORDS.search(text)


def test_a_second_run_gives_the_same_profile(profiled, tmp_path):  # S25.18
    again = run_profile(profiled["db"], tmp_path)
    assert again.returncode == 0, again.stderr
    second = json.loads((tmp_path / "post_ingest_profile.json").read_text("utf-8"))
    assert without_timing(second) == without_timing(profiled["profile"])
    assert second["timing"]["queries"] == profiled["profile"]["timing"]["queries"]


def test_the_output_matches_the_contract(profiled):  # S25.19
    jsonschema.validate(profiled["profile"], SCHEMA)
    assert (profiled["dir"] / "post_ingest_profile.md").read_text("utf-8").startswith("# ")


def test_the_profile_changes_nothing_in_the_database(profiled):  # M2.5 is read-only
    assert dump(profiled["db"]) == profiled["before"]
    assert tables(profiled["db"]) == ["readings_numeric", "readings_state"]


def test_voltage_agrees_with_an_independent_pull(profiled):  # cross-check, as S25.21 on the fixture
    rows = query(
        profiled["db"],
        "SELECT time, value FROM readings_numeric WHERE experiment_id = 'EXP_001' "
        "AND signal = 'voltage' AND time >= '2026-05-04T08:00:00Z' "
        "AND time < '2026-05-04T08:02:00Z' ORDER BY time",
    )
    times = [datetime.fromisoformat(r["time"]).timestamp() for r in rows]
    values = [r["value"] for r in rows]
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    longest_run = current = 1
    for before, after in zip(values, values[1:], strict=False):
        current = current + 1 if after == before else 1
        longest_run = max(longest_run, current)
    voltage = series(profiled, "EXP_001", "voltage")
    assert voltage["points"] == len(rows)
    assert voltage["values"]["min"] == min(values) and voltage["values"]["max"] == max(values)
    assert voltage["values"]["median"] == statistics.median(values)
    assert voltage["intervals_s"]["median"] == statistics.median(gaps)
    assert voltage["runs"]["max_samples"] == longest_run
