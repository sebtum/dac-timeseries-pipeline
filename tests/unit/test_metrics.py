"""Unit tests for the M4 metric functions (S4.3, S4.6, S4.8, S4.10, S4.11, S4.22).

Every formula is checked on a small hand-built series with the arithmetic written out. Times are
written in seconds and turned into ns by `ns()`; a bare `1` ns offset marks an exact boundary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline import metrics as m
from pipeline.signals import DECLARED_SIGNALS

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = json.loads((REPO_ROOT / "contracts" / "metrics_summary.schema.json").read_text("utf-8"))

# Pinned with the version: editing any number in POLICY changes the fingerprint, so the test
# fails until this line and METRICS_VERSION are updated together.
PINNED_VERSION = "m4-v1"
PINNED_FINGERPRINT = "ac004cddaaebee8786dd70517f0173430d6931a53b9aecf27f15e06569bb518b"

S = 1_000_000_000


def ns(seconds: float) -> int:
    return round(seconds * S)


def series(*points: tuple[float, float]) -> list[tuple[int, float]]:
    """Series from `(seconds, value)` pairs."""
    return [(ns(t), v) for t, v in points]


def const(value: float, times: list[float]) -> list[tuple[int, float]]:
    return [(ns(t), value) for t in times]


def rng(start: int, stop: int, step: int = 1) -> list[float]:
    """Whole seconds start..stop inclusive."""
    return list(range(start, stop + 1, step))


# CO2 captured per hour at flow 1200 m3/h, co2_in 420, co2_out 105 ppm, 1013.25 hPa, 15 degC.
#   p = 1013.25 hPa x 100 = 101325 Pa; T = 15 + 273.15 = 288.15 K
#   p x M = 101325 x 0.04401 = 4459.31325;  R x T = 8.314462618 x 288.15 = 2395.8124033767
#   kg of CO2 per m3 of air per unit mole fraction = 4459.31325 / 2395.8124033767 = 1.861294834...
#   captured: 1200 x (420 - 105) x 1e-6 = 0.378 m3/h of CO2  ->  0.378 x 1.8612948 = 0.7035694 kg/h
#   inlet:    1200 x 420 x 1e-6 = 0.504 m3/h of CO2          ->  0.504 x 1.8612948 = 0.9380926 kg/h
RATE_KG_H = 0.703569447309087
INLET_KG_H = 0.938092596412116


# -------------------------------------------------------------- S4.22 policy, version, fingerprint


def test_version_and_fingerprint_are_pinned() -> None:
    canonical = json.dumps(m.POLICY, sort_keys=True, separators=(",", ":"))
    assert m.METRICS_VERSION == "m4-v1" == PINNED_VERSION
    assert m.METRICS_FINGERPRINT == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert m.METRICS_FINGERPRINT == m.policy_fingerprint()
    assert m.METRICS_FINGERPRINT == PINNED_FINGERPRINT


def test_policy_values_are_the_decided_constants() -> None:
    assert m.POLICY == {
        "power_max_spacing_s": 2,
        "capture_max_spacing_s": 4,
        "ambient_max_age_s": 120,
        "power_tol_rel": 0.01,
        "power_tol_w": 10,
        "complete_coverage": 0.95,
        "co2_molar_mass_kg_per_mol": 0.04401,
        "gas_constant_j_per_mol_k": 8.314462618,
        "sec_floor_kwh_per_kg": 0.10,
        "energy_agreement_rel": 0.01,
    }
    assert m.KELVIN_OFFSET == 273.15


def test_policy_keys_equal_the_contract_parameters() -> None:
    parameters = SCHEMA["properties"]["parameters"]
    assert set(m.POLICY) == set(parameters["properties"]) == set(parameters["required"])


def test_names_and_units_match_the_contract() -> None:
    experiment = SCHEMA["$defs"]["experiment"]["properties"]
    assert list(m.METRIC_UNITS) == experiment["metrics"]["required"]
    assert len(m.METRIC_UNITS) == 13
    assert set(m.METRIC_UNITS.values()) <= set(
        SCHEMA["$defs"]["metric"]["properties"]["unit"]["enum"]
    )
    assert set(m.SERIES_UNITS) == set(experiment["series_written"]["required"])
    assert len(m.SERIES_UNITS) == 4
    assert m.SERIES_UNITS == {
        "power_computed": "W",
        "power_residual": "W",
        "capture_efficiency": "fraction",
        "capture_rate": "kg/h",
    }
    checks = experiment["plausibility"]["items"]["properties"]["check"]["enum"]
    assert list(m.PLAUSIBILITY_CHECKS) == checks == sorted(checks)


# ------------------------------------------------------------------ power series and residual


def test_power_series_exists_only_where_both_inputs_exist() -> None:
    voltage = series((0, 100), (1, 100.5), (2, 101), (3, 101))
    current = series((0, 150), (2, 151), (3, 152))  # no current at +1 s (BAD or missing)
    # 0 s: 100 x 150 = 15000;  2 s: 101 x 151 = 15251;  3 s: 101 x 152 = 15352
    assert m.power_series(voltage, current) == series((0, 15000), (2, 15251), (3, 15352))
    assert m.power_series([], current) == []


def test_residual_needs_all_three_and_is_logged_minus_computed() -> None:
    voltage = series((0, 100), (1, 100), (2, 100))
    current = series((0, 150), (1, 150), (2, 150))
    power = series((0, 15000), (2, 15250), (5, 15000))  # no logged power at +1 s
    # 0 s: 15000 - 100 x 150 = 0;  2 s: 15250 - 15000 = +250;  5 s has no voltage or current
    assert m.residual_series(power, voltage, current) == series((0, 0), (2, 250))


def test_residual_tolerance_example() -> None:
    ui = 15000.0  # limit = 0.01 x 15000 + 10 = 160 W
    assert not m.within_tolerance(250.0, ui)
    assert m.within_tolerance(150.0, ui)
    assert m.within_tolerance(-150.0, ui)
    assert not m.within_tolerance(-250.0, ui)
    assert m.within_tolerance(160.0, ui)  # at the limit
    assert not m.within_tolerance(160.001, ui)
    assert m.within_tolerance(10.0, 0.0)  # at zero power only the 10 W floor applies
    assert not m.within_tolerance(10.001, 0.0)
    assert m.within_tolerance(0.0, -15000.0)


# ------------------------------------------------------------------ S4.3 spacing rule


def test_s4_3_power_spacings_1s_2s_bridged_2s_plus_1ns_and_3s_not() -> None:
    points = [
        (0, 10.0),
        (ns(1), 20.0),  # spacing 1 s: bridged
        (ns(3), 30.0),  # spacing 2 s: bridged (at the limit)
        (ns(5) + 1, 40.0),  # spacing 2 s + 1 ns: not bridged
        (ns(8) + 1, 50.0),  # spacing 3 s: not bridged
    ]
    # 1 s: (10 + 20) / 2 x 1 = 15;  2 s: (20 + 30) / 2 x 2 = 50;  integral 65 over 3 s covered
    assert m.integrate(points, 2) == (65.0, 3.0)
    assert m.covered_intervals(points, 2) == [(0, ns(3))]


def test_s4_3_one_ns_past_the_limit_is_not_bridged_and_the_limit_is() -> None:
    assert m.integrate([(0, 5.0), (ns(2) + 1, 5.0)], 2) == (0.0, 0.0)
    assert m.integrate([(0, 5.0), (ns(2), 5.0)], 2) == (10.0, 2.0)
    assert m.covered_intervals([(0, 5.0), (ns(2) + 1, 5.0)], 2) == []


def test_s4_3_capture_spacings_4s_bridged_6s_not() -> None:
    points = series((0, 10), (4, 20), (10, 30))
    # 4 s: (10 + 20) / 2 x 4 = 60 over 4 s;  the 6 s spacing is skipped
    assert m.integrate(points, 4) == (60.0, 4.0)
    assert m.covered_intervals(points, 4) == [(0, ns(4))]


def test_covered_intervals_merge_runs_and_split_at_gaps() -> None:
    points = const(1.0, [0, 1, 2, 5, 6, 9, 20, 21])
    # spacings: 1,1 bridged -> [0,2]; 3 gap; 1 bridged -> [5,6]; 3 gap; 11 gap; 1 -> [20,21]
    assert m.covered_intervals(points, 2) == [(0, ns(2)), (ns(5), ns(6)), (ns(20), ns(21))]
    assert m.covered_intervals([], 2) == []
    assert m.covered_intervals([(0, 1.0)], 2) == []


def test_integrate_is_not_scaled_up_for_the_gap() -> None:
    # 600 s run, points at 0..300 and 316..600: a 16 s gap, covered 300 + 284 = 584 s.
    points = const(15000.0, rng(0, 300) + rng(316, 600))
    integral, covered = m.integrate(points, 2)
    assert covered == 584.0
    assert integral == 15000.0 * 584  # = 8,760,000 W s; not 15000 x 600
    assert covered / 600 == pytest.approx(0.9733, abs=1e-4)


# ------------------------------------------------------------------ overlap and integrate_over


def test_overlap_of_two_interval_lists() -> None:
    a = [(0, 10), (20, 30)]
    b = [(5, 25), (28, 40)]
    # [0,10] n [5,25] = [5,10];  [20,30] n [5,25] = [20,25];  [20,30] n [28,40] = [28,30]
    assert m.overlap(a, b) == [(5, 10), (20, 25), (28, 30)]
    assert m.overlap(a, []) == []
    assert m.overlap([(0, 5)], [(5, 9)]) == []  # touching at a point: zero length, dropped


S4_10_POWER = [(0, 299), (311, 449), (452, 599)]
S4_10_CAPTURE = [(0, 360), (420, 498), (504, 598)]
S4_10_OVERLAP = [(0, 299), (311, 360), (420, 449), (452, 498), (504, 598)]


def _to_ns(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(ns(a), ns(b)) for a, b in intervals]


def test_s4_10_overlap_of_the_scenario_intervals() -> None:
    result = m.overlap(_to_ns(S4_10_POWER), _to_ns(S4_10_CAPTURE))
    assert result == _to_ns(S4_10_OVERLAP)
    # 299 + 49 + 29 + 46 + 94 = 517 s
    assert sum(b - a for a, b in S4_10_OVERLAP) == 517
    assert m._seconds(result) == 517.0


def test_s4_10_integrate_over_clips_with_interpolated_endpoints() -> None:
    # v(t) = t at every even second of the capture-covered intervals: a straight line, so the
    # interpolant is exact at odd clip points such as 299, 311, 449 and 499.
    times = rng(0, 360, 2) + rng(420, 498, 2) + rng(504, 598, 2)
    line = [(ns(t), float(t)) for t in times]
    # integral of t dt over [a, b] = (b^2 - a^2) / 2
    #   299^2 = 89401;  360^2 - 311^2 = 129600 - 96721 = 32879
    #   449^2 - 420^2 = 201601 - 176400 = 25201
    #   498^2 - 452^2 = 248004 - 204304 = 43700;  598^2 - 504^2 = 357604 - 254016 = 103588
    #   (89401 + 32879 + 25201 + 43700 + 103588) / 2 = 294769 / 2 = 147384.5
    assert m.integrate_over(line, _to_ns(S4_10_OVERLAP)) == pytest.approx(147384.5, abs=1e-6)


def test_integrate_over_clipped_interval_between_points() -> None:
    points = series((0, 10), (10, 20))  # v = 10 + t
    # [2, 6]: v(2) = 12, v(6) = 16;  (12 + 16) / 2 x 4 = 56
    assert m.integrate_over(points, [(ns(2), ns(6))]) == 56.0
    # the whole span: (10 + 20) / 2 x 10 = 150
    # two pieces [0,3] and [7,10]: 3 x (10 + 13) / 2 + 3 x (17 + 20) / 2 = 34.5 + 55.5 = 90
    assert m.integrate_over(points, [(0, ns(10))]) == 150.0
    assert m.integrate_over(points, [(0, ns(3)), (ns(7), ns(10))]) == pytest.approx(90.0)
    assert m.integrate_over(points, []) == 0.0


def test_integrate_over_keeps_interior_points() -> None:
    points = series((0, 0), (5, 10), (10, 0))  # a triangle
    # [2, 8]: v(2) = 4, v(5) = 10, v(8) = 4;  (4 + 10) / 2 x 3 + (10 + 4) / 2 x 3 = 42
    assert m.integrate_over(points, [(ns(2), ns(8))]) == 42.0


def test_integrate_over_rejects_an_interval_outside_the_series() -> None:
    with pytest.raises(ValueError):
        m.integrate_over(series((0, 1), (10, 1)), [(ns(5), ns(11))])


# ------------------------------------------------------------------ S4.6 efficiency


def test_s4_6_efficiency_at_or_below_zero_is_kept_and_counted() -> None:
    co2_in = const(400.0, [0, 2, 4])
    co2_out = series((0, 400), (2, 410), (4, 100))
    eff = m.efficiency_series(co2_in, co2_out)
    # 0 s: (400 - 400) / 400 = 0.0;  2 s: (400 - 410) / 400 = -0.025;  4 s: 300 / 400 = 0.75
    assert eff == series((0, 0.0), (2, -0.025), (4, 0.75))
    result = m.experiment_metrics(m.ExperimentInputs(co2_in=co2_in, co2_out=co2_out), 10)
    assert result.efficiency_check == {"instants": 3, "at_or_below_zero": 2}
    # the mean keeps them: (0 - 0.025 + 0.75) / 3
    assert result.metrics["capture_efficiency_mean"]["value"] == pytest.approx(0.725 / 3)


def test_efficiency_joins_on_the_same_instant_and_skips_zero_inlet() -> None:
    co2_in = series((0, 400), (2, 0), (4, 400))
    co2_out = series((0, 100), (2, 0), (6, 100))
    # only 0 s is joined with a non-zero inlet: 4 s has no outlet, 6 s no inlet, 2 s divides by 0
    assert m.efficiency_series(co2_in, co2_out) == series((0, 0.75))


# ------------------------------------------------------------------ S4.8 as-of ambient


def test_as_of_age_limit_is_exact() -> None:
    temp = series((240, 15.0), (420, 16.0))
    limit = 120 * S
    assert m.as_of(temp, ns(360), limit) == 15.0  # age 120 s: used
    assert m.as_of(temp, ns(360) + 1, limit) is None  # age 120 s + 1 ns: not used
    assert m.as_of(temp, ns(362), limit) is None  # age 122 s
    assert m.as_of(temp, ns(420), limit) == 16.0  # age 0 s
    assert m.as_of(temp, ns(239), limit) is None  # before the first reading
    assert m.as_of([], ns(1), limit) is None


def test_s4_8_capture_uses_ambient_up_to_120_s_old() -> None:
    temp = series((240, 15.0), (420, 15.0))
    press = series((240, 1013.25), (420, 1013.25))
    co2_in = const(420.0, [360, 362, 420])
    co2_out = const(105.0, [360, 362, 420])
    flow = const(1200.0, [360, 362, 420])
    out = m.capture_series(co2_in, co2_out, flow, temp, press)
    # +360 s: age 120 s -> value;  +362 s: age 122 s -> none;  +420 s: age 0 s -> value
    assert [t for t, _ in out] == [ns(360), ns(420)]


def test_capture_needs_both_ambient_readings() -> None:
    co2_in, co2_out, flow = const(420.0, [0]), const(105.0, [0]), const(1200.0, [0])
    assert m.capture_series(co2_in, co2_out, flow, [], series((0, 1013.25))) == []
    assert m.capture_series(co2_in, co2_out, flow, series((0, 15.0)), []) == []


# ------------------------------------------------------------------ capture rate formula


def test_capture_rate_matches_the_hand_computation() -> None:
    args = (
        const(420.0, [0]),
        const(105.0, [0]),
        const(1200.0, [0]),
        series((0, 15.0)),
        series((0, 1013.25)),
    )
    [(t, rate)] = m.capture_series(*args)
    [(t_in, inlet)] = m.capture_series(*args, inlet=True)
    assert t == t_in == 0
    assert rate == pytest.approx(RATE_KG_H, rel=1e-12)
    assert inlet == pytest.approx(INLET_KG_H, rel=1e-12)
    assert rate / inlet == pytest.approx(315 / 420)


def test_capture_rate_follows_ambient_conditions_not_a_fixed_density() -> None:
    def rate_at(temp_c: float) -> float:
        out = m.capture_series(
            const(420.0, [0]),
            const(105.0, [0]),
            const(1200.0, [0]),
            series((0, temp_c)),
            series((0, 1013.25)),
        )
        return out[0][1]

    # ideal gas: rate x T is constant at fixed pressure
    assert rate_at(-5.0) * (-5.0 + 273.15) == pytest.approx(rate_at(30.0) * (30.0 + 273.15))
    assert rate_at(-5.0) > rate_at(30.0)


def test_inlet_series_covers_the_same_instants_as_the_captured_series() -> None:
    co2_in = const(420.0, [0, 2, 4])
    co2_out = const(105.0, [0, 4])  # no outlet at +2 s
    flow = const(1200.0, [0, 2, 4])
    ambient = (series((0, 15.0)), series((0, 1013.25)))
    cap = m.capture_series(co2_in, co2_out, flow, *ambient)
    inl = m.capture_series(co2_in, co2_out, flow, *ambient, inlet=True)
    assert [t for t, _ in cap] == [t for t, _ in inl] == [0, ns(4)]


# ------------------------------------------------------------------ S4.11 labels


def test_s4_11_labels_follow_the_coverage_at_the_boundary() -> None:
    assert m.status_for(1.0, 0.95) == "complete"
    assert m.status_for(1.0, 0.9499999) == "partial"
    assert m.status_for(1.0, 0.0) == "partial"
    assert m.status_for(None, 0.95) == "none"
    assert m.status_for(None, 0.0) == "none"
    assert m.status_for(0.0, 1.0) == "complete"  # a zero value is still a value
    assert m.status_for(1.0, 570 / 600) == "complete"


# ------------------------------------------------------------------ a whole small experiment

# 20 s experiment.
#   voltage 100 V and current 150 A at 0..9 s and 12..19 s  -> computed power 15000 W, covered
#   [0,9] + [12,19] = 16 s;  logged power at 0..19 s: 15000 W, except +150 W at 3 s and
#   +250 W at 5 s.
#   co2_in 420 and co2_out 105 at even seconds 0..18, air flow 1200 at 0..19, 15 degC, 1013.25 hPa
#   at 0 s (as-of 120 s)  -> capture rate constant at RATE_KG_H, covered [0,18] = 18 s.
DURATION = 20.0


def small_inputs() -> m.ExperimentInputs:
    live = rng(0, 9) + rng(12, 19)
    logged = {t: 15000.0 for t in rng(0, 19)}
    logged[3] = 15150.0
    logged[5] = 15250.0
    even = rng(0, 18, 2)
    return m.ExperimentInputs(
        voltage=const(100.0, live),
        current=const(150.0, live),
        power=[(ns(t), v) for t, v in sorted(logged.items())],
        co2_in=const(420.0, even),
        co2_out=const(105.0, even),
        air_flow=const(1200.0, rng(0, 19)),
        temperature=series((0, 15.0)),
        pressure=series((0, 1013.25)),
    )


def test_small_experiment_energy_and_power() -> None:
    result = m.experiment_metrics(small_inputs(), DURATION)
    metrics = result.metrics
    assert list(metrics) == list(m.METRIC_UNITS)
    # computed: 15000 W x 16 s = 240000 W s = 240000 / 3.6e6 = 0.0666667 kWh, coverage 16 / 20
    assert metrics["energy_kwh"] == {
        "value": pytest.approx(240000 / 3.6e6),
        "unit": "kWh",
        "coverage": 0.8,
        "status": "partial",
    }
    # logged over 0..19 s (19 s covered): 15000 x 19 = 285000, plus the two bumps: a bump of d W
    # at an interior point adds d x (0.5 + 0.5) s = d W s -> 150 + 250 = 400;  285400 / 3.6e6
    assert metrics["energy_logged_kwh"]["value"] == pytest.approx(285400 / 3.6e6)
    assert metrics["energy_logged_kwh"]["coverage"] == pytest.approx(19 / 20)
    assert metrics["energy_logged_kwh"]["status"] == "complete"
    # mean power = 0.0666667 kWh / (16 / 3600 h) = 15 kW
    assert metrics["mean_power_kw"]["value"] == pytest.approx(15.0)
    assert metrics["mean_power_kw"]["unit"] == "kW"
    assert metrics["mean_power_kw"]["coverage"] == 0.8


def test_small_experiment_energy_difference_is_taken_over_the_overlap() -> None:
    result = m.experiment_metrics(small_inputs(), DURATION)
    diff = result.metrics["energy_relative_difference"]
    # overlap = [0,9] + [12,19] = 16 s;  E_computed = 15000 x 16 = 240000;
    # E_logged over it = 15000 x 16 + 150 + 250 = 240400;  (240400 - 240000) / 240000
    assert diff["value"] == pytest.approx(400 / 240000)
    assert diff["coverage"] == 0.8
    assert diff["status"] == "partial"
    # taken over each series' own time instead, the logged energy over 19 s would differ by ~19 %
    own = (285400 - 240000) / 240000
    assert own > 0.18
    assert {p["check"]: p["passed"] for p in m.plausibility(result)}["energy_agreement"] is True


def test_small_experiment_power_check() -> None:
    check = m.experiment_metrics(small_inputs(), DURATION).power_check
    # instants with voltage, current and logged power: 0..9 and 12..19 = 18;
    # residuals: 0 everywhere except +150 W at 3 s (inside 160 W) and +250 W at 5 s (outside)
    assert check["instants_compared"] == 18
    assert check["within_tolerance"] == 17
    assert check["within_tolerance_fraction"] == pytest.approx(17 / 18)
    assert check["residual_median_w"] == 0.0
    assert check["residual_max_abs_w"] == 250.0
    # |residual| sorted: sixteen 0, 150, 250; position (18 - 1) x 0.95 = 16.15 -> 150 + 0.15 x 100
    assert check["residual_p95_abs_w"] == pytest.approx(165.0)


def test_small_experiment_capture_metrics() -> None:
    result = m.experiment_metrics(small_inputs(), DURATION)
    metrics = result.metrics
    # efficiency (420 - 105) / 420 = 0.75 at 10 instants, covered [0,18] = 18 s of 20
    assert metrics["capture_efficiency_mean"]["value"] == pytest.approx(0.75)
    assert metrics["capture_efficiency_mean"]["coverage"] == 0.9
    assert metrics["capture_efficiency_mean"]["status"] == "partial"
    # captured: 0.70357 kg/h x 18 s / 3600 = 0.0035178 kg;  inlet 0.93809 x 18 / 3600 = 0.0046905
    assert metrics["co2_captured_kg"]["value"] == pytest.approx(RATE_KG_H * 18 / 3600)
    assert metrics["co2_inlet_kg"]["value"] == pytest.approx(INLET_KG_H * 18 / 3600)
    assert metrics["co2_captured_kg"]["coverage"] == 0.9
    assert metrics["co2_inlet_kg"]["coverage"] == 0.9
    assert metrics["co2_captured_kg"]["unit"] == "kg"
    # mean rate = captured / (18 / 3600 h) = the constant rate
    assert metrics["capture_rate_mean_kg_h"]["value"] == pytest.approx(RATE_KG_H)
    assert metrics["capture_rate_mean_kg_h"]["unit"] == "kg/h"
    assert result.efficiency_check == {"instants": 10, "at_or_below_zero": 0}
    assert result.series_written() == {
        "power_computed": 18,
        "power_residual": 18,
        "capture_efficiency": 10,
        "capture_rate": 10,
    }


def test_small_experiment_energy_per_kg_uses_only_the_overlap() -> None:
    result = m.experiment_metrics(small_inputs(), DURATION)
    sec = result.metrics["sec_kwh_per_kg"]
    # power covered [0,9] + [12,19];  capture covered [0,18];  overlap [0,9] + [12,18] = 15 s
    #   energy 15000 W x 15 s / 3.6e6 = 0.0625 kWh;  CO2 0.70357 x 15 / 3600 = 0.0029315 kg
    #   0.0625 / 0.0029315 = 15 / 0.70357 = 21.32 kWh/kg
    assert sec["value"] == pytest.approx(15.0 / RATE_KG_H)
    assert sec["unit"] == "kWh/kg"
    assert sec["coverage"] == 0.75
    assert sec["status"] == "partial"


def test_energy_per_kg_is_null_with_an_empty_overlap() -> None:
    inputs = m.ExperimentInputs(
        voltage=const(100.0, rng(0, 10)),
        current=const(150.0, rng(0, 10)),
        co2_in=const(420.0, rng(100, 110, 2)),
        co2_out=const(105.0, rng(100, 110, 2)),
        air_flow=const(1200.0, rng(100, 110)),
        temperature=series((100, 15.0)),
        pressure=series((100, 1013.25)),
    )
    sec = m.experiment_metrics(inputs, 200.0).metrics["sec_kwh_per_kg"]
    assert sec == {"value": None, "unit": "kWh/kg", "coverage": 0.0, "status": "none"}


def test_energy_per_kg_is_null_when_captured_co2_is_not_positive() -> None:
    inputs = small_inputs()
    inputs.co2_out = const(420.0, rng(0, 18, 2))  # outlet equals inlet: captured 0
    metrics = m.experiment_metrics(inputs, DURATION).metrics
    assert metrics["co2_captured_kg"]["value"] == 0.0
    assert metrics["sec_kwh_per_kg"]["value"] is None
    assert metrics["sec_kwh_per_kg"]["status"] == "none"
    inputs.co2_out = const(500.0, rng(0, 18, 2))  # outlet above inlet: negative capture
    metrics = m.experiment_metrics(inputs, DURATION).metrics
    assert metrics["co2_captured_kg"]["value"] < 0
    assert metrics["sec_kwh_per_kg"]["value"] is None


def test_s4_11_status_of_the_whole_experiment_follows_the_coverage() -> None:
    # 600 s run, 584 s covered (16 s unbridged): energy_kwh coverage 0.9733 -> complete
    live = rng(0, 300) + rng(316, 600)
    inputs = m.ExperimentInputs(voltage=const(100.0, live), current=const(150.0, live))
    energy = m.experiment_metrics(inputs, 600.0).metrics["energy_kwh"]
    assert energy["coverage"] == pytest.approx(584 / 600)
    assert energy["status"] == "complete"
    # 15000 W x 584 s = 8,760,000 W s = 2.4333333 kWh
    assert energy["value"] == pytest.approx(8_760_000 / 3.6e6)
    # exactly 0.95: 570 s covered of 600 is complete
    inputs = m.ExperimentInputs(
        voltage=const(100.0, rng(0, 570)), current=const(150.0, rng(0, 570))
    )
    assert m.experiment_metrics(inputs, 600.0).metrics["energy_kwh"]["status"] == "complete"
    inputs = m.ExperimentInputs(
        voltage=const(100.0, rng(0, 569)), current=const(150.0, rng(0, 569))
    )
    assert m.experiment_metrics(inputs, 600.0).metrics["energy_kwh"]["status"] == "partial"


def test_empty_experiment_has_all_thirteen_metrics_as_null() -> None:
    result = m.experiment_metrics(m.ExperimentInputs(), 600.0)
    assert list(result.metrics) == list(m.METRIC_UNITS)
    for name, metric in result.metrics.items():
        assert metric["value"] is None
        assert metric["unit"] == m.METRIC_UNITS[name]
        if name in m.QUALITY_METRICS:
            assert metric["coverage"] is None and metric["status"] is None
        else:
            assert metric["coverage"] == 0.0 and metric["status"] == "none"
    assert result.power_check == {
        "instants_compared": 0,
        "within_tolerance": 0,
        "within_tolerance_fraction": None,
        "residual_median_w": None,
        "residual_p95_abs_w": None,
        "residual_max_abs_w": None,
    }
    assert result.efficiency_check == {"instants": 0, "at_or_below_zero": 0}
    assert result.series_written() == dict.fromkeys(m.SERIES_UNITS, 0)


def test_metric_objects_have_the_contract_fields() -> None:
    required = SCHEMA["$defs"]["metric"]["required"]
    result = m.experiment_metrics(small_inputs(), DURATION)
    assert all(list(metric) == required for metric in result.metrics.values())
    assert (
        list(result.power_check)
        == SCHEMA["$defs"]["experiment"]["properties"]["power_check"]["required"]
    )
    assert (
        list(result.efficiency_check)
        == SCHEMA["$defs"]["experiment"]["properties"]["efficiency_check"]["required"]
    )


# ------------------------------------------------------------------ quality shares


def counts_row(source: str, signal: str, quality: str, verdict: str, count: int) -> dict:
    return {
        "source": source,
        "signal": signal,
        "quality": quality,
        "verdict": verdict,
        "count": count,
    }


# The fixture's counts (S4.12, S4.13), 600 s run.
FIXTURE_COUNTS = [
    counts_row("absorber", "air_flow", "GOOD", "accepted", 600),
    counts_row("absorber", "co2_in_ppm", "GOOD", "accepted", 298),
    counts_row("absorber", "co2_in_ppm", "BAD", "excluded", 2),
    counts_row("absorber", "co2_out_ppm", "GOOD", "accepted", 299),
    counts_row("absorber", "co2_out_ppm", "UNCERTAIN", "excluded", 1),
    counts_row("ambient", "ambient_pressure", "GOOD", "accepted", 8),
    counts_row("ambient", "ambient_temperature", "GOOD", "accepted", 8),
    counts_row("hydrolyzer", "current", "GOOD", "accepted", 586),
    counts_row("hydrolyzer", "current", "BAD", "excluded", 1),
    counts_row("hydrolyzer", "power", "GOOD", "accepted", 589),
    counts_row("hydrolyzer", "voltage", "GOOD", "accepted", 589),
    counts_row("plant", "process_state", "GOOD", "accepted", 2),
]


def by_signal(entries: list[dict]) -> dict[str, dict]:
    return {e["signal"]: e for e in entries}


def test_signal_quality_lists_all_25_pairs_sorted() -> None:
    entries = m.signal_quality(FIXTURE_COUNTS, 600.0)
    assert len(entries) == 25
    keys = [(e["source"], e["signal"]) for e in entries]
    assert keys == sorted(keys)
    assert set(keys) == {(s, g) for s, gs in DECLARED_SIGNALS.items() for g in gs}
    contract = SCHEMA["$defs"]["signal"]["required"]
    assert all(list(e) == contract for e in entries)


def test_signal_quality_current_example() -> None:
    current = by_signal(m.signal_quality(FIXTURE_COUNTS, 600.0))["current"]
    # 587 present of 600 expected, 586 accepted, 1 BAD
    assert current["nominal_interval_s"] == 1.0
    assert (current["present"], current["expected"]) == (587, 600)
    assert (current["accepted"], current["bad"], current["uncertain"]) == (586, 1, 0)
    assert current["completeness"] == 587 / 600
    assert current["valid_fraction"] == 586 / 587
    assert current["bad_fraction"] == 1 / 587
    assert current["uncertain_fraction"] == 0.0


def test_signal_quality_other_fixture_signals() -> None:
    entries = by_signal(m.signal_quality(FIXTURE_COUNTS, 600.0))
    assert entries["co2_out_ppm"]["uncertain"] == 1
    assert entries["co2_out_ppm"]["expected"] == 300  # floor(600 / 2)
    assert entries["co2_out_ppm"]["uncertain_fraction"] == 1 / 300
    pressure = entries["ambient_pressure"]
    assert (pressure["present"], pressure["expected"]) == (8, 10)  # floor(600 / 60)
    assert pressure["completeness"] == 0.8
    assert entries["solvent_pH"]["expected"] == 120  # floor(600 / 5)


def test_signal_quality_on_change_signal_has_no_expected_count() -> None:
    state = by_signal(m.signal_quality(FIXTURE_COUNTS, 600.0))["process_state"]
    assert state["nominal_interval_s"] is None
    assert state["present"] == 2
    assert state["expected"] is None
    assert state["completeness"] is None
    assert state["valid_fraction"] == 1.0
    valve = by_signal(m.signal_quality(FIXTURE_COUNTS, 600.0))["valve_state"]
    assert (valve["present"], valve["expected"], valve["completeness"]) == (0, None, None)
    assert valve["valid_fraction"] is None


def test_signal_quality_pair_with_no_rows_has_present_zero_and_null_fractions() -> None:
    flow = by_signal(m.signal_quality(FIXTURE_COUNTS, 600.0))["flow"]
    assert (flow["present"], flow["expected"], flow["accepted"]) == (0, 600, 0)
    assert flow["completeness"] == 0.0
    assert flow["valid_fraction"] is flow["bad_fraction"] is flow["uncertain_fraction"] is None


def test_signal_quality_counts_a_good_but_excluded_row_as_present_not_accepted() -> None:
    counts = [
        counts_row("hydrolyzer", "voltage", "GOOD", "accepted", 8),
        counts_row("hydrolyzer", "voltage", "GOOD", "excluded", 2),  # e.g. a spike
    ]
    voltage = by_signal(m.signal_quality(counts, 10.0))["voltage"]
    assert (voltage["present"], voltage["accepted"], voltage["bad"]) == (10, 8, 0)
    assert voltage["valid_fraction"] == 0.8
    assert voltage["bad_fraction"] == 0.0


def test_signal_quality_zero_denominators_give_none_not_an_error() -> None:
    entries = m.signal_quality([], 0.5)  # floor(0.5 / 1) = 0 expected for a 1 Hz signal
    voltage = by_signal(entries)["voltage"]
    assert voltage["expected"] == 0
    assert voltage["completeness"] is None
    assert voltage["valid_fraction"] is None
    assert len(entries) == 25


def test_signal_quality_rejects_an_undeclared_pair() -> None:
    with pytest.raises(ValueError):
        m.signal_quality([counts_row("plant", "mystery", "GOOD", "accepted", 1)], 600.0)


def test_s4_13_experiment_quality_adds_up_over_the_signals() -> None:
    shares = m.experiment_quality(m.signal_quality(FIXTURE_COUNTS, 600.0))
    assert list(shares) == list(m.QUALITY_METRICS)
    # polled present: 600 + 298 + 2 + 299 + 1 + 8 + 8 + 587 + 589 + 589 = 2981 (process_state's 2
    # is on-change and left out);  expected: 9 x 600 + 4 x 300 + 6 x 120 + 4 x 10 = 7360
    assert shares["completeness"]["value"] == 2981 / 7360
    # all 25 pairs: present 2983, accepted 2979, BAD 3, UNCERTAIN 1
    assert shares["valid_fraction"]["value"] == 2979 / 2983
    assert shares["bad_fraction"]["value"] == 3 / 2983
    assert shares["uncertain_fraction"]["value"] == 1 / 2983
    for name, share in shares.items():
        assert share == {
            "value": share["value"],
            "unit": "fraction",
            "coverage": None,
            "status": None,
        }, name


def test_experiment_quality_with_no_rows_is_null() -> None:
    shares = m.experiment_quality([])
    assert [s["value"] for s in shares.values()] == [None, None, None, None]
    shares = m.experiment_quality(m.signal_quality([], 600.0))  # 25 pairs, nothing present
    assert shares["completeness"]["value"] == 0.0
    assert shares["valid_fraction"]["value"] is None


def test_experiment_metrics_takes_the_quality_shares_from_signals() -> None:
    inputs = small_inputs()
    inputs.signals = m.signal_quality(FIXTURE_COUNTS, 600.0)
    metrics = m.experiment_metrics(inputs, DURATION).metrics
    assert metrics["valid_fraction"]["value"] == 2979 / 2983
    assert metrics["completeness"]["status"] is None


# ------------------------------------------------------------------ plausibility


def result_with(**values: float | None) -> m.ExperimentResult:
    result = m.experiment_metrics(m.ExperimentInputs(), 600.0)
    for name, value in values.items():
        result.metrics[name]["value"] = value
    return result


def verdicts(result: m.ExperimentResult) -> dict[str, bool | None]:
    return {p["check"]: p["passed"] for p in m.plausibility(result)}


def test_plausibility_with_null_metrics_is_null_and_sorted() -> None:
    entries = m.plausibility(result_with())
    assert [e["check"] for e in entries] == [
        "capture_below_inlet",
        "efficiency_in_unit_interval",
        "energy_agreement",
        "sec_above_floor",
    ]
    assert all(e["passed"] is None and e["value"] is None for e in entries)
    assert all(list(e) == ["check", "passed", "value", "limit"] for e in entries)
    assert {e["check"]: e["limit"] for e in entries} == {
        "capture_below_inlet": 0.0,
        "efficiency_in_unit_interval": 1,
        "energy_agreement": 0.01,
        "sec_above_floor": 0.10,
    }


def test_plausibility_efficiency_mean_1_2_fails() -> None:
    entries = {e["check"]: e for e in m.plausibility(result_with(capture_efficiency_mean=1.2))}
    assert entries["efficiency_in_unit_interval"]["passed"] is False
    assert entries["efficiency_in_unit_interval"]["value"] == 1.2
    assert entries["efficiency_in_unit_interval"]["limit"] == 1


@pytest.mark.parametrize(
    ("value", "passed"),
    [(0.0, True), (0.75, True), (1.0, True), (1.0000001, False), (-0.0000001, False)],
)
def test_plausibility_efficiency_boundaries(value: float, passed: bool) -> None:
    assert (
        verdicts(result_with(capture_efficiency_mean=value))["efficiency_in_unit_interval"]
        is passed
    )


@pytest.mark.parametrize(
    ("captured", "inlet", "passed"),
    [
        (0.5, 1.0, True),
        (1.0, 1.0, True),
        (1.0001, 1.0, False),
        (None, 1.0, None),
        (1.0, None, None),
    ],
)
def test_plausibility_capture_below_inlet(
    captured: float | None, inlet: float | None, passed: bool | None
) -> None:
    result = result_with(co2_captured_kg=captured, co2_inlet_kg=inlet)
    entry = next(e for e in m.plausibility(result) if e["check"] == "capture_below_inlet")
    assert entry["passed"] is passed
    assert entry["value"] == captured


def test_plausibility_capture_below_inlet_reports_the_inlet_as_limit() -> None:
    result = result_with(co2_captured_kg=0.0963, co2_inlet_kg=0.1285)
    entry = next(e for e in m.plausibility(result) if e["check"] == "capture_below_inlet")
    assert (entry["value"], entry["limit"]) == (0.0963, 0.1285)


@pytest.mark.parametrize(
    ("value", "passed"), [(0.10, True), (23.02, True), (0.0999, False), (0.0, False), (-1.0, False)]
)
def test_plausibility_sec_floor(value: float, passed: bool) -> None:
    assert verdicts(result_with(sec_kwh_per_kg=value))["sec_above_floor"] is passed


@pytest.mark.parametrize(
    ("value", "passed"),
    [(0.0, True), (0.01, True), (-0.01, True), (0.0100001, False), (-0.0100001, False)],
)
def test_plausibility_energy_agreement(value: float, passed: bool) -> None:
    assert verdicts(result_with(energy_relative_difference=value))["energy_agreement"] is passed


def test_plausibility_of_the_small_experiment_passes_where_defined() -> None:
    assert verdicts(m.experiment_metrics(small_inputs(), DURATION)) == {
        "capture_below_inlet": True,
        "efficiency_in_unit_interval": True,
        "energy_agreement": True,
        "sec_above_floor": True,
    }
