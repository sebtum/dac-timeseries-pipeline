"""Build the compare fixture: `python tests/fixtures/compare/make_fixture.py` (kept for review).

Not run in CI: the committed `readings.csv`, `experiments.json` and `readings.sha256` are the
fixture. Stdlib only, deterministic, and it imports nothing from `pipeline/` (the noise amplitudes
below are half of each signal's declared normal step, copied by hand from
`pipeline/cleaning_policy.py`, so the file cannot drift with the code it is meant to check).

Three experiments of 1,200 s (M5, S5.12 to S5.16):

  EXP_001  2026-05-04T08:00:00Z  setpoint 150 A, air flow 1200 m3/h, batch SB-A, operator Op A
  EXP_002  2026-05-11T09:00:00Z  setpoint 200 A, air flow 1200 m3/h, batch SB-A, operator Op A
  EXP_003  2026-05-18T07:30:00Z  setpoint 150 A, air flow 2400 m3/h, batch SB-B, operator Op B

Every instant below is seconds after the experiment's start.

  process_state  STARTUP 0, STEADY_STATE +120, LOAD_CHANGE +600, STEADY_STATE +660, SHUTDOWN +1140.
  current_setpoint 1 Hz   nominal, +20 A from +600 to +659. No noise.
  current        1 Hz     setpoint +- 0.15 A.
  flow           1 Hz     40 L/min + triangle wave (period 300 s, amplitude 2) +- 0.19.
  pressure       1 Hz     2.5 bar + triangle wave (period 420 s, amplitude 0.1) +- 0.0145.
  electrolyte_temperature 0.2 Hz  35 degC + 0.005 per second +- 0.095.
  voltage        1 Hz     40 + 0.3 current - 0.2 flow + 3.0 pressure - 0.1 T + e, where T is the
                          electrolyte temperature reading an as-of join pairs with that instant
                          (latest reading at or before it) and e is
                          random.Random("compare-fixture").uniform(-0.05, 0.05), one draw per
                          second (the same sequence in each experiment). Every input is rounded to
                          the decimals written before the voltage is computed from it; the voltage
                          is written with 6 decimals. BAD at +300 in EXP_001 (value as normal).
  power          1 Hz     voltage x current, exact decimal.
  air_flow       1 Hz     nominal +- 3.775.
  pressure_drop  0.5 Hz   15 x (nominal air flow / 1200)^2 +- 0.12.
  co2_in_ppm     0.5 Hz   420 +- 0.55.
  co2_out_ppm    0.5 Hz   105 +- 0.4.
  solvent_flow   0.5 Hz   8.0 +- 0.07.
  ambient_temperature 15 +- 0.065, ambient_pressure 1013.25 +- 0.03, relative_humidity 50 +- 0.7,
                  all once a minute.

Noise is a fixed alternation of plus and minus half the signal's normal step, plus at an even
reading index (the second for 1 Hz signals), so cleaning accepts every normal reading.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent

DURATION_S = 1200
HEADER = ["timestamp", "experiment_id", "source", "signal", "value", "quality"]

# id, start, setpoint A, air flow m3/h, batch, operator
EXPERIMENTS = [
    ("EXP_001", datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC), 150, 1200, "SB-A", "Op A"),
    ("EXP_002", datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC), 200, 1200, "SB-A", "Op A"),
    ("EXP_003", datetime(2026, 5, 18, 7, 30, 0, tzinfo=UTC), 150, 2400, "SB-B", "Op B"),
]
PLANTED_BAD = ("EXP_001", "voltage", 300)

ORDER = [
    ("ambient", "ambient_temperature"),
    ("ambient", "relative_humidity"),
    ("ambient", "ambient_pressure"),
    ("absorber", "air_flow"),
    ("absorber", "pressure_drop"),
    ("absorber", "co2_in_ppm"),
    ("absorber", "co2_out_ppm"),
    ("absorber", "solvent_flow"),
    ("hydrolyzer", "current_setpoint"),
    ("hydrolyzer", "current"),
    ("hydrolyzer", "voltage"),
    ("hydrolyzer", "power"),
    ("hydrolyzer", "electrolyte_temperature"),
    ("hydrolyzer", "flow"),
    ("hydrolyzer", "pressure"),
    ("plant", "process_state"),
]

D = Decimal
Row = tuple[int, str, str, str]  # (offset s, source, signal, value text)


def fixed(value: Fraction, places: int) -> Decimal:
    """Round an exact value to `places` decimals (half to even)."""
    with localcontext() as context:
        context.prec = 50
        return (D(value.numerator) / D(value.denominator)).quantize(
            D(1).scaleb(-places), rounding=ROUND_HALF_EVEN
        )


def noisy(level: Fraction, half_step: str, index: int, places: int) -> Decimal:
    """`level` plus half a step at an even index, minus half a step at an odd one."""
    half = Fraction(D(half_step))
    return fixed(level + (half if index % 2 == 0 else -half), places)


def triangle(t: int, period: int, amplitude: str) -> Fraction:
    """Triangle wave through 0 at t = 0, rising to +amplitude, down to -amplitude, back."""
    phase = Fraction(t % period, period)
    if phase < Fraction(1, 4):
        unit = 4 * phase
    elif phase < Fraction(3, 4):
        unit = 2 - 4 * phase
    else:
        unit = 4 * phase - 4
    return unit * Fraction(D(amplitude))


def build(setpoint: int, air_flow: int) -> list[Row]:
    rows: list[Row] = []
    rng = random.Random("compare-fixture")  # noqa: S311 (a fixture, not a secret)
    pressure_drop_level = Fraction(15) * Fraction(air_flow, 1200) ** 2

    def add(offset: int, pair: tuple[str, str], value: Decimal | str):
        text = value if isinstance(value, str) else format(value, "f")
        rows.append((offset, pair[0], pair[1], text))

    temperature_at: dict[int, Decimal] = {}
    for i in range(DURATION_S // 5):
        t = 5 * i
        temperature_at[t] = noisy(Fraction(35) + Fraction(5, 1000) * t, "0.095", i, 3)
        add(t, ("hydrolyzer", "electrolyte_temperature"), temperature_at[t])

    for k in range(DURATION_S):
        set_value = setpoint + (20 if 600 <= k <= 659 else 0)
        add(k, ("hydrolyzer", "current_setpoint"), f"{set_value}.0")
        current = noisy(Fraction(set_value), "0.15", k, 3)
        flow = noisy(Fraction(40) + triangle(k, 300, "2"), "0.19", k, 3)
        pressure = noisy(Fraction("2.5") + triangle(k, 420, "0.1"), "0.0145", k, 4)
        add(k, ("hydrolyzer", "current"), current)
        add(k, ("hydrolyzer", "flow"), flow)
        add(k, ("hydrolyzer", "pressure"), pressure)

        temperature = temperature_at[5 * (k // 5)]
        e = rng.uniform(-0.05, 0.05)
        volts = (
            40 + 0.3 * float(current) - 0.2 * float(flow) + 3.0 * float(pressure)
            - 0.1 * float(temperature) + e
        )  # fmt: skip
        voltage = D(f"{volts:.6f}")
        add(k, ("hydrolyzer", "voltage"), voltage)
        add(k, ("hydrolyzer", "power"), voltage * current)

        add(k, ("absorber", "air_flow"), noisy(Fraction(air_flow), "3.775", k, 3))

    for i in range(DURATION_S // 2):
        k = 2 * i
        add(k, ("absorber", "pressure_drop"), noisy(pressure_drop_level, "0.12", i, 3))
        add(k, ("absorber", "co2_in_ppm"), noisy(Fraction(420), "0.55", i, 2))
        add(k, ("absorber", "co2_out_ppm"), noisy(Fraction(105), "0.4", i, 2))
        add(k, ("absorber", "solvent_flow"), noisy(Fraction(8), "0.07", i, 2))

    for m in range(DURATION_S // 60):
        k = 60 * m
        add(k, ("ambient", "ambient_temperature"), noisy(Fraction(15), "0.065", m, 3))
        add(k, ("ambient", "relative_humidity"), noisy(Fraction(50), "0.7", m, 1))
        add(k, ("ambient", "ambient_pressure"), noisy(Fraction("1013.25"), "0.03", m, 2))

    for offset, state in (
        (0, "STARTUP"),
        (120, "STEADY_STATE"),
        (600, "LOAD_CHANGE"),
        (660, "STEADY_STATE"),
        (1140, "SHUTDOWN"),
    ):
        add(offset, ("plant", "process_state"), state)

    order = {pair: n for n, pair in enumerate(ORDER)}
    rows.sort(key=lambda r: (r[0], order[(r[1], r[2])]))
    return rows


def stamp(start: datetime, offset: int) -> str:
    return (start + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    csv_path = HERE / "readings.csv"
    experiments = []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for experiment_id, start, setpoint, air_flow, batch, operator in EXPERIMENTS:
            for offset, source, signal, value in build(setpoint, air_flow):
                bad = (experiment_id, signal, offset) == PLANTED_BAD
                writer.writerow(
                    [
                        stamp(start, offset),
                        experiment_id,
                        source,
                        signal,
                        value,
                        "BAD" if bad else "GOOD",
                    ]
                )
            experiments.append(
                {
                    "experiment_id": experiment_id,
                    "start_time": stamp(start, 0),
                    "end_time": stamp(start, DURATION_S),
                    "duration_s": DURATION_S,
                    "current_setpoint_nominal_A": float(setpoint),
                    "air_flow_nominal_m3h": float(air_flow),
                    "solvent_flow_nominal_Lmin": 8.0,
                    "operator": operator,
                    "sorbent_batch": batch,
                    "notes": None,
                }
            )
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
