"""The dashboard document matches the dashboards (M6, scenario S6.26).

`docs/dashboard.md` is read by people; `grafana/dashboards/*.json` is what Grafana loads. This test
reads every dashboard file and compares the document's tables with it: the dashboard uids and
files, every variable with its type, visibility, selection and default, every panel with its id,
title, type and data source, the annotation, and the colour conventions (status words, fraction
steps, series colours). It also checks the committed counts of the dashboard check against
`reports/dashboard_check.json`, and the read-only provisioning the document claims.

The files are read in plain loops, not through `parametrize`: a parametrized test over a missing
directory is collected as a skip, and a skip would hide that nothing was compared. An empty or
absent directory fails here instead (`test_the_dashboard_files_are_present`).

The mutation tests change a copy of the document text in memory and check that the comparison
notices. They do not touch the document or any dashboard file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from pipeline import metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "dashboard.md"
DOC_TEXT = DOC.read_text(encoding="utf-8")
DASHBOARD_DIR = REPO_ROOT / "grafana" / "dashboards"
PROVIDER = REPO_ROOT / "grafana" / "provisioning" / "dashboards" / "dashboards.yaml"
CHECK_REPORT = REPO_ROOT / "reports" / "dashboard_check.json"

# The words the document uses for colours. Grafana's `orange` and the hex `#EAB839` are the same
# warning colour (the document says so); a colour not listed here fails the test, so a new colour
# in a dashboard has to be named in the document.
COLOUR_WORDS = {
    "green": "green",
    "orange": "amber",
    "#EAB839": "amber",
    "red": "red",
    "#9AA0A6": "grey",
    "blue": "blue",
}
SOURCES = {"${pg}": "Postgres", "${influx}": "InfluxDB"}
ANY_COLUMN = "(any column)"
MINUS = "−"


# ---------------------------------------------------------------------------- reading the files


def dashboard_files() -> list[Path]:
    return sorted(DASHBOARD_DIR.glob("*.json")) if DASHBOARD_DIR.is_dir() else []


def load_dashboards() -> dict[str, dict]:
    """Every dashboard file, keyed by uid; plain loop, so an empty directory is an empty dict."""
    found: dict[str, dict] = {}
    for path in dashboard_files():
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["_file"] = path.relative_to(REPO_ROOT).as_posix()
        assert doc["uid"] not in found, f"uid {doc['uid']} appears in two files"
        found[doc["uid"]] = doc
    return found


def panels_of(doc: dict) -> list[dict]:
    """Every panel, rows included, in id order."""
    found: list[dict] = []

    def walk(items: list[dict]) -> None:
        for panel in items:
            found.append(panel)
            walk(panel.get("panels", []))

    walk(doc["panels"])
    return sorted(found, key=lambda p: p["id"])


def colour(value: str) -> str:
    assert value in COLOUR_WORDS, f"colour {value!r} has no word in the document's vocabulary"
    return COLOUR_WORDS[value]


# ---------------------------------------------------------------------------- reading the document


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table(text: str, header: list[str]) -> list[list[str]]:
    """Body rows of the first table whose header row starts with these cells."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _cells(line)[: len(header)] == header:
            rows = []
            for body in lines[i + 2 :]:  # skip the |---| rule
                if not body.startswith("|"):
                    break
                rows.append([c.strip("`") for c in _cells(body)])
            return rows
    raise AssertionError(f"no table headed {header} in the text")


def section(text: str, uid: str) -> str:
    """The `## ` section whose heading names this uid, up to the next `## ` heading."""
    match = re.search(rf"^## [^\n]*`{re.escape(uid)}`[^\n]*\n", text, flags=re.MULTILINE)
    assert match, f"no section for {uid}"
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: end.start()] if end else rest


# ---------------------------------------------------------------------------- expected rows


def expected_variables(doc: dict) -> list[list[str]]:
    rows = []
    for var in doc["templating"]["list"]:
        shown = "no" if var.get("hide") == 2 else "yes"
        if var.get("multi") and var.get("includeAll"):
            selection = "multi-value with All"
        elif var.get("multi"):
            selection = "multi-value"
        elif var["type"] in ("query", "custom") and shown == "yes":
            selection = "single"
        else:
            selection = "-"
        current = var.get("current") or {}
        text = current.get("text")
        default = ", ".join(text) if isinstance(text, list) else (text or "computed")
        rows.append([var["name"], var["type"], shown, selection, default])
    return rows


