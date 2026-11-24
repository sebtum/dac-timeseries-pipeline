"""Unit tests for `pipeline.rollup.compute_rollup`, per ADR-0011 and M1.md T8.

Every test builds its own samples and predicate; nothing here reaches into
InfluxDB or any other I/O — that is the point of `rollup.py` being pure.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pyarrow as pa
import pytest

import scripts.rollup as rollup_cli
from pipeline.ingest_influx import DatabaseCheckFailed
from pipeline.rollup import Sample, compute_rollup
from pipeline.rollup_run import RollupFailed, is_accepted, run_rollup

T0 = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)


def sample(
    value: float | None, quality: str = "GOOD", ts: datetime = T0, verdict: str | None = None
) -> Sample:
    return Sample(timestamp=ts, value=value, quality=quality, verdict=verdict)


def good_only(s: Sample) -> bool:
    """The M1 placeholder predicate: UNCERTAIN excluded, same as BAD."""
    return s.quality == "GOOD"


# ---------------------------------------------------------------------------
# Hand-computed bucket
# ---------------------------------------------------------------------------


def test_hand_computed_bucket_all_good():
    """samples = [1.0, 2.0, 3.0], all GOOD.

    count_all = 3
    min_all = 1.0, max_all = 3.0
    sum_all = 1.0 + 2.0 + 3.0 = 6.0
    sumsq_all = 1.0 + 4.0 + 9.0 = 14.0
    mean = 6.0 / 3 = 2.0
    population variance = ((1-2)^2 + (2-2)^2 + (3-2)^2) / 3 = (1 + 0 + 1) / 3 = 0.6666...
    std = sqrt(2/3) = 0.816496580927726
    median = 2.0
    count_included = 3 (all pass good_only)
    count_good = 3, count_uncertain = 0, count_bad = 0
    """
    samples = [sample(1.0), sample(2.0), sample(3.0)]

    row = compute_rollup(samples, good_only, policy_version="v1")

    assert row.count_all == 3
    assert row.min_all == 1.0
    assert row.max_all == 3.0
    assert row.sum_all == pytest.approx(6.0)
    assert row.sumsq_all == pytest.approx(14.0)

    assert row.count_included == 3
    assert row.mean == pytest.approx(2.0)
    assert row.std == pytest.approx((2.0 / 3) ** 0.5)
    assert row.median == pytest.approx(2.0)

    assert row.count_good == 3
    assert row.count_uncertain == 0
    assert row.count_bad == 0
    assert row.count_good + row.count_uncertain + row.count_bad == row.count_all

    assert row.policy_version == "v1"


# ---------------------------------------------------------------------------
# Verdict-independent vs verdict-dependent columns under two predicates
# ---------------------------------------------------------------------------


def test_verdict_independent_columns_identical_across_predicates():
    samples = [
        sample(10.0, "GOOD"),
        sample(20.0, "UNCERTAIN"),
        sample(30.0, "BAD"),
        sample(40.0, "GOOD"),
    ]

    def include_good_only(s: Sample) -> bool:
        return s.quality == "GOOD"

    def include_good_and_uncertain(s: Sample) -> bool:
        return s.quality in ("GOOD", "UNCERTAIN")

    row_a = compute_rollup(samples, include_good_only, policy_version="v1")
    row_b = compute_rollup(samples, include_good_and_uncertain, policy_version="v1")

    # Verdict-independent: identical regardless of predicate.
    assert row_a.count_all == row_b.count_all == 4
    assert row_a.min_all == row_b.min_all == 10.0
    assert row_a.max_all == row_b.max_all == 40.0
    assert row_a.sum_all == row_b.sum_all == pytest.approx(100.0)
    assert row_a.sumsq_all == row_b.sumsq_all == pytest.approx(3000.0)

    # Composition counts are also predicate-independent.
    assert row_a.count_good == row_b.count_good == 2
    assert row_a.count_uncertain == row_b.count_uncertain == 1
    assert row_a.count_bad == row_b.count_bad == 1

    # Verdict-dependent: differ between the two predicates.
    assert row_a.count_included == 2  # only the two GOOD samples: 10.0, 40.0
    assert row_b.count_included == 3  # GOOD + UNCERTAIN: 10.0, 20.0, 40.0
    assert row_a.mean != row_b.mean
    assert row_a.median != row_b.median
    assert row_a.mean == pytest.approx(25.0)
    assert row_b.mean == pytest.approx(70.0 / 3)


# ---------------------------------------------------------------------------
# Composition invariant across a spread of test buckets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "samples",
    [
        [sample(1.0, "GOOD")],
        [sample(1.0, "GOOD"), sample(2.0, "UNCERTAIN"), sample(3.0, "BAD")],
        [sample(5.0, "BAD"), sample(6.0, "BAD")],
        [sample(v, "GOOD") for v in range(10)],
    ],
)
def test_composition_counts_partition_count_all(samples):
    row = compute_rollup(samples, good_only, policy_version="v1")
    assert row.count_good + row.count_uncertain + row.count_bad == row.count_all


# ---------------------------------------------------------------------------
# n=1 bucket: std must be exactly 0.0, never an error or None
# ---------------------------------------------------------------------------


def test_n1_bucket_std_is_zero_not_error_not_none():
    samples = [sample(42.0, "GOOD")]

    row = compute_rollup(samples, good_only, policy_version="v1")

    assert row.count_included == 1
    assert row.std == 0.0
    assert row.std is not None
    assert row.mean == pytest.approx(42.0)
    assert row.median == pytest.approx(42.0)
    assert row.count_all == 1
    assert row.count_good == 1
    assert row.count_uncertain == 0
    assert row.count_bad == 0


# ---------------------------------------------------------------------------
# All samples excluded by the predicate
# ---------------------------------------------------------------------------


def test_all_excluded_bucket_verdict_dependent_columns_are_none():
    samples = [sample(-5.0, "BAD"), sample(100.0, "UNCERTAIN"), sample(3.0, "BAD")]

    row = compute_rollup(samples, good_only, policy_version="v1")

    assert row.count_included == 0
    assert row.mean is None
    assert row.std is None
    assert row.median is None

    # Verdict-independent columns still populated from ALL samples.
    assert row.count_all == 3
    assert row.min_all == -5.0
    assert row.max_all == 100.0
    assert row.sum_all == pytest.approx(98.0)
    assert row.sumsq_all == pytest.approx(25.0 + 10000.0 + 9.0)

    assert row.count_good == 0
    assert row.count_uncertain == 1
    assert row.count_bad == 2
    assert row.count_good + row.count_uncertain + row.count_bad == row.count_all


# ---------------------------------------------------------------------------
# Sufficient-statistics / pooling claim
# ---------------------------------------------------------------------------


def test_pooling_two_buckets_reproduces_aggregate_over_the_union():
    """ADR-0011's permanence argument: (count_all, sum_all, sumsq_all) are
    sufficient statistics, so pooling two adjacent buckets' values must
    reproduce what compute_rollup would return for their union in a single
    call — this asserts that claim rather than just citing it.
    """
    bucket_1 = [sample(1.0, "GOOD"), sample(2.0, "BAD")]
    bucket_2 = [sample(3.0, "GOOD"), sample(4.0, "UNCERTAIN"), sample(5.0, "GOOD")]

    row_1 = compute_rollup(bucket_1, good_only, policy_version="v1")
    row_2 = compute_rollup(bucket_2, good_only, policy_version="v1")

    pooled_count_all = row_1.count_all + row_2.count_all
    pooled_sum_all = row_1.sum_all + row_2.sum_all
    pooled_sumsq_all = row_1.sumsq_all + row_2.sumsq_all

    union_row = compute_rollup(bucket_1 + bucket_2, good_only, policy_version="v1")

    assert pooled_count_all == union_row.count_all
    assert pooled_sum_all == pytest.approx(union_row.sum_all)
    assert pooled_sumsq_all == pytest.approx(union_row.sumsq_all)

    # min_all/max_all pool too, via min()/max() rather than addition.
    assert min(row_1.min_all, row_2.min_all) == union_row.min_all
    assert max(row_1.max_all, row_2.max_all) == union_row.max_all


# ---------------------------------------------------------------------------
# policy_version is required, never silently defaulted
# ---------------------------------------------------------------------------


def test_policy_version_is_required():
    samples = [sample(1.0, "GOOD")]

    with pytest.raises(TypeError):
        compute_rollup(samples, good_only)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Empty bucket is rejected — bucket existence is the caller's decision
# ---------------------------------------------------------------------------


def test_empty_samples_raises_value_error():
    with pytest.raises(ValueError):
        compute_rollup([], good_only, policy_version="v1")


def test_unrecognised_quality_label_raises_value_error():
    with pytest.raises(ValueError):
        compute_rollup([sample(1.0, "SUSPICIOUS")], good_only, policy_version="v1")


# ---------------------------------------------------------------------------
# M3: points with no value, and the verdict predicate
# ---------------------------------------------------------------------------


def test_verdict_predicate_includes_accepted_only():
    assert is_accepted(sample(1.0, verdict="accepted"))
    assert not is_accepted(sample(1.0, verdict="excluded"))
    assert not is_accepted(sample(1.0))  # no verdict is never silently accepted


def test_included_columns_follow_the_verdict_not_the_quality_flag():
    """A GOOD-flagged point the cleaning excluded (spike) is out of the included columns but
    in the _all columns; a BAD-flagged point is in count_bad whatever the verdict says.

    values 10 (accepted), 20 (excluded GOOD, spike), 30 (excluded BAD): count_all 3,
    sum_all 60, count_included 1, mean 10, count_good 2, count_bad 1.
    """
    samples = [
        sample(10.0, "GOOD", verdict="accepted"),
        sample(20.0, "GOOD", verdict="excluded"),
        sample(30.0, "BAD", verdict="excluded"),
    ]

    row = compute_rollup(samples, is_accepted, policy_version="m3-v1")

    assert row.count_all == 3
    assert row.min_all == 10.0
    assert row.max_all == 30.0
    assert row.sum_all == pytest.approx(60.0)
    assert row.count_included == 1
    assert row.mean == pytest.approx(10.0)
    assert row.std == 0.0
    assert row.median == pytest.approx(10.0)
    assert row.count_good == 2
    assert row.count_bad == 1
    assert row.count_no_value == 0


def test_a_point_with_no_value_is_counted_not_crashed_on():
    """Four points: 1.0 accepted, 3.0 accepted, 100.0 excluded, one with no value (excluded,
    reason no_value). Value columns see the three raw values: count_all 3, min 1, max 100,
    sum 104, sumsq 1 + 9 + 10000 = 10010. Included: [1, 3] -> mean 2, median 2, pstdev 1.
    count_no_value 1. Quality counts still partition all four points.
    """
    samples = [
        sample(1.0, verdict="accepted"),
        sample(3.0, verdict="accepted"),
        sample(100.0, verdict="excluded"),
        sample(None, "GOOD", verdict="excluded"),
    ]

    row = compute_rollup(samples, is_accepted, policy_version="m3-v1")

    assert row.count_no_value == 1
    assert row.count_all == 3
    assert row.min_all == 1.0
    assert row.max_all == 100.0
    assert row.sum_all == pytest.approx(104.0)
    assert row.sumsq_all == pytest.approx(10010.0)
    assert row.count_included == 2
    assert row.mean == pytest.approx(2.0)
    assert row.std == pytest.approx(1.0)
    assert row.median == pytest.approx(2.0)
    assert row.count_good + row.count_uncertain + row.count_bad == 4
    assert row.count_all + row.count_no_value == 4


def test_the_predicate_is_not_asked_about_a_point_with_no_value():
    seen: list[Sample] = []

    def include_everything(s: Sample) -> bool:
        seen.append(s)
        return True

    row = compute_rollup(
        [sample(None, "BAD"), sample(2.0, "GOOD")], include_everything, policy_version="v1"
    )

    assert [s.value for s in seen] == [2.0]
    assert row.count_included == 1
    assert row.mean == pytest.approx(2.0)


def test_bucket_with_no_raw_value_at_all_does_not_crash():
    """Every point has no value: count_all 0, sum/sumsq are the empty sum 0.0 (so pooling stays
    correct), min/max are None (nothing to take a minimum of), mean/std/median None.
    """
    samples = [sample(None, "BAD", verdict="excluded"), sample(None, "GOOD", verdict="excluded")]

    row = compute_rollup(samples, is_accepted, policy_version="m3-v1")

    assert row.count_no_value == 2
    assert row.count_all == 0
    assert row.min_all is None
    assert row.max_all is None
    assert row.sum_all == 0.0
    assert row.sumsq_all == 0.0
    assert row.count_included == 0
    assert row.mean is None
    assert row.std is None
    assert row.median is None
    assert row.count_good == 1
    assert row.count_bad == 1


def test_no_value_bucket_pools_with_a_valued_bucket():
    """The empty sum is 0.0, so pooling a no-value bucket with a normal one reproduces the
    normal one's sufficient statistics."""
    empty = compute_rollup([sample(None)], is_accepted, policy_version="v1")
    normal = compute_rollup([sample(4.0, verdict="accepted")], is_accepted, policy_version="v1")

    assert empty.count_all + normal.count_all == 1
    assert empty.sum_all + normal.sum_all == pytest.approx(4.0)
    assert empty.sumsq_all + normal.sumsq_all == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# CLI: exit codes with fake gateways (nothing here needs InfluxDB)
