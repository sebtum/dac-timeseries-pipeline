"""Profile the stored readings: `python -m scripts.post_ingest_profile`.

Measures what ingest saved in InfluxDB, per experiment and series, and writes the numbers to a
file. It measures; it never judges a reading, cleans anything or writes to the database
(M2.5, ADR-0010, ADR-0014). Per series: value range against the documented range, spacing between
points against the nominal rate, gaps, runs of identical values, step-to-step change. Per
experiment: four physical cross-checks (power against voltage times current, outlet against
inlet CO2, current against its setpoint with the lag, pressure drop against air flow).

    0  profile written
    2  refused, nothing written (database missing, no readings, experiments file unreadable,
       InfluxDB not configured or not reachable)
    3  a profiling query failed, nothing written
    70 internal error (a bug)

Outputs in `--report-dir`: `post_ingest_profile.json` (contract:
`contracts/post_ingest_profile.schema.json`), `post_ingest_profile.md` (same numbers as tables),
and `post_ingest_profile_span_probe.txt` only when the server refused the one full-span query.
Files are written at the end, so a failed run leaves no half-written profile behind.
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
from pathlib import Path
from typing import Any

from pipeline.ingest import load_experiment_windows
from pipeline.ingest_influx import DatabaseCheckFailed, list_databases
from pipeline.profiling import (
    PROBE_MESSAGE_FILE,
    build_profile,
    datetime_text,
    render_markdown,
)
from pipeline.profiling_sql import (
    Gateway,
    InfluxGateway,
    QueryFailed,
    Window,
    profile_experiment,
    span_probe,
    tables_present,
)
from pipeline.signals import NUMERIC_TABLE
from scripts.ingest import display_path
from scripts.init_influx import load_env

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "raw" / "experiments.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_DATABASE = "dac_raw"

EXIT_REFUSED = 2
EXIT_QUERY_FAILED = 3
EXIT_INTERNAL_ERROR = 70

JSON_NAME = "post_ingest_profile.json"
MARKDOWN_NAME = "post_ingest_profile.md"


@dataclass(frozen=True)
class Config:
    database: str = DEFAULT_DATABASE
    experiments_path: Path = DEFAULT_EXPERIMENTS
    report_dir: Path = DEFAULT_REPORT_DIR


@dataclass
class Deps:
    """Everything the run reaches outside itself for; tests substitute these."""

    list_databases: Callable[[str, str], list[str]] = list_databases
    gateway_factory: Callable[[str, str, str], Gateway] = InfluxGateway
    env: dict[str, str] | None = None
    clock: Callable[[], float] = field(default=time.monotonic)


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_outputs(report_dir: Path, profile: dict[str, Any], probe_message: str | None) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_text(report_dir / JSON_NAME, json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
    _write_text(report_dir / MARKDOWN_NAME, render_markdown(profile))
    message_path = report_dir / PROBE_MESSAGE_FILE
    if probe_message is not None:
        _write_text(message_path, probe_message.rstrip("\n") + "\n")
    elif message_path.exists():
        message_path.unlink()  # a leftover from an earlier run would contradict this profile


def run(config: Config, deps: Deps | None = None) -> int:
    """Run one profile and return its exit code. Writes nothing unless it returns 0."""
    deps = deps or Deps()
    clock_start = deps.clock()

    def refuse(reason: str, detail: str) -> int:
        print(f"post_ingest_profile: refused ({reason}): {detail}", file=sys.stderr)
        return EXIT_REFUSED

    # ---- 1. refuse early: nothing here touches the report directory ---------------------
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
            f"database {config.database!r} does not exist; the profile never creates one",
        )

    # ---- 2. measure: read-only queries, one experiment window at a time -----------------
    gateway = deps.gateway_factory(host, token, config.database)
    try:
        tables = tables_present(gateway)
        if not tables:
            return refuse("no_readings", f"{config.database!r} has no readings table")

        series: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        ordered = sorted(windows.values(), key=lambda e: e.experiment_id)
        for experiment in ordered:
            window = Window(experiment.experiment_id, experiment.start, experiment.end)
            found, related = profile_experiment(gateway, window, tables)
            series += found
            relationships += related
        if not series:
            return refuse("no_readings", "no readings inside any experiment window")

        # ---- 3. the one full-span query, recorded whether or not it is answered ---------
        first = min(e.start for e in ordered)
        last = max(e.end for e in ordered)
        count, message = span_probe(gateway, first, last)
        per_experiment_sum = sum(s["points"] for s in series if s["table"] == NUMERIC_TABLE)
        queries = gateway.queries
    except QueryFailed as exc:
        print(f"post_ingest_profile: {exc}", file=sys.stderr)
        return EXIT_QUERY_FAILED
    finally:
        close = getattr(gateway, "close", None)
        if close is not None:
            close()

    profile = build_profile(
        database=config.database,
        experiments_file=display_path(config.experiments_path),
        experiments=[
            {
                "experiment_id": e.experiment_id,
                "start": datetime_text(e.start),
                "end": datetime_text(e.end),
            }
            for e in ordered
        ],
        span_probe={
            "start": datetime_text(first),
            "end": datetime_text(last),
            "succeeded": message is None,
            "count": count,
            "sum_of_per_experiment_counts": per_experiment_sum,
            "message_file": None if message is None else PROBE_MESSAGE_FILE,
        },
        series=series,
        relationships=relationships,
        seconds=deps.clock() - clock_start,
        queries=queries,
    )
    write_outputs(config.report_dir, profile, message)

    points = sum(s["points"] for s in series)
    print(
        f"post_ingest_profile: {len(series)} series, {len(ordered)} experiments, "
        f"{len(relationships)} relationships, {points} points, {queries} queries; "
        f"span probe {'answered' if message is None else 'refused'}; "
        f"written to {display_path(config.report_dir)}"
    )
    return 0


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.post_ingest_profile", description=__doc__
    )
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
