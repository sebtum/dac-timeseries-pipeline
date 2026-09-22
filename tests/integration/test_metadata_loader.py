"""Integration tests for `pipeline.metadata_loader`, per `docs/plans/M1.md` T7.

Throwaway-schema pattern, matching T6's `test_migrations.py`: `CREATE SCHEMA` /
`DROP SCHEMA ... CASCADE` per test rather than a throwaway database, migrations applied
fresh into it, teardown in the fixture's `finally` so a failing test still cleans up.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

import psycopg
import pytest

import scripts.migrate as migrate
from pipeline.metadata_loader import (
    CORRECTABLE_COLUMNS,
    EXPERIMENTS_PATH,
    STRUCTURAL_COLUMNS,
    load_experiments,
)
from pipeline.pg_migrate import run_migrations

pytestmark = pytest.mark.postgres


@dataclass(frozen=True)
class PgSchema:
    connect_kwargs: dict[str, str]
    schema: str


@pytest.fixture
def pg_schema(postgres_conn) -> PgSchema:
    """A fresh schema with the real `migrations/` already applied, dropped even on failure."""
    schema = f"test_metadata_loader_{uuid.uuid4().hex[:12]}"
    with postgres_conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    postgres_conn.commit()
    try:
        base = migrate.connect_kwargs(migrate.load_env())
        connect_kwargs = {**base, "options": f"-c search_path={schema}"}
        run_migrations(connect_kwargs)
        yield PgSchema(connect_kwargs=connect_kwargs, schema=schema)
    finally:
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    psycopg.sql.Identifier(schema)
                )
            )
        postgres_conn.commit()


def _fetch_experiment(pg_schema: PgSchema, experiment_id: str) -> dict:
    with (
        psycopg.connect(**pg_schema.connect_kwargs, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "SELECT experiment_id, start_time, end_time, duration_s, "
            "current_setpoint_nominal_a, air_flow_nominal_m3h, solvent_flow_nominal_lmin, "
            "operator, sorbent_batch, notes FROM experiment WHERE experiment_id = %s",
            (experiment_id,),
        )
        row = cur.fetchone()
        columns = [d.name for d in cur.description]
        return dict(zip(columns, row, strict=True))


def _field_source(pg_schema: PgSchema, experiment_id: str, field_name: str) -> str | None:
    with (
        psycopg.connect(**pg_schema.connect_kwargs, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "SELECT source FROM experiment_field_source "
            "WHERE experiment_id = %s AND field_name = %s",
            (experiment_id, field_name),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _set_manually(pg_schema: PgSchema, experiment_id: str, column: str, value) -> None:
    """A human correction: no `app.actor` set, matching the trigger's fail-safe default."""
    with (
        psycopg.connect(**pg_schema.connect_kwargs, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            psycopg.sql.SQL("UPDATE experiment SET {} = %s WHERE experiment_id = %s").format(
                psycopg.sql.Identifier(column)
            ),
            (value, experiment_id),
        )


def _write_json(tmp_path, experiments: list[dict]):
    path = tmp_path / "experiments.json"
    path.write_text(json.dumps(experiments), encoding="utf-8")
    return path


def test_load_populates_all_six_experiments(pg_schema):
    """V8."""
    count = load_experiments(pg_schema.connect_kwargs)
    assert count == 6

    with (
        psycopg.connect(**pg_schema.connect_kwargs, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT count(*) FROM experiment")
        (total,) = cur.fetchone()
    assert total == 6

    exp001 = _fetch_experiment(pg_schema, "EXP_001")
    assert exp001["operator"] == "J. Nguyen"
    assert exp001["sorbent_batch"] == "SB-2026-014"


def test_null_fields_survive_as_null_not_defaulted(pg_schema):
    """V8: EXP_003.notes, EXP_005.sorbent_batch, EXP_006.operator are NULL, not '' or a
    default.
    """
    load_experiments(pg_schema.connect_kwargs)

    assert _fetch_experiment(pg_schema, "EXP_003")["notes"] is None
    assert _fetch_experiment(pg_schema, "EXP_005")["sorbent_batch"] is None
    assert _fetch_experiment(pg_schema, "EXP_006")["operator"] is None


def test_rerun_cannot_revert_a_manual_null_correction(pg_schema):
    """V9, null case: EXP_005.sorbent_batch is null in the JSON; correct it by hand, re-run,
    and the correction survives.
    """
    load_experiments(pg_schema.connect_kwargs)
    _set_manually(pg_schema, "EXP_005", "sorbent_batch", "SB-2026-CORRECTED")

    load_experiments(pg_schema.connect_kwargs)

    assert _fetch_experiment(pg_schema, "EXP_005")["sorbent_batch"] == "SB-2026-CORRECTED"
    assert _field_source(pg_schema, "EXP_005", "sorbent_batch") == "manual_override"


def test_rerun_cannot_revert_a_manual_wrong_non_null_correction(pg_schema):
    """V9, wrong-non-null case — what a plain `COALESCE(EXCLUDED.col, e.col)` would not have
    caught (ADR-0012): the file holds a non-null value that disagrees with a human
    correction, and the correction must still win.
    """
    load_experiments(pg_schema.connect_kwargs)
    _set_manually(pg_schema, "EXP_001", "operator", "R. Okafor")

    load_experiments(pg_schema.connect_kwargs)

    assert _fetch_experiment(pg_schema, "EXP_001")["operator"] == "R. Okafor"
    assert _field_source(pg_schema, "EXP_001", "operator") == "manual_override"


def test_unset_actor_defaults_to_manual_override(pg_schema):
    """The fail-safe default, independent of the loader: a write made with `app.actor`
    unset is recorded as `manual_override`, never `loader`.
    """
    load_experiments(pg_schema.connect_kwargs)
    _set_manually(pg_schema, "EXP_002", "notes", "hand-edited note, no app.actor set")

    assert _field_source(pg_schema, "EXP_002", "notes") == "manual_override"


def test_loader_owned_field_change_is_recorded_as_loader(pg_schema, tmp_path):
    """The counterpart to manual_override: a field nobody has corrected still gets updated
    from a revised source file, and provenance attributes that change to `loader`.
    """
    load_experiments(pg_schema.connect_kwargs)
    assert _field_source(pg_schema, "EXP_002", "notes") is None  # insert never fires the
    # AFTER UPDATE trigger — no provenance row exists until something actually changes.

    experiments = json.loads(EXPERIMENTS_PATH.read_text(encoding="utf-8"))
    for experiment in experiments:
        if experiment["experiment_id"] == "EXP_002":
            experiment["notes"] = "revised note from an updated source file"
    edited_path = _write_json(tmp_path, experiments)

    load_experiments(pg_schema.connect_kwargs, path=edited_path)

    assert (
        _fetch_experiment(pg_schema, "EXP_002")["notes"]
        == "revised note from an updated source file"
    )
    assert _field_source(pg_schema, "EXP_002", "notes") == "loader"


def test_deleting_provenance_row_hands_field_back_to_loader(pg_schema):
    """The documented escape hatch (ADR-0012): deleting the `experiment_field_source` row
    un-protects the field, and the next run updates it from the file again.
    """
    load_experiments(pg_schema.connect_kwargs)
    _set_manually(pg_schema, "EXP_005", "sorbent_batch", "SB-2026-CORRECTED")
    load_experiments(pg_schema.connect_kwargs)
    assert _fetch_experiment(pg_schema, "EXP_005")["sorbent_batch"] == "SB-2026-CORRECTED"

    with (
        psycopg.connect(**pg_schema.connect_kwargs, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "DELETE FROM experiment_field_source WHERE experiment_id = %s AND field_name = %s",
            ("EXP_005", "sorbent_batch"),
        )

    load_experiments(pg_schema.connect_kwargs)

    # EXP_005.sorbent_batch is null in the real experiments.json — handed back to the
    # loader, which writes what the file actually says.
    assert _fetch_experiment(pg_schema, "EXP_005")["sorbent_batch"] is None


def test_row_removed_from_json_is_not_hard_deleted(pg_schema, tmp_path):
    """No hard deletes: an experiment dropped from a later copy of the file is left exactly
    as it is in the database.
    """
    load_experiments(pg_schema.connect_kwargs)

    experiments = json.loads(EXPERIMENTS_PATH.read_text(encoding="utf-8"))
    trimmed = [e for e in experiments if e["experiment_id"] != "EXP_004"]
    trimmed_path = _write_json(tmp_path, trimmed)

    load_experiments(pg_schema.connect_kwargs, path=trimmed_path)

    assert _fetch_experiment(pg_schema, "EXP_004")["experiment_id"] == "EXP_004"


def test_provenance_trigger_array_matches_correctable_columns(pg_schema):
    """ADR-0012 consequence: provenance covers only what's named in the trigger's array — a
    column added to the table and forgotten in the trigger is silently unprotected; one
    added to the trigger and not the table fails outright. Checked against the live
    database and against this module's own map, so either side drifting is caught.
    """
    with (
        psycopg.connect(**pg_schema.connect_kwargs, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'experiment' AND table_schema = %s",
            (pg_schema.schema,),
        )
        table_columns = {row[0] for row in cur.fetchall()}

        cur.execute(
            "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE p.proname = 'record_experiment_provenance' AND n.nspname = %s",
            (pg_schema.schema,),
        )
        (prosrc,) = cur.fetchone()

    array_literal = prosrc.split("ARRAY[", 1)[1].split("]", 1)[0]
    trigger_fields = set(re.findall(r"'([a-z0-9_]+)'", array_literal))

    table_correctable_columns = table_columns - STRUCTURAL_COLUMNS

    assert trigger_fields == table_correctable_columns
    assert trigger_fields == set(CORRECTABLE_COLUMNS.values())
