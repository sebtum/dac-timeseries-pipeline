"""Load the comparison summary into Postgres: `python -m scripts.load_comparison`.

Reads `comparison_summary.json` (written by `python -m scripts.compare`), checks it against
`contracts/comparison_summary.schema.json`, and replaces the rows of its `compare_version` in
the three tables of migration 0004 in one transaction. Connection values come from `.env`
(`POSTGRES_*`). It writes nothing to InfluxDB and never creates a table or schema.

    0  written and read back
    2  refused, nothing written
    3  the write failed, rolled back
    4  written, but a read-back count differs
    70 internal error (a bug)

A second run on the same summary leaves the tables identical.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from pipeline.comparison_loader import (
    DEFAULT_PG_SCHEMA,
    DEFAULT_SUMMARY,
    EXIT_INTERNAL_ERROR,
    Config,
    run,
)


def parse_args(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="python -m scripts.load_comparison", description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--pg-schema",
        default=DEFAULT_PG_SCHEMA,
        help="Postgres schema used as search_path (tests use a throwaway schema)",
    )
    args = parser.parse_args(argv)
    return Config(summary_path=args.summary, pg_schema=args.pg_schema)


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        return run(config)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
