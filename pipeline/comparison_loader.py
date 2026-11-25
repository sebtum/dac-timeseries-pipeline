"""Load the comparison summary into Postgres (M6, decision 13).

`python -m scripts.load_comparison` calls `run` here. The job copies three parts of
`comparison_summary.json` into the three tables of migration 0004, so Grafana can read them:

- `experiments[].kpis`        -> `comparison_kpi`       (one row per experiment and KPI)
- `comparisons[]`             -> `comparison_pair`      (one row per pair, `a < b`)
- `comparisons[].kpis[]`      -> `comparison_pair_kpi`  (one row per pair and KPI)

Values are copied unchanged. Policy and metrics versions come from the summary's top level.
`differing` becomes the factor names joined by a comma, in the order the summary lists them
(factor order).

One load replaces one `compare_version`: in a single transaction the version's rows are deleted
and the summary's rows inserted, so a rerun leaves the tables identical and rows of other versions
are never touched. The counts are read back afterwards.

    0  written and read back
    2  refused, nothing written (summary unreadable or failing the contract, Postgres not
       configured or not reachable, migration 0004 not applied, an experiment id missing from
       `experiment`)
    3  the write failed and was rolled back
    4  written, but a read-back count differs
    70 internal error (a bug; see `scripts/load_comparison.py`)
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
DEFAULT_SUMMARY = REPO_ROOT / "reports" / "comparison_summary.json"
SCHEMA_PATH = REPO_ROOT / "contracts" / "comparison_summary.schema.json"
DEFAULT_PG_SCHEMA = "public"

KPI_TABLE = "comparison_kpi"
PAIR_TABLE = "comparison_pair"
PAIR_KPI_TABLE = "comparison_pair_kpi"
TABLES = (KPI_TABLE, PAIR_TABLE, PAIR_KPI_TABLE)

KPI_COLUMNS = (
    "experiment_id",
    "compare_version",
    "kpi",
    "policy_version",
    "metrics_version",
    "value",
    "unit",
    "coverage",
    "status",
    "interval_low",
    "interval_high",
)
PAIR_COLUMNS = ("a", "b", "compare_version", "conditions_status", "differing")
PAIR_KPI_COLUMNS = (
    "a",
    "b",
    "compare_version",
    "kpi",
    "unit",
    "difference",
    "interval_low",
    "interval_high",
    "excludes_zero",
    "coverage_status",
)

CONNECT_TIMEOUT_S = 5
EXIT_REFUSED = 2
EXIT_FAILED = 3
EXIT_UNBALANCED = 4
EXIT_INTERNAL_ERROR = 70

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Refused(Exception):
    """The load must not start; nothing has been written."""

    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class ComparisonRows:
    """The rows of one summary, as dicts with the column names of migration 0004."""

    compare_version: str
    kpis: list[dict[str, Any]] = field(default_factory=list)
    pairs: list[dict[str, Any]] = field(default_factory=list)
    pair_kpis: list[dict[str, Any]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "kpis": len(self.kpis),
            "pairs": len(self.pairs),
            "pair_kpis": len(self.pair_kpis),
        }

    def experiment_ids(self) -> list[str]:
        """Every experiment id the rows reference, sorted."""
        ids = {row["experiment_id"] for row in self.kpis}
        for row in self.pairs:
            ids.update((row["a"], row["b"]))
        return sorted(ids)


# ------------------------------------------------------------------------------ pure mapping


def rows_from_summary(summary: Mapping[str, Any]) -> ComparisonRows:
    """Map a (contract-valid) summary to the rows of the three tables.

    Raises `ValueError` for what the contract does not pin but the tables need: a pair with
    `a >= b`, or a key that would appear twice.
    """
    version = summary["compare_version"]
    policy_version = summary["policy_version"]
    metrics_version = summary["metrics_version"]

    kpis: list[dict[str, Any]] = []
    for experiment in summary["experiments"]:
        for name, kpi in experiment["kpis"].items():
            kpis.append(
                {
                    "experiment_id": experiment["experiment_id"],
                    "compare_version": version,
                    "kpi": name,
                    "policy_version": policy_version,
                    "metrics_version": metrics_version,
                    "value": kpi["value"],
                    "unit": kpi["unit"],
                    "coverage": kpi["coverage"],
                    "status": kpi["status"],
                    "interval_low": kpi["interval_low"],
                    "interval_high": kpi["interval_high"],
                }
            )

    pairs: list[dict[str, Any]] = []
    pair_kpis: list[dict[str, Any]] = []
    for comparison in summary["comparisons"]:
        a, b = comparison["a"], comparison["b"]
        if not a < b:
            raise ValueError(f"pair ({a!r}, {b!r}) is not ordered a < b")
        pairs.append(
            {
                "a": a,
                "b": b,
                "compare_version": version,
                "conditions_status": comparison["conditions_status"],
                "differing": ",".join(comparison["differing"]),
            }
        )
        for kpi in comparison["kpis"]:
            pair_kpis.append(
                {
                    "a": a,
                    "b": b,
                    "compare_version": version,
                    "kpi": kpi["name"],
                    "unit": kpi["unit"],
                    "difference": kpi["difference"],
                    "interval_low": kpi["interval_low"],
                    "interval_high": kpi["interval_high"],
                    "excludes_zero": kpi["excludes_zero"],
                    "coverage_status": kpi["coverage_status"],
                }
            )

    for label, rows, key in (
        (KPI_TABLE, kpis, ("experiment_id", "kpi")),
        (PAIR_TABLE, pairs, ("a", "b")),
        (PAIR_KPI_TABLE, pair_kpis, ("a", "b", "kpi")),
    ):
        keys = [tuple(row[k] for k in key) for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError(f"duplicate key in {label} rows")

    return ComparisonRows(version, kpis, pairs, pair_kpis)


def validate_summary(summary: Any, schema: Mapping[str, Any]) -> list[str]:
    """Contract problems of `summary`, worst-first by path; empty when it conforms."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(summary), key=lambda e: list(map(str, e.absolute_path)))
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message[:200]}"
        for error in errors
    ]


