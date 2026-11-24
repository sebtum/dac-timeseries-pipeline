"""Decide for every stored reading whether it can be trusted: `python -m scripts.clean`.

Reads the raw tables of one InfluxDB database, applies the rules in `pipeline/cleaning_policy.py`
and writes three new tables beside them: `readings_processed` (one row per numeric reading, raw
value, processed value, flag, verdict, reason), `state_intervals` (one row per state event and
how long it lasted) and `quality_intervals` (gaps and flatline runs). It never writes a raw
table and never creates a database (M3, ADR-0015).

    0  written, and the read-back counts balance
    2  refused, nothing written (database missing, no raw readings, series not in the policy,
       experiments file unreadable, InfluxDB not configured or not reachable)
    3  a query or a write failed; nothing is reported
    4  written, but the read-back counts do not balance (the summary says where)
    70 internal error (a bug)

Outputs in `--report-dir`: `cleaning_summary.json` (contract:
`contracts/cleaning_summary.schema.json`) and `cleaning_report.md` (the same numbers as tables,
plus hand-check samples). They are written only after the read-back, so exit 2 and 3 leave no
summary behind. A re-run on the same data writes the same rows (same keys, same values).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline import cleaning
from pipeline.cleaning import RawPoint, SeriesResult, Verdict
from pipeline.cleaning_influx import (
    PROCESSED_FOR,
    CleaningGateway,
    Gateway,
    raw_counts,
    series_lines,
)
from pipeline.cleaning_policy import POLICY_VERSION, REASON_CODES
from pipeline.ingest import Experiment, load_experiment_windows, timestamp_ns
from pipeline.ingest_influx import (
    DatabaseCheckFailed,
    WriteFailed,
    list_databases,
    send_with_retry,
)
from pipeline.profiling_sql import QueryFailed
from pipeline.signals import NUMERIC_TABLE, STATE_TABLE, TABLE_FOR
from scripts.ingest import display_path
from scripts.init_influx import load_env

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "raw" / "experiments.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_DATABASE = "dac_raw"
BATCH_LINES = 10_000

EXIT_REFUSED = 2
EXIT_FAILED = 3
EXIT_UNBALANCED = 4
EXIT_INTERNAL_ERROR = 70

JSON_NAME = "cleaning_summary.json"
MARKDOWN_NAME = "cleaning_report.md"


@dataclass(frozen=True)
class Config:
    database: str = DEFAULT_DATABASE
    experiments_path: Path = DEFAULT_EXPERIMENTS
    report_dir: Path = DEFAULT_REPORT_DIR


@dataclass
class Deps:
    """Everything the run reaches outside itself for; tests substitute these."""

    list_databases: Callable[[str, str], list[str]] = list_databases
    gateway_factory: Callable[[str, str, str], Gateway] = CleaningGateway
    env: dict[str, str] | None = None
    clock: Callable[[], float] = field(default=time.monotonic)
    sleep: Callable[[float], None] = field(default=time.sleep)


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_outputs(report_dir: Path, summary: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_text(report_dir / JSON_NAME, json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    _write_text(report_dir / MARKDOWN_NAME, cleaning.render_report(summary))


def judge_series(
    gateway: Gateway,
    window: Experiment,
    pair: tuple[str, str],
    conflicts: set[tuple[str, str, int]],
) -> tuple[list[RawPoint], list[Verdict]]:
    """Pull one series of one experiment and judge every point of it."""
    table = TABLE_FOR[pair]
    points = gateway.pull(table, window.experiment_id, pair[0], pair[1], window.start, window.end)
    instants = {t for s, g, t in conflicts if (s, g) == pair}
    return points, cleaning.judge(pair, points, instants)


def _ns(instant: datetime) -> int:
    return timestamp_ns(instant)


def run(config: Config, deps: Deps | None = None) -> int:
    """Run one cleaning and return its exit code. Writes no summary unless it returns 0 or 4."""
    deps = deps or Deps()
    clock_start = deps.clock()

    def refuse(reason: str, detail: str) -> int:
        print(f"clean: refused ({reason}): {detail}", file=sys.stderr)
        return EXIT_REFUSED

    # ---- 1. refuse early: nothing here touches the report directory or the database --------
    try:
        windows = load_experiment_windows(config.experiments_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return refuse("experiments_unreadable", f"{config.experiments_path}: {exc}")

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
            f"database {config.database!r} does not exist; cleaning never creates one",
        )

    ordered = sorted(windows.values(), key=lambda e: e.experiment_id)
    gateway = deps.gateway_factory(host, token, config.database)
    try:
        try:
            summary, points_written = _clean(gateway, config, ordered, deps)
        except Refused as exc:
            return refuse(exc.reason, exc.detail)
        queries = gateway.queries
    except (QueryFailed, WriteFailed) as exc:
        print(f"clean: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        close = getattr(gateway, "close", None)
        if close is not None:
            close()

    summary["timing"] = {
        "seconds": round(deps.clock() - clock_start, 3),
        "queries": queries,
        "points_written": points_written,
    }
    write_outputs(config.report_dir, summary)

    totals = summary["totals"]
    recon = summary["reconciliation"]
    balanced = recon["balanced"] and recon["raw_unchanged"]
    print(
        f"clean: {len(summary['series'])} series, {totals['raw_points']} raw points, "
        f"{totals['accepted']} accepted, {totals['excluded']} excluded, "
        f"{totals['gap_intervals']} gaps, {totals['flatline_intervals']} flatline runs; "
        f"{'balanced' if balanced else 'NOT balanced'}; "
        f"written to {display_path(config.report_dir)}"
    )
    return 0 if balanced else EXIT_UNBALANCED


def _clean(
    gateway: Gateway, config: Config, windows: list[Experiment], deps: Deps
) -> tuple[dict[str, Any], int]:
    tables = gateway.tables()
    if not tables & {NUMERIC_TABLE, STATE_TABLE}:
        raise Refused("no_raw_readings", f"{config.database!r} has no raw readings table")

    # Which series exist, and does the policy know all of them? Decided before any write.
    keys: dict[str, list[tuple[str, str]]] = {}
    for window in windows:
        found: set[tuple[str, str]] = set()
        for table in (NUMERIC_TABLE, STATE_TABLE):
            if table in tables:
                found |= set(
                    gateway.series_keys(table, window.experiment_id, window.start, window.end)
                )
        unknown = sorted(pair for pair in found if pair not in TABLE_FOR)
        if unknown:
            raise Refused("series_not_in_policy", f"{window.experiment_id}: {unknown}")
        keys[window.experiment_id] = sorted(found)
    if not any(keys.values()):
        raise Refused("no_raw_readings", "no readings inside any experiment window")

    raw_before = raw_counts(gateway, windows, tables)

    # ---- 2. judge and write, one series at a time ----------------------------------------
    results: list[SeriesResult] = []
    refs: dict[str, list[tuple[Experiment, tuple[str, str], int]]] = {c: [] for c in REASON_CODES}
    batch: list[str] = []
    points_written = 0

    def flush() -> None:
        nonlocal points_written
        if batch:
            send_with_retry(gateway.write, "\n".join(batch), deps.sleep)
            points_written += len(batch)
            batch.clear()

    for window in windows:
        conflicts = gateway.conflict_instants(window.experiment_id, window.start, window.end)
        for pair in keys[window.experiment_id]:
            points, verdicts = judge_series(gateway, window, pair, conflicts)
            result = cleaning.summarise_series(window.experiment_id, pair, points, verdicts)
            results.append(result)
            for index, verdict in enumerate(verdicts):
                if verdict.reason:
                    refs[verdict.reason].append((window, pair, index))
            spans = (
                cleaning.state_intervals(points, _ns(window.end))
                if TABLE_FOR[pair] == STATE_TABLE
                else None
            )
            batch += series_lines(
                window.experiment_id,
                pair,
                POLICY_VERSION,
                points,
                verdicts,
                spans,
                result.gaps,
                result.flatlines,
            )
            if len(batch) >= BATCH_LINES:
                flush()
    flush()

    # ---- 3. read back what was stored, and check the raw tables did not move ---------------
    by_key = {r.key: r for r in results}
    tables_now = gateway.tables()
    for window in windows:
        for raw_table, processed_table in PROCESSED_FOR.items():
            if processed_table not in tables_now:
                continue
            stored = gateway.count_processed(
                processed_table, window.experiment_id, window.start, window.end, POLICY_VERSION
            )
            for (source, signal), (rows, with_value) in stored.items():
                result = by_key.get((window.experiment_id, source, signal))
                if result is not None and result.table == raw_table:
                    result.processed_points = rows
                    result.processed_with_value = with_value
    raw_after = raw_counts(gateway, windows, tables_now)

    samples = _samples(gateway, refs)
    summary = cleaning.build_summary(
        policy_version=POLICY_VERSION,
        database=config.database,
        experiments_file=display_path(config.experiments_path),
        experiments=[
            {
                "experiment_id": w.experiment_id,
                "start": cleaning.instant_text(_ns(w.start)),
                "end": cleaning.instant_text(_ns(w.end)),
            }
            for w in windows
        ],
        results=results,
        raw_unchanged=raw_before == raw_after,
        samples=samples,
        seconds=0.0,
        queries=0,
        points_written=points_written,
    )
    return summary, points_written


def _samples(
    gateway: Gateway, refs: dict[str, list[tuple[Experiment, tuple[str, str], int]]]
) -> list[dict]:
    """First, middle and last excluded reading per reason, with their raw neighbours.

    A series is pulled again for each pick (at most 3 per reason), because the middle of all
    excluded readings is only known once every series has been judged.
    """
    cache: dict[tuple[str, str, str], tuple[list[RawPoint], list[Verdict]]] = {}
    conflicts: dict[str, set[tuple[str, str, int]]] = {}
    samples = []
    for code in REASON_CODES:
        found = refs[code]
        for pick in cleaning.pick_sample_indices(len(found)):
            window, pair, index = found[pick]
            key = (window.experiment_id, *pair)
            if key not in cache:
                if window.experiment_id not in conflicts:
                    conflicts[window.experiment_id] = gateway.conflict_instants(
                        window.experiment_id, window.start, window.end
                    )
                cache[key] = judge_series(gateway, window, pair, conflicts[window.experiment_id])
            points, verdicts = cache[key]
            samples.append(
                cleaning.sample_record(window.experiment_id, pair, index, points, verdicts)
            )
    return samples


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="python -m scripts.clean", description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)
    return Config(
        database=args.database, experiments_path=args.experiments, report_dir=args.report_dir
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
