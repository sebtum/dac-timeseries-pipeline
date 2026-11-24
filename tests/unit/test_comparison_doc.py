"""The comparison method document matches the comparison code (M5, scenario S5.26).

`docs/comparison.md` is read by people; `pipeline/compare.py` is what the numbers are made with.
This test reads the document's tables and compares them with the code: every parameter of `POLICY`
with its value, every KPI with its unit, every factor, every model with its predictors, and every
status. The statuses are not constants in the code, so they are collected from the functions that
produce them (by calling them on small inputs, and for the evidence rule also from the source text).
The mutation tests change a copy of the document text in memory and check that the comparison
notices.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from pipeline import compare

DOC = Path(__file__).resolve().parents[2] / "docs" / "comparison.md"
DOC_TEXT = DOC.read_text(encoding="utf-8")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table(text: str, header: list[str]) -> list[list[str]]:
    """Body rows of the table whose header row starts with these cells (no header row, no rule)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _cells(line)[: len(header)] == header:
            rows = []
            for body in lines[i + 2 :]:  # skip the |---| rule
                if not body.startswith("|"):
                    break
                rows.append(_cells(body))
            return rows
    raise AssertionError(f"no table headed {header} in the document")


def keyed(text: str, header: list[str]) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for cells in table(text, header):
        name = cells[0].strip("`")
        assert name not in rows, f"{name} appears twice in the {header[0]} table"
        rows[name] = cells[1:]
    return rows


# ---------------------------------------------------------------------------- code-side statuses


def evidence_statuses() -> set[str]:
    """Every status `compare.evidence` can return, found by calling it on one case each."""

    def entry(low: float, high: float) -> dict:
        return {
            "testable": True,
            "terms": [
                {"name": name, "interval_low": low, "interval_high": high}
                for name in compare.MODELS["hydrolyzer"]
            ],
        }

    pooled = {
        "model": "hydrolyzer",
        "window": "steady",
        "terms": [
            {"name": n, "coefficient": 0.0, "interval_low": -1.0, "interval_high": 1.0}
            for n in compare.MODELS["hydrolyzer"]
        ],
    }
    cases = [
        [],  # no testable fit
        [entry(1, 2), entry(1, 2)],  # all exclude zero, one sign
        [entry(1, 2)],  # one fit, excludes zero
        [entry(1, 2), entry(-2, -1)],  # opposite signs
        [entry(1, 2), entry(-1, 1)],  # anything else
    ]
    found = {row["status"] for case in cases for row in compare.evidence(case, pooled)}
    literals = set(re.findall(r'status(?:, sign)? = "(\w+)"', inspect.getsource(compare.evidence)))
    assert found == literals, "evidence() has a status the probe cases do not reach"
    return found


def conditions_statuses() -> set[str]:
    def factors(n_differing: int) -> list[dict]:
        return [{"factor": f"f{i}", "differs": i < n_differing} for i in range(3)]

    return {compare.conditions_status(factors(n))[0] for n in (0, 1, 2)}


def coverage_statuses() -> set[str]:
    def kpis(value: float | None, status: str) -> compare.KpiResult:
        entries = {name: {"value": value, "status": status} for name in compare.KPI_UNITS}
        samples = {name: [1.0, 2.0] if value is not None else [] for name in compare.KPI_UNITS}
        return compare.KpiResult(entries=entries, samples=samples)

    complete, partial, missing = kpis(1.0, "complete"), kpis(1.0, "partial"), kpis(None, "none")
    return {
        compare.kpi_differences(complete, other)[0]["coverage_status"]
        for other in (complete, partial, missing)
    }


# ---------------------------------------------------------------------------- the comparison


