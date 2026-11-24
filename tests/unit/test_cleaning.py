"""Unit tests for the cleaning rules (M3): pure functions, no InfluxDB, no randomness.

Every series is built by construction. Noise is a fixed alternating pattern of plus and minus
half the signal's declared step size, so every normal step equals the step size (never flat) and
the expected verdicts follow from the construction alone.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from pipeline import cleaning, cleaning_policy
from pipeline.cleaning import (
    NS,
    Interval,
    RawPoint,
    Verdict,
    build_summary,
    flatline_intervals,
    flatline_positions,
    gap_intervals,
    instant_text,
    judge,
    judge_numeric,
    judge_state,
    pick_sample_indices,
    render_report,
    sample_record,
    spike_positions,
    state_intervals,
    summarise_series,
)
from pipeline.cleaning_policy import POLICY, POLICY_VERSION, REASON_CODES

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = REPO_ROOT / "contracts" / "cleaning_summary.schema.json"

T0 = int(datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC).timestamp()) * NS

VOLTAGE = ("hydrolyzer", "voltage")  # 1 Hz, step 0.15, limits 0..200, typical 60..130
CURRENT = ("hydrolyzer", "current")  # 1 Hz, step 0.3, limits -2..500, typical 0..260
SETPOINT = ("hydrolyzer", "current_setpoint")  # 1 Hz, commanded
AIR_FLOW = ("absorber", "air_flow")  # 1 Hz, step 7.55
SOLVENT_TEMP = ("absorber", "solvent_temperature")  # 0.2 Hz, step 0.285
SOLVENT_PH = ("absorber", "solvent_pH")  # 0.2 Hz, step 0.0485, limits 0..14, typical 6..9
CONDUCTIVITY = ("hydrolyzer", "conductivity")  # 0.2 Hz
SOLAR = ("ambient", "available_solar_power")  # 1/60 Hz, step 12.255, limits 0..1000
PROCESS_STATE = ("plant", "process_state")
VALVE_STATE = ("plant", "valve_state")

NONE: frozenset[int] = frozenset()


# ---------------------------------------------------------------------------- builders


def points(
    values: list,
    nominal_s: float = 1.0,
    *,
    quality: dict[int, str] | None = None,
    start_s: float = 0.0,
) -> list[RawPoint]:
    quality = quality or {}
    return [
        RawPoint(T0 + round((start_s + k * nominal_s) * NS), v, quality.get(k, "GOOD"))
        for k, v in enumerate(values)
    ]


def noise(n: int, base: float, step: float) -> list[float]:
    """Alternating +/- half a step around `base`: every step has size `step`."""
    return [base + (step / 2 if k % 2 == 0 else -step / 2) for k in range(n)]


def from_steps(start: float, sizes: list[float]) -> list[float]:
    """A series whose k-th step has size `sizes[k]`, signs alternating so values stay near start."""
    values = [start]
    for k, size in enumerate(sizes):
        values.append(values[-1] + (size if k % 2 == 0 else -size))
    return values


def hits(verdicts: list[Verdict], code: str) -> list[int]:
    return [i for i, v in enumerate(verdicts) if code in v.flags]


def run(pair, values, nominal_s=1.0, **kwargs) -> list[Verdict]:
    return judge_numeric(pair, points(values, nominal_s, **kwargs), NONE)


# ---------------------------------------------------------------------------- acquisition codes


def test_accepted_reading_has_empty_reason_and_no_flags() -> None:
    verdicts = run(VOLTAGE, noise(30, 100.0, 0.15))
    assert all(v.accepted and v.reason == "" and v.flags == () for v in verdicts)
    assert verdicts[0].verdict == "accepted"


def test_no_value() -> None:
    values = noise(20, 100.0, 0.15)
    values[7] = None
    verdicts = run(VOLTAGE, values)
    assert verdicts[7].reason == "no_value"
    assert verdicts[7].flags == ("no_value",)
    assert verdicts[7].verdict == "excluded"
    assert all(v.accepted for k, v in enumerate(verdicts) if k != 7)


def test_bad_quality_is_excluded() -> None:
    verdicts = run(CONDUCTIVITY, noise(20, 200.0, 1.85), 5.0, quality={3: "BAD", 4: "BAD"})
    assert [v.reason for v in verdicts[3:5]] == ["flag_bad", "flag_bad"]
    assert verdicts[2].accepted and verdicts[5].accepted


def test_uncertain_is_excluded() -> None:
    verdicts = run(VOLTAGE, noise(20, 100.0, 0.15), quality={5: "UNCERTAIN"})
    assert verdicts[5].reason == "flag_uncertain"
    assert verdicts[5].flags == ("flag_uncertain",)


# ---------------------------------------------------------------------------- physical limits


def test_value_outside_physical_limits_is_excluded_and_never_a_spike() -> None:
    values = noise(30, 7.6, 0.0485)
    values[15] = 27.4
    verdicts = run(SOLVENT_PH, values, 5.0)
    assert verdicts[15].reason == "outside_physical_limits"
    assert "spike" not in verdicts[15].flags
    # outside typical range too, so the note is last
    assert verdicts[15].flags == ("outside_physical_limits", "outside_typical_range")
    assert verdicts[14].accepted and verdicts[16].accepted
    assert hits(verdicts, "spike") == []


@pytest.mark.parametrize(
    ("value", "inside"),
    [(14.0, True), (0.0, True), (13.999, True), (14.0001, False), (-0.0001, False)],
)
def test_physical_limit_bounds_are_inclusive(value: float, inside: bool) -> None:
    (verdict,) = run(SOLVENT_PH, [value], 5.0)
    assert ("outside_physical_limits" not in verdict.flags) is inside
    assert verdict.accepted is inside


def test_physical_limit_bounds_inclusive_at_the_declared_numbers() -> None:
    for pair in (VOLTAGE, CURRENT, SOLVENT_PH, SOLAR):
        low, high = POLICY[pair].limits
        for value in (low, high):
            (verdict,) = run(pair, [value])
            assert "outside_physical_limits" not in verdict.flags, (pair, value)


def test_typical_range_violation_is_a_note_not_an_exclusion() -> None:
    values = noise(60, 0.5, 0.3)
    values[30] = -0.5
    verdicts = run(CURRENT, values)
    assert verdicts[30].accepted
    assert verdicts[30].flags == ("outside_typical_range",)
    assert verdicts[30].reason == ""
    assert hits(verdicts, "spike") == []
    assert sum(1 for v in verdicts if v.flags) == 1


# ---------------------------------------------------------------------------- spike


def test_single_spike_is_excluded_and_neighbours_are_kept() -> None:
    values = noise(60, 100.0, 0.15)
    values[30] = 140.0
    verdicts = run(VOLTAGE, values)
    assert verdicts[30].reason == "spike"
    assert verdicts[30].flags == ("spike", "outside_typical_range")
    assert all(v.accepted for k, v in enumerate(verdicts) if k != 30)


def test_step_is_not_a_spike() -> None:
    values = noise(30, 100.0, 0.15) + noise(30, 110.0, 0.15)
    verdicts = run(VOLTAGE, values)
    assert hits(verdicts, "spike") == []
    assert all(v.accepted for v in verdicts)


def test_ramp_is_not_a_spike() -> None:
    hold = noise(30, 150.0, 0.3)
    ramp = [150.0 + 4.0 * k for k in range(1, 16)]
    values = hold + ramp + noise(30, 210.0, 0.3)
    verdicts = run(CURRENT, values)
    assert hits(verdicts, "spike") == []
    assert hits(verdicts, "flatline") == []


def test_spike_at_both_series_ends_uses_a_truncated_window() -> None:
    values = noise(20, 100.0, 0.15)
    values[0] = 140.0
    values[-1] = 60.0
    verdicts = run(VOLTAGE, values)
    assert hits(verdicts, "spike") == [0, 19]


def test_hampel_window_is_truncated_not_padded() -> None:
    # Two readings: the median sits between them, so no deviation exceeds the floor of the
    # window's own spread; three readings give the median a majority to rest on.
    assert spike_positions([100.0, 140.0], 0.15) == []
    assert spike_positions([100.0, 140.0, 100.1], 0.15) == [1]
    assert spike_positions([140.0], 0.15) == []
    assert spike_positions([], 0.15) == []


def test_spike_floor_is_ten_normal_steps() -> None:
    base = noise(21, 100.0, 0.15)
    just_under = list(base)
    just_under[10] = 100.0 + 1.3  # below 10 x 0.15 = 1.5 from the median
    over = list(base)
    over[10] = 100.0 + 1.8
    assert 10 not in spike_positions(just_under, 0.15)
    assert 10 in spike_positions(over, 0.15)


def test_burst_longer_than_the_window_is_not_caught() -> None:
    # Documented limit: a burst of 6 or more readings carries its own median.
    values = noise(40, 100.0, 0.15)
    for k in range(15, 24):
        values[k] = 140.0 + (k % 2) * 0.1
    assert 19 not in spike_positions(values, 0.15)


def test_setpoint_hold_is_exempt_from_spike_and_flatline() -> None:
    values = [0.0] * 100 + [150.0] * 300 + [210.0] * 400
    verdicts = run(SETPOINT, values)
    assert all(v.accepted and v.flags == () for v in verdicts)


# ---------------------------------------------------------------------------- flatline


def test_exact_run_of_40_is_a_flatline_and_a_run_of_3_is_not() -> None:
    values = noise(100, 31.0, 0.285)
    for k in range(20, 60):
        values[k] = 30.22
    for k in range(80, 83):
        values[k] = 31.0
    verdicts = run(SOLVENT_TEMP, values, 5.0)
    assert hits(verdicts, "flatline") == list(range(20, 60))
    assert all(verdicts[k].reason == "flatline" for k in range(20, 60))
    assert hits(verdicts, "flatline")[0] == 20
    assert all(verdicts[k].accepted for k in (79, 80, 81, 82, 83))


def test_run_of_3_readings_flags_none() -> None:
    values = noise(60, 100.0, 0.15)
    values[30] = values[31] = values[32] = 100.0
    verdicts = run(VOLTAGE, values)
    assert hits(verdicts, "flatline") == []


def test_noise_collapse_is_a_flatline_with_a_sharp_boundary() -> None:
    normal = noise(60, 1200.0, 7.55)
    collapsed = noise(40, 1200.0, 7.55 * 0.05)
    verdicts = run(AIR_FLOW, normal + collapsed)
    flagged = hits(verdicts, "flatline")
    assert flagged == list(range(60, 100))
    assert all(v.reason == "flatline" for v in verdicts[60:])
    assert all(v.accepted for v in verdicts[:60])


def test_flat_step_threshold_is_a_fifth_of_the_step() -> None:
    # 1.4 < 0.2 x 7.55 = 1.51 is flat; 1.6 is not.
    flat = noise(60, 1200.0, 7.55) + noise(30, 1200.0, 1.4)
    not_flat = noise(60, 1200.0, 7.55) + noise(30, 1200.0, 1.6)
    assert hits(run(AIR_FLOW, flat), "flatline") != []
    assert hits(run(AIR_FLOW, not_flat), "flatline") == []


S = 0.005  # a small step on solvent_pH: below 0.2 x 0.0485 = 0.0097
N = 0.0485  # a normal step on solvent_pH


def test_s3_32_scattered_small_steps_are_chance_not_a_flatline(monkeypatch) -> None:
    # 7 of 13 consecutive steps are small, never 5 in a row.
    pattern = [S, S, S, S, N, S, S, S, N, N, N, N, N]
    sizes = [N] * 20 + pattern + [N] * 20
    values = from_steps(7.6, sizes)
    assert hits(run(SOLVENT_PH, values, 5.0), "flatline") == []
    # the majority rule alone would have fired: the run rule is what keeps it quiet
    monkeypatch.setattr(cleaning_policy, "FLAT_MIN_RUN", 1)
    assert hits(run(SOLVENT_PH, values, 5.0), "flatline") != []


def test_s3_32_four_small_steps_in_a_row_in_a_mostly_flat_window(monkeypatch) -> None:
    sizes = [N] * 10 + ([S] * 4 + [N]) * 6 + [N] * 10
    values = from_steps(7.6, sizes)
    assert hits(run(SOLVENT_PH, values, 5.0), "flatline") == []
    monkeypatch.setattr(cleaning_policy, "FLAT_MIN_RUN", 1)
    assert hits(run(SOLVENT_PH, values, 5.0), "flatline") != []


def test_s3_32_five_small_steps_in_a_row_in_a_mostly_flat_window() -> None:
    group = [S] * 4 + [N]
    sizes = [N] * 10 + group * 3 + [S] * 5 + [N] + group * 3 + [N] * 10
    values = from_steps(7.6, sizes)
    verdicts = run(SOLVENT_PH, values, 5.0)
    # the 5-run is steps 25..29, that is readings 25..30: exactly those 6
    assert hits(verdicts, "flatline") == [25, 26, 27, 28, 29, 30]


def _solar_series() -> tuple[list[float], dict[str, range]]:
    seg_a = noise(30, 300.0, 12.255)
    ramp_steps = [0.8 + (5.0 - 0.8) * k / 23 for k in range(24)]
    ramp = [20.0]
    for size in ramp_steps:
        ramp.append(ramp[-1] + size)
    assert len(ramp) == 25 and ramp[1] - ramp[0] == pytest.approx(0.8)
    assert ramp[-1] - ramp[-2] == pytest.approx(5.0)
    seg_b = noise(30, 300.0, 12.255)
    frozen = [312.4] * 12
    seg_c = noise(30, 300.0, 12.255)
    zeros = [0.0] * 20
    seg_d = noise(30, 300.0, 12.255)
    values = seg_a + ramp + seg_b + frozen + seg_c + zeros + seg_d
    at = 30
    spans = {}
    for name, seg in (
        ("ramp", ramp),
        ("seg_b", seg_b),
        ("frozen", frozen),
        ("seg_c", seg_c),
        ("zeros", zeros),
    ):
        spans[name] = range(at, at + len(seg))
        at += len(seg)
    return values, spans


def test_s3_33_solar_only_an_exactly_repeated_value_is_a_flatline() -> None:
    values, spans = _solar_series()
    verdicts = run(SOLAR, values, 60.0)
    flagged = hits(verdicts, "flatline")
    assert flagged == list(spans["frozen"])
    assert len(flagged) == 12
    assert not set(flagged) & set(spans["ramp"])
    assert not set(flagged) & set(spans["zeros"])


def test_solar_zeros_alone_are_accepted() -> None:
    verdicts = run(SOLAR, [0.0] * 20, 60.0)
    assert all(v.accepted and v.flags == () for v in verdicts)


def test_solar_slow_ramp_is_not_flat() -> None:
    # 25 readings rising 0.8 to 5 kW per step: most steps are under 0.2 x 12.255 = 2.45, yet none
    # is an exact repeat.
    ramp = [20.0]
    for k in range(24):
        ramp.append(ramp[-1] + 0.8 + (5.0 - 0.8) * k / 23)
    verdicts = run(SOLAR, ramp, 60.0)
    assert all(v.accepted for v in verdicts)


def test_solar_frozen_value_is_flagged() -> None:
    values = noise(20, 300.0, 12.255) + [312.4] * 12 + noise(20, 300.0, 12.255)
    verdicts = run(SOLAR, values, 60.0)
    assert hits(verdicts, "flatline") == list(range(20, 32))
    assert all(verdicts[k].reason == "flatline" for k in range(20, 32))


def test_solar_zero_step_needs_both_values_exactly_zero_to_be_exempt() -> None:
    # exact-repeat rule: 0.0 -> 0.0 is night, never flat; 5.0 -> 5.0 is a repeat
    assert flatline_positions([0.0] * 20, 12.255, 5, True) == []
    assert flatline_positions([5.0] * 12, 12.255, 5, True) == list(range(12))
    # a tiny change is not an exact repeat
    assert flatline_positions([5.0 + 0.01 * (k % 2) for k in range(12)], 12.255, 5, True) == []


def test_chance_flat_steps_alone_are_not_a_flatline_on_a_smooth_signal() -> None:
    # 4 identical readings in the middle of normal noise: 3 flat steps
    values = noise(80, 31.0, 0.285)
    values[40:44] = [31.0] * 4
    assert hits(run(SOLVENT_TEMP, values, 5.0), "flatline") == []


def test_flatline_at_the_end_of_a_series() -> None:
    values = noise(40, 31.0, 0.285) + [31.0] * 12
    assert hits(run(SOLVENT_TEMP, values, 5.0), "flatline") == list(range(40, 52))


# ---------------------------------------------------------------------------- conflicts, priority


def test_conflicting_duplicate_is_excluded_and_other_instants_are_not() -> None:
    pts = points(noise(20, 100.0, 0.15))
    verdicts = judge_numeric(VOLTAGE, pts, frozenset({pts[8].time_ns}))
    assert verdicts[8].reason == "conflicting_duplicate"
    assert all(v.accepted for k, v in enumerate(verdicts) if k != 8)


def test_conflicting_duplicate_that_is_also_a_spike_keeps_both_flags() -> None:
    # decision 26: the primary reason is the higher-priority code, spike is still in flags
    values = noise(30, 100.0, 0.15)
    values[15] = 140.0
    pts = points(values)
    verdicts = judge_numeric(VOLTAGE, pts, frozenset({pts[15].time_ns}))
    assert verdicts[15].reason == "conflicting_duplicate"
    assert verdicts[15].flags == ("conflicting_duplicate", "spike", "outside_typical_range")


def test_priority_bad_and_spike() -> None:
    values = noise(60, 100.0, 0.15)
    values[30] = 140.0
    verdicts = run(VOLTAGE, values, quality={30: "BAD"})
    assert verdicts[30].reason == "flag_bad"
    assert verdicts[30].flags == ("flag_bad", "spike", "outside_typical_range")


def test_priority_bad_and_outside_limits_lists_both_in_order_note_last() -> None:
    values = noise(30, 7.6, 0.0485)
    values[10] = 27.4
    verdicts = run(SOLVENT_PH, values, 5.0, quality={10: "BAD"})
    assert verdicts[10].reason == "flag_bad"
    assert verdicts[10].flags == ("flag_bad", "outside_physical_limits", "outside_typical_range")


def test_priority_order_follows_the_declared_codes() -> None:
    values = noise(30, 7.6, 0.0485)
    values[10] = None
    verdicts = run(SOLVENT_PH, values, 5.0, quality={10: "UNCERTAIN"})
    assert verdicts[10].reason == "no_value"
    assert verdicts[10].flags == ("no_value", "flag_uncertain")
    assert verdicts[10].flags_text == "no_value,flag_uncertain"


def test_every_flag_list_is_in_priority_order() -> None:
    order = {code: k for k, code in enumerate(cleaning_policy.FLAG_CODES)}
    values = noise(60, 100.0, 0.15)
    values[30] = 140.0
    pts = points(values, quality={30: "BAD"})
    for verdict in judge_numeric(VOLTAGE, pts, frozenset({pts[30].time_ns})):
        ranks = [order[code] for code in verdict.flags]
        assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------- states


def test_state_unknown_value_is_excluded() -> None:
    pts = points(["STARTUP", "STEADY_STATE", "WARMUP", "SHUTDOWN"])
    verdicts = judge_state(PROCESS_STATE, pts, NONE)
    assert [v.reason for v in verdicts] == ["", "", "unknown_state", ""]
    assert verdicts[2].flags == ("unknown_state",)


def test_state_acquisition_flags_and_conflicts() -> None:
    pts = points(["OPEN", "CLOSED", None, "OPEN"], quality={1: "BAD"})
    verdicts = judge_state(VALVE_STATE, pts, frozenset({pts[3].time_ns}))
    assert verdicts[0].accepted
    assert verdicts[1].reason == "flag_bad"
    assert verdicts[2].reason == "no_value"
    assert verdicts[3].reason == "conflicting_duplicate"


def test_judge_dispatches_on_the_table() -> None:
    state = judge(PROCESS_STATE, points(["STARTUP", "WARMUP"]), NONE)
    assert [v.reason for v in state] == ["", "unknown_state"]
    numeric = judge(VOLTAGE, points(noise(10, 100.0, 0.15)), NONE)
    assert all(v.accepted for v in numeric)


def test_state_series_has_no_numeric_rules() -> None:
    assert cleaning_policy.POLICY[PROCESS_STATE].states is not None
    pts = points(["STEADY_STATE"] * 50)  # a long hold is normal for a state signal
    assert all(v.accepted for v in judge_state(PROCESS_STATE, pts, NONE))


# ---------------------------------------------------------------------------- intervals


def test_gap_hole_of_10_s_in_a_1_hz_series_is_one_11_s_row() -> None:
    times = [*range(0, 400), *range(410, 600)]
    pts = [RawPoint(T0 + t * NS, 100.0, "GOOD") for t in times]
    gaps = gap_intervals(VOLTAGE, pts)
    assert gaps == [Interval(T0 + 399 * NS, T0 + 410 * NS)]
    assert gaps[0].seconds == 11.0
    assert len(pts) == 590  # nothing invented


def test_gap_threshold_is_over_twice_nominal() -> None:
    twice = [RawPoint(T0 + t * NS, 1.0, "GOOD") for t in (0, 1, 3, 4)]  # a 2 s spacing
    thrice = [RawPoint(T0 + t * NS, 1.0, "GOOD") for t in (0, 1, 4, 5)]  # a 3 s spacing
    assert gap_intervals(VOLTAGE, twice) == []
    assert len(gap_intervals(VOLTAGE, thrice)) == 1
    slow = [RawPoint(T0 + t * NS, 1.0, "GOOD") for t in (0, 5, 16, 21)]  # 0.2 Hz: 10 s limit
    assert gap_intervals(SOLVENT_PH, slow) == [Interval(T0 + 5 * NS, T0 + 16 * NS)]


def test_no_gap_rows_for_on_change_signals() -> None:
    pts = points(["STARTUP", "STEADY_STATE", "SHUTDOWN"], 1000.0)
    assert gap_intervals(PROCESS_STATE, pts) is None
    assert gap_intervals(VALVE_STATE, pts) is None


def test_flatline_intervals_one_row_per_run() -> None:
    values = noise(100, 31.0, 0.285)
    for k in range(20, 60):
        values[k] = 30.22
    for k in range(70, 80):
        values[k] = 31.5
    pts = points(values, 5.0)
    verdicts = judge_numeric(SOLVENT_TEMP, pts, NONE)
    runs = flatline_intervals(SOLVENT_TEMP, pts, verdicts)
    assert runs == [
        Interval(T0 + 100 * NS, T0 + 295 * NS, 40),
        Interval(T0 + 350 * NS, T0 + 395 * NS, 10),
    ]


def test_flatline_interval_that_runs_to_the_series_end_is_closed() -> None:
    values = noise(40, 31.0, 0.285) + [31.0] * 12
    pts = points(values, 5.0)
    verdicts = judge_numeric(SOLVENT_TEMP, pts, NONE)
    assert flatline_intervals(SOLVENT_TEMP, pts, verdicts) == [
        Interval(T0 + 200 * NS, T0 + 255 * NS, 12)
    ]


def test_flatline_intervals_none_where_the_rule_does_not_apply() -> None:
    pts = points([150.0] * 30)
    verdicts = judge_numeric(SETPOINT, pts, NONE)
    assert flatline_intervals(SETPOINT, pts, verdicts) is None
    clean = points(noise(30, 100.0, 0.15))
    assert flatline_intervals(VOLTAGE, clean, judge_numeric(VOLTAGE, clean, NONE)) == []


def test_state_intervals_are_carried_forward_without_expiry() -> None:
    offsets = [0, 120, 400, 540]
    pts = [
        RawPoint(T0 + t * NS, v, "GOOD")
        for t, v in zip(offsets, ["STARTUP", "STEADY_STATE", "WARMUP", "SHUTDOWN"], strict=True)
    ]
    intervals = state_intervals(pts, T0 + 600 * NS)
    assert [i.seconds for i in intervals] == [120.0, 280.0, 140.0, 60.0]
    assert intervals[-1].end_ns == T0 + 600 * NS
    assert intervals[1].start_ns == T0 + 120 * NS and intervals[1].end_ns == T0 + 400 * NS


def test_state_interval_of_a_single_event_runs_to_the_experiment_end() -> None:
    pts = [RawPoint(T0, "OPEN", "GOOD")]
    (interval,) = state_intervals(pts, T0 + 600 * NS)
    assert interval.seconds == 600.0
    assert state_intervals([], T0 + 600 * NS) == []


def test_unknown_state_keeps_its_interval() -> None:
    pts = points(["STARTUP", "WARMUP", "SHUTDOWN"], 100.0)
    verdicts = judge_state(PROCESS_STATE, pts, NONE)
    intervals = state_intervals(pts, T0 + 300 * NS)
    assert verdicts[1].reason == "unknown_state"
    assert [i.seconds for i in intervals] == [100.0, 100.0, 100.0]


# ---------------------------------------------------------------------------- summary


def _voltage_series():
    values = noise(60, 100.0, 0.15)
    values[20] = 140.0
    values[40] = 100.0
    pts = points(values, quality={40: "BAD"})
    return pts, judge_numeric(VOLTAGE, pts, NONE)


def test_summarise_series_reconciles() -> None:
    pts, verdicts = _voltage_series()
    result = summarise_series("EXP_001", VOLTAGE, pts, verdicts)
    assert result.raw_points == len(pts) == 60
    assert result.raw_points == result.accepted + result.excluded
    assert result.excluded == sum(result.excluded_by_reason.values()) == 2
    assert result.excluded_by_reason["spike"] == 1
    assert result.excluded_by_reason["flag_bad"] == 1
    assert set(result.excluded_by_reason) == set(REASON_CODES)
    assert result.flags["outside_typical_range"] == 1
    assert result.flags["spike"] == 1
    assert result.gaps == [] and result.flatlines == []
    assert result.table == "readings_numeric"
    assert result.key == ("EXP_001", "hydrolyzer", "voltage")


def test_summarise_state_series_has_no_gap_or_flatline_blocks() -> None:
    pts = points(["STARTUP", "WARMUP"], 100.0)
    verdicts = judge_state(PROCESS_STATE, pts, NONE)
    result = summarise_series("EXP_001", PROCESS_STATE, pts, verdicts)
    assert result.gaps is None
    assert result.flatlines is None
    assert result.table == "readings_state"
    assert result.excluded_by_reason["unknown_state"] == 1


def _full_summary(short_by: int = 0) -> tuple[dict, list]:
    pts, verdicts = _voltage_series()
    volts = summarise_series("EXP_001", VOLTAGE, pts, verdicts)
    volts.processed_points = volts.raw_points
    volts.processed_with_value = volts.accepted
    state_pts = points(["STARTUP", "STEADY_STATE", "WARMUP"], 100.0)
    state_verdicts = judge_state(PROCESS_STATE, state_pts, NONE)
    state = summarise_series("EXP_001", PROCESS_STATE, state_pts, state_verdicts)
    state.processed_points = state.raw_points - short_by
    state.processed_with_value = state.accepted
    samples = []
    for index in pick_sample_indices(len([v for v in verdicts if not v.accepted])):
        excluded = [k for k, v in enumerate(verdicts) if not v.accepted]
        samples.append(sample_record("EXP_001", VOLTAGE, excluded[index], pts, verdicts))
    summary = build_summary(
        policy_version=POLICY_VERSION,
        database="dac_raw",
        experiments_file="data/raw/experiments.json",
        experiments=[
            {
                "experiment_id": "EXP_001",
                "start": instant_text(T0),
                "end": instant_text(T0 + 600 * NS),
            }
        ],
        results=[state, volts],  # deliberately out of order
        raw_unchanged=True,
        samples=samples,
        seconds=1.23456,
        queries=7,
        points_written=123,
    )
    return summary, [volts, state]


def test_build_summary_totals_reconcile_with_the_series() -> None:
    summary, _ = _full_summary()
    series = summary["series"]
    assert [s["signal"] for s in series] == ["voltage", "process_state"]  # sorted by key
    for s in series:
        assert s["raw_points"] == s["accepted"] + s["excluded"]
        assert s["excluded"] == sum(s["excluded_by_reason"].values())
    totals = summary["totals"]
    assert totals["raw_points"] == sum(s["raw_points"] for s in series) == 63
    assert totals["accepted"] + totals["excluded"] == totals["raw_points"]
    assert totals["excluded"] == sum(totals["excluded_by_reason"].values())
    assert totals["excluded_by_reason"]["spike"] == 1
    assert totals["excluded_by_reason"]["unknown_state"] == 1
    assert totals["flags"]["outside_typical_range"] == 1
    assert totals["gap_intervals"] == 0 and totals["flatline_intervals"] == 0
    assert summary["policy_version"] == POLICY_VERSION
    assert summary["reconciliation"] == {
        "balanced": True,
        "series_checked": 2,
        "unbalanced": [],
        "raw_unchanged": True,
    }
    assert summary["timing"] == {"seconds": 1.235, "queries": 7, "points_written": 123}


def test_build_summary_lists_an_unbalanced_series() -> None:
    summary, _ = _full_summary(short_by=1)
    recon = summary["reconciliation"]
    assert recon["balanced"] is False
    assert recon["unbalanced"] == [
        {
            "experiment_id": "EXP_001",
            "source": "plant",
            "signal": "process_state",
            "raw_points": 3,
            "processed_points": 2,
        }
    ]


def test_series_balances_only_when_both_counts_match() -> None:
    pts, verdicts = _voltage_series()
    result = summarise_series("EXP_001", VOLTAGE, pts, verdicts)
    assert not result.balanced  # nothing read back yet
    result.processed_points = result.raw_points
    result.processed_with_value = result.accepted + 1  # an excluded row kept a value
    assert not result.balanced
    result.processed_with_value = result.accepted
    assert result.balanced


def test_summary_gap_and_flatline_blocks() -> None:
    times = [*range(0, 30), *range(40, 70)]
    values = noise(60, 100.0, 0.15)
    pts = [RawPoint(T0 + t * NS, v, "GOOD") for t, v in zip(times, values, strict=True)]
    result = summarise_series("EXP_001", VOLTAGE, pts, judge_numeric(VOLTAGE, pts, NONE))
    block = cleaning.series_json(result)
    assert block["gaps"] == {
        "count": 1,
        "seconds": 11.0,
        "longest": [
            {
                "start": instant_text(T0 + 29 * NS),
                "end": instant_text(T0 + 40 * NS),
                "seconds": 11.0,
            }
        ],
    }
    assert block["flatline_intervals"] == {"count": 0, "seconds": 0.0}


def test_summary_validates_against_the_contract() -> None:
    summary, _ = _full_summary()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(summary, schema)
    summary["reconciliation"]["balanced"] = "yes"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(summary, schema)


def test_report_renders_the_summary_numbers() -> None:
    summary, _ = _full_summary()
    text = render_report(summary)
    assert POLICY_VERSION in text
    assert "## Hand-check samples" in text
    assert "spike" in text


def test_instant_text_writes_a_fraction_only_when_there_is_one() -> None:
    assert instant_text(T0) == "2026-05-04T08:00:00Z"
    assert instant_text(T0 + 500_000_000) == "2026-05-04T08:00:00.5Z"
    assert instant_text(T0 + 1) == "2026-05-04T08:00:00.000000001Z"


# ---------------------------------------------------------------------------- samples


def test_pick_sample_indices_first_middle_last() -> None:
    assert pick_sample_indices(0) == []
    assert pick_sample_indices(1) == [0]
    assert pick_sample_indices(2) == [0, 1]
    assert pick_sample_indices(3) == [0, 1, 2]
    assert pick_sample_indices(10) == [0, 5, 9]
    assert pick_sample_indices(11) == [0, 5, 10]


def test_sample_record_has_up_to_five_neighbours_each_side() -> None:
    values = noise(30, 100.0, 0.15)
    values[15] = 140.0
    pts = points(values)
    verdicts = judge_numeric(VOLTAGE, pts, NONE)
    record = sample_record("EXP_001", VOLTAGE, 15, pts, verdicts)
    assert record["reason"] == "spike"
    assert record["value_raw"] == 140.0
    assert record["time"] == instant_text(T0 + 15 * NS)
    assert [n["time"] for n in record["neighbours"]] == [
        instant_text(T0 + k * NS) for k in [*range(10, 15), *range(16, 21)]
    ]
    assert all(n["verdict"] == "accepted" for n in record["neighbours"])
    assert {record["experiment_id"], record["source"], record["signal"]} == {
        "EXP_001",
        "hydrolyzer",
        "voltage",
    }


def test_sample_record_truncates_at_the_series_ends_and_shows_raw_values() -> None:
    values = noise(8, 100.0, 0.15)
    values[1] = 140.0
    values[2] = None
    pts = points(values)
    verdicts = judge_numeric(VOLTAGE, pts, NONE)
    record = sample_record("EXP_001", VOLTAGE, 1, pts, verdicts)
    assert len(record["neighbours"]) == 1 + 5  # one before, five after
    assert record["neighbours"][1]["value_raw"] is None
    assert record["neighbours"][1]["verdict"] == "excluded"
    last = sample_record("EXP_001", VOLTAGE, 7, pts, verdicts)
    assert len(last["neighbours"]) == 5
