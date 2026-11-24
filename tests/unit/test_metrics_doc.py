"""The metrics document matches the metrics code (M4, scenario S4.23).

`docs/metrics.md` is read by people; `pipeline/metrics.py` is what the numbers are made with. This
test reads the document's entries and its constants table and compares them with the code, so a
changed unit, a missing entry or a changed constant in either place fails it. The mutation tests
change a copy of the document text in memory and check that the comparison notices.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline import metrics

DOC = Path(__file__).resolve().parents[2] / "docs" / "metrics.md"
DOC_TEXT = DOC.read_text(encoding="utf-8")

ENTRY = re.compile(r"^#### `(?P<name>[a-z0-9_]+)`$", re.MULTILINE)
UNIT = re.compile(r"^- \*\*Unit:\*\* `(?P<unit>[^`]+)`", re.MULTILINE)
NAME_UNITS = {**metrics.METRIC_UNITS, **metrics.SERIES_UNITS}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def entries(text: str) -> dict[str, str | None]:
    """Entry name -> the unit its Unit line gives (None when it has none), in the text."""
    found: dict[str, str | None] = {}
    matches = list(ENTRY.finditer(text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        # An entry ends at the next section heading, so a later section's Unit line is not read.
        block = re.split(r"^#{1,3} ", block, maxsplit=1, flags=re.MULTILINE)[0]
        unit = UNIT.search(block)
        name = match.group("name")
        assert name not in found, f"{name} has two entries"
        found[name] = unit.group("unit") if unit else None
    return found


def constants_table(text: str) -> dict[str, str]:
    """Constant name -> the value cell, from the table headed `| Constant | Value |`."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _cells(line)[:2] == ["Constant", "Value"]:
            rows: dict[str, str] = {}
            for body in lines[i + 2 :]:  # skip the |---| separator
                if not body.startswith("|"):
                    break
                cells = _cells(body)
                name = cells[0].strip("`")
                assert name not in rows, f"{name} appears twice"
                rows[name] = cells[1]
            return rows
    raise AssertionError("no constants table in the document")