def problems(text: str) -> list[str]:
    """Every way the document text differs from the code; empty when they agree."""
    found: list[str] = []

    params = keyed(text, ["Parameter", "Value"])
    for name in sorted(set(compare.POLICY) - set(params)):
        found.append(f"parameter {name} is not in the table")
    for name in sorted(set(params) - set(compare.POLICY)):
        found.append(f"parameter {name} is in the table but not in POLICY")
    for name, value in compare.POLICY.items():
        if name not in params:
            continue
        cell = params[name][0].strip("`")
        same = cell == value if isinstance(value, str) else _number(cell) == float(value)
        if not same:
            found.append(f"{name}: document says {cell}, code says {value}")

    fixed = keyed(text, ["Constant", "Value"])
    if "PIVOT_REL" not in fixed or _number(fixed["PIVOT_REL"][0]) != compare.PIVOT_REL:
        found.append("PIVOT_REL differs or is missing")

    kpis = keyed(text, ["KPI", "Unit"])
    if {k: v[0].strip("`") for k, v in kpis.items()} != compare.KPI_UNITS:
        found.append("the KPIs or their units differ from KPI_UNITS")

    factors = [c[0].strip("`") for c in table(text, ["Factor", "Differs when"])]
    if factors != list(compare.FACTORS):
        found.append("the factors differ from FACTORS")

    models = {
        k: tuple(p.strip() for p in v[0].split(","))
        for k, v in keyed(text, ["Model", "Predictors, in order"]).items()
    }
    if models != dict(compare.MODELS):
        found.append("the models or their predictors differ from MODELS")
    units = {k: v[0] for k, v in keyed(text, ["Predictor", "Unit"]).items()}
    if units != compare.PREDICTOR_UNITS:
        found.append("the predictor units differ from PREDICTOR_UNITS")

    for header, expected, label in (
        (["Evidence status", "Rule"], evidence_statuses(), "evidence statuses"),
        (["Conditions status", "Rule"], conditions_statuses(), "conditions statuses"),
        (["Coverage status", "Rule"], coverage_statuses(), "coverage statuses"),
    ):
        if set(keyed(text, header)) != expected:
            found.append(f"the {label} differ from the code")

    if f"`{compare.COMPARE_VERSION}`" not in text:
        found.append("the document does not name the compare version")
    if f"`{compare.COMPARE_FINGERPRINT[:8]}`" not in text:
        found.append("the document does not give the fingerprint prefix")
    return found


def _number(cell: str) -> float:
    return float(cell.strip("`"))


# ---------------------------------------------------------------------------- the document


def test_s5_26_the_document_agrees_with_the_code():
    assert problems(DOC_TEXT) == []


@pytest.mark.parametrize("name", sorted(compare.POLICY))
def test_s5_26_each_policy_key_has_its_value_in_the_document(name):
    cell = keyed(DOC_TEXT, ["Parameter", "Value"])[name][0].strip("`")
    value = compare.POLICY[name]
    assert cell == value if isinstance(value, str) else float(cell) == float(value)


def test_s5_26_the_parameter_table_has_exactly_the_policy_keys():
    assert set(keyed(DOC_TEXT, ["Parameter", "Value"])) == set(compare.POLICY)


@pytest.mark.parametrize("name", sorted(compare.KPI_UNITS))
def test_s5_26_each_kpi_has_its_unit(name):
    assert keyed(DOC_TEXT, ["KPI", "Unit"])[name][0].strip("`") == compare.KPI_UNITS[name]


def test_s5_26_every_factor_is_listed_in_order():
    listed = [c[0].strip("`") for c in table(DOC_TEXT, ["Factor", "Differs when"])]
    assert listed == list(compare.FACTORS)


def test_s5_26_the_status_tables_match_what_the_code_can_return():
    assert evidence_statuses() == {
        "supported",
        "single_run",
        "inconsistent",
        "not_resolved",
        "not_testable",
    }
    assert conditions_statuses() == {"same_conditions", "supported", "confounded"}
    assert coverage_statuses() == {"both_complete", "partial_coverage", "not_available"}


def test_the_document_names_its_reading_choices_and_limits():
    for phrase in (
        "838 of 840",
        "block boundaries",
        "testable on their own",
        "centred cross-product matrix",
        "A flat voltage is not testable",
        "Empty blocks are left out",
        "not evidence of no effect",
        "One run per condition",
        "EXP_005",
    ):
        assert phrase in DOC_TEXT, phrase


def test_the_document_never_names_the_project():
    assert "phl" + "air" not in DOC_TEXT.lower()


# ---------------------------------------------------------------------------- mutation checks
# Each test changes a copy of the document text and checks that `problems` notices. They show the
# comparison can fail; they do not touch the document or any pipeline file.


