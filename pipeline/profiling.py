"""Post-ingest profile: turning query rows into the profile document (M2.5, ADR-0014).

Everything here is pure: no InfluxDB, no files. `pipeline/profiling_sql.py` asks the database and
hands rows to the `shape_*` functions; `scripts/post_ingest_profile.py` runs it and writes the
two output files. The shape of the JSON is pinned by `contracts/post_ingest_profile.schema.json`.

The profile measures. It never judges: no verdict words, no thresholds that label a reading
(MISTAKES.md C-01, C-02). A reading outside the documented range is counted; it is not called
anything. The step-to-step change is named `differences` for the same reason.

Conventions (ADR-0014):

- Floats are rounded to 9 significant digits and every list is sorted, so a re-run on the same
  data gives the same bytes. Only the `timing` block differs.
- Durations are seconds; instants are UTC `...Z` strings. The database gives nanosecond integers
  and they are converted here, once.
- `stddev` is the sample standard deviation (n - 1); it is null for a single value.
- Percentiles are exact and linearly interpolated (`PERCENTILE_CONT`), not approximate.
- Runs and step-to-step change look only at points that hold a value. A point with no value
  neither breaks a run nor starts one; it is counted in `points_without_value`.
- `instants_unmatched` is the number of points of the first-named (dependent) signal of a
  relationship that found no partner at the exact same instant.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from pipeline.signals import DOCUMENTED_RANGE, NOMINAL_INTERVAL_S, NUMERIC_TABLE

NS = 1_000_000_000
MAX_LAG_S = 60
LONGEST = 5
QUALITY_FLAGS = ("GOOD", "UNCERTAIN", "BAD")

RELATIONSHIP_KINDS = (
    "power_vs_voltage_x_current",
    "co2_out_vs_co2_in",
    "current_vs_current_setpoint",
    "pressure_drop_vs_air_flow",
)

PROBE_MESSAGE_FILE = "post_ingest_profile_span_probe.txt"


# ---------------------------------------------------------------------------- numbers


def sig9(value: Any) -> Any:
    """Round a float to 9 significant digits. `None`, NaN and infinities become `None`."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return float(f"{number:.9g}")


def seconds_from_ns(value: Any) -> Any:
    """Nanoseconds (int or float, as the database returns them) to rounded seconds."""
    if value is None:
        return None
    return sig9(float(value) / NS)