def expected_panels(doc: dict) -> list[list[str]]:
    return [
        [str(p["id"]), p["title"], p["type"], SOURCES[p["datasource"]["uid"]]]
        for p in panels_of(doc)
    ]


def expected_annotations(doc: dict) -> list[list[str]]:
    return [
        [a["name"], ", ".join(str(i) for i in a["filter"]["ids"]), colour(a["iconColor"])]
        for a in doc.get("annotations", {}).get("list", [])
        if a.get("name") != "Annotations & Alerts"
    ]


def override_property(override: dict, prop_id: str):
    for prop in override["properties"]:
        if prop["id"] == prop_id:
            return prop["value"]
    return None


def mapping_rows(doc: dict) -> dict[tuple[str, str, str], str]:
    """(panel title, column, value) -> colour word, from every value mapping that sets a colour."""
    rows: dict[tuple[str, str, str], str] = {}
    for panel in panels_of(doc):
        sources = [(ANY_COLUMN, panel.get("fieldConfig", {}).get("defaults", {}).get("mappings"))]
        for override in panel.get("fieldConfig", {}).get("overrides", []):
            sources.append(
                (override["matcher"]["options"], override_property(override, "mappings"))
            )
        for column, mappings in sources:
            for mapping in mappings or []:
                for value, entry in mapping["options"].items():
                    key = (panel["title"], column, value)
                    assert key not in rows, f"{key} is mapped twice"
                    rows[key] = colour(entry["color"])
    return rows


def step_text(steps: list[dict]) -> str:
    parts = [colour(steps[0]["color"])]
    parts += [f"{colour(s['color'])} from {s['value']:g}" for s in steps[1:]]
    return "; ".join(parts)


def threshold_rows(doc: dict) -> dict[tuple[str, str], str]:
    """(panel title, column) -> colour steps, from every column override that sets thresholds."""
    rows: dict[tuple[str, str], str] = {}
    for panel in panels_of(doc):
        for override in panel.get("fieldConfig", {}).get("overrides", []):
            thresholds = override_property(override, "thresholds")
            if thresholds is not None:
                rows[(panel["title"], override["matcher"]["options"])] = step_text(
                    thresholds["steps"]
                )
    return rows


def series_rows(doc: dict) -> dict[tuple[str, str], tuple[str, str]]:
    """(series name, panel title) -> (colour word, drawn as), from fixed-colour series overrides."""
    rows: dict[tuple[str, str], tuple[str, str]] = {}
    for panel in panels_of(doc):
        defaults = panel.get("fieldConfig", {}).get("defaults", {})
        for override in panel.get("fieldConfig", {}).get("overrides", []):
            value = override_property(override, "color")
            if value is None or value.get("mode") != "fixed" or "fixedColor" not in value:
                continue
            drawn = override_property(override, "custom.drawStyle") or defaults.get(
                "custom", {}
            ).get("drawStyle", "line")
            rows[(override["matcher"]["options"], panel["title"])] = (
                colour(value["fixedColor"]),
                drawn,
            )
    return rows


# ---------------------------------------------------------------------------- the comparison


def problems(text: str, dashboards: dict[str, dict] | None = None) -> list[str]:
    """Every way the document text differs from the dashboards; empty when they agree."""
    dashboards = load_dashboards() if dashboards is None else dashboards
    found: list[str] = []
    if not dashboards:
        return ["no dashboard files were found"]

    listed = {row[1]: row for row in table(text, ["Dashboard", "uid", "File", "Folder"])}
    folder = yaml.safe_load(PROVIDER.read_text(encoding="utf-8"))["providers"][0]["folder"]
    if set(listed) != set(dashboards):
        found.append(
            f"the dashboard table lists {sorted(listed)}, the files are {sorted(dashboards)}"
        )

    for uid, doc in dashboards.items():
        if uid not in listed:
            continue
        row = listed[uid]
        if row[0] != doc["title"] or row[2] != doc["_file"] or row[3] != folder:
            found.append(f"{uid}: title, file or folder differ from the dashboard table row")
        try:
            body = section(text, uid)
        except AssertionError:
            found.append(f"{uid}: the document has no section for it")
            continue

        for label, header, expected in (
            (
                "variables",
                ["Variable", "Type", "Shown", "Selection", "Default"],
                expected_variables,
            ),
            ("panels", ["Id", "Title", "Type", "Source"], expected_panels),
        ):
            try:
                rows = [r[: len(header)] for r in table(body, header)]
            except AssertionError:
                found.append(f"{uid}: no {label} table")
                continue
            want = expected(doc)
            for item in want:
                if item not in rows:
                    found.append(f"{uid}: {label} row {item} is missing or differs in the document")
            for item in rows:
                if item not in want:
                    found.append(f"{uid}: {label} row {item} is in the document, not the dashboard")
            if len(rows) != len(want):
                found.append(f"{uid}: {label} count is {len(rows)}, the dashboard has {len(want)}")

        want_annotations = expected_annotations(doc)
        if want_annotations:
            try:
                rows = table(body, ["Annotation", "Panels", "Colour"])
            except AssertionError:
                found.append(f"{uid}: no annotation table")
            else:
                if [r[:3] for r in rows] != want_annotations:
                    found.append(f"{uid}: annotation rows differ from the dashboard")

    found += convention_problems(text, dashboards)
    found += claim_problems(text)
    return found


