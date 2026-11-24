"""The metrics batch job (M4): refuse, compute, write, read back, report.

`python -m scripts.metrics` calls `run` here. The order is decision 17 of M4:

1. refusal checks (nothing is written, the report directory is not touched);
2. compute everything for every experiment from the accepted readings;
3. write the four derived series into InfluxDB (`metrics_series`);
4. write the two Postgres tables in one transaction;
5. read the counts back and compare them with what was written;
6. write `metrics_summary.json` and `metrics_report.md`.

The report is a pure function of the summary (`render_report`), and the summary is the only input
to it, so the two files cannot disagree. Nothing time-varying is in the report; `timing` lives in
the summary only.

    0  written and read back, every plausibility check passed or was not computable
    1  written and read back, at least one plausibility check failed (outputs are written)
    2  refused, nothing written (database missing, no cleaned rows for the policy version,
       experiments file unreadable, Postgres not configured or not reachable, migration 0003
       not applied, an experiment missing from Postgres `experiment`)
    3  a query or a write failed; no outputs
    4  written, but a read-back count differs or an input table changed; outputs are written
       and list the mismatches
    70 internal error (a bug; see `scripts/metrics.py`)
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from pipeline import metrics, metrics_store
from pipeline.cleaning import instant_text
from pipeline.cleaning_influx import PROCESSED_TABLE
from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.ingest import Experiment, load_experiment_windows, timestamp_ns
from pipeline.ingest_influx import (
    DatabaseCheckFailed,
    WriteFailed,
    list_databases,
)
from pipeline.metrics import (
    METRIC_UNITS,
    METRICS_VERSION,
    POLICY,
    ExperimentInputs,
    ExperimentResult,
)
from pipeline.profiling_sql import QueryFailed
from scripts.init_influx import load_env
from scripts.migrate import connect_kwargs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "raw" / "experiments.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_DATABASE = "dac_raw"
DEFAULT_PG_SCHEMA = "public"

EXIT_FAILED_PLAUSIBILITY = 1
EXIT_REFUSED = 2
EXIT_FAILED = 3
EXIT_UNBALANCED = 4
EXIT_INTERNAL_ERROR = 70

JSON_NAME = "metrics_summary.json"
MARKDOWN_NAME = "metrics_report.md"

SCHEMA_VERSION = 1

# Accepted input series of one experiment, by the field of `ExperimentInputs` they fill.
INPUT_SIGNALS: dict[str, str] = {
    "voltage": "voltage",
    "current": "current",
    "power": "power",
    "co2_in": "co2_in_ppm",
    "co2_out": "co2_out_ppm",
    "air_flow": "air_flow",
    "temperature": "ambient_temperature",
    "pressure": "ambient_pressure",
}


@dataclass(frozen=True)
class Config:
    database: str = DEFAULT_DATABASE
    experiments_path: Path = DEFAULT_EXPERIMENTS
    report_dir: Path = DEFAULT_REPORT_DIR
    policy_version: str = POLICY_VERSION
    pg_schema: str = DEFAULT_PG_SCHEMA


@dataclass
class Deps:
    """Everything the run reaches outside itself for; tests substitute these."""

    list_databases: Callable[[str, str], list[str]] = list_databases
    gateway_factory: Callable[[str, str, str], Any] = metrics_store.MetricsGateway
    pg_connect: Callable[[dict[str, str], str], Any] = metrics_store.pg_connect
    pg_check: Callable[[Any], str | None] = metrics_store.pg_check
    missing_experiments: Callable[[Any, list[str]], list[str]] = metrics_store.missing_experiments
    write_postgres: Callable[[Any, list[dict], list[dict]], None] = metrics_store.write_postgres
    count_rows: Callable[[Any, str, str], dict[str, int]] = metrics_store.count_rows
    env: dict[str, str] | None = None
    clock: Callable[[], float] = field(default=time.monotonic)


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass
class Computed:
    """One experiment's results, kept until everything has been computed."""

    window: Experiment
    duration_s: float
    result: ExperimentResult
    signals: list[dict]
    plausibility: list[dict]