def instant_text(ns: int) -> str:
    """UTC instant for a nanosecond epoch, e.g. `2026-05-04T08:00:49Z`; keeps up to 6 decimals."""
    whole, rest = divmod(int(ns), NS)
    stamp = datetime.fromtimestamp(whole, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")
    micro = rest // 1000
    if micro:
        return f"{stamp}.{micro:06d}".rstrip("0") + "Z"
    return stamp + "Z"


def datetime_text(moment: datetime) -> str:
    """UTC instant text for a timezone-aware datetime."""
    utc = moment.astimezone(UTC)
    whole = int(utc.replace(microsecond=0).timestamp())
    return instant_text(whole * NS + utc.microsecond * 1000)


def count(value: Any) -> int:
    return int(value) if value is not None else 0


def maybe_count(value: Any) -> int | None:
    return int(value) if value is not None else None


# ---------------------------------------------------------------------------- lag search


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation, or `None` with fewer than 2 pairs or no spread in either series."""
    n = len(xs)
    if n < 2:
        return None
    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n
    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    syy = math.fsum((y - mean_y) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def best_lag(
    current: Mapping[int, float], setpoint: Mapping[int, float], max_lag_s: int = MAX_LAG_S
) -> tuple[int | None, float | None]:
    """Shift the setpoint later by 0..`max_lag_s` whole seconds; return the shift where it
    correlates best with the current, and that correlation.

    Both mappings are `{instant in ns: value}`. At shift `k` a current reading at `t` is paired
    with the setpoint reading at exactly `t - k` seconds. The correlation is rounded to 9
    significant digits before comparing, so a tie is a tie in the output too; ties go to the
    smaller shift. `(None, None)` when no shift has two pairs with spread in both series.
    """
    best_k: int | None = None
    best_corr: float | None = None
    items = sorted(current.items())
    for lag in range(max_lag_s + 1):
        shift = lag * NS
        xs: list[float] = []
        ys: list[float] = []
        for instant, value in items:
            partner = setpoint.get(instant - shift)
            if partner is not None:
                xs.append(value)
                ys.append(partner)
        corr = sig9(pearson(xs, ys))
        if corr is not None and (best_corr is None or corr > best_corr):
            best_k, best_corr = lag, corr
    return best_k, best_corr


def fit_line(xs: list[float], ys: list[float]) -> dict[str, float | None]:
    """Least-squares line of `ys` on `xs`: `corr`, `slope`, `intercept`, `r2`.

    Two-pass with exactly rounded sums (`math.fsum`), so the same pairs always give the same bits.
    Fewer than 2 pairs, or no spread in `xs`, gives `None` for the line; no spread in `ys` gives
    `None` for the correlation.
    """
    n = len(xs)
    out: dict[str, float | None] = {"corr": None, "slope": None, "intercept": None, "r2": None}
    if n < 2:
        return out
    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n
    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    syy = math.fsum((y - mean_y) ** 2 for y in ys)
    sxy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    if sxx > 0:
        out["slope"] = sxy / sxx
        out["intercept"] = mean_y - out["slope"] * mean_x
    if sxx > 0 and syy > 0:
        out["corr"] = max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))
        out["r2"] = out["corr"] ** 2
    return out


def _common(*series: Mapping[int, float]) -> list[int]:
    instants = set(series[0])
    for other in series[1:]:
        instants &= set(other)
    return sorted(instants)


def relationship_fits(
    kind: str, pulled: Mapping[str, Mapping[int, float]]
) -> dict[str, float | int | None]:
    """The Python part of one relationship, from `{signal: {instant ns: value}}` pulls.

    Pairs are formed on the exact same instant (M2.5 decision 5), as in the SQL.
    """
    if kind == "power_vs_voltage_x_current":
        power, voltage, current = pulled["power"], pulled["voltage"], pulled["current"]
        instants = _common(power, voltage, current)
        return fit_line([voltage[t] * current[t] for t in instants], [power[t] for t in instants])
    if kind == "co2_out_vs_co2_in":
        out, inlet = pulled["co2_out_ppm"], pulled["co2_in_ppm"]
        instants = _common(out, inlet)
        return {"corr": fit_line([inlet[t] for t in instants], [out[t] for t in instants])["corr"]}
    if kind == "current_vs_current_setpoint":
        current, setpoint = pulled["current"], pulled["current_setpoint"]
        instants = _common(current, setpoint)
        corr = fit_line([setpoint[t] for t in instants], [current[t] for t in instants])["corr"]
        lag, lag_corr = best_lag(current, setpoint)
        return {"corr": corr, "best_lag_s": lag, "corr_at_best_lag": lag_corr}
    if kind == "pressure_drop_vs_air_flow":
        drop, flow = pulled["pressure_drop"], pulled["air_flow"]
        instants = _common(drop, flow)
        ys = [drop[t] for t in instants]
        linear = fit_line([flow[t] for t in instants], ys)
        squared = fit_line([flow[t] ** 2 for t in instants], ys)
        return {
            "corr": linear["corr"],
            "slope": linear["slope"],
            "intercept": linear["intercept"],
            "r2": linear["r2"],
            "slope_sq": squared["slope"],
            "intercept_sq": squared["intercept"],
            "r2_sq": squared["r2"],
        }
    raise ValueError(f"unknown relationship kind {kind!r}")


# ---------------------------------------------------------------------------- shaping series


def _index(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {(r["source"], r["signal"]): r for r in rows}


def _grouped(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["source"], row["signal"]), []).append(row)
    return grouped


def shape_intervals(
    pair: tuple[str, str], row: Mapping[str, Any] | None, longest: list[Mapping[str, Any]]
) -> dict[str, Any]:
    nominal = NOMINAL_INTERVAL_S.get(pair)
    row = row or {}
    return {
        "count": count(row.get("n")),
        "min": seconds_from_ns(row.get("dt_min")),
        "median": seconds_from_ns(row.get("dt_median")),
        "p95": seconds_from_ns(row.get("dt_p95")),
        "max": seconds_from_ns(row.get("dt_max")),
        "over_2x_nominal": count(row.get("over2")) if nominal else None,
        "over_10x_nominal": count(row.get("over10")) if nominal else None,
        "seconds_in_over_2x": seconds_from_ns(row.get("secs2") or 0) if nominal else None,
        "longest": [
            {
                "start": instant_text(item["t0"]),
                "end": instant_text(item["t1"]),
                "seconds": seconds_from_ns(item["t1"] - item["t0"]),
            }
            for item in longest[:LONGEST]
        ],
    }


def shape_runs(row: Mapping[str, Any] | None, longest: list[Mapping[str, Any]]) -> dict[str, Any]:
    row = row or {}
    return {
        "count": count(row.get("n")),
        "median_samples": sig9(row.get("median_samples")),
        "max_samples": maybe_count(row.get("max_samples")),
        "max_seconds": seconds_from_ns(row.get("max_ns")),
        "longest": [
            {
                "start": instant_text(item["t0"]),
                "end": instant_text(item["t1"]),
                "samples": int(item["samples"]),
                "seconds": seconds_from_ns(item["t1"] - item["t0"]),
                "value": sig9(item["value"])
                if not isinstance(item["value"], str)
                else item["value"],
            }
            for item in longest[:LONGEST]
        ],
    }


def shape_differences(row: Mapping[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    return {
        "count": count(row.get("n")),
        "mean": sig9(row.get("d_mean")),
        "stddev": sig9(row.get("d_stddev")),
        "median_abs": sig9(row.get("d_median_abs")),
        "p95_abs": sig9(row.get("d_p95_abs")),
        "max_abs": sig9(row.get("d_max_abs")),
    }


def shape_series(
    experiment_id: str,
    table: str,
    basics: Iterable[Mapping[str, Any]],
    state_counts: Iterable[Mapping[str, Any]],
    intervals: Iterable[Mapping[str, Any]],
    intervals_longest: Iterable[Mapping[str, Any]],
    runs: Iterable[Mapping[str, Any]],
    runs_longest: Iterable[Mapping[str, Any]],
    differences: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One `series` entry per `(source, signal)` that has at least one point in `table`."""
    interval_rows = _index(intervals)
    longest_intervals = _grouped(intervals_longest)
    run_rows = _index(runs)
    longest_runs = _grouped(runs_longest)
    difference_rows = _index(differences)
    states: dict[tuple[str, str], dict[str, int]] = {}
    for row in state_counts:
        states.setdefault((row["source"], row["signal"]), {})[str(row["value"])] = int(row["n"])

    out: list[dict[str, Any]] = []
    for base in sorted(basics, key=lambda r: (r["source"], r["signal"])):
        pair = (base["source"], base["signal"])
        numeric = table == NUMERIC_TABLE
        low, high, unit = DOCUMENTED_RANGE.get(pair, (None, None, None))
        values = None
        if numeric:
            values = {
                "min": sig9(base.get("v_min")),
                "max": sig9(base.get("v_max")),
                "mean": sig9(base.get("v_mean")),
                "stddev": sig9(base.get("v_stddev")),
                "median": sig9(base.get("v_median")),
                "p05": sig9(base.get("v_p05")),
                "p95": sig9(base.get("v_p95")),
                "below_documented_min": maybe_count(base.get("below")) if low is not None else None,
                "above_documented_max": maybe_count(base.get("above"))
                if high is not None
                else None,
            }
        out.append(
            {
                "experiment_id": experiment_id,
                "source": pair[0],
                "signal": pair[1],
                "table": table,
                "unit": unit,
                "nominal_interval_s": NOMINAL_INTERVAL_S.get(pair),
                "documented_min": low,
                "documented_max": high,
                "points": count(base["points"]),
                "points_without_value": count(base["points_without_value"]),
                "quality": {
                    "GOOD": count(base.get("q_good")),
                    "UNCERTAIN": count(base.get("q_uncertain")),
                    "BAD": count(base.get("q_bad")),
                },
                "values": values,
                "states": None if numeric else dict(sorted(states.get(pair, {}).items())),
                "intervals_s": shape_intervals(
                    pair, interval_rows.get(pair), longest_intervals.get(pair, [])
                ),
                "runs": shape_runs(run_rows.get(pair), longest_runs.get(pair, [])),
                "differences": shape_differences(difference_rows.get(pair)) if numeric else None,
            }
        )
    return out


# ---------------------------------------------------------------------------- relationships


def _unmatched(dependent_points: int, matched: int) -> int:
    return max(dependent_points - matched, 0)


def shape_relationship(
    kind: str,
    experiment_id: str,
    row: Mapping[str, Any] | None,
    dependent_points: int,
    fits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One relationship entry. `row` holds the SQL measures over the exact-instant join and
    `fits` the Python ones (`relationship_fits`)."""
    row = row or {}
    fits = fits or {}
    matched = count(row.get("matched"))
    entry: dict[str, Any] = {
        "experiment_id": experiment_id,
        "kind": kind,
        "instants_matched": matched,
        "instants_unmatched": _unmatched(dependent_points, matched),
        "corr": sig9(fits.get("corr")),
    }
    if kind == "power_vs_voltage_x_current":
        entry |= {
            "residual_mean": sig9(row.get("r_mean")),
            "residual_stddev": sig9(row.get("r_stddev")),
            "residual_median": sig9(row.get("r_median")),
            "residual_p05": sig9(row.get("r_p05")),
            "residual_p95": sig9(row.get("r_p95")),
            "residual_max_abs": sig9(row.get("r_max_abs")),
            "relative_residual_median": sig9(row.get("rel_median")),
            "relative_residual_p95": sig9(row.get("rel_p95")),
            "power_zero_instants": count(row.get("zero")),
            "slope": sig9(fits.get("slope")),
            "intercept": sig9(fits.get("intercept")),
            "r2": sig9(fits.get("r2")),
        }
    elif kind == "co2_out_vs_co2_in":
        entry |= {
            "ratio_median": sig9(row.get("ratio_median")),
            "ratio_p05": sig9(row.get("ratio_p05")),
            "ratio_p95": sig9(row.get("ratio_p95")),
            "out_at_or_above_in": count(row.get("at_or_above")),
        }
    elif kind == "current_vs_current_setpoint":
        entry |= {
            "difference_mean": sig9(row.get("d_mean")),
            "difference_stddev": sig9(row.get("d_stddev")),
            "difference_median": sig9(row.get("d_median")),
            "difference_max_abs": sig9(row.get("d_max_abs")),
            "best_lag_s": fits.get("best_lag_s"),
            "corr_at_best_lag": sig9(fits.get("corr_at_best_lag")),
        }
    elif kind == "pressure_drop_vs_air_flow":
        entry |= {
            "slope_air_flow": sig9(fits.get("slope")),
            "intercept_air_flow": sig9(fits.get("intercept")),
            "r2_air_flow": sig9(fits.get("r2")),
            "slope_air_flow_sq": sig9(fits.get("slope_sq")),
            "intercept_air_flow_sq": sig9(fits.get("intercept_sq")),
            "r2_air_flow_sq": sig9(fits.get("r2_sq")),
        }
    else:
        raise ValueError(f"unknown relationship kind {kind!r}")
    return entry


# ---------------------------------------------------------------------------- the document


def build_profile(
    *,
    database: str,
    experiments_file: str,
    experiments: list[dict[str, str]],
    span_probe: dict[str, Any],
    series: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    seconds: float,
    queries: int,
) -> dict[str, Any]:
    kind_order = {kind: i for i, kind in enumerate(RELATIONSHIP_KINDS)}
    return {
        "schema_version": 1,
        "source": {"database": database, "experiments_file": experiments_file},
        "experiments": sorted(experiments, key=lambda e: e["experiment_id"]),
        "span_probe": span_probe,
        "series": sorted(series, key=lambda s: (s["experiment_id"], s["source"], s["signal"])),
        "relationships": sorted(
            relationships, key=lambda r: (r["experiment_id"], kind_order[r["kind"]])
        ),
        "timing": {"seconds": round(seconds, 3), "queries": queries},
    }


def without_timing(profile: Mapping[str, Any]) -> dict[str, Any]:
    """The profile minus the one block that may differ between two runs on the same data."""
    return {key: value for key, value in profile.items() if key != "timing"}


# ---------------------------------------------------------------------------- Markdown


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.9g}"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return lines


def _span(item: Mapping[str, Any]) -> str:
    return f"{item['start']} to {item['end']}"


def render_markdown(profile: Mapping[str, Any]) -> str:
    """The same numbers as the JSON, as tables. The JSON is the complete record: this file shows
    the first entry of each `longest` list only."""
    out: list[str] = ["# Post-ingest profile", ""]
    source = profile["source"]
    out += [
        "Counts, distributions and samples of the stored readings. Nothing here labels a reading.",
        "",
        f"- Database: `{source['database']}`; windows from `{source['experiments_file']}`.",
        "- Every query is limited to one experiment's window (start included, end excluded).",
        "- Floats are rounded to 9 significant digits. `stddev` is the sample standard deviation.",
        "- Percentiles are exact. Intervals and runs are in seconds.",
        "- `unmatched` counts points of the first-named signal with no partner at that instant.",
        "",
        "## Experiments",
        "",
    ]
    out += _table(
        ["experiment", "start", "end"],
        [[e["experiment_id"], e["start"], e["end"]] for e in profile["experiments"]],
    )
    probe = profile["span_probe"]
    out += ["", "## Span probe", ""]
    out += _table(
        ["from", "to", "answered", "count", "sum of per-experiment counts", "message file"],
        [
            [
                probe["start"],
                probe["end"],
                "yes" if probe["succeeded"] else "no",
                probe["count"],
                probe["sum_of_per_experiment_counts"],
                probe["message_file"],
            ]
        ],
    )

    by_experiment: dict[str, list[Mapping[str, Any]]] = {}
    for entry in profile["series"]:
        by_experiment.setdefault(entry["experiment_id"], []).append(entry)
    relationships: dict[str, list[Mapping[str, Any]]] = {}
    for rel in profile["relationships"]:
        relationships.setdefault(rel["experiment_id"], []).append(rel)

    for experiment_id in sorted(set(by_experiment) | set(relationships)):
        series = by_experiment.get(experiment_id, [])
        out += ["", f"## {experiment_id}"]
        numeric = [s for s in series if s["values"] is not None]
        text = [s for s in series if s["states"] is not None]

        out += ["", "### Values", ""]
        out += _table(
            [
                "source",
                "signal",
                "unit",
                "points",
                "no value",
                "GOOD",
                "UNCERTAIN",
                "BAD",
                "min",
                "p05",
                "median",
                "mean",
                "p95",
                "max",
                "stddev",
                "doc. min",
                "doc. max",
                "below doc. min",
                "above doc. max",
            ],
            [
                [
                    s["source"],
                    s["signal"],
                    s["unit"],
                    s["points"],
                    s["points_without_value"],
                    s["quality"]["GOOD"],
                    s["quality"]["UNCERTAIN"],
                    s["quality"]["BAD"],
                    s["values"]["min"],
                    s["values"]["p05"],
                    s["values"]["median"],
                    s["values"]["mean"],
                    s["values"]["p95"],
                    s["values"]["max"],
                    s["values"]["stddev"],
                    s["documented_min"],
                    s["documented_max"],
                    s["values"]["below_documented_min"],
                    s["values"]["above_documented_max"],
                ]
                for s in numeric
            ],
        )
        if text:
            out += ["", "### Text signals", ""]
            out += _table(
                ["source", "signal", "points", "no value", "GOOD", "UNCERTAIN", "BAD", "values"],
                [
                    [
                        s["source"],
                        s["signal"],
                        s["points"],
                        s["points_without_value"],
                        s["quality"]["GOOD"],
                        s["quality"]["UNCERTAIN"],
                        s["quality"]["BAD"],
                        ", ".join(f"{k}: {v}" for k, v in s["states"].items()),
                    ]
                    for s in text
                ],
            )

        out += ["", "### Intervals between points (seconds)", ""]
        out += _table(
            [
                "signal",
                "nominal",
                "count",
                "min",
                "median",
                "p95",
                "max",
                "over 2x nominal",
                "over 10x nominal",
                "seconds in over-2x",
                "longest",
            ],
            [
                [
                    s["signal"],
                    s["nominal_interval_s"],
                    s["intervals_s"]["count"],
                    s["intervals_s"]["min"],
                    s["intervals_s"]["median"],
                    s["intervals_s"]["p95"],
                    s["intervals_s"]["max"],
                    s["intervals_s"]["over_2x_nominal"],
                    s["intervals_s"]["over_10x_nominal"],
                    s["intervals_s"]["seconds_in_over_2x"],
                    (
                        f"{_span(s['intervals_s']['longest'][0])} "
                        f"({_fmt(s['intervals_s']['longest'][0]['seconds'])} s)"
                        if s["intervals_s"]["longest"]
                        else None
                    ),
                ]
                for s in series
            ],
        )

        out += ["", "### Runs of identical values", ""]
        out += _table(
            ["signal", "runs", "median samples", "max samples", "max seconds", "longest run"],
            [
                [
                    s["signal"],
                    s["runs"]["count"],
                    s["runs"]["median_samples"],
                    s["runs"]["max_samples"],
                    s["runs"]["max_seconds"],
                    (
                        f"{_span(s['runs']['longest'][0])}: {s['runs']['longest'][0]['samples']} "
                        f"samples of {_fmt(s['runs']['longest'][0]['value'])}"
                        if s["runs"]["longest"]
                        else None
                    ),
                ]
                for s in series
            ],
        )

        out += ["", "### Step-to-step change (each value minus the previous)", ""]
        out += _table(
            ["signal", "count", "mean", "stddev", "median abs", "p95 abs", "max abs"],
            [
                [
                    s["signal"],
                    s["differences"]["count"],
                    s["differences"]["mean"],
                    s["differences"]["stddev"],
                    s["differences"]["median_abs"],
                    s["differences"]["p95_abs"],
                    s["differences"]["max_abs"],
                ]
                for s in numeric
            ],
        )

        for rel in relationships.get(experiment_id, []):
            out += ["", f"### Relationship: {rel['kind'].replace('_', ' ')}", ""]
            rows = [
                [key, value] for key, value in rel.items() if key not in ("experiment_id", "kind")
            ]
            out += _table(["measure", "value"], rows)

    timing = profile["timing"]
    out += ["", "## Timing", "", f"{timing['queries']} queries, {_fmt(timing['seconds'])} s.", ""]
    return "\n".join(out)
