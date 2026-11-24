"""The cleaning rules, pure (M3, ADR-0015): readings in, verdicts and intervals out.

No I/O and no InfluxDB here. A series of one experiment (at most about 7,200 points) is a list of
`RawPoint`, sorted by time; `judge_numeric` / `judge_state` return one `Verdict` per point. The
numbers all come from `pipeline/cleaning_policy.py`.

What a verdict is: `reason` is the first code that fired, in the priority order of
`REASON_CODES`, or empty when the reading is accepted; `flags` lists every code that fired in
that order, with the note `outside_typical_range` last. A reading is excluded exactly when
`reason` is not empty. Nothing is ever clamped, filled or smoothed: an accepted reading keeps
its raw value.

Two rules look at neighbours, so their definitions are exact (decisions 11 and 12):

- **spike** (Hampel): among the readings that have a value inside the physical limits, take up to
  5 on each side in time order. With the median `m` and the MAD of those neighbours plus the
  reading, the reading is a spike when `|x - m| > max(5 * 1.4826 * MAD, 10 * step)`. A step or a
  ramp keeps the median with it, so it is not a spike. A burst longer than 5 readings is not
  caught (a documented limit).
- **flatline**: over the same readings, step `j` (reading `j` to `j + 1`) is flat when
  `|change| < 0.2 * step`. A flat step is flagged when more than half of the steps within `h`
  on each side (the ones that exist) are flat; `h = max(5, ceil(30 / nominal))`. A flagged step
  must also sit in an unbroken run of at least `FLAT_MIN_RUN` (5) flat steps (decision 24), so
  scattered small steps on a smooth signal are chance, not a flatline, and a run of 3 readings
  flags none. For solar power (decision 25) a step is flat only when the change is exactly 0 and
  the two values are not both 0.0 (night). A reading is a flatline when it is an end of a flagged
  step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pipeline import cleaning_policy as policy
from pipeline.cleaning_policy import (
    FLAG_CODES,
    GAP_FACTOR,
    NOTE_OUTSIDE_TYPICAL,
    REASON_CODES,
)
from pipeline.signals import DOCUMENTED_RANGE, NOMINAL_INTERVAL_S, NUMERIC_TABLE, TABLE_FOR

NS = 1_000_000_000
ACCEPTED = "accepted"
EXCLUDED = "excluded"
LONGEST = 5
SAMPLE_NEIGHBOURS = 5


@dataclass(frozen=True)
class RawPoint:
    """One stored reading. `value` is None for a point saved without a value."""

    time_ns: int
    value: float | str | None
    quality: str


@dataclass(frozen=True)
class Verdict:
    reason: str  # "" when accepted
    flags: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.reason == ""

    @property
    def verdict(self) -> str:
        return ACCEPTED if self.accepted else EXCLUDED

    @property
    def flags_text(self) -> str:
        return ",".join(self.flags)


@dataclass(frozen=True)
class Interval:
    start_ns: int
    end_ns: int
    points: int = 0

    @property
    def seconds(self) -> float:
        return (self.end_ns - self.start_ns) / NS


# ---------------------------------------------------------------------------- helpers


def _median(sorted_values: list[float]) -> float:
    n = len(sorted_values)
    mid = n // 2
    if n % 2:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2


def _verdict(fired: set[str]) -> Verdict:
    flags = [code for code in REASON_CODES if code in fired]
    reason = flags[0] if flags else ""
    if NOTE_OUTSIDE_TYPICAL in fired:
        flags.append(NOTE_OUTSIDE_TYPICAL)
    return Verdict(reason=reason, flags=tuple(flags))


def _acquisition_codes(point: RawPoint, fired: set[str]) -> None:
    if point.value is None:
        fired.add("no_value")
    if point.quality == "BAD":
        fired.add("flag_bad")
    elif point.quality == "UNCERTAIN":
        fired.add("flag_uncertain")


# ---------------------------------------------------------------------------- spike, flatline


def spike_positions(values: list[float], step: float) -> list[int]:
    """Positions (in `values`) of the readings that deviate from the median of their window."""
    half = policy.SPIKE_HALF_WINDOW
    floor = policy.SPIKE_FLOOR_STEPS * step
    found = []
    for k, x in enumerate(values):
        window = sorted(values[max(0, k - half) : k + half + 1])
        m = _median(window)
        mad = _median(sorted(abs(w - m) for w in window))
        limit = max(policy.SPIKE_ROBUST_FACTOR * policy.SPIKE_MAD_SCALE * mad, floor)
        if abs(x - m) > limit:
            found.append(k)
    return found


def flatline_positions(
    values: list[float], step: float, half_window: int, exact_repeat: bool
) -> list[int]:
    """Positions (in `values`) of the readings that are an end of a flagged flat step.

    A step is flat when `|change| < 0.2 * step`; with `exact_repeat` (solar power) only when the
    change is exactly 0 and the two values are not both 0.0. A flat step is flagged when more than
    half of the steps within `half_window` on each side are flat and it sits in an unbroken run of
    at least `FLAT_MIN_RUN` flat steps.
    """
    n_steps = len(values) - 1
    if n_steps < 1:
        return []
    threshold = policy.FLAT_FRACTION * step
    flat = []
    for j in range(n_steps):
        change = abs(values[j + 1] - values[j])
        if exact_repeat:
            is_flat = change == 0.0 and values[j] != 0.0
        else:
            is_flat = change < threshold
        flat.append(is_flat)
    run_length = [0] * n_steps
    j = 0
    while j < n_steps:
        if not flat[j]:
            j += 1
            continue
        end = j
        while end < n_steps and flat[end]:
            end += 1
        for k in range(j, end):
            run_length[k] = end - j
        j = end
    prefix = [0]
    for is_flat in flat:
        prefix.append(prefix[-1] + (1 if is_flat else 0))
    flagged = [False] * len(values)
    for j in range(n_steps):
        if not flat[j] or run_length[j] < policy.FLAT_MIN_RUN:
            continue
        low = max(0, j - half_window)
        high = min(n_steps - 1, j + half_window)
        existing = high - low + 1
        if 2 * (prefix[high + 1] - prefix[low]) > existing:
            flagged[j] = flagged[j + 1] = True
    return [k for k, hit in enumerate(flagged) if hit]


# ---------------------------------------------------------------------------- verdicts


def judge_numeric(
    pair: tuple[str, str], points: list[RawPoint], conflicts: frozenset[int] | set[int]
) -> list[Verdict]:
    """One verdict per point of a numeric series (`points` sorted by time)."""
    rules = policy.POLICY[pair]
    low, high = rules.limits
    documented = DOCUMENTED_RANGE[pair]
    fired: list[set[str]] = [set() for _ in points]
    usable: list[int] = []
    for i, point in enumerate(points):
        codes = fired[i]
        _acquisition_codes(point, codes)
        value = point.value
        if value is not None:
            if not (low <= value <= high):
                codes.add("outside_physical_limits")
            else:
                usable.append(i)
            if value < documented[0] or value > documented[1]:
                codes.add(NOTE_OUTSIDE_TYPICAL)
        if point.time_ns in conflicts:
            codes.add("conflicting_duplicate")

    values = [float(points[i].value) for i in usable]
    if rules.spike:
        for k in spike_positions(values, rules.step):
            fired[usable[k]].add("spike")
    if rules.flatline:
        for k in flatline_positions(values, rules.step, rules.flat_half_window, rules.exact_repeat):
            fired[usable[k]].add("flatline")
    return [_verdict(codes) for codes in fired]


def judge_state(
    pair: tuple[str, str], points: list[RawPoint], conflicts: frozenset[int] | set[int]
) -> list[Verdict]:
    """One verdict per event of a state series. A value outside the declared set is excluded."""
    allowed = policy.POLICY[pair].states
    verdicts = []
    for point in points:
        codes: set[str] = set()
        _acquisition_codes(point, codes)
        if point.value is not None and point.value not in allowed:
            codes.add("unknown_state")
        if point.time_ns in conflicts:
            codes.add("conflicting_duplicate")
        verdicts.append(_verdict(codes))
    return verdicts


def judge(
    pair: tuple[str, str], points: list[RawPoint], conflicts: frozenset[int] | set[int]
) -> list[Verdict]:
    if TABLE_FOR[pair] == NUMERIC_TABLE:
        return judge_numeric(pair, points, conflicts)
    return judge_state(pair, points, conflicts)


# ---------------------------------------------------------------------------- intervals


def gap_intervals(pair: tuple[str, str], points: list[RawPoint]) -> list[Interval] | None:
    """Spacings over 2 x nominal between consecutive points. None for an on-change signal."""
    nominal = NOMINAL_INTERVAL_S.get(pair)
    if nominal is None:
        return None
    limit = GAP_FACTOR * nominal * NS
    return [
        Interval(a.time_ns, b.time_ns)
        for a, b in zip(points, points[1:], strict=False)
        if b.time_ns - a.time_ns > limit
    ]


def flatline_intervals(
    pair: tuple[str, str], points: list[RawPoint], verdicts: list[Verdict]
) -> list[Interval] | None:
    """Runs of consecutive flatline readings. None where the rule does not apply."""
    rules = policy.POLICY[pair]
    if not rules.flatline:
        return None
    runs: list[Interval] = []
    start = None
    for i, verdict in enumerate(verdicts):
        hit = "flatline" in verdict.flags
        if hit and start is None:
            start = i
        if start is not None and (not hit or i == len(verdicts) - 1):
            last = i if hit else i - 1
            runs.append(Interval(points[start].time_ns, points[last].time_ns, last - start + 1))
            start = None
    return runs


def state_intervals(points: list[RawPoint], experiment_end_ns: int) -> list[Interval]:
    """Each event lasts until the next one; the last until the experiment end. No expiry."""
    out = []
    for i, point in enumerate(points):
        end = points[i + 1].time_ns if i + 1 < len(points) else experiment_end_ns
        out.append(Interval(point.time_ns, max(end, point.time_ns), 1))
    return out


# ---------------------------------------------------------------------------- summary


def instant_text(time_ns: int) -> str:
    """UTC RFC 3339 with a fraction only when there is one, as the contract writes instants."""
    base = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=time_ns // NS)
    text = base.strftime("%Y-%m-%dT%H:%M:%S")
    fraction = time_ns % NS
    if fraction:
        text += "." + f"{fraction:09d}".rstrip("0")
    return text + "Z"


def _round(value: float) -> float:
    return float(f"{value:.9g}")


@dataclass
class SeriesResult:
    """Everything the summary needs about one series, without keeping its points."""

    experiment_id: str
    source: str
    signal: str
    raw_points: int
    accepted: int
    excluded: int
    excluded_by_reason: dict[str, int]
    flags: dict[str, int]
    gaps: list[Interval] | None
    flatlines: list[Interval] | None
    processed_points: int = 0  # read back from the database
    processed_with_value: int = 0  # read back: rows that carry a value

    @property
    def table(self) -> str:
        return TABLE_FOR[(self.source, self.signal)]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.experiment_id, self.source, self.signal)

    @property
    def balanced(self) -> bool:
        return (
            self.processed_points == self.raw_points and self.processed_with_value == self.accepted
        )


def summarise_series(
    experiment_id: str,
    pair: tuple[str, str],
    points: list[RawPoint],
    verdicts: list[Verdict],
) -> SeriesResult:
    by_reason = dict.fromkeys(REASON_CODES, 0)
    flag_counts = dict.fromkeys(FLAG_CODES, 0)
    for verdict in verdicts:
        if verdict.reason:
            by_reason[verdict.reason] += 1
        for code in verdict.flags:
            flag_counts[code] += 1
    excluded = sum(by_reason.values())
    return SeriesResult(
        experiment_id=experiment_id,
        source=pair[0],
        signal=pair[1],
        raw_points=len(points),
        accepted=len(points) - excluded,
        excluded=excluded,
        excluded_by_reason=by_reason,
        flags=flag_counts,
        gaps=gap_intervals(pair, points),
        flatlines=flatline_intervals(pair, points, verdicts),
    )


def _interval_json(interval: Interval) -> dict:
    return {
        "start": instant_text(interval.start_ns),
        "end": instant_text(interval.end_ns),
        "seconds": _round(interval.seconds),
    }


def series_json(result: SeriesResult) -> dict:
    gaps = None
    if result.gaps is not None:
        longest = sorted(result.gaps, key=lambda g: (-(g.end_ns - g.start_ns), g.start_ns))
        gaps = {
            "count": len(result.gaps),
            "seconds": _round(sum(g.seconds for g in result.gaps)),
            "longest": [_interval_json(g) for g in longest[:LONGEST]],
        }
    flatlines = None
    if result.flatlines is not None:
        flatlines = {
            "count": len(result.flatlines),
            "seconds": _round(sum(f.seconds for f in result.flatlines)),
        }
    return {
        "experiment_id": result.experiment_id,
        "source": result.source,
        "signal": result.signal,
        "table": result.table,
        "raw_points": result.raw_points,
        "processed_points": result.processed_points,
        "accepted": result.accepted,
        "excluded": result.excluded,
        "excluded_by_reason": dict(result.excluded_by_reason),
        "flags": dict(result.flags),
        "gaps": gaps,
        "flatline_intervals": flatlines,
    }


def build_summary(
    *,
    policy_version: str,
    database: str,
    experiments_file: str,
    experiments: list[dict],
    results: list[SeriesResult],
    raw_unchanged: bool,
    samples: list[dict],
    seconds: float,
    queries: int,
    points_written: int,
) -> dict:
    """The `cleaning_summary.json` document (contract: `contracts/cleaning_summary.schema.json`)."""
    ordered = sorted(results, key=lambda r: r.key)
    by_reason = dict.fromkeys(REASON_CODES, 0)
    flag_counts = dict.fromkeys(FLAG_CODES, 0)
    gap_intervals_n = 0
    gap_seconds = 0.0
    flatline_n = 0
    for result in ordered:
        for code, n in result.excluded_by_reason.items():
            by_reason[code] += n
        for code, n in result.flags.items():
            flag_counts[code] += n
        if result.gaps is not None:
            gap_intervals_n += len(result.gaps)
            gap_seconds += sum(g.seconds for g in result.gaps)
        if result.flatlines is not None:
            flatline_n += len(result.flatlines)
    unbalanced = [
        {
            "experiment_id": r.experiment_id,
            "source": r.source,
            "signal": r.signal,
            "raw_points": r.raw_points,
            "processed_points": r.processed_points,
        }
        for r in ordered
        if not r.balanced
    ]
    return {
        "schema_version": 1,
        "policy_version": policy_version,
        "source": {"database": database, "experiments_file": experiments_file},
        "experiments": experiments,
        "series": [series_json(r) for r in ordered],
        "totals": {
            "raw_points": sum(r.raw_points for r in ordered),
            "processed_points": sum(r.processed_points for r in ordered),
            "accepted": sum(r.accepted for r in ordered),
            "excluded": sum(r.excluded for r in ordered),
            "excluded_by_reason": by_reason,
            "flags": flag_counts,
            "gap_intervals": gap_intervals_n,
            "gap_seconds": _round(gap_seconds),
            "flatline_intervals": flatline_n,
        },
        "reconciliation": {
            "balanced": not unbalanced,
            "series_checked": len(ordered),
            "unbalanced": unbalanced,
            "raw_unchanged": raw_unchanged,
        },
        "samples": samples,
        "timing": {
            "seconds": round(seconds, 3),
            "queries": queries,
            "points_written": points_written,
        },
    }


# ---------------------------------------------------------------------------- samples


def pick_sample_indices(n: int) -> list[int]:
    """First, middle and last of `n` ordered items (fewer when `n` is small)."""
    if n <= 0:
        return []
    return sorted({0, n // 2, n - 1})


def sample_record(
    experiment_id: str,
    pair: tuple[str, str],
    index: int,
    points: list[RawPoint],
    verdicts: list[Verdict],
) -> dict:
    """One hand-check sample: the excluded reading and up to 5 raw neighbours on each side."""
    point = points[index]
    low = max(0, index - SAMPLE_NEIGHBOURS)
    high = min(len(points), index + SAMPLE_NEIGHBOURS + 1)
    return {
        "reason": verdicts[index].reason,
        "experiment_id": experiment_id,
        "source": pair[0],
        "signal": pair[1],
        "time": instant_text(point.time_ns),
        "value_raw": point.value,
        "neighbours": [
            {
                "time": instant_text(points[k].time_ns),
                "value_raw": points[k].value,
                "verdict": verdicts[k].verdict,
            }
            for k in range(low, high)
            if k != index
        ],
    }


# ---------------------------------------------------------------------------- report


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def render_report(summary: dict) -> str:
    """The same numbers as the summary, as tables, plus the hand-check samples."""
    totals = summary["totals"]
    recon = summary["reconciliation"]
    out = [
        "# Cleaning report",
        "",
        f"Policy version `{summary['policy_version']}`, "
        f"database `{summary['source']['database']}`. "
        "Generated by `python -m scripts.clean`; the numbers are the ones in "
        "`cleaning_summary.json`.",
        "",
        "## Totals",
        "",
        *_table(
            ["Measure", "Count"],
            [
                ["raw points", f"{totals['raw_points']:,}"],
                ["processed points", f"{totals['processed_points']:,}"],
                ["accepted", f"{totals['accepted']:,}"],
                ["excluded", f"{totals['excluded']:,}"],
                ["gap intervals", f"{totals['gap_intervals']:,}"],
                ["gap seconds", totals["gap_seconds"]],
                ["flatline intervals", f"{totals['flatline_intervals']:,}"],
            ],
        ),
        "",
        "## Reconciliation",
        "",
        *_table(
            ["Check", "Result"],
            [
                ["series checked", recon["series_checked"]],
                ["balanced (processed = raw, rows with a value = accepted)", recon["balanced"]],
                ["raw tables unchanged (counts before = after)", recon["raw_unchanged"]],
            ],
        ),
        "",
    ]
    if recon["unbalanced"]:
        out += [
            *_table(
                ["Experiment", "Source", "Signal", "Raw", "Processed"],
                [
                    [
                        u["experiment_id"],
                        u["source"],
                        u["signal"],
                        u["raw_points"],
                        u["processed_points"],
                    ]
                    for u in recon["unbalanced"]
                ],
            ),
            "",
        ]
    out += [
        "## Excluded readings by primary reason",
        "",
        *_table(
            ["Reason", "Excluded", "Fired (primary or not)"],
            [
                [code, f"{totals['excluded_by_reason'][code]:,}", f"{totals['flags'][code]:,}"]
                for code in REASON_CODES
            ]
            + [
                [
                    NOTE_OUTSIDE_TYPICAL + " (note)",
                    "0",
                    f"{totals['flags'][NOTE_OUTSIDE_TYPICAL]:,}",
                ]
            ],
        ),
        "",
        "## Series with an exclusion, a gap or a flatline",
        "",
    ]
    rows = []
    for s in summary["series"]:
        gaps = s["gaps"]["count"] if s["gaps"] else 0
        flat = s["flatline_intervals"]["count"] if s["flatline_intervals"] else 0
        if s["excluded"] or gaps or flat:
            reasons = ", ".join(f"{c} {n}" for c, n in s["excluded_by_reason"].items() if n)
            rows.append(
                [
                    s["experiment_id"],
                    s["source"],
                    s["signal"],
                    f"{s['raw_points']:,}",
                    s["excluded"],
                    reasons or "-",
                    gaps,
                    flat,
                ]
            )
    out += [
        *_table(
            ["Experiment", "Source", "Signal", "Raw", "Excluded", "By reason", "Gaps", "Flatlines"],
            rows,
        ),
        "",
        "## Hand-check samples",
        "",
        "For each reason that fired: the first, middle and last excluded reading in "
        "(experiment, source, signal, time) order, with up to 5 raw neighbours on each side.",
        "",
    ]
    for sample in summary["samples"]:
        out += [
            f"### {sample['reason']}: {sample['experiment_id']} {sample['source']}/"
            f"{sample['signal']} at {sample['time']}",
            "",
            f"Raw value `{sample['value_raw']}`.",
            "",
            *_table(
                ["Time", "Raw value", "Verdict"],
                [[n["time"], n["value_raw"], n["verdict"]] for n in sample["neighbours"]],
            ),
            "",
        ]
    timing = summary["timing"]
    out += [
        "## Timing",
        "",
        f"{timing['seconds']} s, {timing['queries']} queries, {timing['points_written']:,} "
        "points written.",
        "",
    ]
    return "\n".join(out)
