"""The draft findings match the committed comparison summary (M5, scenarios S5.24 and S5.25).

`reports/findings.md` is read by people. Every number in it is followed by a hidden reference
comment, `<!-- ref: <path> -->`, that points into `reports/comparison_summary.json`:

- `/` separates keys; a key is a plain dictionary key (`parameters/vif_limit`) or, for a list, a
  selector `key=value[,key=value]` that must match exactly one item
  (`voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient`).
- The number written just before the comment must equal the referenced value rounded to the digits
  written. The rule, in one place (`check_ref`): a number written with `d` decimals equals the
  value rounded half away from zero to `d` decimals; a number written in scientific notation with
  `m` mantissa decimals (`1.39e-05`) equals `format(value, '.{m}e')`; a number followed by ` %`
  equals the value times 100, rounded the same way; a word in backticks equals the referenced
  string.
- A decimal number with no reference is a failure, except inside code blocks and inside the closing
  "Limits and sources" section, which says where its own numbers come from.

The mutation tests change a copy of the text in memory and check that the checks notice.
"""

from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FINDINGS = ROOT / "reports" / "findings.md"
SUMMARY_FILE = ROOT / "reports" / "comparison_summary.json"
TEXT = FINDINGS.read_text(encoding="utf-8")
SUMMARY = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))

STATUS_LINE = "Status: draft, awaiting Sebastian's approval"
MIN_FINDINGS = 3

# A written number (or a backticked word), one space, then its reference comment.
REF = re.compile(
    r"(?:(?<![\w.])(?P<num>-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)(?P<pct> %)?|`(?P<word>[^`\n]+)`)"
    r" <!-- ref: (?P<path>[^>]+?) -->"
)
ANY_REF = re.compile(r"<!-- ref: (?P<path>[^>]+?) -->")
FINDING_HEAD = re.compile(r"^### Finding (?P<n>\d+): (?P<title>.+)$", re.MULTILINE)
HEADING = re.compile(r"^#{1,3} ", re.MULTILINE)
CAUSAL = re.compile(r"\b(caus\w*|due to|leads? to|drives?|because)\b", re.IGNORECASE)
LIMITS_HEADING = "## Limits and sources"


# ---------------------------------------------------------------------------- the reference rule


def resolve(path: str, summary: dict = SUMMARY):
    """Follow a reference path into the summary; raise `LookupError` when it does not resolve."""
    node = summary
    for segment in path.split("/"):
        if "=" in segment:
            if not isinstance(node, list):
                raise LookupError(f"{segment!r} selects from a list, but the node is not one")
            wanted = dict(part.split("=", 1) for part in segment.split(","))
            hits = [
                item
                for item in node
                if isinstance(item, dict) and all(str(item.get(k)) == v for k, v in wanted.items())
            ]
            if len(hits) != 1:
                raise LookupError(f"{segment!r} matches {len(hits)} items, not exactly one")
            node = hits[0]
        else:
            if not isinstance(node, dict) or segment not in node:
                raise LookupError(f"no key {segment!r}")
            node = node[segment]
    return node


def check_ref(
    num: str | None, pct: str | None, word: str | None, path: str, summary: dict = SUMMARY
) -> str | None:
    """None when the written token equals the referenced value, else a short problem text."""
    try:
        value = resolve(path, summary)
    except LookupError as error:
        return f"{path}: {error}"
    if word is not None:
        return None if str(value) == word else f"{path}: written {word!r}, summary says {value!r}"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return f"{path}: value {value!r} is not a number"
    if "e" in num:
        mantissa_decimals = len(num.split("e")[0].partition(".")[2])
        expected = Decimal(f"{value:.{mantissa_decimals}e}")
    else:
        decimals = len(num.partition(".")[2])
        exact = Decimal(repr(float(value)))
        if pct:
            exact *= 100
        expected = exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        if expected == 0:
            expected = abs(expected)  # "-0.00" and "0.00" are the same number
    if Decimal(num) != expected:
        return f"{path}: written {num}, rounded value is {expected}"
    return None


