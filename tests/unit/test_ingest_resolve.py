"""Which reading wins an instant, and that file order never matters (S2.11-S2.16, unit level)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from itertools import permutations

import pytest

from pipeline.collisions import Reading, find_collisions, group_by_instant, sort_key
from pipeline.ingest import resolve_group

NUMERIC = "readings_numeric"
STATE = "readings_state"
T0 = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)


def reading(row_number: int, value: str, quality: str = "GOOD", signal="voltage") -> Reading:
    return Reading(
        row_number=row_number,
        timestamp_raw="2026-05-04T08:00:00Z",
        timestamp=T0,
        experiment_id="EXP_T1",
        source="hydrolyzer",
        signal=signal,
        value_raw=value,
        quality=quality,
    )


def outcome(group: list[Reading], table: str = NUMERIC):
    """Stored value and flag, copies, and every conflict record, without row numbers."""
    result = resolve_group(group, table)
    discarded = sorted(
        (x.rank, x.reading.value_raw, x.reading.quality, x.reason, x.resolution)
        for x in result.losers
    )
    return (result.kept.value_raw, result.kept.quality, result.exact_copies, discarded)


def test_exact_copy_collapses_without_a_conflict():  # S2.11
    result = resolve_group([reading(1, "250.0"), reading(2, "250.00")], NUMERIC)
    assert result.exact_copies == 1
    assert result.losers == ()
    assert float(result.kept.value_raw) == 250.0


def test_equal_flags_smaller_value_wins():  # S2.12
    result = resolve_group([reading(1, "1223.4"), reading(2, "1209.4")], NUMERIC)
    assert result.kept.value_raw == "1209.4"
    (loser,) = result.losers
    assert (loser.reading.value_raw, loser.reason, loser.resolution) == (
        "1223.4",
        "value_differs",
        "lower_value",
    )


def test_better_flag_beats_the_smaller_value():  # S2.13
    result = resolve_group([reading(1, "15.06", "UNCERTAIN"), reading(2, "16.00")], NUMERIC)
    assert (result.kept.value_raw, result.kept.quality) == ("16.00", "GOOD")
    assert result.losers[0].resolution == "better_quality"
    assert result.losers[0].reason == "value_differs"


def test_same_value_different_flag_is_a_conflict():  # S2.14
    result = resolve_group([reading(1, "7.755", "BAD"), reading(2, "7.755", "GOOD")], NUMERIC)
    assert result.kept.quality == "GOOD"
    assert result.exact_copies == 0
    assert (result.losers[0].reason, result.losers[0].resolution) == (
        "quality_differs",
        "better_quality",
    )


def test_quality_order_is_good_then_uncertain_then_bad():
    result = resolve_group(
        [reading(1, "1", "BAD"), reading(2, "2", "UNCERTAIN"), reading(3, "3", "GOOD")], NUMERIC
    )
    assert result.kept.value_raw == "3"
    assert [x.reading.quality for x in result.losers] == ["UNCERTAIN", "BAD"]


def test_text_conflict_keeps_the_alphabetically_first_value():  # S2.16
    group = [reading(1, "OPEN", signal="valve_state"), reading(2, "CLOSED", signal="valve_state")]
    result = resolve_group(group, STATE)
    assert result.kept.value_raw == "CLOSED"
    assert result.losers[0].reading.value_raw == "OPEN"
    assert result.losers[0].resolution == "alphabetical"


def test_text_order_is_bytes_not_locale_or_case_folding():
    result = resolve_group([reading(1, "a", signal="valve_state"), reading(2, "B")], STATE)
    assert result.kept.value_raw == "B"  # 0x42 < 0x61


def test_a_present_value_beats_an_empty_one_at_equal_flags():
    result = resolve_group([reading(1, "", "BAD"), reading(2, "5.0", "BAD")], NUMERIC)
    assert result.kept.value_raw == "5.0"
    assert result.losers[0].resolution == "present_value"
    assert result.losers[0].reason == "value_differs"


def test_better_flag_beats_a_present_value():
    result = resolve_group([reading(1, "5.0", "BAD"), reading(2, "", "GOOD")], NUMERIC)
    assert (result.kept.value_raw, result.kept.quality) == ("", "GOOD")


def test_two_empty_values_with_equal_flags_are_exact_copies():
    result = resolve_group([reading(1, "", "BAD"), reading(2, "", "BAD")], NUMERIC)
    assert result.exact_copies == 1 and result.losers == ()


def test_a_group_of_three_keeps_one_record_per_discarded_reading():
    result = resolve_group([reading(1, "520"), reading(2, "500"), reading(3, "510")], NUMERIC)
    assert result.kept.value_raw == "500"
    assert [(x.rank, x.reading.value_raw) for x in result.losers] == [(1, "510"), (2, "520")]


def test_a_loser_equal_to_the_winner_is_a_copy_not_a_conflict():
    result = resolve_group([reading(1, "1.0"), reading(2, "2.0"), reading(3, "1.00")], NUMERIC)
    assert result.exact_copies == 1
    assert [x.reading.value_raw for x in result.losers] == ["2.0"]


@pytest.mark.parametrize(
    "group",
    [
        [reading(1, "1223.4"), reading(2, "1209.4")],
        [reading(1, "15.06", "UNCERTAIN"), reading(2, "16.00"), reading(3, "16.0")],
        [reading(1, ""), reading(2, "5.0", "BAD"), reading(3, "5.0"), reading(4, "7", "UNCERTAIN")],
    ],
)
def test_file_order_never_changes_the_outcome(group):  # S2.15, unit level
    # Row numbers differ with order, so they are left out of the comparison on purpose: they
    # are provenance (where in the file), not content. Stored value and flag, the number of
    # copies and every conflict record must agree for every ordering.
    outcomes = {str(outcome(list(ordering))) for ordering in permutations(group)}
    assert len(outcomes) == 1


# ---- the shared grouping pass --------------------------------------------------------------


def test_group_by_instant_yields_singletons_and_find_collisions_does_not():
    later = Reading(
        3,
        "2026-05-04T08:00:01Z",
        datetime(2026, 5, 4, 8, 0, 1, tzinfo=UTC),
        "EXP_T1",
        "plant",
        "fan_speed",
        "9",
        "GOOD",
    )
    rows = sorted([reading(1, "1"), reading(2, "2"), later], key=sort_key)
    assert [len(g) for g in group_by_instant(rows)] == [2, 1]
    assert [len(g) for g in find_collisions(rows)] == [2]


def test_equal_instants_with_different_offsets_are_one_group():
    a = reading(1, "1")
    b = Reading(
        2,
        "2026-05-04T10:00:00+02:00",
        datetime(2026, 5, 4, 10, 0, tzinfo=timezone(timedelta(hours=2))),
        "EXP_T1",
        "hydrolyzer",
        "voltage",
        "2",
        "GOOD",
    )
    assert [len(g) for g in group_by_instant(sorted([a, b], key=sort_key))] == [2]