# ----------------------------------------------------------------------------- summary shaping


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def round_floats(value: Any) -> Any:
    """Floats to 9 significant digits, recursively; ints, bools, strings and None unchanged."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return float(f"{value:.9g}")
    if isinstance(value, dict):
        return {k: round_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v) for v in value]
    return value


def _number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def experiment_entry(item: Computed) -> dict[str, Any]:
    window = item.window
    result = item.result
    return {
        "experiment_id": window.experiment_id,
        "start": instant_text(timestamp_ns(window.start)),
        "end": instant_text(timestamp_ns(window.end)),
        "duration_s": _number(item.duration_s),
        "metrics": {name: dict(result.metrics[name]) for name in METRIC_UNITS},
        "power_check": dict(result.power_check),
        "efficiency_check": dict(result.efficiency_check),
        "series_written": result.series_written(),
        "signals": [dict(row) for row in item.signals],
        "plausibility": [dict(row) for row in item.plausibility],
    }


def build_summary(
    config: Config,
    computed: list[Computed],
    reconciliation: dict[str, Any],
    timing: dict[str, Any],
) -> dict[str, Any]:
    entries = sorted(
        (experiment_entry(item) for item in computed), key=lambda e: e["experiment_id"]
    )
    failed = sum(1 for e in entries for row in e["plausibility"] if row["passed"] is False)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "metrics_version": METRICS_VERSION,
        "policy_version": config.policy_version,
        "source": {
            "database": config.database,
            "experiments_file": display_path(config.experiments_path),
            "pg_schema": config.pg_schema,
        },
        "parameters": {},
        "experiments": entries,
        "plausibility_failed": failed,
        "reconciliation": reconciliation,
        "timing": timing,
    }
    summary = round_floats(summary)
    summary["parameters"] = dict(POLICY)  # the policy as declared, not rounded
    return summary


def metric_rows(config: Config, item: Computed) -> list[dict[str, Any]]:
    experiment_id = item.window.experiment_id
    return [
        {
            "experiment_id": experiment_id,
            "metrics_version": METRICS_VERSION,
            "policy_version": config.policy_version,
            "metric": name,
            "value": item.result.metrics[name]["value"],
            "unit": item.result.metrics[name]["unit"],
            "coverage": item.result.metrics[name]["coverage"],
            "status": item.result.metrics[name]["status"],
        }
        for name in METRIC_UNITS
    ]


def quality_rows(config: Config, item: Computed) -> list[dict[str, Any]]:
    experiment_id = item.window.experiment_id
    return [
        {
            "experiment_id": experiment_id,
            "metrics_version": METRICS_VERSION,
            "policy_version": config.policy_version,
            **row,
        }
        for row in item.signals
    ]


# ----------------------------------------------------------------------------------- report


def _cell(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.9g}"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows]
    return lines


def render_report(summary: dict[str, Any]) -> str:
    """The report as Markdown, from the summary alone (a pure function of it)."""
    recon = summary["reconciliation"]
    out = [
        "# Metrics report",
        "",
        f"Metrics version `{summary['metrics_version']}`, cleaning policy "
        f"`{summary['policy_version']}`, database `{summary['source']['database']}`, "
        f"Postgres schema `{summary['source']['pg_schema']}`. Generated by "
        "`python -m scripts.metrics`; the numbers are the ones in `metrics_summary.json`.",
        "",
        "## Run checks",
        "",
        *_table(
            ["Check", "Result"],
            [
                ["plausibility checks failed", summary["plausibility_failed"]],
                ["series counts read back from InfluxDB", recon["influx_series_checked"]],
                ["rows read back from Postgres", recon["postgres_rows_checked"]],
                ["written counts equal read-back counts", recon["balanced"]],
                ["input tables unchanged (counts before = after)", recon["inputs_unchanged"]],
            ],
        ),
        "",
    ]
    for mismatch in recon["mismatches"]:
        out.append(
            f"- mismatch in {mismatch['store']} for {mismatch['experiment_id']}, "
            f"{mismatch['name']}: written {mismatch['written']}, read back "
            f"{mismatch['read_back']}"
        )
    if recon["mismatches"]:
        out.append("")

    for entry in summary["experiments"]:
        out += [
            f"## {entry['experiment_id']}",
            "",
            f"From {entry['start']} to {entry['end']} ({_cell(entry['duration_s'])} s).",
            "",
            "### Metrics",
            "",
            *_table(
                ["Metric", "Value", "Unit", "Coverage", "Status"],
                [
                    [name, m["value"], m["unit"], m["coverage"], m["status"]]
                    for name, m in entry["metrics"].items()
                ],
            ),
            "",
            "### Power check (logged power against voltage x current)",
            "",
            *_table(["Measure", "Value"], [[k, v] for k, v in entry["power_check"].items()]),
            "",
            "### Capture efficiency check",
            "",
            *_table(["Measure", "Value"], [[k, v] for k, v in entry["efficiency_check"].items()]),
            "",
            "### Series written to metrics_series",
            "",
            *_table(["Series", "Points"], [[k, v] for k, v in entry["series_written"].items()]),
            "",
            "### Plausibility",
            "",
            *_table(
                ["Check", "Passed", "Value", "Limit"],
                [[p["check"], p["passed"], p["value"], p["limit"]] for p in entry["plausibility"]],
            ),
            "",
            "### Data quality per signal",
            "",
            *_table(
                [
                    "Source",
                    "Signal",
                    "Present",
                    "Expected",
                    "Accepted",
                    "BAD",
                    "UNCERTAIN",
                    "Completeness",
                    "Valid",
                    "BAD share",
                    "UNCERTAIN share",
                ],
                [
                    [
                        s["source"],
                        s["signal"],
                        s["present"],
                        s["expected"],
                        s["accepted"],
                        s["bad"],
                        s["uncertain"],
                        s["completeness"],
                        s["valid_fraction"],
                        s["bad_fraction"],
                        s["uncertain_fraction"],
                    ]
                    for s in entry["signals"]
                ],
            ),
            "",
        ]
    out += [
        "## Parameters",
        "",
        *_table(["Name", "Value"], [[k, v] for k, v in summary["parameters"].items()]),
        "",
    ]
    return "\n".join(out)


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_outputs(report_dir: Path, summary: dict[str, Any]) -> None:
    """Write both files; the report is rendered from the summary as it is read back from disk."""
    report_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    _write_text(report_dir / JSON_NAME, text)
    _write_text(report_dir / MARKDOWN_NAME, render_report(json.loads(text)))


# ------------------------------------------------------------------------------------- run


def run(config: Config, deps: Deps | None = None) -> int:
    """Run the metrics job once and return its exit code."""
    deps = deps or Deps()
    clock_start = deps.clock()

    def refuse(reason: str, detail: str) -> int:
        print(f"metrics: refused ({reason}): {detail}", file=sys.stderr)
        return EXIT_REFUSED

    # ---- 1. refuse early: nothing here touches the report directory or any store ----------
    try:
        windows = load_experiment_windows(config.experiments_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return refuse("experiments_unreadable", f"{config.experiments_path}: {exc}")

    env = {
        **load_env(),
        **{k: v for k, v in os.environ.items() if k.startswith(("INFLUX_", "POSTGRES_"))},
    }
    if deps.env is not None:
        env = deps.env
    host = env.get("INFLUX_HOST", "").strip()
    token = env.get("INFLUX_TOKEN", "").strip()
    if not host or not token:
        return refuse("influx_not_configured", "INFLUX_HOST/INFLUX_TOKEN not set (see .env)")
    try:
        databases = deps.list_databases(host, token)
    except DatabaseCheckFailed as exc:
        return refuse(f"influx_{exc.kind}", exc.detail)
    if config.database not in databases:
        return refuse(
            "database_missing",
            f"database {config.database!r} does not exist; metrics never creates one",
        )
    try:
        conninfo = connect_kwargs(env)
    except RuntimeError as exc:
        return refuse("postgres_not_configured", str(exc))

    ordered = sorted(windows.values(), key=lambda e: e.experiment_id)
    gateway = deps.gateway_factory(host, token, config.database)
    conn = None
    try:
        try:
            tables = gateway.tables()
            if PROCESSED_TABLE not in tables or not gateway.has_policy_rows(config.policy_version):
                raise Refused(
                    "no_cleaned_readings",
                    f"{config.database!r} has no {PROCESSED_TABLE} rows for policy version "
                    f"{config.policy_version!r}; run python -m scripts.clean first",
                )
            try:
                conn = deps.pg_connect(conninfo, config.pg_schema)
            except (psycopg.OperationalError, ValueError) as exc:
                raise Refused("postgres_unreachable", f"{type(exc).__name__}: {exc}") from exc
            problem = deps.pg_check(conn)
            if problem is not None:
                raise Refused("postgres_not_migrated", problem)
            absent = deps.missing_experiments(conn, [w.experiment_id for w in ordered])
            if absent:
                raise Refused(
                    "experiment_missing_in_postgres",
                    f"no row in experiment for {', '.join(absent)} "
                    "(run python -m scripts.load_experiments)",
                )

            # ---- 2-5. compute, write, read back -------------------------------------------
            summary_parts = _compute_and_write(gateway, conn, config, ordered, deps)
        except Refused as exc:
            return refuse(exc.reason, exc.detail)
        except metrics_store.DatabaseMissing as exc:
            return refuse("database_missing", str(exc))
        queries = getattr(gateway, "queries", 0)
    except (QueryFailed, WriteFailed, psycopg.Error) as exc:
        print(f"metrics: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        close = getattr(gateway, "close", None)
        if close is not None:
            close()
        if conn is not None:
            conn.close()

    computed, reconciliation, points_written = summary_parts
    timing = {
        "seconds": round(deps.clock() - clock_start, 3),
        "queries": queries,
        "points_written": points_written,
    }
    summary = build_summary(config, computed, reconciliation, timing)

    # ---- 6. outputs, only now ----------------------------------------------------------------
    write_outputs(config.report_dir, summary)

    failed = summary["plausibility_failed"]
    balanced = reconciliation["balanced"] and reconciliation["inputs_unchanged"]
    print(
        f"metrics: {len(computed)} experiment(s), {points_written} points in metrics_series, "
        f"{reconciliation['postgres_rows_checked']} Postgres rows; "
        f"{'balanced' if balanced else 'NOT balanced'}; {failed} plausibility check(s) failed; "
        f"written to {display_path(config.report_dir)}"
    )
    if not balanced:
        return EXIT_UNBALANCED
    return EXIT_FAILED_PLAUSIBILITY if failed else 0


def _pull_inputs(
    gateway: Any, window: Experiment, policy_version: str, signals: list[dict]
) -> ExperimentInputs:
    series = {
        field_name: gateway.accepted_series(
            window.experiment_id, signal, window.start, window.end, policy_version
        )
        for field_name, signal in INPUT_SIGNALS.items()
    }
    return ExperimentInputs(**series, signals=signals)


def _compute(gateway: Any, config: Config, windows: list[Experiment]) -> list[Computed]:
    computed: list[Computed] = []
    for window in windows:
        duration_s = (window.end - window.start).total_seconds()
        counts = gateway.quality_counts(
            window.experiment_id, window.start, window.end, config.policy_version
        )
        signals = metrics.signal_quality(counts, duration_s)
        inputs = _pull_inputs(gateway, window, config.policy_version, signals)
        result = metrics.experiment_metrics(inputs, duration_s)
        computed.append(
            Computed(
                window=window,
                duration_s=duration_s,
                result=result,
                signals=signals,
                plausibility=metrics.plausibility(result),
            )
        )
    return computed


def _compute_and_write(
    gateway: Any, conn: Any, config: Config, windows: list[Experiment], deps: Deps
) -> tuple[list[Computed], dict[str, Any], int]:
    span_start = min(w.start for w in windows)
    span_end = max(w.end for w in windows)
    inputs_before = gateway.input_counts(span_start, span_end)

    computed = _compute(gateway, config, windows)

    # InfluxDB: all four series of every experiment.
    points_written = 0
    for item in computed:
        for name, series in item.result.series().items():
            points_written += gateway.write_series(
                item.window.experiment_id,
                name,
                METRICS_VERSION,
                config.policy_version,
                series,
            )

    # Postgres: both tables of every experiment, one transaction.
    all_metric_rows = [row for item in computed for row in metric_rows(config, item)]
    all_quality_rows = [row for item in computed for row in quality_rows(config, item)]
    deps.write_postgres(conn, all_metric_rows, all_quality_rows)

    # Read back and compare with what was written.
    mismatches: list[dict[str, Any]] = []
    series_checked = 0
    for item in computed:
        window = item.window
        for name, series in item.result.series().items():
            read_back = gateway.count_series(
                window.experiment_id, name, METRICS_VERSION, window.start, window.end
            )
            series_checked += 1
            if read_back != len(series):
                mismatches.append(
                    {
                        "store": "influx",
                        "experiment_id": window.experiment_id,
                        "name": name,
                        "written": len(series),
                        "read_back": read_back,
                    }
                )
    written_by_table = {
        metrics_store.METRICS_TABLE: _per_experiment(all_metric_rows),
        metrics_store.QUALITY_TABLE: _per_experiment(all_quality_rows),
    }
    for table, written in written_by_table.items():
        stored = deps.count_rows(conn, table, METRICS_VERSION)
        for experiment_id in sorted(written):
            if stored.get(experiment_id, 0) != written[experiment_id]:
                mismatches.append(
                    {
                        "store": "postgres",
                        "experiment_id": experiment_id,
                        "name": table,
                        "written": written[experiment_id],
                        "read_back": stored.get(experiment_id, 0),
                    }
                )

    inputs_after = gateway.input_counts(span_start, span_end)
    reconciliation = {
        "balanced": not mismatches,
        "influx_series_checked": series_checked,
        "postgres_rows_checked": len(all_metric_rows) + len(all_quality_rows),
        "mismatches": mismatches,
        "inputs_unchanged": inputs_before == inputs_after,
    }
    return computed, reconciliation, points_written


def _per_experiment(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["experiment_id"]] = counts.get(row["experiment_id"], 0) + 1
    return counts
