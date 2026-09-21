"""CLI entrypoint for `pipeline.pg_migrate`: apply every pending migration to Postgres.

Connection parameters come from `.env` (see `.env.example`), same convention as
`scripts/init_influx.py` and `scripts/bootstrap_influx_token.py` — nothing here is a literal.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pipeline.pg_migrate import run_migrations

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


def load_env() -> dict[str, str]:
    """Parse `.env` into a dict; returns {} if it doesn't exist (nothing bootstrapped yet)."""
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def connect_kwargs(env: dict[str, str]) -> dict[str, str]:
    host = env.get("POSTGRES_HOST", "").strip()
    port = env.get("POSTGRES_PORT", "").strip()
    dbname = env.get("POSTGRES_DB", "").strip()
    user = env.get("POSTGRES_USER", "").strip()
    password = env.get("POSTGRES_PASSWORD", "").strip()
    if not all([host, port, dbname, user]):
        raise RuntimeError(
            "POSTGRES_HOST/PORT/DB/USER not set — copy .env.example to .env and fill in "
            "Postgres values"
        )
    return {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password,
    }


def main() -> int:
    try:
        applied = run_migrations(connect_kwargs(load_env()))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if applied:
        print(f"applied: {', '.join(applied)}")
    else:
        print("up to date, nothing to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
