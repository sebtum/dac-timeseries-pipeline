"""M0 pre-ingest census.

Measures what ingestion destroys, or what ingestion needs as input, per
ADR-0010 — nothing else. Read-only against `data/raw/dac_raw_timeseries.csv`;
touches no database, no containers. Reports counts, distributions and
samples only, never verdict labels (MISTAKES.md C-02) — grep for "GOOD",
"BAD" and "UNCERTAIN" only turns up the raw quality column, never something
this script decided.

Memory is bounded independently of file size: the file-order pass below
keeps only small, fixed-size accumulators (row counts, format-shape
counters, a last-seen timestamp per series — ~150 series), and the
collision pass sorts via `pipeline.collisions.sorted_external`, which never
holds more than one chunk plus one row per temp run (see that module's
docstring, and MISTAKES.md E-03 for the in-memory version this replaced).

Run: python -m scripts.pre_ingest_census [--chunk-size N]
Output: reports/pre_ingest_census.md
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pipeline.collisions import (
    DEFAULT_CHUNK_SIZE,
    Reading,
    find_collisions,
    parse_timestamp,
    sorted_external,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "dac_raw_timeseries.csv"
RAW_SHA256_FILE = ROOT / "data" / "raw" / "dac_raw_timeseries.sha256"
REPORT_PATH = ROOT / "reports" / "pre_ingest_census.md"

CATEGORICAL_SIGNALS_DECLARED = {"valve_state", "process_state"}  # ADR-0006:117
SAMPLE_LIMIT = 5

_DIGIT_RE = re.compile(r"\d")


def timestamp_shape(raw: str) -> str:
    """Collapse digits to 'D' so format variants group by punctuation/tz shape."""
    return _DIGIT_RE.sub("D", raw)


def is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class CensusStats:
    """Fixed-size accumulators updated once per row, in file order."""

    def __init__(self) -> None:
        self.total_rows = 0
        self.row_counts: Counter[tuple[str, str, str]] = Counter()
        self.last_seen_ts: dict[tuple[str, str, str], tuple[int, str, datetime]] = {}
        self.out_of_order_count = 0
        self.out_of_order_by_series: Counter[tuple[str, str, str]] = Counter()
        self.out_of_order_examples: list[dict] = []
        self.timestamp_shapes: dict[str, Counter[str]] = defaultdict(Counter)
        self.timestamp_shape_example: dict[tuple[str, str], str] = {}
        self.timestamp_parse_failures: list[dict] = []
        self.empty_value_counts: Counter[tuple[str, str, str]] = Counter()
        self.non_float_values: dict[str, Counter[str]] = defaultdict(Counter)


def stream_readings(path: Path, stats: CensusStats) -> Iterator[Reading]:
    """Single pass over the CSV in file order. Updates `stats` as it goes
    and yields a `Reading` for every row whose timestamp parses — the only
    rows the sort/collision stage can use.
    """
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=1):
            stats.total_rows += 1
            experiment_id = row["experiment_id"]
            source = row["source"]
            signal = row["signal"]
            value_raw = row["value"]
            quality = row["quality"]
            ts_raw = row["timestamp"]
            key = (experiment_id, source, signal)

            stats.row_counts[key] += 1

            shape = timestamp_shape(ts_raw)
            stats.timestamp_shapes[source][shape] += 1
            stats.timestamp_shape_example.setdefault((source, shape), ts_raw)

            if value_raw == "":
                stats.empty_value_counts[key] += 1
            elif not is_float(value_raw):
                stats.non_float_values[signal][value_raw] += 1

            try:
                ts = parse_timestamp(ts_raw)
            except ValueError:
                stats.timestamp_parse_failures.append(
                    {"row_number": row_number, "timestamp_raw": ts_raw, **row}
                )
                continue

            prev = stats.last_seen_ts.get(key)
            if prev is not None and ts < prev[2]:
                stats.out_of_order_count += 1
                stats.out_of_order_by_series[key] += 1
                if len(stats.out_of_order_examples) < SAMPLE_LIMIT:
                    stats.out_of_order_examples.append(
                        {
                            "series": key,
                            "prev_row": prev[0],
                            "prev_timestamp": prev[1],
                            "this_row": row_number,
                            "this_timestamp": ts_raw,
                        }
                    )
            stats.last_seen_ts[key] = (row_number, ts_raw, ts)

            yield Reading(
                row_number=row_number,
                timestamp_raw=ts_raw,
                timestamp=ts,
                experiment_id=experiment_id,
                source=source,
                signal=signal,
                value_raw=value_raw,
                quality=quality,
            )


def values_equal_raw(group: list[Reading]) -> bool:
    return len({r.value_raw for r in group}) == 1


def values_equal_float_exact(group: list[Reading]) -> bool | None:
    try:
        floats = {float(r.value_raw) for r in group}
    except ValueError:
        return None
    return len(floats) == 1


def values_equal_float_tolerant(group: list[Reading], tol: float = 1e-6) -> bool | None:
    try:
        floats = [float(r.value_raw) for r in group]
    except ValueError:
        return None
    return max(floats) - min(floats) <= tol


def run_collision_pass(sorted_readings: Iterator[Reading]):
    group_size_dist: Counter[int] = Counter()
    per_series_group_count: Counter[tuple[str, str, str]] = Counter()
    equal_raw_count = 0
    equal_float_exact_count = 0
    equal_float_tolerant_count = 0
    quality_differs_count = 0
    categorical_collision_groups: list[list[Reading]] = []
    conflicting_raw_samples: list[list[Reading]] = []
    exact_raw_samples: list[list[Reading]] = []
    total_groups = 0
    total_rows_in_groups = 0

    for group in find_collisions(sorted_readings):
        total_groups += 1
        total_rows_in_groups += len(group)
        group_size_dist[len(group)] += 1
        key = (group[0].experiment_id, group[0].source, group[0].signal)
        per_series_group_count[key] += 1

        raw_equal = values_equal_raw(group)
        if raw_equal:
            equal_raw_count += 1
            if len(exact_raw_samples) < SAMPLE_LIMIT:
                exact_raw_samples.append(group)
        else:
            if len(conflicting_raw_samples) < SAMPLE_LIMIT:
                conflicting_raw_samples.append(group)

        if values_equal_float_exact(group):
            equal_float_exact_count += 1

        if values_equal_float_tolerant(group):
            equal_float_tolerant_count += 1

        if len({r.quality for r in group}) > 1:
            quality_differs_count += 1

        if group[0].signal in CATEGORICAL_SIGNALS_DECLARED:
            categorical_collision_groups.append(group)

    return {
        "total_groups": total_groups,
        "total_rows_in_groups": total_rows_in_groups,
        "group_size_dist": group_size_dist,
        "per_series_group_count": per_series_group_count,
        "equal_raw_count": equal_raw_count,
        "equal_float_exact_count": equal_float_exact_count,
        "equal_float_tolerant_count": equal_float_tolerant_count,
        "quality_differs_count": quality_differs_count,
        "categorical_collision_groups": categorical_collision_groups,
        "conflicting_raw_samples": conflicting_raw_samples,
        "exact_raw_samples": exact_raw_samples,
    }


def fmt_group(group: list[Reading]) -> str:
    lines = [f"  series={group[0].experiment_id}/{group[0].source}/{group[0].signal}"]
    for r in group:
        lines.append(
            f"    row={r.row_number} ts={r.timestamp_raw!r} value={r.value_raw!r} "
            f"quality={r.quality!r}"
        )
    return "\n".join(lines)


def render_report(stats: CensusStats, collisions: dict, checksum: dict, chunk_size: int) -> str:
    lines: list[str] = []
    a = lines.append

    a("# Pre-ingest census")
    a("")
    a(f"Source: `{RAW_CSV.relative_to(ROOT).as_posix()}`")
    a("")
    a("Counts, distributions and samples only. See ADR-0010 for scope, ADR-0007 for the")
    a("collision-detection method reused here in detection-only mode (U-15). Collision")
    a(f"detection sorts via a bounded external merge sort (chunk size {chunk_size}) — see")
    a("`pipeline/collisions.py` and MISTAKES.md E-03.")
    a("")

    a("## Checksum")
    a("")
    a(f"- committed: `{checksum['committed']}`")
    a(f"- computed:  `{checksum['computed']}`")
    a(f"- equal: `{checksum['committed'] == checksum['computed']}`")
    a("")

    a("## Row counts")
    a("")
    a(f"- total data rows: {stats.total_rows}")
    a(f"- distinct series (experiment_id, source, signal): {len(stats.row_counts)}")
    a("")
    a("| experiment_id | source | signal | rows |")
    a("|---|---|---|---|")
    for (exp, src, sig), count in sorted(stats.row_counts.items()):
        a(f"| {exp} | {src} | {sig} | {count} |")
    a("")

    a("## Duplicate / collision census")
    a("")
    a("Groups of 2+ rows sharing (experiment_id, source, signal, timestamp), detected by")
    a("sorting on that key and comparing adjacent rows (ADR-0007). Three candidate")
    a('definitions of "same value" (U-08) are each reported separately.')
    a("")
    a(f"- total collision groups: {collisions['total_groups']}")
    a(f"- total rows involved: {collisions['total_rows_in_groups']}")
    a(f"- group size distribution: {dict(sorted(collisions['group_size_dist'].items()))}")
    a(
        f"- groups equal under raw string equality: {collisions['equal_raw_count']} / "
        f"{collisions['total_groups']}"
    )
    a(
        f"- groups equal under float() exact equality (numeric groups only): "
        f"{collisions['equal_float_exact_count']} / {collisions['total_groups']}"
    )
    a(
        f"- groups equal under float tolerance 1e-6 (numeric groups only): "
        f"{collisions['equal_float_tolerant_count']} / {collisions['total_groups']}"
    )
    a(f"- groups where quality differs between rows: {collisions['quality_differs_count']}")
    a(
        f"- groups on declared categorical signals {sorted(CATEGORICAL_SIGNALS_DECLARED)}: "
        f"{len(collisions['categorical_collision_groups'])}"
    )
    a("")
    a("Collision groups per series (top 15 by count):")
    a("")
    a("| experiment_id | source | signal | groups |")
    a("|---|---|---|---|")
    for (exp, src, sig), count in collisions["per_series_group_count"].most_common(15):
        a(f"| {exp} | {src} | {sig} | {count} |")
    a("")

    if collisions["categorical_collision_groups"]:
        a("Categorical collision groups (verbatim):")
        a("")
        a("```")
        for g in collisions["categorical_collision_groups"][:SAMPLE_LIMIT]:
            a(fmt_group(g))
        a("```")
        a("")

    a(f"Sample groups equal under raw string equality (up to {SAMPLE_LIMIT}):")
    a("")
    a("```")
    for g in collisions["exact_raw_samples"]:
        a(fmt_group(g))
    a("```")
    a("")

    a(f"Sample groups differing under raw string equality (up to {SAMPLE_LIMIT}):")
    a("")
    a("```")
    for g in collisions["conflicting_raw_samples"]:
        a(fmt_group(g))
    a("```")
    a("")

    a("## Out-of-order arrivals")
    a("")
    a("A row whose timestamp is earlier than the previous row seen for the same series,")
    a("in file order — evidence erased once storage sorts by time.")
    a("")
    a(f"- total out-of-order rows: {stats.out_of_order_count}")
    a("")
    if stats.out_of_order_by_series:
        a("By series (top 15):")
        a("")
        a("| experiment_id | source | signal | count |")
        a("|---|---|---|---|")
        for (exp, src, sig), count in stats.out_of_order_by_series.most_common(15):
            a(f"| {exp} | {src} | {sig} | {count} |")
        a("")
    if stats.out_of_order_examples:
        a(f"Sample instances (up to {SAMPLE_LIMIT}):")
        a("")
        a("```")
        for ex in stats.out_of_order_examples:
            a(f"  {ex}")
        a("```")
        a("")

    a("## Timestamp string-format variants")
    a("")
    a("Digits collapsed to 'D' so distinct punctuation/timezone shapes group together.")
    a("")
    a("| source | shape | count | example |")
    a("|---|---|---|---|")
    for source in sorted(stats.timestamp_shapes):
        for shape, count in stats.timestamp_shapes[source].most_common():
            example = stats.timestamp_shape_example[(source, shape)]
            a(f"| {source} | `{shape}` | {count} | `{example}` |")
    a("")
    if stats.timestamp_parse_failures:
        a(f"Unparseable timestamps ({len(stats.timestamp_parse_failures)} total, ")
        a(f"showing up to {SAMPLE_LIMIT}):")
        a("")
        a("```")
        for ex in stats.timestamp_parse_failures[:SAMPLE_LIMIT]:
            a(f"  {ex}")
        a("```")
        a("")
    else:
        a("Unparseable timestamps: 0")
        a("")

    a("## Empty / non-parseable values and non-numeric signals")
    a("")
    a(f"- rows with empty value: {sum(stats.empty_value_counts.values())}")
    a("")
    if stats.empty_value_counts:
        a("By series (top 15):")
        a("")
        a("| experiment_id | source | signal | empty rows |")
        a("|---|---|---|---|")
        for (exp, src, sig), count in stats.empty_value_counts.most_common(15):
            a(f"| {exp} | {src} | {sig} | {count} |")
        a("")

    a(f"Signals declared categorical (ADR-0006): {sorted(CATEGORICAL_SIGNALS_DECLARED)}")
    a("")
    a("Signals with at least one non-empty, non-float value, and the distinct raw values")
    a("seen (count each):")
    a("")
    for signal in sorted(stats.non_float_values):
        values = stats.non_float_values[signal]
        a(f"- `{signal}`: {dict(values.most_common())}")
    a("")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="max readings held in memory at once during the external sort (default: %(default)s)",
    )
    args = parser.parse_args()

    committed_checksum = RAW_SHA256_FILE.read_text(encoding="utf-8").split()[0]
    computed_checksum = sha256_of(RAW_CSV)

    stats = CensusStats()
    readings = stream_readings(RAW_CSV, stats)
    sorted_readings = sorted_external(readings, chunk_size=args.chunk_size)
    collisions = run_collision_pass(sorted_readings)

    report = render_report(
        stats,
        collisions,
        {"committed": committed_checksum, "computed": computed_checksum},
        args.chunk_size,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"wrote {REPORT_PATH.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
