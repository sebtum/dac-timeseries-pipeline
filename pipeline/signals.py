"""The 25 declared `(source, signal)` pairs and the table each one is stored in.

Per ADR-0006 the two text-valued signals go to `readings_state` and the other 23 to
`readings_numeric`. The list is declared, not discovered from the file: a pair that is not here
is rejected at ingest as `unknown_signal` instead of silently creating a new series, and the
numeric/text split cannot drift with whatever the first row of a file happens to look like.
Source: `task/DATA_DICTIONARY.md` (Signals), counts checked against the census (25 pairs).
"""

from __future__ import annotations

NUMERIC_TABLE = "readings_numeric"
STATE_TABLE = "readings_state"
CONFLICTS_TABLE = "readings_conflicts"

DECLARED_SIGNALS: dict[str, tuple[str, ...]] = {
    "ambient": (
        "ambient_temperature",
        "relative_humidity",
        "ambient_pressure",
        "available_solar_power",
    ),
    "absorber": (
        "air_flow",
        "co2_in_ppm",
        "co2_out_ppm",
        "solvent_flow",
        "solvent_temperature",
        "solvent_pH",
        "pressure_drop",
    ),
    "hydrolyzer": (
        "current_setpoint",
        "current",
        "voltage",
        "power",
        "acid_pH",
        "base_pH",
        "conductivity",
        "electrolyte_temperature",
        "flow",
        "pressure",
    ),
    "plant": ("pump_speed", "fan_speed", "valve_state", "process_state"),
}

STATE_SIGNALS = frozenset({"valve_state", "process_state"})

TABLE_FOR: dict[tuple[str, str], str] = {
    (source, signal): STATE_TABLE if signal in STATE_SIGNALS else NUMERIC_TABLE
    for source, signals in DECLARED_SIGNALS.items()
    for signal in signals
}

QUALITY_RANK: dict[str, int] = {"GOOD": 0, "UNCERTAIN": 1, "BAD": 2}