# ------------------------------------------------------------------------------ Postgres side


def _insert_sql(table: str, columns: tuple[str, ...]) -> str:
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(f'%({c})s' for c in columns)})"
    )


def pg_connect(conninfo: Mapping[str, Any], schema: str) -> psycopg.Connection:
    """An autocommit connection whose `search_path` is `schema` (only that schema)."""
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"schema {schema!r} is not a plain identifier")
    kwargs = {
        "connect_timeout": CONNECT_TIMEOUT_S,
        **conninfo,
        "options": f"-c search_path={schema}",
    }
    return psycopg.connect(**kwargs, autocommit=True)


def pg_check(conn: psycopg.Connection) -> str | None:
    """None when migration 0004 (and `experiment`) is applied; otherwise the refusal detail."""
    missing = []
    with conn.cursor() as cur:
        for table in ("experiment", *TABLES):
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
            (exists,) = cur.fetchone()
            if not exists:
                missing.append(table)
    if missing:
        return (
            f"missing table(s) {', '.join(missing)}: migration 0004 is not applied "
            "(run python -m scripts.migrate)"
        )
    return None


def missing_experiments(conn: psycopg.Connection, ids: list[str]) -> list[str]:
    """The ids that have no row in `experiment`, in the order given."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT experiment_id FROM experiment WHERE experiment_id = ANY(%s)", (list(ids),)
        )
        found = {row[0] for row in cur.fetchall()}
    return [i for i in ids if i not in found]


def load(conn: psycopg.Connection, rows: ComparisonRows) -> dict[str, int]:
    """Replace the rows of `rows.compare_version` in one transaction; return the counts written.

    Pair KPI rows go with their pair (foreign key, ON DELETE CASCADE), but are deleted first
    explicitly so the order does not depend on the cascade. On any error the transaction rolls
    back and the exception propagates.
    """
    version = rows.compare_version
    with conn.transaction(), conn.cursor() as cur:
        for table in (PAIR_KPI_TABLE, PAIR_TABLE, KPI_TABLE):
            cur.execute(f"DELETE FROM {table} WHERE compare_version = %s", (version,))
        cur.executemany(_insert_sql(KPI_TABLE, KPI_COLUMNS), rows.kpis)
        cur.executemany(_insert_sql(PAIR_TABLE, PAIR_COLUMNS), rows.pairs)
        cur.executemany(_insert_sql(PAIR_KPI_TABLE, PAIR_KPI_COLUMNS), rows.pair_kpis)
    return rows.counts()


def read_back(conn: psycopg.Connection, compare_version: str) -> dict[str, int]:
    """Row counts of the three tables for one `compare_version`."""
    counts = {}
    with conn.cursor() as cur:
        for key, table in (
            ("kpis", KPI_TABLE),
            ("pairs", PAIR_TABLE),
            ("pair_kpis", PAIR_KPI_TABLE),
        ):
            cur.execute(
                f"SELECT count(*) FROM {table} WHERE compare_version = %s", (compare_version,)
            )
            (counts[key],) = cur.fetchone()
    return counts


# ------------------------------------------------------------------------------------- run


@dataclass(frozen=True)
class Config:
    summary_path: Path = DEFAULT_SUMMARY
    pg_schema: str = DEFAULT_PG_SCHEMA


def load_env() -> dict[str, str]:
    """`.env` plus any `POSTGRES_*` variable of the process environment (the latter wins)."""
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip()
    values.update({k: v for k, v in os.environ.items() if k.startswith("POSTGRES_")})
    return values


def connect_kwargs(env: Mapping[str, str]) -> dict[str, str]:
    keys = {
        "host": "POSTGRES_HOST",
        "port": "POSTGRES_PORT",
        "dbname": "POSTGRES_DB",
        "user": "POSTGRES_USER",
    }
    kwargs = {name: env.get(key, "").strip() for name, key in keys.items()}
    if not all(kwargs.values()):
        raise Refused(
            "postgres_not_configured",
            "POSTGRES_HOST/PORT/DB/USER not set (see .env)",
        )
    kwargs["password"] = env.get("POSTGRES_PASSWORD", "").strip()
    return kwargs


def read_summary(path: Path, schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """The summary at `path`, checked against the comparison contract; `Refused` otherwise."""
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused("summary_unreadable", f"{path}: {exc}") from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    problems = validate_summary(summary, schema)
    if problems:
        shown = "; ".join(problems[:5])
        more = f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""
        raise Refused("contract_failed", f"{path}: {shown}{more}")
    return summary


def run(config: Config, env: Mapping[str, str] | None = None) -> int:
    """Run the loader once and return its exit code."""

    def refuse(exc: Refused) -> int:
        print(f"load_comparison: refused ({exc.reason}): {exc.detail}", file=sys.stderr)
        return EXIT_REFUSED

    conn = None
    try:
        summary = read_summary(config.summary_path)
        try:
            rows = rows_from_summary(summary)
        except ValueError as exc:
            raise Refused("contract_failed", f"{config.summary_path}: {exc}") from exc
        conninfo = connect_kwargs(load_env() if env is None else env)
        try:
            conn = pg_connect(conninfo, config.pg_schema)
        except (psycopg.OperationalError, ValueError) as exc:
            raise Refused("postgres_unreachable", f"{type(exc).__name__}: {exc}") from exc
        problem = pg_check(conn)
        if problem is not None:
            raise Refused("postgres_not_migrated", problem)
        absent = missing_experiments(conn, rows.experiment_ids())
        if absent:
            raise Refused(
                "experiment_missing_in_postgres",
                f"no row in experiment for {', '.join(absent)} "
                "(run python -m scripts.load_experiments)",
            )

        try:
            written = load(conn, rows)
            found = read_back(conn, rows.compare_version)
        except psycopg.Error as exc:
            print(f"load_comparison: write failed and was rolled back: {exc}", file=sys.stderr)
            return EXIT_FAILED
    except Refused as exc:
        return refuse(exc)
    except psycopg.Error as exc:
        print(f"load_comparison: Postgres query failed: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        if conn is not None:
            conn.close()

    print(
        f"load_comparison: {rows.compare_version} "
        f"kpis={found['kpis']} pairs={found['pairs']} pair_kpis={found['pair_kpis']}"
    )
    if found != written:
        print(
            f"load_comparison: read-back counts differ: wrote {written}, found {found}",
            file=sys.stderr,
        )
        return EXIT_UNBALANCED
    return 0