def reference_problems(text: str) -> list[str]:
    """Every reference that does not resolve or does not match its written number."""
    found = []
    for match in REF.finditer(text):
        problem = check_ref(match["num"], match["pct"], match["word"], match["path"])
        if problem:
            found.append(problem)
    # A comment that no number or word precedes is a reference to nothing.
    if len(list(ANY_REF.finditer(text))) != len(list(REF.finditer(text))):
        found.append("a reference comment has no number or backticked word right before it")
    return found


def _outside_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def uncited_decimals(text: str) -> list[str]:
    """Decimal numbers outside code blocks and the closing section that carry no reference."""
    body = text.split(LIMITS_HEADING)[0]
    body = REF.sub("", _outside_code(body))
    body = ANY_REF.sub("", body)
    return re.findall(r"(?<![\w.])-?\d+\.\d+(?:e[-+]?\d+)?", body)


# ---------------------------------------------------------------------------- the structure


def findings(text: str) -> list[tuple[int, str, str]]:
    """`(number, title, block)` of each `### Finding N:` block, up to the next heading."""
    heads = list(FINDING_HEAD.finditer(text))
    blocks = []
    for head in heads:
        rest = text[head.end() :]
        nxt = HEADING.search(rest)
        blocks.append((int(head["n"]), head["title"], rest[: nxt.start()] if nxt else rest))
    return blocks


def section(text: str, heading: str) -> str:
    """The text under a `## heading`, up to the next `## ` heading."""
    start = text.find(f"\n{heading}\n")
    if start < 0:
        return ""
    rest = text[start + len(heading) + 2 :]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def structure_problems(text: str) -> list[str]:
    found = []
    if STATUS_LINE not in text.splitlines()[:6]:
        found.append("the status line is missing or not in the first lines")
    blocks = findings(text)
    if len(blocks) < MIN_FINDINGS:
        found.append(f"{len(blocks)} findings, at least {MIN_FINDINGS} are needed")
    for number, _title, block in blocks:
        label = f"finding {number}"
        claims = [ln for ln in block.splitlines() if ln.startswith("Claim:")]
        if len(claims) != 1:
            found.append(f"{label}: needs exactly one Claim line")
        else:
            if "in this run" not in claims[0].lower():
                found.append(f"{label}: the claim is not worded 'in this run'")
            if CAUSAL.search(claims[0]):
                found.append(f"{label}: the claim uses causal wording")
        commands = [ln for ln in block.splitlines() if ln.startswith("Command:")]
        if not commands or "python -m scripts.compare" not in commands[0]:
            found.append(f"{label}: needs a Command line with python -m scripts.compare")
        if not re.search(r"```sql\n.*?SELECT .*?```", block, flags=re.DOTALL):
            found.append(f"{label}: needs an SQL block with a SELECT")
        if not ANY_REF.search(block):
            found.append(f"{label}: has no reference comment")
        if "Details:" not in block:
            found.append(f"{label}: has no Details paragraph")
    flow = section(text, "## Flow and pressure against cell voltage")
    if not flow:
        found.append("the flow and pressure section is missing")
    else:
        hydro, absorber = flow.find("Hydrolyzer model"), flow.find("Absorber model")
        if hydro < 0 or absorber < 0:
            found.append("the flow section needs a hydrolyzer and an absorber finding")
        elif hydro > absorber:
            found.append("the hydrolyzer model must come before the absorber model")
    unsupported = section(text, "## Comparisons the data does not support")
    if not unsupported:
        found.append("the section on comparisons the data does not support is missing")
    else:
        if "Reason" not in unsupported or "Why the data does not support it" not in unsupported:
            found.append("the unsupported section does not give reasons")
        confounded = {
            (p["a"], p["b"]): ", ".join(p["differing"])
            for p in SUMMARY["comparisons"]
            if p["conditions_status"] == "confounded"
        }
        rows = dict(re.findall(r"^\| (EXP_\d+ vs EXP_\d+) \| ([^|]+) \|$", unsupported, flags=re.M))
        listed = {tuple(k.split(" vs ")): v.strip() for k, v in rows.items()}
        if listed != confounded:
            found.append("the confounded pairs listed differ from the summary")
    return found