def plausibility_checks(text: str) -> list[str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _cells(line)[:2] == ["Check", "Passes when"]:
            names = []
            for body in lines[i + 2 :]:
                if not body.startswith("|"):
                    break
                names.append(_cells(body)[0].strip("`"))
            return names
    raise AssertionError("no plausibility table in the document")


def problems(text: str) -> list[str]:
    """Every way the document text differs from the code; empty when they agree."""
    found: list[str] = []

    shown = entries(text)
    for name in sorted(set(NAME_UNITS) - set(shown)):
        found.append(f"no entry for {name}")
    for name in sorted(set(shown) - set(NAME_UNITS)):
        found.append(f"entry for {name}, which is not a metric or a series")
    for name, unit in NAME_UNITS.items():
        if name in shown and shown[name] != unit:
            found.append(f"{name}: document says {shown[name]!r}, code says {unit!r}")

    table = constants_table(text)
    for name in sorted(set(metrics.POLICY) - set(table)):
        found.append(f"constant {name} is not in the table")
    for name in sorted(set(table) - set(metrics.POLICY)):
        found.append(f"constant {name} is in the table but not in POLICY")
    for name, value in metrics.POLICY.items():
        if name in table and float(table[name]) != float(value):
            found.append(f"{name}: document says {table[name]}, code says {value}")

    if sorted(plausibility_checks(text)) != sorted(metrics.PLAUSIBILITY_CHECKS):
        found.append("the plausibility checks differ from the code")

    if f"`{metrics.METRICS_VERSION}`" not in text:
        found.append("the document does not name the metrics version")
    if f"`{metrics.METRICS_FINGERPRINT[:8]}`" not in text:
        found.append("the document does not give the fingerprint prefix")
    if "median of the signed residual" not in text:
        found.append("the document does not say the residual median is signed")
    return found


# ---------------------------------------------------------------------------- the document


def test_s4_23_the_document_agrees_with_the_code():
    assert problems(DOC_TEXT) == []


def test_s4_23_names_do_not_overlap_so_one_unit_table_serves_both():
    assert not set(metrics.METRIC_UNITS) & set(metrics.SERIES_UNITS)
    assert len(metrics.METRIC_UNITS) == 13
    assert len(metrics.SERIES_UNITS) == 4


@pytest.mark.parametrize("name", sorted(NAME_UNITS))
def test_s4_23_each_name_has_one_entry_with_its_unit(name):
    shown = entries(DOC_TEXT)
    assert name in shown
    assert shown[name] == NAME_UNITS[name]


@pytest.mark.parametrize("name", sorted(metrics.POLICY))
def test_s4_23_each_constant_equals_the_code(name):
    table = constants_table(DOC_TEXT)
    assert float(table[name]) == float(metrics.POLICY[name])


def test_the_constants_table_has_exactly_the_policy_keys():
    assert set(constants_table(DOC_TEXT)) == set(metrics.POLICY)


def test_every_metric_entry_gives_its_formula_inputs_alignment_gap_and_label_rule():
    # Each metric and series entry carries the five bullets the document promises.
    for name in NAME_UNITS:
        start = re.search(rf"^#### `{name}`$", DOC_TEXT, flags=re.MULTILINE)
        assert start, name
        block = re.split(r"^#{1,3} ", DOC_TEXT[start.end() :], maxsplit=1, flags=re.MULTILINE)[0]
        block = re.split(r"^#### ", block, maxsplit=1, flags=re.MULTILINE)[0]
        assert "Details:" in block, f"{name} has no Details paragraph"
        for label in ("Unit", "Inputs", "Alignment", "Gap rule", "Label rule"):
            assert f"- **{label}:**" in block, f"{name} has no {label} line"


def test_the_residual_median_is_described_as_signed_and_the_others_as_absolute():
    assert "`residual_median_w` | The median of the SIGNED residual." in DOC_TEXT
    assert "`residual_p95_abs_w` | The 95th percentile of the ABSOLUTE residual" in DOC_TEXT
    assert "`residual_max_abs_w` | The largest ABSOLUTE residual." in DOC_TEXT


# ---------------------------------------------------------------------------- mutation checks
# Each test changes a copy of the document text and checks that `problems` notices. They show the
# comparison can fail; they do not touch the document or any pipeline file.


def _mutated(old: str, new: str) -> str:
    assert DOC_TEXT.count(old) >= 1, f"{old!r} is not in the document"
    return DOC_TEXT.replace(old, new, 1)


def test_mutation_a_changed_unit_is_noticed():
    text = _mutated("- **Unit:** `kWh`", "- **Unit:** `Wh`")
    assert any("energy_kwh" in p and "Wh" in p for p in problems(text))


def test_mutation_a_changed_series_unit_is_noticed():
    text = _mutated("- **Unit:** `kg/h`", "- **Unit:** `kg/s`")
    assert problems(text)


def test_mutation_a_changed_constant_is_noticed():
    text = _mutated("| `power_tol_w` | 10 |", "| `power_tol_w` | 11 |")
    assert any("power_tol_w" in p for p in problems(text))


def test_mutation_a_changed_gas_constant_digit_is_noticed():
    text = _mutated("8.314462618", "8.314462619")
    assert any("gas_constant_j_per_mol_k" in p for p in problems(text))


def test_mutation_a_dropped_constant_row_is_noticed():
    lines = DOC_TEXT.splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith("| `complete_coverage` |")]
    assert len(kept) == len(lines) - 1
    assert any("complete_coverage" in p for p in problems("".join(kept)))


def test_mutation_a_dropped_metric_entry_is_noticed():
    text = _mutated("#### `mean_power_kw`", "#### `mean_power_kw_removed`")
    found = problems(text)
    assert any("no entry for mean_power_kw" in p for p in found)
    assert any("mean_power_kw_removed" in p for p in found)


def test_mutation_a_dropped_series_entry_is_noticed():
    text = _mutated("#### `capture_rate`", "#### `capture_rate_x`")
    assert any("no entry for capture_rate" in p for p in problems(text))


def test_mutation_a_new_constant_row_is_noticed():
    text = _mutated(
        "| `energy_agreement_rel` | 0.01 |",
        "| `energy_agreement_rel` | 0.01 |\n| `invented_constant` | 3 | Not in the code. |\n"
        "| `energy_agreement_rel_copy` | 0.01 |",
    )
    assert any("invented_constant" in p for p in problems(text))


def test_mutation_a_changed_version_is_noticed():
    text = DOC_TEXT.replace("`m4-v1`", "`m4-v2`")
    assert any("metrics version" in p for p in problems(text))


def test_mutation_a_changed_fingerprint_prefix_is_noticed():
    text = DOC_TEXT.replace(f"`{metrics.METRICS_FINGERPRINT[:8]}`", "`00000000`")
    assert any("fingerprint" in p for p in problems(text))


def test_mutation_a_renamed_plausibility_check_is_noticed():
    text = _mutated("| `sec_above_floor` |", "| `sec_below_floor` |")
    assert any("plausibility" in p for p in problems(text))


def test_mutation_an_unsigned_median_is_noticed():
    text = DOC_TEXT.replace("median of the signed residual", "median of the residual")
    assert any("signed" in p for p in problems(text))
