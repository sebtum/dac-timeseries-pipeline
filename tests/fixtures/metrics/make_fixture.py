"""Build the metrics fixture: `python tests/fixtures/metrics/make_fixture.py` (kept for review).

Not run in CI: the committed `readings.csv`, `experiments.json` and `readings.sha256` are the
fixture. Stdlib only, no randomness, and it imports nothing from `pipeline/` (the noise amplitudes
below are half of each signal's declared normal step, copied by hand from
`pipeline/cleaning_policy.py`, so the file cannot drift with the code it is meant to check).

One experiment, EXP_001, 2026-05-04T08:00:00Z to 08:10:00Z (600 s). Every instant below is seconds
after 08:00:00. Every value is an exact decimal, written as text, so the hand computations in
`README.md` are exact.

Noise is a fixed alternation of plus and minus half the signal's normal step, plus at "even"
positions, so cleaning accepts every normal reading (every step equals the normal step exactly:
never flat, never a spike). "Even" means an even second for the 1 Hz signals and an even reading
index for the slower ones (a 0.5 Hz signal read at even seconds would otherwise always be plus,
a constant, which cleaning would call a flatline).

  voltage        1 Hz, 100 +- 0.075 V.
  current        1 Hz, 150 +- 0.15 A. BAD at +100 (value as normal). No rows at +300..+310,
                 +450, +451.
  power          1 Hz, voltage x current exactly, +250 W at +200. No rows at +300..+310.
  co2_in_ppm     0.5 Hz (even seconds), 420 +- 0.55 ppm. BAD at +500 and +502.
  co2_out_ppm    0.5 Hz (even seconds), 105 +- 0.4 ppm. UNCERTAIN at +400.
  air_flow       1 Hz, 1200 +- 3.775 m3/h.
  ambient_temperature  whole minutes, 15 +- 0.065 degC. No rows at +300 and +360.
  ambient_pressure     whole minutes, 1013.25 +- 0.03 hPa. No rows at +300 and +360.
  process_state  STARTUP at 0, STEADY_STATE at +60. No other signal has rows.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXPERIMENT = "EXP_001"
START = datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC)
DURATION_S = 600
HEADER = ["timestamp", "experiment_id", "source", "signal", "value", "quality"]

ORDER = [
    ("ambient", "ambient_temperature"),
    ("ambient", "ambient_pressure"),
    ("absorber", "air_flow"),
    ("absorber", "co2_in_ppm"),
    ("absorber", "co2_out_ppm"),
    ("hydrolyzer", "current"),
    ("hydrolyzer", "voltage"),
    ("hydrolyzer", "power"),
    ("plant", "process_state"),
]

D = Decimal


def noisy(level: str, half_step: str, index: int) -> Decimal:
    """`level` plus half a step at an even index, minus half a step at an odd one."""
    return D(level) + (D(half_step) if index % 2 == 0 else -D(half_step))


Row = tuple[int, str, str, str, str]  # (offset s, source, signal, value, quality)


def build() -> list[Row]:
    rows: list[Row] = []

    def add(offset: int, pair: tuple[str, str], value: Decimal | str, quality: str = "GOOD"):
        rows.append(
            (
                offset,
                pair[0],
                pair[1],
                value if isinstance(value, str) else format(value, "f"),
                quality,
            )
        )

    # hydrolyzer, 1 Hz
    for k in range(DURATION_S):
        no_power_or_electrics = 300 <= k <= 310
        voltage = noisy("100", "0.075", k)
        current = noisy("150", "0.15", k)
        if not no_power_or_electrics:
            add(k, ("hydrolyzer", "voltage"), voltage)
            power = voltage * current + (D(250) if k == 200 else D(0))
            add(k, ("hydrolyzer", "power"), power)
            if k not in (450, 451):
                add(k, ("hydrolyzer", "current"), current, "BAD" if k == 100 else "GOOD")

    # absorber air_flow, 1 Hz
    for k in range(DURATION_S):
        add(k, ("absorber", "air_flow"), noisy("1200", "3.775", k))

    # co2, 0.5 Hz at even seconds; the sign alternates with the reading index
    for i in range(DURATION_S // 2):
        k = 2 * i
        add(
            k,
            ("absorber", "co2_in_ppm"),
            noisy("420", "0.55", i),
            "BAD" if k in (500, 502) else "GOOD",
        )
        add(
            k,
            ("absorber", "co2_out_ppm"),
            noisy("105", "0.4", i),
            "UNCERTAIN" if k == 400 else "GOOD",
        )

    # ambient, whole minutes
    for m in range(DURATION_S // 60):
        k = 60 * m
        if k in (300, 360):
            continue
        add(k, ("ambient", "ambient_temperature"), noisy("15", "0.065", m))
        add(k, ("ambient", "ambient_pressure"), noisy("1013.25", "0.03", m))

    add(0, ("plant", "process_state"), "STARTUP")
    add(60, ("plant", "process_state"), "STEADY_STATE")

    order = {pair: n for n, pair in enumerate(ORDER)}
    rows.sort(key=lambda r: (r[0], order[(r[1], r[2])]))
    return rows


def stamp(offset: int) -> str:
    return (START + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    csv_path = HERE / "readings.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for offset, source, signal, value, quality in build():
            writer.writerow([stamp(offset), EXPERIMENT, source, signal, value, quality])
    end = START + timedelta(seconds=DURATION_S)
    experiments = [
        {
            "experiment_id": EXPERIMENT,
            "start_time": START.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_s": DURATION_S,
            "current_setpoint_nominal_A": 150.0,
            "air_flow_nominal_m3h": 1200.0,
            "solvent_flow_nominal_Lmin": 8.0,
            "operator": "Fixture",
            "sorbent_batch": "SB-FIXTURE",
            "notes": "Metrics fixture: hand-computable series, see README.md.",
        }
    ]
    (HERE / "experiments.json").write_text(
        json.dumps(experiments, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    (HERE / "readings.sha256").write_text(
        f"{digest}  {csv_path.name}\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {csv_path} ({sum(1 for _ in csv_path.open('rb')) - 1} rows), sha256 {digest}")


if __name__ == "__main__":
    main()