def all_problems(text: str) -> list[str]:
    return (
        structure_problems(text)
        + reference_problems(text)
        + [f"uncited decimal {d}" for d in uncited_decimals(text)]
    )


# ---------------------------------------------------------------------------- the document


def test_s5_24_the_findings_document_passes_every_check():
    assert all_problems(TEXT) == []


def test_s5_24_the_status_line_reads_exactly_draft_awaiting_approval():
    assert STATUS_LINE in TEXT.splitlines()[:6]


def test_s5_24_at_least_three_findings_each_with_claim_command_sql_and_numbers():
    blocks = findings(TEXT)
    assert len(blocks) >= MIN_FINDINGS
    assert [n for n, _, _ in blocks] == list(range(1, len(blocks) + 1))
    for number, _title, block in blocks:
        assert any(ln.startswith("Claim:") for ln in block.splitlines()), number
        assert "Command: `python -m scripts.compare" in block, number
        assert "```sql" in block and "SELECT" in block, number
        assert len(ANY_REF.findall(block)) >= 1, number


def test_s5_24_the_flow_and_pressure_section_puts_the_hydrolyzer_model_first():
    flow = section(TEXT, "## Flow and pressure against cell voltage")
    assert 0 <= flow.find("Hydrolyzer model") < flow.find("Absorber model")


def test_s5_24_the_unsupported_section_names_every_confounded_pair_with_its_factors():
    unsupported = section(TEXT, "## Comparisons the data does not support")
    pairs = [p for p in SUMMARY["comparisons"] if p["conditions_status"] == "confounded"]
    assert len(pairs) == 14
    for pair in pairs:
        assert f"| {pair['a']} vs {pair['b']} | {', '.join(pair['differing'])} |" in unsupported
    assert "| EXP_001 vs EXP_002 |" not in unsupported


def test_s5_24_the_claims_in_the_text_hold_in_the_summary():
    # Statements the text makes in words, checked against the summary they rest on.
    assert all(row["status"] == "not_resolved" for row in SUMMARY["voltage_evidence"])
    assert len(SUMMARY["voltage_evidence"]) == 8
    assert "All eight evidence rows" in TEXT
    assert all(fit["testable"] for fit in SUMMARY["voltage_models"])
    assert len(SUMMARY["voltage_models"]) == 28
    assert "all 28 fits were testable" in TEXT
    supported = [p for p in SUMMARY["comparisons"] if p["conditions_status"] == "supported"]
    assert [(p["a"], p["b"]) for p in supported] == [("EXP_001", "EXP_002")]
    assert len(SUMMARY["comparisons"]) == 15
    assert all(
        k["coverage_status"] != "not_available" for p in SUMMARY["comparisons"] for k in p["kpis"]
    )
    hydro_steady = [
        m
        for m in SUMMARY["voltage_models"]
        if m["model"] == "hydrolyzer" and m["window"] == "steady"
    ]
    per_experiment = [m for m in hydro_steady if m["scope"] != "pooled"]
    for m in per_experiment:
        for t in m["terms"]:
            if t["name"] in ("flow", "pressure"):
                assert t["interval_low"] < 0 < t["interval_high"], (m["scope"], t["name"])
    # "the largest of the six" joint R squared drop, cited for EXP_001 in Finding 1
    drops = {m["scope"]: m["joint"]["r2_drop"] for m in per_experiment}
    assert max(drops, key=drops.get) == "EXP_001"
    # the whole-run hydrolyzer fits are all not separable
    whole = [
        m
        for m in SUMMARY["voltage_models"]
        if m["model"] == "hydrolyzer" and m["window"] == "whole_run"
    ]
    assert whole and not any(m["joint"]["separable"] for m in whole)
    # "the largest in size" correlation at the best lag, cited for EXP_004 in Finding 4
    corr = {
        e["experiment_id"]: abs(e["corr_at_best_lag"])
        for e in SUMMARY["pressure_drop_check"]["per_experiment"]
    }
    assert max(corr, key=corr.get) == "EXP_004"
    r2 = {
        e["experiment_id"]: e["r2_air_flow"]
        for e in SUMMARY["pressure_drop_check"]["per_experiment"]
    }
    assert max(r2, key=r2.get) == "EXP_003"


