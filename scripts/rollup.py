"""Roll up the cleaned readings: `python -m scripts.rollup`.

Runs after `python -m scripts.clean`. Reads `readings_processed` in the raw database for the
current `POLICY_VERSION` only, one experiment window at a time, and writes 1-minute buckets to
the rollup database (`readings_rollup`, ADR-0011 columns plus `count_no_value`). The `_all`
columns are over points that have a raw value, the included columns over points whose verdict
is `accepted`; see `pipeline/rollup.py` and `pipeline/rollup_run.py` for the exact column rules
and the re-run limit.

    0  buckets written
    2  refused, nothing written (a database missing - never created -, `readings_processed`
       missing or without rows of the current policy version, experiments file unreadable,
       InfluxDB not configured or not reachable)
    3  a query or a write failed (buckets of earlier windows may already be written; a re-run
       overwrites them with identical values)
    70 internal error (a bug)

The raw database is only read. Neither database is ever created here.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from influxdb_client_3 import InfluxDBClient3

from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.ingest import load_experiment_windows
from pipeline.ingest_influx import DatabaseCheckFailed, list_databases
from pipeline.rollup_run import PROCESSED_MEASUREMENT, RollupFailed, run_rollup
from scripts.ingest import display_path
from scripts.init_influx import load_env

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "raw" / "experiments.json"
DEFAULT_DATABASE = "dac_raw"
DEFAULT_ROLLUP_DATABASE = "dac_rollup"

EXIT_REFUSED = 2
EXIT_FAILED = 3
EXIT_INTERNAL_ERROR = 70

_TABLES_SQL = (
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'iox' "
    "ORDER BY table_name"
)


@dataclass(frozen=True)
class Config:
    database: str = DEFAULT_DATABASE
    rollup_database: str = DEFAULT_ROLLUP_DATABASE
    experiments_path: Path = DEFAULT_EXPERIMENTS


def _make_client(host: str, token: str, database: str) -> InfluxDBClient3:
    return InfluxDBClient3(host=host, token=token, database=database)


@dataclass
class Deps:
    """Everything the run reaches outside itself for; tests substitute these."""

    list_databases: Callable[[str, str], list[str]] = list_databases
    client_factory: Callable[[str, str, str], Any] = _make_client
    env: dict[str, str] | None = None
    policy_version: str = POLICY_VERSION


def run(config: Config, deps: Deps | None = None) -> int:
    """Run one rollup and return its exit code."""
    deps = deps or Deps()

    def refuse(reason: str, detail: str) -> int:
        print(f"rollup: refused ({reason}): {detail}", file=sys.stderr)
        return EXIT_REFUSED

    # ---- 1. refuse early: nothing has been written yet ----------------------------------
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
    for name in (config.database, config.rollup_database):
        if name not in databases:
            return refuse(
                "database_missing",
                f"database {name!r} does not exist; the rollup never creates one",
            )

    # ---- 2. read the cleaned rows, write the buckets ------------------------------------
    raw_client = deps.client_factory(host, token, config.database)
    rollup_client = deps.client_factory(host, token, config.rollup_database)
    try:
        try:
            tables = raw_client.query(_TABLES_SQL, language="sql").column("table_name").to_pylist()
        except Exception as exc:  # noqa: BLE001 - any failure of the table check is a failed query
            print(f"rollup: query failed: {exc}", file=sys.stderr)
            return EXIT_FAILED
        if PROCESSED_MEASUREMENT not in tables:
            return refuse(
                "processed_missing",
                f"{config.database!r} has no {PROCESSED_MEASUREMENT} table; run clean first",
            )

        per_experiment: list[tuple[str, int]] = []
        for experiment in sorted(windows.values(), key=lambda e: e.experiment_id):
            try:
                written = run_rollup(
                    raw_client,
                    rollup_client,
                    experiment.start,
                    experiment.end,
                    deps.policy_version,
                    experiment_id=experiment.experiment_id,
                )
            except RollupFailed as exc:
                print(f"rollup: {experiment.experiment_id}: {exc}", file=sys.stderr)
                return EXIT_FAILED
            per_experiment.append((experiment.experiment_id, written))
            print(f"rollup: {experiment.experiment_id}: {written} buckets written")
    finally:
        for client in (raw_client, rollup_client):
            close = getattr(client, "close", None)
            if close is not None:
                close()

    total = sum(n for _, n in per_experiment)
    if total == 0:
        return refuse(
            "no_processed_rows",
            f"no {PROCESSED_MEASUREMENT} rows of policy_version {deps.policy_version!r} inside "
            "any experiment window; nothing written",
        )
    print(
        f"rollup: {total} buckets over {len(per_experiment)} experiments "
        f"(policy_version {deps.policy_version}) from {display_path(config.experiments_path)}: "
        f"{config.database} -> {config.rollup_database}"
    )
    return 0


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="python -m scripts.rollup", description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--rollup-database", default=DEFAULT_ROLLUP_DATABASE)
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    args = parser.parse_args(argv)
    return Config(
        database=args.database,
        rollup_database=args.rollup_database,
        experiments_path=args.experiments,
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
