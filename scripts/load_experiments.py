"""CLI entrypoint for `pipeline.metadata_loader`: upsert `experiments.json` into Postgres.

Connection parameters come from `.env` (see `.env.example`), reusing `scripts.migrate`'s
`load_env`/`connect_kwargs` — same convention as `scripts/init_influx.py`.
"""

from __future__ import annotations

import sys

from pipeline.metadata_loader import load_experiments
from scripts.migrate import connect_kwargs, load_env


def main() -> int:
    try:
        count = load_experiments(connect_kwargs(load_env()))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"loaded {count} experiment(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
