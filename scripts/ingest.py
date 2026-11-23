"""Ingest the raw CSV into InfluxDB: `python -m scripts.ingest`.

Copies every row of `data/raw/dac_raw_timeseries.csv` into `readings_numeric` /
`readings_state`, without changing a value, and proves with counts that nothing was lost:

    CSV rows = saved + exact copies + conflict losers + rejected      (per series)

`saved` is counted back from InfluxDB, not counted on write. Exit codes (decision 10):

    0  clean              1  finished with findings (rejected rows, readings outside window)
    2  refused, nothing written (wrong fingerprint, missing database, bad header, ...)
    3  a write failed after retries     4  the counts do not balance
    70 internal error (a bug; no summary)

Every run except 70 writes `ingest_summary.json`, `ingest_report.md` and `ingest_rejects.csv`
to the report directory; the summary validates against `contracts/ingest_summary.schema.json`.

Run order: refuse early (before any write) -> read, validate and sort -> resolve instants and
write batches -> count back. The design is in ADR-0013 and docs/discuss/M2.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.collisions import DEFAULT_CHUNK_SIZE, group_by_instant, sorted_external
from pipeline.ingest import (
    CSV_HEADER,
    REJECT_COLUMNS,
    Reject,
    RunFacts,
    Scan,
    SeriesKey,
    build_summary,
    conflict_line,
    decide_outcome,
    load_experiment_windows,
    reading_line,
    render_report,
    resolve_group,
)
from pipeline.ingest_influx import (
    DatabaseCheckFailed,
    InfluxGateway,
    WriteFailed,
    list_databases,
    send_with_retry,
)
from pipeline.signals import TABLE_FOR
from scripts.init_influx import load_env

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "data" / "raw" / "dac_raw_timeseries.csv"
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "raw" / "experiments.json"
DEFAULT_SHA256 = REPO_ROOT / "data" / "raw" / "dac_raw_timeseries.sha256"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_DATABASE = "dac_raw"
DEFAULT_BATCH_SIZE = 10_000

EXIT_REFUSED = 2
EXIT_WRITE_FAILED = 3
EXIT_INTERNAL_ERROR = 70

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Config:
    csv_path: Path = DEFAULT_CSV
    experiments_path: Path = DEFAULT_EXPERIMENTS
    sha256_path: Path = DEFAULT_SHA256
    database: str = DEFAULT_DATABASE
    report_dir: Path = DEFAULT_REPORT_DIR
    batch_size: int = DEFAULT_BATCH_SIZE


@dataclass
class Deps:
    """Everything the run reaches outside itself for; tests substitute these."""

    list_databases: Callable[[str, str], list[str]] = list_databases
    gateway_factory: Callable[[str, str, str], InfluxGateway] = InfluxGateway
    sleep: Callable[[float], None] = time.sleep
    chunk_size: int = DEFAULT_CHUNK_SIZE
    env: dict[str, str] | None = None


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_expected_sha256(path: Path) -> str:
    """First token of a `sha256sum`-style file. Raises FileNotFoundError or ValueError."""
    tokens = path.read_text(encoding="utf-8").split()
    expected = tokens[0].lower() if tokens else ""
    if not _SHA256_RE.match(expected):
        raise ValueError(f"{path} does not start with a 64-character hex SHA-256")
    return expected


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_reports(
    report_dir: Path, summary: dict, phases: dict[str, float], rejects_written: bool
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_text(
        report_dir / "ingest_summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    _write_text(report_dir / "ingest_report.md", render_report(summary, phases))
    if not rejects_written:
        with (report_dir / "ingest_rejects.csv").open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle, lineterminator="\n").writerow(REJECT_COLUMNS)


def _reject_row(reject: Reject) -> list[object]:
    fields = list(reject.fields) if reject.fields else [""] * len(CSV_HEADER)
    return [reject.row_number, reject.reason, reject.detail, *fields]


def run(config: Config, deps: Deps | None = None) -> int:
    """Run one ingest and return its exit code. Always writes the reports (except on a bug)."""
    deps = deps or Deps()
    started_at = datetime.now(UTC)
    clock_start = time.monotonic()
    phases: dict[str, float] = {}
    expected: str | None = None
    actual: str | None = None

    def facts(**overrides) -> RunFacts:
        values = {
            "csv_path": display_path(config.csv_path),
            "experiments_path": display_path(config.experiments_path),
            "database": config.database,
            "sha256_expected": expected,
            "sha256_actual": actual,
            "started_at": started_at,
            "duration_s": time.monotonic() - clock_start,
            "batch_size": config.batch_size,
        }
        values.update(overrides)
        return RunFacts(**values)

    def refuse(reason: str, detail: str) -> int:
        print(f"ingest: refused ({reason}): {detail}", file=sys.stderr)
        summary = build_summary(facts(), "refused", EXIT_REFUSED, None, None, reason)
        write_reports(config.report_dir, summary, phases, rejects_written=False)
        return EXIT_REFUSED

    # ---- 1. refuse early: nothing below this block writes to InfluxDB -------------------
    try:
        experiments = load_experiment_windows(config.experiments_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return refuse("experiments_unreadable", f"{config.experiments_path}: {exc}")

    if not config.csv_path.is_file():
        return refuse("file_missing", f"{config.csv_path} does not exist")

    try:
        expected = read_expected_sha256(config.sha256_path)
    except FileNotFoundError:
        return refuse("sha256_file_missing", f"{config.sha256_path} does not exist")
    except (OSError, ValueError) as exc:
        return refuse("sha256_file_invalid", str(exc))

    phase_start = time.monotonic()
    actual = sha256_of(config.csv_path)
    phases["fingerprint check"] = time.monotonic() - phase_start
    if actual != expected:
        return refuse("checksum_mismatch", f"expected {expected}, file is {actual}")

    try:
        with config.csv_path.open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), None)
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        return refuse("csv_unreadable", f"{config.csv_path}: {exc}")
    if header != CSV_HEADER:
        return refuse("bad_header", f"expected {','.join(CSV_HEADER)}, got {header}")

    env = {**load_env(), **{k: v for k, v in os.environ.items() if k.startswith("INFLUX_")}}
    if deps.env is not None:
        env = deps.env
    host = env.get("INFLUX_HOST", "").strip()
    token = env.get("INFLUX_TOKEN", "").strip()
    if not host or not token:
        return refuse("influx_not_configured", "INFLUX_HOST/INFLUX_TOKEN not set (see .env)")
    try:
        databases = deps.list_databases(host, token)
    except DatabaseCheckFailed as exc:
        return refuse(f"influx_{exc.kind}", exc.detail)
    if config.database not in databases:
        return refuse(
            "database_missing",
            f"database {config.database!r} does not exist; ingest never creates one "
            "(a write would create it with no retention)",
        )

    # ---- 2. read, validate, sort, resolve, write ----------------------------------------
    config.report_dir.mkdir(parents=True, exist_ok=True)
    rejects_path = config.report_dir / "ingest_rejects.csv"
    gateway = deps.gateway_factory(host, token, config.database)
    batches = 0
    conflicts_written = 0
    scan: Scan | None = None
    bounds: dict[str, list[datetime]] = {}
    tables_used: dict[str, set[str]] = {}
    lines: list[str] = []

    def flush() -> None:
        nonlocal batches
        if lines:
            send_with_retry(gateway.write, "\n".join(lines), deps.sleep)
            batches += 1
            lines.clear()

    try:
        with (
            config.csv_path.open(encoding="utf-8", newline="") as csv_file,
            rejects_path.open("w", encoding="utf-8", newline="") as rejects_file,
        ):
            rejects_csv = csv.writer(rejects_file, lineterminator="\n")
            rejects_csv.writerow(REJECT_COLUMNS)
            reader = csv.reader(csv_file)
            next(reader)  # the header, already checked above

            scan = Scan(experiments, on_reject=lambda r: rejects_csv.writerow(_reject_row(r)))
            ordered = sorted_external(scan.readings(enumerate(reader, start=1)), deps.chunk_size)

            phase_start = time.monotonic()
            write_start: float | None = None
            for group in group_by_instant(ordered):
                if write_start is None:
                    write_start = time.monotonic()
                    phases["read, validate, sort"] = write_start - phase_start
                first = group[0]
                key: SeriesKey = (first.experiment_id, first.source, first.signal)
                table = TABLE_FOR[(first.source, first.signal)]
                resolution = resolve_group(group, table)
                tally = scan.tally[key]
                tally.exact_copies += resolution.exact_copies
                tally.conflict_losers += len(resolution.losers)

                lines.append(reading_line(resolution.kept, table))
                for loser in resolution.losers:
                    lines.append(conflict_line(resolution.kept, loser))
                    conflicts_written += 1
                instant = resolution.kept.timestamp.astimezone(UTC)
                low_high = bounds.setdefault(first.experiment_id, [instant, instant])
                low_high[0] = min(low_high[0], instant)
                low_high[1] = max(low_high[1], instant)
                tables_used.setdefault(first.experiment_id, set()).add(table)
                if len(lines) >= config.batch_size:
                    flush()
            if write_start is None:
                phases["read, validate, sort"] = time.monotonic() - phase_start
            flush()
            if write_start is not None:
                phases["resolve and write"] = time.monotonic() - write_start
    except (csv.Error, UnicodeDecodeError) as exc:
        # The scan finishes before the first write, so nothing was saved yet.
        gateway.close()
        return refuse("csv_unreadable", str(exc))
    except WriteFailed as exc:
        print(f"ingest: write failed: {exc}", file=sys.stderr)
        summary = build_summary(
            facts(rows=scan.csv_rows, batches=batches, conflicts_written=conflicts_written),
            "write_failed",
            EXIT_WRITE_FAILED,
            scan,
            None,
        )
        write_reports(config.report_dir, summary, phases, rejects_written=True)
        gateway.close()
        return EXIT_WRITE_FAILED

    # ---- 3. count back from InfluxDB and reconcile --------------------------------------
    assert scan is not None  # noqa: S101
    count_start = time.monotonic()
    saved: dict[SeriesKey, int] = {}
    try:
        for experiment_id in sorted(bounds):
            low, high = bounds[experiment_id]
            for table in sorted(tables_used[experiment_id]):
                counts = gateway.count_points(table, experiment_id, low, high)
                for (source, signal), number in counts.items():
                    saved[(experiment_id, source, signal)] = number
    except Exception as exc:
        print(f"ingest: count-back failed: {exc}", file=sys.stderr)
        summary = build_summary(
            facts(rows=scan.csv_rows, batches=batches, conflicts_written=conflicts_written),
            "reconciliation_failed",
            4,
            scan,
            None,
        )
        write_reports(config.report_dir, summary, phases, rejects_written=True)
        gateway.close()
        return 4
    finally:
        phases["count back"] = time.monotonic() - count_start
    gateway.close()

    summary = build_summary(
        facts(rows=scan.csv_rows, batches=batches, conflicts_written=conflicts_written),
        "ok",
        0,
        scan,
        saved,
    )
    status, code = decide_outcome(
        unbalanced=sum(1 for s in summary["series"] if not s["balanced"]),
        rejected=sum(scan.rejects_by_reason.values()),
        outside_window=summary["window_check"]["outside_window_total"],
    )
    summary["status"], summary["exit_code"] = status, code
    write_reports(config.report_dir, summary, phases, rejects_written=True)

    totals = summary["totals"]
    print(
        f"ingest: {status} (exit {code}): {totals['csv_rows']} rows = {totals['saved']} saved"
        f" + {totals['exact_copies']} exact copies + {totals['conflict_losers']} conflict losers"
        f" + {totals['rejected']} rejected; reports in {display_path(config.report_dir)}"
    )
    return code


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="python -m scripts.ingest", description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--sha256", type=Path, default=DEFAULT_SHA256)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--batch-size", type=positive_int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)
    return Config(
        csv_path=args.csv,
        experiments_path=args.experiments,
        sha256_path=args.sha256,
        database=args.database,
        report_dir=args.report_dir,
        batch_size=args.batch_size,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        return run(config)
    except Exception:
        traceback.print_exc()
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
