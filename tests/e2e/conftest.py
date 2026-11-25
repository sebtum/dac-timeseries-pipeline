"""Fixtures for the end-to-end tests (helpers: `tests/e2e/helpers.py`, `grafana_helpers.py`).

Each fixture creates one empty throwaway database and drops it afterwards, so a test never
touches `dac_raw`. Both depend on the session `influx_client` fixture, which skips when no
InfluxDB is reachable.
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.grafana_helpers import require_grafana
from tests.e2e.helpers import create_database, drop_database


@pytest.fixture(scope="session")
def grafana():
    """A `GrafanaClient` for the Grafana of `.env`; skips (never fails) when it is unreachable.

    Tests that need it carry the `grafana` marker (pyproject.toml). Bring Grafana up with
    `python scripts/verify_stack.py up` (private stack) or `docker compose up -d grafana`.
    """
    return require_grafana()


@pytest.fixture
def scratch_db(influx_client):  # noqa: ARG001 - for skip-if-unreachable only
    name = f"m2_e2e_{uuid.uuid4().hex[:10]}"
    create_database(name)
    try:
        yield name
    finally:
        drop_database(name)


@pytest.fixture(scope="module")
def module_db(influx_client):  # noqa: ARG001
    name = f"m2_e2e_{uuid.uuid4().hex[:10]}"
    create_database(name)
    try:
        yield name
    finally:
        drop_database(name)