def convention_problems(text: str, dashboards: dict[str, dict]) -> list[str]:
    found: list[str] = []
    want_status: dict[tuple[str, str, str], str] = {}
    want_steps: dict[tuple[str, str], str] = {}
    want_series: dict[tuple[str, str], tuple[str, str]] = {}
    for doc in dashboards.values():
        want_status.update(mapping_rows(doc))
        want_steps.update(threshold_rows(doc))
        want_series.update(series_rows(doc))

    got_status = {
        (r[0], r[1], r[2]): r[3] for r in table(text, ["Panel", "Column", "Value", "Colour"])
    }
    if got_status != want_status:
        for key in sorted(set(got_status) ^ set(want_status)):
            found.append(f"status colour row {key} is on one side only")
        for key in sorted(set(got_status) & set(want_status)):
            if got_status[key] != want_status[key]:
                found.append(
                    f"status colour {key}: document {got_status[key]}, dashboard {want_status[key]}"
                )

    got_steps = {(r[0], r[1]): r[2] for r in table(text, ["Panel", "Column", "Colour steps"])}
    if got_steps != want_steps:
        for key in sorted(set(got_steps) ^ set(want_steps)):
            found.append(f"colour steps row {key} is on one side only")
        for key in sorted(set(got_steps) & set(want_steps)):
            if got_steps[key] != want_steps[key]:
                found.append(
                    f"colour steps {key}: document {got_steps[key]}, dashboard {want_steps[key]}"
                )

    got_series = {
        (r[0], r[1]): (r[2], r[3]) for r in table(text, ["Series", "Panel", "Colour", "Drawn as"])
    }
    if got_series != want_series:
        found.append(f"series rows differ: document {got_series}, dashboards {want_series}")

    # The 0.95 of the fraction steps is the metrics step's "complete" limit (display only).
    for steps_text in want_steps.values():
        if "from 0.95" in steps_text and metrics.COMPLETE_COVERAGE != 0.95:
            found.append("the 0.95 in the colour steps is no longer COMPLETE_COVERAGE")
    if f"{metrics.COMPLETE_COVERAGE:g}" not in "".join(got_steps.values()):
        found.append("COMPLETE_COVERAGE does not appear in the colour steps")
    return found


def claim_problems(text: str) -> list[str]:
    """Statements of the document that are checked against committed files."""
    found: list[str] = []
    flat = " ".join(text.split())

    provider = yaml.safe_load(PROVIDER.read_text(encoding="utf-8"))["providers"][0]
    if provider["allowUiUpdates"] is not False or provider["disableDeletion"] is not True:
        found.append(
            "provisioning is no longer read-only (allowUiUpdates false, disableDeletion true)"
        )
    for phrase in ("`allowUiUpdates: false`", "`disableDeletion: true`"):
        if phrase not in text:
            found.append(f"the document does not say {phrase}")

    totals = json.loads(CHECK_REPORT.read_text(encoding="utf-8"))["totals"]
    counts = (
        f"{totals['runs']} runs, {totals['panel_targets']:,} panel queries, "
        f"{totals['with_rows']:,} with rows, {totals['empty_allowed']} empty and allowed"
    )
    if counts not in flat:
        found.append(f"the document does not give the committed check counts: {counts}")
    if totals["empty"] != 0 or totals["errors"] != 0:
        found.append("the committed check has empty or failing panel queries")
    if "0 errors" not in flat:
        found.append("the document does not say 0 errors")

    if f"Power residual (logged {MINUS} computed)" not in text:
        found.append("the document lacks the title with the true minus sign (U+2212)")
    if "Power residual (logged - computed)" in text:
        found.append("the document spells a title with a hyphen minus")
    return found


