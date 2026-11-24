"""Experiment comparison (M5): pure analysis functions, one declared policy table, no I/O.

Everything here is a plain function over plain lists, so each rule can be checked by hand on a
tiny example. The accepted readings come in from `pipeline/compare_store.py`; the command that
ties the two together is `scripts/compare.py`. Nothing in this module reads a database or a file.

Series are `list[tuple[int, float]]`: `(time in ns since the epoch, value)`, ascending in time.
Windows are `list[tuple[int, int]]`: `(start_ns, end_ns)`, half-open `[start, end)`, ascending.
Floats in the returned dicts are not rounded here (the runner rounds); a value that the contract
allows to be null is `None`, never NaN.

Decisions (M5, `.workflow/dac.md`): 5 shared clock; 6 phases and the settle margin; 7 instant
join; 8 the voltage model (OLS) and its per-term numbers; 9 fits per model, window, scope;
10 block bootstrap; 11 lag search; 12 evidence rule; 13 steady-state KPIs; 14 comparability;
16 pressure drop against air flow; 17 air-flow split check; 18 policy table and fingerprint.

`COMPARE_VERSION` names the rule set and `POLICY` holds every number the rules read. A unit test
pins `COMPARE_FINGERPRINT` (the SHA-256 of the canonical JSON of `POLICY`), so editing a number
without bumping the version fails the test. The keys of `POLICY` are exactly the `parameters`
keys of `contracts/comparison_summary.schema.json`.

Two conventions used throughout:

- The normal matrix of a fit is the matrix of centred cross-products of the predictors (the
  intercept is removed by centring, each stratum at its own means). A fit is singular when a
  pivot of the Gaussian elimination (partial pivoting) is at or below `PIVOT_REL` times the
  largest diagonal entry of that matrix.
- Quantiles are type 7 (linear interpolation between order statistics, numpy's default).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from bisect import bisect_right
from dataclasses import dataclass, field

from pipeline.metrics import (
    NS_PER_S,
    SECONDS_PER_HOUR,
    WS_PER_KWH,
    as_of,
    covered_intervals,
    integrate_over,
    overlap,
    status_for,
)
from pipeline.metrics import POLICY as METRICS_POLICY

COMPARE_VERSION = "m5-v1"

# The declared policy table. Its keys are exactly `parameters` in
# `contracts/comparison_summary.schema.json`; the unit test reads the schema and compares.
POLICY: dict[str, float | int | str] = {
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


def policy_fingerprint() -> str:
    """SHA-256 of the canonical JSON of `POLICY` (sorted keys, compact separators)."""
    canonical = json.dumps(POLICY, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


COMPARE_FINGERPRINT = policy_fingerprint()

# A pivot at or below this fraction of the largest diagonal entry makes a fit singular (decision 8).
PIVOT_REL = 1e-9
# A series whose centred sum of squares is at most this fraction of its raw sum of squares is flat
# (constant up to rounding): a correlation or a line through it is not defined.
_FLAT_REL = 1e-28

# ---------------------------------------------------------------------------- names and units

# Model -> its four predictors in order: current, electrolyte_temperature, X1, X2.
MODELS: dict[str, tuple[str, str, str, str]] = {
    "hydrolyzer": ("current", "electrolyte_temperature", "flow", "pressure"),
    "absorber": ("current", "electrolyte_temperature", "air_flow", "pressure_drop"),
}

PREDICTOR_UNITS: dict[str, str] = {
    "current": "A",
    "electrolyte_temperature": "°C",
    "flow": "L/min",
    "pressure": "bar",
    "air_flow": "m³/h",
    "pressure_drop": "mbar",
}

KPI_UNITS: dict[str, str] = {
    "voltage_mean_v": "V",
    "mean_power_kw": "kW",
    "capture_rate_mean_kg_h": "kg/h",
    "capture_efficiency_mean": "fraction",
    "sec_kwh_per_kg": "kWh/kg",
}

FACTORS: tuple[str, ...] = (
    "current_setpoint",
    "current_setpoint_profile",
    "air_flow",
    "solvent_flow",
    "ambient_temperature",
    "relative_humidity",
    "sorbent_batch",
)

STEADY_STATE = "STEADY_STATE"

Series = list[tuple[int, float]]
Windows = list[tuple[int, int]]

# ---------------------------------------------------------------------------- small statistics


def percentile(sorted_values: list[float], q: float) -> float:
    """Type 7 quantile (linear interpolation between order statistics) of a sorted list."""
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def median(values: list[float]) -> float | None:
    """The median (mean of the two middle values for an even count); None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _interval(samples: list[float], level: float) -> tuple[float, float] | None:
    """`(low, high)` at `(1 - level) / 2` and `(1 + level) / 2` (type 7); None for no samples."""
    if not samples:
        return None
    ordered = sorted(samples)
    return percentile(ordered, (1 - level) / 2), percentile(ordered, (1 + level) / 2)