def test_the_words_never_name_the_project():
    assert "phl" + "air" not in TEXT.lower()


# ---------------------------------------------------------------------------- the reference rule


@pytest.mark.parametrize(
    ("written", "pct", "word", "path", "ok"),
    [
        (
            "-0.0068",
            None,
            None,
            "voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient",
            True,
        ),
        (
            "-0.0069",
            None,
            None,
            "voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient",
            False,
        ),
        (
            "-0.007",
            None,
            None,
            "voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient",
            True,
        ),
        (
            "-0.00677218078",
            None,
            None,
            "voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient",
            True,
        ),
        ("-98.3", " %", None, "airflow_check/signals/signal=air_flow/relative_change", True),
        ("-98.4", " %", None, "airflow_check/signals/signal=air_flow/relative_change", False),
        ("-0.983", None, None, "airflow_check/signals/signal=air_flow/relative_change", True),
        (
            "1.39e-05",
            None,
            None,
            "voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/joint/r2_drop",
            True,
        ),
        (
            "1.40e-05",
            None,
            None,
            "voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/joint/r2_drop",
            False,
        ),
        ("10", None, None, "parameters/vif_limit", True),
        ("11", None, None, "parameters/vif_limit", False),
        (
            None,
            None,
            "not_resolved",
            "voltage_evidence/model=hydrolyzer,window=steady,term=flow/status",
            True,
        ),
        (
            None,
            None,
            "supported",
            "voltage_evidence/model=hydrolyzer,window=steady,term=flow/status",
            False,
        ),
    ],
)
def test_s5_25_the_rounding_rule(written, pct, word, path, ok):
    assert (check_ref(written, pct, word, path) is None) is ok


def test_s5_25_a_tie_rounds_away_from_zero_and_a_negative_zero_is_zero():
    fake = {"a": 0.125, "b": -0.004, "c": 2.5, "d": -2.5}
    assert check_ref("0.13", None, None, "a", fake) is None
    assert check_ref("0.12", None, None, "a", fake) is not None
    assert check_ref("3", None, None, "c", fake) is None
    assert check_ref("-3", None, None, "d", fake) is None
    assert check_ref("0.00", None, None, "b", fake) is None
    assert check_ref("-0.00", None, None, "b", fake) is None
    assert check_ref("-0.01", None, None, "b", fake) is not None


@pytest.mark.parametrize(
    "path",
    [
        "no_such_key/x",
        "voltage_models/model=hydrolyzer/terms/name=flow/coefficient",  # matches many items
        "voltage_models/model=nothing,window=steady,scope=pooled/instants",  # matches none
        "parameters/vif_limit/extra",
        "airflow_check/signals/signal=air_flow",  # a dict, not a number
    ],
)
def test_s5_25_a_path_that_does_not_resolve_is_a_problem(path):
    assert check_ref("1", None, None, path) is not None


# ---------------------------------------------------------------------------- mutation checks
# Each test changes a copy of the findings text and checks that the checks notice.


def _mutated(old: str, new: str, count: int = 1) -> str:
    assert TEXT.count(old) >= 1, f"{old!r} is not in the findings"
    return TEXT.replace(old, new, count)


def test_mutation_a_changed_written_number_is_noticed():
    assert any(
        "written -0.0069" in p
        for p in reference_problems(_mutated("-0.0068 <!-- ref", "-0.0069 <!-- ref"))
    )


def test_mutation_a_number_written_with_more_digits_but_wrong_is_noticed():
    problems = reference_problems(_mutated("1200.1 <!-- ref", "1200.2 <!-- ref"))
    assert any("written 1200.2" in p for p in problems)


