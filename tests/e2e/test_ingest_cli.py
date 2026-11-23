"""End-to-end ingest: the real CLI against a live InfluxDB (M2 scenarios S2.5-S2.27).

The numbers in `EXPECTED` were worked out by hand from `tests/fixtures/ingest/slice.csv`
(36 data rows) before the code ran, row by row; see the comments next to each.
"""

from __future__ import annotations

import csv
import json
import uuid

import jsonschema
import pytest
from influxdb_client_3 import InfluxDBClient3

import scripts.init_influx as init_influx
from tests.e2e.helpers import (
    REPO_ROOT,
    create_database,
    database_names,
    drop_database,
    dump,
    fixture_files,
    query,
    read_summary,
    run_ingest,
    tables,
    write_input,
)

pytestmark = pytest.mark.influx

SCHEMA = json.loads((REPO_ROOT / "contracts" / "ingest_summary.schema.json").read_text("utf-8"))

# 36 rows = 21 saved (18 numeric + 3 state) + 1 copy + 6 conflict losers + 8 rejected.
EXPECTED = {"csv_rows": 36, "saved": 21, "exact_copies": 1, "conflict_losers": 6, "rejected": 8}
EXPECTED_BY_SERIES = {  # (experiment, source, signal): (csv_rows, saved, copies, losers, rejected)
    ("EXP_T1", "hydrolyzer", "voltage"): (7, 5, 1, 1, 0),
    ("EXP_T1", "hydrolyzer", "current"): (5, 3, 0, 2, 0),
    ("EXP_T1", "hydrolyzer", "power"): (2, 2, 0, 0, 0),
    ("EXP_T1", "hydrolyzer", "flow"): (3, 0, 0, 0, 3),
    ("EXP_T1", "hydrolyzer", "pressure"): (3, 1, 0, 0, 2),
    ("EXP_T1", "ambient", "ambient_temperature"): (2, 2, 0, 0, 0),
    ("EXP_T1", "ambient", "ambient_pressure"): (1, 1, 0, 0, 0),
    ("EXP_T1", "plant", "valve_state"): (3, 2, 0, 1, 0),
    ("EXP_T1", "plant", "process_state"): (1, 1, 0, 0, 0),
    ("EXP_T1", "plant", "pump_speed"): (3, 1, 0, 2, 0),
    ("EXP_T1", "absorber", "voltage"): (1, 0, 0, 0, 1),
    ("EXP_999", "hydrolyzer", "voltage"): (1, 0, 0, 0, 1),
    ("", "", ""): (1, 0, 0, 0, 1),
    ("EXP_T2", "absorber", "air_flow"): (3, 3, 0, 0, 0),
}


@pytest.fixture(scope="module")
def first_run(module_db, tmp_path_factory):
    report_dir = tmp_path_factory.mktemp("first_run")
    result = run_ingest(fixture_files(), module_db, report_dir)
    return {
        "db": module_db,
        "result": result,
        "report_dir": report_dir,
        "summary": read_summary(report_dir),
    }


def series_of(summary: dict) -> dict[tuple, tuple]:
    return {
        (s["experiment_id"], s["source"], s["signal"]): (
            s["csv_rows"],
            s["saved"],
            s["exact_copies"],
            s["conflict_losers"],
            s["rejected"],
        )
        for s in summary["series"]
    }


def test_the_run_finishes_with_findings_and_the_summary_matches_the_contract(first_run):  # S2.27
    assert first_run["result"].returncode == 1, first_run["result"].stderr
    summary = first_run["summary"]
    jsonschema.validate(summary, SCHEMA)
    assert summary["status"] == "completed_with_findings" and summary["exit_code"] == 1
    timing = summary["timing"]
    assert timing["batch_size"] == 10_000 and timing["batches"] == 1
    assert timing["rows_per_second"] and timing["rows_per_second"] > 0
    for name in ("ingest_summary.json", "ingest_report.md", "ingest_rejects.csv"):
        assert (first_run["report_dir"] / name).is_file()


def test_the_counts_balance_and_match_the_numbers_written_beforehand(first_run):  # S2.21
    totals = first_run["summary"]["totals"]
    assert {k: totals[k] for k in EXPECTED} == EXPECTED
    assert totals["balanced"] is True
    assert series_of(first_run["summary"]) == EXPECTED_BY_SERIES
    assert all(s["balanced"] for s in first_run["summary"]["series"])


def test_saved_equals_what_a_count_query_finds(first_run):  # S2.21, independent of the code
    db = first_run["db"]
    numeric = query(db, "SELECT COUNT(*) AS n FROM readings_numeric")[0]["n"]
    state = query(db, "SELECT COUNT(*) AS n FROM readings_state")[0]["n"]
    conflicts = query(db, "SELECT COUNT(*) AS n FROM readings_conflicts")[0]["n"]
    assert (numeric, state, conflicts) == (18, 3, 6)


