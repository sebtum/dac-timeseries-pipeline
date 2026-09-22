"""Shared fixtures for tests that need a live InfluxDB or PostgreSQL container.

Both fixtures skip (via `pytest.skip`) rather than fail when the corresponding service is
unreachable — no container running, `.env` not bootstrapped yet (scripts/bootstrap_influx_token.py),
or a stale/invalid token — so `pytest` with no containers up reports skips, not errors or
failures. Tests that need Influx or Postgres should be marked `@pytest.mark.influx` /
`@pytest.mark.postgres` (registered in pyproject.toml) so a later CI task can select them.

Values are read from `.env` at the repo root (see `.env.example` for the full set and what
each one means); nothing here reads `.env.example` itself — an unbootstrapped environment has
no real token and must skip, not silently connect with a placeholder.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

HEALTH_CHECK_TIMEOUT_S = 3
QUERY_CHECK_TIMEOUT_S = 5
CONNECT_TIMEOUT_S = 3


def _load_env() -> dict[str, str]:
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


@pytest.fixture(scope="session")
def influx_client():
    """A connected `InfluxDBClient3`, scoped to the `_internal` database.

    `_internal` is used here only to prove connectivity + token validity — it always exists
    on a running Core instance (docs/spikes/U-13-core-token-bootstrap.md), unlike the project's
    own databases (`dac_raw` etc.), which are provisioned by a later M1 task. Tests that need a
    specific database should open their own client against the same host/token rather than
    reuse this one's database binding.
    """
    from influxdb_client_3 import InfluxDBClient3

    env = _load_env()
    host = env.get("INFLUX_HOST", "").strip()
    token = env.get("INFLUX_TOKEN", "").strip()
    if not host or not token:
        pytest.skip(
            "INFLUX_HOST/INFLUX_TOKEN not set — .env missing or not bootstrapped "
            "(run scripts/bootstrap_influx_token.py against a running influxdb container)"
        )

    try:
        urllib.request.urlopen(f"{host}/health", timeout=HEALTH_CHECK_TIMEOUT_S)  # noqa: S310
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        pytest.skip(f"InfluxDB not reachable at {host}: {exc}")

    try:
        client = InfluxDBClient3(host=host, token=token, database="_internal")
        client.query("SELECT 1", language="sql")
    except Exception as exc:  # noqa: BLE001 - any connection/auth failure means "skip"
        pytest.skip(f"InfluxDB client at {host} failed to connect/authenticate: {exc}")

    yield client
    client.close()


@pytest.fixture(scope="session")
def postgres_conn():
    """A connected `psycopg.Connection` to the project's PostgreSQL database."""
    import psycopg

    env = _load_env()
    host = env.get("POSTGRES_HOST", "").strip()
    port = env.get("POSTGRES_PORT", "").strip()
    dbname = env.get("POSTGRES_DB", "").strip()
    user = env.get("POSTGRES_USER", "").strip()
    password = env.get("POSTGRES_PASSWORD", "").strip()
    if not all([host, port, dbname, user]):
        pytest.skip(
            "POSTGRES_HOST/PORT/DB/USER not set — .env missing "
            "(copy .env.example to .env and fill in Postgres values)"
        )

    try:
        conn = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=CONNECT_TIMEOUT_S,
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable at {host}:{port}: {exc}")

    yield conn
    conn.close()
