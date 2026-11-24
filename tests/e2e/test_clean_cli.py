"""End-to-end cleaning: the real CLIs against a live InfluxDB (M3: S3.1-S3.20, S3.23, S3.25).

The fixture `tests/fixtures/clean/readings.csv` is built by `make_fixture.py` with defects
planted at stated instants (seconds after 2026-05-04T08:00:00Z, one experiment EXP_001 of
600 s). Noise is a fixed alternating +/- half the signal's normal step, so the expected
verdict of every reading follows from the construction. The verdicts below were written from
that construction, not from the rules:

  voltage          1 Hz. +120 s: 140.0, a spike. +300 s: steps 100 -> 110 V (kept). +400 s to
                   +409 s: no points (one gap +399 -> +410, 11 s). +500 s: 140.0 and BAD (reason
                   flag_bad, flags flag_bad and spike).
  current          1 Hz. +30 s: -0.5 A (kept, note outside_typical_range). +60 s: no value.
                   +100 s: step 0 -> 150 A. +200 s to +215 s: ramp 150 -> 210 A at 4 A/s (kept).
  current_setpoint 1 Hz, held 400 s at 210 from +200 s (exempt, kept).
  solvent_temperature  0.2 Hz. 30.22 from +100 s to +295 s, 40 readings (flatline). 31.0 at +20,
                   +25, +30 s: a run of 3 (kept).
  air_flow         1 Hz. From +360 s to the end, steps of 5 % of normal: 240 readings (flatline).
  solvent_pH       0.2 Hz. +250 s: 27.4 (outside physical limits, and not also a spike).
  pressure         1 Hz. +45 s: UNCERTAIN.
  conductivity     0.2 Hz. 10 BAD readings from +150 s to +195 s.
  available_solar_power  1/60 Hz, 0.0 x 10 (night, kept).
  co2_in_ppm       0.5 Hz. +80 s: a conflicting pair (415.55 kept, 420.55 discarded) ->
                   conflicting_duplicate. +90 s: an exact copy -> kept.
  process_state    STARTUP +0, STEADY_STATE +120, WARMUP +400 (unknown_state), SHUTDOWN +540:
                   intervals of 120, 280, 140 and 60 s. valve_state: OPEN +0, 600 s.

The rollup writes into the same throwaway database as the cleaning (`--rollup-database` = the same
name): Core allows 5 databases, the project's dev stack already holds 4, so a second throwaway
database would not fit. The rollup table is separate from the cleaning tables either way.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import UTC, datetime

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

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "clean"
EXPERIMENTS = FIXTURES / "experiments.json"
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "cleaning_summary.schema.json").read_text(encoding="utf-8")
)
POLICY_VERSION = "m3-v1"
START = datetime(2026, 5, 4, 8, 0, 0)
DURATION = 600

PAIRS = {
    "available_solar_power": "ambient",
    "air_flow": "absorber",
    "co2_in_ppm": "absorber",
    "solvent_temperature": "absorber",
    "solvent_pH": "absorber",
    "current_setpoint": "hydrolyzer",
    "current": "hydrolyzer",
    "voltage": "hydrolyzer",
    "conductivity": "hydrolyzer",
    "pressure": "hydrolyzer",
    "valve_state": "plant",
    "process_state": "plant",
}
STATE_SIGNALS = {"valve_state", "process_state"}

# ------------------------------------------------------------------ the construction, by hand


def offsets(signal: str) -> list[int]:
    """The instants (seconds after 08:00:00) at which the fixture has a reading."""
    if signal == "voltage":
        return [k for k in range(DURATION) if not 400 <= k <= 409]
    if signal in ("solvent_temperature", "solvent_pH", "conductivity"):
        return list(range(0, DURATION, 5))
    if signal == "co2_in_ppm":
        return list(range(0, DURATION, 2))
    if signal == "available_solar_power":
        return list(range(0, DURATION, 60))
    if signal == "process_state":
        return [0, 120, 400, 540]
    if signal == "valve_state":
        return [0]
    return list(range(DURATION))


EXPECTED_COUNTS = {
    "voltage": 590,
    "current": 600,
    "current_setpoint": 600,
    "solvent_temperature": 120,
    "air_flow": 600,
    "solvent_pH": 120,
    "pressure": 600,
    "conductivity": 120,
    "available_solar_power": 10,
    "co2_in_ppm": 300,
    "process_state": 4,
    "valve_state": 1,
}


def expected_verdict(signal: str, k: int) -> tuple[str, str]:
    """`(reason, flags)` of the reading of `signal` at +k s, from the planted defects."""
    if signal == "voltage":
        if k == 120:
            return "spike", "spike,outside_typical_range"
        if k == 500:
            return "flag_bad", "flag_bad,spike,outside_typical_range"
    elif signal == "current":
        if k == 30:
            return "", "outside_typical_range"
        if k == 60:
            return "no_value", "no_value"
    elif signal == "solvent_temperature":
        if 100 <= k <= 295:
            return "flatline", "flatline"
    elif signal == "air_flow":
        if k >= 360:
            return "flatline", "flatline,outside_typical_range"
    elif signal == "solvent_pH":
        if k == 250:
            return "outside_physical_limits", "outside_physical_limits,outside_typical_range"
    elif signal == "pressure":
        if k == 45:
            return "flag_uncertain", "flag_uncertain"
    elif signal == "conductivity":
        if 150 <= k <= 195:
            return "flag_bad", "flag_bad"
    elif signal == "co2_in_ppm":
        if k == 80:
            return "conflicting_duplicate", "conflicting_duplicate"
    elif signal == "process_state" and k == 400:
        return "unknown_state", "unknown_state"
    return "", ""


def expected_quality(signal: str, k: int) -> str:
    if (signal, k) in {("voltage", 500), ("pressure", 45)} | {
        ("conductivity", j) for j in range(150, 196, 5)
    }:
        return {"voltage": "BAD", "pressure": "UNCERTAIN", "conductivity": "BAD"}[signal]
    return "GOOD"


# Hand-written raw values from the construction (the rest are read from the committed CSV).
HAND_VALUES = {
    ("voltage", 0): 100.075,
    ("voltage", 1): 99.925,
    ("voltage", 120): 140.0,
    ("voltage", 300): 110.075,
    ("voltage", 500): 140.0,
    ("current", 30): -0.5,
    ("current", 60): None,
    ("current", 100): 150.15,
    ("current", 200): 150.0,
    ("current", 215): 210.0,
    ("current_setpoint", 99): 0.0,
    ("current_setpoint", 100): 150.0,
    ("current_setpoint", 599): 210.0,
    ("solvent_temperature", 20): 31.0,
    ("solvent_temperature", 25): 31.0,
    ("solvent_temperature", 30): 31.0,
    ("solvent_temperature", 100): 30.22,
    ("solvent_temperature", 295): 30.22,
    ("air_flow", 359): 1196.225,
    ("air_flow", 360): 20.18875,
    ("solvent_pH", 250): 27.4,
    ("co2_in_ppm", 80): 415.55,
    ("co2_in_ppm", 90): 414.45,
    ("available_solar_power", 0): 0.0,
    ("process_state", 400): "WARMUP",
}


def csv_values() -> dict[tuple[str, int], float | str | None]:
    """Raw value per (signal, offset) as ingest keeps it: of a conflicting pair, the smaller."""
    values: dict[tuple[str, int], float | str | None] = {}
    with (FIXTURES / "readings.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            at = datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
            key = (row["signal"], int((at - START).total_seconds()))
            text = row["value"]
            if row["signal"] in STATE_SIGNALS:
                value: float | str | None = text
            else:
                value = float(text) if text else None
            if key not in values or (
                isinstance(value, float) and isinstance(values[key], float) and value < values[key]
            ):
                values[key] = value
    return values


# ------------------------------------------------------------------ running the CLIs


def run_clean(database, report_dir, *extra) -> subprocess.CompletedProcess:
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
            *extra,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def run_rollup(database, rollup_database) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.rollup",
            "--database",
            database,
            "--rollup-database",
            rollup_database,
            "--experiments",
            str(EXPERIMENTS),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def clean_files() -> dict:
    return {
        "csv": FIXTURES / "readings.csv",
        "sha256": FIXTURES / "readings.sha256",
        "experiments": EXPERIMENTS,
    }


def offset_of(text: str) -> int:
    return int((datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S") - START).total_seconds())


def processed_dump(database: str) -> dict[str, list[dict]]:
    return {
        "readings_processed": query(
            database, "SELECT * FROM readings_processed ORDER BY experiment_id, signal, time"
        ),
        "state_intervals": query(
            database, "SELECT * FROM state_intervals ORDER BY experiment_id, signal, time"
        ),
        "quality_intervals": query(
            database, "SELECT * FROM quality_intervals ORDER BY experiment_id, signal, kind, time"
        ),
    }


def without_timing(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k != "timing"}


@pytest.fixture(scope="module")
def cleaned(module_db, tmp_path_factory):
    ingested = run_ingest(clean_files(), module_db, tmp_path_factory.mktemp("ingest"))
    assert ingested.returncode == 0, ingested.stderr + ingested.stdout
    raw_before = dump(module_db)
    first_dir = tmp_path_factory.mktemp("first")
    first = run_clean(module_db, first_dir)
    assert first.returncode == 0, first.stderr + first.stdout
    after_first = processed_dump(module_db)
    raw_after = dump(module_db)
    second_dir = tmp_path_factory.mktemp("second")
    second = run_clean(module_db, second_dir)
    assert second.returncode == 0, second.stderr + second.stdout
    after_second = processed_dump(module_db)
    return {
        "db": module_db,
        "dir": first_dir,
        "stdout": first.stdout,
        "summary": json.loads((first_dir / "cleaning_summary.json").read_text("utf-8")),
        "second_summary": json.loads((second_dir / "cleaning_summary.json").read_text("utf-8")),
        "raw_before": raw_before,
        "raw_after": raw_after,
        "after_first": after_first,
        "after_second": after_second,
        "tmp": tmp_path_factory,
    }


def rows_of(cleaned, signal: str) -> dict[int, dict]:
    table = "state_intervals" if signal in STATE_SIGNALS else "readings_processed"
    return {offset_of(r["time"]): r for r in cleaned["after_first"][table] if r["signal"] == signal}


def row(cleaned, signal: str, k: int) -> dict:
    return rows_of(cleaned, signal)[k]


# ------------------------------------------------------------------ S3.1 - S3.3: shape


def test_s3_1_every_reading_has_exactly_one_processed_row(cleaned):
    for signal, expected in EXPECTED_COUNTS.items():
        found = rows_of(cleaned, signal)
        assert len(found) == expected, signal
        assert sorted(found) == offsets(signal), signal
    total_rows = len(cleaned["after_first"]["readings_processed"]) + len(
        cleaned["after_first"]["state_intervals"]
    )
    assert total_rows == sum(EXPECTED_COUNTS.values()) == 3665
    summary = cleaned["summary"]
    for series in summary["series"]:
        assert series["raw_points"] == EXPECTED_COUNTS[series["signal"]]
        assert series["processed_points"] == series["raw_points"]
    assert summary["totals"]["raw_points"] == summary["totals"]["processed_points"] == 3665
    raw = cleaned["raw_before"]
    assert len(raw["readings_numeric"]) + len(raw["readings_state"]) == 3665


def test_s3_2_raw_values_are_copied_and_accepted_values_are_not_altered(cleaned):
    values = csv_values()
    for key, hand in HAND_VALUES.items():
        assert values[key] == hand, key
    for signal in PAIRS:
        for k, r in rows_of(cleaned, signal).items():
            assert r["value_raw"] == values[(signal, k)], (signal, k)
            assert r["quality"] == expected_quality(signal, k), (signal, k)
            if r["verdict"] == "accepted":
                assert r["value"] == r["value_raw"], (signal, k)


def test_s3_3_excluded_rows_have_no_value_and_a_reason(cleaned):
    excluded = accepted = 0
    for signal in PAIRS:
        for r in rows_of(cleaned, signal).values():
            if r["verdict"] == "excluded":
                excluded += 1
                assert r["value"] is None
                assert r["reason"] != ""
            else:
                accepted += 1
                assert r["verdict"] == "accepted"
                assert r["reason"] == ""
                assert r["value"] is not None
    assert (accepted, excluded) == (3368, 297)


# ------------------------------------------------------------------ S3.4 - S3.14: the rules


def test_s3_4_bad_and_uncertain_readings_are_excluded(cleaned):
    for k in range(150, 200, 5):
        r = row(cleaned, "conductivity", k)
        assert (r["reason"], r["quality"], r["value"]) == ("flag_bad", "BAD", None)
    assert row(cleaned, "conductivity", 145)["verdict"] == "accepted"
    assert row(cleaned, "conductivity", 200)["verdict"] == "accepted"
    r = row(cleaned, "pressure", 45)
    assert (r["reason"], r["quality"], r["value"]) == ("flag_uncertain", "UNCERTAIN", None)
    assert row(cleaned, "pressure", 44)["verdict"] == "accepted"


def test_s3_5_a_point_without_a_value_is_excluded(cleaned):
    r = row(cleaned, "current", 60)
    assert r["value_raw"] is None and r["value"] is None
    assert (r["reason"], r["flags"], r["verdict"]) == ("no_value", "no_value", "excluded")
    assert (
        row(cleaned, "current", 59)["verdict"]
        == row(cleaned, "current", 61)["verdict"]
        == "accepted"
    )


def test_s3_6_a_value_outside_physical_limits_is_excluded_and_not_a_spike(cleaned):
    r = row(cleaned, "solvent_pH", 250)
    assert r["reason"] == "outside_physical_limits"
    assert "spike" not in r["flags"].split(",")
    assert r["value_raw"] == 27.4 and r["value"] is None
    assert row(cleaned, "solvent_pH", 245)["verdict"] == "accepted"
    assert row(cleaned, "solvent_pH", 255)["verdict"] == "accepted"


def test_s3_7_outside_the_typical_range_is_kept_with_a_note(cleaned):
    r = row(cleaned, "current", 30)
    assert (r["verdict"], r["value"], r["flags"], r["reason"]) == (
        "accepted",
        -0.5,
        "outside_typical_range",
        "",
    )


def test_s3_8_a_single_spike_is_excluded_and_its_neighbours_are_kept(cleaned):
    r = row(cleaned, "voltage", 120)
    assert (r["reason"], r["value_raw"], r["value"]) == ("spike", 140.0, None)
    for k in range(115, 126):
        if k != 120:
            assert row(cleaned, "voltage", k)["verdict"] == "accepted", k


def test_s3_9_a_step_and_a_ramp_are_not_spikes(cleaned):
    def flags(signal, k):
        return row(cleaned, signal, k)["flags"].split(",")

    for k in range(290, 311):
        assert "spike" not in flags("voltage", k), k
    for k in list(range(95, 106)) + list(range(195, 221)):
        assert "spike" not in flags("current", k), k
        assert row(cleaned, "current", k)["verdict"] == "accepted", k
    assert row(cleaned, "voltage", 300)["value"] == 110.075
    assert row(cleaned, "current", 100)["value"] == 150.15
    assert row(cleaned, "current", 210)["value"] == 190.0


def test_s3_10_an_exact_run_is_a_flatline_and_a_short_run_is_not(cleaned):
    flat = sorted(
        k
        for k, r in rows_of(cleaned, "solvent_temperature").items()
        if "flatline" in r["flags"].split(",")
    )
    assert flat == list(range(100, 296, 5))
    assert len(flat) == 40
    for k in (20, 25, 30):
        r = row(cleaned, "solvent_temperature", k)
        assert (r["value_raw"], r["verdict"], r["flags"]) == (31.0, "accepted", "")
    intervals = [
        r
        for r in cleaned["after_first"]["quality_intervals"]
        if r["signal"] == "solvent_temperature"
    ]
    assert len(intervals) == 1
    assert (intervals[0]["kind"], intervals[0]["points"], intervals[0]["seconds"]) == (
        "flatline",
        40,
        195.0,
    )
    assert offset_of(intervals[0]["time"]) == 100
    start_ns = int(datetime(2026, 5, 4, 8, 0, tzinfo=UTC).timestamp()) * 10**9
    assert intervals[0]["end_ns"] == start_ns + 295 * 10**9


def test_s3_11_collapsed_noise_is_a_flatline_with_a_sharp_boundary(cleaned):
    found = rows_of(cleaned, "air_flow")
    for k in range(360, DURATION):
        assert found[k]["reason"] == "flatline", k
        assert found[k]["value"] is None
    for k in range(360):
        assert "flatline" not in found[k]["flags"].split(","), k
        assert found[k]["verdict"] == "accepted", k
    run = [r for r in cleaned["after_first"]["quality_intervals"] if r["signal"] == "air_flow"]
    assert [(r["kind"], r["points"], offset_of(r["time"])) for r in run] == [("flatline", 240, 360)]


def test_s3_12_a_setpoint_hold_and_solar_zeros_are_not_flatlines(cleaned):
    for signal in ("current_setpoint", "available_solar_power"):
        found = rows_of(cleaned, signal)
        assert len(found) == EXPECTED_COUNTS[signal]
        for k, r in found.items():
            assert (r["verdict"], r["reason"], r["flags"]) == ("accepted", "", ""), (signal, k)
            assert r["value"] == r["value_raw"]
    assert row(cleaned, "current_setpoint", 250)["value"] == 210.0
    assert row(cleaned, "available_solar_power", 300)["value"] == 0.0


def test_s3_13_a_conflicting_duplicate_is_excluded_and_an_exact_copy_is_not(cleaned):
    conflicts = cleaned["raw_before"]["readings_conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["signal"] == "co2_in_ppm" and offset_of(conflicts[0]["time"]) == 80
    r = row(cleaned, "co2_in_ppm", 80)
    assert (r["reason"], r["flags"], r["value_raw"], r["value"]) == (
        "conflicting_duplicate",
        "conflicting_duplicate",
        415.55,
        None,
    )
    r = row(cleaned, "co2_in_ppm", 90)
    assert (r["verdict"], r["value"], r["flags"]) == ("accepted", 414.45, "")


def test_s3_14_priority_picks_the_first_reason_and_flags_list_them_all(cleaned):
    r = row(cleaned, "voltage", 500)
    assert r["reason"] == "flag_bad"
    assert r["quality"] == "BAD"
    flags = r["flags"].split(",")
    assert "flag_bad" in flags and "spike" in flags
    assert r["flags"] == "flag_bad,spike,outside_typical_range"


def test_every_verdict_matches_the_construction(cleaned):
    """A SELECT-pull recompute of every row, independent of `pipeline.cleaning`."""
    mismatches = []
    checked = 0
    for signal in PAIRS:
        found = rows_of(cleaned, signal)
        for k in offsets(signal):
            reason, flags = expected_verdict(signal, k)
            r = found[k]
            got = (r["reason"], r["flags"], r["verdict"])
            want = (reason, flags, "excluded" if reason else "accepted")
            checked += 1
            if got != want:
                mismatches.append((signal, k, got, want))
    assert checked == 3665
    assert mismatches == []
    # The summary's per-reason counts agree with the same construction.
    expected_by_reason: dict[str, int] = {}
    for signal in PAIRS:
        for k in offsets(signal):
            reason = expected_verdict(signal, k)[0]
            if reason:
                expected_by_reason[reason] = expected_by_reason.get(reason, 0) + 1
    totals = cleaned["summary"]["totals"]["excluded_by_reason"]
    assert {code: n for code, n in totals.items() if n} == expected_by_reason
    assert expected_by_reason == {
        "no_value": 1,
        "flag_bad": 11,
        "flag_uncertain": 1,
        "outside_physical_limits": 1,
        "unknown_state": 1,
        "conflicting_duplicate": 1,
        "spike": 1,
        "flatline": 280,
    }


# ------------------------------------------------------------------ S3.15, S3.16: intervals


def test_s3_15_a_gap_is_recorded_and_nothing_is_invented(cleaned):
    gaps = [r for r in cleaned["after_first"]["quality_intervals"] if r["kind"] == "gap"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["signal"] == "voltage"
    assert offset_of(gap["time"]) == 399
    assert gap["seconds"] == 11.0 and gap["points"] == 0
    start_ns = int(datetime(2026, 5, 4, 8, 0, tzinfo=UTC).timestamp()) * 10**9
    assert gap["end_ns"] == start_ns + 410 * 10**9
    found = rows_of(cleaned, "voltage")
    assert [k for k in range(400, 410) if k in found] == []
    assert 399 in found and 410 in found
    assert not [
        r for r in cleaned["after_first"]["quality_intervals"] if r["signal"] in STATE_SIGNALS
    ]
    summary_gaps = {
        s["signal"]: s["gaps"] for s in cleaned["summary"]["series"] if s["gaps"] is not None
    }
    assert summary_gaps["voltage"]["count"] == 1
    assert summary_gaps["voltage"]["seconds"] == 11.0
    assert sum(g["count"] for g in summary_gaps.values()) == 1
    states = [s for s in cleaned["summary"]["series"] if s["signal"] in STATE_SIGNALS]
    assert len(states) == 2 and all(s["gaps"] is None for s in states)


def test_s3_16_state_events_are_carried_forward_without_expiry(cleaned):
    found = rows_of(cleaned, "process_state")
    assert [found[k]["seconds"] for k in (0, 120, 400, 540)] == [120.0, 280.0, 140.0, 60.0]
    assert [found[k]["value_raw"] for k in (0, 120, 400, 540)] == [
        "STARTUP",
        "STEADY_STATE",
        "WARMUP",
        "SHUTDOWN",
    ]
    warmup = found[400]
    assert (warmup["reason"], warmup["value"], warmup["verdict"]) == (
        "unknown_state",
        None,
        "excluded",
    )
    for k in (0, 120, 540):
        assert found[k]["verdict"] == "accepted" and found[k]["value"] == found[k]["value_raw"]
    start_ns = int(datetime(2026, 5, 4, 8, 0, tzinfo=UTC).timestamp()) * 10**9
    assert found[540]["end_ns"] == start_ns + 600 * 10**9  # the last event lasts to the end
    assert rows_of(cleaned, "valve_state")[0]["seconds"] == 600.0


# ------------------------------------------------------------------ S3.17 - S3.19, S3.23


def test_s3_17_the_summary_reconciles_every_series(cleaned):
    summary = cleaned["summary"]
    assert summary["policy_version"] == POLICY_VERSION
    assert len(summary["series"]) == 12
    for series in summary["series"]:
        assert series["raw_points"] == series["accepted"] + series["excluded"]
        assert series["excluded"] == sum(series["excluded_by_reason"].values())
        assert series["table"] == (
            "readings_state" if series["signal"] in STATE_SIGNALS else "readings_numeric"
        )
    assert summary["reconciliation"]["balanced"] is True
    assert summary["reconciliation"]["raw_unchanged"] is True
    assert summary["reconciliation"]["series_checked"] == 12
    assert summary["reconciliation"]["unbalanced"] == []
    assert summary["totals"]["accepted"] + summary["totals"]["excluded"] == 3665
    by_signal = {s["signal"]: s for s in summary["series"]}
    assert by_signal["voltage"]["excluded_by_reason"]["spike"] == 1
    assert by_signal["voltage"]["flags"]["outside_typical_range"] == 2
    assert by_signal["air_flow"]["flatline_intervals"] == {"count": 1, "seconds": 239.0}
    assert by_signal["current_setpoint"]["flatline_intervals"] is None
    report = (cleaned["dir"] / "cleaning_report.md").read_text(encoding="utf-8")
    for code in ("no_value", "flag_bad", "spike", "flatline", "unknown_state"):
        assert code in report
    assert "balanced" in cleaned["stdout"]


def test_s3_18_the_raw_tables_are_not_changed_by_cleaning(cleaned):
    assert cleaned["raw_before"] == cleaned["raw_after"]
    present = tables(cleaned["db"])
    assert {"readings_processed", "state_intervals", "quality_intervals"} <= set(present)


def test_s3_19_a_second_run_gives_the_same_result(cleaned):
    assert cleaned["after_first"] == cleaned["after_second"]
    assert without_timing(cleaned["summary"]) == without_timing(cleaned["second_summary"])
    assert dump(cleaned["db"]) == cleaned["raw_before"]


def test_s3_23_the_summary_matches_the_contract(cleaned):
    jsonschema.Draft202012Validator(SCHEMA).validate(cleaned["summary"])
    jsonschema.Draft202012Validator(SCHEMA).validate(cleaned["second_summary"])
    example = json.loads(
        (REPO_ROOT / "contracts" / "examples" / "cleaning_summary.example.json").read_text("utf-8")
    )
    assert set(cleaned["summary"]) == set(example)
    # 3665 readings, 3 rows for the 2 gaps/flatline runs of the fixture: 1 gap + 2 flatline runs.
    assert cleaned["summary"]["timing"]["points_written"] == 3665 + 3


# ------------------------------------------------------------------ S3.20: refused


def test_s3_20_a_missing_database_is_refused_not_created(cleaned, tmp_path):
    report_dir = tmp_path / "refused"
    report_dir.mkdir()
    result = run_clean("dac_missing", report_dir)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "database_missing" in result.stderr
    assert list(report_dir.iterdir()) == []
    assert "dac_missing" not in database_names()


def test_exit_2_when_the_experiments_file_is_unreadable(cleaned, tmp_path):
    report_dir = tmp_path / "refused"
    report_dir.mkdir()
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.clean",
            "--database",
            cleaned["db"],
            "--experiments",
            str(tmp_path / "nope.json"),
            "--report-dir",
            str(report_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 2
    assert list(report_dir.iterdir()) == []


# ------------------------------------------------------------------ S3.25: rollup


@pytest.fixture(scope="module")
def rolled_up(cleaned):
    first = run_rollup(cleaned["db"], cleaned["db"])
    assert first.returncode == 0, first.stderr + first.stdout
    return {
        "stdout": first.stdout,
        "voltage": query(
            cleaned["db"],
            "SELECT * FROM readings_rollup WHERE signal = 'voltage' ORDER BY time",
        ),
        "current": query(
            cleaned["db"],
            "SELECT * FROM readings_rollup WHERE signal = 'current' ORDER BY time",
        ),
    }


def test_s3_25_the_rollup_aggregates_over_the_verdict(rolled_up):
    buckets = {offset_of(r["time"]): r for r in rolled_up["voltage"]}
    assert sorted(buckets) == [60 * m for m in range(10)]
    bucket = buckets[120]  # 08:02:00, readings +120 s .. +179 s
    # All 60 raw values: 99.925 / 100.075 alternating, and the spike 140.0 at +120 s.
    assert bucket["count_all"] == 60
    assert bucket["min_all"] == 99.925
    assert bucket["max_all"] == 140.0
    assert bucket["count_no_value"] == 0
    assert bucket["policy_version"] == POLICY_VERSION
    # Accepted: everything but the spike. Odd offsets 121..179 are 99.925 (30 values), even
    # offsets 122..178 are 100.075 (29 values).
    assert bucket["count_included"] == 59
    expected_mean = (30 * 99.925 + 29 * 100.075) / 59
    assert bucket["mean"] == pytest.approx(expected_mean, abs=1e-9)
    assert bucket["sum_all"] == pytest.approx(30 * 99.925 + 29 * 100.075 + 140.0, abs=1e-6)
    assert (bucket["count_good"], bucket["count_uncertain"], bucket["count_bad"]) == (60, 0, 0)
    # +500 s is BAD and 140.0: it is in count_all, not in the included statistics.
    last = buckets[480]  # +480 .. +539: the BAD 140.0 at +500
    assert (last["count_all"], last["count_included"], last["count_bad"]) == (60, 59, 1)
    assert last["max_all"] == 140.0


def test_s3_25_a_point_without_a_value_is_counted_not_dropped(rolled_up):
    buckets = {offset_of(r["time"]): r for r in rolled_up["current"]}
    bucket = buckets[60]  # +60 .. +119 holds the point with no value at +60 s
    assert bucket["count_no_value"] == 1
    assert bucket["count_all"] == 59
    assert bucket["count_included"] == 59
