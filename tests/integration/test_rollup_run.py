"""Behavioural proof of the rollup over the cleaned rows (needs a running InfluxDB; skipped if
none is reachable, runs in CI's integration job).

Two throwaway databases per test - one standing in for `dac_raw` (holding `readings_processed`),
one for `dac_rollup` - created and dropped in the fixture's teardown, so this never touches the
real `dac_raw` / `dac_rollup`. Core allows at most 5 databases, hence the teardown always drops.

M3 rewrite (decision 18): the source is `readings_processed`, rows of one policy version,
included columns over `verdict = 'accepted'`, a point with no `value_raw` counted in
`count_no_value`. The hand-computed bucket from M1 stays, expressed in verdicts.
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
import scripts.rollup as rollup_cli
from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.rollup_run import ROLLUP_MEASUREMENT, run_rollup

pytestmark = pytest.mark.influx

BASE = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)
EXPERIMENT = "EXP_TEST"


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
    """Idempotent: a 404 (already gone) is not an error - teardown must never raise over
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
def db_names():
    suffix = uuid.uuid4().hex[:8]
    return f"t2_raw_{suffix}", f"t2_rollup_{suffix}"


@pytest.fixture
def raw_and_rollup_dbs(influx_client, db_names):  # noqa: ARG001 - influx_client: skip-if-unreachable
    env = init_influx.load_env()
    host = env["INFLUX_HOST"]
    token = env["INFLUX_TOKEN"]
    raw_name, rollup_name = db_names

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


def processed(
    signal: str,
    at: datetime,
    value_raw: float | None,
    verdict: str = "accepted",
    quality: str = "GOOD",
    policy_version: str = POLICY_VERSION,
    experiment_id: str = EXPERIMENT,
) -> Point:
    """One `readings_processed` row as the cleaning writes it: `value_raw` absent when the raw
    point had no value, `value` present only when accepted."""
    point = (
        Point("readings_processed")
        .tag("experiment_id", experiment_id)
        .tag("source", "x")
        .tag("signal", signal)
        .tag("policy_version", policy_version)
        .field("quality", quality)
        .field("verdict", verdict)
        .field("reason", "" if verdict == "accepted" else "spike")
        .field("flags", "")
        .time(at)
    )
    if value_raw is not None:
        point = point.field("value_raw", value_raw)
        if verdict == "accepted":
            point = point.field("value", value_raw)
    return point


def _write_fixture(raw_client: InfluxDBClient3) -> None:
    """Two buckets on one series (`EXP_TEST/x/voltage`), with a gap between them.

    Bucket at minute 0: [1.0 accepted, 2.0 accepted, 100.0 excluded] -> count_all=3,
    count_included=2, mean/median over [1.0, 2.0] = 1.5.

    Bucket at minute 2 (minute 1 is a gap, no rows at all): 60 accepted rows
    [0.0 .. 59.0] -> count_all=60, count_included=60 - deliberately a dense minute right after
    an empty one, so the two buckets stay distinguishable by count_all.
    """
    points = [
        processed("voltage", BASE, 1.0),
        processed("voltage", BASE + timedelta(seconds=20), 2.0),
        processed("voltage", BASE + timedelta(seconds=40), 100.0, verdict="excluded"),
    ]
    points += [
        processed("voltage", BASE + timedelta(minutes=2, seconds=s), float(s)) for s in range(60)
    ]
    raw_client.write(record=points)


def _roll(raw_client, rollup_client, experiment_id: str = EXPERIMENT, **kwargs) -> int:
    return run_rollup(
        raw_client,
        rollup_client,
        kwargs.pop("start", BASE - timedelta(minutes=1)),
        kwargs.pop("end", BASE + timedelta(minutes=5)),
        kwargs.pop("policy_version", POLICY_VERSION),
        experiment_id=experiment_id,
        **kwargs,
    )


def test_rollup_matches_hand_computed_aggregate_and_distinguishes_a_gap(raw_and_rollup_dbs):
    """count_all=3/count_included=2 for the sparse bucket and count_all=60 for the dense one,
    computed by hand rather than read back from the thing under test - ADR-0006/ADR-0011's
    "demonstrable by query" standard.
    """
    raw_client, rollup_client = raw_and_rollup_dbs
    _write_fixture(raw_client)

    assert _roll(raw_client, rollup_client) == 2

    result = rollup_client.query(
        f"SELECT * FROM {ROLLUP_MEASUREMENT} ORDER BY time", language="sql"
    )
    rows = result.to_pylist()
    assert len(rows) == 2
    sparse, dense = rows

    assert sparse["count_all"] == 3
    assert sparse["count_included"] == 2
    assert sparse["count_no_value"] == 0
    assert sparse["count_good"] == 3  # the quality flag is independent of the verdict
    assert sparse["count_bad"] == 0
    assert sparse["count_uncertain"] == 0
    assert sparse["min_all"] == pytest.approx(1.0)
    assert sparse["max_all"] == pytest.approx(100.0)
    assert sparse["sum_all"] == pytest.approx(1.0 + 2.0 + 100.0)
    assert sparse["sumsq_all"] == pytest.approx(1.0 + 4.0 + 10000.0)
    assert sparse["mean"] == pytest.approx(1.5)  # over the two accepted values only
    assert sparse["median"] == pytest.approx(1.5)
    assert sparse["std"] == pytest.approx(0.5)  # population std of [1, 2]

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

    _roll(raw_client, rollup_client)

    result = rollup_client.query(f"SELECT policy_version FROM {ROLLUP_MEASUREMENT}", language="sql")
    assert result.column("policy_version").to_pylist() == [POLICY_VERSION, POLICY_VERSION]


