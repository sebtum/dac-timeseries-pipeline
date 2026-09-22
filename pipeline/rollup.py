"""Pure aggregation of one rollup bucket's samples, per ADR-0011.

`compute_rollup` takes the samples already grouped into one
`(experiment_id, source, signal, bucket_start)` bucket and returns
ADR-0011's rollup column set. It does no I/O, imports nothing from
InfluxDB, and does not perform the bucketing/time-flooring itself —
that grouping is the caller's job (T9). This module only knows how to
turn "here is a bucket's worth of samples" into the stored aggregate.

Column split, from ADR-0011:

  verdict-independent (over ALL samples, regardless of the predicate):
    count_all, min_all, max_all, sum_all, sumsq_all
  verdict-dependent (over samples the predicate includes only):
    count_included, mean, std, median
  composition (counts by acquisition-time quality label, independent
  of the predicate):
    count_good, count_uncertain, count_bad
  provenance:
    policy_version

The inclusion predicate is injected, not hardcoded. At M1 the caller
passes a placeholder equivalent to `quality == 'GOOD'` (UNCERTAIN is
excluded, same as BAD); M3 replaces it with the pipeline's real
verdict. This module must not know or assume what the predicate is —
it only calls it.

`std` is **population** standard deviation (denominator n, not n-1).
`statistics.pstdev` gives this directly, including the n=1 case
(`pstdev([x]) == 0.0`, no ZeroDivisionError) — the reason ADR-0011
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
    """

    timestamp: datetime
    value: float
    quality: str


InclusionPredicate = Callable[[Sample], bool]


@dataclass(frozen=True)
class RollupRow:
    """ADR-0011's rollup column set for one bucket."""

    count_all: int
    min_all: float
    max_all: float
    sum_all: float
    sumsq_all: float

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

    `include` is called once per sample; only samples for which it
    returns True contribute to the verdict-dependent columns
    (`count_included`, `mean`, `std`, `median`). Every sample —
    regardless of `include` — contributes to the verdict-independent
    columns (`count_all`, `min_all`, `max_all`, `sum_all`,
    `sumsq_all`) and to the composition counts (`count_good`,
    `count_uncertain`, `count_bad`), which partition on the
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

    values_all = [s.value for s in samples]
    count_all = len(values_all)
    min_all = min(values_all)
    max_all = max(values_all)
    sum_all = sum(values_all)
    sumsq_all = sum(v * v for v in values_all)

    count_good = sum(1 for s in samples if s.quality == "GOOD")
    count_uncertain = sum(1 for s in samples if s.quality == "UNCERTAIN")
    count_bad = sum(1 for s in samples if s.quality == "BAD")

    included_values = [s.value for s in samples if include(s)]
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
        count_included=count_included,
        mean=mean,
        std=std,
        median=median,
        count_good=count_good,
        count_uncertain=count_uncertain,
        count_bad=count_bad,
        policy_version=policy_version,
    )
