"""Integration tests for the comparison loader (M6 T2; S6.9 and S6.10).

Every test runs against a throwaway Postgres schema (migrations 0001 to 0004 applied, a few
`experiment` rows inserted), created and dropped in a fixture's `finally`, like
`tests/integration/test_migrations.py`. Nothing here touches the `public` schema.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import psycopg.rows
import psycopg.sql
import pytest

import scripts.migrate as migrate
from pipeline import comparison_loader as cl
from pipeline.pg_migrate import MIGRATIONS_DIR, run_migrations
from scripts import load_comparison

pytestmark = pytest.mark.postgres

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "contracts" / "examples" / "comparison_summary.example.json"
REAL = REPO_ROOT / "reports" / "comparison_summary.json"


def _kwargs(schema: str) -> dict:
    return {**migrate.connect_kwargs(migrate.load_env()), "options": f"-c search_path={schema}"}


def _insert_experiments(schema: str, ids: list[str]) -> None:
    with psycopg.connect(**_kwargs(schema), autocommit=True) as conn, conn.cursor() as cur:
        for experiment_id in ids:
            cur.execute(
                "INSERT INTO experiment (experiment_id, start_time, end_time, duration_s) "
                "VALUES (%s, now(), now(), 1)",
                (experiment_id,),
            )


def _make_schema(postgres_conn, migrations_dir: Path | None = None) -> str:
    schema = f"test_cmp_loader_{uuid.uuid4().hex[:12]}"
    with postgres_conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    postgres_conn.commit()
    run_migrations(_kwargs(schema), directory=migrations_dir or MIGRATIONS_DIR)
    return schema


def _drop_schema(postgres_conn, schema: str) -> None:
    with postgres_conn.cursor() as cur:
        cur.execute(
            psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                psycopg.sql.Identifier(schema)
            )
        )
    postgres_conn.commit()


@pytest.fixture
def schema(postgres_conn):
    """A schema migrated to 0004 with EXP_001 to EXP_006 loaded; dropped even on failure."""
    name = _make_schema(postgres_conn)
    try:
        _insert_experiments(name, [f"EXP_00{i}" for i in range(1, 7)])
        yield name
    finally:
        _drop_schema(postgres_conn, name)


def _dump(schema: str) -> dict[str, list[tuple]]:
    """Every row of the three tables, in primary-key order."""
    dumps = {}
    with psycopg.connect(**_kwargs(schema), autocommit=True) as conn, conn.cursor() as cur:
        for table in cl.TABLES:
            cur.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3, 4")
            dumps[table] = cur.fetchall()
    return dumps


def _rows(schema: str, table: str) -> list[dict]:
    with (
        psycopg.connect(
            **_kwargs(schema), autocommit=True, row_factory=psycopg.rows.dict_row
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(f"SELECT * FROM {table}")
        return cur.fetchall()


def _load(schema: str, path: Path) -> int:
    return load_comparison.main(["--summary", str(path), "--pg-schema", schema])


def _write(tmp_path: Path, summary: dict, name: str = "summary.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


def _by_key(rows: list[dict], key: tuple[str, ...]) -> dict:
    return {tuple(r[k] for k in key): r for r in rows}


# --------------------------------------------------------------------------------------- S6.9


def test_example_rows_equal_their_summary_entries(schema, capsys):
    """Every stored value is the summary's, checked against the JSON, not against the mapping."""
    assert _load(schema, EXAMPLE) == 0
    assert capsys.readouterr().out.strip() == "load_comparison: m5-v1 kpis=15 pairs=3 pair_kpis=15"
    summary = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    kpis = _by_key(_rows(schema, "comparison_kpi"), ("experiment_id", "kpi"))
    assert len(kpis) == 15
    for experiment in summary["experiments"]:
        for name, kpi in experiment["kpis"].items():
            row = kpis[(experiment["experiment_id"], name)]
            assert row["compare_version"] == "m5-v1"
            assert row["policy_version"] == summary["policy_version"]
            assert row["metrics_version"] == summary["metrics_version"]
            for key in ("value", "unit", "coverage", "status", "interval_low", "interval_high"):
                assert row[key] == kpi[key], (experiment["experiment_id"], name, key)

    pairs = _by_key(_rows(schema, "comparison_pair"), ("a", "b"))
    pair_kpis = _by_key(_rows(schema, "comparison_pair_kpi"), ("a", "b", "kpi"))
    assert len(pairs) == 3
    assert len(pair_kpis) == 15
    for comparison in summary["comparisons"]:
        pair = pairs[(comparison["a"], comparison["b"])]
        assert pair["conditions_status"] == comparison["conditions_status"]
        assert pair["differing"] == ",".join(comparison["differing"])
        for kpi in comparison["kpis"]:
            row = pair_kpis[(comparison["a"], comparison["b"], kpi["name"])]
            for key in (
                "unit",
                "difference",
                "interval_low",
                "interval_high",
                "excludes_zero",
                "coverage_status",
            ):
                assert row[key] == kpi[key], (comparison["a"], comparison["b"], kpi["name"], key)

    differing = {(r["a"], r["b"]): r["differing"] for r in pairs.values()}
    assert differing[("EXP_002", "EXP_003")] == "current_setpoint,air_flow,sorbent_batch"


