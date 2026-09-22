"""`experiments.json` loader with per-field provenance (ADR-0012, Option C).

`data/raw/experiments.json` stays the immutable source of truth; this module is the only
writer of the `experiment` table. It is an idempotent upsert keyed on `experiment_id`, with
**no hard deletes** — a row missing from a later copy of the JSON is left exactly as it is
in the database, since removing an experiment from the file must never delete a row
time-series data still references.

The load-bearing property, per ADR-0012: a re-run cannot silently revert a value a human
has corrected in Postgres — the entire justification for putting this metadata in Postgres
at all (ADR-0005). That is enforced in the upsert SQL itself, one `CASE WHEN
is_manual(...)` guard per correctable column, and *recorded* by the `experiment_provenance`
trigger from `migrations/0002_experiment_provenance.sql`. This module's only part in the
provenance mechanism is `SET LOCAL app.actor = 'loader'` for the duration of the write, so
that trigger can tell this write apart from a manual one; the actual protection lives in the
SQL, not in Python, so there is exactly one place the rule can drift from ADR-0012.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_PATH = REPO_ROOT / "data" / "raw" / "experiments.json"

# Set once at load time, never hand-corrected (migrations/0001's comment) — no provenance
# guard applies to these.
STRUCTURAL_COLUMNS = frozenset({"experiment_id", "start_time", "end_time", "duration_s"})

# JSON key -> `experiment` column. Spelled out once here because the JSON's unit suffixes
# (`_A`, `_Lmin`) don't fold to Postgres's lowercase identifiers (`_a`, `_lmin`). This must
# match the array in migrations/0002_experiment_provenance.sql's
# record_experiment_provenance() trigger exactly, or a column protected on one side and not
# the other is silently unprotected or silently un-writable —
# tests/integration/test_metadata_loader.py checks that coupling directly against the
# database, not just against this constant.
CORRECTABLE_COLUMNS = {
    "current_setpoint_nominal_A": "current_setpoint_nominal_a",
    "air_flow_nominal_m3h": "air_flow_nominal_m3h",
    "solvent_flow_nominal_Lmin": "solvent_flow_nominal_lmin",
    "operator": "operator",
    "sorbent_batch": "sorbent_batch",
    "notes": "notes",
}

_UPSERT_SQL = """
INSERT INTO experiment AS e (
    experiment_id, start_time, end_time, duration_s,
    current_setpoint_nominal_a, air_flow_nominal_m3h, solvent_flow_nominal_lmin,
    operator, sorbent_batch, notes
) VALUES (
    %(experiment_id)s, %(start_time)s, %(end_time)s, %(duration_s)s,
    %(current_setpoint_nominal_a)s, %(air_flow_nominal_m3h)s, %(solvent_flow_nominal_lmin)s,
    %(operator)s, %(sorbent_batch)s, %(notes)s
)
ON CONFLICT (experiment_id) DO UPDATE SET
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    duration_s = EXCLUDED.duration_s,
    current_setpoint_nominal_a = CASE
        WHEN is_manual(e.experiment_id, 'current_setpoint_nominal_a')
        THEN e.current_setpoint_nominal_a ELSE EXCLUDED.current_setpoint_nominal_a END,
    air_flow_nominal_m3h = CASE
        WHEN is_manual(e.experiment_id, 'air_flow_nominal_m3h')
        THEN e.air_flow_nominal_m3h ELSE EXCLUDED.air_flow_nominal_m3h END,
    solvent_flow_nominal_lmin = CASE
        WHEN is_manual(e.experiment_id, 'solvent_flow_nominal_lmin')
        THEN e.solvent_flow_nominal_lmin ELSE EXCLUDED.solvent_flow_nominal_lmin END,
    operator = CASE
        WHEN is_manual(e.experiment_id, 'operator')
        THEN e.operator ELSE EXCLUDED.operator END,
    sorbent_batch = CASE
        WHEN is_manual(e.experiment_id, 'sorbent_batch')
        THEN e.sorbent_batch ELSE EXCLUDED.sorbent_batch END,
    notes = CASE
        WHEN is_manual(e.experiment_id, 'notes')
        THEN e.notes ELSE EXCLUDED.notes END
"""


def read_experiments(path: Path = EXPERIMENTS_PATH) -> list[dict]:
    """Parse `path` as-is — no defaulting, no type coercion beyond what `json.loads` already
    does, so a null in the file stays `None` all the way to the upsert's parameters.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _row_params(experiment: dict) -> dict:
    params = {
        "experiment_id": experiment["experiment_id"],
        "start_time": datetime.fromisoformat(experiment["start_time"]),
        "end_time": datetime.fromisoformat(experiment["end_time"]),
        "duration_s": experiment["duration_s"],
    }
    params.update({column: experiment[key] for key, column in CORRECTABLE_COLUMNS.items()})
    return params


def load_experiments(conninfo: str | dict, path: Path = EXPERIMENTS_PATH) -> int:
    """Upsert every experiment in `path` into Postgres in one transaction.

    `conninfo` is either a psycopg conninfo string or a dict of `psycopg.connect` keyword
    arguments, matching `pipeline.pg_migrate.run_migrations`'s convention.

    Returns the number of experiments read from `path`. The upsert unconditionally submits
    every row for every experiment; whether a given field's new value actually sticks is
    decided by `is_manual(...)` inside the SQL above, not by anything in this function.
    """
    experiments = read_experiments(path)
    conn = psycopg.connect(**conninfo) if isinstance(conninfo, dict) else psycopg.connect(conninfo)
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("SET LOCAL app.actor = 'loader'")
            for experiment in experiments:
                cur.execute(_UPSERT_SQL, _row_params(experiment))
        return len(experiments)
    finally:
        conn.close()
