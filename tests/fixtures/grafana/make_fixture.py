"""Writes `data.lp`, the tiny InfluxDB data behind `dashboard.json` (the checker's test dashboard).

Two experiments of 60 s (`experiments.json`), 20 readings each of `voltage` and `current`, one
per second from the start, in the `readings_processed` shape of ADR-0015. EXP_001's voltage at
+3 s is excluded (raw value 140.0, no `value`). One gap row in `quality_intervals`: EXP_001 voltage
from +5 s to +8 s. Counts every test relies on, from this construction:

    readings_processed: 80 rows (EXP_001: 20 voltage + 20 current; EXP_002 the same)
    accepted voltage:   EXP_001 19, EXP_002 20
    quality_intervals:  1 row (EXP_001, voltage, gap, 3 s)

`python tests/fixtures/grafana/make_fixture.py` rewrites the file; `lines(...)` is also what the
tests import, so the committed file and the tests cannot drift apart.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECOND = 10**9
STARTS = {
    "EXP_001": datetime(2026, 5, 4, 8, 0, 0, tzinfo=UTC),
    "EXP_002": datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC),
}
READINGS = 20
BASE = {"voltage": 80.0, "current": 100.0}


def _ns(moment: datetime) -> int:
    return int(moment.timestamp()) * SECOND


def lines(*, interval_experiment: str = "EXP_001") -> list[str]:
    """Line protocol. `interval_experiment` names the experiment the gap row belongs to; a test
    that needs the intervals panel empty writes it for an experiment the dashboard never selects."""
    out: list[str] = []
    for experiment, start in STARTS.items():
        t0 = _ns(start)
        for signal, base in BASE.items():
            tags = f"experiment_id={experiment},source=plant,signal={signal},policy_version=m3-v1"
            for k in range(READINGS):
                ts = t0 + k * SECOND
                if experiment == "EXP_001" and signal == "voltage" and k == 3:
                    out.append(
                        f'readings_processed,{tags} value_raw=140.0,quality="GOOD",'
                        f'verdict="excluded",reason="spike",flags="" {ts}'
                    )
                else:
                    value = base + k
                    out.append(
                        f"readings_processed,{tags} value_raw={value},value={value},"
                        f'quality="GOOD",verdict="accepted",reason="",flags="" {ts}'
                    )
    t0 = _ns(STARTS["EXP_001"])
    out.append(
        f"quality_intervals,experiment_id={interval_experiment},source=plant,signal=voltage,"
        f"policy_version=m3-v1,kind=gap seconds=3.0,end_ns={t0 + 8 * SECOND}i,points=0i "
        f"{t0 + 5 * SECOND}"
    )
    return out


if __name__ == "__main__":
    (HERE / "data.lp").write_text("\n".join(lines()) + "\n", encoding="utf-8", newline="\n")
