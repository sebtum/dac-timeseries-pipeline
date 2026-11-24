"""Pure aggregation of one rollup bucket's samples, per ADR-0011.

`compute_rollup` takes the samples already grouped into one
`(experiment_id, source, signal, bucket_start)` bucket and returns
ADR-0011's rollup column set. It does no I/O, imports nothing from
InfluxDB, and does not perform the bucketing/time-flooring itself —
that grouping is the caller's job (T9). This module only knows how to
turn "here is a bucket's worth of samples" into the stored aggregate.

Column split, from ADR-0011:

  verdict-independent (over ALL samples that have a value, regardless of the predicate):
    count_all, min_all, max_all, sum_all, sumsq_all
  points with no value (M3 addendum, below):
    count_no_value
  verdict-dependent (over samples the predicate includes only):
    count_included, mean, std, median
  composition (counts by acquisition-time quality label, independent
  of the predicate):
    count_good, count_uncertain, count_bad
  provenance:
    policy_version

The inclusion predicate is injected, not hardcoded. M1 passed a placeholder
(`quality == 'GOOD'`); M3 passes the cleaning pipeline's real verdict
(`verdict == 'accepted'`, see `pipeline/rollup_run.py`). This module must not know or
assume what the predicate is - it only calls it.

M3 addendum to ADR-0011 (not a reversal): a point can have no value (the raw reading was
empty, so `readings_processed` has no `value_raw`). `Sample.value` is then `None`. Such a
point:
  - is counted in the new column `count_no_value`;
  - is left out of every value column: `count_all`, `min_all`, `max_all`, `sum_all`,
    `sumsq_all` and the included columns work over points that have a raw value only;
  - still counts in `count_good` / `count_uncertain` / `count_bad`, which partition the
    bucket by acquisition-time quality label whatever the value;
  - never reaches the predicate-based columns even if the predicate says yes
    (`count_included` is the number of included samples that have a value).
So `count_all + count_no_value` is the number of points in the bucket, and
`count_good + count_uncertain + count_bad` equals that sum.

A bucket with no raw value at all (every point has no value): `count_all` is 0, `sum_all`
and `sumsq_all` are 0.0 (the empty sum, so pooling buckets stays correct), and `min_all` /
`max_all` are `None` (there is no smallest of nothing). The driver leaves `None` fields out
of the written point. `mean` / `std` / `median` are `None` whenever `count_included` is 0.

`std` is **population** standard deviation (denominator n, not n-1).
`statistics.pstdev` gives this directly, including the n=1 case
(`pstdev([x]) == 0.0`, no ZeroDivisionError) - the reason ADR-0011
chose the population convention, since all four ambient signals hit
n=1 at 1-minute buckets and sample std (n-1) would be undefined there.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

QUALITY_LABELS = ("GOOD", "UNCERTAIN", "BAD")


@dataclass(frozen=True)
class Sample:
    """One raw reading belonging to a bucket.

    `timestamp` is carried through for traceability (it is what the
    caller used to assign this sample to its bucket) but is not used
    in the aggregation math below — this function trusts the caller's
    grouping and does no bucketing of its own.

    `value` is the raw value (`value_raw` in `readings_processed`), or `None` when the point
    has no value. `verdict` (`accepted` | `excluded`) is the cleaning verdict; the injected
    predicate reads it, this module does not.
    """

    timestamp: datetime
    value: float | None
    quality: str
    verdict: str | None = None


InclusionPredicate = Callable[[Sample], bool]


@dataclass(frozen=True)
class RollupRow:
    """ADR-0011's rollup column set for one bucket."""

    count_all: int
    min_all: float | None
    max_all: float | None
    sum_all: float
    sumsq_all: float
    count_no_value: int

    count_included: int
    mean: float | None
    std: float | None
    median: float | None

    count_good: int
    count_uncertain: int
    count_bad: int

    policy_version: str


def compute_rollup(
    samples: Sequence[Sample],
    include: InclusionPredicate,
    policy_version: str,
) -> RollupRow:
    """Aggregate one bucket's samples into a `RollupRow`.

    `samples` must be non-empty and already belong to a single
    `(experiment_id, source, signal, bucket_start)` group — deciding
    whether a bucket exists at all is the caller's job, not this
    function's.

    `include` is called once per sample that has a value; only samples for
    which it returns True contribute to the verdict-dependent columns
    (`count_included`, `mean`, `std`, `median`). Every sample with a
    value — regardless of `include` — contributes to the verdict-independent
    columns (`count_all`, `min_all`, `max_all`, `sum_all`, `sumsq_all`).
    Samples without a value are counted in `count_no_value` only. Every
    sample, with or without a value, contributes to the composition counts
    (`count_good`, `count_uncertain`, `count_bad`), which partition on the
    acquisition-time `quality` label alone.

    `policy_version` is required (no default) — see ADR-0011 on why a
    frozen bucket must carry the policy generation that sealed it.

    Raises `ValueError` if `samples` is empty, or if any sample's
    `quality` is not one of GOOD/UNCERTAIN/BAD.
    """
    if not samples:
        raise ValueError("compute_rollup requires at least one sample")

    for s in samples:
        if s.quality not in QUALITY_LABELS:
            raise ValueError(f"unrecognised quality label: {s.quality!r}")

    with_value = [s for s in samples if s.value is not None]
    values_all: list[float] = [s.value for s in with_value if s.value is not None]
    count_all = len(values_all)
    count_no_value = len(samples) - count_all
    min_all = min(values_all) if values_all else None
    max_all = max(values_all) if values_all else None
    sum_all = float(sum(values_all))
    sumsq_all = float(sum(v * v for v in values_all))

    count_good = sum(1 for s in samples if s.quality == "GOOD")
    count_uncertain = sum(1 for s in samples if s.quality == "UNCERTAIN")
    count_bad = sum(1 for s in samples if s.quality == "BAD")

    included_values: list[float] = [
        s.value for s in with_value if s.value is not None and include(s)
    ]
    count_included = len(included_values)

    if count_included == 0:
        mean = std = median = None
    else:
        mean = statistics.mean(included_values)
        std = statistics.pstdev(included_values)
        median = statistics.median(included_values)

    return RollupRow(
        count_all=count_all,
        min_all=min_all,
        max_all=max_all,
        sum_all=sum_all,
        sumsq_all=sumsq_all,
        count_no_value=count_no_value,
        count_included=count_included,
        mean=mean,
        std=std,
        median=median,
        count_good=count_good,
        count_uncertain=count_uncertain,
        count_bad=count_bad,
        policy_version=policy_version,
    )
