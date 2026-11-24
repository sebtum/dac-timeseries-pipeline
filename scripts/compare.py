"""Compare the experiments from the cleaned readings and metrics: `python -m scripts.compare`.

Runs after `python -m scripts.clean` and `python -m scripts.metrics`. Reads the accepted readings
and phases of the current cleaning policy version, the `metrics_series` of the current metrics
version and the Postgres `experiment` and `experiment_metrics` rows, then fits the voltage models,
computes the steady-state KPIs and the comparability of every pair, and writes
`comparison_summary.json` (contract: `contracts/comparison_summary.schema.json`) and
`comparison_report.md` to `--report-dir`. It is read-only: it writes no InfluxDB or Postgres row,
never creates a database, and writes its two files only at the end of a successful run (M5).

    0  written
    2  refused, nothing written (database missing, no cleaned rows for the policy version, no
       metrics_series rows for the metrics and policy version, experiments file unreadable,
       Postgres not reachable, migration 0003 not applied, an experiment missing from Postgres
       or without experiment_metrics rows, or window_mismatch)
    3  a query failed; no outputs
    70 internal error (a bug)

A re-run on the same data gives the same summary except `timing`, and the same report.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.compare_run import (
    DEFAULT_DATABASE,
    DEFAULT_EXPERIMENTS,
    DEFAULT_PG_SCHEMA,
    DEFAULT_REPORT_DIR,
    EXIT_INTERNAL_ERROR,
    Config,
    run,
)
from pipeline.metrics import METRICS_VERSION


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="python -m scripts.compare", description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--policy-version",
        default=POLICY_VERSION,
        help="cleaning policy version whose accepted readings are the inputs",
    )
    parser.add_argument(
        "--metrics-version",
        default=METRICS_VERSION,
        help="metrics version whose metrics_series and experiment_metrics rows are the inputs",
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
        metrics_version=args.metrics_version,
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
