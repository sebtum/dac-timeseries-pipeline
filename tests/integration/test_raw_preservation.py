"""Behavioural proof that raw values are preserved unchanged (V2), per `docs/plans/M1.md` T5.

ADR-0006's "raw values must be preserved unchanged" is stated as "demonstrable by query,
not asserted" — this exercises that before ingestion (M2) exists, against a throwaway
database carrying the same `readings_numeric` / `readings_state` schema ADR-0006 settled
for `dac_raw`. A high-precision float and a negative value cover the numeric table; both
categorical signals (`process_state`, `valve_state`) as literal strings cover the state
table and are the specific case ADR-0006 rejected integer-encoding to avoid — round-
tripping them as strings is what would fail if anything upstream ever did that encoding.

Uses a throwaway database (created and dropped per test, teardown in the fixture) rather
than writing into the real `dac_raw`, matching `test_retention.py`'s pattern: M2's row-
count reconciliation (CSV -> Influx per experiment/signal) should never have to account
for fixture rows that aren't in the raw CSV.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

import pytest
from influxdb_client_3 import InfluxDBClient3, Point

import scripts.init_influx as init_influx

pytestmark = pytest.mark.influx


def _create_database(host: str, token: str, name: str) -> None:
    req = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database",
        data=json.dumps({"db": name}).encode("utf-8"),
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
def throwaway_db(influx_client):  # noqa: ARG001 - depended on for skip-if-unreachable only
    env = init_influx.load_env()
    host = env["INFLUX_HOST"]
    token = env["INFLUX_TOKEN"]
    name = f"t5_raw_preservation_{uuid.uuid4().hex[:8]}"

    _create_database(host, token, name)
    try:
        yield host, token, name
    finally:
        _delete_database(host, token, name)


def test_numeric_value_round_trips_at_full_precision_including_negative(throwaway_db):
    host, token, name = throwaway_db
    client = InfluxDBClient3(host=host, token=token, database=name)

    ts = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
    written_value = -3.14159265358979

    client.write(
        record=Point("readings_numeric")
        .tag("experiment_id", "EXP_TEST")
        .tag("source", "hydrolyzer")
        .tag("signal", "voltage")
        .field("value", written_value)
        .field("quality", "GOOD")
        .time(ts)
    )

    result = client.query("SELECT value, quality FROM readings_numeric", language="sql")
    assert result.column("value").to_pylist() == [written_value]
    assert result.column("quality").to_pylist() == ["GOOD"]
    client.close()


def test_categorical_state_round_trips_as_a_literal_string_not_an_integer(throwaway_db):
    """The case ADR-0006 rejected integer-encoding to avoid: if `process_state` or
    `valve_state` were ever coerced to a numeric code, this would come back as an int or
    fail to parse — not as the literal string that was written.
    """
    host, token, name = throwaway_db
    client = InfluxDBClient3(host=host, token=token, database=name)

    ts = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)

    client.write(
        record=[
            Point("readings_state")
            .tag("experiment_id", "EXP_TEST")
            .tag("source", "plant")
            .tag("signal", "process_state")
            .field("value", "STEADY_STATE")
            .field("quality", "GOOD")
            .time(ts),
            Point("readings_state")
            .tag("experiment_id", "EXP_TEST")
            .tag("source", "plant")
            .tag("signal", "valve_state")
            .field("value", "OPEN")
            .field("quality", "GOOD")
            .time(ts),
        ]
    )

    result = client.query(
        "SELECT signal, value FROM readings_state ORDER BY signal", language="sql"
    )
    signals = result.column("signal").to_pylist()
    values = result.column("value").to_pylist()

    assert dict(zip(signals, values, strict=True)) == {
        "process_state": "STEADY_STATE",
        "valve_state": "OPEN",
    }
    assert all(isinstance(v, str) for v in values)
    client.close()
