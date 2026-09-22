"""Behavioural proof of InfluxDB 3 Core retention (V5), per `docs/plans/M1.md` T5.

Deliberately behavioural, not configuration-based: `influxdb3 show databases` and `GET
/api/v3/configure/database` reported no retention period back on Core 3.7.0
(https://github.com/influxdata/influxdb/issues/27082), so asserting on either would risk
silently asserting nothing. This creates a throwaway database with a **1-hour** retention
period, writes one point 2 hours old and one 5 minutes old, and asserts on the query
result which one comes back — proven directly against `influxdb:3.11.2-core`: the expired
point is invisible immediately at query time, no wait needed (matches
`docs/ROADMAP.md`'s C-06 note that Core filters expired points at query time, not on a
delayed sweep).

Teardown is in the fixture (`finally`, not the test body) so the throwaway database is
dropped even when the test fails — T4's handoff confirmed a deleted database's slot is
reclaimed immediately on this build (influxdata/influxdb#25701 does not reproduce on
3.11.2), so this is safe to repeat indefinitely across local runs and CI.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from influxdb_client_3 import InfluxDBClient3, Point

import scripts.init_influx as init_influx

pytestmark = pytest.mark.influx


def _create_database(host: str, token: str, name: str, retention: str) -> None:
    req = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database",
        data=json.dumps({"db": name, "retention_period": retention}).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        resp.read()


def _delete_database(host: str, token: str, name: str) -> None:
    """Idempotent: a 404 (already gone) is not an error — teardown must never raise over
    a database that failed to be created in the first place.
    """
    req = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database?db={name}",
        method="DELETE",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise


@pytest.fixture
def throwaway_retention_db(influx_client):  # noqa: ARG001 - depended on for skip-if-unreachable only
    env = init_influx.load_env()
    host = env["INFLUX_HOST"]
    token = env["INFLUX_TOKEN"]
    name = f"t5_retention_{uuid.uuid4().hex[:8]}"

    _create_database(host, token, name, retention="1h")
    try:
        yield host, token, name
    finally:
        _delete_database(host, token, name)


def test_retention_hides_expired_points_but_keeps_fresh_ones(throwaway_retention_db):
    host, token, name = throwaway_retention_db
    client = InfluxDBClient3(host=host, token=token, database=name)

    now = datetime.now(UTC)
    expired = now - timedelta(hours=2)
    fresh = now - timedelta(minutes=5)

    client.write(
        record=[
            Point("probe").tag("k", "v").field("value", 1.0).time(expired),
            Point("probe").tag("k", "v").field("value", 2.0).time(fresh),
        ]
    )

    result = client.query("SELECT value FROM probe ORDER BY time", language="sql")
    values = result.column("value").to_pylist()

    assert values == [2.0]
    client.close()
