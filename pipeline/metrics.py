"""Derived process metrics (M4): pure functions, one declared policy table, no I/O.

Everything here is a plain function over plain lists, so each formula can be checked by hand on a
tiny series. The accepted readings come in from `pipeline/metrics_store.py`; the batch job that
ties the two together is `scripts/metrics.py`. Nothing in this module reads a database or a file.

Series are `list[tuple[int, float]]`: `(time in ns since the epoch, value)`, ascending in time.

Decisions (M4, `.workflow/dac.md`): 4 accepted inputs only, nothing filled; 5 exact-instant joins
and as-of ambient; 6 trapezoid integration with a gap rule; 7 power residual; 8 energy twice;
9 capture rate; 10 capture efficiency; 11 energy per kg over the overlap; 12 coverage and labels;
13 data-quality shares; 15 policy table and fingerprint; 16 plausibility checks.

`METRICS_VERSION` names the rule set and `POLICY` holds every number the rules read. A unit test
pins `METRICS_FINGERPRINT` (the SHA-256 of the canonical JSON of `POLICY`), so editing a number
without bumping the version fails the test. The three physical conversions that cannot change
(`KELVIN_OFFSET`, hPa to Pa, ppm to a fraction) and the unit scale factors are plain module
constants, not policy: they are not choices.
"""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from pipeline.signals import DECLARED_SIGNALS, NOMINAL_INTERVAL_S

METRICS_VERSION = "m4-v1"

# ---------------------------------------------------------------------------- policy constants

AMBIENT_MAX_AGE_S = 120  # latest ambient reading usable when at most this old (2 x nominal)
POWER_MAX_SPACING_S = 2  # a power spacing above this is a gap (2 x 1 s)
CAPTURE_MAX_SPACING_S = 4  # a capture spacing above this is a gap (2 x 2 s)
POWER_TOL_REL = 0.01  # |residual| <= POWER_TOL_REL x |V x I| + POWER_TOL_W agrees
POWER_TOL_W = 10
MOLAR_MASS_CO2_KG_MOL = 0.04401
GAS_CONSTANT = 8.314462618  # J / (mol K)
COMPLETE_COVERAGE = 0.95  # coverage at or above this is "complete"
SEC_FLOOR_KWH_PER_KG = 0.10  # below the minimum work of separating CO2 from air
ENERGY_AGREEMENT_REL = 0.01  # |energy_relative_difference| at most this passes

# The declared policy table. Its keys are exactly `parameters` in
# `contracts/metrics_summary.schema.json`; the unit test reads the schema and compares.
POLICY: dict[str, float] = {
    "power_max_spacing_s": POWER_MAX_SPACING_S,
    "capture_max_spacing_s": CAPTURE_MAX_SPACING_S,
    "ambient_max_age_s": AMBIENT_MAX_AGE_S,
    "power_tol_rel": POWER_TOL_REL,
    "power_tol_w": POWER_TOL_W,
    "complete_coverage": COMPLETE_COVERAGE,
    "co2_molar_mass_kg_per_mol": MOLAR_MASS_CO2_KG_MOL,
    "gas_constant_j_per_mol_k": GAS_CONSTANT,
    "sec_floor_kwh_per_kg": SEC_FLOOR_KWH_PER_KG,
    "energy_agreement_rel": ENERGY_AGREEMENT_REL,
}


