"""Same-series, same-timestamp collision detection, at bounded memory.

Per ADR-0007: detect collisions by sorting on series key then time and
comparing adjacent rows, so a colliding pair lands next to each other and
the comparison step holds only the current group. That comparison step is
`find_collisions` below, and on its own it is genuinely O(1).

What ADR-0007 does not make O(1) by itself is the *sort*. `sorted_external`
supplies that: a two-phase external merge sort (buffer a bounded chunk,
sort it in memory, spill it to disk as a sorted run; once the source is
exhausted, k-way merge the runs with `heapq.merge`, which holds only one
row per open run). Memory is O(chunk_size + run_count), never O(total
rows) — the property the M0 census and M2 ingestion both need, since
ADR-0007's addendum says this module is reused by both, and U-06 (ADR-0003)
names memory-scaling as the standing, not-yet-fully-defended challenge.

Detection only — classifying a group as an exact duplicate vs a conflict,
and picking a winner, is resolution and needs U-07/U-08 settled first (see
the ADR-0007 addendum).
"""

from __future__ import annotations

import csv
import heapq
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_CHUNK_SIZE = 50_000


@dataclass(frozen=True)
class Reading:
    row_number: int  # 1-based, header excluded — matches file order
    timestamp_raw: str
    timestamp: datetime
    experiment_id: str
    source: str
    signal: str
    value_raw: str
    quality: str


def parse_timestamp(raw: str) -> datetime:
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    return datetime.fromisoformat(text)


def series_key(r: Reading) -> tuple[str, str, str]:
    return (r.experiment_id, r.source, r.signal)


def sort_key(r: Reading) -> tuple[str, str, str, datetime]:
    return (*series_key(r), r.timestamp)


def find_collisions(readings: Iterable[Reading]) -> Iterator[list[Reading]]:
    """Yield groups of 2+ readings sharing (series key, timestamp).

    `readings` must already be sorted by `sort_key`. Holds only the current
    group in memory: O(1) relative to the number of readings.
    """
    group: list[Reading] = []
    current_key: tuple[str, str, str, datetime] | None = None
    for r in readings:
        key = sort_key(r)
        if key == current_key:
            group.append(r)
        else:
            if len(group) > 1:
                yield group
            group = [r]
            current_key = key
    if len(group) > 1:
        yield group


def _spill_run(chunk: list[Reading], run_dir: Path, run_index: int) -> Path:
    chunk.sort(key=sort_key)
    path = run_dir / f"run_{run_index}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for r in chunk:
            writer.writerow(
                [
                    r.row_number,
                    r.timestamp_raw,
                    r.experiment_id,
                    r.source,
                    r.signal,
                    r.value_raw,
                    r.quality,
                ]
            )
    return path


def _read_run(path: Path) -> Iterator[Reading]:
    with path.open(newline="", encoding="utf-8") as f:
        for (
            row_number,
            timestamp_raw,
            experiment_id,
            source,
            signal,
            value_raw,
            quality,
        ) in csv.reader(f):
            yield Reading(
                row_number=int(row_number),
                timestamp_raw=timestamp_raw,
                timestamp=parse_timestamp(timestamp_raw),
                experiment_id=experiment_id,
                source=source,
                signal=signal,
                value_raw=value_raw,
                quality=quality,
            )


def sorted_external(
    readings: Iterable[Reading],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    tmp_dir: Path | None = None,
) -> Iterator[Reading]:
    """Yield `readings` in `sort_key` order, without ever holding all of
    them in memory at once.

    Phase 1: buffer up to `chunk_size` readings, sort that chunk in memory
    (bounded by `chunk_size`), spill it to a temp file as a sorted run.
    Phase 2: k-way merge the runs with `heapq.merge`, which reads one line
    at a time per run — memory O(run_count), not O(total readings).

    Single merge pass: fan-in is bounded by the OS's open-file limit. A
    fully general external sort would merge runs in multiple passes to
    remove that bound; not needed at this dataset's scale, and named here
    rather than silently assumed away.
    """
    with tempfile.TemporaryDirectory(dir=tmp_dir) as td:
        run_dir = Path(td)
        run_paths: list[Path] = []
        chunk: list[Reading] = []

        for r in readings:
            chunk.append(r)
            if len(chunk) >= chunk_size:
                run_paths.append(_spill_run(chunk, run_dir, len(run_paths)))
                chunk = []
        if chunk:
            run_paths.append(_spill_run(chunk, run_dir, len(run_paths)))

        if not run_paths:
            return

        run_iters = [_read_run(p) for p in run_paths]
        yield from heapq.merge(*run_iters, key=sort_key)
