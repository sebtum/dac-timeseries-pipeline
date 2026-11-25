"""Helpers for the dashboard tests: a Grafana client, throwaway datasources and schemas, the
fixture pipeline and the checker CLI.

Nothing here touches `dac_raw`. A test creates one throwaway InfluxDB database (see
`tests/e2e/helpers.py`), points a temporary Grafana datasource at it (`temp_influx_datasource`,
deleted on exit) and a throwaway Postgres schema (`prepare_pg_schema` / `drop_pg_schema`), then
passes `--var influx=<uid> --var pg_schema=<schema>` to the checker (`run_checker`). Core allows
five databases and four exist, so a test holds at most one extra one.

Grafana comes from `.env` (`GRAFANA_URL`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`); a
`GRAFANA_*` variable in the process environment wins, which is how CI and a one-off Grafana on
another port are pointed at.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest

import scripts.init_influx as init_influx
import scripts.migrate as migrate
from pipeline.grafana_check import CheckError, GrafanaClient, read_env
from pipeline.metadata_loader import load_experiments
from pipeline.pg_migrate import run_migrations

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
GRAFANA_FIXTURE = FIXTURES / "grafana"
DEFAULT_GRAFANA_URL = "http://localhost:3000"
PIPELINE_STEPS = ("ingest", "clean", "metrics", "compare", "load_comparison")
# `scripts.metrics` ends 1 when a metric is only partly covered, which the fixtures do on purpose.
ACCEPTED_EXIT = {"metrics": (0, 1)}


def grafana_settings() -> dict[str, str]:
    env = read_env()
    for key, value in os.environ.items():
        if key.startswith("GRAFANA_"):
            env[key] = value
    return env


def grafana_client() -> GrafanaClient:
    """A client for the Grafana named in `.env` (see the module docstring)."""
    env = grafana_settings()
    return GrafanaClient(
        env.get("GRAFANA_URL", DEFAULT_GRAFANA_URL),
        env.get("GRAFANA_ADMIN_USER", ""),
        env.get("GRAFANA_ADMIN_PASSWORD", ""),
        timeout=30,
    )


def grafana_unreachable_reason() -> str | None:
    """Why Grafana cannot be used (unreachable, login refused), or None when it can."""
    try:
        grafana_client().health()
    except CheckError as exc:
        return str(exc)
    return None


def require_grafana() -> GrafanaClient:
    """The Grafana client, or a skip when Grafana cannot be used (unreachable, login refused)."""
    reason = grafana_unreachable_reason()
    if reason is not None:
        pytest.skip(f"Grafana not usable: {reason}")
    return grafana_client()


@contextmanager
def temp_influx_datasource(database: str) -> Iterator[str]:
    """A temporary Grafana datasource on `database`; yields its uid and deletes it afterwards."""
    client = grafana_client()
    uid = client.create_influx_datasource(f"tmp-{database}", database)
    try:
        yield uid
    finally:
        client.delete_datasource(uid)


def write_line_protocol(database: str, lines: list[str]) -> None:
    """Write line protocol into a (throwaway) database; the whole batch or an error."""
    env = init_influx.load_env()
    request = urllib.request.Request(  # noqa: S310
        f"{env['INFLUX_HOST']}/api/v3/write_lp?db={database}&precision=nanosecond"
        "&accept_partial=false",
        data="\n".join(lines).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {env['INFLUX_TOKEN']}", "Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        response.read()


def _pg_kwargs(schema: str | None = None) -> dict[str, str]:
    kwargs = migrate.connect_kwargs(migrate.load_env())
    if schema:
        kwargs["options"] = f"-c search_path={schema}"
    return kwargs


def prepare_pg_schema(schema: str, experiments_file: Path) -> None:
    """Create `schema`, apply migrations 0001 to 0004 in it and load the experiments file."""
    with psycopg.connect(**_pg_kwargs(), autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    kwargs = _pg_kwargs(schema)
    run_migrations(kwargs)
    load_experiments(kwargs, Path(experiments_file))


def drop_pg_schema(schema: str) -> None:
    with psycopg.connect(**_pg_kwargs(), autocommit=True) as conn:
        conn.execute(
            psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                psycopg.sql.Identifier(schema)
            )
        )


def _module(module: str, *args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", module, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def run_pipeline(
    fixture_dir: Path,
    database: str,
    schema: str,
    work_dir: Path,
    steps: tuple[str, ...] = PIPELINE_STEPS,
) -> dict[str, subprocess.CompletedProcess]:
    """Run the pipeline CLIs on a fixture (`readings.csv`, `readings.sha256`, `experiments.json`).

    `steps` are run in the order given (`ingest`, `clean`, `metrics`, `compare`,
    `load_comparison`), each with its own report directory under `work_dir`. A step that exits
    outside its accepted codes raises `AssertionError` with its output.
    """
    fixture_dir = Path(fixture_dir)
    work_dir = Path(work_dir)
    experiments = str(fixture_dir / "experiments.json")
    commands: dict[str, list[str]] = {
        "ingest": [
            "--csv",
            str(fixture_dir / "readings.csv"),
            "--experiments",
            experiments,
            "--sha256",
            str(fixture_dir / "readings.sha256"),
            "--database",
            database,
            "--report-dir",
            str(work_dir / "ingest"),
        ],
        "clean": [
            "--database",
            database,
            "--experiments",
            experiments,
            "--report-dir",
            str(work_dir / "clean"),
        ],
        "metrics": [
            "--database",
            database,
            "--experiments",
            experiments,
            "--pg-schema",
            schema,
            "--report-dir",
            str(work_dir / "metrics"),
        ],
        "compare": [
            "--database",
            database,
            "--experiments",
            experiments,
            "--pg-schema",
            schema,
            "--report-dir",
            str(work_dir / "compare"),
        ],
        "load_comparison": [
            "--summary",
            str(work_dir / "compare" / "comparison_summary.json"),
            "--pg-schema",
            schema,
        ],
    }
    results: dict[str, subprocess.CompletedProcess] = {}
    for step in steps:
        if step not in commands:
            raise ValueError(f"unknown pipeline step {step!r}; known: {', '.join(PIPELINE_STEPS)}")
        result = _module(f"scripts.{step}", *commands[step])
        results[step] = result
        if result.returncode not in ACCEPTED_EXIT.get(step, (0,)):
            raise AssertionError(
                f"scripts.{step} exited {result.returncode}:\n{result.stdout}\n{result.stderr}"
            )
    return results


def run_checker(*args: str) -> tuple[int, dict | None]:
    """Run `python -m scripts.check_dashboards` with `args`; return (exit code, parsed report).

    The report goes to a temporary directory unless `--report-dir` is given. It is None when the
    command wrote no file (exit 2, or a bad argument).
    """
    arguments = list(args)
    holder = None
    if "--report-dir" in arguments:
        report_dir = Path(arguments[arguments.index("--report-dir") + 1])
    else:
        holder = tempfile.TemporaryDirectory()
        report_dir = Path(holder.name)
        arguments += ["--report-dir", str(report_dir)]
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "scripts.check_dashboards", *arguments],
            cwd=REPO_ROOT,
            env={**os.environ, **{k: v for k, v in grafana_settings().items()}},
            capture_output=True,
            text=True,
            check=False,
            timeout=1800,
        )
        report = report_dir / "dashboard_check.json"
        parsed = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        run_checker.last = result  # type: ignore[attr-defined]  # stdout/stderr for assertion messages
        return result.returncode, parsed
    finally:
        if holder is not None:
            holder.cleanup()
