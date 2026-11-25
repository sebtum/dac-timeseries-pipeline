"""Integration tests for `pipeline.pg_migrate`, per `docs/plans/M1.md` T6.

Each test runs against a throwaway Postgres **schema** rather than a throwaway database
(T5's InfluxDB pattern) — `CREATE DATABASE` can't run inside a transaction and stands up a
whole new server-level object, but `CREATE SCHEMA` / `DROP SCHEMA ... CASCADE` gives the same
"start from nothing, clean up even on failure" guarantee at much lower cost, and every
migration file here is schema-search-path-relative (no fully-qualified table names), so
scoping a connection's `search_path` to the throwaway schema is enough to isolate it.
Teardown lives in the fixture's `finally`, not the test body, matching T5.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

import scripts.migrate as migrate
from pipeline.pg_migrate import ADVISORY_LOCK_KEY, run_migrations

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_schema(postgres_conn):
    """Connect-kwargs for a fresh, empty, uniquely-named schema; dropped even on failure."""
    schema = f"test_migrations_{uuid.uuid4().hex[:12]}"
    with postgres_conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    postgres_conn.commit()
    try:
        base = migrate.connect_kwargs(migrate.load_env())
        yield {**base, "options": f"-c search_path={schema}"}
    finally:
        with postgres_conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    psycopg.sql.Identifier(schema)
                )
            )
        postgres_conn.commit()


def _write_migrations(tmp_path, contents: dict[str, str]):
    directory = tmp_path / "migrations"
    directory.mkdir()
    for name, sql in contents.items():
        (directory / name).write_text(sql, encoding="utf-8")
    return directory


def _table_exists(pg_schema, table_name: str) -> bool:
    with psycopg.connect(**pg_schema, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_regclass(%s) IS NOT NULL",
            (table_name,),
        )
        (exists,) = cur.fetchone()
        return exists


def test_real_migrations_apply_clean_and_rerun_is_noop(pg_schema):
    """V10: the project's actual migrations/ directory, run against an empty schema."""
    first = run_migrations(pg_schema)
    assert first == ["0001", "0002", "0003", "0004"]
    assert _table_exists(pg_schema, "experiment")
    assert _table_exists(pg_schema, "experiment_field_source")
    assert _table_exists(pg_schema, "experiment_metrics")
    assert _table_exists(pg_schema, "signal_quality")
    assert _table_exists(pg_schema, "comparison_kpi")
    assert _table_exists(pg_schema, "comparison_pair")
    assert _table_exists(pg_schema, "comparison_pair_kpi")

    second = run_migrations(pg_schema)
    assert second == []


