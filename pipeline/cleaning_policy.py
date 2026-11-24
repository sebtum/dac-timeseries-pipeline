"""The declared cleaning policy (M3, ADR-0015): every number a verdict depends on, in one table.

A reading is accepted or excluded by rules that read only this module. Nothing here is learned
from the data at run time; the numbers were set once, from the profile of the six experiments
(`reports/post_ingest_profile.json`) and the data dictionary, and a unit test checks the step
sizes against that profile again so they cannot drift.

`POLICY_VERSION` names the rule set. Every processed row carries it as a tag, so a new rule set
writes new series beside the old ones instead of half overwriting them. `policy_fingerprint()`
is the SHA-256 of the canonical JSON of the whole table; a unit test pins it to the version
string, so editing a number here without bumping the version fails the test.

Reason codes are verdicts on purpose: this is the milestone where readings are judged. The
profile outputs (M2.5) stay free of verdict words; these do not.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from pipeline.signals import NOMINAL_INTERVAL_S, STATE_SIGNALS, TABLE_FOR

POLICY_VERSION = "m3-v1"

# ---------------------------------------------------------------------------- reason codes

# Priority order (decision 8): the first code that fires is the `reason`; every code that fires
# goes in `flags`, in this order, and the note comes last.
REASON_CODES: tuple[str, ...] = (
    "no_value",
    "flag_bad",
    "flag_uncertain",
    "outside_physical_limits",
    "unknown_state",
    "conflicting_duplicate",
    "spike",
    "flatline",
)
# A note, never a reason: the reading is physically possible and stays accepted (decision 10).
NOTE_OUTSIDE_TYPICAL = "outside_typical_range"
FLAG_CODES: tuple[str, ...] = (*REASON_CODES, NOTE_OUTSIDE_TYPICAL)

# ---------------------------------------------------------------------------- constants

SPIKE_HALF_WINDOW = 5  # neighbours on each side, in time order, taken from usable readings
SPIKE_ROBUST_FACTOR = 5.0  # times the robust standard deviation (1.4826 x MAD)
SPIKE_MAD_SCALE = 1.4826
SPIKE_FLOOR_STEPS = 10.0  # times the signal's normal step: the least a spike can deviate
FLAT_FRACTION = 0.2  # a step is flat when it is smaller than this times the normal step
FLAT_WINDOW_SECONDS = 30.0  # the flatline window is about this long, ...
FLAT_MIN_HALF_WINDOW = 5  # ... and at least this many steps on each side
FLAT_MIN_RUN = 5  # a flagged flat step must sit in an unbroken run of at least this many flat steps
GAP_FACTOR = 2.0  # a spacing over this times the nominal interval is a gap

# ---------------------------------------------------------------------------- per signal

MEASURED = "measured"
COMMANDED = "commanded"
STATE = "state"

# Physical limits, inclusive. They stand in for instrument spans we do not have (A-05) and
# always contain the documented typical range (unit-tested). A value outside is not possible
# for this plant, whatever the flag says.
_LIMITS: dict[str, tuple[float, float]] = {
    "ambient_temperature": (-40.0, 60.0),
    "relative_humidity": (0.0, 100.0),
    "ambient_pressure": (900.0, 1100.0),
    "available_solar_power": (0.0, 1000.0),
    "air_flow": (0.0, 5000.0),
    "co2_in_ppm": (0.0, 5000.0),
    "co2_out_ppm": (0.0, 5000.0),
    "solvent_flow": (0.0, 50.0),
    "solvent_temperature": (-10.0, 100.0),
    "solvent_pH": (0.0, 14.0),
    "acid_pH": (0.0, 14.0),
    "base_pH": (0.0, 14.0),
    "pressure_drop": (0.0, 200.0),
    "current_setpoint": (0.0, 500.0),
    "current": (-2.0, 500.0),
    "voltage": (0.0, 200.0),
    "power": (-100.0, 60000.0),
    "conductivity": (0.0, 1000.0),
    "electrolyte_temperature": (-10.0, 100.0),
    "flow": (0.0, 200.0),
    "pressure": (0.0, 10.0),
    "pump_speed": (0.0, 2000.0),
    "fan_speed": (0.0, 3000.0),
}

# Normal step size: the median over the six experiments of the profile's
# `differences.median_abs`, so one degraded experiment cannot move it (decision 13).
# Checked against `reports/post_ingest_profile.json` at 9 significant digits by a unit test.
_STEP: dict[str, float] = {
    "acid_pH": 0.047,
    "air_flow": 7.55,
    "ambient_pressure": 0.06,
    "ambient_temperature": 0.13,
    "available_solar_power": 12.255,
    "base_pH": 0.0475,
    "co2_in_ppm": 1.1,
    "co2_out_ppm": 0.8,
    "conductivity": 1.85,
    "current": 0.3,
    "current_setpoint": 0.0,
    "electrolyte_temperature": 0.19,
    "fan_speed": 4.8,
    "flow": 0.38,
    "power": 37.65,
    "pressure": 0.029,
    "pressure_drop": 0.24,
    "pump_speed": 2.9,
    "relative_humidity": 1.4,
    "solvent_flow": 0.14,
    "solvent_pH": 0.0485,
    "solvent_temperature": 0.285,
    "voltage": 0.15,
}

# What a state signal may say (task/DATA_DICTIONARY.md).
_STATES: dict[str, tuple[str, ...]] = {
    "valve_state": ("CLOSED", "OPEN"),
    "process_state": ("LOAD_CHANGE", "SHUTDOWN", "STARTUP", "STEADY_STATE"),
}

# A setpoint is held on purpose, so neither spike nor flatline applies to it.
_COMMANDED = frozenset({"current_setpoint"})
# Solar power rises from 0 kW at dawn in steps far smaller than the declared normal step, so a
# fraction of that step is the wrong yardstick (decision 25): for these signals a step is flat only
# when the change is exactly 0, and never when both values are 0.0 (night).
_EXACT_REPEAT = frozenset({"available_solar_power"})


@dataclass(frozen=True)
class SignalPolicy:
    kind: str
    limits: tuple[float, float] | None
    step: float | None
    spike: bool
    flatline: bool
    exact_repeat: bool
    flat_half_window: int | None
    states: tuple[str, ...] | None


def _build() -> dict[tuple[str, str], SignalPolicy]:
    policies: dict[tuple[str, str], SignalPolicy] = {}
    for pair in TABLE_FOR:
        _source, signal = pair
        if signal in STATE_SIGNALS:
            policies[pair] = SignalPolicy(
                kind=STATE,
                limits=None,
                step=None,
                spike=False,
                flatline=False,
                exact_repeat=False,
                flat_half_window=None,
                states=_STATES[signal],
            )
            continue
        commanded = signal in _COMMANDED
        nominal = NOMINAL_INTERVAL_S[pair]
        policies[pair] = SignalPolicy(
            kind=COMMANDED if commanded else MEASURED,
            limits=_LIMITS[signal],
            step=_STEP[signal],
            spike=not commanded,
            flatline=not commanded,
            exact_repeat=signal in _EXACT_REPEAT,
            flat_half_window=max(FLAT_MIN_HALF_WINDOW, math.ceil(FLAT_WINDOW_SECONDS / nominal)),
            states=None,
        )
    return policies


POLICY: dict[tuple[str, str], SignalPolicy] = _build()


def policy_table() -> dict:
    """The whole policy as plain data, in a fixed order. Its canonical JSON is fingerprinted."""
    return {
        "reason_codes": list(REASON_CODES),
        "note": NOTE_OUTSIDE_TYPICAL,
        "constants": {
            "spike_half_window": SPIKE_HALF_WINDOW,
            "spike_robust_factor": SPIKE_ROBUST_FACTOR,
            "spike_mad_scale": SPIKE_MAD_SCALE,
            "spike_floor_steps": SPIKE_FLOOR_STEPS,
            "flat_fraction": FLAT_FRACTION,
            "flat_window_seconds": FLAT_WINDOW_SECONDS,
            "flat_min_half_window": FLAT_MIN_HALF_WINDOW,
            "flat_min_run": FLAT_MIN_RUN,
            "gap_factor": GAP_FACTOR,
        },
        "signals": {
            f"{source}/{signal}": {
                "kind": p.kind,
                "limits": list(p.limits) if p.limits else None,
                "step": p.step,
                "spike": p.spike,
                "flatline": p.flatline,
                "exact_repeat": p.exact_repeat,
                "flat_half_window": p.flat_half_window,
                "states": list(p.states) if p.states else None,
            }
            for (source, signal), p in sorted(POLICY.items())
        },
    }


def policy_fingerprint() -> str:
    canonical = json.dumps(policy_table(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
