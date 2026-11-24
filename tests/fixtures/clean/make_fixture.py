"""Build the cleaning fixture: `python tests/fixtures/clean/make_fixture.py` (kept for review).

Not run in CI: the committed `readings.csv`, `experiments.json` and `readings.sha256` are the
fixture. Stdlib only, no randomness. One experiment, EXP_001, 2026-05-04T08:00:00Z to
08:10:00Z (600 s). Every instant below is seconds after 08:00:00.

Noise is a fixed alternating pattern of plus and minus half the signal's declared normal step
(`pipeline/cleaning_policy.py`), so every normal step equals the step size exactly: never flat
(a step is flat below 0.2 x the step size), never a spike (a spike needs 10 x the step size).
The expected verdicts therefore follow from the construction alone, and
`tests/e2e/test_clean_cli.py` writes them down from the list below, not from the rules.

Planted defects:

  voltage          1 Hz around 100 V. 140.0 at +120 (spike). 110 V from +300 (a step). No points
                   from +400 to +409 (points at +399 and +410: one gap of 11 s). 140.0 and BAD
                   at +500 (priority).
  current          1 Hz around 0.5 A. -0.5 at +30 (outside the typical range, physically
                   possible). No value at +60. 150 A from +100 (a step). Ramp 150 -> 210 A at
                   4 A/s from +200 to +215, then 210 A.
  current_setpoint 1 Hz. 0 to +99, 150 from +100, 210 from +200 (held 400 s, on purpose).
  solvent_temperature  0.2 Hz around 31 C. 30.22 for 40 readings from +100 to +295 (an exact
                   run). 31.0 three times at +20, +25, +30 (a short run, not a flatline).
  air_flow         1 Hz around 1200. From +360 around 20 with steps of 5 % of normal (noise
                   collapse, to the end).
  solvent_pH       0.2 Hz around 7.6. 27.4 at +250 (outside the physical limits).
  pressure         1 Hz around 2.5 bar. UNCERTAIN at +45.
  conductivity     0.2 Hz around 200. BAD for 10 readings from +150 to +195.
  available_solar_power  1/60 Hz: 0.0 for all 10 readings (night).
  co2_in_ppm       0.5 Hz around 415. A conflicting duplicate at +80 (415.55 and 420.55, both
                   GOOD: ingest keeps the smaller). An exact copy at +90.
  process_state    STARTUP at 0, STEADY_STATE at +120, WARMUP at +400 (not a declared state),
                   SHUTDOWN at +540. valve_state: OPEN at 0.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent))

from pipeline.cleaning_policy import POLICY  # noqa: E402

EXPERIMENT = "EXP_001"
START = datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC)
DURATION_S = 600
HEADER = ["timestamp", "experiment_id", "source", "signal", "value", "quality"]

ORDER = [
    ("ambient", "available_solar_power"),
    ("absorber", "air_flow"),
    ("absorber", "co2_in_ppm"),
    ("absorber", "solvent_temperature"),
    ("absorber", "solvent_pH"),
    ("hydrolyzer", "current_setpoint"),
    ("hydrolyzer", "current"),
    ("hydrolyzer", "voltage"),
    ("hydrolyzer", "conductivity"),
    ("hydrolyzer", "pressure"),
    ("plant", "valve_state"),
    ("plant", "process_state"),
]


def step(signal: str) -> float:
    return next(p.step for (_, s), p in POLICY.items() if s == signal)


def noisy(signal: str, index: int, level: float, factor: float = 1.0) -> float:
    """`level` plus or minus half a step (alternating by reading index)."""
    half = step(signal) * factor / 2
    return round(level + (half if index % 2 == 0 else -half), 6)


def text(value: float | str | None) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else repr(value)


Row = tuple[int, str, str, str, str]  # (offset s, source, signal, value, quality)


def build() -> list[Row]:
    rows: list[Row] = []

    def add(offset: int, pair: tuple[str, str], value: float | str | None, quality: str = "GOOD"):
        rows.append((offset, pair[0], pair[1], text(value), quality))

    # voltage, 1 Hz
    pair = ("hydrolyzer", "voltage")
    for k in range(DURATION_S):
        if 400 <= k <= 409:
            continue
        level = 110.0 if k >= 300 else 100.0
        value = noisy("voltage", k, level)
        quality = "GOOD"
        if k == 120:
            value = 140.0
        if k == 500:
            value, quality = 140.0, "BAD"
        add(k, pair, value, quality)

    # current, 1 Hz
    pair = ("hydrolyzer", "current")
    for k in range(DURATION_S):
        if k < 100:
            value = noisy("current", k, 0.5)
        elif k < 200:
            value = noisy("current", k, 150.0)
        elif k <= 215:
            value = 150.0 + 4.0 * (k - 200)
        else:
            value = noisy("current", k, 210.0)
        if k == 30:
            value = -0.5
        if k == 60:
            value = None
        add(k, pair, value)

    # current_setpoint, 1 Hz
    pair = ("hydrolyzer", "current_setpoint")
    for k in range(DURATION_S):
        add(k, pair, 0.0 if k < 100 else (150.0 if k < 200 else 210.0))

    # solvent_temperature, 0.2 Hz
    pair = ("absorber", "solvent_temperature")
    for i in range(DURATION_S // 5):
        value = noisy("solvent_temperature", i, 31.0)
        if 20 <= i <= 59:
            value = 30.22
        if i in (4, 5, 6):
            value = 31.0
        add(5 * i, pair, value)

    # air_flow, 1 Hz
    pair = ("absorber", "air_flow")
    for k in range(DURATION_S):
        if k < 360:
            add(k, pair, noisy("air_flow", k, 1200.0))
        else:
            add(k, pair, noisy("air_flow", k, 20.0, factor=0.05))

    # solvent_pH, 0.2 Hz
    pair = ("absorber", "solvent_pH")
    for i in range(DURATION_S // 5):
        add(5 * i, pair, 27.4 if i == 50 else noisy("solvent_pH", i, 7.6))

    # pressure, 1 Hz
    pair = ("hydrolyzer", "pressure")
    for k in range(DURATION_S):
        add(k, pair, noisy("pressure", k, 2.5), "UNCERTAIN" if k == 45 else "GOOD")

    # conductivity, 0.2 Hz
    pair = ("hydrolyzer", "conductivity")
    for i in range(DURATION_S // 5):
        add(5 * i, pair, noisy("conductivity", i, 200.0), "BAD" if 30 <= i <= 39 else "GOOD")

    # available_solar_power, 1/60 Hz
    pair = ("ambient", "available_solar_power")
    for m in range(DURATION_S // 60):
        add(60 * m, pair, 0.0)

    # co2_in_ppm, 0.5 Hz
    pair = ("absorber", "co2_in_ppm")
    for i in range(DURATION_S // 2):
        value = noisy("co2_in_ppm", i, 415.0)
        add(2 * i, pair, value)
        if 2 * i == 80:
            add(80, pair, 420.55)  # conflicting duplicate: ingest keeps 415.55
        if 2 * i == 90:
            add(90, pair, value)  # exact copy

    # states
    for offset, state in (
        (0, "STARTUP"),
        (120, "STEADY_STATE"),
        (400, "WARMUP"),
        (540, "SHUTDOWN"),
    ):
        add(offset, ("plant", "process_state"), state)
    add(0, ("plant", "valve_state"), "OPEN")

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