def test_ordering_is_by_parsed_version_not_filename_string(pg_schema, tmp_path):
    """'10_b.sql' sorts before '2_a.sql' as strings but must run after it as versions —
    if the runner ever regresses to string/filesystem ordering, '10_b' inserting into a
    table '2_a' hasn't created yet raises, and this test fails loudly instead of silently
    passing under lucky directory-listing order.
    """
    directory = _write_migrations(
        tmp_path,
        {
            "2_a.sql": (
                "CREATE TABLE order_log (id serial PRIMARY KEY, step text NOT NULL);"
                "INSERT INTO order_log (step) VALUES ('a');"
            ),
            "10_b.sql": "INSERT INTO order_log (step) VALUES ('b');",
        },
    )

    applied = run_migrations(pg_schema, directory=directory)
    assert applied == ["2", "10"]

    with psycopg.connect(**pg_schema, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT step FROM order_log ORDER BY id")
        assert [row[0] for row in cur.fetchall()] == ["a", "b"]


def test_edited_applied_migration_fails_loudly_and_is_not_reapplied(pg_schema, tmp_path):
    directory = _write_migrations(tmp_path, {"0001_x.sql": "CREATE TABLE t1 (id int);"})
    run_migrations(pg_schema, directory=directory)
    assert _table_exists(pg_schema, "t1")

    (directory / "0001_x.sql").write_text(
        "CREATE TABLE t1 (id int); CREATE TABLE t2 (id int);", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="0001"):
        run_migrations(pg_schema, directory=directory)

    # Refused before reapplying, so the edited file's extra statement never ran.
    assert not _table_exists(pg_schema, "t2")


def test_failing_migration_leaves_schema_unchanged(pg_schema, tmp_path):
    """Migration 0001 commits; 0002 fails partway. 0001's effect survives (it's a separate,
    already-committed transaction); 0002's effect — including the part of its own SQL that
    would otherwise have succeeded — is fully rolled back.
    """
    directory = _write_migrations(
        tmp_path,
        {
            "0001_ok.sql": "CREATE TABLE keep_me (id int);",
            "0002_bad.sql": "CREATE TABLE bar (id int); INSERT INTO bar (bogus_col) VALUES (1);",
        },
    )

    with pytest.raises(psycopg.errors.UndefinedColumn):
        run_migrations(pg_schema, directory=directory)

    assert _table_exists(pg_schema, "keep_me")
    assert not _table_exists(pg_schema, "bar")

    with psycopg.connect(**pg_schema, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        assert [row[0] for row in cur.fetchall()] == ["0001"]


def test_concurrent_runner_is_rejected_not_raced(pg_schema, tmp_path):
    directory = _write_migrations(tmp_path, {"0001_x.sql": "CREATE TABLE t1 (id int);"})

    holder = psycopg.connect(**pg_schema, autocommit=True)
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))

        with pytest.raises(RuntimeError, match="advisory lock"):
            run_migrations(pg_schema, directory=directory)
        assert not _table_exists(pg_schema, "t1")
    finally:
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
        holder.close()

    # Lock released — the same call now succeeds.
    applied = run_migrations(pg_schema, directory=directory)
    assert applied == ["0001"]


def _primary_key(pg_schema, table_name: str) -> list[str]:
    with psycopg.connect(**pg_schema, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = to_regclass(%s) AND i.indisprimary "
            "ORDER BY array_position(i.indkey::int2[], a.attnum)",
            (table_name,),
        )
        return [row[0] for row in cur.fetchall()]