def test_a_stated_offset_is_stored_as_utc(first_run):  # S2.5
    rows = query(
        first_run["db"],
        "SELECT time, value FROM readings_numeric WHERE signal = 'ambient_temperature' "
        "ORDER BY time",
    )
    assert [r["time"] for r in rows] == ["2026-05-04 08:00:00", "2026-05-04 08:01:00"]
    assert [r["value"] for r in rows] == [18.5, 18.6]


def test_rejected_rows_are_listed_with_row_number_and_reason(first_run):  # S2.6, S2.8, S2.9
    path = first_run["report_dir"] / "ingest_rejects.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(int(r["row_number"]), r["reason"]) for r in rows] == [
        (25, "missing_offset"),
        (26, "precision_too_fine"),
        (27, "bad_number"),
        (28, "unknown_signal"),
        (29, "unknown_experiment"),
        (30, "bad_quality"),
        (31, "malformed_row"),
        (33, "bad_timestamp"),
    ]
    # no point exists for a rejected row: the missing-offset row would have been 08:00:00 flow
    assert query(first_run["db"], "SELECT * FROM readings_numeric WHERE signal = 'flow'") == []


def test_sub_second_instants_are_two_points(first_run):  # S2.7
    rows = query(
        first_run["db"],
        "SELECT time, value FROM readings_numeric WHERE signal = 'power' ORDER BY time",
    )
    assert [r["time"] for r in rows] == ["2026-05-04 08:00:00.300000", "2026-05-04 08:00:00.700000"]


def test_exact_copy_is_one_point_and_not_a_conflict(first_run):  # S2.11
    db = first_run["db"]
    rows = query(
        db,
        "SELECT value FROM readings_numeric WHERE signal = 'voltage' AND time = "
        "'2026-05-04T08:00:01Z'",
    )
    assert [r["value"] for r in rows] == [101.0]
    assert (
        query(
            db,
            "SELECT * FROM readings_conflicts WHERE signal = 'voltage' AND time = "
            "'2026-05-04T08:00:01Z'",
        )
        == []
    )


def test_equal_flags_keep_the_smaller_value(first_run):  # S2.12
    db = first_run["db"]
    stored = query(
        db,
        "SELECT value FROM readings_numeric WHERE signal = 'voltage' AND time = "
        "'2026-05-04T08:00:02Z'",
    )
    assert [r["value"] for r in stored] == [1209.4]
    (conflict,) = query(
        db, "SELECT * FROM readings_conflicts WHERE signal = 'voltage' ORDER BY time"
    )
    assert conflict["value_kept_raw"] == "1209.4"
    assert conflict["value_discarded_raw"] == "1223.4"
    assert (conflict["reason"], conflict["resolution"]) == ("value_differs", "lower_value")
    assert (conflict["source_row_kept"], conflict["source_row_discarded"]) == (5, 4)


def test_better_flag_wins_over_the_smaller_value(first_run):  # S2.13
    db = first_run["db"]
    stored = query(
        db,
        "SELECT value, quality FROM readings_numeric WHERE signal = 'current' AND time = "
        "'2026-05-04T08:00:00Z'",
    )
    assert stored == [{"value": 16.0, "quality": "GOOD"}]
    conflict = query(
        db,
        "SELECT resolution FROM readings_conflicts WHERE signal = 'current' ORDER BY time",
    )[0]
    assert conflict["resolution"] == "better_quality"


def test_same_value_with_a_different_flag_is_a_conflict(first_run):  # S2.14
    db = first_run["db"]
    stored = query(
        db,
        "SELECT quality FROM readings_numeric WHERE signal = 'current' AND time = "
        "'2026-05-04T08:00:01Z'",
    )
    assert stored == [{"quality": "GOOD"}]
    conflict = query(
        db,
        "SELECT reason, quality_discarded FROM readings_conflicts WHERE signal = 'current' "
        "AND time = '2026-05-04T08:00:01Z'",
    )
    assert conflict == [{"reason": "quality_differs", "quality_discarded": "BAD"}]


def test_a_text_conflict_is_stored_as_text(first_run):  # S2.16
    db = first_run["db"]
    stored = query(
        db,
        "SELECT value FROM readings_state WHERE signal = 'valve_state' ORDER BY time",
    )
    assert [r["value"] for r in stored] == ["OPEN", "CLOSED"]
    (conflict,) = query(db, "SELECT * FROM readings_conflicts WHERE signal = 'valve_state'")
    assert (conflict["value_kept_raw"], conflict["value_discarded_raw"]) == ("CLOSED", "OPEN")