def policy_fingerprint() -> str:
    """SHA-256 of the canonical JSON of `POLICY` (sorted keys, compact separators)."""
    canonical = json.dumps(POLICY, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


METRICS_FINGERPRINT = policy_fingerprint()

# ---------------------------------------------------------------------------- fixed conversions

KELVIN_OFFSET = 273.15  # degC to K
PA_PER_HPA = 100.0
PPM = 1e-6
NS_PER_S = 1_000_000_000
SECONDS_PER_HOUR = 3600.0
WS_PER_KWH = 3.6e6  # watt-seconds in a kilowatt-hour

ACCEPTED = "accepted"  # the verdict of an accepted processed row (pipeline.cleaning.ACCEPTED)

# ---------------------------------------------------------------------------- names and units

METRIC_UNITS: dict[str, str] = {
    "energy_kwh": "kWh",
    "energy_logged_kwh": "kWh",
    "energy_relative_difference": "fraction",
    "mean_power_kw": "kW",
    "capture_efficiency_mean": "fraction",
    "co2_captured_kg": "kg",
    "co2_inlet_kg": "kg",
    "capture_rate_mean_kg_h": "kg/h",
    "sec_kwh_per_kg": "kWh/kg",
    "completeness": "fraction",
    "valid_fraction": "fraction",
    "bad_fraction": "fraction",
    "uncertain_fraction": "fraction",
}

QUALITY_METRICS: tuple[str, ...] = (
    "completeness",
    "valid_fraction",
    "bad_fraction",
    "uncertain_fraction",
)

SERIES_UNITS: dict[str, str] = {
    "power_computed": "W",
    "power_residual": "W",
    "capture_efficiency": "fraction",
    "capture_rate": "kg/h",
}

PLAUSIBILITY_CHECKS: tuple[str, ...] = (
    "capture_below_inlet",
    "efficiency_in_unit_interval",
    "energy_agreement",
    "sec_above_floor",
)

Series = list[tuple[int, float]]
Intervals = list[tuple[int, int]]

# ---------------------------------------------------------------------------- joins


def _limit_ns(max_spacing_s: float) -> int:
    """The spacing limit as an integer number of ns, so every comparison is exact."""
    return round(max_spacing_s * NS_PER_S)


def _join(first: Series, *others: Series) -> list[tuple[int, tuple[float, ...]]]:
    """Instants present in every series (exact ns equality), ascending, with all their values."""
    lookups = [dict(s) for s in others]
    joined: list[tuple[int, tuple[float, ...]]] = []
    for t, v in first:
        values = [v]
        for lookup in lookups:
            other = lookup.get(t)
            if other is None:
                break
            values.append(other)
        else:
            joined.append((t, tuple(values)))
    return joined


def as_of(series: Series, t_ns: int, max_age_ns: int) -> float | None:
    """The latest value at or before `t_ns`, if its age is at most `max_age_ns`; else None.

    An age equal to `max_age_ns` is used; one nanosecond more is not. The series is not changed
    and nothing is interpolated.
    """
    idx = bisect_right(series, t_ns, key=lambda point: point[0])
    if idx == 0:
        return None
    t, value = series[idx - 1]
    if t_ns - t > max_age_ns:
        return None
    return value


# ---------------------------------------------------------------------------- derived series


def power_series(voltage: Series, current: Series) -> Series:
    """`voltage x current` (W) at the instants where both exist."""
    return [(t, v * i) for t, (v, i) in _join(voltage, current)]


def residual_series(power: Series, voltage: Series, current: Series) -> Series:
    """`power - voltage x current` (W) at the instants where all three exist."""
    return [(t, p - v * i) for t, (p, v, i) in _join(power, voltage, current)]


def within_tolerance(residual: float, ui: float) -> bool:
    """True when `|residual| <= POWER_TOL_REL x |ui| + POWER_TOL_W` (`ui` is voltage x current)."""
    return abs(residual) <= POWER_TOL_REL * abs(ui) + POWER_TOL_W


def efficiency_series(co2_in: Series, co2_out: Series) -> Series:
    """`(co2_in - co2_out) / co2_in` at the instants where both exist.

    Values at or below zero are kept (not clamped). An instant with `co2_in == 0` has no defined
    efficiency and is left out; the declared limit for CO2 in is 0..5000 ppm, so this is a guard
    and not an expected case.
    """
    return [(t, (a - b) / a) for t, (a, b) in _join(co2_in, co2_out) if a != 0]


def capture_series(
    co2_in: Series,
    co2_out: Series,
    air_flow: Series,
    temperature: Series,
    pressure: Series,
    *,
    inlet: bool = False,
) -> Series:
    """Captured CO2 rate in kg/h, or the inlet CO2 rate when `inlet` is true.

    `air_flow [m3/h] x ppm x 1e-6 x p x M / (R x T)` with p = ambient pressure [hPa] x 100 Pa,
    T = ambient temperature [degC] + 273.15 K, M = 0.04401 kg/mol and R = 8.314462618. The ppm
    is `co2_in - co2_out` (captured) or `co2_in` (inlet).

    Instants: where co2_in, co2_out and air_flow are all present at the same instant, in both
    modes, so the inlet series covers the same time as the captured series. Ambient temperature
    and pressure are taken as-of (latest reading at or before the instant, age at most
    `AMBIENT_MAX_AGE_S`); an instant with either one missing has no value.
    """
    max_age_ns = AMBIENT_MAX_AGE_S * NS_PER_S
    out: Series = []
    for t, (c_in, c_out, flow) in _join(co2_in, co2_out, air_flow):
        temp_c = as_of(temperature, t, max_age_ns)
        press_hpa = as_of(pressure, t, max_age_ns)
        if temp_c is None or press_hpa is None:
            continue
        ppm = c_in if inlet else c_in - c_out
        density = (
            press_hpa
            * PA_PER_HPA
            * MOLAR_MASS_CO2_KG_MOL
            / (GAS_CONSTANT * (temp_c + KELVIN_OFFSET))
        )
        out.append((t, flow * ppm * PPM * density))
    return out


# ---------------------------------------------------------------------------- integration


def covered_intervals(series: Series, max_spacing_s: float) -> Intervals:
    """Maximal `(start_ns, end_ns)` intervals made of bridged spacings, ascending.

    A spacing is bridged when it is at most `max_spacing_s` (an exact integer-ns comparison, so
    the limit plus 1 ns is not bridged). Consecutive bridged spacings merge into one interval; a
    point with no bridged neighbour is in no interval.
    """
    limit = _limit_ns(max_spacing_s)
    intervals: Intervals = []
    for (t0, _), (t1, _) in zip(series, series[1:], strict=False):
        if t1 - t0 > limit:
            continue
        if intervals and intervals[-1][1] == t0:
            intervals[-1] = (intervals[-1][0], t1)
        else:
            intervals.append((t0, t1))
    return intervals


def integrate(series: Series, max_spacing_s: float) -> tuple[float, float]:
    """`(integral, covered_seconds)` by the trapezoid rule over bridged spacings only.

    The integral is in value x seconds. Spacings above `max_spacing_s` are skipped: they add to
    neither the integral nor the covered seconds. Nothing is scaled up for the missing time.
    """
    limit = _limit_ns(max_spacing_s)
    areas: list[float] = []
    covered_ns = 0
    for (t0, v0), (t1, v1) in zip(series, series[1:], strict=False):
        dt = t1 - t0
        if dt > limit:
            continue
        areas.append((v0 + v1) / 2.0 * (dt / NS_PER_S))
        covered_ns += dt
    return math.fsum(areas), covered_ns / NS_PER_S


def overlap(a: Intervals, b: Intervals) -> Intervals:
    """The intersection of two ascending interval lists; zero-length pieces are dropped."""
    out: Intervals = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if end > start:
            out.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _value_at(series: Series, times: list[int], t_ns: int) -> float:
    """The piecewise-linear interpolant of `series` at `t_ns`; raises outside its time span."""
    idx = bisect_left(times, t_ns)
    if idx < len(times) and times[idx] == t_ns:
        return series[idx][1]
    if idx == 0 or idx == len(times):
        raise ValueError(f"{t_ns} ns lies outside the series")
    t0, v0 = series[idx - 1]
    t1, v1 = series[idx]
    return v0 + (v1 - v0) * ((t_ns - t0) / (t1 - t0))


def integrate_over(series: Series, intervals: Intervals) -> float:
    """Integral (value x seconds) of the series over the given intervals, clipped exactly.

    On each interval the series is the piecewise-linear interpolant through its points; the
    interval ends are interpolated values, so a clipped interval gets no invented time and no
    dropped sliver. The intervals must lie inside the span of the series (they do when they come
    from `covered_intervals` / `overlap` of it); a `ValueError` says otherwise.
    """
    times = [t for t, _ in series]
    areas: list[float] = []
    for start, end in intervals:
        points = [(start, _value_at(series, times, start))]
        points.extend(series[bisect_right(times, start) : bisect_left(times, end)])
        points.append((end, _value_at(series, times, end)))
        for (t0, v0), (t1, v1) in zip(points, points[1:], strict=False):
            areas.append((v0 + v1) / 2.0 * ((t1 - t0) / NS_PER_S))
    return math.fsum(areas)


def _seconds(intervals: Intervals) -> float:
    return sum(end - start for start, end in intervals) / NS_PER_S


def status_for(value: float | None, coverage: float | None) -> str:
    """`none` when the value is null, else `complete` at coverage >= 0.95, else `partial`."""
    if value is None:
        return "none"
    if coverage is not None and coverage >= COMPLETE_COVERAGE:
        return "complete"
    return "partial"


# ---------------------------------------------------------------------------- data quality


def _safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def signal_quality(counts: list[dict], duration_s: float) -> list[dict]:
    """One entry per declared `(source, signal)` pair (25), sorted by source then signal.

    `counts` are the rows of a `GROUP BY quality, verdict` over both processed tables: dicts with
    keys `source`, `signal`, `quality` (`GOOD` / `UNCERTAIN` / `BAD`), `verdict` (`accepted` or
    `excluded`) and `count`. A pair with no rows is listed with `present` 0. A pair that is not
    declared raises `ValueError`.

    Each entry is a dict with keys `source`, `signal`, `nominal_interval_s` (float, or None for
    the two on-change state signals), `present` (all rows), `expected` (`floor(duration_s /
    nominal)`, None for on-change signals), `accepted` (rows with verdict `accepted`), `bad` and
    `uncertain` (rows with that acquisition quality), `completeness` (`present / expected`, None
    when expected is None or 0), `valid_fraction` (`accepted / present`), `bad_fraction`,
    `uncertain_fraction` (None when `present` is 0).
    """
    tally = {
        (source, signal): {"present": 0, "accepted": 0, "bad": 0, "uncertain": 0}
        for source, signals in DECLARED_SIGNALS.items()
        for signal in signals
    }
    for row in counts:
        pair = (row["source"], row["signal"])
        if pair not in tally:
            raise ValueError(f"undeclared signal {pair}")
        n = int(row["count"])
        entry = tally[pair]
        entry["present"] += n
        if row["verdict"] == ACCEPTED:
            entry["accepted"] += n
        if row["quality"] == "BAD":
            entry["bad"] += n
        elif row["quality"] == "UNCERTAIN":
            entry["uncertain"] += n

    entries: list[dict] = []
    for (source, signal), t in sorted(tally.items()):
        nominal = NOMINAL_INTERVAL_S.get((source, signal))
        expected = None if nominal is None else math.floor(duration_s / nominal)
        entries.append(
            {
                "source": source,
                "signal": signal,
                "nominal_interval_s": nominal,
                "present": t["present"],
                "expected": expected,
                "accepted": t["accepted"],
                "bad": t["bad"],
                "uncertain": t["uncertain"],
                "completeness": None if expected is None else _safe_div(t["present"], expected),
                "valid_fraction": _safe_div(t["accepted"], t["present"]),
                "bad_fraction": _safe_div(t["bad"], t["present"]),
                "uncertain_fraction": _safe_div(t["uncertain"], t["present"]),
            }
        )
    return entries


def _share(value: float | None) -> dict:
    return {"value": value, "unit": "fraction", "coverage": None, "status": None}


def experiment_quality(rows: list[dict]) -> dict[str, dict]:
    """The four experiment-level quality shares as metric objects, from `signal_quality` entries.

    Returns `{"completeness", "valid_fraction", "bad_fraction", "uncertain_fraction"}`, each
    `{value, unit: "fraction", coverage: None, status: None}`. `completeness` is the sum of
    `present` over the polled entries (expected not None) divided by the sum of `expected`; the
    three fractions are the sums of `accepted`, `bad` and `uncertain` over all entries divided by
    the sum of `present` over all entries. A zero denominator gives value None.
    """
    polled = [r for r in rows if r["expected"] is not None]
    total_present = sum(r["present"] for r in rows)
    return {
        "completeness": _share(
            _safe_div(sum(r["present"] for r in polled), sum(r["expected"] for r in polled))
        ),
        "valid_fraction": _share(_safe_div(sum(r["accepted"] for r in rows), total_present)),
        "bad_fraction": _share(_safe_div(sum(r["bad"] for r in rows), total_present)),
        "uncertain_fraction": _share(_safe_div(sum(r["uncertain"] for r in rows), total_present)),
    }


# ---------------------------------------------------------------------------- one experiment


@dataclass
class ExperimentInputs:
    """The accepted readings of one experiment (series as `list[tuple[int, float]]`, ns, ascending).

    voltage [V], current [A], power [W] (the logged power), co2_in [ppm], co2_out [ppm],
    air_flow [m3/h], temperature [degC] (ambient), pressure [hPa] (ambient). `signals` is the
    optional output of `signal_quality` for this experiment; when given, the four quality shares
    are filled from it, otherwise they are null.
    """

    voltage: Series = field(default_factory=list)
    current: Series = field(default_factory=list)
    power: Series = field(default_factory=list)
    co2_in: Series = field(default_factory=list)
    co2_out: Series = field(default_factory=list)
    air_flow: Series = field(default_factory=list)
    temperature: Series = field(default_factory=list)
    pressure: Series = field(default_factory=list)
    signals: list[dict] | None = None


@dataclass
class ExperimentResult:
    """What `experiment_metrics` returns.

    metrics: `{name: {"value": float | None, "unit": str, "coverage": float | None,
        "status": "complete" | "partial" | "none" | None}}` for the 13 names of `METRIC_UNITS`,
        in that order. Coverage is covered seconds / duration_s (0.0 when nothing is covered);
        the four quality shares have coverage and status None.
    power_check: `{instants_compared, within_tolerance, within_tolerance_fraction,
        residual_median_w, residual_p95_abs_w, residual_max_abs_w}`; the fraction and the
        residual statistics are None when no instant was compared. The p95 uses linear
        interpolation between order statistics (numpy's default method).
    efficiency_check: `{instants, at_or_below_zero}` (values <= 0 in `capture_efficiency`).
    power_computed, power_residual, capture_efficiency, capture_rate: the four derived series
        (`SERIES_UNITS`), as `list[tuple[int, float]]`.
    """

    metrics: dict[str, dict]
    power_check: dict
    efficiency_check: dict
    power_computed: Series
    power_residual: Series
    capture_efficiency: Series
    capture_rate: Series

    def series(self) -> dict[str, Series]:
        """The four series by name (the keys of `SERIES_UNITS`)."""
        return {
            "power_computed": self.power_computed,
            "power_residual": self.power_residual,
            "capture_efficiency": self.capture_efficiency,
            "capture_rate": self.capture_rate,
        }

    def series_written(self) -> dict[str, int]:
        """Number of points in each series (the summary's `series_written`)."""
        return {name: len(s) for name, s in self.series().items()}


def _metric(name: str, value: float | None, covered_s: float, duration_s: float) -> dict:
    coverage = covered_s / duration_s
    return {
        "value": value,
        "unit": METRIC_UNITS[name],
        "coverage": coverage,
        "status": status_for(value, coverage),
    }


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation between order statistics (numpy's default)."""
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _median(sorted_values: list[float]) -> float:
    n = len(sorted_values)
    mid = n // 2
    if n % 2:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _power_check(residual: Series, power_computed: Series) -> dict[str, float | int | None]:
    ui_at = dict(power_computed)
    compared = len(residual)
    within = sum(1 for t, r in residual if within_tolerance(r, ui_at[t]))
    absolute = sorted(abs(r) for _, r in residual)
    ordered = sorted(r for _, r in residual)
    return {
        "instants_compared": compared,
        "within_tolerance": within,
        "within_tolerance_fraction": _safe_div(within, compared),
        "residual_median_w": _median(ordered) if compared else None,
        "residual_p95_abs_w": _percentile(absolute, 0.95) if compared else None,
        "residual_max_abs_w": absolute[-1] if compared else None,
    }


def experiment_metrics(inputs: ExperimentInputs, duration_s: float) -> ExperimentResult:
    """All metrics of one experiment from its accepted readings (decisions 4-12).

    `duration_s` is the experiment length in seconds; every coverage is covered seconds divided
    by it. The 13 metric objects are always present; a metric that cannot be computed has value
    None, status `none` and coverage 0.0 (the quality shares: None, None).
    """
    power_computed = power_series(inputs.voltage, inputs.current)
    power_residual = residual_series(inputs.power, inputs.voltage, inputs.current)
    efficiency = efficiency_series(inputs.co2_in, inputs.co2_out)
    rate = capture_series(
        inputs.co2_in, inputs.co2_out, inputs.air_flow, inputs.temperature, inputs.pressure
    )
    inlet = capture_series(
        inputs.co2_in,
        inputs.co2_out,
        inputs.air_flow,
        inputs.temperature,
        inputs.pressure,
        inlet=True,
    )

    # Energy twice: each over its own covered time.
    e_ws, e_s = integrate(power_computed, POWER_MAX_SPACING_S)
    energy_kwh = e_ws / WS_PER_KWH if e_s > 0 else None
    l_ws, l_s = integrate(inputs.power, POWER_MAX_SPACING_S)
    energy_logged_kwh = l_ws / WS_PER_KWH if l_s > 0 else None
    mean_power_kw = energy_kwh / (e_s / SECONDS_PER_HOUR) if energy_kwh is not None else None

    # Relative difference over the overlap of the two covered-interval sets.
    power_cover = covered_intervals(power_computed, POWER_MAX_SPACING_S)
    logged_cover = covered_intervals(inputs.power, POWER_MAX_SPACING_S)
    energy_overlap = overlap(power_cover, logged_cover)
    rel_diff = None
    if energy_overlap:
        e_c = integrate_over(power_computed, energy_overlap)
        e_l = integrate_over(inputs.power, energy_overlap)
        rel_diff = (e_l - e_c) / e_c if e_c != 0 else None

    # Capture efficiency: plain mean of the series.
    eff_mean = math.fsum(v for _, v in efficiency) / len(efficiency) if efficiency else None
    _, eff_s = integrate(efficiency, CAPTURE_MAX_SPACING_S)

    # CO2 captured and inlet: integrals of the two rate series.
    cap_ws, cap_s = integrate(rate, CAPTURE_MAX_SPACING_S)
    inl_ws, inl_s = integrate(inlet, CAPTURE_MAX_SPACING_S)
    co2_captured = cap_ws / SECONDS_PER_HOUR if cap_s > 0 else None
    co2_inlet = inl_ws / SECONDS_PER_HOUR if inl_s > 0 else None
    rate_mean = co2_captured / (cap_s / SECONDS_PER_HOUR) if co2_captured is not None else None

    # Energy per kg CO2 over the overlap of the power and capture covered time.
    capture_cover = covered_intervals(rate, CAPTURE_MAX_SPACING_S)
    sec_overlap = overlap(power_cover, capture_cover)
    sec = None
    if sec_overlap:
        sec_kwh = integrate_over(power_computed, sec_overlap) / WS_PER_KWH
        sec_kg = integrate_over(rate, sec_overlap) / SECONDS_PER_HOUR
        sec = sec_kwh / sec_kg if sec_kg > 0 else None

    metrics = {
        "energy_kwh": _metric("energy_kwh", energy_kwh, e_s, duration_s),
        "energy_logged_kwh": _metric("energy_logged_kwh", energy_logged_kwh, l_s, duration_s),
        "energy_relative_difference": _metric(
            "energy_relative_difference", rel_diff, _seconds(energy_overlap), duration_s
        ),
        "mean_power_kw": _metric("mean_power_kw", mean_power_kw, e_s, duration_s),
        "capture_efficiency_mean": _metric("capture_efficiency_mean", eff_mean, eff_s, duration_s),
        "co2_captured_kg": _metric("co2_captured_kg", co2_captured, cap_s, duration_s),
        "co2_inlet_kg": _metric("co2_inlet_kg", co2_inlet, inl_s, duration_s),
        "capture_rate_mean_kg_h": _metric("capture_rate_mean_kg_h", rate_mean, cap_s, duration_s),
        "sec_kwh_per_kg": _metric("sec_kwh_per_kg", sec, _seconds(sec_overlap), duration_s),
    }
    if inputs.signals is not None:
        metrics.update(experiment_quality(inputs.signals))
    else:
        metrics.update({name: _share(None) for name in QUALITY_METRICS})

    return ExperimentResult(
        metrics=metrics,
        power_check=_power_check(power_residual, power_computed),
        efficiency_check={
            "instants": len(efficiency),
            "at_or_below_zero": sum(1 for _, v in efficiency if v <= 0),
        },
        power_computed=power_computed,
        power_residual=power_residual,
        capture_efficiency=efficiency,
        capture_rate=rate,
    )


# ---------------------------------------------------------------------------- plausibility


def plausibility(result: ExperimentResult) -> list[dict]:
    """The four plausibility checks, sorted by check name (decision 16).

    Each entry is `{check, passed, value, limit}`; `passed` is None when the tested metric is
    null (for `capture_below_inlet`, when either CO2 total is null).

    - `efficiency_in_unit_interval`: value `capture_efficiency_mean`, limit 1, passed when
      `0 <= value <= 1`.
    - `capture_below_inlet`: value `co2_captured_kg`, limit `co2_inlet_kg`, passed when
      `value <= limit`. A null inlet gives limit 0.0 (the contract wants a number there).
    - `sec_above_floor`: value `sec_kwh_per_kg`, limit `SEC_FLOOR_KWH_PER_KG`, passed when
      `value >= limit`.
    - `energy_agreement`: value `energy_relative_difference`, limit `ENERGY_AGREEMENT_REL`,
      passed when `|value| <= limit`.
    """
    m = result.metrics
    efficiency = m["capture_efficiency_mean"]["value"]
    captured = m["co2_captured_kg"]["value"]
    inlet = m["co2_inlet_kg"]["value"]
    sec = m["sec_kwh_per_kg"]["value"]
    rel_diff = m["energy_relative_difference"]["value"]
    return [
        {
            "check": "capture_below_inlet",
            "passed": None if captured is None or inlet is None else captured <= inlet,
            "value": captured,
            "limit": 0.0 if inlet is None else inlet,
        },
        {
            "check": "efficiency_in_unit_interval",
            "passed": None if efficiency is None else 0 <= efficiency <= 1,
            "value": efficiency,
            "limit": 1,
        },
        {
            "check": "energy_agreement",
            "passed": None if rel_diff is None else abs(rel_diff) <= ENERGY_AGREEMENT_REL,
            "value": rel_diff,
            "limit": ENERGY_AGREEMENT_REL,
        },
        {
            "check": "sec_above_floor",
            "passed": None if sec is None else sec >= SEC_FLOOR_KWH_PER_KG,
            "value": sec,
            "limit": SEC_FLOOR_KWH_PER_KG,
        },
    ]