def test_mutation_a_changed_percentage_is_noticed():
    assert reference_problems(_mutated("-98.3 % <!-- ref", "-98.2 % <!-- ref"))


def test_mutation_a_changed_ref_path_is_noticed():
    text = _mutated(
        "scope=pooled/terms/name=flow/coefficient",
        "scope=EXP_001/terms/name=flow/coefficient",
    )
    assert reference_problems(text)


def test_mutation_a_ref_path_that_does_not_exist_is_noticed():
    text = _mutated(
        "airflow_check/signals/signal=fan_speed/before_median",
        "airflow_check/signals/signal=fan_speed/before_mean",
    )
    assert any("no key" in p for p in reference_problems(text))


def test_mutation_a_changed_word_is_noticed():
    text = _mutated("`partial_coverage` <!-- ref", "`both_complete` <!-- ref")
    assert any("partial_coverage" in p for p in reference_problems(text))


def test_mutation_a_ref_comment_with_nothing_before_it_is_noticed():
    text = _mutated(
        "10 <!-- ref: parameters/vif_limit -->", "ten <!-- ref: parameters/vif_limit -->"
    )
    assert any("no number" in p for p in reference_problems(text))


def test_mutation_a_number_without_a_reference_is_noticed():
    path = "voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient"
    text = _mutated(f"-0.0068 <!-- ref: {path} -->", "-0.0068")
    assert "-0.0068" in uncited_decimals(text)
    assert all_problems(text)


def test_mutation_a_finding_without_any_reference_fails():
    text = TEXT
    start = text.index("### Finding 4")
    end = text.index("### Finding 5")
    problems = structure_problems(text[:start] + ANY_REF.sub("", text[start:end]) + text[end:])
    assert any("finding 4: has no reference comment" in p for p in problems)


def test_mutation_a_changed_status_line_is_noticed():
    text = _mutated(STATUS_LINE, "Status: approved")
    assert any("status line" in p for p in structure_problems(text))


def test_mutation_fewer_than_three_findings_is_noticed():
    text = (
        TEXT[: TEXT.index("### Finding 3")]
        + TEXT[TEXT.index("## Comparisons the data does not support") :]
    )
    assert any("at least 3" in p for p in structure_problems(text))


def test_mutation_a_finding_without_a_command_or_sql_is_noticed():
    text = _mutated("Command: `python -m scripts.compare --report-dir reports`", "Command: none", 1)
    assert any("Command line" in p for p in structure_problems(text))
    text = _mutated("```sql", "```text", 1)
    assert any("SQL block" in p for p in structure_problems(text))


def test_mutation_a_claim_not_worded_in_this_run_or_causal_is_noticed():
    text = _mutated("Claim: In this run, the hydrolyzer data", "Claim: The hydrolyzer data")
    assert any("in this run" in p for p in structure_problems(text))
    text = _mutated(
        "Claim: In this run, the hydrolyzer data",
        "Claim: In this run, flow causes the hydrolyzer data",
    )
    assert any("causal" in p for p in structure_problems(text))


def test_mutation_the_absorber_before_the_hydrolyzer_is_noticed():
    text = TEXT.replace("Hydrolyzer model", "Xx model", 1).replace(
        "Absorber model", "Hydrolyzer model", 1
    )
    text = text.replace("Xx model", "Absorber model", 1)
    # the first Hydrolyzer heading is now where the Absorber one was, and vice versa
    assert any("must come before" in p for p in structure_problems(text))


def test_mutation_a_missing_unsupported_pair_or_changed_factor_is_noticed():
    row = "| EXP_001 vs EXP_003 | air_flow, sorbent_batch |"
    text = _mutated(row, "")
    assert any("confounded pairs" in p for p in structure_problems(text))
    text = _mutated(row, "| EXP_001 vs EXP_003 | air_flow |")
    assert any("confounded pairs" in p for p in structure_problems(text))


def test_mutation_a_removed_unsupported_section_is_noticed():
    text = TEXT.replace("## Comparisons the data does not support", "## Something else")
    assert any("not support" in p for p in structure_problems(text))
