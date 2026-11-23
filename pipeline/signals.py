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

# ---------------------------------------------------------------------------- profiling (M2.5)
#
# Declared, not parsed from the data dictionary at run time (M2.5 decision 6): a unit test
# checks that both tables cover the 23 numeric pairs and none of the 2 text pairs.
# Source: `task/DATA_DICTIONARY.md`, "Sampling rates (nominal)" and the per-signal range tables.
# The ranges are the dictionary's "roughly" / "typical" bounds. The profile counts how many
# stored values fall outside them; it never calls a reading anything because of that.

# Nominal seconds between points. A pair that is not here (the two text signals) is written on
# change, so it has no nominal interval and is never counted against one (MISTAKES.md C-01).
_NOMINAL_BY_SIGNAL: dict[str, float] = {
    # ~1 Hz
    "current_setpoint": 1.0,
    "current": 1.0,
    "voltage": 1.0,
    "power": 1.0,
    "flow": 1.0,
    "pressure": 1.0,
    "air_flow": 1.0,
    "pump_speed": 1.0,
    "fan_speed": 1.0,
    # ~0.5 Hz
    "co2_in_ppm": 2.0,
    "co2_out_ppm": 2.0,
    "solvent_flow": 2.0,
    "pressure_drop": 2.0,
    # ~0.2 Hz
    "acid_pH": 5.0,
    "base_pH": 5.0,
    "solvent_pH": 5.0,
    "conductivity": 5.0,
    "electrolyte_temperature": 5.0,
    "solvent_temperature": 5.0,
    # ~1/60 Hz
    "ambient_temperature": 60.0,
    "relative_humidity": 60.0,
    "ambient_pressure": 60.0,
    "available_solar_power": 60.0,
}

# signal -> (documented low, documented high, unit). `None` unit: the dictionary gives none (pH).
_RANGE_BY_SIGNAL: dict[str, tuple[float, float, str | None]] = {
    "ambient_temperature": (-5.0, 30.0, "°C"),
    "relative_humidity": (20.0, 100.0, "%"),
    "ambient_pressure": (990.0, 1030.0, "hPa"),
    "available_solar_power": (0.0, 550.0, "kW"),
    "air_flow": (1000.0, 2500.0, "m³/h"),
    "co2_in_ppm": (400.0, 430.0, "ppm"),
    "co2_out_ppm": (50.0, 200.0, "ppm"),
    "solvent_flow": (7.0, 10.0, "L/min"),
    "solvent_temperature": (5.0, 40.0, "°C"),
    "solvent_pH": (6.0, 9.0, None),
    "pressure_drop": (10.0, 65.0, "mbar"),
    "current_setpoint": (0.0, 260.0, "A"),
    "current": (0.0, 260.0, "A"),
    "voltage": (60.0, 130.0, "V"),
    "power": (0.0, 35000.0, "W"),
    "acid_pH": (0.5, 4.0, None),
    "base_pH": (10.0, 13.5, None),
    "conductivity": (150.0, 240.0, "mS/cm"),
    "electrolyte_temperature": (0.0, 45.0, "°C"),
    "flow": (25.0, 55.0, "L/min"),
    "pressure": (2.0, 3.0, "bar"),
    "pump_speed": (450.0, 650.0, "rpm"),
    "fan_speed": (800.0, 1600.0, "rpm"),
}

NOMINAL_INTERVAL_S: dict[tuple[str, str], float] = {
    pair: _NOMINAL_BY_SIGNAL[pair[1]] for pair, table in TABLE_FOR.items() if table == NUMERIC_TABLE
}

DOCUMENTED_RANGE: dict[tuple[str, str], tuple[float, float, str | None]] = {
    pair: _RANGE_BY_SIGNAL[pair[1]] for pair, table in TABLE_FOR.items() if table == NUMERIC_TABLE
}