def test_only_the_current_policy_version_is_read(raw_and_rollup_dbs):
    """Rows left by an older rule set sit beside the current ones as separate series; the
    rollup must not mix them in."""
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(
        record=[
            processed("voltage", BASE, 10.0),
            processed("voltage", BASE + timedelta(seconds=1), 20.0),
            processed("voltage", BASE + timedelta(seconds=2), 9999.0, policy_version="old-v0"),
            processed("voltage", BASE + timedelta(minutes=3), 5.0, policy_version="old-v0"),
        ]
    )

    assert _roll(raw_client, rollup_client) == 1

    rows = rollup_client.query(f"SELECT * FROM {ROLLUP_MEASUREMENT}", language="sql").to_pylist()
    assert len(rows) == 1
    assert rows[0]["count_all"] == 2
    assert rows[0]["max_all"] == pytest.approx(20.0)
    assert rows[0]["policy_version"] == POLICY_VERSION


def test_rerun_over_same_range_does_not_duplicate_rows(raw_and_rollup_dbs):
    raw_client, rollup_client = raw_and_rollup_dbs
    _write_fixture(raw_client)

    for _ in range(3):
        _roll(raw_client, rollup_client)

    result = rollup_client.query(f"SELECT COUNT(*) AS c FROM {ROLLUP_MEASUREMENT}", language="sql")
    assert result.column("c").to_pylist() == [2]


def test_only_the_asked_experiment_and_window_are_rolled_up(raw_and_rollup_dbs):
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(
        record=[
            processed("voltage", BASE, 1.0),
            processed("voltage", BASE, 7.0, experiment_id="EXP_OTHER"),
            processed("voltage", BASE + timedelta(minutes=10), 3.0),  # outside the window
        ]
    )

    written = _roll(raw_client, rollup_client, end=BASE + timedelta(minutes=5))

    assert written == 1
    rows = rollup_client.query(f"SELECT * FROM {ROLLUP_MEASUREMENT}", language="sql").to_pylist()
    assert [(r["experiment_id"], r["count_all"]) for r in rows] == [(EXPERIMENT, 1)]


def test_bucket_with_no_accepted_point_has_no_mean_std_median_but_keeps_min_max(
    raw_and_rollup_dbs,
):
    """Every point of a bucket excluded: the included columns are simply absent fields
    (InfluxDB has no null-field write), not zeros - and the `_all` columns are still populated.
    Documents the limit in `pipeline/rollup_run.py`: the first write of a bucket decides; a later
    write of the same key without a field keeps the old value.
    """
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(
        record=[
            processed("pressure", BASE, -5.0, verdict="excluded", quality="BAD"),
            processed(
                "pressure",
                BASE + timedelta(seconds=10),
                3.0,
                verdict="excluded",
                quality="UNCERTAIN",
            ),
            # A different series in the same minute with one accepted point, so the table's
            # mean/std/median columns exist in the schema at all (Core fixes a column's type
            # at its first write, per table; a column nothing ever wrote is not nullable, it
            # is absent - see `_row_to_point`).
            processed("voltage", BASE, 42.0),
        ]
    )

    _roll(raw_client, rollup_client, end=BASE + timedelta(minutes=1))

    result = rollup_client.query(
        f"SELECT signal, count_all, count_included, min_all, max_all, mean, std, median, "
        f"count_bad, count_uncertain FROM {ROLLUP_MEASUREMENT} ORDER BY signal",
        language="sql",
    )
    rows = {row["signal"]: row for row in result.to_pylist()}

    excluded = rows["pressure"]
    assert excluded["count_all"] == 2
    assert excluded["count_included"] == 0
    assert excluded["min_all"] == pytest.approx(-5.0)
    assert excluded["max_all"] == pytest.approx(3.0)
    assert excluded["count_bad"] == 1
    assert excluded["count_uncertain"] == 1
    assert excluded["mean"] is None
    assert excluded["std"] is None
    assert excluded["median"] is None

    included = rows["voltage"]
    assert included["count_included"] == 1
    assert included["mean"] == pytest.approx(42.0)


