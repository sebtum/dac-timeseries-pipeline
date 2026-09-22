"""Unit tests for `pipeline.rollup.compute_rollup`, per ADR-0011 and M1.md T8.

Every test builds its own samples and predicate; nothing here reaches into
InfluxDB or any other I/O — that is the point of `rollup.py` being pure.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipeline.rollup import Sample, compute_rollup

T0 = datetime(2026, 3, 2, 0, 0, 0, tzinfo=UTC)


def sample(value: float, quality: str = "GOOD", ts: datetime = T0) -> Sample:
    return Sample(timestamp=ts, value=value, quality=quality)


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
