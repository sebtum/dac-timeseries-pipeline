"""Unit tests for `pipeline.comparison_loader` (M6 T2): the mapping and the refusals that need no
database. The Postgres side (S6.8 to S6.10) is in `tests/integration/test_comparison_loader.py`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pipeline import comparison_loader as cl
from scripts import load_comparison

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "contracts" / "examples" / "comparison_summary.example.json"
REAL = REPO_ROOT / "reports" / "comparison_summary.json"
SCHEMA = json.loads(cl.SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_maps_to_counts_and_versions(example):
    rows = cl.rows_from_summary(example)
    assert rows.compare_version == "m5-v1"
    assert rows.counts() == {"kpis": 15, "pairs": 3, "pair_kpis": 15}
    assert rows.experiment_ids() == ["EXP_001", "EXP_002", "EXP_003"]
    assert {r["policy_version"] for r in rows.kpis} == {"m3-v1"}
    assert {r["metrics_version"] for r in rows.kpis} == {"m4-v1"}
    assert {r["compare_version"] for r in rows.kpis + rows.pairs + rows.pair_kpis} == {"m5-v1"}


def test_rows_use_exactly_the_ddl_columns(example):
    rows = cl.rows_from_summary(example)
    assert all(tuple(r) == cl.KPI_COLUMNS for r in rows.kpis)
    assert all(tuple(r) == cl.PAIR_COLUMNS for r in rows.pairs)
    assert all(tuple(r) == cl.PAIR_KPI_COLUMNS for r in rows.pair_kpis)


def test_kpi_rows_copy_the_summary_values_in_summary_order(example):
    rows = cl.rows_from_summary(example)
    first = example["experiments"][0]
    mine = [r for r in rows.kpis if r["experiment_id"] == first["experiment_id"]]
    assert [r["kpi"] for r in mine] == list(first["kpis"])
    for row in mine:
        kpi = first["kpis"][row["kpi"]]
        for key in ("value", "unit", "coverage", "status", "interval_low", "interval_high"):
            assert row[key] == kpi[key]
    # Experiments keep the summary's order.
    assert [r["experiment_id"] for r in rows.kpis[::5]] == ["EXP_001", "EXP_002", "EXP_003"]


def test_pair_rows_join_differing_in_factor_order(example):
    rows = cl.rows_from_summary(example)
    by_pair = {(r["a"], r["b"]): r for r in rows.pairs}
    assert by_pair[("EXP_001", "EXP_002")]["differing"] == "current_setpoint"
    assert by_pair[("EXP_001", "EXP_003")]["differing"] == "air_flow,sorbent_batch"
    assert by_pair[("EXP_002", "EXP_003")]["differing"] == "current_setpoint,air_flow,sorbent_batch"
    assert by_pair[("EXP_001", "EXP_002")]["conditions_status"] == "supported"
    assert all(r["a"] < r["b"] for r in rows.pairs)


def test_no_differing_factor_gives_the_empty_string(example):
    example["comparisons"][0]["differing"] = []
    example["comparisons"][0]["conditions_status"] = "same_conditions"
    rows = cl.rows_from_summary(example)
    assert rows.pairs[0]["differing"] == ""


def test_pair_kpi_rows_copy_the_summary_values(example):
    rows = cl.rows_from_summary(example)
    comparison = example["comparisons"][0]
    mine = [r for r in rows.pair_kpis if (r["a"], r["b"]) == (comparison["a"], comparison["b"])]
    assert [r["kpi"] for r in mine] == [k["name"] for k in comparison["kpis"]]
    for row, kpi in zip(mine, comparison["kpis"], strict=True):
        for key in (
            "unit",
            "difference",
            "interval_low",
            "interval_high",
            "excludes_zero",
            "coverage_status",
        ):
            assert row[key] == kpi[key]


def test_null_values_stay_null(example):
    kpi = example["experiments"][0]["kpis"]["sec_kwh_per_kg"]
    kpi.update(value=None, interval_low=None, interval_high=None, status="none")
    pair_kpi = example["comparisons"][0]["kpis"][0]
    pair_kpi.update(
        difference=None,
        interval_low=None,
        interval_high=None,
        excludes_zero=None,
        coverage_status="not_available",
    )
    rows = cl.rows_from_summary(example)
    row = next(r for r in rows.kpis if r["kpi"] == "sec_kwh_per_kg")
    assert (row["value"], row["interval_low"], row["interval_high"]) == (None, None, None)
    assert rows.pair_kpis[0]["excludes_zero"] is None


def test_real_summary_gives_30_15_75():
    rows = cl.rows_from_summary(json.loads(REAL.read_text(encoding="utf-8")))
    assert rows.counts() == {"kpis": 30, "pairs": 15, "pair_kpis": 75}
    assert rows.experiment_ids() == [f"EXP_00{i}" for i in range(1, 7)]


def test_pair_not_ordered_is_refused(example):
    example["comparisons"][0].update(a="EXP_002", b="EXP_001")
    with pytest.raises(ValueError, match="a < b"):
        cl.rows_from_summary(example)


def test_duplicate_pair_is_refused(example):
    example["comparisons"].append(copy.deepcopy(example["comparisons"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        cl.rows_from_summary(example)


def test_committed_files_conform_to_the_contract(example):
    assert cl.validate_summary(example, SCHEMA) == []
    assert cl.validate_summary(json.loads(REAL.read_text(encoding="utf-8")), SCHEMA) == []


def test_missing_comparisons_is_a_contract_problem(example):
    del example["comparisons"]
    problems = cl.validate_summary(example, SCHEMA)
    assert problems
    assert any("comparisons" in p for p in problems)


# ---------------------------------------------------------------- refusals before any database


def _run(tmp_path, summary, env=None) -> int:
    path = tmp_path / "summary.json"
    if summary is not None:
        path.write_text(json.dumps(summary), encoding="utf-8")
    return cl.run(cl.Config(summary_path=path, pg_schema="nowhere"), env=env or {})


def test_unreadable_summary_exits_2(tmp_path, capsys):
    assert _run(tmp_path, None) == 2
    assert "summary_unreadable" in capsys.readouterr().err


def test_not_json_exits_2(tmp_path, capsys):
    path = tmp_path / "summary.json"
    path.write_text("{not json", encoding="utf-8")
    assert cl.run(cl.Config(summary_path=path), env={}) == 2
    assert "summary_unreadable" in capsys.readouterr().err


def test_contract_failure_exits_2_before_postgres(tmp_path, example, capsys):
    del example["comparisons"]
    assert _run(tmp_path, example) == 2
    assert "contract_failed" in capsys.readouterr().err


def test_unordered_pair_exits_2(tmp_path, example, capsys):
    example["comparisons"][0].update(a="EXP_002", b="EXP_001")
    assert _run(tmp_path, example) == 2
    assert "contract_failed" in capsys.readouterr().err


def test_postgres_not_configured_exits_2(tmp_path, example, capsys):
    assert _run(tmp_path, example, env={}) == 2
    assert "postgres_not_configured" in capsys.readouterr().err


def test_postgres_unreachable_exits_2(tmp_path, example, capsys):
    env = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "1",
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "x",
    }
    assert _run(tmp_path, example, env=env) == 2
    assert "postgres_unreachable" in capsys.readouterr().err


def test_bad_schema_name_exits_2(tmp_path, example, capsys):
    env = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "1",
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "x",
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    assert cl.run(cl.Config(summary_path=path, pg_schema="a; drop"), env=env) == 2
    assert "postgres_unreachable" in capsys.readouterr().err


def test_cli_defaults_and_arguments():
    default = load_comparison.parse_args([])
    assert default.summary_path == REAL
    assert default.pg_schema == "public"
    custom = load_comparison.parse_args(["--summary", "x.json", "--pg-schema", "s1"])
    assert custom.summary_path == Path("x.json")
    assert custom.pg_schema == "s1"