def test_an_empty_value_is_a_point_with_no_value(first_run):  # S2.17
    rows = query(
        first_run["db"],
        "SELECT value, quality FROM readings_numeric WHERE signal = 'current' AND time = "
        "'2026-05-04T08:00:02Z'",
    )
    assert rows == [{"value": None, "quality": "BAD"}]


def test_a_group_of_three_keeps_both_discards(first_run):
    rows = query(
        first_run["db"],
        "SELECT discard_rank, value_discarded_raw FROM readings_conflicts "
        "WHERE signal = 'pump_speed' ORDER BY discard_rank",
    )
    assert rows == [
        {"discard_rank": "1", "value_discarded_raw": "510"},
        {"discard_rank": "2", "value_discarded_raw": "520"},
    ]


def test_out_of_order_rows_are_counted_and_both_stored(first_run):  # S2.18
    summary = first_run["summary"]
    assert summary["out_of_order"] == {
        "total": 1,
        "by_series": [
            {"experiment_id": "EXP_T1", "source": "hydrolyzer", "signal": "voltage", "count": 1}
        ],
    }
    rows = query(
        first_run["db"],
        "SELECT time FROM readings_numeric WHERE signal = 'voltage' ORDER BY time",
    )
    assert "2026-05-04 08:00:05" in [r["time"] for r in rows]
    assert "2026-05-04 08:00:09" in [r["time"] for r in rows]


def test_an_outside_window_reading_is_saved_and_counted(first_run):  # S2.19
    window = first_run["summary"]["window_check"]
    assert window["outside_window_total"] == 1
    ambient = next(
        w
        for w in window["by_experiment_source"]
        if (w["experiment_id"], w["source"]) == ("EXP_T1", "ambient")
    )
    assert ambient["outside_window"] == 1 and ambient["last_offset_s"] == 7200
    stored = query(
        first_run["db"],
        "SELECT time FROM readings_numeric WHERE signal = 'ambient_pressure'",
    )
    assert [r["time"] for r in stored] == ["2026-05-04 12:00:00"]


def test_offsets_and_window_edges_are_in_the_summary(first_run):  # S2.20
    summary = first_run["summary"]
    assert summary["offsets_seen"]["ambient"] == ["+02:00"]
    assert summary["offsets_seen"]["absorber"] == ["Z"]
    rows = {
        (w["experiment_id"], w["source"]): (w["first_offset_s"], w["last_offset_s"])
        for w in summary["window_check"]["by_experiment_source"]
    }
    assert rows[("EXP_T2", "absorber")] == (0, -1)
    assert rows[("EXP_T1", "plant")] == (0, -5400)


def test_a_second_run_changes_nothing(first_run, tmp_path):  # S2.22
    db = first_run["db"]
    before = dump(db)
    second = run_ingest(fixture_files(), db, tmp_path)
    assert second.returncode == first_run["result"].returncode == 1
    assert series_of(read_summary(tmp_path)) == series_of(first_run["summary"])
    assert dump(db) == before  # readings and conflicts rows, field for field


def test_batch_size_does_not_change_what_is_stored(first_run, scratch_db, tmp_path):
    result = run_ingest(fixture_files(), scratch_db, tmp_path, "--batch-size", "5")
    assert result.returncode == 1, result.stderr
    summary = read_summary(tmp_path)
    assert summary["timing"]["batches"] == 6  # 27 lines in batches of 5
    assert dump(scratch_db) == dump(first_run["db"])


# ---- smaller scenarios with their own input ----------------------------------------------------

GOOD = ["2026-05-04T08:00:0{n}Z", "EXP_T1", "hydrolyzer", "voltage", "1{n}.0", "GOOD"]


def good_rows(count: int) -> list[list[str]]:
    return [[c.format(n=n) for c in GOOD] for n in range(count)]


def test_good_rows_are_saved_even_when_one_row_is_rejected(scratch_db, tmp_path):  # S2.10
    rows = good_rows(9) + [
        ["2026-05-04T08:00:09", "EXP_T1", "hydrolyzer", "voltage", "1.0", "GOOD"]
    ]
    result = run_ingest(write_input(tmp_path, rows), scratch_db, tmp_path / "out")
    assert result.returncode == 1
    summary = read_summary(tmp_path / "out")
    assert summary["totals"]["saved"] == 9 and summary["totals"]["rejected"] == 1
    assert query(scratch_db, "SELECT COUNT(*) AS n FROM readings_numeric")[0]["n"] == 9


def test_a_clean_file_exits_zero(scratch_db, tmp_path):
    result = run_ingest(write_input(tmp_path, good_rows(5)), scratch_db, tmp_path / "out")
    assert result.returncode == 0, result.stderr
    assert read_summary(tmp_path / "out")["status"] == "ok"