# ---------------------------------------------------------------------------- the document


def test_the_dashboard_files_are_present():
    dashboards = load_dashboards()
    assert sorted(dashboards) == ["dac-compare", "dac-experiment"]
    assert [p.name for p in dashboard_files()] == ["compare.json", "experiment.json"]


def test_s6_26_the_document_agrees_with_the_dashboards():
    assert problems(DOC_TEXT) == []


def test_s6_26_every_panel_title_of_every_file_is_in_the_document():
    for uid, doc in load_dashboards().items():
        titles = [
            row[1] for row in table(section(DOC_TEXT, uid), ["Id", "Title", "Type", "Source"])
        ]
        assert titles == [p["title"] for p in panels_of(doc)], uid
        assert len(titles) == len(set(titles)), f"{uid} repeats a title"


def test_s6_26_every_variable_of_every_file_is_in_the_document():
    for uid, doc in load_dashboards().items():
        names = [r[0] for r in table(section(DOC_TEXT, uid), ["Variable", "Type", "Shown"])]
        assert names == [v["name"] for v in doc["templating"]["list"]], uid


def test_s6_26_the_inventory_has_the_planned_sizes():
    dashboards = load_dashboards()
    assert len(panels_of(dashboards["dac-compare"])) == 9
    assert len(panels_of(dashboards["dac-experiment"])) == 10
    assert len(expected_annotations(dashboards["dac-experiment"])) == 1
    assert expected_annotations(dashboards["dac-compare"]) == []


def test_s6_26_the_colour_conventions_of_the_plan_are_in_the_json():
    status = {}
    for doc in load_dashboards().values():
        status.update(mapping_rows(doc))
    assert status[("Whole-run KPIs", "status", "complete")] == "green"
    assert status[("Whole-run KPIs", "status", "partial")] == "amber"
    assert status[("Whole-run KPIs", "status", "none")] == "red"
    assert (
        status[("Which pairs can be compared", "conditions_status", "same_conditions")] == "green"
    )
    assert status[("Which pairs can be compared", "conditions_status", "supported")] == "green"
    assert status[("Which pairs can be compared", "conditions_status", "confounded")] == "amber"
    assert status[("Gaps and stuck stretches", "kind", "gap")] == "grey"
    assert status[("Gaps and stuck stretches", "kind", "flatline")] == "amber"
    series = {}
    for doc in load_dashboards().values():
        series.update(series_rows(doc))
    assert series[("excluded (raw value)", "${signal}: accepted and excluded")] == ("red", "points")
    assert series[("accepted", "${signal}: accepted and excluded")] == ("blue", "line")


def test_the_document_names_its_limits():
    for phrase in (
        "Grafana 13 has no colour per annotation row",
        "`quality_intervals` does not exist",
        "EXP_005",
        "mirrored",
        "No finding is shown",
        "dac_rollup",
    ):
        assert phrase in DOC_TEXT, phrase


def test_the_document_never_names_the_project():
    assert "phl" + "air" not in DOC_TEXT.lower()


# ---------------------------------------------------------------------------- mutation checks
# Each test changes a copy of the document text and checks that `problems` notices.


def _mutated(old: str, new: str) -> str:
    assert DOC_TEXT.count(old) >= 1, f"{old!r} is not in the document"
    return DOC_TEXT.replace(old, new, 1)


def test_mutation_a_changed_panel_title_is_noticed():
    text = _mutated("| `Signal quality` | table |", "| `Signal quality now` | table |")
    assert any("panels" in p for p in problems(text))


def test_mutation_the_minus_sign_replaced_by_a_hyphen_is_noticed():
    text = _mutated(f"(logged {MINUS} computed)", "(logged - computed)")
    assert any("minus" in p or "hyphen" in p or "panels" in p for p in problems(text))


def test_mutation_a_dropped_panel_row_is_noticed():
    lines = DOC_TEXT.splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.startswith("| 9 | `Excluded readings by reason` |")]
    assert len(kept) == len(lines) - 1
    assert any("panels" in p for p in problems("".join(kept)))