def test_real_summary_writes_30_15_75_and_a_rerun_is_identical(schema, capsys):
    assert _load(schema, REAL) == 0
    assert capsys.readouterr().out.strip() == "load_comparison: m5-v1 kpis=30 pairs=15 pair_kpis=75"
    first = _dump(schema)
    assert [len(first[t]) for t in cl.TABLES] == [30, 15, 75]

    assert _load(schema, REAL) == 0
    assert _dump(schema) == first


def test_module_entry_point_runs_as_python_dash_m(schema):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.load_comparison",
            "--summary",
            str(EXAMPLE),
            "--pg-schema",
            schema,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "load_comparison: m5-v1 kpis=15 pairs=3 pair_kpis=15"
    assert [len(rows) for rows in _dump(schema).values()] == [15, 3, 15]


def test_read_back_counts_are_per_version(schema):
    rows = cl.rows_from_summary(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    with cl.pg_connect(_kwargs(schema), schema) as conn:
        assert cl.load(conn, rows) == {"kpis": 15, "pairs": 3, "pair_kpis": 15}
        assert cl.read_back(conn, "m5-v1") == {"kpis": 15, "pairs": 3, "pair_kpis": 15}
        assert cl.read_back(conn, "other") == {"kpis": 0, "pairs": 0, "pair_kpis": 0}


# -------------------------------------------------------------------------------------- S6.10


def test_a_smaller_summary_replaces_its_version_and_leaves_others(schema, tmp_path):
    summary = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    other = copy.deepcopy(summary)
    other["compare_version"] = "m5-v0"
    assert _load(schema, _write(tmp_path, summary)) == 0
    assert _load(schema, _write(tmp_path, other, "other.json")) == 0
    counts = {}
    with psycopg.connect(**_kwargs(schema), autocommit=True) as conn, conn.cursor() as cur:
        for table in cl.TABLES:
            cur.execute(f"SELECT compare_version, count(*) FROM {table} GROUP BY 1 ORDER BY 1")
            counts[table] = cur.fetchall()
    assert counts == {
        "comparison_kpi": [("m5-v0", 15), ("m5-v1", 15)],
        "comparison_pair": [("m5-v0", 3), ("m5-v1", 3)],
        "comparison_pair_kpi": [("m5-v0", 15), ("m5-v1", 15)],
    }
    before_other = [[row for row in rows if "m5-v0" in row] for rows in _dump(schema).values()]

    smaller = copy.deepcopy(summary)
    smaller["comparisons"] = smaller["comparisons"][:2]
    assert _load(schema, _write(tmp_path, smaller)) == 0

    after = _dump(schema)
    assert [len([r for r in rows if "m5-v1" in r]) for rows in after.values()] == [15, 2, 10]
    assert [[row for row in rows if "m5-v0" in row] for rows in after.values()] == before_other
    pairs = {(r[0], r[1]) for r in after["comparison_pair"] if r[2] == "m5-v1"}
    assert pairs == {("EXP_001", "EXP_002"), ("EXP_001", "EXP_003")}
    gone = [r for r in after["comparison_pair_kpi"] if (r[0], r[1]) == ("EXP_002", "EXP_003")]
    assert [r[2] for r in gone] == ["m5-v0"] * 5


def test_summary_failing_the_contract_exits_2_and_changes_nothing(schema, tmp_path, capsys):
    summary = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert _load(schema, _write(tmp_path, summary)) == 0
    before = _dump(schema)
    capsys.readouterr()

    broken = copy.deepcopy(summary)
    del broken["comparisons"]
    assert _load(schema, _write(tmp_path, broken, "broken.json")) == 2
    assert "contract_failed" in capsys.readouterr().err
    assert _dump(schema) == before


def test_unknown_experiment_id_exits_2_and_changes_nothing(postgres_conn, tmp_path, capsys):
    name = _make_schema(postgres_conn)
    try:
        _insert_experiments(name, ["EXP_001", "EXP_002"])  # the example also names EXP_003
        assert _load(name, EXAMPLE) == 2
        err = capsys.readouterr().err
        assert "experiment_missing_in_postgres" in err
        assert "EXP_003" in err
        assert [len(rows) for rows in _dump(name).values()] == [0, 0, 0]
    finally:
        _drop_schema(postgres_conn, name)


def test_schema_without_0004_exits_2(postgres_conn, tmp_path, capsys):
    older = tmp_path / "migrations_to_0003"
    older.mkdir()
    for path in MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 3:
            (older / path.name).write_bytes(path.read_bytes())
    name = _make_schema(postgres_conn, older)
    try:
        _insert_experiments(name, ["EXP_001", "EXP_002", "EXP_003"])
        assert _load(name, EXAMPLE) == 2
        err = capsys.readouterr().err
        assert "postgres_not_migrated" in err
        assert "comparison_kpi" in err
        with psycopg.connect(**_kwargs(name), autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('comparison_kpi') IS NULL")
            assert cur.fetchone() == (True,)
    finally:
        _drop_schema(postgres_conn, name)


def test_unreadable_summary_exits_2(schema, tmp_path):
    assert _load(schema, tmp_path / "missing.json") == 2
    assert [len(rows) for rows in _dump(schema).values()] == [0, 0, 0]


# ---------------------------------------------------------------------------- exits 3 and 4


def test_a_failing_write_rolls_back_and_exits_3(schema, tmp_path, monkeypatch, capsys):
    summary = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert _load(schema, _write(tmp_path, summary)) == 0
    before = _dump(schema)
    capsys.readouterr()

    original = cl.rows_from_summary

    def bad_rows(summary):
        rows = original(summary)
        rows.pair_kpis[-1]["coverage_status"] = "bogus"  # fails the table's check, last insert
        return rows

    monkeypatch.setattr(cl, "rows_from_summary", bad_rows)
    assert _load(schema, EXAMPLE) == 3
    assert "rolled back" in capsys.readouterr().err
    assert _dump(schema) == before


def test_load_rolls_back_the_delete_when_an_insert_fails(schema):
    rows = cl.rows_from_summary(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    with cl.pg_connect(_kwargs(schema), schema) as conn:
        cl.load(conn, rows)
        before = _dump(schema)
        bad = cl.ComparisonRows(
            rows.compare_version, rows.kpis, rows.pairs[:1] * 2, []
        )  # duplicate pair key
        with pytest.raises(psycopg.errors.UniqueViolation):
            cl.load(conn, bad)
    assert _dump(schema) == before


def test_a_read_back_difference_exits_4(schema, monkeypatch, capsys):
    monkeypatch.setattr(
        cl, "read_back", lambda conn, version: {"kpis": 0, "pairs": 0, "pair_kpis": 0}
    )
    assert _load(schema, EXAMPLE) == 4
    assert "read-back counts differ" in capsys.readouterr().err
