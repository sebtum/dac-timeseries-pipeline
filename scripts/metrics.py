"""Derive the process metrics from the cleaned readings: `python -m scripts.metrics`.

Runs after `python -m scripts.clean`. Reads the accepted readings of the current cleaning policy
version, computes the 13 metrics of every experiment (energy, capture, specific energy,
data quality), writes four derived series into `metrics_series` of the same InfluxDB database and
two small tables into Postgres (`experiment_metrics`, `signal_quality`), reads the counts back,
and writes `metrics_summary.json` (contract: `contracts/metrics_summary.schema.json`) and
`metrics_report.md` to `--report-dir`. It never creates a database and never writes an input
table (M4, ADR-0016).

    0  written and read back
    1  written and read back, but a plausibility check failed (outputs are written)
    2  refused, nothing written (database missing, no cleaned rows for the policy version,
       experiments file unreadable, Postgres not reachable, migration 0003 not applied, an
       experiment missing from Postgres)
    3  a query or a write failed; no outputs
    4  written, but a read-back count differs (the summary says where)
    70 internal error (a bug)

A re-run on the same data writes the same rows (same keys, same values).
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.metrics_run import (
    DEFAULT_DATABASE,
    DEFAULT_EXPERIMENTS,
    DEFAULT_PG_SCHEMA,
    DEFAULT_REPORT_DIR,
    EXIT_INTERNAL_ERROR,
    Config,
    run,
)


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="python -m scripts.metrics", description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--policy-version",
        default=POLICY_VERSION,
        help="cleaning policy version whose accepted readings are the inputs",
    )
    parser.add_argument(
        "--pg-schema",
        default=DEFAULT_PG_SCHEMA,
        help="Postgres schema used as search_path (tests use a throwaway schema)",
    )
    args = parser.parse_args(argv)
    return Config(
        database=args.database,
        experiments_path=args.experiments,
        report_dir=args.report_dir,
        policy_version=args.policy_version,
        pg_schema=args.pg_schema,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        return run(config)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
