"""Unit tests for pipeline/compare.py (M5): scenarios S5.1-S5.9 and every rule boundary.

Every test uses small hand-made series or exact planted relations; nothing needs a service.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import math
import random
from fractions import Fraction
from pathlib import Path

import pytest

from pipeline import compare as c
from pipeline.metrics import NS_PER_S

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((REPO_ROOT / "contracts" / "comparison_summary.schema.json").read_text("utf-8"))

PINNED_FINGERPRINT = "a0274e7e07bfda3c38e6aca3e2bd05821c23a6a46176e70c14da8489eb33db36"

S = NS_PER_S
FAST = {**c.POLICY, "bootstrap_resamples": 40}
PLANTED = (0.3, -0.1, -0.2, 3.0)  # current, electrolyte_temperature, flow, pressure
INTERCEPT = 40.0
HYDRO = c.MODELS["hydrolyzer"]


def ns(seconds: float) -> int:
    return round(seconds * S)


# ---------------------------------------------------------------------------- data builders


def make_rows(
    n: int,
    *,
    seed: int = 1,
    noise: float = 0.0,
    offset: float = 0.0,
    window_start: int = 0,
    step_s: float = 1.0,
    flow_fn=None,
    pressure_fn=None,
) -> c.Rows:
    """`n` hydrolyzer rows, voltage = 40 + 0.3 I - 0.1 T - 0.2 flow + 3 p (+ offset + noise)."""
    rng = random.Random(seed)
    rows = c.Rows(columns={name: [] for name in HYDRO})
    for i in range(n):
        current = rng.uniform(140, 160)
        temp = rng.uniform(30, 40)
        flow = rng.uniform(38, 42) if flow_fn is None else flow_fn(i, rng)
        pressure = rng.uniform(2.4, 2.6) if pressure_fn is None else pressure_fn(i, flow, rng)
        voltage = (
            INTERCEPT
            + PLANTED[0] * current
            + PLANTED[1] * temp
            + PLANTED[2] * flow
            + PLANTED[3] * pressure
            + offset
            + (rng.gauss(0, noise) if noise else 0.0)
        )
        rows.t.append(window_start + ns(i * step_s))
        rows.window_index.append(0)
        rows.window_start.append(window_start)
        rows.voltage.append(voltage)
        for name, value in zip(HYDRO, (current, temp, flow, pressure), strict=True):
            rows.columns[name].append(value)
    return rows


def naive_r2(rows: c.Rows, keep: list[str]) -> Fraction:
    """R squared of voltage on `keep` (with an intercept), in exact rational arithmetic."""
    n = len(rows)
    cols = [rows.columns[name] for name in keep]
    k = len(cols) + 1
    x = [[Fraction(1)] + [Fraction(col[i]) for col in cols] for i in range(n)]
    y = [Fraction(v) for v in rows.voltage]
    a = [[sum(x[r][i] * x[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    b = [sum(x[r][i] * y[r] for r in range(n)) for i in range(k)]
    beta = solve_exact(a, b)
    mean = sum(y) / n
    sse = sum((y[r] - sum(beta[i] * x[r][i] for i in range(k))) ** 2 for r in range(n))
    sst = sum((v - mean) ** 2 for v in y)
    return 1 - sse / sst


def naive_coefficients(rows: c.Rows, order: tuple[str, ...]) -> list[Fraction]:
    """Slopes (not the intercept) of voltage on `order` columns, in exact arithmetic."""
    n = len(rows)
    cols = [rows.columns[name] for name in order]
    k = len(cols) + 1
    x = [[Fraction(1)] + [Fraction(col[i]) for col in cols] for i in range(n)]
    y = [Fraction(v) for v in rows.voltage]
    a = [[sum(x[r][i] * x[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    b = [sum(x[r][i] * y[r] for r in range(n)) for i in range(k)]
    return solve_exact(a, b)[1:]


def solve_exact(a: list[list[Fraction]], b: list[Fraction]) -> list[Fraction]:
    k = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(k):
        piv = next(r for r in range(col, k) if m[r][col] != 0)
        m[col], m[piv] = m[piv], m[col]
        m[col] = [v / m[col][col] for v in m[col]]
        for r in range(k):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                m[r] = [m[r][i] - f * m[col][i] for i in range(k + 1)]
    return [m[i][k] for i in range(k)]


def term(entry: dict, name: str) -> dict:
    return next(t for t in entry["terms"] if t["name"] == name)


# ---------------------------------------------------------------------------- S5.9 policy


def test_compare_version_is_pinned():
    assert c.COMPARE_VERSION == "m5-v1"


def test_policy_keys_are_exactly_the_contract_parameters():
    assert set(c.POLICY) == set(SCHEMA["properties"]["parameters"]["properties"])
    assert set(c.POLICY) == set(SCHEMA["properties"]["parameters"]["required"])


def test_policy_values_match_the_plan():
    assert c.POLICY == {
        "settle_s": 60,
        "bootstrap_block_s": 120,
        "bootstrap_resamples": 1000,
        "bootstrap_seed": 20261124,
        "interval_level": 0.95,
        "lag_max_s": 60,
        "temp_max_age_s": 10,
        "min_instants": 300,
        "vif_limit": 10,
        "condition_tol_rel": 0.05,
        "ambient_tol_c": 5,
        "humidity_tol_pct": 15,
        "airflow_check_experiment": "EXP_004",
        "airflow_check_boundary": "2026-03-02T09:00:00Z",
    }


def test_fingerprint_is_the_sha256_of_the_canonical_policy_json():
    canonical = json.dumps(c.POLICY, sort_keys=True, separators=(",", ":"))
    assert c.COMPARE_FINGERPRINT == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert c.COMPARE_FINGERPRINT == c.policy_fingerprint()
    # Editing a number without bumping the version changes this and fails here.
    assert c.COMPARE_FINGERPRINT == PINNED_FINGERPRINT


def test_names_and_units_are_the_contract_ones():
    assert c.MODELS["hydrolyzer"] == ("current", "electrolyte_temperature", "flow", "pressure")
    assert c.MODELS["absorber"] == (
        "current",
        "electrolyte_temperature",
        "air_flow",
        "pressure_drop",
    )
    assert c.PREDICTOR_UNITS == {
        "current": "A",
        "electrolyte_temperature": "°C",
        "flow": "L/min",
        "pressure": "bar",
        "air_flow": "m³/h",
        "pressure_drop": "mbar",
    }
    assert list(c.KPI_UNITS) == list(SCHEMA["$defs"]["kpi_name"]["enum"])
    assert c.KPI_UNITS["sec_kwh_per_kg"] == "kWh/kg"
    assert list(c.FACTORS) == SCHEMA["$defs"]["factor_name"]["enum"]
    term_names = set(SCHEMA["$defs"]["term"]["properties"]["name"]["enum"])
    assert {n for names in c.MODELS.values() for n in names} == term_names


# ---------------------------------------------------------------------------- S5.1 time


def utc_ns(year, month, day, hour, minute, second=0):
    return calendar.timegm((year, month, day, hour, minute, second)) * S


def test_experiment_time_is_seconds_since_start_and_date_independent():
    first = utc_ns(2026, 5, 4, 8, 0)
    second = utc_ns(2026, 5, 11, 9, 0)
    assert c.experiment_time_s(utc_ns(2026, 5, 4, 8, 5), first) == 300.0
    assert c.experiment_time_s(utc_ns(2026, 5, 11, 9, 5), second) == 300.0


def test_experiment_time_keeps_sub_second_and_negative_offsets():
    start = utc_ns(2026, 5, 4, 8, 0)
    assert c.experiment_time_s(start + 1_500_000_000, start) == 1.5
    assert c.experiment_time_s(start - S, start) == -1.0
    assert c.experiment_time_s(start, start) == 0.0


# ---------------------------------------------------------------------------- S5.2 phases


def events(*items):
    return [(ns(a), ns(b), state) for a, b, state in items]


def test_phases_windows_trimmed_by_settle_margin():
    ev = events(
        (0, 120, "STARTUP"),
        (120, 600, "STEADY_STATE"),
        (600, 660, "LOAD_CHANGE"),
        (660, 1140, "STEADY_STATE"),
        (1140, 1200, "SHUTDOWN"),
    )
    ph = c.phases(ev, 60)
    assert [p.index for p in ph] == [0, 1, 2, 3, 4]
    assert [p.state for p in ph] == [
        "STARTUP",
        "STEADY_STATE",
        "LOAD_CHANGE",
        "STEADY_STATE",
        "SHUTDOWN",
    ]
    assert [(p.start_ns, p.end_ns) for p in ph] == [(a, b) for a, b, _ in ev]
    assert [p.window for p in ph] == [
        (ns(60), ns(120)),
        (ns(180), ns(600)),
        None,
        (ns(720), ns(1140)),
        None,
    ]
    assert c.steady_windows(ph) == [(ns(180), ns(600)), (ns(720), ns(1140))]


def test_settle_margin_boundary_60_s_gives_none_61_s_gives_one_second():
    exact = c.phases(events((600, 660, "LOAD_CHANGE")), 60)
    assert exact[0].window is None
    over = c.phases(events((600, 661, "LOAD_CHANGE")), 60)
    assert over[0].window == (ns(660), ns(661))
    one_ns = c.phases([(ns(600), ns(660) + 1, "X")], 60)
    assert one_ns[0].window == (ns(660), ns(660) + 1)


def test_phases_are_numbered_in_time_order_and_zero_settle_keeps_the_whole_phase():
    ph = c.phases(events((100, 200, "B"), (0, 100, "A")), 0)
    assert [(p.index, p.state) for p in ph] == [(0, "A"), (1, "B")]
    assert [p.window for p in ph] == [(0, ns(100)), (ns(100), ns(200))]


def test_steady_windows_only_from_steady_state_phases_with_a_window():
    ph = c.phases(events((0, 30, "STEADY_STATE"), (30, 300, "STEADY_STATE"), (300, 400, "X")), 60)
    assert c.steady_windows(ph) == [(ns(90), ns(300))]
    assert c.steady_windows([]) == []


# ---------------------------------------------------------------------------- instant join


def hydro_series(n=20, *, drop=None):
    series = {
        "voltage": [(ns(i), 80.0 + i) for i in range(n)],
        "current": [(ns(i), 150.0) for i in range(n)],
        "flow": [(ns(i), 40.0 + i) for i in range(n)],
        "pressure": [(ns(i), 2.5) for i in range(n)],
        "electrolyte_temperature": [(ns(5 * k), 35.0) for k in range(n // 5 + 1)],
    }
    if drop:
        series[drop] = [p for p in series[drop] if p[0] != ns(5)]
    return series


def test_model_rows_exact_join_uses_the_same_instant_in_every_signal():
    series = hydro_series(drop="flow")
    rows = c.model_rows("hydrolyzer", series, [(0, ns(20))], c.POLICY)
    assert ns(5) not in rows.t
    assert len(rows) == 19
    assert all(len(col) == 19 for col in rows.columns.values())


def test_model_rows_only_instants_inside_windows_half_open():
    series = hydro_series()
    rows = c.model_rows("hydrolyzer", series, [(ns(3), ns(6)), (ns(10), ns(12))], c.POLICY)
    assert rows.t == [ns(3), ns(4), ns(5), ns(10), ns(11)]
    assert rows.window_index == [0, 0, 0, 1, 1]
    assert rows.window_start == [ns(3)] * 3 + [ns(10)] * 2
    assert rows.voltage == [83.0, 84.0, 85.0, 90.0, 91.0]
    assert rows.columns["flow"] == [43.0, 44.0, 45.0, 50.0, 51.0]
    assert rows.columns["electrolyte_temperature"] == [35.0] * 5


def test_model_rows_temperature_as_of_boundary_10_s_used_10_s_plus_1_ns_dropped():
    series = {
        "voltage": [(ns(10), 80.0), (ns(10) + 1, 81.0)],
        "current": [(ns(10), 150.0), (ns(10) + 1, 150.0)],
        "flow": [(ns(10), 40.0), (ns(10) + 1, 40.0)],
        "pressure": [(ns(10), 2.5), (ns(10) + 1, 2.5)],
        "electrolyte_temperature": [(0, 35.0)],
    }
    rows = c.model_rows("hydrolyzer", series, [(0, ns(20))], c.POLICY)
    assert rows.t == [ns(10)]
    assert rows.columns["electrolyte_temperature"] == [35.0]


def test_model_rows_temperature_is_the_latest_reading_at_or_before_the_instant():
    series = hydro_series(12)
    series["electrolyte_temperature"] = [(0, 30.0), (ns(5), 31.0), (ns(9), 32.0)]
    rows = c.model_rows("hydrolyzer", series, [(0, ns(12))], c.POLICY)
    temps = dict(zip(rows.t, rows.columns["electrolyte_temperature"], strict=True))
    assert temps[ns(4)] == 30.0
    assert temps[ns(5)] == 31.0
    assert temps[ns(8)] == 31.0
    assert temps[ns(9)] == 32.0
    # A future reading is never used for an earlier instant.
    series["electrolyte_temperature"] = [(ns(6), 99.0)]
    rows = c.model_rows("hydrolyzer", series, [(0, ns(12))], c.POLICY)
    assert rows.t[0] == ns(6)


def test_model_rows_no_temperature_means_no_rows():
    series = hydro_series()
    series["electrolyte_temperature"] = []
    assert len(c.model_rows("hydrolyzer", series, [(0, ns(20))], c.POLICY)) == 0
    del series["electrolyte_temperature"]
    assert len(c.model_rows("hydrolyzer", series, [(0, ns(20))], c.POLICY)) == 0


def test_model_rows_absorber_uses_pressure_drop_instants():
    series = {
        "voltage": [(ns(i), 80.0 + i) for i in range(20)],
        "current": [(ns(i), 150.0) for i in range(20)],
        "air_flow": [(ns(i), 1200.0 + i) for i in range(20)],
        "pressure_drop": [(ns(i), 15.0 + i) for i in range(0, 20, 2)],
        "electrolyte_temperature": [(ns(5 * k), 35.0) for k in range(5)],
    }
    rows = c.model_rows("absorber", series, [(0, ns(20))], c.POLICY)
    assert rows.t == [ns(i) for i in range(0, 20, 2)]
    assert rows.voltage == [80.0 + i for i in range(0, 20, 2)]
    assert rows.columns["air_flow"] == [1200.0 + i for i in range(0, 20, 2)]
    assert rows.columns["pressure_drop"] == [15.0 + i for i in range(0, 20, 2)]
    assert set(rows.columns) == set(c.MODELS["absorber"])
    # a pressure_drop instant with no voltage at the same instant is dropped
    series["voltage"] = [p for p in series["voltage"] if p[0] != ns(4)]
    assert ns(4) not in c.model_rows("absorber", series, [(0, ns(20))], c.POLICY).t


def test_model_rows_respects_a_policy_temperature_age():
    series = hydro_series(12)
    series["electrolyte_temperature"] = [(0, 35.0)]
    tight = {**c.POLICY, "temp_max_age_s": 3}
    rows = c.model_rows("hydrolyzer", series, [(0, ns(12))], tight)
    assert rows.t == [ns(i) for i in range(4)]


def test_blocks_are_floor_of_offset_over_block_length_within_each_window():
    rows = c.Rows(
        t=[ns(0), ns(119.999), ns(120), ns(239), ns(1000), ns(1130)],
        window_index=[0, 0, 0, 0, 1, 1],
        window_start=[0, 0, 0, 0, ns(1000), ns(1000)],
        voltage=[1.0] * 6,
        columns={name: [1.0] * 6 for name in HYDRO},
    )
    stratum = c._build_stratum(rows, HYDRO, 120)
    assert [int(b[0]) for b in stratum.blocks] == [2, 2, 1, 1]


# ---------------------------------------------------------------------------- S5.3 the fit


def test_ols_recovers_planted_coefficients_and_r2_drops():
    rows = make_rows(300)
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, FAST)
    assert entry["testable"] is True
    assert entry["instants"] == 300
    assert entry["r2"] == pytest.approx(1.0, abs=1e-9)
    for name, planted in zip(HYDRO, PLANTED, strict=True):
        assert term(entry, name)["coefficient"] == pytest.approx(planted, abs=1e-9)
    r2_full = naive_r2(rows, list(HYDRO))
    for name in HYDRO:
        without = naive_r2(rows, [n for n in HYDRO if n != name])
        assert term(entry, name)["r2_drop"] == pytest.approx(float(r2_full - without), abs=1e-9)
        assert term(entry, name)["r2_drop"] == pytest.approx(1 - float(without), abs=1e-9)
    joint = naive_r2(rows, ["current", "electrolyte_temperature"])
    assert entry["joint"]["terms"] == ["flow", "pressure"]
    assert entry["joint"]["r2_drop"] == pytest.approx(1 - float(joint), abs=1e-9)
    assert entry["joint"]["separable"] is True


def test_ols_on_noisy_data_matches_exact_rational_solution():
    rows = make_rows(300, seed=5, noise=0.5)
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, FAST)
    exact = naive_coefficients(rows, HYDRO)
    for name, value in zip(HYDRO, exact, strict=True):
        assert term(entry, name)["coefficient"] == pytest.approx(float(value), rel=1e-9)
    assert entry["r2"] == pytest.approx(float(naive_r2(rows, list(HYDRO))), abs=1e-9)


def test_term_order_names_and_units():
    entry = c.analyse_model(make_rows(300), "hydrolyzer", "steady", "EXP_001", {}, FAST)
    assert [t["name"] for t in entry["terms"]] == list(HYDRO)
    assert [t["unit"] for t in entry["terms"]] == [
        "V per A",
        "V per °C",
        "V per L/min",
        "V per bar",
    ]
    assert (entry["model"], entry["window"], entry["scope"]) == ("hydrolyzer", "steady", "EXP_001")
    assert set(entry) == set(SCHEMA["$defs"]["voltage_model"]["required"])
    for t in entry["terms"]:
        assert set(t) == set(SCHEMA["$defs"]["term"]["required"])
        assert -1.0 <= t["plain_corr"] <= 1.0


def test_plain_correlation_and_vif_of_independent_predictors():
    rows = make_rows(300, seed=2)
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, FAST)
    for t in entry["terms"]:
        assert 1.0 <= t["vif"] < 1.5
    flow = term(entry, "flow")
    assert flow["plain_corr"] == pytest.approx(c.pearson(rows.voltage, rows.columns["flow"]))


def test_299_rows_not_testable_300_testable():
    short = c.analyse_model(make_rows(299), "hydrolyzer", "steady", "EXP_001", {}, FAST)
    assert short["testable"] is False
    assert short["instants"] == 299
    assert short["r2"] is None
    assert short["resamples_used"] == 0 and short["resamples_singular"] == 0
    assert len(short["terms"]) == 4
    for t in short["terms"]:
        assert all(t[k] is None for k in t if k not in ("name", "unit"))
    assert short["joint"] == {"terms": ["flow", "pressure"], "r2_drop": None, "separable": None}
    ok = c.analyse_model(make_rows(300), "hydrolyzer", "steady", "EXP_001", {}, FAST)
    assert ok["testable"] is True


def test_min_instants_comes_from_the_policy():
    low = {**FAST, "min_instants": 50}
    assert c.analyse_model(make_rows(60), "hydrolyzer", "w", "s", {}, low)["testable"]
    assert not c.analyse_model(make_rows(49), "hydrolyzer", "w", "s", {}, low)["testable"]


def test_singular_normal_matrix_is_not_testable():
    flat = make_rows(300, flow_fn=lambda i, rng: 40.0)
    entry = c.analyse_model(flat, "hydrolyzer", "steady", "EXP_001", {}, FAST)
    assert entry["testable"] is False
    assert entry["instants"] == 300
    exact_copy = make_rows(300, pressure_fn=lambda i, flow, rng: 0.05 * flow)
    assert not c.analyse_model(exact_copy, "hydrolyzer", "s", "e", {}, FAST)["testable"]


def test_flat_voltage_is_not_testable():
    rows = make_rows(300)
    rows.voltage = [80.0] * 300
    assert not c.analyse_model(rows, "hydrolyzer", "s", "e", {}, FAST)["testable"]


def test_solve_pivot_rule_is_relative_to_largest_diagonal():
    assert c._solve([[1.0, 0.0], [0.0, 1.0]], [3.0, 4.0]) == [3.0, 4.0]
    # a pivot at 1e-9 x the largest diagonal is singular; just above is not
    assert c._solve([[1.0, 0.0], [0.0, 1e-9]], [1.0, 1.0]) is None
    assert c._solve([[1.0, 0.0], [0.0, 2e-9]], [1.0, 1.0]) is not None
    # partial pivoting: a zero leading entry is fine when a row below can pivot
    assert c._solve([[0.0, 1.0], [1.0, 0.0]], [2.0, 3.0]) == [3.0, 2.0]
    assert c._solve([[0.0, 0.0], [0.0, 0.0]], [1.0, 1.0]) is None


# ---------------------------------------------------------------------------- S5.4 collinear


def test_collinear_flow_and_pressure_give_high_vif_and_joint_only():
    rows = make_rows(
        300,
        seed=4,
        flow_fn=lambda i, rng: rng.uniform(38, 42),
        pressure_fn=lambda i, flow, rng: 0.05 * flow + (1e-4 if i % 2 else -1e-4),
    )
    # keep the other predictors small-scale so the 1e-9 pivot rule does not hide the fit
    rows.columns["current"] = [150.0 + 0.5 * math.sin(i) for i in range(300)]
    rows.columns["electrolyte_temperature"] = [35.0 + 0.5 * math.cos(1.3 * i) for i in range(300)]
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, FAST)
    assert entry["testable"] is True
    assert term(entry, "flow")["vif"] >= 10
    assert term(entry, "pressure")["vif"] >= 10
    assert entry["joint"]["separable"] is False
    assert entry["joint"]["r2_drop"] is not None
    assert entry["joint"]["r2_drop"] > 0


def test_vif_just_below_and_above_the_limit():
    # two predictors with correlation r have vif 1 / (1 - r^2); r^2 = 0.9 gives exactly 10
    sxx = [[1.0, math.sqrt(0.9)], [math.sqrt(0.9), 1.0]]
    assert c._vif(sxx, 0) == pytest.approx(10.0)
    sxx = [[1.0, math.sqrt(0.89)], [math.sqrt(0.89), 1.0]]
    assert c._vif(sxx, 0) < 10
    assert c._vif([[0.0, 0.0], [0.0, 1.0]], 0) is None


def test_separable_follows_the_policy_vif_limit():
    rows = make_rows(300, seed=2)
    loose = {**FAST, "vif_limit": 1.0000001}
    assert c.analyse_model(rows, "hydrolyzer", "w", "s", {}, FAST)["joint"]["separable"] is True
    assert c.analyse_model(rows, "hydrolyzer", "w", "s", {}, loose)["joint"]["separable"] is False


# ---------------------------------------------------------------------------- S5.5 bootstrap


def test_bootstrap_is_deterministic_and_covers_the_estimate():
    rows = make_rows(1200, seed=7, noise=0.5)
    policy = {**c.POLICY, "bootstrap_resamples": 300}
    first = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, policy)
    second = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, policy)
    assert first == second
    assert first["resamples_used"] + first["resamples_singular"] == 300
    for t in first["terms"]:
        assert t["interval_low"] <= t["coefficient"] <= t["interval_high"]
        assert t["interval_low"] < t["interval_high"]


def test_bootstrap_depends_on_the_seed_key():
    rows = make_rows(1200, seed=7, noise=0.5)
    base = {**c.POLICY, "bootstrap_resamples": 100}
    a = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, base)
    b = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_002", {}, base)
    c2 = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, {**base, "bootstrap_seed": 1})
    assert term(a, "flow")["interval_low"] != term(b, "flow")["interval_low"]
    assert term(a, "flow")["interval_low"] != term(c2, "flow")["interval_low"]
    assert term(a, "flow")["coefficient"] == term(b, "flow")["coefficient"]


def test_default_policy_runs_1000_resamples():
    rows = make_rows(480, seed=3, noise=0.3)
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, c.POLICY)
    assert entry["resamples_used"] + entry["resamples_singular"] == 1000


def test_singular_resamples_are_counted_and_skipped():
    # flow varies only in block 1 of 4: a resample that misses block 1 has a constant flow.
    def flow_fn(i, rng):
        return rng.uniform(38, 42) if 120 <= i < 240 else 40.0

    rows = make_rows(480, seed=11, noise=0.2, flow_fn=flow_fn)
    policy = {**c.POLICY, "bootstrap_resamples": 200}
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, policy)
    assert entry["testable"] is True
    assert entry["resamples_singular"] > 0
    assert entry["resamples_used"] > 0
    assert entry["resamples_used"] + entry["resamples_singular"] == 200
    # (3/4)^4 of the resamples miss block 1 on average; the draws are deterministic
    rng = random.Random("20261124|hydrolyzer|steady|EXP_001")
    expected = sum(1 for _ in range(200) if 1 not in [rng.randrange(4) for _ in range(4)])
    assert entry["resamples_singular"] == expected
    assert term(entry, "flow")["interval_low"] is not None


def test_all_resamples_singular_gives_null_intervals_but_keeps_the_estimate():
    # Flow varies only in block 3 of 4. With one resample, pick the scope label whose single
    # resample (4 draws of randrange(4), read from the same rng) misses block 3.
    def misses_block_3(scope: str) -> bool:
        rng = random.Random(f"20261124|hydrolyzer|steady|{scope}")
        return 3 not in [rng.randrange(4) for _ in range(4)]

    scope = next(f"S{k}" for k in range(100) if misses_block_3(f"S{k}"))
    rows = make_rows(
        480, seed=11, noise=0.2, flow_fn=lambda i, rng: 40.0 if i < 360 else 41.0 + i % 3
    )
    policy = {**c.POLICY, "bootstrap_resamples": 1}
    entry = c.analyse_model(rows, "hydrolyzer", "steady", scope, {}, policy)
    assert entry["testable"] is True
    assert entry["resamples_singular"] == 1
    assert entry["resamples_used"] == 0
    for t in entry["terms"]:
        assert t["interval_low"] is None and t["interval_high"] is None
        assert t["coefficient"] is not None


def test_bootstrap_re_derived_by_hand_on_a_four_block_example():
    rows = make_rows(480, seed=21, noise=0.4)
    n_resamples = 12
    policy = {**c.POLICY, "bootstrap_resamples": n_resamples}
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {}, policy)
    assert entry["resamples_used"] == n_resamples

    # Blocks of 120 s: rows 0-119, 120-239, 240-359, 360-479.
    rng = random.Random("20261124|hydrolyzer|steady|EXP_001")
    per_term: list[list[float]] = [[] for _ in HYDRO]
    for _ in range(n_resamples):
        draws = [rng.randrange(4) for _ in range(4)]
        index = [i for d in draws for i in range(120 * d, 120 * d + 120)]
        sub = c.Rows(
            t=[rows.t[i] for i in index],
            window_index=[0] * len(index),
            window_start=[0] * len(index),
            voltage=[rows.voltage[i] for i in index],
            columns={name: [rows.columns[name][i] for i in index] for name in HYDRO},
        )
        for k, value in enumerate(naive_coefficients(sub, HYDRO)):
            per_term[k].append(float(value))

    def type7(values, q):
        ordered = sorted(values)
        pos = (len(ordered) - 1) * q
        lo = math.floor(pos)
        return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (pos - lo)

    for k, name in enumerate(HYDRO):
        assert term(entry, name)["interval_low"] == pytest.approx(
            type7(per_term[k], 0.025), abs=1e-7
        )
        assert term(entry, name)["interval_high"] == pytest.approx(
            type7(per_term[k], 0.975), abs=1e-7
        )


def test_percentile_type_7_and_interval_level():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert c.percentile(values, 0.0) == 1.0
    assert c.percentile(values, 1.0) == 5.0
    assert c.percentile(values, 0.5) == 3.0
    assert c.percentile(values, 0.25) == 2.0
    assert c.percentile(values, 0.1) == pytest.approx(1.4)
    assert c._interval([], 0.95) is None
    low, high = c._interval([float(v) for v in range(101)], 0.95)
    assert (low, high) == (pytest.approx(2.5), pytest.approx(97.5))
    low, high = c._interval([float(v) for v in range(101)], 0.5)
    assert (low, high) == (pytest.approx(25.0), pytest.approx(75.0))


def test_pooled_bootstrap_is_stratified_and_deterministic():
    by_exp = {
        "EXP_002": make_rows(480, seed=2, noise=0.3),
        "EXP_001": make_rows(480, seed=1, noise=0.3),
    }
    policy = {**c.POLICY, "bootstrap_resamples": 100}
    first = c.analyse_pooled(by_exp, "hydrolyzer", "steady", policy)
    second = c.analyse_pooled(dict(reversed(list(by_exp.items()))), "hydrolyzer", "steady", policy)
    assert first == second
    assert first["scope"] == "pooled"
    assert first["resamples_used"] + first["resamples_singular"] == 100
    for t in first["terms"]:
        assert t["interval_low"] <= t["coefficient"] <= t["interval_high"]


# ---------------------------------------------------------------------------- pooled fit


def test_pooled_has_one_intercept_per_experiment():
    by_exp = {
        "EXP_001": make_rows(300, seed=1, offset=0.0),
        "EXP_002": make_rows(320, seed=2, offset=5.0),
        "EXP_003": make_rows(340, seed=3, offset=-3.0),
    }
    pooled = c.analyse_pooled(by_exp, "hydrolyzer", "steady", FAST)
    assert pooled["scope"] == "pooled"
    assert pooled["testable"] is True
    assert pooled["instants"] == 960
    assert pooled["r2"] == pytest.approx(1.0, abs=1e-9)
    for name, planted in zip(HYDRO, PLANTED, strict=True):
        assert term(pooled, name)["coefficient"] == pytest.approx(planted, abs=1e-8)
        assert term(pooled, name)["best_lag_s"] is None
        assert term(pooled, name)["corr_at_best_lag"] is None
        assert term(pooled, name)["corr_at_zero"] is None
    assert set(pooled) == set(SCHEMA["$defs"]["voltage_model"]["required"])


def test_pooled_pools_only_testable_experiments():
    by_exp = {
        "EXP_001": make_rows(300, seed=1),
        "EXP_002": make_rows(299, seed=2, offset=50.0),
        "EXP_003": make_rows(400, seed=3, flow_fn=lambda i, rng: 40.0),
    }
    pooled = c.analyse_pooled(by_exp, "hydrolyzer", "steady", FAST)
    assert pooled["testable"] is True
    assert pooled["instants"] == 300
    only_one = c.analyse_model(by_exp["EXP_001"], "hydrolyzer", "steady", "EXP_001", {}, FAST)
    for name in HYDRO:
        assert term(pooled, name)["coefficient"] == pytest.approx(
            term(only_one, name)["coefficient"], abs=1e-9
        )


def test_pooled_with_no_testable_experiment():
    pooled = c.analyse_pooled({"EXP_001": make_rows(299)}, "hydrolyzer", "steady", FAST)
    assert pooled["testable"] is False
    assert pooled["instants"] == 0
    assert pooled["scope"] == "pooled"
    assert c.analyse_pooled({}, "hydrolyzer", "steady", FAST)["testable"] is False


# ---------------------------------------------------------------------------- S5.8 lag search


def test_lag_search_finds_the_shift():
    rng = random.Random(9)
    term_series = [(ns(i), rng.uniform(-1, 1)) for i in range(-100, 400)]
    lookup = dict(term_series)
    times = [ns(i) for i in range(0, 400)]
    values = [2.0 * lookup[t - ns(7)] + 1.0 for t in times]
    policy = {**c.POLICY, "min_instants": 100}
    best, corr, zero = c.lag_search(times, values, term_series, policy)
    assert best == 7
    assert corr == pytest.approx(1.0)
    assert abs(zero) < 0.3


def test_lag_search_negative_correlation_uses_abs_and_keeps_the_sign():
    rng = random.Random(10)
    term_series = [(ns(i), rng.uniform(-1, 1)) for i in range(-100, 400)]
    lookup = dict(term_series)
    times = [ns(i) for i in range(400)]
    values = [-lookup[t - ns(12)] for t in times]
    best, corr, _ = c.lag_search(times, values, term_series, {**c.POLICY, "min_instants": 100})
    assert best == 12
    assert corr == pytest.approx(-1.0)


def test_lag_ties_go_to_the_smaller_shift():
    # a series with period 4 s: shifts of 3 s and 7 s give identical pairs, hence equal |corr|
    pattern = [1.0, 5.0, 2.0, 9.0]
    term_series = [(ns(i), pattern[i % 4]) for i in range(-100, 300)]
    lookup = dict(term_series)
    times = [ns(i) for i in range(200)]
    values = [lookup[t - ns(3)] for t in times]
    policy = {**c.POLICY, "min_instants": 100}
    best, corr, _ = c.lag_search(times, values, term_series, policy)
    assert best == 3
    assert corr == pytest.approx(1.0)
    # ... and the larger shift would have tied exactly
    values7 = [lookup[t - ns(7)] for t in times]
    assert values7 == values
    # shifting the planted value to 7 s picks 7 only when 3 is not as good
    rng = random.Random(1)
    other = [(ns(i), rng.uniform(0, 1)) for i in range(-100, 300)]
    lookup = dict(other)
    values = [lookup[t - ns(7)] for t in times]
    assert c.lag_search(times, values, other, policy)[0] == 7


def test_lag_with_fewer_than_min_instants_pairs_is_skipped():
    rng = random.Random(3)
    term_series = [(ns(i), rng.uniform(-1, 1)) for i in range(100)]
    lookup = dict(term_series)
    times = [ns(i) for i in range(100)]
    # value(t) = term(t - 50): only 50 pairs exist at that shift
    values = [lookup.get(t - ns(50), rng.uniform(-1, 1)) for t in times]
    strict = {**c.POLICY, "min_instants": 60}
    best, _, zero = c.lag_search(times, values, term_series, strict)
    assert best != 50
    assert best is None or best <= 40
    assert zero is not None
    relaxed = {**c.POLICY, "min_instants": 50}
    assert c.lag_search(times, values, term_series, relaxed)[0] == 50
    # nothing qualifies: all None
    assert c.lag_search(times, values, term_series, {**c.POLICY, "min_instants": 101}) == (
        None,
        None,
        None,
    )


def test_lag_range_is_zero_to_lag_max_inclusive():
    rng = random.Random(4)
    term_series = [(ns(i), rng.uniform(-1, 1)) for i in range(-100, 300)]
    lookup = dict(term_series)
    times = [ns(i) for i in range(200)]
    values = [lookup[t - ns(60)] for t in times]
    policy = {**c.POLICY, "min_instants": 100}
    assert c.lag_search(times, values, term_series, policy)[0] == 60
    values = [lookup[t - ns(61)] for t in times]
    assert c.lag_search(times, values, term_series, policy)[0] != 61
    assert c.lag_search(times, values, term_series, {**policy, "lag_max_s": 61})[0] == 61


def test_analyse_model_lag_fields_for_x1_and_x2_only():
    rng = random.Random(12)
    n = 400
    flow_series = [(ns(i), rng.uniform(38, 42)) for i in range(-100, n)]
    flow_at = dict(flow_series)
    rows = make_rows(n, seed=12)
    # voltage follows flow 7 s ago; the model's own flow column (now) is unrelated to it
    rows.voltage = [
        v - PLANTED[2] * rows.columns["flow"][i] + 1.0 * flow_at[rows.t[i] - ns(7)]
        for i, v in enumerate(rows.voltage)
    ]
    policy = {**FAST, "min_instants": 300}
    entry = c.analyse_model(rows, "hydrolyzer", "steady", "EXP_001", {"flow": flow_series}, policy)
    flow = term(entry, "flow")
    assert flow["best_lag_s"] == 7
    assert flow["corr_at_best_lag"] > 0.9
    assert abs(flow["corr_at_zero"]) < 0.3
    for name in ("current", "electrolyte_temperature"):
        t = term(entry, name)
        assert (t["best_lag_s"], t["corr_at_best_lag"], t["corr_at_zero"]) == (None, None, None)
    pressure = term(entry, "pressure")  # no series given: no lag numbers
    assert pressure["best_lag_s"] is None


# ---------------------------------------------------------------------------- S5.6 evidence


def fake_entry(flow_iv, pressure_iv=None, *, testable=True, model="hydrolyzer"):
    names = c.MODELS[model]
    ivs = {names[2]: flow_iv, names[3]: pressure_iv or flow_iv}
    terms = []
    for name in names:
        low, high = ivs.get(name, (0.0, 0.0))
        terms.append(
            {
                "name": name,
                "coefficient": None if not testable or low is None else (low + high) / 2,
                "interval_low": low if testable else None,
                "interval_high": high if testable else None,
            }
        )
    return {
        "model": model,
        "window": "steady",
        "scope": "EXP",
        "testable": testable,
        "terms": terms,
    }


def fake_pooled(model="hydrolyzer", coef=0.25, low=0.1, high=0.4, testable=True):
    names = c.MODELS[model]
    terms = [
        {
            "name": n,
            "coefficient": coef if testable else None,
            "interval_low": low if testable else None,
            "interval_high": high if testable else None,
        }
        for n in names
    ]
    return {
        "model": model,
        "window": "steady",
        "scope": "pooled",
        "testable": testable,
        "terms": terms,
    }


def status_of(*intervals, model="hydrolyzer"):
    entries = [
        fake_entry(iv, model=model)
        if iv is not None
        else fake_entry((None, None), testable=False, model=model)
        for iv in intervals
    ]
    out = c.evidence(entries, fake_pooled(model=model))
    assert [e["term"] for e in out] == list(c.MODELS[model][2:])
    assert out[0]["status"] == out[1]["status"]
    return out[0]["status"], out[0]["sign"]


def test_evidence_supported_positive_and_negative():
    assert status_of((0.1, 0.5), (0.2, 0.9)) == ("supported", "positive")
    assert status_of((-0.5, -0.1), (-0.9, -0.2)) == ("supported", "negative")
    assert status_of((0.1, 0.5), (0.2, 0.9), (0.3, 0.4)) == ("supported", "positive")


def test_evidence_inconsistent_when_two_fits_exclude_zero_with_opposite_signs():
    assert status_of((0.1, 0.5), (-0.9, -0.2)) == ("inconsistent", None)
    assert status_of((0.1, 0.5), (0.2, 0.9), (-0.9, -0.2)) == ("inconsistent", None)
    assert status_of((0.1, 0.5), (-0.9, -0.2), (-0.3, 0.4)) == ("inconsistent", None)


def test_evidence_not_resolved_cases():
    assert status_of((0.1, 0.5), (-0.3, 0.4)) == ("not_resolved", None)
    assert status_of((0.0, 0.5), (0.2, 0.9)) == ("not_resolved", None)
    assert status_of((-0.5, 0.0), (-0.9, -0.2)) == ("not_resolved", None)
    assert status_of((-0.3, 0.4), (-0.2, 0.9)) == ("not_resolved", None)
    assert status_of((-0.3, 0.4)) == ("not_resolved", None)


def test_evidence_single_run_and_not_testable():
    assert status_of((0.1, 0.5)) == ("single_run", "positive")
    assert status_of((-0.5, -0.1)) == ("single_run", "negative")
    assert status_of((0.1, 0.5), None) == ("single_run", "positive")
    assert status_of((0.0, 0.5)) == ("not_resolved", None)
    assert status_of(None) == ("not_testable", None)
    assert status_of(None, None) == ("not_testable", None)
    entries: list[dict] = []
    out = c.evidence(entries, fake_pooled(testable=False))
    assert [e["status"] for e in out] == ["not_testable", "not_testable"]


def test_excludes_zero_boundary():
    assert c._excludes_zero(0.0, 0.4) is False
    assert c._excludes_zero(0.001, 0.4) is True
    assert c._excludes_zero(-0.4, 0.0) is False
    assert c._excludes_zero(-0.4, -0.001) is True
    assert c._excludes_zero(-0.1, 0.1) is False
    assert c._excludes_zero(None, None) is False


def test_evidence_reports_counts_pooled_numbers_and_all_keys():
    entries = [
        fake_entry((0.1, 0.5)),
        fake_entry((-0.3, 0.4)),
        fake_entry((0.0, 0.0), testable=False),
    ]
    out = c.evidence(entries, fake_pooled(coef=0.25, low=0.1, high=0.4))
    assert set(out[0]) == set(SCHEMA["$defs"]["evidence"]["required"])
    assert out[0]["experiments_testable"] == 2
    assert out[0]["experiments_excluding_zero"] == 1
    assert (out[0]["pooled_coefficient"], out[0]["pooled_interval_low"]) == (0.25, 0.1)
    assert out[0]["pooled_interval_high"] == 0.4
    assert (out[0]["model"], out[0]["window"], out[0]["term"]) == ("hydrolyzer", "steady", "flow")
    assert out[1]["term"] == "pressure"


def test_evidence_pooled_does_not_change_the_status():
    entries = [fake_entry((0.1, 0.5)), fake_entry((0.2, 0.9))]
    a = c.evidence(entries, fake_pooled(coef=-9.0, low=-10.0, high=-8.0))
    assert a[0]["status"] == "supported" and a[0]["sign"] == "positive"
    assert a[0]["pooled_coefficient"] == -9.0


def test_evidence_absorber_terms():
    entries = [fake_entry((0.1, 0.5), model="absorber"), fake_entry((0.2, 0.9), model="absorber")]
    out = c.evidence(entries, fake_pooled(model="absorber"))
    assert [e["term"] for e in out] == ["air_flow", "pressure_drop"]
    assert out[0]["model"] == "absorber"


def test_evidence_from_real_fits():
    by_exp = [
        c.analyse_model(
            make_rows(480, seed=s, noise=0.2), "hydrolyzer", "steady", f"EXP_00{s}", {}, FAST
        )
        for s in (1, 2, 3)
    ]
    pooled = c.analyse_pooled(
        {f"EXP_00{s}": make_rows(480, seed=s, noise=0.2) for s in (1, 2, 3)},
        "hydrolyzer",
        "steady",
        FAST,
    )
    out = c.evidence(by_exp, pooled)
    flow, pressure = out
    assert (flow["status"], flow["sign"]) == ("supported", "negative")
    assert (pressure["status"], pressure["sign"]) == ("supported", "positive")
    assert flow["experiments_testable"] == flow["experiments_excluding_zero"] == 3


# ---------------------------------------------------------------------------- S5.7 comparability


META_A = {"sorbent_batch": "SB-A", "operator": "Op A"}
COND = {
    "current_setpoint_a": 150.0,
    "current_setpoint_profile": "constant",
    "air_flow_m3h": 1200.0,
    "solvent_flow_lmin": 8.0,
    "ambient_temperature_c": 15.0,
    "relative_humidity_pct": 50.0,
}


def factors_for(cond_b=None, meta_b=None, cond_a=None, meta_a=None):
    return c.compare_factors(
        meta_a or META_A,
        {**COND, **(cond_a or {})},
        meta_b or META_A,
        {**COND, **(cond_b or {})},
    )


def differs_map(factors):
    return {f["factor"]: f["differs"] for f in factors}


def test_factors_are_the_seven_in_order_with_values():
    fs = factors_for()
    assert [f["factor"] for f in fs] == list(c.FACTORS)
    assert [f["differs"] for f in fs] == [False] * 7
    assert fs[0]["a"] == 150.0 and fs[0]["b"] == 150.0
    assert fs[1]["a"] == "constant"
    assert fs[6]["a"] == "SB-A"
    for f in fs:
        assert set(f) == {"factor", "a", "b", "differs"}


def test_relative_factor_boundary_150_vs_157_5_same_150_vs_158_differs():
    assert differs_map(factors_for({"current_setpoint_a": 157.5}))["current_setpoint"] is False
    assert differs_map(factors_for({"current_setpoint_a": 158.0}))["current_setpoint"] is True
    # symmetric in a and b
    swapped = factors_for({"current_setpoint_a": 150.0}, cond_a={"current_setpoint_a": 158.0})
    assert differs_map(swapped)["current_setpoint"] is True
    # other relative factors use the same rule
    assert differs_map(factors_for({"air_flow_m3h": 1263.0}))["air_flow"] is False
    assert differs_map(factors_for({"air_flow_m3h": 1264.0}))["air_flow"] is True
    assert differs_map(factors_for({"solvent_flow_lmin": 8.4}))["solvent_flow"] is False
    assert differs_map(factors_for({"solvent_flow_lmin": 8.5}))["solvent_flow"] is True


def test_absolute_factor_boundaries():
    assert differs_map(factors_for({"ambient_temperature_c": 20.0}))["ambient_temperature"] is False
    assert differs_map(factors_for({"ambient_temperature_c": 20.01}))["ambient_temperature"] is True
    assert differs_map(factors_for({"ambient_temperature_c": 10.0}))["ambient_temperature"] is False
    assert differs_map(factors_for({"ambient_temperature_c": 9.99}))["ambient_temperature"] is True
    assert differs_map(factors_for({"relative_humidity_pct": 65.0}))["relative_humidity"] is False
    assert differs_map(factors_for({"relative_humidity_pct": 65.01}))["relative_humidity"] is True


def test_ambient_10_vs_15_same_and_10_vs_15_01_differs():
    fs = factors_for({"ambient_temperature_c": 15.0}, cond_a={"ambient_temperature_c": 10.0})
    assert differs_map(fs)["ambient_temperature"] is False
    fs = factors_for({"ambient_temperature_c": 15.01}, cond_a={"ambient_temperature_c": 10.0})
    assert differs_map(fs)["ambient_temperature"] is True


def test_profile_and_batch_differ_when_not_equal():
    fs = factors_for({"current_setpoint_profile": "varying"})
    assert differs_map(fs)["current_setpoint_profile"] is True
    fs = factors_for(meta_b={"sorbent_batch": "SB-B", "operator": "Op A"})
    assert differs_map(fs)["sorbent_batch"] is True


def test_unknown_factor_gives_null_and_counts_as_differing():
    fs = factors_for(
        meta_b={"sorbent_batch": None, "operator": "Op A"},
        meta_a={"sorbent_batch": "SB-2026-014", "operator": "Op A"},
    )
    assert differs_map(fs)["sorbent_batch"] is None
    assert c.conditions_status(fs) == ("supported", ["sorbent_batch"])
    fs = factors_for({"air_flow_m3h": None})
    assert differs_map(fs)["air_flow"] is None
    assert fs[2]["b"] is None


def test_policy_tolerances_are_read_from_the_policy():
    tight = {**c.POLICY, "condition_tol_rel": 0.01, "ambient_tol_c": 1, "humidity_tol_pct": 1}
    fs = c.compare_factors(
        META_A,
        COND,
        META_A,
        {
            **COND,
            "current_setpoint_a": 152.0,
            "ambient_temperature_c": 17.0,
            "relative_humidity_pct": 52.0,
        },
        tight,
    )
    d = differs_map(fs)
    assert d["current_setpoint"] is True
    assert d["ambient_temperature"] is True
    assert d["relative_humidity"] is True


def test_conditions_status_same_supported_confounded():
    fs = factors_for()
    assert c.conditions_status(fs) == ("same_conditions", [])
    fs = factors_for({"current_setpoint_a": 158.0})
    assert c.conditions_status(fs) == ("supported", ["current_setpoint"])
    fs = factors_for({"air_flow_m3h": 2400.0}, meta_b={"sorbent_batch": "SB-B", "operator": "Op B"})
    assert c.conditions_status(fs) == ("confounded", ["air_flow", "sorbent_batch"])
    fs = factors_for(
        {"current_setpoint_a": 200.0, "air_flow_m3h": 2400.0},
        meta_b={"sorbent_batch": "SB-B", "operator": "Op A"},
    )
    assert c.conditions_status(fs) == (
        "confounded",
        ["current_setpoint", "air_flow", "sorbent_batch"],
    )


def test_conditions_status_two_unknowns_are_confounded():
    fs = factors_for({"air_flow_m3h": None, "solvent_flow_lmin": None})
    assert c.conditions_status(fs) == ("confounded", ["air_flow", "solvent_flow"])


def test_operator_is_a_recorded_difference_not_a_factor():
    assert c.recorded_differences(META_A, META_A) == []
    other = {"sorbent_batch": "SB-A", "operator": "Op B"}
    assert c.recorded_differences(META_A, other) == [
        {"field": "operator", "a": "Op A", "b": "Op B"}
    ]
    assert c.recorded_differences(META_A, {"operator": None}) == [
        {"field": "operator", "a": "Op A", "b": None}
    ]
    assert c.recorded_differences({"operator": None}, {"operator": None}) == []
    fs = c.compare_factors(META_A, COND, other, COND)
    assert c.conditions_status(fs) == ("same_conditions", [])


# ---------------------------------------------------------------------------- conditions


def test_measured_conditions_are_medians_inside_the_windows_only():
    windows = [(ns(10), ns(20)), (ns(30), ns(40))]
    series = {
        "current_setpoint": [(ns(5), 999.0)] + [(ns(t), 150.0) for t in (10, 15, 30, 35)],
        "air_flow": [(ns(t), v) for t, v in ((12, 1200.0), (14, 1210.0), (31, 1190.0), (50, 5.0))],
        "solvent_flow": [(ns(11), 8.0), (ns(39), 8.2)],
        "ambient_temperature": [(ns(10), 14.0), (ns(30), 16.0), (ns(40), 99.0)],
        "relative_humidity": [(ns(19.999), 50.0), (ns(20), 99.0)],
    }
    cond = c.measured_conditions(series, windows)
    assert cond == {
        "current_setpoint_a": 150.0,
        "current_setpoint_profile": "constant",
        "air_flow_m3h": 1200.0,
        "solvent_flow_lmin": pytest.approx(8.1),
        "ambient_temperature_c": 15.0,
        "relative_humidity_pct": 50.0,
    }
    assert set(cond) == set(SCHEMA["$defs"]["experiment"]["properties"]["conditions"]["required"])


def test_measured_conditions_null_without_readings():
    cond = c.measured_conditions({}, [(0, ns(10))])
    assert all(v is None for v in cond.values())
    cond = c.measured_conditions({"air_flow": [(ns(50), 1.0)]}, [(0, ns(10))])
    assert cond["air_flow_m3h"] is None


def test_setpoint_profile_varying_when_spread_exceeds_5_percent_of_the_median():
    window = [(0, ns(1000))]
    varying = {"current_setpoint": [(ns(i), 150.0 if i % 2 else 160.0) for i in range(100)]}
    assert c.measured_conditions(varying, window)["current_setpoint_profile"] == "varying"
    constant = {"current_setpoint": [(ns(i), 150.0) for i in range(100)]}
    assert c.measured_conditions(constant, window)["current_setpoint_profile"] == "constant"
    # an outlier beyond the 5th/95th percentile does not make it varying
    outlier = {"current_setpoint": [(ns(i), 150.0) for i in range(100)] + [(ns(500), 400.0)]}
    assert c.measured_conditions(outlier, window)["current_setpoint_profile"] == "constant"
    # boundary: p95 - p05 = 5 <= 0.05 x 102.5 stays constant; 6 > 0.05 x 103 is varying
    near = {"current_setpoint": [(ns(i), 100.0 if i < 50 else 105.0) for i in range(100)]}
    assert c.measured_conditions(near, window)["current_setpoint_profile"] == "constant"
    wide = {"current_setpoint": [(ns(i), 100.0 if i < 50 else 106.0) for i in range(100)]}
    assert c.measured_conditions(wide, window)["current_setpoint_profile"] == "varying"


# ---------------------------------------------------------------------------- steady KPIs


def ramp_series(values, start_s=0.0, step_s=1.0):
    return [(ns(start_s + i * step_s), v) for i, v in enumerate(values)]


KPI_POLICY = {**c.POLICY, "bootstrap_block_s": 4}


def test_voltage_mean_is_ratio_of_sums_over_unequal_blocks():
    # window [0, 6 s) with 4 s blocks: block 0 has 4 instants of 10 V, block 1 has 2 of 20 V
    series = {"voltage": ramp_series([10.0] * 4 + [20.0] * 2)}
    policy = {**KPI_POLICY, "bootstrap_resamples": 60}
    result = c.steady_kpis(series, [(0, ns(6))], "EXP_X", policy)
    v = result.entries["voltage_mean_v"]
    assert v["value"] == pytest.approx((40 + 40) / 6)
    assert v["unit"] == "V"
    rng = random.Random("20261124|kpi|voltage_mean_v|EXP_X")
    parts = [(40.0, 4), (40.0, 2)]
    expected = []
    for _ in range(60):
        drawn = [parts[rng.randrange(2)] for _ in range(2)]
        expected.append(sum(p[0] for p in drawn) / sum(p[1] for p in drawn))
    assert result.samples["voltage_mean_v"] == pytest.approx(expected)
    # ratio of sums, not mean of block means: a mixed draw gives 80/6, never (10+20)/2
    assert {round(s, 6) for s in expected} <= {10.0, 20.0, round(80 / 6, 6)}
    assert 15.0 not in result.samples["voltage_mean_v"]
    assert len(result.samples["voltage_mean_v"]) == 60
    low, high = v["interval_low"], v["interval_high"]
    assert (low, high) == (
        pytest.approx(c.percentile(sorted(expected), 0.025)),
        pytest.approx(c.percentile(sorted(expected), 0.975)),
    )
    # 6 instants at 1 Hz bridge 5 s of the 6 s window
    assert v["coverage"] == pytest.approx(5 / 6)
    assert v["status"] == "partial"


def test_coverage_boundary_at_095_is_complete():
    series = {"voltage": ramp_series([10.0] * 20)}  # instants 0..19 s: 19 s covered
    result = c.steady_kpis(series, [(0, ns(20))], "EXP_X", {**KPI_POLICY, "bootstrap_resamples": 5})
    assert result.entries["voltage_mean_v"]["coverage"] == 0.95
    assert result.entries["voltage_mean_v"]["status"] == "complete"
    series = {"voltage": ramp_series([10.0] * 20)}
    result = c.steady_kpis(series, [(0, ns(21))], "EXP_X", {**KPI_POLICY, "bootstrap_resamples": 5})
    assert result.entries["voltage_mean_v"]["status"] == "partial"


def test_coverage_uses_the_spacing_limit_gap_rule():
    # a 2 s hole is bridged for voltage (limit 2 s); a 3 s hole is not
    ok = {"voltage": [(ns(t), 10.0) for t in (0, 1, 3, 4)]}
    gap = {"voltage": [(ns(t), 10.0) for t in (0, 1, 4, 5)]}
    r_ok = c.steady_kpis(ok, [(0, ns(4))], "E", {**KPI_POLICY, "bootstrap_resamples": 5})
    r_gap = c.steady_kpis(gap, [(0, ns(5))], "E", {**KPI_POLICY, "bootstrap_resamples": 5})
    assert r_ok.entries["voltage_mean_v"]["coverage"] == 1.0
    assert r_gap.entries["voltage_mean_v"]["coverage"] == pytest.approx(2 / 5)


def test_mean_power_is_a_trapezoid_integral_over_covered_seconds():
    power = ramp_series([1000.0 + 100.0 * i for i in range(5)])  # 1000 .. 1400 W at 0..4 s
    result = c.steady_kpis(
        {"power_computed": power}, [(0, ns(5))], "E", {**KPI_POLICY, "bootstrap_resamples": 5}
    )
    p = result.entries["mean_power_kw"]
    assert p["value"] == pytest.approx(1.2)  # 4800 W s over 4 s
    assert p["unit"] == "kW"
    assert p["coverage"] == pytest.approx(4 / 5)
    assert p["status"] == "partial"


def test_power_blocks_contribute_partial_integrals_and_seconds():
    power = ramp_series([1000.0 + 100.0 * i for i in range(6)])  # 0..5 s, covered (0, 5)
    policy = {**KPI_POLICY, "bootstrap_resamples": 80}
    result = c.steady_kpis({"power_computed": power}, [(0, ns(6))], "EXP_X", policy)
    # block [0,4): integral 4800 over 4 s; block [4,6) clipped to the covered [4,5): 1450 over 1 s
    parts = [(4800.0, 4.0), (1450.0, 1.0)]
    rng = random.Random("20261124|kpi|mean_power_kw|EXP_X")
    expected = []
    for _ in range(80):
        drawn = [parts[rng.randrange(2)] for _ in range(2)]
        expected.append(sum(p[0] for p in drawn) / sum(p[1] for p in drawn) / 1000)
    assert result.samples["mean_power_kw"] == pytest.approx(expected)
    assert result.entries["mean_power_kw"]["value"] == pytest.approx(6250 / 5 / 1000)
    assert {round(s, 9) for s in expected} <= {1.2, 1.25, 1.45}


def test_capture_rate_mean_and_efficiency_mean():
    rate = ramp_series([2.0] * 5)
    eff = ramp_series([0.5, 0.7, 0.9, 0.7, 0.2])
    result = c.steady_kpis(
        {"capture_rate": rate, "capture_efficiency": eff},
        [(0, ns(5))],
        "E",
        {**KPI_POLICY, "bootstrap_resamples": 5},
    )
    assert result.entries["capture_rate_mean_kg_h"]["value"] == pytest.approx(2.0)
    assert result.entries["capture_rate_mean_kg_h"]["unit"] == "kg/h"
    # plain mean of the instants (not a time-weighted integral)
    assert result.entries["capture_efficiency_mean"]["value"] == pytest.approx(0.6)
    assert result.entries["capture_efficiency_mean"]["unit"] == "fraction"
    assert result.entries["capture_efficiency_mean"]["coverage"] == pytest.approx(4 / 5)


def test_capture_spacing_limit_is_4_s():
    rate = [(ns(t), 2.0) for t in (0, 4, 8)]
    result = c.steady_kpis(
        {"capture_rate": rate}, [(0, ns(8))], "E", {**KPI_POLICY, "bootstrap_resamples": 5}
    )
    assert result.entries["capture_rate_mean_kg_h"]["coverage"] == 1.0
    rate = [(0, 2.0), (ns(4) + 1, 2.0)]
    result = c.steady_kpis(
        {"capture_rate": rate}, [(0, ns(5))], "E", {**KPI_POLICY, "bootstrap_resamples": 5}
    )
    assert result.entries["capture_rate_mean_kg_h"]["value"] is None
    assert result.entries["capture_rate_mean_kg_h"]["coverage"] == 0.0


def test_sec_is_energy_over_the_overlap_divided_by_co2_captured_there():
    power = ramp_series([1000.0 + 100.0 * i for i in range(5)])  # 0..4 s, covered (0, 4)
    rate = ramp_series([2.0] * 5, start_s=2.0)  # 2..6 s, covered (2, 6)
    result = c.steady_kpis(
        {"power_computed": power, "capture_rate": rate},
        [(0, ns(10))],
        "E",
        {**KPI_POLICY, "bootstrap_resamples": 5},
    )
    sec = result.entries["sec_kwh_per_kg"]
    # overlap (2, 4): energy 1200..1400 W over 2 s = 2600 W s; captured 2 kg/h x 2 s = 4
    assert sec["value"] == pytest.approx(2600 / 4 * (3600 / 3.6e6))
    assert sec["unit"] == "kWh/kg"
    assert sec["coverage"] == pytest.approx(2 / 10)
    assert sec["status"] == "partial"


def test_sec_on_a_hand_example_equals_0_6():
    power = ramp_series([1000.0 + 100.0 * i for i in range(5)])
    rate = ramp_series([2.0] * 5)
    result = c.steady_kpis(
        {"power_computed": power, "capture_rate": rate},
        [(0, ns(4.5))],
        "E",
        {**KPI_POLICY, "bootstrap_resamples": 20},
    )
    # energy 4800 W s = 4800 / 3.6e6 kWh; captured 2 kg/h x 4 s = 8 / 3600 kg; ratio 0.6
    assert result.entries["sec_kwh_per_kg"]["value"] == pytest.approx(0.6)
    assert len(result.samples["sec_kwh_per_kg"]) == 20


def test_sec_is_null_when_nothing_was_captured():
    power = ramp_series([1000.0] * 5)
    rate = ramp_series([0.0] * 5)
    result = c.steady_kpis(
        {"power_computed": power, "capture_rate": rate}, [(0, ns(5))], "E", KPI_POLICY
    )
    assert result.entries["sec_kwh_per_kg"]["value"] is None
    assert result.entries["sec_kwh_per_kg"]["status"] == "none"
    assert result.samples["sec_kwh_per_kg"] == []


def test_kpis_with_no_data_or_no_windows_are_null_with_zero_coverage():
    result = c.steady_kpis({}, [(0, ns(10))], "E", KPI_POLICY)
    assert list(result.entries) == list(c.KPI_UNITS)
    for name, entry in result.entries.items():
        assert set(entry) == set(SCHEMA["$defs"]["kpi"]["required"])
        assert entry["value"] is None
        assert entry["status"] == "none"
        assert entry["coverage"] == 0.0
        assert entry["interval_low"] is None and entry["interval_high"] is None
        assert result.samples[name] == []
    none = c.steady_kpis({"voltage": ramp_series([1.0, 2.0])}, [], "E", KPI_POLICY)
    assert none.entries["voltage_mean_v"]["value"] is None
    assert none.entries["voltage_mean_v"]["coverage"] == 0.0


def test_kpis_only_use_instants_and_time_inside_the_windows():
    series = {"voltage": ramp_series([100.0, 10.0, 10.0, 10.0, 10.0, 100.0], start_s=0)}
    result = c.steady_kpis(series, [(ns(1), ns(5))], "E", {**KPI_POLICY, "bootstrap_resamples": 5})
    assert result.entries["voltage_mean_v"]["value"] == 10.0
    assert result.entries["voltage_mean_v"]["coverage"] == 1.0


def test_kpis_over_two_windows_use_each_windows_own_blocks():
    series = {"voltage": ramp_series([10.0] * 12)}
    policy = {**KPI_POLICY, "bootstrap_resamples": 20}
    result = c.steady_kpis(series, [(0, ns(5)), (ns(6), ns(12))], "E", policy)
    assert result.entries["voltage_mean_v"]["value"] == 10.0
    assert set(result.samples["voltage_mean_v"]) == {10.0}


def test_kpi_bootstrap_is_deterministic_and_seeded_per_kpi_and_experiment():
    series = {"voltage": ramp_series([10.0 + (i % 7) for i in range(60)])}
    policy = {**c.POLICY, "bootstrap_block_s": 10, "bootstrap_resamples": 50}
    a = c.steady_kpis(series, [(0, ns(60))], "EXP_001", policy)
    b = c.steady_kpis(series, [(0, ns(60))], "EXP_001", policy)
    other = c.steady_kpis(series, [(0, ns(60))], "EXP_002", policy)
    assert a.samples == b.samples and a.entries == b.entries
    assert a.samples["voltage_mean_v"] != other.samples["voltage_mean_v"]
    assert a.entries["voltage_mean_v"]["value"] == other.entries["voltage_mean_v"]["value"]


def test_kpi_samples_default_to_1000_resamples():
    series = {"voltage": ramp_series([10.0 + (i % 3) for i in range(300)])}
    result = c.steady_kpis(series, [(0, ns(300))], "EXP_001", c.POLICY)
    assert len(result.samples["voltage_mean_v"]) == 1000


# ---------------------------------------------------------------------------- KPI differences


def entry(value, status="complete"):
    return {
        "value": value,
        "unit": "x",
        "coverage": 1.0 if status == "complete" else 0.5,
        "status": status if value is not None else "none",
        "interval_low": None,
        "interval_high": None,
    }


def kpi_result(values: dict, statuses=None, samples=None):
    statuses = statuses or {}
    samples = samples or {}
    entries = {
        name: entry(values.get(name), statuses.get(name, "complete")) for name in c.KPI_UNITS
    }
    return c.KpiResult(
        entries=entries,
        samples={
            name: samples.get(name, [] if values.get(name) is None else [values[name]])
            for name in c.KPI_UNITS
        },
    )


def test_kpi_difference_is_b_minus_a_with_interval_from_elementwise_differences():
    sa = [float(i) for i in range(101)]
    sb = [float(i) + 10.0 + (i % 2) for i in range(101)]
    a = kpi_result({"voltage_mean_v": 50.0}, samples={"voltage_mean_v": sa})
    b = kpi_result({"voltage_mean_v": 61.0}, samples={"voltage_mean_v": sb})
    out = c.kpi_differences(a, b)
    row = out[0]
    assert [r["name"] for r in out] == list(c.KPI_UNITS)
    assert row["unit"] == "V"
    assert row["difference"] == 11.0
    diffs = sorted(y - x for x, y in zip(sa, sb, strict=True))
    assert row["interval_low"] == pytest.approx(c.percentile(diffs, 0.025))
    assert row["interval_high"] == pytest.approx(c.percentile(diffs, 0.975))
    assert row["excludes_zero"] is True
    assert row["coverage_status"] == "both_complete"
    for r in out:
        assert set(r) == set(
            SCHEMA["$defs"]["comparison"]["properties"]["kpis"]["items"]["required"]
        )


def test_kpi_difference_interval_straddling_zero_does_not_exclude_it():
    sa = [float(i % 5) for i in range(100)]
    sb = [float((i + 2) % 5) for i in range(100)]
    a = kpi_result({"voltage_mean_v": 2.0}, samples={"voltage_mean_v": sa})
    b = kpi_result({"voltage_mean_v": 2.0}, samples={"voltage_mean_v": sb})
    row = c.kpi_differences(a, b)[0]
    assert row["difference"] == 0.0
    assert row["excludes_zero"] is False


def test_kpi_partial_on_one_side_is_partial_coverage():
    a = kpi_result(
        {"mean_power_kw": 5.0},
        statuses={"mean_power_kw": "partial"},
        samples={"mean_power_kw": [5.0, 5.0]},
    )
    b = kpi_result({"mean_power_kw": 6.0}, samples={"mean_power_kw": [6.0, 6.0]})
    row = c.kpi_differences(a, b)[1]
    assert row["coverage_status"] == "partial_coverage"
    assert row["difference"] == 1.0
    assert row["interval_low"] == 1.0
    both_partial = kpi_result({"mean_power_kw": 6.0}, statuses={"mean_power_kw": "partial"})
    assert c.kpi_differences(a, both_partial)[1]["coverage_status"] == "partial_coverage"
    assert c.kpi_differences(b, a)[1]["coverage_status"] == "partial_coverage"


def test_kpi_null_on_either_side_is_not_available_with_null_difference():
    a = kpi_result({"sec_kwh_per_kg": None})
    b = kpi_result({"sec_kwh_per_kg": 3.0})
    for x, y in ((a, b), (b, a), (a, a)):
        row = c.kpi_differences(x, y)[4]
        assert row["coverage_status"] == "not_available"
        assert row["difference"] is None
        assert row["interval_low"] is None and row["interval_high"] is None
        assert row["excludes_zero"] is None


def test_kpi_difference_without_matching_samples_has_no_interval():
    a = kpi_result({"voltage_mean_v": 1.0}, samples={"voltage_mean_v": [1.0, 1.0, 1.0]})
    b = kpi_result({"voltage_mean_v": 2.0}, samples={"voltage_mean_v": [2.0, 2.0]})
    row = c.kpi_differences(a, b)[0]
    assert row["difference"] == 1.0
    assert row["interval_low"] is None
    assert row["excludes_zero"] is None


def test_kpi_difference_end_to_end_with_real_kpis():
    series_a = {"voltage": ramp_series([10.0 + (i // 10) for i in range(100)])}
    series_b = {"voltage": ramp_series([25.0 + (i // 10) for i in range(100)])}
    policy = {**c.POLICY, "bootstrap_block_s": 10, "bootstrap_resamples": 100}
    a = c.steady_kpis(series_a, [(0, ns(100))], "EXP_001", policy)
    b = c.steady_kpis(series_b, [(0, ns(100))], "EXP_002", policy)
    row = c.kpi_differences(a, b, policy)[0]
    assert row["difference"] == pytest.approx(15.0)
    assert row["interval_low"] < row["interval_high"]
    assert row["interval_low"] > 0
    assert row["excludes_zero"] is True
    assert row["coverage_status"] == "both_complete"
    # the same experiment compared with itself has a zero difference and an interval around it
    same = c.kpi_differences(a, a, policy)[0]
    assert same["difference"] == 0.0
    assert same["interval_low"] == same["interval_high"] == 0.0
    assert same["excludes_zero"] is False


# ---------------------------------------------------------------------------- pressure drop


def test_pressure_drop_fit_on_exact_lines():
    rng = random.Random(3)
    times = [ns(2 * i) for i in range(200)]
    air = [(t, 1000.0 + rng.uniform(0, 400)) for t in times]
    linear = [(t, 0.5 + 2.0 * a) for (t, a) in air]
    policy = {**c.POLICY, "min_instants": 100}
    out = c.pressure_drop_fit(air, linear, [(0, ns(400))], policy)
    assert out["instants"] == 200
    assert out["slope_air_flow"] == pytest.approx(2.0)
    assert out["intercept_air_flow"] == pytest.approx(0.5, abs=1e-6)
    assert out["r2_air_flow"] == pytest.approx(1.0)
    assert out["best_lag_s"] == 0
    assert out["corr_at_best_lag"] == pytest.approx(1.0)
    assert out["corr_at_zero"] == pytest.approx(1.0)
    assert set(out) == set(
        SCHEMA["properties"]["pressure_drop_check"]["properties"]["per_experiment"]["items"][
            "required"
        ]
    ) - {"experiment_id"}

    quad = [(t, 3.0 + 0.001 * a * a) for (t, a) in air]
    out = c.pressure_drop_fit(air, quad, [(0, ns(400))], policy)
    assert out["slope_air_flow_sq"] == pytest.approx(0.001)
    assert out["intercept_air_flow_sq"] == pytest.approx(3.0, abs=1e-6)
    assert out["r2_air_flow_sq"] == pytest.approx(1.0)
    assert out["r2_air_flow"] < 1.0  # the plain line cannot be exact for a quadratic


def test_pressure_drop_fit_uses_only_window_instants_with_air_flow_at_the_same_instant():
    air = [(ns(t), 100.0 + t) for t in range(0, 20)]
    air = [p for p in air if p[0] != ns(6)]
    drop = [(ns(t), 1.0 + 0.5 * (100.0 + t)) for t in range(0, 20, 2)] + [(ns(7), 5.0)]
    policy = {**c.POLICY, "min_instants": 3}
    out = c.pressure_drop_fit(air, drop, [(ns(2), ns(10)), (ns(14), ns(16))], policy)
    # pressure_drop instants in [2,10) and [14,16): 2, 4, 7, 8, 14 (6 has no air flow; 10, 12
    # and 16+ are outside the windows)
    assert out["instants"] == 5
    assert out["slope_air_flow"] is not None


def test_pressure_drop_fit_flat_or_too_short_gives_nulls():
    air = [(ns(t), 100.0) for t in range(10)]
    drop = [(ns(t), 5.0 + t) for t in range(10)]
    policy = {**c.POLICY, "min_instants": 3}
    out = c.pressure_drop_fit(air, drop, [(0, ns(10))], policy)
    assert out["instants"] == 10
    assert out["slope_air_flow"] is None and out["r2_air_flow"] is None
    assert out["slope_air_flow_sq"] is None
    assert out["best_lag_s"] is None
    empty = c.pressure_drop_fit([], [], [(0, ns(10))], policy)
    assert empty["instants"] == 0
    assert all(v is None for k, v in empty.items() if k != "instants")
    one = c.pressure_drop_fit([(0, 1.0)], [(0, 2.0)], [(0, ns(10))], policy)
    assert one["instants"] == 1 and one["slope_air_flow"] is None


def test_pressure_drop_lag_finds_a_shift():
    rng = random.Random(8)
    air = [(ns(i), rng.uniform(1000, 1400)) for i in range(-100, 300)]
    lookup = dict(air)
    times = [ns(i) for i in range(0, 300, 2)]
    drop = [(t, 0.01 * lookup[t - ns(10)]) for t in times]
    policy = {**c.POLICY, "min_instants": 100}
    out = c.pressure_drop_fit(air, drop, [(0, ns(300))], policy)
    assert out["best_lag_s"] == 10
    assert out["corr_at_best_lag"] == pytest.approx(1.0)
    assert abs(out["corr_at_zero"]) < 0.4


def test_across_line_on_exact_lines():
    out = c.across_line([(1200.0, 15.0), (1200.0, 15.0), (2400.0, 60.0)])
    assert out["slope"] == pytest.approx(0.0375)
    assert out["intercept"] == pytest.approx(-30.0)
    assert out["r2"] == pytest.approx(1.0)
    out = c.across_line([(0.0, 1.0), (1.0, 3.0), (2.0, 5.0)])
    assert (out["slope"], out["intercept"], out["r2"]) == (
        pytest.approx(2.0),
        pytest.approx(1.0),
        pytest.approx(1.0),
    )
    assert set(out) == {"slope", "intercept", "r2"}


def test_across_line_with_scatter_has_r2_below_one():
    out = c.across_line([(0.0, 0.0), (1.0, 1.0), (2.0, 1.0), (3.0, 4.0)])
    assert 0 < out["r2"] < 1
    assert out["slope"] == pytest.approx(1.2)


def test_across_line_degenerate_inputs_are_null():
    null = {"slope": None, "intercept": None, "r2": None}
    assert c.across_line([]) == null
    assert c.across_line([(1.0, 2.0)]) == null
    assert c.across_line([(1.0, 2.0), (1.0, 3.0)]) == null
    assert c.across_line([(1.0, None), (2.0, 3.0)]) == null
    flat_y = c.across_line([(1.0, 5.0), (2.0, 5.0), (3.0, 5.0)])
    assert flat_y["slope"] == 0.0 and flat_y["intercept"] == 5.0 and flat_y["r2"] is None


# ---------------------------------------------------------------------------- split check


def test_split_check_points_medians_and_relative_change():
    boundary = ns(100)
    series = [(ns(t), v) for t, v in ((10, 4.0), (20, 6.0), (30, 5.0), (100, 10.0), (110, 14.0))]
    out = c.split_check(series, boundary)
    assert out == {
        "before_points": 3,
        "before_median": 5.0,
        "after_points": 2,
        "after_median": 12.0,
        "relative_change": pytest.approx(1.4),
    }


def test_split_check_boundary_instant_belongs_to_after():
    out = c.split_check([(ns(99.999999999), 1.0), (ns(100), 2.0)], ns(100))
    assert out["before_points"] == 1 and out["after_points"] == 1
    assert out["before_median"] == 1.0 and out["after_median"] == 2.0
    assert out["relative_change"] == 1.0


def test_split_check_with_an_empty_side():
    only_before = c.split_check([(ns(1), 3.0), (ns(2), 5.0)], ns(100))
    assert only_before == {
        "before_points": 2,
        "before_median": 4.0,
        "after_points": 0,
        "after_median": None,
        "relative_change": None,
    }
    only_after = c.split_check([(ns(200), 3.0)], ns(100))
    assert only_after["before_points"] == 0 and only_after["before_median"] is None
    assert only_after["after_median"] == 3.0
    assert only_after["relative_change"] is None
    nothing = c.split_check([], ns(100))
    assert nothing["before_points"] == 0 and nothing["after_points"] == 0
    assert nothing["relative_change"] is None


def test_split_check_skips_null_values_and_zero_before_median():
    raw = [(ns(1), None), (ns(2), 4.0), (ns(150), None), (ns(160), 8.0)]
    out = c.split_check(raw, ns(100))
    assert out["before_points"] == 1 and out["after_points"] == 1
    assert out["relative_change"] == 1.0
    zero = c.split_check([(ns(1), 0.0), (ns(200), 5.0)], ns(100))
    assert zero["before_median"] == 0.0
    assert zero["relative_change"] is None
    assert set(out) == {
        "before_points",
        "before_median",
        "after_points",
        "after_median",
        "relative_change",
    }


def test_median_helper():
    assert c.median([]) is None
    assert c.median([3.0]) == 3.0
    assert c.median([3.0, 1.0]) == 2.0
    assert c.median([5.0, 1.0, 3.0]) == 3.0


def test_pearson_and_simple_fit_degenerate_cases():
    assert c.pearson([1.0], [1.0]) is None
    assert c.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
    assert c.pearson([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) is None
    assert c.pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    assert c.pearson([1.0, 2.0, 3.0], [6.0, 4.0, 2.0]) == pytest.approx(-1.0)
    assert c.simple_fit([1.0], [1.0]) is None
    assert c.simple_fit([2.0, 2.0], [1.0, 3.0]) is None


# ---------------------------------------------------------------------------- end to end (pure)


def test_rows_to_fit_on_a_fixture_shaped_series():
    """1 Hz hydrolyzer signals, 0.2 Hz temperature, two steady windows: 840 instants."""
    rng = random.Random(17)
    n = 1200
    temp = [(ns(5 * k), 35.0 + 0.005 * 5 * k + rng.uniform(-0.05, 0.05)) for k in range(n // 5)]
    series = {
        "current": [(ns(i), 150.0 + rng.uniform(-0.5, 0.5)) for i in range(n)],
        "flow": [
            (ns(i), 40.0 + 2.0 * math.sin(i / 47) + rng.uniform(-0.05, 0.05)) for i in range(n)
        ],
        "pressure": [
            (ns(i), 2.5 + 0.1 * math.sin(i / 67) + rng.uniform(-0.005, 0.005)) for i in range(n)
        ],
        "electrolyte_temperature": temp,
    }
    max_age = 10 * S
    from pipeline.metrics import as_of

    series["voltage"] = []
    for i in range(n):
        t_i = as_of(temp, ns(i), max_age)
        v = (
            40.0
            + 0.3 * series["current"][i][1]
            - 0.2 * series["flow"][i][1]
            + 3.0 * series["pressure"][i][1]
            - 0.1 * t_i
            + rng.uniform(-0.05, 0.05)
        )
        series["voltage"].append((ns(i), v))
    windows = [(ns(180), ns(600)), (ns(720), ns(1140))]
    rows = c.model_rows("hydrolyzer", series, windows)
    assert len(rows) == 840
    entry = c.analyse_model(
        rows,
        "hydrolyzer",
        "steady",
        "EXP_001",
        {"flow": series["flow"], "pressure": series["pressure"]},
        FAST,
    )
    assert entry["testable"] is True
    assert term(entry, "flow")["coefficient"] == pytest.approx(-0.2, abs=0.05)
    assert term(entry, "pressure")["coefficient"] == pytest.approx(3.0, abs=0.5)
    assert term(entry, "flow")["best_lag_s"] is not None
