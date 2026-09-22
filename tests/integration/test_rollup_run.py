"""Behavioural proof of the rollup driver (V3, end-to-end half), per `docs/plans/M1.md` T9.

Two throwaway databases per test — one standing in for `dac_raw`, one for `dac_rollup`
— created and dropped per test (teardown in the fixture, T5's pattern), so this never
touches the real `dac_raw`/`dac_rollup` or accounts for fixture rows in M2's row-count
reconciliation.
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
from pipeline.rollup_run import ROLLUP_MEASUREMENT, run_rollup

pytestmark = pytest.mark.influx

BASE = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)
POLICY_VERSION = "m1-placeholder-v1"


def good_only(sample) -> bool:
    """The M1 placeholder predicate: UNCERTAIN excluded, same as BAD."""
    return sample.quality == "GOOD"


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
def raw_and_rollup_dbs(influx_client):  # noqa: ARG001 - depended on for skip-if-unreachable only
    env = init_influx.load_env()
    host = env["INFLUX_HOST"]
    token = env["INFLUX_TOKEN"]
    suffix = uuid.uuid4().hex[:8]
    raw_name = f"t9_raw_{suffix}"
    rollup_name = f"t9_rollup_{suffix}"

    _create_database(host, token, raw_name)
    _create_database(host, token, rollup_name)
    try:
        raw_client = InfluxDBClient3(host=host, token=token, database=raw_name)
        rollup_client = InfluxDBClient3(host=host, token=token, database=rollup_name)
        try:
            yield raw_client, rollup_client
        finally:
            raw_client.close()
            rollup_client.close()
    finally:
        _delete_database(host, token, raw_name)
        _delete_database(host, token, rollup_name)


def _write_fixture(raw_client: InfluxDBClient3) -> None:
    """Two buckets on one series (`EXP_TEST/x/voltage`), with a gap between them, plus
    one `readings_state` point that must never reach the rollup.

    Bucket at minute 0: [1.0 GOOD, 2.0 GOOD, 100.0 BAD] -> count_all=3, count_included=2
    (100.0 excluded by the GOOD-only placeholder), mean/std/median over [1.0, 2.0].

    Bucket at minute 2 (minute 1 is a gap, no samples at all): 60 GOOD samples
    [0.0 .. 59.0] -> count_all=60, count_included=60 -- deliberately a dense minute
    right after an empty one, so the two buckets stay distinguishable by count_all.
    """
    points = [
        Point("readings_numeric")
        .tag("experiment_id", "EXP_TEST")
        .tag("source", "x")
        .tag("signal", "voltage")
        .field("value", 1.0)
        .field("quality", "GOOD")
        .time(BASE),
        Point("readings_numeric")
        .tag("experiment_id", "EXP_TEST")
        .tag("source", "x")
        .tag("signal", "voltage")
        .field("value", 2.0)
        .field("quality", "GOOD")
        .time(BASE + timedelta(seconds=20)),
        Point("readings_numeric")
        .tag("experiment_id", "EXP_TEST")
        .tag("source", "x")
        .tag("signal", "voltage")
        .field("value", 100.0)
        .field("quality", "BAD")
        .time(BASE + timedelta(seconds=40)),
    ]
    points += [
        Point("readings_numeric")
        .tag("experiment_id", "EXP_TEST")
        .tag("source", "x")
        .tag("signal", "voltage")
        .field("value", float(s))
        .field("quality", "GOOD")
        .time(BASE + timedelta(minutes=2, seconds=s))
        for s in range(60)
    ]
    points.append(
        Point("readings_state")
        .tag("experiment_id", "EXP_TEST")
        .tag("source", "plant")
        .tag("signal", "process_state")
        .field("value", "STEADY_STATE")
        .field("quality", "GOOD")
        .time(BASE)
    )
    raw_client.write(record=points)


def test_rollup_matches_hand_computed_aggregate_and_distinguishes_a_gap(
    raw_and_rollup_dbs,
):
    """count_all=3/count_included=2 for the sparse bucket and count_all=60 for the
    dense one, computed by hand rather than read back from the thing under test --
    ADR-0006/ADR-0011's "demonstrable by query" standard, same as T5.
    """
    raw_client, rollup_client = raw_and_rollup_dbs
    _write_fixture(raw_client)

    written = run_rollup(
        raw_client,
        rollup_client,
        BASE - timedelta(minutes=1),
        BASE + timedelta(minutes=5),
        good_only,
        POLICY_VERSION,
    )
    assert written == 2

    result = rollup_client.query(
        f"SELECT * FROM {ROLLUP_MEASUREMENT} ORDER BY time", language="sql"
    )
    rows = result.to_pylist()
    assert len(rows) == 2

    sparse, dense = rows

    assert sparse["count_all"] == 3
    assert sparse["count_included"] == 2
    assert sparse["count_good"] == 2
    assert sparse["count_bad"] == 1
    assert sparse["count_uncertain"] == 0
    assert sparse["min_all"] == pytest.approx(1.0)
    assert sparse["max_all"] == pytest.approx(100.0)
    assert sparse["sum_all"] == pytest.approx(1.0 + 2.0 + 100.0)
    assert sparse["mean"] == pytest.approx(1.5)  # mean of the two GOOD-only values
    assert sparse["median"] == pytest.approx(1.5)

    # The gap-adjacent dense bucket: 60 samples, none excluded.
    assert dense["count_all"] == 60
    assert dense["count_included"] == 60
    assert dense["min_all"] == pytest.approx(0.0)
    assert dense["max_all"] == pytest.approx(59.0)
    assert dense["mean"] == pytest.approx(29.5)

    # No empty-bucket row was invented for the gap minute in between.
    times = result.column("time").to_pylist()
    assert BASE + timedelta(minutes=1) not in times


def test_policy_version_is_stamped_on_every_written_row(raw_and_rollup_dbs):
    raw_client, rollup_client = raw_and_rollup_dbs
    _write_fixture(raw_client)

    run_rollup(
        raw_client,
        rollup_client,
        BASE - timedelta(minutes=1),
        BASE + timedelta(minutes=5),
        good_only,
        POLICY_VERSION,
    )

    result = rollup_client.query(f"SELECT policy_version FROM {ROLLUP_MEASUREMENT}", language="sql")
    assert result.column("policy_version").to_pylist() == [POLICY_VERSION, POLICY_VERSION]


def test_rerun_over_same_range_does_not_duplicate_rows(raw_and_rollup_dbs):
    raw_client, rollup_client = raw_and_rollup_dbs
    _write_fixture(raw_client)

    args = (
        raw_client,
        rollup_client,
        BASE - timedelta(minutes=1),
        BASE + timedelta(minutes=5),
        good_only,
        POLICY_VERSION,
    )
    run_rollup(*args)
    run_rollup(*args)
    run_rollup(*args)

    result = rollup_client.query(f"SELECT COUNT(*) AS c FROM {ROLLUP_MEASUREMENT}", language="sql")
    assert result.column("c").to_pylist() == [2]


def test_no_readings_state_data_reaches_the_rollup(raw_and_rollup_dbs):
    raw_client, rollup_client = raw_and_rollup_dbs
    _write_fixture(raw_client)

    run_rollup(
        raw_client,
        rollup_client,
        BASE - timedelta(minutes=1),
        BASE + timedelta(minutes=5),
        good_only,
        POLICY_VERSION,
    )

    result = rollup_client.query(
        f"SELECT DISTINCT signal FROM {ROLLUP_MEASUREMENT}", language="sql"
    )
    assert result.column("signal").to_pylist() == ["voltage"]


def test_bucket_with_every_sample_excluded_has_no_mean_std_median_but_keeps_min_max(
    raw_and_rollup_dbs,
):
    """A bucket where the predicate excludes every sample: verdict-dependent columns
    are simply absent fields (InfluxDB has no null-field write), not zeros -- and the
    verdict-independent columns (count_all, min_all, max_all) are still populated,
    same invariant T8's unit test asserts on the pure function directly.
    """
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(
        record=[
            # Minute 0, on 'pressure': nothing here passes the GOOD-only predicate.
            Point("readings_numeric")
            .tag("experiment_id", "EXP_TEST")
            .tag("source", "x")
            .tag("signal", "pressure")
            .field("value", -5.0)
            .field("quality", "BAD")
            .time(BASE),
            Point("readings_numeric")
            .tag("experiment_id", "EXP_TEST")
            .tag("source", "x")
            .tag("signal", "pressure")
            .field("value", 3.0)
            .field("quality", "UNCERTAIN")
            .time(BASE + timedelta(seconds=10)),
            # Minute 0, on a different series ('voltage'): one GOOD sample, so the
            # table's mean/std/median columns exist in the schema at all (Core fixes
            # a column's type at its first write, per table -- a column nothing has
            # ever written to isn't nullable, it's simply absent, see _row_to_point).
            Point("readings_numeric")
            .tag("experiment_id", "EXP_TEST")
            .tag("source", "x")
            .tag("signal", "voltage")
            .field("value", 42.0)
            .field("quality", "GOOD")
            .time(BASE),
        ]
    )

    run_rollup(
        raw_client,
        rollup_client,
        BASE - timedelta(minutes=1),
        BASE + timedelta(minutes=1),
        good_only,
        POLICY_VERSION,
    )

    result = rollup_client.query(
        f"SELECT signal, count_all, count_included, min_all, max_all, mean, std, median "
        f"FROM {ROLLUP_MEASUREMENT} ORDER BY signal",
        language="sql",
    )
    rows = {row["signal"]: row for row in result.to_pylist()}

    excluded = rows["pressure"]
    assert excluded["count_all"] == 2
    assert excluded["count_included"] == 0
    assert excluded["min_all"] == pytest.approx(-5.0)
    assert excluded["max_all"] == pytest.approx(3.0)
    assert excluded["mean"] is None
    assert excluded["std"] is None
    assert excluded["median"] is None

    included = rows["voltage"]
    assert included["count_included"] == 1
    assert included["mean"] == pytest.approx(42.0)