def _mutated(old: str, new: str) -> str:
    assert DOC_TEXT.count(old) >= 1, f"{old!r} is not in the document"
    return DOC_TEXT.replace(old, new, 1)


def test_mutation_a_changed_parameter_value_is_noticed():
    text = _mutated("| `min_instants` | 300 |", "| `min_instants` | 301 |")
    assert any("min_instants" in p for p in problems(text))


def test_mutation_a_changed_seed_is_noticed():
    text = _mutated("20261124", "20261125")
    assert any("bootstrap_seed" in p for p in problems(text))


def test_mutation_a_changed_string_parameter_is_noticed():
    text = _mutated(
        "| `airflow_check_experiment` | EXP_004 |", "| `airflow_check_experiment` | EXP_005 |"
    )
    assert any("airflow_check_experiment" in p for p in problems(text))
    text = _mutated("2026-03-02T09:00:00Z |", "2026-03-02T10:00:00Z |")
    assert any("airflow_check_boundary" in p for p in problems(text))


def test_mutation_a_dropped_parameter_row_is_noticed():
    lines = DOC_TEXT.splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith("| `vif_limit` |")]
    assert len(kept) == len(lines) - 1
    assert any("vif_limit" in p for p in problems("".join(kept)))


def test_mutation_an_invented_parameter_row_is_noticed():
    text = _mutated(
        "| `lag_max_s` | 60 |",
        "| `invented_parameter` | 3 | Not in the code. |\n| `lag_max_s` | 60 |",
    )
    assert any("invented_parameter" in p for p in problems(text))


def test_mutation_a_changed_pivot_limit_is_noticed():
    text = _mutated("| `PIVOT_REL` | 1e-9 |", "| `PIVOT_REL` | 1e-8 |")
    assert any("PIVOT_REL" in p for p in problems(text))


def test_mutation_a_changed_kpi_unit_is_noticed():
    text = _mutated("| `mean_power_kw` | kW |", "| `mean_power_kw` | W |")
    assert any("KPI" in p for p in problems(text))


def test_mutation_a_dropped_kpi_is_noticed():
    text = _mutated("| `sec_kwh_per_kg` | kWh/kg |", "| `sec_kwh_per_kg_x` | kWh/kg |")
    assert any("KPI" in p for p in problems(text))


def test_mutation_a_renamed_or_dropped_factor_is_noticed():
    text = _mutated(
        "| `sorbent_batch` | The recorded batches are not equal. |",
        "| `sorbent_lot` | The recorded batches are not equal. |",
    )
    assert any("factors" in p for p in problems(text))
    lines = DOC_TEXT.splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.startswith("| `relative_humidity` | The medians")]
    assert len(kept) == len(lines) - 1
    assert any("factors" in p for p in problems("".join(kept)))


def test_mutation_a_changed_evidence_status_is_noticed():
    text = _mutated("| `single_run` |", "| `one_run` |")
    assert any("evidence statuses" in p for p in problems(text))


def test_mutation_a_changed_conditions_or_coverage_status_is_noticed():
    text = _mutated("| `confounded` |", "| `mixed` |")
    assert any("conditions statuses" in p for p in problems(text))
    text = _mutated("| `partial_coverage` |", "| `partial` |")
    assert any("coverage statuses" in p for p in problems(text))


def test_mutation_a_changed_model_predictor_or_unit_is_noticed():
    text = _mutated(
        "| `hydrolyzer` | current, electrolyte_temperature, flow, pressure |",
        "| `hydrolyzer` | current, electrolyte_temperature, flow, pressure_drop |",
    )
    assert any("MODELS" in p for p in problems(text))
    text = _mutated("| `pressure` | bar |", "| `pressure` | Pa |")
    assert any("PREDICTOR_UNITS" in p for p in problems(text))


def test_mutation_a_changed_version_or_fingerprint_is_noticed():
    text = DOC_TEXT.replace("`m5-v1`", "`m5-v2`")
    assert any("compare version" in p for p in problems(text))
    text = DOC_TEXT.replace(f"`{compare.COMPARE_FINGERPRINT[:8]}`", "`00000000`")
    assert any("fingerprint" in p for p in problems(text))
