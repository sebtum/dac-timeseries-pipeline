"""Bootstrap the InfluxDB 3 Core admin token into a gitignored `.env`.

Why this exists (ADR-0009 exception 1): InfluxDB 3 Core does not mint an admin token on
first boot — auth is on from the moment the server starts, and every endpoint including
`/health` returns 401 until a token is explicitly created (docs/spikes/U-13-core-token-
bootstrap.md). This script creates that token non-interactively and idempotently, since the
compose file (ADR-0008) never runs `influxdb3 create token --admin` for you.

Why `docker exec` + the CLI, not `influxdb3-python` / a raw HTTP call (ADR-0003/ADR-0004
otherwise prefer the Python client over shelling out): the spike verified `influxdb3 create
token --admin` as a CLI command; no documented HTTP endpoint for *creating* the initial admin
token was found (the endpoint the CLI itself calls isn't part of the public HTTP API this
project queries against — that's reached only once a token already exists). The CLI ships
inside the image and nowhere else, so `docker exec` is the only non-interactive path available
without adding an `influxdb3` binary to the host. Once a token exists, all *other* interaction
with the server (writes, queries, database/token administration) goes through
`influxdb3-python` / HTTP as ADR-0003/ADR-0004 require — this script is the one deliberate
exception, scoped to the one operation the CLI alone can do.

Idempotency (spike finding, confirmed again while writing this script): a second
`create token --admin` call does not fail via a nonzero exit code — the CLI exits 0 either
way and prints a plain-text error to stdout (not stderr, and not JSON despite `--format json`
being requested) reading `Failed to create token, error: ApiError { code: 409, message:
"token name already exists, _admin", ... }`. Idempotency detection therefore has to pattern-
match stdout text, not rely on the process exit code or parse JSON unconditionally. This is a
new finding beyond the spike (worth a MISTAKES.md entry per the T2 handoff) — the spike only
showed the 409 message appearing, not that the exit code stays 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

CONTAINER_NAME = os.environ.get("INFLUX_CONTAINER_NAME", "dac-influxdb")
INFLUX_HOST = os.environ.get("INFLUX_HOST", "http://localhost:8181")
WAIT_TIMEOUT_S = 60
WAIT_POLL_INTERVAL_S = 1.5


def read_env_lines() -> list[str]:
    """Return the current .env's lines, seeding it from .env.example if .env is absent yet."""
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    if not ENV_EXAMPLE_PATH.exists():
        raise FileNotFoundError(f"{ENV_EXAMPLE_PATH} not found; cannot seed .env")
    return ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()


def parse_env(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def write_env_with_token(lines: list[str], token: str) -> None:
    """Rewrite .env with INFLUX_TOKEN set, preserving every other line (comments included)."""
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith("INFLUX_TOKEN="):
            new_lines.append(f"INFLUX_TOKEN={token}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"INFLUX_TOKEN={token}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def wait_for_influx_reachable(host: str, timeout_s: float) -> None:
    """Poll the unauthenticated /health endpoint until it answers or the timeout expires.

    /health is reachable without a token because the compose command passes
    `--disable-authz health` (see docker-compose.yml) — every other endpoint still requires
    the bootstrapped admin token.
    """
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{host}/health", timeout=5) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        time.sleep(WAIT_POLL_INTERVAL_S)
    raise TimeoutError(
        f"InfluxDB at {host} did not become reachable within {timeout_s}s "
        f"(container {CONTAINER_NAME!r} running?): {last_error}"
    )


def token_is_valid(host: str, token: str) -> bool:
    """Check an existing token by hitting an endpoint that requires auth (unlike /health)."""
    req = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database?format=json",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            return resp.status == 200
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError:
        return False


def create_admin_token_via_docker_exec() -> str | None:
    """Run `influxdb3 create token --admin` inside the container.

    Returns the new token on success, or None if the server reports the admin token already
    exists (409 — see module docstring on why this can't be detected via exit code).
    Raises RuntimeError on any other failure.
    """
    result = subprocess.run(  # noqa: S603
        [
            "docker",
            "exec",
            CONTAINER_NAME,
            "influxdb3",
            "create",
            "token",
            "--admin",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = result.stdout.strip()

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = None

    if payload is not None and "token" in payload:
        return payload["token"]

    if "already exists" in stdout or "409" in stdout:
        return None

    raise RuntimeError(
        f"influxdb3 create token --admin failed unexpectedly "
        f"(exit={result.returncode}): stdout={stdout!r} stderr={result.stderr!r}"
    )


def main() -> int:
    lines = read_env_lines()
    env = parse_env(lines)
    existing_token = env.get("INFLUX_TOKEN", "").strip()
    host = env.get("INFLUX_HOST", INFLUX_HOST).strip() or INFLUX_HOST

    wait_for_influx_reachable(host, WAIT_TIMEOUT_S)

    if existing_token and token_is_valid(host, existing_token):
        print("token already exists, nothing to do")
        return 0

    token = create_admin_token_via_docker_exec()

    if token is None:
        if existing_token:
            print(
                f"The token recorded in {ENV_PATH} does not authenticate, and the server "
                "reports an admin token already exists (name collision) rather than handing "
                "us its value. The local token is stale or wrong and cannot be recovered by "
                "this script. This script will not run --regenerate automatically because "
                "that invalidates the existing token. If you intend to invalidate it, run "
                "inside the container: "
                "`influxdb3 create token --admin --regenerate --format json`, "
                "then set INFLUX_TOKEN in .env to the printed value.",
                file=sys.stderr,
            )
            return 1
        print(
            "Admin token already exists on the server, but no valid token is recorded "
            f"locally in {ENV_PATH}. This script will not run --regenerate automatically "
            "because that invalidates the existing token. If you intend to invalidate it, "
            "run inside the container: "
            "`influxdb3 create token --admin --regenerate --format json`, "
            "then set INFLUX_TOKEN in .env to the printed value.",
            file=sys.stderr,
        )
        return 1

    write_env_with_token(lines, token)
    print(f"bootstrapped new admin token into {ENV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