def test_mutation_a_changed_panel_type_or_source_is_noticed():
    text = _mutated(
        "| `Process phases` | state-timeline | InfluxDB |",
        "| `Process phases` | timeseries | InfluxDB |",
    )
    assert any("panels" in p for p in problems(text))
    text = _mutated("| `Experiments` | table | Postgres |", "| `Experiments` | table | InfluxDB |")
    assert any("panels" in p for p in problems(text))


def test_mutation_a_changed_variable_is_noticed():
    text = _mutated(
        "| `pg_schema` | constant | no | - | public |", "| `pg_schema` | constant | no | - | dac |"
    )
    assert any("variables" in p for p in problems(text))
    text = _mutated(
        "| `signal` | query | yes | single | voltage |",
        "| `signal` | query | no | single | voltage |",
    )
    assert any("variables" in p for p in problems(text))


def test_mutation_a_dropped_or_invented_variable_is_noticed():
    lines = DOC_TEXT.splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.startswith("| `metric` |")]
    assert len(kept) == len(lines) - 1
    assert any("variables" in p for p in problems("".join(kept)))
    text = _mutated(
        "| `metric` | custom |",
        "| `invented` | custom | yes | single | x |\n| `metric` | custom |",
    )
    assert any("invented" in p for p in problems(text))


def test_mutation_a_changed_uid_or_file_is_noticed():
    text = _mutated(
        "| `dac-compare` | `grafana/dashboards/compare.json` |",
        "| `dac-compare2` | `grafana/dashboards/compare.json` |",
    )
    assert problems(text)
    text = _mutated(
        "`grafana/dashboards/experiment.json` | DAC", "`grafana/dashboards/detail.json` | DAC"
    )
    assert any("title, file or folder" in p for p in problems(text))


def test_mutation_a_changed_annotation_is_noticed():
    text = _mutated(
        "| `Gaps and stuck stretches` | 3 | amber |", "| `Gaps and stuck stretches` | 4 | amber |"
    )
    assert any("annotation" in p for p in problems(text))
    text = _mutated(
        "| `Gaps and stuck stretches` | 3 | amber |", "| `Gaps and stuck stretches` | 3 | grey |"
    )
    assert any("annotation" in p for p in problems(text))


def test_mutation_a_changed_status_colour_is_noticed():
    text = _mutated(
        "| Whole-run KPIs | status | partial | amber |",
        "| Whole-run KPIs | status | partial | red |",
    )
    assert any("status colour" in p for p in problems(text))
    text = _mutated(
        "| Gaps and stuck stretches | kind | gap | grey |",
        "| Gaps and stuck stretches | kind | gap | amber |",
    )
    assert any("status colour" in p for p in problems(text))


def test_mutation_a_dropped_status_row_is_noticed():
    lines = DOC_TEXT.splitlines(keepends=True)
    kept = [
        ln
        for ln in lines
        if not ln.startswith("| Which pairs can be compared | conditions_status | confounded |")
    ]
    assert len(kept) == len(lines) - 1
    assert any("status colour" in p for p in problems("".join(kept)))


def test_mutation_a_changed_threshold_is_noticed():
    text = _mutated(
        "red; amber from 0.5; green from 0.95 |", "red; amber from 0.5; green from 0.9 |"
    )
    assert any("colour steps" in p or "COMPLETE_COVERAGE" in p for p in problems(text))
    text = _mutated(
        "green; amber from 0.05; red from 0.5 |", "green; amber from 0.1; red from 0.5 |"
    )
    assert any("colour steps" in p for p in problems(text))


def test_mutation_a_changed_series_colour_is_noticed():
    text = _mutated("| excluded (raw value) |", "| excluded (raw values) |")
    assert any("series" in p for p in problems(text))
    text = _mutated("| red | points |", "| red | line |")
    assert any("series" in p for p in problems(text))


def test_mutation_changed_check_counts_are_noticed():
    text = _mutated("299 runs", "300 runs")
    assert any("check counts" in p for p in problems(text))
    text = _mutated("3,082 with rows", "3,081 with rows")
    assert any("check counts" in p for p in problems(text))


def test_mutation_a_missing_dashboard_file_is_noticed():
    only_one = {k: v for k, v in load_dashboards().items() if k == "dac-compare"}
    assert any("dashboard table" in p for p in problems(DOC_TEXT, only_one))
    assert problems(DOC_TEXT, {}) == ["no dashboard files were found"]


def test_mutation_a_read_write_provider_claim_is_noticed():
    text = _mutated("`allowUiUpdates: false`", "`allowUiUpdates: true`")
    assert any("allowUiUpdates" in p for p in problems(text))