def test_a_reading_two_hours_after_the_end_is_saved_and_the_run_exits_1(
    scratch_db, tmp_path
):  # S2.19
    rows = good_rows(2) + [
        ["2026-05-04T14:00:00+02:00", "EXP_T1", "ambient", "ambient_pressure", "1010.0", "GOOD"]
    ]
    result = run_ingest(write_input(tmp_path, rows), scratch_db, tmp_path / "out")
    assert result.returncode == 1
    summary = read_summary(tmp_path / "out")
    assert summary["window_check"]["outside_window_total"] == 1
    assert summary["totals"]["rejected"] == 0 and summary["totals"]["saved"] == 3
    assert summary["totals"]["balanced"] is True


def test_file_order_never_changes_the_result(influx_client, tmp_path):  # S2.15
    pair = [
        ["2026-05-04T08:00:00Z", "EXP_T1", "hydrolyzer", "voltage", "1223.4", "GOOD"],
        ["2026-05-04T08:00:00Z", "EXP_T1", "hydrolyzer", "voltage", "1209.4", "GOOD"],
    ]
    state_pair = [
        ["2026-05-04T08:30:00Z", "EXP_T1", "plant", "valve_state", "OPEN", "GOOD"],
        ["2026-05-04T08:30:00Z", "EXP_T1", "plant", "valve_state", "CLOSED", "GOOD"],
    ]
    dumps = []
    for name, rows in (("a", pair + state_pair), ("b", pair[::-1] + state_pair[::-1])):
        db = f"m2_e2e_order_{uuid.uuid4().hex[:8]}_{name}"
        create_database(db)
        try:
            files = write_input(tmp_path / name, rows)
            assert run_ingest(files, db, tmp_path / f"out_{name}").returncode == 0
            dumps.append(dump(db))
        finally:
            drop_database(db)
    a, b = dumps
    assert a["readings_numeric"] == b["readings_numeric"]
    assert a["readings_state"] == b["readings_state"]

    def content(rows):  # everything but the file positions, which swap with the rows
        return [{k: v for k, v in r.items() if not k.startswith("source_row_")} for r in rows]

    assert content(a["readings_conflicts"]) == content(b["readings_conflicts"])
    assert len(a["readings_conflicts"]) == 2
    for first, second in zip(a["readings_conflicts"], b["readings_conflicts"], strict=True):
        assert first["source_row_kept"] == second["source_row_discarded"]
        assert first["source_row_discarded"] == second["source_row_kept"]


# ---- refusals and failed writes against a live server -------------------------------------------


def test_a_wrong_fingerprint_writes_nothing(scratch_db, tmp_path):  # S2.23
    files = write_input(tmp_path, good_rows(3))
    with files["csv"].open("r+b") as handle:
        handle.seek(-3, 2)
        last = handle.read(1)
        handle.seek(-3, 2)
        handle.write(b"9" if last != b"9" else b"8")  # one changed byte
    result = run_ingest(files, scratch_db, tmp_path / "out")
    assert result.returncode == 2
    assert read_summary(tmp_path / "out")["refusal_reason"] == "checksum_mismatch"
    assert tables(scratch_db) == []


def test_a_missing_database_is_refused_and_not_created(tmp_path):  # S2.24
    name = "dac_missing"
    assert name not in database_names()
    files = write_input(tmp_path, good_rows(3))
    result = run_ingest(files, name, tmp_path / "out")
    assert result.returncode == 2
    summary = read_summary(tmp_path / "out")
    jsonschema.validate(summary, SCHEMA)
    assert summary["refusal_reason"] == "database_missing"
    assert name not in database_names()


def test_a_refused_line_fails_the_whole_batch(scratch_db, tmp_path):  # S2.25
    env = init_influx.load_env()
    client = InfluxDBClient3(
        host=env["INFLUX_HOST"], token=env["INFLUX_TOKEN"], database=scratch_db
    )
    # the column `value` of readings_numeric becomes text, so any number written there is refused
    client.write(
        record="readings_numeric,experiment_id=EXP_T1,source=hydrolyzer,signal=voltage "
        'value="text",quality="GOOD" 1000000000'
    )
    client.close()
    result = run_ingest(fixture_files(), scratch_db, tmp_path)
    assert result.returncode == 3
    summary = read_summary(tmp_path)
    jsonschema.validate(summary, SCHEMA)
    assert summary["status"] == "write_failed"
    # the single batch carried every table's lines; none of it was saved
    assert tables(scratch_db) == ["readings_numeric"]
    assert query(scratch_db, "SELECT COUNT(*) AS n FROM readings_numeric")[0]["n"] == 1