def test_bucket_without_any_raw_value_has_count_no_value_and_no_min_max(raw_and_rollup_dbs):
    """Every point of the bucket has no value_raw: the rollup does not crash, count_all is 0,
    count_no_value is the point count, min_all/max_all are absent (not 0)."""
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(
        record=[
            processed("current", BASE, None, verdict="excluded"),
            processed("current", BASE + timedelta(seconds=1), None, verdict="excluded"),
            processed("voltage", BASE, 42.0),  # gives the table its value columns
        ]
    )

    _roll(raw_client, rollup_client, end=BASE + timedelta(minutes=1))

    rows = {
        r["signal"]: r
        for r in rollup_client.query(
            f"SELECT * FROM {ROLLUP_MEASUREMENT}", language="sql"
        ).to_pylist()
    }
    empty = rows["current"]
    assert empty["count_no_value"] == 2
    assert empty["count_all"] == 0
    assert empty["sum_all"] == 0.0
    assert empty["count_included"] == 0
    assert empty["min_all"] is None
    assert empty["max_all"] is None
    assert empty["mean"] is None


def test_rerun_after_the_included_count_drops_keeps_the_old_mean_documented_limit(
    raw_and_rollup_dbs,
):
    """Documents the limit in `pipeline/rollup_run.py` as the code behaves today: if the rows
    of a bucket change under the SAME policy version (which cleaning never does - a rule change
    bumps the version), a re-run writes the new counts, but `mean` keeps its old value because
    a write without a field keeps the old one. The counts are right; `mean` must be read only
    where `count_included > 0`.
    """
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(record=[processed("voltage", BASE, 4.0)])
    _roll(raw_client, rollup_client, end=BASE + timedelta(minutes=1))

    raw_client.write(record=[processed("voltage", BASE, 4.0, verdict="excluded")])
    _roll(raw_client, rollup_client, end=BASE + timedelta(minutes=1))

    row = rollup_client.query(
        f"SELECT count_all, count_included, mean FROM {ROLLUP_MEASUREMENT}", language="sql"
    ).to_pylist()[0]
    assert row["count_all"] == 1
    assert row["count_included"] == 0  # the count is current
    assert row["mean"] == pytest.approx(4.0)  # the stale value the docstring warns about


def test_s3_26_the_cli_counts_a_point_with_no_value_instead_of_failing(
    raw_and_rollup_dbs, db_names, tmp_path, capsys
):
    """S3.26. One current bucket in a throwaway database, one row without value_raw: the
    rollup exits 0 and the bucket has count_no_value 1 and count_all over the other rows."""
    raw_client, rollup_client = raw_and_rollup_dbs
    raw_client.write(
        record=[
            processed("current", BASE + timedelta(seconds=10), 5.0),
            processed("current", BASE + timedelta(seconds=20), 7.0),
            processed("current", BASE + timedelta(seconds=30), 300.0, verdict="excluded"),
            processed("current", BASE + timedelta(seconds=40), None, verdict="excluded"),
        ]
    )
    experiments = tmp_path / "experiments.json"
    experiments.write_text(
        json.dumps(
            [
                {
                    "experiment_id": EXPERIMENT,
                    "start_time": "2026-03-02T00:00:00Z",
                    "end_time": "2026-03-02T02:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    code = rollup_cli.main(
        [
            "--database",
            db_names[0],
            "--rollup-database",
            db_names[1],
            "--experiments",
            str(experiments),
        ]
    )

    assert code == 0
    assert f"{EXPERIMENT}: 1 buckets written" in capsys.readouterr().out
    rows = rollup_client.query(f"SELECT * FROM {ROLLUP_MEASUREMENT}", language="sql").to_pylist()
    assert len(rows) == 1
    bucket = rows[0]
    assert bucket["count_no_value"] == 1
    assert bucket["count_all"] == 3  # the three rows that have a raw value
    assert bucket["count_included"] == 2
    assert bucket["mean"] == pytest.approx(6.0)
    assert bucket["max_all"] == pytest.approx(300.0)
    assert bucket["policy_version"] == POLICY_VERSION


def test_cli_refuses_a_missing_database_without_creating_it(raw_and_rollup_dbs, db_names, tmp_path):
    experiments = tmp_path / "experiments.json"
    experiments.write_text(
        json.dumps(
            [
                {
                    "experiment_id": EXPERIMENT,
                    "start_time": "2026-03-02T00:00:00Z",
                    "end_time": "2026-03-02T02:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    missing = f"t2_missing_{uuid.uuid4().hex[:8]}"

    code = rollup_cli.main(
        [
            "--database",
            db_names[0],
            "--rollup-database",
            missing,
            "--experiments",
            str(experiments),
        ]
    )

    assert code == 2
    env = init_influx.load_env()
    from pipeline.ingest_influx import list_databases

    assert missing not in list_databases(env["INFLUX_HOST"], env["INFLUX_TOKEN"])