def _excludes_zero(low: float | None, high: float | None) -> bool:
    """True when the interval lies strictly on one side of zero (an endpoint of 0 does not)."""
    return low is not None and high is not None and (low > 0 or high < 0)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None for fewer than 2 pairs or a flat (constant) side."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = math.fsum(xs) / n
    my = math.fsum(ys) / n
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    if sxx <= _FLAT_REL * math.fsum(x * x for x in xs):
        return None
    if syy <= _FLAT_REL * math.fsum(y * y for y in ys):
        return None
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def simple_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float | None] | None:
    """Least-squares line `y = intercept + slope x` as `(slope, intercept, r2)`.

    None for fewer than 2 points or a flat x. `r2` is None when y is flat (nothing to explain).
    """
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = math.fsum(xs) / n
    my = math.fsum(ys) / n
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    if sxx <= _FLAT_REL * math.fsum(x * x for x in xs):
        return None
    syy = math.fsum((y - my) ** 2 for y in ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = my - slope * mx
    flat_y = syy <= _FLAT_REL * math.fsum(y * y for y in ys)
    return slope, intercept, None if flat_y else min(1.0, (sxy * sxy) / (sxx * syy))


# ---------------------------------------------------------------------------- shared clock


def experiment_time_s(t_ns: int, start_ns: int) -> float:
    """Seconds since the experiment's start: `(t_ns - start_ns) / 1e9` (decision 5)."""
    return (t_ns - start_ns) / NS_PER_S


@dataclass
class Phase:
    """One `process_state` phase: `[start_ns, end_ns)`, with its analysis window or None.

    `window` is `[start + settle, end)` when `start + settle < end`, otherwise None.
    """

    index: int
    state: str
    start_ns: int
    end_ns: int
    window: tuple[int, int] | None


def phases(events: list[tuple[int, int, str]], settle_s: float) -> list[Phase]:
    """Phases from accepted `process_state` events `(time_ns, end_ns, state)` (decision 6).

    Phases are numbered in time order. A phase of exactly `settle_s` seconds or less has no
    analysis window; one nanosecond over has a window of one nanosecond.
    """
    settle_ns = round(settle_s * NS_PER_S)
    out: list[Phase] = []
    for index, (start, end, state) in enumerate(sorted(events, key=lambda e: e[0])):
        win_start = start + settle_ns
        out.append(
            Phase(
                index=index,
                state=state,
                start_ns=start,
                end_ns=end,
                window=(win_start, end) if win_start < end else None,
            )
        )
    return out


def steady_windows(phase_list: list[Phase]) -> Windows:
    """The analysis windows of the `STEADY_STATE` phases, in time order."""
    return [p.window for p in phase_list if p.state == STEADY_STATE and p.window is not None]


# ---------------------------------------------------------------------------- instant join


@dataclass
class Rows:
    """Aligned instants of one fit (decision 7), ascending in time.

    `t` (ns), `window_index` (index into the windows list the rows came from) and
    `window_start` (ns, the start of that window) say where each instant sits for the bootstrap
    blocks. `voltage` is the response; `columns` maps each predictor name of the model
    (`MODELS[model]`) to its values at the same instants.
    """

    t: list[int] = field(default_factory=list)
    window_index: list[int] = field(default_factory=list)
    window_start: list[int] = field(default_factory=list)
    voltage: list[float] = field(default_factory=list)
    columns: dict[str, list[float]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.t)


def _window_of(starts: list[int], windows: Windows, t: int) -> int | None:
    idx = bisect_right(starts, t) - 1
    if idx >= 0 and t < windows[idx][1]:
        return idx
    return None


def model_rows(
    model: str,
    series: dict[str, Series],
    windows: Windows,
    policy: dict = POLICY,
) -> Rows:
    """The instants of one model inside the analysis windows (decision 7).

    Hydrolyzer: the instants of `voltage` where `current`, `flow` and `pressure` exist at the
    exact same instant. Absorber: the instants of `pressure_drop` where `voltage`, `current` and
    `air_flow` exist at the exact same instant. `electrolyte_temperature` is taken as-of (latest
    reading at or before the instant, at most `temp_max_age_s` old; an instant without one is
    dropped). Nothing is resampled or filled.
    """
    names = MODELS[model]
    x1, x2 = names[2], names[3]
    base_name = "voltage" if model == "hydrolyzer" else x2
    needed = ["voltage", "current", x1, x2]
    others = {n: dict(series.get(n, [])) for n in needed if n != base_name}
    temperature = series.get("electrolyte_temperature", [])
    max_age_ns = round(policy["temp_max_age_s"] * NS_PER_S)
    ordered = sorted(windows)
    starts = [w[0] for w in ordered]

    rows = Rows(columns={n: [] for n in names})
    for t, base_value in series.get(base_name, []):
        w = _window_of(starts, ordered, t)
        if w is None:
            continue
        values = {base_name: base_value}
        for n, lookup in others.items():
            v = lookup.get(t)
            if v is None:
                break
            values[n] = v
        else:
            temp = as_of(temperature, t, max_age_ns)
            if temp is None:
                continue
            rows.t.append(t)
            rows.window_index.append(w)
            rows.window_start.append(ordered[w][0])
            rows.voltage.append(values["voltage"])
            for n in names:
                rows.columns[n].append(temp if n == "electrolyte_temperature" else values[n])
    return rows


# ---------------------------------------------------------------------------- linear algebra


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve `a x = b` by Gaussian elimination with partial pivoting; None when singular.

    Singular means a pivot at or below `PIVOT_REL` times the largest diagonal entry of `a`.
    """
    p = len(b)
    if p == 0:
        return []
    limit = PIVOT_REL * max(a[i][i] for i in range(p))
    m = [list(a[i]) + [b[i]] for i in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) <= limit:
            return None
        m[c], m[piv] = m[piv], m[c]
        for r in range(c + 1, p):
            f = m[r][c] / m[c][c]
            if f:
                for k in range(c, p + 1):
                    m[r][k] -= f * m[c][k]
    x = [0.0] * p
    for i in range(p - 1, -1, -1):
        terms = [m[i][p]] + [-m[i][k] * x[k] for k in range(i + 1, p)]
        x[i] = math.fsum(terms) / m[i][i]
    return x


def _explained(sxx: list[list[float]], sxy: list[float], idx: list[int]) -> float | None:
    """Explained sum of squares of the model on the predictors `idx` (0.0 for none)."""
    if not idx:
        return 0.0
    beta = _solve([[sxx[i][j] for j in idx] for i in idx], [sxy[i] for i in idx])
    if beta is None:
        return None
    return math.fsum(b * sxy[i] for b, i in zip(beta, idx, strict=True))


def _vif(sxx: list[list[float]], j: int) -> float | None:
    """`1 / (1 - R^2)` of predictor `j` on the other predictors; None when undefined."""
    others = [i for i in range(len(sxx)) if i != j]
    if sxx[j][j] <= 0:
        return None
    explained = _explained(sxx, [sxx[i][j] for i in range(len(sxx))], others)
    if explained is None:
        return None
    one_minus = 1 - explained / sxx[j][j]
    return None if one_minus <= 0 else 1.0 / one_minus


# Per-block sufficient statistics: a flat vector, layout (p predictors):
#   [n, sx_0..sx_{p-1}, sy, sxx_ij for i<=j (row-major), sxy_0..sxy_{p-1}, syy]
# where every sum is over centred values (x - stratum mean, y - stratum mean).


def _pairs(p: int) -> list[tuple[int, int]]:
    return [(i, j) for i in range(p) for j in range(i, p)]


@dataclass
class _Stratum:
    """One set of rows centred at its own means, split into bootstrap blocks."""

    rows: Rows
    n: int
    blocks: list[list[float]]


def _build_stratum(rows: Rows, names: tuple[str, ...], block_s: float) -> _Stratum:
    n = len(rows)
    p = len(names)
    cols = [rows.columns[name] for name in names]
    means = [math.fsum(c) / n for c in cols]
    my = math.fsum(rows.voltage) / n
    block_ns = round(block_s * NS_PER_S)
    groups: dict[tuple[int, int], list[int]] = {}
    for r in range(n):
        key = (rows.window_index[r], (rows.t[r] - rows.window_start[r]) // block_ns)
        groups.setdefault(key, []).append(r)
    pairs = _pairs(p)
    blocks: list[list[float]] = []
    for key in sorted(groups):
        idx = groups[key]
        xc = [[cols[i][r] - means[i] for r in idx] for i in range(p)]
        yc = [rows.voltage[r] - my for r in idx]
        vec = [float(len(idx))]
        vec += [math.fsum(xc[i]) for i in range(p)]
        vec.append(math.fsum(yc))
        vec += [math.fsum(a * b for a, b in zip(xc[i], xc[j], strict=True)) for i, j in pairs]
        vec += [math.fsum(a * b for a, b in zip(xc[i], yc, strict=True)) for i in range(p)]
        vec.append(math.fsum(v * v for v in yc))
        blocks.append(vec)
    return _Stratum(rows=rows, n=n, blocks=blocks)


def _total(vectors: list[list[float]]) -> list[float]:
    return [math.fsum(v[c] for v in vectors) for c in range(len(vectors[0]))]


def _centred(total: list[float], p: int) -> tuple[float, list[list[float]], list[float], float]:
    """`(N, Sxx, Sxy, Syy)` of one stratum from its summed block vectors (re-centred)."""
    n = total[0]
    sx = total[1 : 1 + p]
    sy = total[1 + p]
    sxx = [[0.0] * p for _ in range(p)]
    for k, (i, j) in enumerate(_pairs(p)):
        value = total[2 + p + k] - sx[i] * sx[j] / n
        sxx[i][j] = value
        sxx[j][i] = value
    base = 2 + p + p * (p + 1) // 2
    sxy = [total[base + i] - sx[i] * sy / n for i in range(p)]
    syy = total[base + p] - sy * sy / n
    return n, sxx, sxy, syy


def _pooled(
    totals: list[list[float]], p: int
) -> tuple[float, list[list[float]], list[float], float]:
    """Sum of the per-stratum centred statistics (one intercept per stratum)."""
    parts = [_centred(t, p) for t in totals]
    sxx = [[math.fsum(part[1][i][j] for part in parts) for j in range(p)] for i in range(p)]
    sxy = [math.fsum(part[2][i] for part in parts) for i in range(p)]
    syy = math.fsum(part[3] for part in parts)
    return sum(part[0] for part in parts), sxx, sxy, syy


@dataclass
class _Fit:
    beta: list[float]
    sxx: list[list[float]]
    sxy: list[float]
    syy: float
    r2: float


def _fit_strata(strata: list[_Stratum], p: int) -> _Fit | None:
    """OLS over the strata (one intercept each); None when singular or the response is flat."""
    _, sxx, sxy, syy = _pooled([_total(s.blocks) for s in strata], p)
    if syy <= 0:
        return None
    beta = _solve(sxx, sxy)
    if beta is None:
        return None
    explained = math.fsum(b * s for b, s in zip(beta, sxy, strict=True))
    return _Fit(beta=beta, sxx=sxx, sxy=sxy, syy=syy, r2=explained / syy)


# ---------------------------------------------------------------------------- lag search


def lag_search(
    times: list[int],
    values: list[float],
    term: Series,
    policy: dict = POLICY,
) -> tuple[int | None, float | None, float | None]:
    """Strongest shift of `term` against `values` (decision 11).

    `values[i]` is at instant `times[i]` (ns). For each shift `k` = 0 ... `lag_max_s` seconds the
    pairs are `(values[i], term at times[i] - k s)` where that exact instant exists; a shift with
    fewer than `min_instants` pairs, or a flat side, is skipped. Returns `(best_lag_s,
    corr_at_best_lag, corr_at_zero)`: the best is the highest |Pearson| (the signed value is
    returned), ties to the smaller shift; each is None when no shift qualifies.
    """
    lookup = dict(term)
    min_n = policy["min_instants"]
    best_k: int | None = None
    best_r: float | None = None
    corr_zero: float | None = None
    for k in range(int(policy["lag_max_s"]) + 1):
        shift = k * NS_PER_S
        ys: list[float] = []
        xs: list[float] = []
        for t, v in zip(times, values, strict=True):
            x = lookup.get(t - shift)
            if x is not None:
                xs.append(x)
                ys.append(v)
        if len(xs) < min_n:
            continue
        r = pearson(ys, xs)
        if r is None:
            continue
        if k == 0:
            corr_zero = r
        if best_r is None or abs(r) > abs(best_r):
            best_k, best_r = k, r
    return best_k, best_r, corr_zero


# ---------------------------------------------------------------------------- the voltage model


def _coef_unit(name: str) -> str:
    return f"V per {PREDICTOR_UNITS[name]}"


def _not_testable(model: str, window: str, scope: str, instants: int) -> dict:
    names = MODELS[model]
    terms = [
        {
            "name": name,
            "unit": _coef_unit(name),
            "coefficient": None,
            "interval_low": None,
            "interval_high": None,
            "r2_drop": None,
            "vif": None,
            "plain_corr": None,
            "best_lag_s": None,
            "corr_at_best_lag": None,
            "corr_at_zero": None,
        }
        for name in names
    ]
    return {
        "model": model,
        "window": window,
        "scope": scope,
        "testable": False,
        "instants": instants,
        "r2": None,
        "resamples_used": 0,
        "resamples_singular": 0,
        "terms": terms,
        "joint": {"terms": [names[2], names[3]], "r2_drop": None, "separable": None},
    }


def _bootstrap(
    strata: list[_Stratum], p: int, policy: dict, seed_key: str
) -> tuple[list[list[float]], int]:
    """Block bootstrap of the coefficients (decision 10): `(values per term, singular count)`."""
    rng = random.Random(seed_key)
    coefs: list[list[float]] = [[] for _ in range(p)]
    singular = 0
    for _ in range(int(policy["bootstrap_resamples"])):
        totals = []
        for s in strata:
            count = len(s.blocks)
            totals.append(_total([s.blocks[rng.randrange(count)] for _ in range(count)]))
        _, sxx, sxy, _ = _pooled(totals, p)
        beta = _solve(sxx, sxy)
        if beta is None:
            singular += 1
            continue
        for i, b in enumerate(beta):
            coefs[i].append(b)
    return coefs, singular


def _model_entry(
    strata: list[_Stratum],
    model: str,
    window: str,
    scope: str,
    policy: dict,
    lag_per_term: dict[int, tuple[int | None, float | None, float | None]],
) -> dict:
    """The `voltage_models` entry for strata already known to be estimable."""
    names = MODELS[model]
    p = len(names)
    fit = _fit_strata(strata, p)
    assert fit is not None
    seed_key = f"{policy['bootstrap_seed']}|{model}|{window}|{scope}"
    coefs, singular = _bootstrap(strata, p, policy, seed_key)

    all_y: list[float] = []
    all_x: list[list[float]] = [[] for _ in range(p)]
    for s in strata:
        all_y += s.rows.voltage
        for i, name in enumerate(names):
            all_x[i] += s.rows.columns[name]

    def r2_without(drop: list[int]) -> float | None:
        explained = _explained(fit.sxx, fit.sxy, [i for i in range(p) if i not in drop])
        return None if explained is None else explained / fit.syy

    terms = []
    for i, name in enumerate(names):
        interval = _interval(coefs[i], policy["interval_level"])
        sub = r2_without([i])
        lag = lag_per_term.get(i, (None, None, None))
        terms.append(
            {
                "name": name,
                "unit": _coef_unit(name),
                "coefficient": fit.beta[i],
                "interval_low": None if interval is None else interval[0],
                "interval_high": None if interval is None else interval[1],
                "r2_drop": None if sub is None else fit.r2 - sub,
                "vif": _vif(fit.sxx, i),
                "plain_corr": pearson(all_y, all_x[i]),
                "best_lag_s": lag[0],
                "corr_at_best_lag": lag[1],
                "corr_at_zero": lag[2],
            }
        )
    joint_sub = r2_without([2, 3])
    vif_x1, vif_x2 = terms[2]["vif"], terms[3]["vif"]
    limit = policy["vif_limit"]
    return {
        "model": model,
        "window": window,
        "scope": scope,
        "testable": True,
        "instants": sum(s.n for s in strata),
        "r2": fit.r2,
        "resamples_used": len(coefs[0]),
        "resamples_singular": singular,
        "terms": terms,
        "joint": {
            "terms": [names[2], names[3]],
            "r2_drop": None if joint_sub is None else fit.r2 - joint_sub,
            "separable": (
                vif_x1 is not None and vif_x2 is not None and vif_x1 < limit and vif_x2 < limit
            ),
        },
    }


def _estimable(rows: Rows, model: str, policy: dict) -> _Stratum | None:
    """The stratum of `rows` when it is testable (enough rows, non-singular, varying voltage)."""
    if len(rows) < policy["min_instants"]:
        return None
    names = MODELS[model]
    stratum = _build_stratum(rows, names, policy["bootstrap_block_s"])
    return stratum if _fit_strata([stratum], len(names)) is not None else None


def analyse_model(
    rows: Rows,
    model: str,
    window: str,
    scope: str,
    lag_series: dict[str, Series],
    policy: dict = POLICY,
) -> dict:
    """One `voltage_models` entry for one experiment (decisions 8, 10, 11).

    `lag_series` maps the X1 and X2 predictor names to their full accepted series (the lag
    search reads the term at `t - k s`, which may lie outside the rows).

    Keys: `model`, `window`, `scope`, `testable`, `instants`, `r2`, `resamples_used`,
    `resamples_singular`, `terms` (4 dicts in predictor order with `name`, `unit`, `coefficient`,
    `interval_low`, `interval_high`, `r2_drop`, `vif`, `plain_corr`, `best_lag_s`,
    `corr_at_best_lag`, `corr_at_zero`) and `joint` (`terms`, `r2_drop`, `separable`). A fit with
    fewer than `min_instants` rows or a singular normal matrix is not testable: every number
    is None and no bootstrap is run. The lag fields of the current and temperature terms are
    always None.
    """
    stratum = _estimable(rows, model, policy)
    if stratum is None:
        return _not_testable(model, window, scope, len(rows))
    names = MODELS[model]
    p = len(names)
    fit = _fit_strata([stratum], p)
    assert fit is not None

    n = len(rows)
    means = [math.fsum(rows.columns[name]) / n for name in names]
    y_mean = math.fsum(rows.voltage) / n
    lag_per_term: dict[int, tuple[int | None, float | None, float | None]] = {}
    for j in (2, 3):
        term_series = lag_series.get(names[j])
        if term_series is None:
            continue
        others = [i for i in range(p) if i != j]
        beta = _solve(
            [[fit.sxx[a][b] for b in others] for a in others], [fit.sxy[a] for a in others]
        )
        if beta is None:
            continue
        residual = [
            rows.voltage[r]
            - y_mean
            - math.fsum(
                b * (rows.columns[names[i]][r] - means[i])
                for b, i in zip(beta, others, strict=True)
            )
            for r in range(n)
        ]
        lag_per_term[j] = lag_search(rows.t, residual, term_series, policy)
    return _model_entry([stratum], model, window, scope, policy, lag_per_term)


def analyse_pooled(
    rows_by_experiment: dict[str, Rows],
    model: str,
    window: str,
    policy: dict = POLICY,
) -> dict:
    """The `pooled` `voltage_models` entry (decisions 8, 9, 10).

    Pools the testable experiments of the model and window (enough rows and a non-singular own
    fit) with one intercept per experiment instead of a common one; the bootstrap is stratified
    (each experiment, in id order, draws its own blocks; one rng). `instants` is the sum over
    the pooled experiments; `r2` and the drops are within-experiment. `plain_corr` is the Pearson
    correlation over all pooled rows. The lag fields are None. Keys as `analyse_model`. With no
    testable experiment the entry is not testable with `instants` 0.
    """
    names = MODELS[model]
    strata = []
    for experiment_id in sorted(rows_by_experiment):
        stratum = _estimable(rows_by_experiment[experiment_id], model, policy)
        if stratum is not None:
            strata.append(stratum)
    if not strata:
        return _not_testable(model, window, "pooled", 0)
    if _fit_strata(strata, len(names)) is None:
        return _not_testable(model, window, "pooled", sum(s.n for s in strata))
    return _model_entry(strata, model, window, "pooled", policy, {})


# ---------------------------------------------------------------------------- evidence rule


def evidence(entries: list[dict], pooled: dict) -> list[dict]:
    """`voltage_evidence` entries (X1 then X2) for one model and window (decision 12).

    `entries` are the per-experiment `voltage_models` dicts of that model and window; `pooled` is
    the pooled one (reported beside the status, not used by it). Each entry has `model`,
    `window`, `term`, `status`, `sign`, `experiments_testable`, `experiments_excluding_zero`,
    `pooled_coefficient`, `pooled_interval_low`, `pooled_interval_high`.

    An interval excludes zero when `low > 0` or `high < 0`. Status: `supported` (at least 2
    testable fits, all exclude zero, all one sign), `single_run` (exactly 1 testable and it
    excludes zero), `inconsistent` (two testable fits exclude zero with opposite signs),
    `not_resolved` (any other case with a testable fit), `not_testable` (none). `sign` is set
    for `supported` and `single_run` only.
    """
    model, window = pooled["model"], pooled["window"]
    out = []
    for term_name in MODELS[model][2:]:
        intervals = []
        for entry in entries:
            if not entry["testable"]:
                continue
            term = next(t for t in entry["terms"] if t["name"] == term_name)
            intervals.append((term["interval_low"], term["interval_high"]))
        excluding = [iv for iv in intervals if _excludes_zero(*iv)]
        signs = {"positive" if low > 0 else "negative" for low, _ in excluding}
        sign: str | None = None
        if not intervals:
            status = "not_testable"
        elif len(intervals) >= 2 and len(excluding) == len(intervals) and len(signs) == 1:
            status, sign = "supported", next(iter(signs))
        elif len(intervals) == 1 and excluding:
            status, sign = "single_run", next(iter(signs))
        elif len(signs) == 2:
            status = "inconsistent"
        else:
            status = "not_resolved"
        pooled_term = next(t for t in pooled["terms"] if t["name"] == term_name)
        out.append(
            {
                "model": model,
                "window": window,
                "term": term_name,
                "status": status,
                "sign": sign,
                "experiments_testable": len(intervals),
                "experiments_excluding_zero": len(excluding),
                "pooled_coefficient": pooled_term["coefficient"],
                "pooled_interval_low": pooled_term["interval_low"],
                "pooled_interval_high": pooled_term["interval_high"],
            }
        )
    return out


# ---------------------------------------------------------------------------- conditions


def _in_windows_values(series: Series, windows: Windows) -> list[float]:
    ordered = sorted(windows)
    starts = [w[0] for w in ordered]
    return [v for t, v in series if _window_of(starts, ordered, t) is not None]


def measured_conditions(series: dict[str, Series], windows: Windows, policy: dict = POLICY) -> dict:
    """The `conditions` object, measured from accepted readings inside the windows (decision 14).

    Keys: `current_setpoint_a` (median of `current_setpoint`), `current_setpoint_profile`
    (`varying` when p95 - p05 of the setpoint exceeds `condition_tol_rel` x |median|, else
    `constant`), `air_flow_m3h`, `solvent_flow_lmin`, `ambient_temperature_c`,
    `relative_humidity_pct` (medians of `air_flow`, `solvent_flow`, `ambient_temperature`,
    `relative_humidity`). Each is None when there is no reading in the windows.
    """
    setpoint = _in_windows_values(series.get("current_setpoint", []), windows)
    setpoint_median = median(setpoint)
    profile: str | None = None
    if setpoint:
        ordered = sorted(setpoint)
        spread = percentile(ordered, 0.95) - percentile(ordered, 0.05)
        varying = spread > policy["condition_tol_rel"] * abs(setpoint_median)
        profile = "varying" if varying else "constant"

    def med(name: str) -> float | None:
        return median(_in_windows_values(series.get(name, []), windows))

    return {
        "current_setpoint_a": setpoint_median,
        "current_setpoint_profile": profile,
        "air_flow_m3h": med("air_flow"),
        "solvent_flow_lmin": med("solvent_flow"),
        "ambient_temperature_c": med("ambient_temperature"),
        "relative_humidity_pct": med("relative_humidity"),
    }


# (factor, key in the conditions object, kind) in factor order; the batch comes last.
_FACTOR_SOURCES = (
    ("current_setpoint", "current_setpoint_a", "relative"),
    ("current_setpoint_profile", "current_setpoint_profile", "equal"),
    ("air_flow", "air_flow_m3h", "relative"),
    ("solvent_flow", "solvent_flow_lmin", "relative"),
    ("ambient_temperature", "ambient_temperature_c", "ambient"),
    ("relative_humidity", "relative_humidity_pct", "humidity"),
)


def _differs(a, b, kind: str, policy: dict) -> bool | None:
    if a is None or b is None:
        return None
    if kind == "equal":
        return a != b
    gap = abs(a - b)
    if kind == "relative":
        return gap > policy["condition_tol_rel"] * max(abs(a), abs(b))
    if kind == "ambient":
        return gap > policy["ambient_tol_c"]
    return gap > policy["humidity_tol_pct"]


def compare_factors(
    meta_a: dict, cond_a: dict, meta_b: dict, cond_b: dict, policy: dict = POLICY
) -> list[dict]:
    """The seven factors of one pair, in `FACTORS` order (decision 14).

    Each is `{factor, a, b, differs}`. Relative factors differ when `|a - b| > condition_tol_rel
    x max(|a|, |b|)`; ambient temperature when `|a - b| > ambient_tol_c`; humidity when
    `|a - b| > humidity_tol_pct`; profile and batch when not equal. A missing value makes
    `differs` None. `meta_*` need `sorbent_batch`; `cond_*` are `measured_conditions` objects.
    """
    out = []
    for factor, key, kind in _FACTOR_SOURCES:
        a, b = cond_a.get(key), cond_b.get(key)
        out.append({"factor": factor, "a": a, "b": b, "differs": _differs(a, b, kind, policy)})
    a, b = meta_a.get("sorbent_batch"), meta_b.get("sorbent_batch")
    out.append(
        {"factor": "sorbent_batch", "a": a, "b": b, "differs": _differs(a, b, "equal", policy)}
    )
    return out


def conditions_status(factors: list[dict]) -> tuple[str, list[str]]:
    """`(status, differing factor names)` (decision 14).

    A factor counts as differing when `differs` is True or None (unknown). 0 differing is
    `same_conditions`, exactly 1 is `supported`, 2 or more is `confounded`.
    """
    differing = [f["factor"] for f in factors if f["differs"] is not False]
    if not differing:
        return "same_conditions", differing
    return ("supported" if len(differing) == 1 else "confounded"), differing


def recorded_differences(meta_a: dict, meta_b: dict) -> list[dict]:
    """`[{field: "operator", a, b}]` when the recorded operators differ, else `[]`.

    The operator is not a factor (setpoints are automated); it is only listed.
    """
    a, b = meta_a.get("operator"), meta_b.get("operator")
    return [{"field": "operator", "a": a, "b": b}] if a != b else []


# ---------------------------------------------------------------------------- steady KPIs


@dataclass
class KpiResult:
    """The result of `steady_kpis`.

    `entries`: `{kpi name: {value, unit, coverage, status, interval_low, interval_high}}` for the
    five names of `KPI_UNITS`, in that order. `samples`: kpi name -> the resample values (one per
    bootstrap resample), or an empty list when the value is None.
    """

    entries: dict[str, dict]
    samples: dict[str, list[float]]


def _cover(series: Series, max_spacing_s: float, windows: Windows) -> list[tuple[int, int]]:
    """Covered intervals of `series` (spacing rule of `pipeline.metrics`) inside the windows."""
    return overlap(covered_intervals(series, max_spacing_s), windows)


def _seconds(intervals: list[tuple[int, int]]) -> float:
    return sum(end - start for start, end in intervals) / NS_PER_S


def _layout(windows: Windows, block_s: float) -> list[tuple[int, int]]:
    """The bootstrap blocks over the windows: `[ws + k b, ws + (k + 1) b)` clipped to the window."""
    block_ns = round(block_s * NS_PER_S)
    out = []
    for ws, we in windows:
        start = ws
        while start < we:
            out.append((start, min(start + block_ns, we)))
            start += block_ns
    return out


def _resample_kpi(
    parts: list[tuple[float, float]], scale: float, policy: dict, seed_key: str
) -> list[float]:
    """Resample values of a ratio of sums: `scale x sum(num) / sum(den)` over drawn blocks.

    `parts` are `(num, den)` of the non-empty blocks; B draws of `rng.randrange(B)` per resample.
    Returns `[]` when a resample has a non-positive denominator (the ratio is undefined).
    """
    rng = random.Random(seed_key)
    count = len(parts)
    out: list[float] = []
    for _ in range(int(policy["bootstrap_resamples"])):
        drawn = [parts[rng.randrange(count)] for _ in range(count)]
        den = math.fsum(d for _, d in drawn)
        if den <= 0:
            return []
        out.append(scale * math.fsum(n for n, _ in drawn) / den)
    return out


def steady_kpis(
    series: dict[str, Series],
    windows: Windows,
    experiment_id: str,
    policy: dict = POLICY,
) -> KpiResult:
    """The five steady-state KPIs of one experiment over its steady windows (decision 13).

    Needs `voltage`, `power_computed`, `capture_rate`, `capture_efficiency` in `series`.
    `voltage_mean_v` and `capture_efficiency_mean` are plain means of the instants in the
    windows; `mean_power_kw` and `capture_rate_mean_kg_h` are trapezoid integrals over the
    covered intervals inside the windows divided by the covered seconds (kW: also by 1000);
    `sec_kwh_per_kg` is the energy over the overlap of power-covered and capture-covered time
    divided by the CO2 captured over it. Spacing limits come from `pipeline.metrics.POLICY`
    (2 s for voltage and power, 4 s for capture and efficiency). Coverage is covered seconds
    divided by the steady seconds (0.0 when there are none); status is
    `pipeline.metrics.status_for`. The interval is the block bootstrap of decision 10 on the
    steady windows: each block contributes its partial sums and a resample is the ratio of the
    summed parts (seed key `"<seed>|kpi|<kpi>|<experiment_id>"`); blocks with nothing to
    contribute are left out of the draw.
    """
    wins = sorted(windows)
    starts = [w[0] for w in wins]
    steady_s = _seconds(wins)
    layout = _layout(wins, policy["bootstrap_block_s"])
    power = series.get("power_computed", [])
    rate = series.get("capture_rate", [])
    spacing_p = METRICS_POLICY["power_max_spacing_s"]
    spacing_c = METRICS_POLICY["capture_max_spacing_s"]
    per_kwh = SECONDS_PER_HOUR / WS_PER_KWH

    def instants_kpi(s: Series, spacing: float):
        pts = [(t, v) for t, v in s if _window_of(starts, wins, t) is not None]
        parts: list[tuple[float, float]] = []
        for b0, b1 in layout:
            vals = [v for t, v in pts if b0 <= t < b1]
            if vals:
                parts.append((math.fsum(vals), float(len(vals))))
        value = math.fsum(v for _, v in pts) / len(pts) if pts else None
        return value, _seconds(_cover(s, spacing, wins)), parts, 1.0

    def integral_kpi(s: Series, spacing: float, scale: float):
        cover = _cover(s, spacing, wins)
        secs = _seconds(cover)
        parts = []
        for block in layout:
            clip = overlap(cover, [block])
            clip_s = _seconds(clip)
            if clip_s > 0:
                parts.append((integrate_over(s, clip), clip_s))
        value = integrate_over(s, cover) / secs * scale if secs > 0 else None
        return value, secs, parts, scale

    def sec_kpi():
        cover = overlap(_cover(power, spacing_p, wins), _cover(rate, spacing_c, wins))
        secs = _seconds(cover)
        parts = []
        for block in layout:
            clip = overlap(cover, [block])
            if _seconds(clip) > 0:
                parts.append((integrate_over(power, clip), integrate_over(rate, clip)))
        value = None
        if secs > 0:
            captured = integrate_over(rate, cover)
            if captured > 0:
                value = integrate_over(power, cover) / captured * per_kwh
        return value, secs, parts, per_kwh

    raw = {
        "voltage_mean_v": instants_kpi(series.get("voltage", []), spacing_p),
        "mean_power_kw": integral_kpi(power, spacing_p, 1 / 1000),
        "capture_rate_mean_kg_h": integral_kpi(rate, spacing_c, 1.0),
        "capture_efficiency_mean": instants_kpi(series.get("capture_efficiency", []), spacing_c),
        "sec_kwh_per_kg": sec_kpi(),
    }
    entries: dict[str, dict] = {}
    samples: dict[str, list[float]] = {}
    for name, (value, covered_s, parts, scale) in raw.items():
        coverage = covered_s / steady_s if steady_s > 0 else 0.0
        resampled: list[float] = []
        if value is not None and parts:
            seed_key = f"{policy['bootstrap_seed']}|kpi|{name}|{experiment_id}"
            resampled = _resample_kpi(parts, scale, policy, seed_key)
        interval = _interval(resampled, policy["interval_level"])
        entries[name] = {
            "value": value,
            "unit": KPI_UNITS[name],
            "coverage": coverage,
            "status": status_for(value, coverage),
            "interval_low": None if interval is None else interval[0],
            "interval_high": None if interval is None else interval[1],
        }
        samples[name] = resampled
    return KpiResult(entries=entries, samples=samples)


def kpi_differences(a: KpiResult, b: KpiResult, policy: dict = POLICY) -> list[dict]:
    """Per-KPI comparison of two experiments, in `KPI_UNITS` order (decision 14).

    Each is `{name, unit, difference, interval_low, interval_high, excludes_zero,
    coverage_status}`. `difference` is `b - a`; the interval is the type 7 quantiles of the
    element-wise differences of the two resample arrays; `excludes_zero` is None without an
    interval. `coverage_status`: `both_complete`, `partial_coverage` (both have a value, one or
    both partial) or `not_available` (either value None: difference and interval are None).
    """
    out = []
    for name, unit in KPI_UNITS.items():
        ea, eb = a.entries[name], b.entries[name]
        difference = interval = None
        if ea["value"] is None or eb["value"] is None:
            coverage_status = "not_available"
        else:
            difference = eb["value"] - ea["value"]
            both = ea["status"] == "complete" and eb["status"] == "complete"
            coverage_status = "both_complete" if both else "partial_coverage"
            sa, sb = a.samples[name], b.samples[name]
            if sa and len(sa) == len(sb):
                diffs = [y - x for x, y in zip(sa, sb, strict=True)]
                interval = _interval(diffs, policy["interval_level"])
        out.append(
            {
                "name": name,
                "unit": unit,
                "difference": difference,
                "interval_low": None if interval is None else interval[0],
                "interval_high": None if interval is None else interval[1],
                "excludes_zero": None if interval is None else _excludes_zero(*interval),
                "coverage_status": coverage_status,
            }
        )
    return out


# ---------------------------------------------------------------------------- pressure drop


def pressure_drop_fit(
    air_flow: Series, pressure_drop: Series, windows: Windows, policy: dict = POLICY
) -> dict:
    """The per-experiment pressure-drop check (decision 16), without the experiment id.

    Over the pressure-drop instants inside the windows that have an air flow at the same
    instant: the lines `pressure_drop ~ air_flow` and `~ air_flow^2`, and the lag search of
    decision 11 on air flow (the pressure drop against air flow at `t - k s`).
    Keys: `instants`, `slope_air_flow`, `intercept_air_flow`, `r2_air_flow`,
    `slope_air_flow_sq`, `intercept_air_flow_sq`, `r2_air_flow_sq`, `best_lag_s`,
    `corr_at_best_lag`, `corr_at_zero`; a fit that cannot be made (fewer than 2 instants, flat
    air flow) is None.
    """
    ordered = sorted(windows)
    starts = [w[0] for w in ordered]
    flow_at = dict(air_flow)
    times: list[int] = []
    xs: list[float] = []
    ys: list[float] = []
    for t, drop in pressure_drop:
        if _window_of(starts, ordered, t) is None or t not in flow_at:
            continue
        times.append(t)
        xs.append(flow_at[t])
        ys.append(drop)
    lin = simple_fit(xs, ys)
    sq = simple_fit([x * x for x in xs], ys)
    best_lag, best_corr, corr_zero = lag_search(times, ys, air_flow, policy)
    return {
        "instants": len(times),
        "slope_air_flow": None if lin is None else lin[0],
        "intercept_air_flow": None if lin is None else lin[1],
        "r2_air_flow": None if lin is None else lin[2],
        "slope_air_flow_sq": None if sq is None else sq[0],
        "intercept_air_flow_sq": None if sq is None else sq[1],
        "r2_air_flow_sq": None if sq is None else sq[2],
        "best_lag_s": best_lag,
        "corr_at_best_lag": best_corr,
        "corr_at_zero": corr_zero,
    }


def across_line(points: list[tuple[float, float]]) -> dict:
    """The line through `(air_flow_median, pressure_drop_median)` points: `{slope, intercept, r2}`.

    Points with a missing coordinate are left out. Each key is None when fewer than 2 points
    remain or the x values are all equal; `r2` is None when the y values are all equal.
    """
    usable = [(x, y) for x, y in points if x is not None and y is not None]
    fit = simple_fit([x for x, _ in usable], [y for _, y in usable])
    if fit is None:
        return {"slope": None, "intercept": None, "r2": None}
    return {"slope": fit[0], "intercept": fit[1], "r2": fit[2]}


# ---------------------------------------------------------------------------- air-flow check


def split_check(series: Series, boundary_ns: int) -> dict:
    """Points and medians before and after a boundary (decision 17).

    Before is `t < boundary_ns`, after is `t >= boundary_ns`; points whose value is None are not
    counted. Keys: `before_points`, `before_median`, `after_points`, `after_median`,
    `relative_change` (`(after - before) / before`; None when a side is empty or the before
    median is 0).
    """
    before = [v for t, v in series if t < boundary_ns and v is not None]
    after = [v for t, v in series if t >= boundary_ns and v is not None]
    before_median = median(before)
    after_median = median(after)
    change = None
    if before_median is not None and after_median is not None and before_median != 0:
        change = (after_median - before_median) / before_median
    return {
        "before_points": len(before),
        "before_median": before_median,
        "after_points": len(after),
        "after_median": after_median,
        "relative_change": change,
    }
