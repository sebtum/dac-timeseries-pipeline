"""Idempotently create the three InfluxDB 3 Core databases M1's schema needs.

InfluxDB 3 Core has no declarative database configuration (ADR-0009) — "as code" here
means this script, run once against a fresh stack and safely re-runnable. Retention is
read entirely from the environment (ADR-0011: "a parameter of the init script, not a
constant in it"); no retention literal appears below.

HTTP path, not the CLI (standing assumption 2 in docs/plans/M1.md): `POST
/api/v3/configure/database` creates a database and accepts an optional
`retention_period` duration string in the same request body, verified directly against
`influxdb:3.11.2-core` while writing this script (docker exec logs confirmed
`CreateDatabaseOptions { retention_period: Some(31536000s) }` for a `365d` request).
Unlike `create token --admin` (docs/spikes/U-13-core-token-bootstrap.md), a second
create call against an existing database returns a plain HTTP 409 — no exit-code-0
plain-text-error quirk — so idempotency here is a straightforward status check. This is
a new finding beyond T1's spike, which only exercised `create database
--retention-period` via the CLI: the HTTP API turns out not to be CLI-only after all.

New finding, unrelated to any ADR, worth a handoff flag: Core enforces a hard ceiling of
5 non-internal databases (confirmed empirically: a 6th create call returned HTTP 422
"Adding a new database would exceed limit of 5 databases", matching InfluxData's
published Core-vs-Enterprise limits). `dac_raw` + `dac_rollup` + `dac_pinned` is 3, so
M1 is nowhere near it, but a future 4th distinct-retention tier would need Enterprise
or reclaiming a slot. Also confirmed on this build: deleting a database *does* free its
slot (an upstream bug where deleted databases still counted, influxdata/influxdb#25701,
does not reproduce on 3.11.2) — relevant to T5's throwaway-database teardown pattern
being safe to repeat across CI runs.

Before `dac_raw` is created, the script computes `now - INFLUX_RAW_RETENTION` and
refuses if that cutoff falls after any experiment's `start_time` in
`data/raw/experiments.json` — C-06 (MISTAKES.md) turned into code. A retention period
is a claim about age relative to *now*; the failure mode of an inadequate one is a
silent, invisible-at-write-time exclusion, so the guard runs before any write happens.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
EXPERIMENTS_PATH = REPO_ROOT / "data" / "raw" / "experiments.json"

DATABASES = ("dac_raw", "dac_rollup", "dac_pinned")

_DURATION_RE = re.compile(r"^(\d+)(y|w|d|h|m|s)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400, "y": 365 * 86400}


def load_env() -> dict[str, str]:
    """Parse `.env` into a dict; returns {} if it doesn't exist (nothing bootstrapped yet)."""
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def parse_duration(value: str) -> timedelta:
    """Parse a duration string like '365d', '5y', '90d', '1h' into a timedelta.

    Deliberately not the full set the server's own parser accepts or rejects (it takes
    '365d'/'5y' but rejects '9mo', confirmed empirically) — this only needs to parse
    values that are actually ever assigned to the retention env vars.
    """
    match = _DURATION_RE.match(value.strip())
    if not match:
        raise ValueError(f"unrecognised duration {value!r} (expected e.g. '365d', '5y', '90d')")
    amount, unit = match.groups()
    return timedelta(seconds=int(amount) * _UNIT_SECONDS[unit])


def load_experiments(path: Path = EXPERIMENTS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def excluded_experiments(
    retention: timedelta, experiments: list[dict], now: datetime
) -> list[dict]:
    """Experiments whose start_time falls before the retention window, oldest first."""
    cutoff = now - retention
    excluded = [exp for exp in experiments if datetime.fromisoformat(exp["start_time"]) < cutoff]
    return sorted(excluded, key=lambda exp: exp["start_time"])


def assert_raw_retention_covers_experiments(
    retention_str: str, experiments: list[dict], now: datetime
) -> None:
    excluded = excluded_experiments(parse_duration(retention_str), experiments, now)
    if excluded:
        names = ", ".join(exp["experiment_id"] for exp in excluded)
        raise RuntimeError(
            f"INFLUX_RAW_RETENTION={retention_str} would silently exclude "
            f"{len(excluded)} experiment(s) whose start_time falls outside the "
            f"retention window (as of {now.isoformat()}): {names}. Refusing to create "
            "dac_raw — a retention period is a claim about age relative to now, and "
            "this would hide historical data with no error at write time (MISTAKES.md C-06)."
        )


def create_database(host: str, token: str, name: str, retention: str | None) -> str:
    """Create `name`, returning 'created' or 'exists'. Raises RuntimeError on any other failure."""
    body: dict[str, str] = {"db": name}
    if retention:
        body["retention_period"] = retention
    req = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            resp.read()
            return "created"
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return "exists"
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"failed to create database {name!r}: HTTP {exc.code} {detail}") from exc


def run_init(env: dict[str, str] | None = None, now: datetime | None = None) -> dict[str, str]:
    """Create dac_raw, dac_rollup, dac_pinned; returns {name: 'created' | 'exists'}."""
    env = load_env() if env is None else env
    now = datetime.now(UTC) if now is None else now

    host = env.get("INFLUX_HOST", "").strip()
    token = env.get("INFLUX_TOKEN", "").strip()
    if not host or not token:
        raise RuntimeError(
            "INFLUX_HOST/INFLUX_TOKEN not set — run scripts/bootstrap_influx_token.py first"
        )

    raw_retention = env.get("INFLUX_RAW_RETENTION", "").strip()
    rollup_retention = env.get("INFLUX_ROLLUP_RETENTION", "").strip()
    pinned_retention = env.get("INFLUX_PINNED_RETENTION", "").strip()
    if not raw_retention or not rollup_retention:
        raise RuntimeError(
            "INFLUX_RAW_RETENTION and INFLUX_ROLLUP_RETENTION must both be set in .env "
            "(no default lives in source — ADR-0011)"
        )

    assert_raw_retention_covers_experiments(raw_retention, load_experiments(), now)

    return {
        "dac_raw": create_database(host, token, "dac_raw", raw_retention),
        "dac_rollup": create_database(host, token, "dac_rollup", rollup_retention),
        "dac_pinned": create_database(host, token, "dac_pinned", pinned_retention or None),
    }


def main() -> int:
    try:
        results = run_init()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for name, status in results.items():
        label = "created" if status == "created" else "already exists, nothing to do"
        print(f"{name}: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