# ---------------------------------------------------------------------------

_EXPERIMENT = {
    "experiment_id": "EXP_T",
    "start_time": "2026-05-04T08:00:00Z",
    "end_time": "2026-05-04T08:10:00Z",
}


class FakeClient:
    """Stands in for `InfluxDBClient3`; records writes, fails on demand."""

    def __init__(self, database: str, log: dict, *, tables=("readings_processed",)):
        self.database = database
        self.log = log
        self.tables = list(tables)
        self.closed = False

    def query(self, sql, language="sql", mode="all", query_parameters=None):
        if "information_schema" in sql:
            return pa.table({"table_name": self.tables})
        if self.log.get("fail_query"):
            raise RuntimeError("query boom")
        rows = self.log.get("rows", [])
        if not rows:
            return iter([])
        names = ["experiment_id", "source", "signal", "time", "value_raw", "quality", "verdict"]
        columns = {
            name: list(col) for name, col in zip(names, zip(*rows, strict=True), strict=True)
        }
        columns["value_raw"] = pa.array(columns["value_raw"], type=pa.float64())
        return iter([pa.RecordBatch.from_pydict(columns)])

    def write(self, record):
        if self.log.get("fail_write"):
            raise RuntimeError("write boom")
        self.log.setdefault("writes", []).append((self.database, record))

    def close(self):
        self.closed = True


