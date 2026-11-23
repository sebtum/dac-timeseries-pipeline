"""Ingest logic that needs no database: parse, validate, resolve, count, report.

Everything here is a pure function of the input rows (ADR-0007: no ingest time, run id or
file-order logic may reach a point), so the same file always produces the same points. The
database side (existence check, batched writes, retry, count-back) lives in
`pipeline/ingest_influx.py`; the command that wires the two together is `scripts/ingest.py`.

Row life cycle:

1. `parse_row` turns one CSV record into a `Reading` or a `Reject` with a named reason.
2. `Scan` counts what it sees in file order: rejects, out-of-order rows, offsets, the
   experiment-window check, per-series row counts. Its memory is bounded by the number of
   series, not rows (E-03: the claim has to hold at every stage).
3. The accepted readings are sorted by series then instant (`pipeline.collisions`), grouped
   by instant, and each group goes through `resolve_group`.
4. `reading_line` / `conflict_line` render the line protocol; `build_summary` and
   `render_report` describe the run.

Decisions behind the rules are in ADR-0013 (D1-D9 of docs/discuss/M2.md plus the planning
decisions) and ADR-0007.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from pipeline.collisions import Reading, parse_timestamp
from pipeline.signals import (
    CONFLICTS_TABLE,
    NUMERIC_TABLE,
    QUALITY_RANK,
    TABLE_FOR,
)

CSV_HEADER = ["timestamp", "experiment_id", "source", "signal", "value", "quality"]
REJECT_COLUMNS = [
    "row_number",
    "reason",
    "detail",
    "timestamp",
    "experiment_id",
    "source",
    "signal",
    "value",
    "quality",
]
REJECT_REASONS = (
    "bad_timestamp",
    "missing_offset",
    "precision_too_fine",
    "bad_number",
    "unknown_signal",
    "unknown_experiment",
    "bad_quality",
    "malformed_row",
)

# Series keys of rows that cannot be attributed to a real series (wrong column count, or
# garbage keys past the cap below) are counted under this key so the totals still balance.
UNATTRIBUTED = ("", "", "")
MAX_TRACKED_SERIES = 5_000

_TIMESTAMP_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$"
)
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

SeriesKey = tuple[str, str, str]


# --------------------------------------------------------------------------- experiments


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    start: datetime
    end: datetime


def load_experiment_windows(path: Path) -> dict[str, Experiment]:
    """Read experiment windows from `experiments.json` (decision 9: ingest needs only Influx)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    windows: dict[str, Experiment] = {}
    for entry in raw:
        windows[entry["experiment_id"]] = Experiment(
            experiment_id=entry["experiment_id"],
            start=parse_timestamp(entry["start_time"]).astimezone(UTC),
            end=parse_timestamp(entry["end_time"]).astimezone(UTC),
        )
    if not windows:
        raise ValueError("no experiments in file")
    return windows


# ---------------------------------------------------------------------------- parsing


