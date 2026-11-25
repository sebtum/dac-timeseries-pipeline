"""The committed dashboards and the Grafana provisioning pass the lint (S6.5, second clause).

The dashboards arrive after this file (`grafana/dashboards/compare.json`, `experiment.json`), so
the loop over the files that exist is deliberately not a `parametrize`: a parametrized test over an
empty directory is collected as a skip, and a skip would hide that the lint ran over nothing. A
plain loop passes with an empty or absent directory, and says so in
`test_the_dashboard_directory_is_handled_explicitly`. The provisioning and compose checks below
pin the read-only, secret-free setup of decisions 1, 4 and 5.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from pipeline.grafana_check import lint, lint_uniqueness, load_dashboard, provisioned_uids

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "grafana" / "dashboards"
PROVISIONING = REPO_ROOT / "grafana" / "provisioning"
DATASOURCES = PROVISIONING / "datasources" / "datasources.yaml"
COMPOSE = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def dashboard_files(directory: Path = DASHBOARD_DIR) -> list[Path]:
    """The dashboard files that exist; an absent directory is an empty list, not an error."""
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def lint_directory(directory: Path) -> dict[str, list[str]]:
    uids = provisioned_uids(DATASOURCES)
    docs: dict[str, dict] = {}
    problems: dict[str, list[str]] = {}
    for path in dashboard_files(directory):
        doc = load_dashboard(path)
        docs[path.name] = doc
        found = lint(doc, uids)
        if found:
            problems[path.name] = found
    duplicated = lint_uniqueness(docs)
    if duplicated:
        problems["(uids)"] = duplicated
    return problems


def test_s6_5_every_committed_dashboard_lints_clean():
    assert lint_directory(DASHBOARD_DIR) == {}


def test_the_dashboard_directory_is_handled_explicitly(tmp_path):
    files = dashboard_files()
    if DASHBOARD_DIR.exists():
        assert DASHBOARD_DIR.is_dir()
    else:
        assert files == []  # absent directory: nothing to lint, and that is stated here
    assert all(path.suffix == ".json" for path in files)
    # an absent and an empty directory both give an empty list, never an error
    assert dashboard_files(tmp_path / "missing") == []
    assert dashboard_files(tmp_path) == []
    # only the two dashboards of M6 are expected
    assert {path.name for path in files} <= {"compare.json", "experiment.json"}


def test_the_loop_does_see_a_bad_dashboard_when_one_exists(tmp_path):
    good = {"uid": "good", "title": "Good", "panels": []}
    bad = {
        "uid": "bad",
        "title": "Bad",
        "panels": [
            {
                "id": 1,
                "title": "P",
                "datasource": {"uid": "other"},
                "targets": [{"refId": "A", "rawSql": "SELECT ${undeclared}"}],
            }
        ],
    }
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    problems = lint_directory(tmp_path)
    assert set(problems) == {"bad.json"}
    assert len(problems["bad.json"]) == 2


def test_two_files_with_the_same_dashboard_uid_are_caught(tmp_path):
    doc = json.dumps({"uid": "same", "title": "T", "panels": []})
    (tmp_path / "a.json").write_text(doc, encoding="utf-8")
    (tmp_path / "b.json").write_text(doc, encoding="utf-8")
    assert "(uids)" in lint_directory(tmp_path)


def test_committed_dashboards_are_json_files_with_a_dashboard_uid():
    for path in dashboard_files():
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(doc["uid"], str) and doc["uid"], path.name


# ------------------------------------------------------------------- provisioning (decisions 1, 5)


def test_the_provisioned_datasources_have_the_fixed_uids_and_no_inline_secret():
    text = DATASOURCES.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    by_uid = {d["uid"]: d for d in doc["datasources"]}
    assert set(by_uid) == {"influx-dac", "pg-dac"}
    influx, pg = by_uid["influx-dac"], by_uid["pg-dac"]
    assert influx["type"] == "influxdb"
    assert influx["jsonData"] == {
        "version": "SQL",
        "dbName": "dac_raw",
        "httpMode": "POST",
        "insecureGrpc": True,
    }
    assert influx["url"] == "$DAC_INFLUX_URL"
    assert influx["secureJsonData"] == {"token": "$INFLUX_TOKEN"}
    assert pg["type"] == "grafana-postgresql-datasource"
    assert pg["url"] == "$DAC_POSTGRES_HOST"
    assert pg["user"] == "$POSTGRES_USER"
    assert pg["jsonData"]["database"] == "$POSTGRES_DB"
    assert pg["jsonData"]["sslmode"] == "disable"
    assert pg["secureJsonData"] == {"password": "$POSTGRES_PASSWORD"}
    assert not influx["editable"] and not pg["editable"]
    # every secret-looking value is an environment reference, never a literal
    assert not re.search(r"apiv3_|changeme", text)


def test_dashboards_are_provisioned_read_only_into_the_dac_folder():
    doc = yaml.safe_load(
        (PROVISIONING / "dashboards" / "dashboards.yaml").read_text(encoding="utf-8")
    )
    (provider,) = doc["providers"]
    assert provider["folder"] == "DAC"
    assert provider["allowUiUpdates"] is False
    assert provider["disableDeletion"] is True
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"


# ---------------------------------------------------------------------- compose (decisions 4, 10)


def test_grafana_and_renderer_images_are_pinned_to_exact_tags():
    for service, repository in (
        ("grafana", "grafana/grafana"),
        ("renderer", "grafana/grafana-image-renderer"),
    ):
        image = COMPOSE["services"][service]["image"]
        name, _, tag = image.partition(":")
        assert name == repository
        assert re.fullmatch(r"v?\d+\.\d+\.\d+", tag), image  # no latest, no floating minor


def test_grafana_service_matches_decision_4():
    grafana = COMPOSE["services"]["grafana"]
    assert grafana["container_name"] == "${GRAFANA_CONTAINER_NAME:-dac-grafana}"
    assert grafana["ports"] == ["${GRAFANA_PORT:-3000}:3000"]
    assert grafana["depends_on"] == {
        "influxdb": {"condition": "service_healthy"},
        "postgres": {"condition": "service_healthy"},
    }
    assert "grafana-data" in COMPOSE["volumes"]
    assert set(grafana["volumes"]) == {
        "grafana-data:/var/lib/grafana",
        "./grafana/provisioning:/etc/grafana/provisioning:ro",
        "./grafana/dashboards:/var/lib/grafana/dashboards:ro",
    }
    env = grafana["environment"]
    assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert env["GF_USERS_ALLOW_SIGN_UP"] == "false"
    assert env["GF_SECURITY_ADMIN_USER"].startswith("${GRAFANA_ADMIN_USER")
    assert env["GF_SECURITY_ADMIN_PASSWORD"].startswith("${GRAFANA_ADMIN_PASSWORD")
    assert env["DAC_INFLUX_URL"] == "${DAC_INFLUX_URL:-http://influxdb:8181}"
    assert env["DAC_POSTGRES_HOST"] == "${DAC_POSTGRES_HOST:-postgres:5432}"
    assert env["INFLUX_TOKEN"] == "${INFLUX_TOKEN:-}"
    assert env["GF_RENDERING_SERVER_URL"] == "http://renderer:8081/render"
    assert env["GF_RENDERING_CALLBACK_URL"] == "http://grafana:3000/"


def test_the_renderer_only_runs_under_the_render_profile():
    renderer = COMPOSE["services"]["renderer"]
    assert renderer["profiles"] == ["render"]
    assert "profiles" not in COMPOSE["services"]["grafana"]
    assert "ports" not in renderer  # reached by Grafana over the compose network only


def test_no_secret_value_is_written_into_the_compose_file():
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "apiv3_" not in text
