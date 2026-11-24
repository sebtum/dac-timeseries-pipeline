"""The policy document matches the policy table (M3, scenario S3.34).

`docs/cleaning_policy.md` is read by people; `pipeline/cleaning_policy.py` is what the rules run
on. This test parses the document's table and compares it, row by row, with the declared table,
so the two cannot drift: one changed number in either fails it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import cleaning_policy as policy
from pipeline.signals import DOCUMENTED_RANGE, NOMINAL_INTERVAL_S, TABLE_FOR

DOC = Path(__file__).resolve().parents[2] / "docs" / "cleaning_policy.md"

COLUMNS = [
    "Source",
    "Signal",
    "Class",
    "Nominal s",
    "Limit low",
    "Limit high",
    "Typical low",
    "Typical high",
    "Step",
    "Spike",
    "Flatline",
    "Exact repeat",
    "Half-window",
    "Gaps",
    "Allowed values",
]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_after(header_first_cells: list[str]) -> list[list[str]]:
    """The body rows of the first Markdown table whose header starts with these cells."""
    lines = DOC.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _cells(line)[: len(header_first_cells)] == header_first_cells:
            rows = []
            for body in lines[i + 2 :]:  # skip the |---| separator
                if not body.startswith("|"):
                    break
                rows.append(_cells(body))
            return rows
    raise AssertionError(f"no table starting with {header_first_cells} in {DOC.name}")


def _number(cell: str) -> float | None:
    return None if cell == "-" else float(cell)


def _yes_no(cell: str) -> bool:
    assert cell in {"yes", "no"}, f"expected yes or no, got {cell!r}"
    return cell == "yes"


@pytest.fixture(scope="module")
def doc_rows() -> dict[tuple[str, str], list[str]]:
    header = next(
        _cells(line)
        for line in DOC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| Source |")
    )
    assert header == COLUMNS
    rows = _table_after(COLUMNS[:2])
    parsed: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        assert len(row) == len(COLUMNS), row
        key = (row[0], row[1])
        assert key not in parsed, f"{key} appears twice"
        parsed[key] = row
    return parsed


def test_s3_34_the_document_has_one_row_per_signal_pair_25_in_all(doc_rows):
    assert len(doc_rows) == 25
    assert set(doc_rows) == set(TABLE_FOR)
    classes = [row[2] for row in doc_rows.values()]
    assert classes.count("state") == 2
    assert classes.count("state") + classes.count("measured") + classes.count("commanded") == 25


@pytest.mark.parametrize("pair", sorted(policy.POLICY))
def test_s3_34_each_row_equals_the_declared_policy(doc_rows, pair):
    row = dict(zip(COLUMNS, doc_rows[pair], strict=True))
    declared = policy.POLICY[pair]

    assert row["Class"] == declared.kind
    assert _yes_no(row["Spike"]) is declared.spike
    assert _yes_no(row["Flatline"]) is declared.flatline
    assert _yes_no(row["Exact repeat"]) is declared.exact_repeat

    if declared.kind == policy.STATE:
        assert [_number(row[c]) for c in ("Limit low", "Limit high", "Step")] == [None] * 3
        assert row["Nominal s"] == "-"
        assert _yes_no(row["Gaps"]) is False
        assert tuple(v.strip() for v in row["Allowed values"].split(",")) == declared.states
        return

    # Physical limits, step size and nominal interval, as numbers.
    low, high = declared.limits
    assert _number(row["Limit low"]) == low
    assert _number(row["Limit high"]) == high
    assert _number(row["Step"]) == declared.step
    assert _number(row["Nominal s"]) == NOMINAL_INTERVAL_S[pair]
    assert (_number(row["Typical low"]), _number(row["Typical high"])) == DOCUMENTED_RANGE[pair][:2]

    # Which rules apply: gaps for every polled signal, a half-window only where flatline applies.
    assert _yes_no(row["Gaps"]) is True
    assert row["Allowed values"] == "-"
    if declared.flatline:
        assert _number(row["Half-window"]) == declared.flat_half_window
    else:
        assert row["Half-window"] == "-"


def test_the_document_names_the_policy_version_the_code_runs():
    assert f"`{policy.POLICY_VERSION}`" in DOC.read_text(encoding="utf-8")


def test_the_constants_table_equals_the_declared_constants(doc_rows):  # noqa: ARG001
    rows = _table_after(["Constant", "Value"])
    shown = {row[0]: float(row[1]) for row in rows}
    assert shown == {k: float(v) for k, v in policy.policy_table()["constants"].items()}


def test_the_reason_table_lists_every_reason_in_priority_order():
    rows = _table_after(["Order", "Reason"])
    listed = [row[1].strip("`") for row in rows if row[0] != "note"]
    assert tuple(listed) == policy.REASON_CODES
    assert [row[1].strip("`") for row in rows if row[0] == "note"] == [policy.NOTE_OUTSIDE_TYPICAL]