def test_migration_0003_pins_the_keys_foreign_keys_and_status_check(pg_schema):
    """M4: the two summary tables have the pinned primary keys, reference `experiment`, and
    refuse a status outside complete/partial/none."""
    run_migrations(pg_schema)

    assert _primary_key(pg_schema, "experiment_metrics") == [
        "experiment_id",
        "metrics_version",
        "metric",
    ]
    assert _primary_key(pg_schema, "signal_quality") == [
        "experiment_id",
        "metrics_version",
        "source",
        "signal",
    ]

    with psycopg.connect(**pg_schema, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text, confrelid::regclass::text FROM pg_constraint "
            "WHERE contype = 'f' AND conrelid IN "
            "(to_regclass('experiment_metrics'), to_regclass('signal_quality')) ORDER BY 1"
        )
        references = [tuple(name.rpartition(".")[2] for name in row) for row in cur.fetchall()]
        assert references == [
            ("experiment_metrics", "experiment"),
            ("signal_quality", "experiment"),
        ]

        cur.execute(
            "INSERT INTO experiment (experiment_id, start_time, end_time, duration_s) "
            "VALUES ('E1', now(), now(), 1)"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO experiment_metrics (experiment_id, metrics_version, policy_version, "
                "metric, unit, status) VALUES ('E1', 'v', 'p', 'm', 'kg', 'bogus')"
            )
        with pytest.raises(psycopg.errors.NotNullViolation):
            cur.execute(
                "INSERT INTO experiment_metrics (experiment_id, metrics_version, policy_version, "
                "metric, unit) VALUES ('E1', 'v', NULL, 'm', 'kg')"
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO experiment_metrics (experiment_id, metrics_version, policy_version, "
                "metric, unit) VALUES ('NOPE', 'v', 'p', 'm', 'kg')"
            )
        # A null value, coverage and status is allowed (a share, or a metric with no value).
        cur.execute(
            "INSERT INTO experiment_metrics (experiment_id, metrics_version, policy_version, "
            "metric, unit) VALUES ('E1', 'v', 'p', 'm', 'kg')"
        )


def test_migration_0004_pins_the_keys_checks_and_foreign_keys(pg_schema):
    """M6 (S6.8): the three comparison tables have the pinned primary keys, the experiment
    references, the pair-to-KPI cascade, and refuse a bad status, an unordered pair and an
    unknown experiment."""
    run_migrations(pg_schema)

    assert _primary_key(pg_schema, "comparison_kpi") == ["experiment_id", "compare_version", "kpi"]
    assert _primary_key(pg_schema, "comparison_pair") == ["a", "b", "compare_version"]
    assert _primary_key(pg_schema, "comparison_pair_kpi") == ["a", "b", "compare_version", "kpi"]

    with psycopg.connect(**pg_schema, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text, confrelid::regclass::text, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE contype = 'f' AND conrelid IN "
            "(to_regclass('comparison_kpi'), to_regclass('comparison_pair'), "
            "to_regclass('comparison_pair_kpi')) ORDER BY 1, 3"
        )
        foreign_keys = [
            (child.rpartition(".")[2], parent.rpartition(".")[2], definition)
            for child, parent, definition in cur.fetchall()
        ]
        assert foreign_keys == [
            (
                "comparison_kpi",
                "experiment",
                "FOREIGN KEY (experiment_id) REFERENCES experiment(experiment_id)",
            ),
            (
                "comparison_pair",
                "experiment",
                "FOREIGN KEY (a) REFERENCES experiment(experiment_id)",
            ),
            (
                "comparison_pair",
                "experiment",
                "FOREIGN KEY (b) REFERENCES experiment(experiment_id)",
            ),
            (
                "comparison_pair_kpi",
                "comparison_pair",
                "FOREIGN KEY (a, b, compare_version) REFERENCES comparison_pair(a, b, "
                "compare_version) ON DELETE CASCADE",
            ),
        ]

        cur.execute(
            "INSERT INTO experiment (experiment_id, start_time, end_time, duration_s) "
            "VALUES ('E1', now(), now(), 1), ('E2', now(), now(), 1)"
        )
        kpi = (
            "INSERT INTO comparison_kpi (experiment_id, compare_version, kpi, policy_version, "
            "metrics_version, unit, status) VALUES (%s, 'c', 'k', 'p', 'm', 'V', %s)"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(kpi, ("E1", "bogus"))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(kpi, ("NOPE", "complete"))
        # A null value, coverage and interval is allowed (status 'none').
        cur.execute(kpi, ("E1", "none"))
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(kpi, ("E1", "none"))

        pair = (
            "INSERT INTO comparison_pair (a, b, compare_version, conditions_status, differing) "
            "VALUES (%s, %s, 'c', %s, '')"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(pair, ("E1", "E2", "bogus"))
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(pair, ("E2", "E1", "supported"))  # a < b
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(pair, ("E1", "E1", "supported"))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(pair, ("E1", "NOPE", "supported"))
        cur.execute(pair, ("E1", "E2", "same_conditions"))

        pair_kpi = (
            "INSERT INTO comparison_pair_kpi (a, b, compare_version, kpi, unit, coverage_status) "
            "VALUES (%s, %s, 'c', 'k', 'V', %s)"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(pair_kpi, ("E1", "E2", "bogus"))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(pair_kpi, ("E1", "E3", "both_complete"))  # no such pair
        cur.execute(pair_kpi, ("E1", "E2", "not_available"))

        cur.execute("DELETE FROM comparison_pair WHERE a = 'E1' AND b = 'E2'")
        cur.execute("SELECT count(*) FROM comparison_pair_kpi")
        assert cur.fetchone() == (0,)
