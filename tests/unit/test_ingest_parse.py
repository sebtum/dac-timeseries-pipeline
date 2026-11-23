"""Parsing and validation rules of the ingest (S2.5-S2.9, S2.17-S2.20 at unit level).

No database: `pipeline.ingest` is pure. Each test names the scenario it backs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipeline.collisions import Reading
from pipeline.ingest import (
    Experiment,
    Parsed,
    Reject,
    RowError,
    Scan,
    conflict_line,
    parse_instant,
    parse_number,
    parse_row,
    reading_line,
    resolve_group,
    timestamp_ns,
)

START = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
EXPERIMENTS = {"EXP_T1": Experiment("EXP_T1", START, START + timedelta(hours=2))}


def row(
    ts="2026-05-04T08:00:00Z",
    exp="EXP_T1",
    source="hydrolyzer",
    signal="voltage",
    value="100.0",
    quality="GOOD",
):
    return [ts, exp, source, signal, value, quality]


def parsed(fields: list[str], row_number: int = 1) -> Parsed:
    outcome = parse_row(row_number, fields, EXPERIMENTS)
    assert isinstance(outcome, Parsed), outcome
    return outcome


def rejected(fields: list[str]) -> Reject:
    outcome = parse_row(1, fields, EXPERIMENTS)
    assert isinstance(outcome, Reject), outcome
    return outcome


# ---- S2.5: a stated offset is honoured --------------------------------------------------


def test_offset_is_honoured_and_kept_as_written():
    instant, offset = parse_instant("2026-05-04T10:00:00+02:00")
    assert instant == datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
    assert instant.utcoffset() == timedelta(0)
    assert offset == "+02:00"


def test_z_and_negative_offsets():
    assert parse_instant("2026-05-04T08:00:00Z") == (START, "Z")
    instant, offset = parse_instant("2026-05-04T03:30:00-04:30")
    assert instant == datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
    assert offset == "-04:30"


# ---- S2.6: no offset is rejected, not guessed -------------------------------------------


def test_missing_offset_is_named():
    with pytest.raises(RowError) as caught:
        parse_instant("2026-05-04T08:00:00")
    assert caught.value.reason == "missing_offset"


# ---- S2.7 / S2.8: precision is kept or refused, never cut -------------------------------


def test_sub_second_instants_are_exact():
    a, _ = parse_instant("2026-05-04T08:00:00.300Z")
    b, _ = parse_instant("2026-05-04T08:00:00.700Z")
    assert b - a == timedelta(milliseconds=400)
    assert timestamp_ns(a) == int(START.timestamp()) * 10**9 + 300_000_000


def test_microsecond_precision_is_kept():
    instant, _ = parse_instant("2026-05-04T08:00:00.123456Z")
    assert instant.microsecond == 123456


def test_finer_than_a_microsecond_is_rejected():
    with pytest.raises(RowError) as caught:
        parse_instant("2026-05-04T08:00:00.1234567Z")
    assert caught.value.reason == "precision_too_fine"


def test_trailing_zeros_past_the_sixth_digit_lose_nothing():
    instant, _ = parse_instant("2026-05-04T08:00:00.1234560Z")
    assert instant.microsecond == 123456


@pytest.mark.parametrize(
    "text",
    ["not-a-time", "2026-13-04T08:00:00Z", "2026-05-04 08:00:00Z", "2026-05-04T08:00:00z", ""],
)
def test_unreadable_timestamps_are_bad_timestamp(text):
    with pytest.raises(RowError) as caught:
        parse_instant(text)
    assert caught.value.reason == "bad_timestamp"


# ---- numbers ------------------------------------------------------------------------------


def test_numbers_parse_exactly_and_empty_is_none():
    assert parse_number("250.0") == parse_number("250.00") == 250.0
    assert parse_number("-3.14159265358979") == -3.14159265358979
    assert parse_number("") is None


@pytest.mark.parametrize("text", ["abc", "1_000", "nan", "inf", "1e999", " 5", "5 ", "--1"])
def test_non_numbers_are_bad_number(text):
    with pytest.raises(RowError) as caught:
        parse_number(text)
    assert caught.value.reason == "bad_number"


# ---- S2.9: every unreadable row gets a named reason --------------------------------------


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        (row(value="abc"), "bad_number"),
        (row(source="absorber", signal="voltage"), "unknown_signal"),
        (row(exp="EXP_999"), "unknown_experiment"),
        (row(quality="OK"), "bad_quality"),
        (row(quality="good"), "bad_quality"),
        (row()[:5], "malformed_row"),
        (row() + ["extra"], "malformed_row"),
        ([], "malformed_row"),
        (row(ts="2026-05-04T08:00:00"), "missing_offset"),
        (row(ts="2026-05-04T08:00:00.1234567Z"), "precision_too_fine"),
        (row(ts="garbage"), "bad_timestamp"),
        (row(source="plant", signal="valve_state", value="OP\nEN"), "malformed_row"),
    ],
)
def test_each_defect_has_its_reason(fields, reason):
    assert rejected(fields).reason == reason


def test_a_word_on_a_numeric_signal_is_rejected_but_on_a_state_signal_is_kept():
    assert rejected(row(value="OPEN")).reason == "bad_number"
    ok = parsed(row(source="plant", signal="valve_state", value="OPEN"))
    assert ok.reading.value_raw == "OPEN"


def test_malformed_row_carries_no_series_key_and_no_fields():
    reject = rejected(row()[:5])
    assert reject.fields == ()
    assert reject.series == ("", "", "")


def test_the_first_failing_check_names_the_reason():
    # unknown experiment is checked before the timestamp and value
    assert rejected(row(exp="EXP_999", ts="garbage", value="abc")).reason == "unknown_experiment"


# ---- S2.17: an empty value is a reading with no value ------------------------------------


def test_empty_value_is_accepted_and_written_without_a_value_field():
    reading = parsed(row(value="", quality="BAD")).reading
    line = reading_line(reading, "readings_numeric")
    assert "value=" not in line
    assert 'quality="BAD"' in line
    prefix = "readings_numeric,experiment_id=EXP_T1,source=hydrolyzer,signal=voltage "
    assert line.startswith(prefix)


def test_numeric_and_text_values_render_as_float_and_string():
    numeric = parsed(row(value="250.00")).reading
    assert 'value=250.0,quality="GOOD"' in reading_line(numeric, "readings_numeric")
    text = parsed(row(source="plant", signal="valve_state", value='OP"EN\\')).reading
    assert 'value="OP\\"EN\\\\"' in reading_line(text, "readings_state")


def test_line_ends_with_exact_nanoseconds():
    reading = parsed(row(ts="2026-05-04T10:00:00.5+02:00")).reading
    assert reading_line(reading, "readings_numeric").endswith(f" {int(START.timestamp())}500000000")


# ---- scan counters: S2.18 order, S2.19 window, S2.20 offsets -----------------------------


def scan_rows(rows: list[list[str]]) -> tuple[Scan, list[Reject]]:
    rejects: list[Reject] = []
    scan = Scan(EXPERIMENTS, on_reject=rejects.append)
    list(scan.readings(enumerate(rows, start=1)))
    return scan, rejects


def test_out_of_order_is_counted_and_both_rows_are_still_accepted():
    rows = [row(ts="2026-05-04T08:00:09Z"), row(ts="2026-05-04T08:00:05Z")]
    scan = Scan(EXPERIMENTS, on_reject=lambda r: None)
    kept = list(scan.readings(enumerate(rows, start=1)))
    assert len(kept) == 2
    assert scan.out_of_order[("EXP_T1", "hydrolyzer", "voltage")] == 1


def test_equal_timestamps_and_ordered_rows_are_not_out_of_order():
    rows = [row(ts="2026-05-04T08:00:05Z")] * 2 + [row(ts="2026-05-04T08:00:06Z")]
    scan, _ = scan_rows(rows)
    assert sum(scan.out_of_order.values()) == 0


def test_out_of_order_is_per_series():
    rows = [
        row(ts="2026-05-04T08:00:09Z"),
        row(ts="2026-05-04T08:00:05Z", signal="current"),  # other series: not out of order
    ]
    scan, _ = scan_rows(rows)
    assert sum(scan.out_of_order.values()) == 0


def test_window_is_start_inclusive_end_exclusive():
    rows = [
        row(ts="2026-05-04T08:00:00Z"),  # at start: inside
        row(ts="2026-05-04T09:59:59Z"),  # last second: inside
        row(ts="2026-05-04T10:00:00Z"),  # at end: outside
        row(ts="2026-05-04T07:59:59Z"),  # before start: outside
        row(ts="2026-05-04T14:00:00+02:00", source="ambient", signal="ambient_pressure"),
    ]
    scan, _ = scan_rows(rows)
    hydro = scan.windows[("EXP_T1", "hydrolyzer")]
    assert hydro.outside == 2
    assert hydro.first == START - timedelta(seconds=1)
    assert hydro.last == START + timedelta(hours=2)
    assert scan.windows[("EXP_T1", "ambient")].outside == 1  # 2 h after the end


def test_offsets_are_recorded_per_source_from_accepted_rows():
    rows = [
        row(),
        row(ts="2026-05-04T10:00:00+02:00", source="ambient", signal="ambient_pressure"),
        row(ts="2026-05-04T08:00:00", source="absorber", signal="air_flow"),  # rejected
    ]
    scan, _ = scan_rows(rows)
    assert scan.offsets_seen == {"hydrolyzer": {"Z"}, "ambient": {"+02:00"}}


def test_rejected_rows_count_in_their_series_and_by_reason():
    rows = [row(), row(value="abc"), row(quality="OK"), row()[:5]]
    scan, rejects = scan_rows(rows)
    assert scan.csv_rows == 4 and len(rejects) == 3
    assert dict(scan.rejects_by_reason) == {"bad_number": 1, "bad_quality": 1, "malformed_row": 1}
    series = scan.tally[("EXP_T1", "hydrolyzer", "voltage")]
    assert (series.csv_rows, series.rejected) == (3, 2)
    assert scan.tally[("", "", "")].rejected == 1


def test_garbage_series_keys_cannot_grow_memory_without_bound(monkeypatch):
    monkeypatch.setattr("pipeline.ingest.MAX_TRACKED_SERIES", 3)
    rows = [row(exp=f"EXP_X{i}") for i in range(10)] + [row()]
    scan, _ = scan_rows(rows)
    assert len(scan.tally) <= 5  # 3 garbage keys at most, the overflow bucket, the real series
    assert scan.tally[("EXP_T1", "hydrolyzer", "voltage")].csv_rows == 1
    assert sum(t.csv_rows for t in scan.tally.values()) == 11


# ---- conflicts line: S2.12 / S2.16 field shapes -------------------------------------------


def test_conflict_line_keeps_raw_text_and_rank_tag():
    kept = parsed(row(value="1209.4"), row_number=5).reading
    other = parsed(row(value="1223.40"), row_number=4).reading
    loser = resolve_group([other, kept], "readings_numeric").losers[0]
    line = conflict_line(kept, loser)
    assert line.startswith(
        "readings_conflicts,experiment_id=EXP_T1,source=hydrolyzer,signal=voltage,discard_rank=1 "
    )
    assert 'value_kept_raw="1209.4"' in line
    assert 'value_discarded_raw="1223.40"' in line
    assert "source_row_kept=5i,source_row_discarded=4i" in line
    assert 'reason="value_differs",resolution="lower_value"' in line


def test_reading_dataclass_is_what_the_collision_module_expects():
    assert isinstance(parsed(row()).reading, Reading)
