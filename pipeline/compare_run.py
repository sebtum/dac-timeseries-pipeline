"""The comparison batch job (M5): refuse, read, analyse, report.

`python -m scripts.compare` calls `run` here. The job is read-only: it writes no InfluxDB or
Postgres row and creates nothing. The order follows decisions 5 to 21 of M5:

1. refusal checks (nothing is written, the report directory is not touched, no database is
   created);
2. for each experiment, read one window at a time (accepted series, raw air flow where needed,
   phases, `metrics_series`) and run the pure analysis of `pipeline/compare.py`;
3. build the summary and render the report from it;
4. write `comparison_summary.json` and `comparison_report.md`, only now.

The report is a pure function of the summary (`render_report`), so the two files cannot disagree.
Nothing time-varying is in the report; `timing` lives in the summary only.

    0  summary and report written
    2  refused, nothing written (database missing, no cleaned rows for the policy version, no
       `metrics_series` rows for the metrics and policy version, experiments file unreadable,
       Postgres not configured or not reachable, migration 0003 not applied, an experiment
       missing from Postgres `experiment` or without its `experiment_metrics` rows, or
       `window_mismatch`: Postgres start/end differs from the experiments file)
    3  a query failed; no outputs
    70 internal error (a bug; see `scripts/compare.py`)
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from pipeline import compare, compare_store
from pipeline.cleaning import instant_text
from pipeline.cleaning_influx import PROCESSED_TABLE
from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.compare import MODELS, POLICY, KpiResult, Rows
from pipeline.ingest import Experiment, load_experiment_windows, parse_timestamp, timestamp_ns
from pipeline.ingest_influx import DatabaseCheckFailed, list_databases
from pipeline.metrics import METRIC_UNITS, METRICS_VERSION
from pipeline.metrics_run import display_path, round_floats
from pipeline.profiling_sql import QueryFailed
from scripts.init_influx import load_env
from scripts.migrate import connect_kwargs

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "raw" / "experiments.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_DATABASE = "dac_raw"
DEFAULT_PG_SCHEMA = "public"

EXIT_REFUSED = 2
EXIT_FAILED = 3
EXIT_INTERNAL_ERROR = 70

JSON_NAME = "comparison_summary.json"
MARKDOWN_NAME = "comparison_report.md"

SCHEMA_VERSION = 1

WINDOWS = ("steady", "whole_run")

# Accepted series of one experiment, by the plain signal name used as the key in `compare`.
ACCEPTED_SIGNALS: tuple[str, ...] = (
    "voltage",
    "current",
    "flow",
    "pressure",
    "electrolyte_temperature",
    "air_flow",
    "pressure_drop",
    "current_setpoint",
    "solvent_flow",
    "ambient_temperature",
    "relative_humidity",
    "co2_in_ppm",
    "co2_out_ppm",
)
# The `metrics_series` names the KPIs read.
METRIC_SERIES: tuple[str, ...] = ("power_computed", "capture_rate", "capture_efficiency")
PROCESS_STATE = "process_state"

# The air-flow check (decision 17): signal, where its numbers come from.
AIRFLOW_SIGNALS: tuple[tuple[str, str], ...] = (
    ("air_flow", "raw"),
    ("fan_speed", "accepted"),
    ("pressure_drop", "accepted"),
    ("co2_in_ppm", "accepted"),
    ("co2_out_ppm", "accepted"),
    ("capture_efficiency", "metrics_series"),
)

METADATA_FIELDS: tuple[str, ...] = (
    "current_setpoint_nominal_a",
    "air_flow_nominal_m3h",
    "solvent_flow_nominal_lmin",
    "operator",
    "sorbent_batch",
    "notes",
)


@dataclass(frozen=True)
class Config:
    database: str = DEFAULT_DATABASE
    experiments_path: Path = DEFAULT_EXPERIMENTS
    report_dir: Path = DEFAULT_REPORT_DIR
    policy_version: str = POLICY_VERSION
    metrics_version: str = METRICS_VERSION
    pg_schema: str = DEFAULT_PG_SCHEMA


@dataclass
class Deps:
    """Everything the run reaches outside itself for; tests substitute these."""

    list_databases: Callable[[str, str], list[str]] = list_databases
    gateway_factory: Callable[[str, str, str], Any] = compare_store.CompareGateway
    pg_connect: Callable[[dict[str, str], str], Any] = compare_store.pg_connect
    pg_check: Callable[[Any], str | None] = compare_store.pg_check
    experiment_rows: Callable[[Any, list[str]], dict[str, dict]] = compare_store.experiment_rows
    experiment_metric_rows: Callable[[Any, str, list[str]], dict[str, dict[str, dict]]] = (
        compare_store.experiment_metric_rows
    )
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
    entry: dict[str, Any]
    kpis: KpiResult
    rows: dict[tuple[str, str], Rows]
    models: list[dict[str, Any]]
    pressure_drop: dict[str, Any]
    drop_median: float | None
    airflow: dict[str, Any] | None


# ----------------------------------------------------------------------------- summary shaping


def _number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _median_in(series: list[tuple[int, float]], windows: list[tuple[int, int]]) -> float | None:
    return compare.median([v for _, v in _inside(series, windows)])


def _inside(
    series: list[tuple[int, float]], windows: list[tuple[int, int]]
) -> list[tuple[int, float]]:
    """The instants of `series` that lie in one of the half-open `windows`."""
    return [(t, v) for t, v in series if any(lo <= t < hi for lo, hi in windows)]


def _phase_entries(phases: list[compare.Phase], start_ns: int) -> list[dict[str, Any]]:
    out = []
    for phase in phases:
        window = phase.window
        out.append(
            {
                "index": phase.index,
                "state": phase.state,
                "start_s": _number(compare.experiment_time_s(phase.start_ns, start_ns)),
                "end_s": _number(compare.experiment_time_s(phase.end_ns, start_ns)),
                "window_start_s": (
                    None
                    if window is None
                    else _number(compare.experiment_time_s(window[0], start_ns))
                ),
                "window_end_s": (
                    None
                    if window is None
                    else _number(compare.experiment_time_s(window[1], start_ns))
                ),
            }
        )
    return out


def _pull(gateway: Any, window: Experiment, config: Config, with_fan: bool) -> dict[str, list]:
    """Every series of one experiment, read inside its own window `[start, end)`."""
    series: dict[str, list] = {}
    for signal in ACCEPTED_SIGNALS:
        series[signal] = gateway.accepted_series(
            window.experiment_id, signal, window.start, window.end, config.policy_version
        )
    for metric in METRIC_SERIES:
        series[metric] = gateway.metric_series(
            window.experiment_id,
            metric,
            config.metrics_version,
            config.policy_version,
            window.start,
            window.end,
        )
    if with_fan:
        series["fan_speed"] = gateway.accepted_series(
            window.experiment_id, "fan_speed", window.start, window.end, config.policy_version
        )
    return series


def _airflow_entry(
    gateway: Any, window: Experiment, config: Config, series: dict[str, list]
) -> dict[str, Any]:
    boundary = POLICY["airflow_check_boundary"]
    boundary_ns = timestamp_ns(parse_timestamp(boundary))
    signals = []
    for signal, source in AIRFLOW_SIGNALS:
        if source == "raw":
            values = gateway.raw_series(
                window.experiment_id, signal, window.start, window.end, config.policy_version
            )
        else:
            values = series[signal]
        signals.append(
            {"signal": signal, "source": source, **compare.split_check(values, boundary_ns)}
        )
    return {"experiment_id": window.experiment_id, "boundary": boundary, "signals": signals}


def _compute_one(
    gateway: Any,
    window: Experiment,
    config: Config,
    meta: dict[str, Any],
    metrics_rows: dict[str, dict],
) -> Computed:
    experiment_id = window.experiment_id
    start_ns = timestamp_ns(window.start)
    end_ns = timestamp_ns(window.end)
    is_airflow = experiment_id == POLICY["airflow_check_experiment"]
    series = _pull(gateway, window, config, with_fan=is_airflow)
    events = gateway.state_events(
        experiment_id, PROCESS_STATE, window.start, window.end, config.policy_version
    )
    phases = compare.phases(events, POLICY["settle_s"])
    steady = compare.steady_windows(phases)
    whole = [(start_ns, end_ns)]
    # The KPIs read only the instants inside the steady windows: an interval that reaches past a
    # window's end would use the first reading of the next phase (the load step), which is what
    # the settle margin keeps out (README of the compare fixture, S5.15).
    kpi_series = {
        name: _inside(series[name], steady)
        for name in ("voltage", "power_computed", "capture_rate", "capture_efficiency")
    }
    kpis = compare.steady_kpis(kpi_series, steady, experiment_id)

    rows: dict[tuple[str, str], Rows] = {}
    models: list[dict[str, Any]] = []
    for model in sorted(MODELS):
        x1, x2 = MODELS[model][2], MODELS[model][3]
        lag_series = {x1: series[x1], x2: series[x2]}
        for name, windows in (("steady", steady), ("whole_run", whole)):
            fit_rows = compare.model_rows(model, series, windows)
            rows[(model, name)] = fit_rows
            models.append(compare.analyse_model(fit_rows, model, name, experiment_id, lag_series))

    pressure_drop = {
        "experiment_id": experiment_id,
        **compare.pressure_drop_fit(series["air_flow"], series["pressure_drop"], steady),
    }
    entry = {
        "experiment_id": experiment_id,
        "start": instant_text(start_ns),
        "end": instant_text(end_ns),
        "duration_s": _number((window.end - window.start).total_seconds()),
        "metadata": {name: meta.get(name) for name in METADATA_FIELDS},
        "conditions": compare.measured_conditions(series, steady),
        "phases": _phase_entries(phases, start_ns),
        "steady_seconds": _number(sum(hi - lo for lo, hi in steady) / 1e9),
        "kpis": kpis.entries,
        "whole_run_metrics": {name: dict(metrics_rows[name]) for name in METRIC_UNITS},
    }
    return Computed(
        window=window,
        entry=entry,
        kpis=kpis,
        rows=rows,
        models=models,
        pressure_drop=pressure_drop,
        drop_median=_median_in(series["pressure_drop"], steady),
        airflow=_airflow_entry(gateway, window, config, series) if is_airflow else None,
    )


def _models_and_evidence(computed: list[Computed]) -> tuple[list[dict], list[dict]]:
    """`voltage_models` (per experiment, then pooled) and `voltage_evidence`, both sorted."""
    models: list[dict] = []
    evidence: list[dict] = []
    for model in sorted(MODELS):
        for window in WINDOWS:
            per_experiment = [
                entry
                for item in computed
                for entry in item.models
                if entry["model"] == model and entry["window"] == window
            ]
            pooled = compare.analyse_pooled(
                {item.window.experiment_id: item.rows[(model, window)] for item in computed},
                model,
                window,
            )
            models += per_experiment + [pooled]
            evidence += compare.evidence(per_experiment, pooled)
    return models, evidence


def _comparisons(computed: list[Computed]) -> list[dict]:
    out = []
    for a, b in itertools.combinations(computed, 2):
        factors = compare.compare_factors(
            a.entry["metadata"], a.entry["conditions"], b.entry["metadata"], b.entry["conditions"]
        )
        status, differing = compare.conditions_status(factors)
        out.append(
            {
                "a": a.window.experiment_id,
                "b": b.window.experiment_id,
                "conditions_status": status,
                "differing": differing,
                "factors": factors,
                "recorded_differences": compare.recorded_differences(
                    a.entry["metadata"], b.entry["metadata"]
                ),
                "kpis": compare.kpi_differences(a.kpis, b.kpis),
            }
        )
    return out


def build_summary(config: Config, computed: list[Computed], timing: dict[str, Any]) -> dict:
    models, evidence = _models_and_evidence(computed)
    points = [
        {
            "experiment_id": item.window.experiment_id,
            "air_flow_median": item.entry["conditions"]["air_flow_m3h"],
            "pressure_drop_median": item.drop_median,
        }
        for item in computed
    ]
    across = compare.across_line(
        [(p["air_flow_median"], p["pressure_drop_median"]) for p in points]
    )
    airflow = next((item.airflow for item in computed if item.airflow is not None), None)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "compare_version": compare.COMPARE_VERSION,
        "policy_version": config.policy_version,
        "metrics_version": config.metrics_version,
        "source": {
            "database": config.database,
            "experiments_file": display_path(config.experiments_path),
            "pg_schema": config.pg_schema,
        },
        "parameters": {},
        "experiments": [item.entry for item in computed],
        "voltage_models": models,
        "voltage_evidence": evidence,
        "comparisons": _comparisons(computed),
        "pressure_drop_check": {
            "per_experiment": [item.pressure_drop for item in computed],
            "across": {"points": points, **across},
        },
        "airflow_check": airflow,
        "timing": timing,
    }
    summary = round_floats(summary)
    summary["parameters"] = dict(POLICY)  # the policy as declared, not rounded
    return summary


# ----------------------------------------------------------------------------------- report


def _cell(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.9g}"
    if isinstance(value, list):
        return ", ".join(_cell(v) for v in value) if value else "none"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows]
    return lines


def _experiment_section(entry: dict[str, Any]) -> list[str]:
    meta = entry["metadata"]
    cond = entry["conditions"]
    return [
        f"## {entry['experiment_id']}",
        "",
        f"From {entry['start']} to {entry['end']} ({_cell(entry['duration_s'])} s); steady "
        f"seconds {_cell(entry['steady_seconds'])}.",
        "",
        "### Recorded metadata",
        "",
        *_table(["Field", "Value"], [[k, v] for k, v in meta.items()]),
        "",
        "### Phases (experiment time, seconds)",
        "",
        *_table(
            ["Index", "State", "Start", "End", "Window start", "Window end"],
            [
                [
                    p["index"],
                    p["state"],
                    p["start_s"],
                    p["end_s"],
                    p["window_start_s"],
                    p["window_end_s"],
                ]
                for p in entry["phases"]
            ],
        ),
        "",
        "### Measured conditions (steady windows)",
        "",
        *_table(["Condition", "Value"], [[k, v] for k, v in cond.items()]),
        "",
        "### Steady-state KPIs",
        "",
        *_table(
            ["KPI", "Value", "Unit", "Coverage", "Status", "Interval low", "Interval high"],
            [
                [
                    name,
                    k["value"],
                    k["unit"],
                    k["coverage"],
                    k["status"],
                    k["interval_low"],
                    k["interval_high"],
                ]
                for name, k in entry["kpis"].items()
            ],
        ),
        "",
        "### Whole-run metrics (from Postgres experiment_metrics)",
        "",
        *_table(
            ["Metric", "Value", "Unit", "Coverage", "Status"],
            [
                [name, m["value"], m["unit"], m["coverage"], m["status"]]
                for name, m in entry["whole_run_metrics"].items()
            ],
        ),
        "",
    ]


def _model_section(summary: dict[str, Any], model: str, window: str) -> list[str]:
    entries = [
        m for m in summary["voltage_models"] if m["model"] == model and m["window"] == window
    ]
    names = MODELS[model]
    out = [
        f"### Model `{model}`, window `{window}`",
        "",
        f"voltage ~ 1 + {' + '.join(names)}",
        "",
        *_table(
            [
                "Scope",
                "Testable",
                "Instants",
                "R2",
                "Resamples used",
                "Singular",
                f"Joint R2 drop ({' + '.join(names[2:])})",
                "Separable",
            ],
            [
                [
                    m["scope"],
                    m["testable"],
                    m["instants"],
                    m["r2"],
                    m["resamples_used"],
                    m["resamples_singular"],
                    m["joint"]["r2_drop"],
                    m["joint"]["separable"],
                ]
                for m in entries
            ],
        ),
        "",
        *_table(
            [
                "Scope",
                "Term",
                "Unit",
                "Coefficient",
                "Interval low",
                "Interval high",
                "R2 drop",
                "VIF",
                "Plain corr",
                "Best lag (s)",
                "Corr at best lag",
                "Corr at zero lag",
            ],
            [
                [
                    m["scope"],
                    t["name"],
                    t["unit"],
                    t["coefficient"],
                    t["interval_low"],
                    t["interval_high"],
                    t["r2_drop"],
                    t["vif"],
                    t["plain_corr"],
                    t["best_lag_s"],
                    t["corr_at_best_lag"],
                    t["corr_at_zero"],
                ]
                for m in entries
                for t in m["terms"]
            ],
        ),
        "",
    ]
    return out


def _comparison_sections(summary: dict[str, Any]) -> list[str]:
    comparisons = summary["comparisons"]
    out = [
        "## Comparability of the experiment pairs",
        "",
        "Status: `same_conditions` (no factor differs), `supported` (exactly one differs),"
        " `confounded` (two or more). A factor with no value counts as differing.",
        "",
        *_table(
            ["Pair", "Status", "Differing factors", "Recorded differences"],
            [
                [
                    f"{c['a']} - {c['b']}",
                    c["conditions_status"],
                    c["differing"],
                    [
                        f"{r['field']}: {_cell(r['a'])} vs {_cell(r['b'])}"
                        for r in c["recorded_differences"]
                    ],
                ]
                for c in comparisons
            ],
        ),
        "",
        "### Factors per pair",
        "",
        *_table(
            ["Pair", "Factor", "a", "b", "Differs"],
            [
                [f"{c['a']} - {c['b']}", f["factor"], f["a"], f["b"], f["differs"]]
                for c in comparisons
                for f in c["factors"]
            ],
        ),
        "",
        "### Steady-state KPI differences (b minus a)",
        "",
        *_table(
            [
                "Pair",
                "KPI",
                "Unit",
                "Difference",
                "Interval low",
                "Interval high",
                "Excludes zero",
                "Coverage",
            ],
            [
                [
                    f"{c['a']} - {c['b']}",
                    k["name"],
                    k["unit"],
                    k["difference"],
                    k["interval_low"],
                    k["interval_high"],
                    k["excludes_zero"],
                    k["coverage_status"],
                ]
                for c in comparisons
                for k in c["kpis"]
            ],
        ),
        "",
    ]
    return out


def _pressure_drop_section(summary: dict[str, Any]) -> list[str]:
    check = summary["pressure_drop_check"]
    across = check["across"]
    return [
        "## Pressure drop against air flow (steady windows)",
        "",
        *_table(
            [
                "Experiment",
                "Instants",
                "Slope (air flow)",
                "Intercept",
                "R2",
                "Slope (air flow squared)",
                "Intercept (squared)",
                "R2 (squared)",
                "Best lag (s)",
                "Corr at best lag",
                "Corr at zero lag",
            ],
            [
                [
                    p["experiment_id"],
                    p["instants"],
                    p["slope_air_flow"],
                    p["intercept_air_flow"],
                    p["r2_air_flow"],
                    p["slope_air_flow_sq"],
                    p["intercept_air_flow_sq"],
                    p["r2_air_flow_sq"],
                    p["best_lag_s"],
                    p["corr_at_best_lag"],
                    p["corr_at_zero"],
                ]
                for p in check["per_experiment"]
            ],
        ),
        "",
        "### Across experiments (steady medians)",
        "",
        *_table(
            ["Experiment", "Air flow median (m3/h)", "Pressure drop median (mbar)"],
            [
                [p["experiment_id"], p["air_flow_median"], p["pressure_drop_median"]]
                for p in across["points"]
            ],
        ),
        "",
        *_table(
            ["Line", "Value"],
            [["slope", across["slope"]], ["intercept", across["intercept"]], ["r2", across["r2"]]],
        ),
        "",
    ]


def _airflow_section(summary: dict[str, Any]) -> list[str]:
    check = summary["airflow_check"]
    out = ["## Air-flow check", ""]
    if check is None:
        out += [
            f"Not run: {summary['parameters']['airflow_check_experiment']} is not in this run.",
            "",
        ]
        return out
    out += [
        f"{check['experiment_id']}, before and after {check['boundary']}.",
        "",
        *_table(
            [
                "Signal",
                "Source",
                "Before points",
                "Before median",
                "After points",
                "After median",
                "Relative change",
            ],
            [
                [
                    s["signal"],
                    s["source"],
                    s["before_points"],
                    s["before_median"],
                    s["after_points"],
                    s["after_median"],
                    s["relative_change"],
                ]
                for s in check["signals"]
            ],
        ),
        "",
    ]
    return out


def render_report(summary: dict[str, Any]) -> str:
    """The report as Markdown, from the summary alone (a pure function of it)."""
    out = [
        "# Comparison report",
        "",
        f"Compare version `{summary['compare_version']}`, cleaning policy "
        f"`{summary['policy_version']}`, metrics version `{summary['metrics_version']}`, "
        f"database `{summary['source']['database']}`, Postgres schema "
        f"`{summary['source']['pg_schema']}`. Generated by `python -m scripts.compare`; the "
        "numbers are the ones in `comparison_summary.json`. Intervals are "
        f"{summary['parameters']['interval_level'] * 100:g} percent block "
        'bootstrap intervals. One run per condition: differences are read as "in this run", '
        "not as causes.",
        "",
    ]
    for entry in summary["experiments"]:
        out += _experiment_section(entry)

    out += ["## Voltage models", ""]
    for model in sorted(MODELS):
        for window in WINDOWS:
            out += _model_section(summary, model, window)

    out += [
        "## Evidence for each term",
        "",
        "Per-experiment fits decide the status; the pooled fit is shown beside it.",
        "",
        *_table(
            [
                "Model",
                "Window",
                "Term",
                "Status",
                "Sign",
                "Testable",
                "Excluding zero",
                "Pooled coefficient",
                "Pooled low",
                "Pooled high",
            ],
            [
                [
                    e["model"],
                    e["window"],
                    e["term"],
                    e["status"],
                    e["sign"],
                    e["experiments_testable"],
                    e["experiments_excluding_zero"],
                    e["pooled_coefficient"],
                    e["pooled_interval_low"],
                    e["pooled_interval_high"],
                ]
                for e in summary["voltage_evidence"]
            ],
        ),
        "",
    ]
    out += _comparison_sections(summary)
    out += _pressure_drop_section(summary)
    out += _airflow_section(summary)
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
    text = json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    report = render_report(json.loads(text))
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_text(report_dir / JSON_NAME, text)
    _write_text(report_dir / MARKDOWN_NAME, report)


# ------------------------------------------------------------------------------------- run


def _check_postgres(
    conn: Any, config: Config, windows: list[Experiment], deps: Deps
) -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    """The refusal checks on Postgres; returns the metadata and metric rows when all pass."""
    problem = deps.pg_check(conn)
    if problem is not None:
        raise Refused("postgres_not_migrated", problem)
    ids = [w.experiment_id for w in windows]
    rows = deps.experiment_rows(conn, ids)
    absent = [i for i in ids if i not in rows]
    if absent:
        raise Refused(
            "experiment_missing_in_postgres",
            f"no row in experiment for {', '.join(absent)} "
            "(run python -m scripts.load_experiments)",
        )
    for window in windows:
        row = rows[window.experiment_id]
        for column, expected in (("start_time", window.start), ("end_time", window.end)):
            found = row.get(column)
            if not isinstance(found, datetime) or found != expected:
                raise Refused(
                    "window_mismatch",
                    f"{window.experiment_id}: Postgres {column} is "
                    f"{found.isoformat() if isinstance(found, datetime) else found!r}, the "
                    f"experiments file says {expected.isoformat()}",
                )
    metric_rows = deps.experiment_metric_rows(conn, config.metrics_version, ids)
    for window in windows:
        have = metric_rows.get(window.experiment_id, {})
        missing = [name for name in METRIC_UNITS if name not in have]
        if missing:
            raise Refused(
                "experiment_metrics_missing",
                f"no experiment_metrics row of metrics version {config.metrics_version!r} for "
                f"{window.experiment_id}: {', '.join(missing)} (run python -m scripts.metrics)",
            )
    return rows, metric_rows


def run(config: Config, deps: Deps | None = None) -> int:
    """Run the comparison once and return its exit code."""
    deps = deps or Deps()
    clock_start = deps.clock()

    def refuse(reason: str, detail: str) -> int:
        print(f"compare: refused ({reason}): {detail}", file=sys.stderr)
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
            f"database {config.database!r} does not exist; compare never creates one",
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
            gateway.require_database()
            if PROCESSED_TABLE not in gateway.tables() or not gateway.has_policy_rows(
                config.policy_version
            ):
                raise Refused(
                    "no_cleaned_readings",
                    f"{config.database!r} has no {PROCESSED_TABLE} rows for policy version "
                    f"{config.policy_version!r}; run python -m scripts.clean first",
                )
            if not gateway.has_metrics_rows(config.metrics_version, config.policy_version):
                raise Refused(
                    "no_metrics_rows",
                    f"{config.database!r} has no metrics_series rows for metrics version "
                    f"{config.metrics_version!r} and policy version {config.policy_version!r}; "
                    "run python -m scripts.metrics first",
                )
            try:
                conn = deps.pg_connect(conninfo, config.pg_schema)
            except (psycopg.OperationalError, ValueError) as exc:
                raise Refused("postgres_unreachable", f"{type(exc).__name__}: {exc}") from exc
            metadata, metric_rows = _check_postgres(conn, config, ordered, deps)

            # ---- 2. read and analyse, one experiment window at a time ---------------------
            computed = [
                _compute_one(
                    gateway,
                    window,
                    config,
                    metadata[window.experiment_id],
                    metric_rows[window.experiment_id],
                )
                for window in ordered
            ]
        except Refused as exc:
            return refuse(exc.reason, exc.detail)
        except compare_store.DatabaseMissing as exc:
            return refuse("database_missing", str(exc))
        queries = getattr(gateway, "queries", 0)
    except (QueryFailed, psycopg.Error) as exc:
        print(f"compare: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        close = getattr(gateway, "close", None)
        if close is not None:
            close()
        if conn is not None:
            conn.close()

    timing = {"seconds": round(deps.clock() - clock_start, 3), "queries": queries}
    summary = build_summary(config, computed, timing)

    # ---- 3. outputs, only now ----------------------------------------------------------------
    write_outputs(config.report_dir, summary)
    print(
        f"compare: {len(computed)} experiment(s), {len(summary['voltage_models'])} voltage "
        f"fit(s), {len(summary['comparisons'])} comparison(s); written to "
        f"{display_path(config.report_dir)}"
    )
    return 0