class RowError(Exception):
    """A row that cannot be ingested; carries the named reason."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Reject:
    row_number: int
    reason: str
    detail: str
    fields: tuple[str, ...]  # the six raw columns, or empty for a malformed row
    series: SeriesKey


@dataclass(frozen=True)
class Parsed:
    reading: Reading
    offset_text: str


def parse_instant(raw: str) -> tuple[datetime, str]:
    """Strict timestamp parse: an explicit offset is mandatory, precision is never cut.

    Returns the instant in UTC and the offset exactly as written ("Z", "+02:00").
    """
    match = _TIMESTAMP_RE.match(raw)
    if not match:
        raise RowError("bad_timestamp", f"not an ISO 8601 timestamp: {raw!r}")
    year, month, day, hour, minute, second, fraction, offset = match.groups()
    if offset is None:
        raise RowError("missing_offset", f"no UTC offset or Z on {raw!r}")
    fraction = fraction or ""
    if len(fraction) > 6 and fraction[6:].strip("0"):
        raise RowError("precision_too_fine", f"finer than a microsecond: {raw!r}")
    microsecond = int(fraction[:6].ljust(6, "0")) if fraction else 0
    try:
        if offset == "Z":
            tz = UTC
        else:
            sign = -1 if offset[0] == "-" else 1
            tz = timezone(
                sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6])),
            )
        instant = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            microsecond,
            tzinfo=tz,
        )
    except ValueError as exc:
        raise RowError("bad_timestamp", f"{exc}: {raw!r}") from exc
    return instant.astimezone(UTC), offset


def parse_number(raw: str) -> float | None:
    """A plain decimal number, or None for an empty value. Anything else is `bad_number`."""
    if raw == "":
        return None
    if not _NUMBER_RE.match(raw):
        raise RowError("bad_number", f"not a number: {raw!r}")
    number = float(raw)
    if not math.isfinite(number):
        raise RowError("bad_number", f"not a finite number: {raw!r}")
    return number


def parse_row(
    row_number: int, fields: list[str], experiments: dict[str, Experiment]
) -> Parsed | Reject:
    """Validate one CSV record. Checks run in a fixed order; the first failure names the reason."""
    if len(fields) != len(CSV_HEADER):
        return Reject(
            row_number,
            "malformed_row",
            f"expected {len(CSV_HEADER)} columns, got {len(fields)}: {','.join(fields)}",
            (),
            UNATTRIBUTED,
        )
    timestamp_raw, experiment_id, source, signal, value_raw, quality = fields
    key = (experiment_id, source, signal)

    def reject(reason: str, detail: str) -> Reject:
        return Reject(row_number, reason, detail, tuple(fields), key)

    if experiment_id not in experiments:
        return reject("unknown_experiment", f"experiment {experiment_id!r} is not in the metadata")
    table = TABLE_FOR.get((source, signal))
    if table is None:
        return reject("unknown_signal", f"signal {signal!r} is not declared for source {source!r}")
    if quality not in QUALITY_RANK:
        return reject("bad_quality", f"quality {quality!r} is not GOOD, UNCERTAIN or BAD")
    try:
        instant, offset = parse_instant(timestamp_raw)
        if table == NUMERIC_TABLE:
            parse_number(value_raw)
        elif "\n" in value_raw or "\r" in value_raw:
            raise RowError("malformed_row", "line break inside a text value")
    except RowError as exc:
        return reject(exc.reason, exc.detail)

    reading = Reading(
        row_number=row_number,
        timestamp_raw=timestamp_raw,
        timestamp=instant,
        experiment_id=experiment_id,
        source=source,
        signal=signal,
        value_raw=value_raw,
        quality=quality,
    )
    return Parsed(reading, offset)


# ------------------------------------------------------------------------- the scan


@dataclass
class SeriesTally:
    csv_rows: int = 0
    rejected: int = 0
    exact_copies: int = 0
    conflict_losers: int = 0


@dataclass
class WindowTally:
    first: datetime | None = None
    last: datetime | None = None
    outside: int = 0


@dataclass
class Scan:
    """Counts everything knowable from the file alone, in file order.

    `readings()` is a generator over the accepted readings; by the time the external sort
    downstream has consumed it, every counter here is final.
    """

    experiments: dict[str, Experiment]
    on_reject: Callable[[Reject], None]
    csv_rows: int = 0
    tally: dict[SeriesKey, SeriesTally] = field(default_factory=dict)
    rejects_by_reason: Counter[str] = field(default_factory=Counter)
    offsets_seen: dict[str, set[str]] = field(default_factory=dict)
    out_of_order: Counter[SeriesKey] = field(default_factory=Counter)
    windows: dict[tuple[str, str], WindowTally] = field(default_factory=dict)
    _last_instant: dict[SeriesKey, datetime] = field(default_factory=dict)

    def _tally_for(self, key: SeriesKey) -> SeriesTally:
        tally = self.tally.get(key)
        if tally is None:
            # Real series (known experiment, declared pair) are bounded by the metadata, so
            # they always get their own entry. Garbage keys from rejected rows are capped,
            # past which they share one bucket: memory must not grow with bad rows (E-03).
            is_real = key[0] in self.experiments and (key[1], key[2]) in TABLE_FOR
            if not is_real and len(self.tally) >= MAX_TRACKED_SERIES:
                key = UNATTRIBUTED
            tally = self.tally.setdefault(key, SeriesTally())
        return tally

    def readings(self, rows: Iterable[tuple[int, list[str]]]) -> Iterator[Reading]:
        for row_number, fields in rows:
            self.csv_rows += 1
            outcome = parse_row(row_number, fields, self.experiments)
            if isinstance(outcome, Reject):
                tally = self._tally_for(outcome.series)
                tally.csv_rows += 1
                tally.rejected += 1
                self.rejects_by_reason[outcome.reason] += 1
                self.on_reject(outcome)
                continue
            reading = outcome.reading
            key = (reading.experiment_id, reading.source, reading.signal)
            self._tally_for(key).csv_rows += 1
            self.offsets_seen.setdefault(reading.source, set()).add(outcome.offset_text)
            self._note_order(key, reading.timestamp)
            self._note_window(reading)
            yield reading

    def _note_order(self, key: SeriesKey, instant: datetime) -> None:
        # Same definition as the M0 census: earlier than the previous row of the same series
        # in file order. Arrival order is transport, not value quality (D9).
        previous = self._last_instant.get(key)
        if previous is not None and instant < previous:
            self.out_of_order[key] += 1
        self._last_instant[key] = instant

    def _note_window(self, reading: Reading) -> None:
        window = self.experiments[reading.experiment_id]
        tally = self.windows.setdefault((reading.experiment_id, reading.source), WindowTally())
        if tally.first is None or reading.timestamp < tally.first:
            tally.first = reading.timestamp
        if tally.last is None or reading.timestamp > tally.last:
            tally.last = reading.timestamp
        # Start inclusive, end exclusive: matches every measured reading (D1).
        if reading.timestamp < window.start or reading.timestamp >= window.end:
            tally.outside += 1


# --------------------------------------------------------------------- resolution


@dataclass(frozen=True)
class Loser:
    reading: Reading
    rank: int  # 1 = the best of the discarded readings; makes each discard its own record
    reason: str  # value_differs | quality_differs
    resolution: str  # better_quality | present_value | lower_value | alphabetical


@dataclass(frozen=True)
class Resolution:
    kept: Reading
    exact_copies: int
    losers: tuple[Loser, ...]


def value_key(table: str, value_raw: str) -> tuple:
    """Content-only ordering key of a value; equal keys mean 'the same value' (D6).

    Numbers compare as numbers, exactly (250.0 == 250.00; no tolerance). Text compares as
    UTF-8 bytes, so the order is alphabetical and locale-independent. An empty value sorts
    after any present value (decision 5).
    """
    if value_raw == "":
        return (1, 0)
    if table == NUMERIC_TABLE:
        return (0, float(value_raw))
    return (0, value_raw.encode("utf-8"))


def _win_key(table: str, reading: Reading) -> tuple:
    return (QUALITY_RANK[reading.quality], *value_key(table, reading.value_raw))


def resolve_group(group: list[Reading], table: str) -> Resolution:
    """Pick the reading to store for one series and instant. Content only, never file order.

    Rule: better quality flag wins; then a present value beats an empty one; then the smaller
    number (or alphabetically first text) wins. Readings with the winner's value and quality
    are exact copies and are only counted; every other reading is a discarded conflict.
    Row number only breaks ties between identical readings, which affects provenance fields
    (`source_row_*`) and nothing stored in the readings tables.
    """
    ordered = sorted(group, key=lambda r: (_win_key(table, r), r.row_number))
    kept = ordered[0]
    kept_key = _win_key(table, kept)
    exact_copies = 0
    losers: list[Loser] = []
    for reading in ordered[1:]:
        key = _win_key(table, reading)
        if key == kept_key:
            exact_copies += 1
            continue
        same_value = key[1:] == kept_key[1:]
        if key[0] != kept_key[0]:
            resolution = "better_quality"
        elif key[1] != kept_key[1]:
            resolution = "present_value"
        elif table == NUMERIC_TABLE:
            resolution = "lower_value"
        else:
            resolution = "alphabetical"
        losers.append(
            Loser(
                reading=reading,
                rank=len(losers) + 1,
                reason="quality_differs" if same_value else "value_differs",
                resolution=resolution,
            )
        )
    return Resolution(kept=kept, exact_copies=exact_copies, losers=tuple(losers))


# ------------------------------------------------------------------ line protocol

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def timestamp_ns(instant: datetime) -> int:
    """Exact nanoseconds since the epoch (D2: store the instant, never round it)."""
    return (instant - _EPOCH) // timedelta(microseconds=1) * 1000


def _tag(value: str) -> str:
    return value.replace(",", r"\,").replace("=", r"\=").replace(" ", r"\ ")


def _text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def reading_line(reading: Reading, table: str) -> str:
    """One line for `readings_numeric` / `readings_state`. An empty value is left out."""
    fields = []
    if reading.value_raw != "":
        if table == NUMERIC_TABLE:
            fields.append(f"value={float(reading.value_raw)!r}")
        else:
            fields.append(f"value={_text(reading.value_raw)}")
    fields.append(f"quality={_text(reading.quality)}")
    tags = (
        f"experiment_id={_tag(reading.experiment_id)},"
        f"source={_tag(reading.source)},signal={_tag(reading.signal)}"
    )
    return f"{table},{tags} {','.join(fields)} {timestamp_ns(reading.timestamp)}"


def conflict_line(kept: Reading, loser: Loser) -> str:
    """One line per discarded reading, tagged with its rank so a group of 3 keeps both records."""
    discarded = loser.reading
    tags = (
        f"experiment_id={_tag(kept.experiment_id)},source={_tag(kept.source)},"
        f"signal={_tag(kept.signal)},discard_rank={loser.rank}"
    )
    fields = ",".join(
        [
            f"value_kept_raw={_text(kept.value_raw)}",
            f"quality_kept={_text(kept.quality)}",
            f"value_discarded_raw={_text(discarded.value_raw)}",
            f"quality_discarded={_text(discarded.quality)}",
            f"source_row_kept={kept.row_number}i",
            f"source_row_discarded={discarded.row_number}i",
            f"reason={_text(loser.reason)}",
            f"resolution={_text(loser.resolution)}",
        ]
    )
    return f"{CONFLICTS_TABLE},{tags} {fields} {timestamp_ns(kept.timestamp)}"


# ------------------------------------------------------------------ summary + report


@dataclass(frozen=True)
class RunFacts:
    """What the driver knows about a run, handed to `build_summary` as plain data."""

    csv_path: str
    experiments_path: str
    database: str
    sha256_expected: str | None
    sha256_actual: str | None
    started_at: datetime
    duration_s: float
    batch_size: int
    batches: int = 0
    conflicts_written: int = 0
    rows: int | None = None


def _counts(csv_rows: int, saved: int, exact: int, losers: int, rejected: int) -> dict:
    return {
        "csv_rows": csv_rows,
        "saved": saved,
        "exact_copies": exact,
        "conflict_losers": losers,
        "rejected": rejected,
        "balanced": csv_rows == saved + exact + losers + rejected,
    }


def build_summary(
    facts: RunFacts,
    status: str,
    exit_code: int,
    scan: Scan | None,
    saved: dict[SeriesKey, int] | None,
    refusal_reason: str | None = None,
) -> dict:
    """The `ingest_summary.json` document (contracts/ingest_summary.schema.json).

    `saved=None` means no count-back happened (refused or write failed): totals and series are
    then omitted rather than guessed. A refused run reports nothing read at all (`scan=None`).
    """
    checksum_ok = facts.sha256_expected is not None and facts.sha256_expected == facts.sha256_actual
    duration = facts.duration_s
    rows_per_second = (
        round(facts.rows / duration, 1) if facts.rows is not None and duration > 0 else None
    )

    totals = None
    series: list[dict] = []
    if scan is not None and saved is not None:
        for key in sorted(scan.tally):
            tally = scan.tally[key]
            series.append(
                {
                    "experiment_id": key[0],
                    "source": key[1],
                    "signal": key[2],
                    "table": TABLE_FOR.get((key[1], key[2]))
                    if key[0] in scan.experiments
                    else None,
                    **_counts(
                        tally.csv_rows,
                        saved.get(key, 0),
                        tally.exact_copies,
                        tally.conflict_losers,
                        tally.rejected,
                    ),
                }
            )
        totals = _counts(
            sum(s["csv_rows"] for s in series),
            sum(s["saved"] for s in series),
            sum(s["exact_copies"] for s in series),
            sum(s["conflict_losers"] for s in series),
            sum(s["rejected"] for s in series),
        )

    ooo_by_series = []
    window_rows = []
    if scan is not None:
        ooo_by_series = [
            {"experiment_id": k[0], "source": k[1], "signal": k[2], "count": n}
            for k, n in sorted(scan.out_of_order.items())
        ]
        for (experiment_id, source), win in sorted(scan.windows.items()):
            experiment = scan.experiments[experiment_id]
            assert win.first is not None and win.last is not None  # noqa: S101
            window_rows.append(
                {
                    "experiment_id": experiment_id,
                    "source": source,
                    "first_offset_s": (win.first - experiment.start).total_seconds(),
                    "last_offset_s": (win.last - experiment.end).total_seconds(),
                    "outside_window": win.outside,
                }
            )

    return {
        "schema_version": 1,
        "status": status,
        "exit_code": exit_code,
        "refusal_reason": refusal_reason,
        "input": {
            "csv_path": facts.csv_path,
            "experiments_path": facts.experiments_path,
            "sha256_expected": facts.sha256_expected,
            "sha256_actual": facts.sha256_actual,
            "checksum_ok": checksum_ok,
            "rows": facts.rows,
        },
        "database": facts.database,
        "totals": totals,
        "series": series,
        "rejects_by_reason": dict(sorted(scan.rejects_by_reason.items())) if scan else {},
        "conflicts_written": facts.conflicts_written,
        "out_of_order": {
            "total": sum(r["count"] for r in ooo_by_series),
            "by_series": ooo_by_series,
        },
        "offsets_seen": (
            {source: sorted(offsets) for source, offsets in sorted(scan.offsets_seen.items())}
            if scan
            else {}
        ),
        "window_check": {
            "outside_window_total": sum(r["outside_window"] for r in window_rows),
            "by_experiment_source": window_rows,
        },
        "timing": {
            "started_at": facts.started_at.isoformat(),
            "duration_s": round(duration, 3),
            "rows_per_second": rows_per_second,
            "batch_size": facts.batch_size,
            "batches": facts.batches,
        },
    }


def decide_outcome(unbalanced: int, rejected: int, outside_window: int) -> tuple[str, int]:
    """Map a finished run to (status, exit code): 0 clean, 1 findings, 4 counts do not balance.

    Refusals (2) and failed writes (3) are decided where they happen. Conflicts, exact copies
    and out-of-order rows are counted but are not findings by themselves: they are expected
    properties of this data, reported in full (the real file exits 0 with 10 and 15).
    """
    if unbalanced:
        return "reconciliation_failed", 4
    if rejected or outside_window:
        return "completed_with_findings", 1
    return "ok", 0


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return lines


def render_report(summary: dict, phases: dict[str, float] | None = None) -> str:
    """The human-readable twin of the summary: same numbers, plain Markdown."""
    inp = summary["input"]
    timing = summary["timing"]
    out = [
        "# Ingest report",
        "",
        f"Status: **{summary['status']}** (exit code {summary['exit_code']})",
    ]
    if summary["refusal_reason"]:
        out.append(f"Refused because: `{summary['refusal_reason']}`. Nothing was written.")
    out += [
        "",
        f"- File: `{inp['csv_path']}`",
        f"- SHA-256 expected: `{inp['sha256_expected']}`",
        f"- SHA-256 actual: `{inp['sha256_actual']}`",
        f"- Fingerprint matches: {inp['checksum_ok']}",
        f"- Database: `{summary['database']}`",
        f"- Data rows read: {inp['rows']}",
        "",
        "## Totals",
        "",
    ]
    totals = summary["totals"]
    if totals is None:
        out.append("No totals: the run ended before the count-back from InfluxDB.")
    else:
        out += _table(
            ["CSV rows", "Saved", "Exact copies", "Conflict losers", "Rejected", "Balanced"],
            [
                [
                    totals["csv_rows"],
                    totals["saved"],
                    totals["exact_copies"],
                    totals["conflict_losers"],
                    totals["rejected"],
                    totals["balanced"],
                ]
            ],
        )
        out += [
            "",
            "`CSV rows = saved + exact copies + conflict losers + rejected`. "
            "`Saved` is counted back from InfluxDB, not counted on write.",
        ]
        unbalanced = [s for s in summary["series"] if not s["balanced"]]
        out += ["", f"Series: {len(summary['series'])}, unbalanced: {len(unbalanced)}."]
        for s in unbalanced:
            out.append(f"- unbalanced: {s['experiment_id']} / {s['source']} / {s['signal']}")

    out += ["", "## Rejected rows", ""]
    if summary["rejects_by_reason"]:
        out += _table(["Reason", "Rows"], [[k, v] for k, v in summary["rejects_by_reason"].items()])
        out.append("")
        out.append("Each one is listed with its row number in `ingest_rejects.csv`.")
    else:
        out.append("None.")

    out += [
        "",
        "## Conflicts",
        "",
        f"Rows written to `readings_conflicts`: {summary['conflicts_written']}",
    ]

    ooo = summary["out_of_order"]
    out += ["", "## Out-of-order rows", "", f"Total: {ooo['total']} (counted, stored normally)."]
    if ooo["by_series"]:
        out.append("")
        out += _table(
            ["Experiment", "Source", "Signal", "Rows"],
            [[o["experiment_id"], o["source"], o["signal"], o["count"]] for o in ooo["by_series"]],
        )

    out += ["", "## Timestamp offsets as written", ""]
    out += _table(
        ["Source", "Offsets"],
        [[s, ", ".join(offsets)] for s, offsets in summary["offsets_seen"].items()],
    )

    window = summary["window_check"]
    out += [
        "",
        "## Experiment window check",
        "",
        "First reading minus experiment start, last reading minus experiment end (seconds). "
        "Window is start inclusive, end exclusive. "
        f"Readings outside: {window['outside_window_total']}.",
        "",
    ]
    out += _table(
        ["Experiment", "Source", "First vs start (s)", "Last vs end (s)", "Outside"],
        [
            [
                w["experiment_id"],
                w["source"],
                w["first_offset_s"],
                w["last_offset_s"],
                w["outside_window"],
            ]
            for w in window["by_experiment_source"]
        ],
    )

    out += [
        "",
        "## Timing",
        "",
        f"- Started: {timing['started_at']}",
        f"- Duration: {timing['duration_s']} s",
        f"- Rows per second: {timing['rows_per_second']}",
        f"- Batch size: {timing['batch_size']}, batches sent: {timing['batches']}",
    ]
    if phases:
        out += [f"- {name}: {seconds:.1f} s" for name, seconds in phases.items()]

    if summary["series"]:
        out += ["", "## Per series", ""]
        out += _table(
            ["Experiment", "Source", "Signal", "CSV rows", "Saved", "Copies", "Losers", "Rejected"],
            [
                [
                    s["experiment_id"],
                    s["source"],
                    s["signal"],
                    s["csv_rows"],
                    s["saved"],
                    s["exact_copies"],
                    s["conflict_losers"],
                    s["rejected"],
                ]
                for s in summary["series"]
            ],
        )
    return "\n".join(out) + "\n"


__all__ = [
    "CSV_HEADER",
    "REJECT_COLUMNS",
    "REJECT_REASONS",
    "UNATTRIBUTED",
    "Experiment",
    "Loser",
    "Parsed",
    "Reject",
    "Resolution",
    "RowError",
    "RunFacts",
    "Scan",
    "SeriesTally",
    "WindowTally",
    "build_summary",
    "conflict_line",
    "decide_outcome",
    "load_experiment_windows",
    "parse_instant",
    "parse_number",
    "parse_row",
    "reading_line",
    "render_report",
    "resolve_group",
    "timestamp_ns",
    "value_key",
]
