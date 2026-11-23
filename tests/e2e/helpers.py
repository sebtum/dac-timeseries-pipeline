"""Helpers for end-to-end ingest tests: databases, the CLI, small input files.

These tests run `python -m scripts.ingest` as a subprocess against a live InfluxDB, always into
a throwaway database created and dropped per test (never `dac_raw`), so they cannot disturb the
real data or M2's reconciliation. Core allows 5 databases and the project uses 3, so a test
holds at most one throwaway database at a time.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from influxdb_client_3 import InfluxDBClient3

import scripts.init_influx as init_influx

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "ingest"
HEADER = ["timestamp", "experiment_id", "source", "signal", "value", "quality"]


def _request(method: str, path: str, body: dict | None = None) -> None:
    env = init_influx.load_env()
    request = urllib.request.Request(  # noqa: S310
        f"{env['INFLUX_HOST']}{path}",
        data=json.dumps(body).encode("utf-8") if body else None,
        method=method,
        headers={
            "Authorization": f"Bearer {env['INFLUX_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            response.read()
    except urllib.error.HTTPError as exc:
        if not (method == "DELETE" and exc.code == 404):
            raise


def create_database(name: str) -> None:
    _request("POST", "/api/v3/configure/database", {"db": name})


def drop_database(name: str) -> None:
    _request("DELETE", f"/api/v3/configure/database?db={name}")


def database_names() -> list[str]:
    env = init_influx.load_env()
    request = urllib.request.Request(  # noqa: S310
        f"{env['INFLUX_HOST']}/api/v3/configure/database?format=json",
        headers={"Authorization": f"Bearer {env['INFLUX_TOKEN']}"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        return [entry["iox::database"] for entry in json.loads(response.read())]


def query(database: str, sql: str) -> list[dict]:
    env = init_influx.load_env()
    client = InfluxDBClient3(host=env["INFLUX_HOST"], token=env["INFLUX_TOKEN"], database=database)
    try:
        return [
            {k: str(v) if k == "time" else v for k, v in row.items()}
            for row in client.query(sql, language="sql").to_pylist()
        ]
    finally:
        client.close()


def tables(database: str) -> list[str]:
    rows = query(
        database,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'iox' "
        "ORDER BY table_name",
    )
    return [r["table_name"] for r in rows]


def dump(database: str) -> dict[str, list[dict]]:
    """Everything the ingest stored, in a stable order, for before/after comparisons."""
    present = tables(database)
    out: dict[str, list[dict]] = {}
    for table in ("readings_numeric", "readings_state", "readings_conflicts"):
        order = "signal, time, discard_rank" if table == "readings_conflicts" else "signal, time"
        out[table] = (
            query(database, f"SELECT * FROM {table} ORDER BY experiment_id, {order}")  # noqa: S608
            if table in present
            else []
        )
    return out


def write_input(directory: Path, rows: list[list[str]], name: str = "in") -> dict[str, Path]:
    """Write a small CSV with its `.sha256`; experiments come from the shared fixture."""
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / f"{name}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)
    sha_path = directory / f"{name}.sha256"
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {csv_path.name}\n", encoding="utf-8")
    return {"csv": csv_path, "sha256": sha_path, "experiments": FIXTURES / "experiments.json"}


def run_ingest(
    files: dict[str, Path], database: str, report_dir: Path, *extra: str
) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.ingest",
            "--csv",
            str(files["csv"]),
            "--experiments",
            str(files["experiments"]),
            "--sha256",
            str(files["sha256"]),
            "--database",
            database,
            "--report-dir",
            str(report_dir),
            *extra,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def read_summary(report_dir: Path) -> dict:
    return json.loads((report_dir / "ingest_summary.json").read_text(encoding="utf-8"))


def fixture_files() -> dict[str, Path]:
    return {
        "csv": FIXTURES / "slice.csv",
        "sha256": FIXTURES / "slice.sha256",
        "experiments": FIXTURES / "experiments.json",
    }
