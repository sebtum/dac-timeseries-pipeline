"""Unit tests for the declared cleaning policy (M3, S3.24): complete, consistent, versioned."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from pipeline import cleaning_policy as policy
from pipeline.signals import (
    DOCUMENTED_RANGE,
    NOMINAL_INTERVAL_S,
    NUMERIC_TABLE,
    STATE_SIGNALS,
    TABLE_FOR,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE = REPO_ROOT / "reports" / "post_ingest_profile.json"

# The fingerprint pinned for POLICY_VERSION. Editing any number in the policy table changes the
# fingerprint, so the test fails until this line and the version string are updated together.
PINNED_VERSION = "m3-v1"
PINNED_FINGERPRINT = "2b004502602bfb8e9cc70a041f65853c1cc568d4223a42c8c2f1c527c49358bb"

NUMERIC_PAIRS = [pair for pair, table in TABLE_FOR.items() if table == NUMERIC_TABLE]
STATE_PAIRS = [pair for pair in TABLE_FOR if pair[1] in STATE_SIGNALS]


def test_policy_covers_all_25_pairs() -> None:
    assert len(TABLE_FOR) == 25
    assert set(policy.POLICY) == set(TABLE_FOR)
    assert len(NUMERIC_PAIRS) == 23
    assert len(STATE_PAIRS) == 2


def test_numeric_policies_are_complete() -> None:
    for pair in NUMERIC_PAIRS:
        rules = policy.POLICY[pair]
        assert rules.limits is not None and rules.limits[0] < rules.limits[1], pair
        assert rules.step is not None and rules.step >= 0, pair
        assert rules.states is None, pair
        assert rules.flat_half_window is not None and rules.flat_half_window >= 5, pair


def test_state_policies_declare_states_and_no_numeric_rules() -> None:
    expected = {
        "valve_state": {"CLOSED", "OPEN"},
        "process_state": {"LOAD_CHANGE", "SHUTDOWN", "STARTUP", "STEADY_STATE"},
    }
    for pair in STATE_PAIRS:
        rules = policy.POLICY[pair]
        assert set(rules.states) == expected[pair[1]]
        assert rules.limits is None and rules.step is None
        assert not rules.spike and not rules.flatline and not rules.exact_repeat


def test_physical_limits_contain_the_documented_typical_range() -> None:
    for pair in NUMERIC_PAIRS:
        low, high = policy.POLICY[pair].limits
        doc_low, doc_high, _unit = DOCUMENTED_RANGE[pair]
        assert low <= doc_low and doc_high <= high, pair


def test_limits_match_the_decision_table() -> None:
    # Spot values from decision 9; the full table is the fingerprint.
    limits = {pair[1]: policy.POLICY[pair].limits for pair in NUMERIC_PAIRS}
    assert limits["solvent_pH"] == (0.0, 14.0)
    assert limits["current"] == (-2.0, 500.0)
    assert limits["power"] == (-100.0, 60000.0)
    assert limits["ambient_temperature"] == (-40.0, 60.0)
    assert limits["available_solar_power"] == (0.0, 1000.0)


def test_step_size_is_the_median_of_the_profile_medians() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    per_signal: dict[str, list[float]] = defaultdict(list)
    for series in profile["series"]:
        if series["differences"] is not None:
            per_signal[series["signal"]].append(series["differences"]["median_abs"])
    for pair in NUMERIC_PAIRS:
        medians = per_signal[pair[1]]
        assert len(medians) == 6, pair
        expected = float(f"{statistics.median(medians):.9g}")
        assert policy.POLICY[pair].step == expected, pair


def test_rule_applicability() -> None:
    for pair in NUMERIC_PAIRS:
        rules = policy.POLICY[pair]
        commanded = pair[1] == "current_setpoint"
        assert rules.spike is not commanded, pair
        assert rules.flatline is not commanded, pair
        assert rules.exact_repeat is (pair[1] == "available_solar_power"), pair
    assert policy.POLICY[("hydrolyzer", "current_setpoint")].kind == policy.COMMANDED


def test_flat_half_window_follows_the_nominal_interval() -> None:
    expected = {1.0: 30, 2.0: 15, 5.0: 6, 60.0: 5}
    for pair in NUMERIC_PAIRS:
        assert policy.POLICY[pair].flat_half_window == expected[NOMINAL_INTERVAL_S[pair]], pair


def test_flatline_constants() -> None:
    assert policy.FLAT_MIN_RUN == 5
    assert policy.FLAT_FRACTION == 0.2


def test_reason_priority_order() -> None:
    assert policy.REASON_CODES == (
        "no_value",
        "flag_bad",
        "flag_uncertain",
        "outside_physical_limits",
        "unknown_state",
        "conflicting_duplicate",
        "spike",
        "flatline",
    )
    assert policy.FLAG_CODES[-1] == policy.NOTE_OUTSIDE_TYPICAL
    assert policy.NOTE_OUTSIDE_TYPICAL not in policy.REASON_CODES


def test_table_includes_the_flatline_amendments() -> None:
    table = policy.policy_table()
    assert table["constants"]["flat_min_run"] == policy.FLAT_MIN_RUN
    solar = table["signals"]["ambient/available_solar_power"]
    assert solar["exact_repeat"] is True
    assert table["signals"]["absorber/air_flow"]["exact_repeat"] is False


def test_fingerprint_is_stable_and_pinned_to_the_version() -> None:
    assert policy.POLICY_VERSION == PINNED_VERSION
    assert policy.policy_fingerprint() == policy.policy_fingerprint()
    assert policy.policy_fingerprint() == PINNED_FINGERPRINT


def test_fingerprint_changes_when_a_number_changes(monkeypatch) -> None:
    monkeypatch.setattr(policy, "FLAT_MIN_RUN", 4)
    assert policy.policy_fingerprint() != PINNED_FINGERPRINT