def _config(tmp_path, experiments=True):
    path = tmp_path / "experiments.json"
    if experiments:
        path.write_text(json.dumps([_EXPERIMENT]), encoding="utf-8")
    return rollup_cli.Config(database="raw_t", rollup_database="roll_t", experiments_path=path)


def _deps(log, databases=("raw_t", "roll_t"), tables=("readings_processed",)):
    def factory(host, token, database):
        return FakeClient(database, log, tables=tables)

    return rollup_cli.Deps(
        list_databases=lambda host, token: list(databases),
        client_factory=factory,
        env={"INFLUX_HOST": "http://x", "INFLUX_TOKEN": "t"},
        policy_version="m3-v1",
    )


def _row(second: int, value, verdict="accepted"):
    ts = datetime(2026, 5, 4, 8, 0, second, tzinfo=UTC)
    return ("EXP_T", "x", "voltage", ts, value, "GOOD", verdict)


def test_cli_exit_0_writes_and_prints_buckets_per_experiment(tmp_path, capsys):
    log = {"rows": [_row(1, 1.0), _row(2, None, "excluded"), _row(3, 3.0)]}

    code = rollup_cli.run(_config(tmp_path), _deps(log))

    assert code == 0
    assert [db for db, _ in log["writes"]] == ["roll_t"]  # never the raw database
    assert "EXP_T: 1 buckets written" in capsys.readouterr().out


