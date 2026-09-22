"""Tests for `scripts/init_influx.py`, per ADR-0011 and M1.md T4.

The retention-guard and request-body tests are pure — no server needed, and they run
even with no containers up. The database-creation tests need a live Core and reuse
`tests/conftest.py`'s `influx_client` fixture purely for its skip-on-unreachable
behaviour; they create the actual project databases (`dac_raw`, `dac_rollup`,
`dac_pinned`) rather than throwaway ones, since these are meant to persist for the rest
of M1/M2 — that is also why the idempotency check is "second call reports all three as
already existing," not "delete and recreate from scratch" (T12's full
`docker compose down -v` cycle is what actually proves the clean-stack case).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest

import scripts.init_influx as init_influx

# A fixed reference "now", not the real wall clock: makes the 90d-exclusion case
# deterministic regardless of when the suite runs. Chosen to sit in the same window as
# the rest of the project's documented timeline (ADR-0011, the U-13 spike).
FIXED_NOW = datetime(2026, 8, 31, tzinfo=UTC)

EXPERIMENTS = init_influx.load_experiments()


# ---------------------------------------------------------------------------
# parse_duration
# ---------------------------------------------------------------------------


def test_parse_duration_accepts_the_values_actually_used():
    assert init_influx.parse_duration("365d").days == 365
    assert init_influx.parse_duration("5y").days == 5 * 365
    assert init_influx.parse_duration("90d").days == 90
    assert init_influx.parse_duration("1h").total_seconds() == 3600


def test_parse_duration_rejects_plant_policy_shorthand():
    """'9mo' is the plant-policy *documentation* value, never a literal config value —
    the server itself rejects it (verified against influxdb:3.11.2-core: HTTP 400
    "invalid value: string \"9mo\", expected a duration"), so the local parser should
    reject it too rather than silently guessing what it means.
    """
    with pytest.raises(ValueError, match="unrecognised duration"):
        init_influx.parse_duration("9mo")


# ---------------------------------------------------------------------------
# The C-06 guard (V4) — pure, no server needed
# ---------------------------------------------------------------------------


def test_90d_retention_refuses_and_names_experiments_oldest_first():
    """cutoff = 2026-08-31 - 90d = 2026-06-02. Against that cutoff:

    EXP_004 2026-03-02  excluded (oldest)
    EXP_006 2026-04-20  excluded
    EXP_001 2026-05-04  excluded
    EXP_002 2026-05-11  excluded
    EXP_003 2026-05-18  excluded
    EXP_005 2026-06-15  clears (after cutoff)
    """
    with pytest.raises(RuntimeError) as exc_info:
        init_influx.assert_raw_retention_covers_experiments("90d", EXPERIMENTS, FIXED_NOW)

    message = str(exc_info.value)
    assert "EXP_004" in message
    excluded_ids = [
        exp["experiment_id"]
        for exp in init_influx.excluded_experiments(
            init_influx.parse_duration("90d"), EXPERIMENTS, FIXED_NOW
        )
    ]
    assert excluded_ids == ["EXP_004", "EXP_006", "EXP_001", "EXP_002", "EXP_003"]
    assert excluded_ids[0] == "EXP_004"
    assert "EXP_005" not in message


def test_365d_local_retention_clears_all_six_experiments():
    """The local default (.env.example): all six windows (2026-03-02 .. 2026-06-15)
    clear a year of margin against the same fixed reference date.
    """
    init_influx.assert_raw_retention_covers_experiments("365d", EXPERIMENTS, FIXED_NOW)


# ---------------------------------------------------------------------------
# create_database request construction — mocked transport, no server needed
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return b""


def test_dac_pinned_request_omits_retention_period_entirely(monkeypatch):
    """'no retention period at all, not a very large one' — checked at the request-body
    level: the key must be absent, not present-with-a-huge-value.
    """
    captured: dict = {}

    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    status = init_influx.create_database("http://x", "tok", "dac_pinned", None)

    assert status == "created"
    assert captured["body"] == {"db": "dac_pinned"}
    assert "retention_period" not in captured["body"]


def test_raw_and_rollup_requests_carry_retention_period(monkeypatch):
    captured: list[dict] = []

    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        captured.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    init_influx.create_database("http://x", "tok", "dac_raw", "365d")
    init_influx.create_database("http://x", "tok", "dac_rollup", "5y")

    assert captured[0] == {"db": "dac_raw", "retention_period": "365d"}
    assert captured[1] == {"db": "dac_rollup", "retention_period": "5y"}


def test_create_database_treats_409_as_already_exists(monkeypatch):
    """Confirmed against a live server: re-creating an existing database returns a
    plain HTTP 409 (unlike `create token --admin`'s exit-0-with-error-text-in-stdout
    quirk), so idempotency here is a status-code check, not text sniffing.
    """

    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert init_influx.create_database("http://x", "tok", "dac_raw", "365d") == "exists"


def test_create_database_raises_on_unexpected_status(monkeypatch):
    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        raise urllib.error.HTTPError(req.full_url, 422, "limit exceeded", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 422"):
        init_influx.create_database("http://x", "tok", "dac_pinned", None)


# ---------------------------------------------------------------------------
# Against a live Core (V4's end-to-end half)
# ---------------------------------------------------------------------------


@pytest.fixture()
def live_env(influx_client):  # noqa: ARG001 - depended on only for its skip-if-unreachable effect
    return init_influx.load_env()


def _live_database_names(host: str, token: str) -> set[str]:
    req = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database?format=json",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        rows = json.loads(resp.read().decode("utf-8"))
    return {row["iox::database"] for row in rows}


@pytest.mark.influx
def test_run_init_creates_the_three_databases_and_a_rerun_is_a_no_op(live_env):
    first = init_influx.run_init(env=live_env)

    assert set(first) == {"dac_raw", "dac_rollup", "dac_pinned"}
    assert all(status in ("created", "exists") for status in first.values())

    names = _live_database_names(live_env["INFLUX_HOST"], live_env["INFLUX_TOKEN"])
    assert {"dac_raw", "dac_rollup", "dac_pinned"} <= names

    second = init_influx.run_init(env=live_env)
    assert second == {"dac_raw": "exists", "dac_rollup": "exists", "dac_pinned": "exists"}