def test_cli_exit_2_when_the_raw_database_is_missing(tmp_path):
    log: dict = {}
    code = rollup_cli.run(_config(tmp_path), _deps(log, databases=("roll_t",)))
    assert code == 2
    assert "writes" not in log


def test_cli_exit_2_when_the_rollup_database_is_missing_and_it_is_not_created(tmp_path):
    log: dict = {}
    opened: list[str] = []

    def factory(host, token, database):
        opened.append(database)
        return FakeClient(database, log)

    deps = _deps(log, databases=("raw_t",))
    deps.client_factory = factory
    code = rollup_cli.run(_config(tmp_path), deps)

    assert code == 2
    assert opened == []  # refused before any client was opened


def test_cli_exit_2_when_readings_processed_is_missing(tmp_path):
    log: dict = {}
    code = rollup_cli.run(_config(tmp_path), _deps(log, tables=("readings_numeric",)))
    assert code == 2
    assert "writes" not in log


def test_cli_exit_2_when_the_experiments_file_is_unreadable(tmp_path):
    log: dict = {}
    assert rollup_cli.run(_config(tmp_path, experiments=False), _deps(log)) == 2
    (tmp_path / "experiments.json").write_text("not json", encoding="utf-8")
    assert rollup_cli.run(_config(tmp_path, experiments=False), _deps(log)) == 2


def test_cli_exit_2_when_influx_is_not_reachable(tmp_path):
    def unreachable(host, token):
        raise DatabaseCheckFailed("unreachable", "down")

    deps = _deps({})
    deps.list_databases = unreachable
    assert rollup_cli.run(_config(tmp_path), deps) == 2


def test_cli_exit_2_when_no_row_of_the_policy_version_exists(tmp_path):
    log: dict = {"rows": []}
    assert rollup_cli.run(_config(tmp_path), _deps(log)) == 2
    assert "writes" not in log


def test_cli_exit_3_when_a_query_fails(tmp_path):
    assert rollup_cli.run(_config(tmp_path), _deps({"fail_query": True})) == 3


def test_cli_exit_3_when_a_write_fails(tmp_path):
    log = {"rows": [_row(1, 1.0)], "fail_write": True}
    assert rollup_cli.run(_config(tmp_path), _deps(log)) == 3


def test_run_rollup_wraps_failures_in_rollup_failed():
    log = {"fail_query": True}
    with pytest.raises(RollupFailed) as info:
        run_rollup(
            FakeClient("a", log),
            FakeClient("b", log),
            T0,
            T0,
            "m3-v1",
            experiment_id="EXP_T",
        )
    assert info.value.stage == "query"
