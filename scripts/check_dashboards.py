"""Check the committed Grafana dashboards: lint them, then run every panel query through Grafana.

    python -m scripts.check_dashboards [--dashboard PATH ...] [--experiment ID ...]
        [--var NAME=VALUE ...] [--sweep NAME ...] [--time-range window|span|FROM,TO]
        [--allow-empty TITLE ...] [--report-dir DIR]

Every selection (each experiment alone, plus all requested together when the dashboard's
`experiment` variable takes several) is run against Grafana with the variables resolved as the
dashboard would resolve them. Each panel target and annotation query is posted to
`/api/ds/query` and the rows it returns are counted. The result is `dashboard_check.json`
(contract `contracts/dashboard_check.schema.json`).

Exit codes: 0 every panel target returned at least one row without error (targets of panels
named by `--allow-empty` may be empty) and no annotation query failed; 1 a panel target was empty
or failed, or an annotation query failed (the file is written); 2 refused, nothing written (Grafana
unreachable or the login refused, a dashboard unreadable or failing the lint, an unknown
experiment, a bad argument).

Grafana comes from `.env` (or the process environment, which wins): `GRAFANA_URL`,
`GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pipeline.grafana_check import (
    DEFAULT_DATASOURCES_YAML,
    ENV_PATH,
    REPO_ROOT,
    CheckError,
    ClientFactory,
    GrafanaClient,
    exit_code,
    failures,
    lint,
    lint_uniqueness,
    load_dashboard,
    parse_time_range,
    provisioned_uids,
    read_env,
    run_check,
)

DASHBOARD_DIR = REPO_ROOT / "grafana" / "dashboards"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
REPORT_NAME = "dashboard_check.json"
DEFAULT_URL = "http://localhost:3000"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.check_dashboards", description=__doc__)
    many = {"nargs": "+", "action": "extend", "default": []}
    parser.add_argument("--dashboard", type=Path, metavar="PATH", **many)
    parser.add_argument("--experiment", metavar="ID", **many)
    parser.add_argument("--var", metavar="NAME=VALUE", **many)
    parser.add_argument("--sweep", metavar="NAME", **many)
    parser.add_argument("--allow-empty", metavar="TITLE", **many)
    parser.add_argument("--time-range", default="window", metavar="window|span|FROM,TO")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--datasources",
        type=Path,
        default=DEFAULT_DATASOURCES_YAML,
        help="provisioning file whose uids the lint accepts",
    )
    return parser.parse_args(argv)


def parse_overrides(items: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise CheckError(f"--var expects NAME=VALUE (got {item!r})")
        overrides[name] = value
    return overrides


def grafana_settings() -> tuple[str, str, str]:
    env = {
        **read_env(ENV_PATH),
        **{k: v for k, v in os.environ.items() if k.startswith("GRAFANA_")},
    }
    url = env.get("GRAFANA_URL", DEFAULT_URL)
    user = env.get("GRAFANA_ADMIN_USER", "")
    password = env.get("GRAFANA_ADMIN_PASSWORD", "")
    if not user or not password:
        raise CheckError("GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD are not set (.env)")
    return url, user, password


def load_and_lint(paths: list[Path], datasources: Path) -> list[tuple[Path, dict]]:
    uids = provisioned_uids(datasources)
    loaded: list[tuple[Path, dict]] = []
    problems: list[str] = []
    for path in paths:
        doc = load_dashboard(path)
        problems.extend(f"{path}: {problem}" for problem in lint(doc, uids))
        loaded.append((path, doc))
    problems.extend(lint_uniqueness({str(p): d for p, d in loaded}))
    if problems:
        raise CheckError("lint failed:\n  " + "\n  ".join(problems))
    return loaded


def main(argv: list[str] | None = None, client_factory: ClientFactory = GrafanaClient) -> int:
    args = parse_args(argv)
    try:
        overrides = parse_overrides(args.var)
        parse_time_range(args.time_range)
        paths = args.dashboard or sorted(DASHBOARD_DIR.glob("*.json"))
        if not paths:
            raise CheckError(f"no dashboards found in {DASHBOARD_DIR}")
        loaded = load_and_lint(paths, args.datasources)
        url, user, password = grafana_settings()
        client = client_factory(url, user, password)
        client.health()
        summary = run_check(
            client,
            loaded,
            experiments=args.experiment or None,
            overrides=overrides,
            sweep=args.sweep,
            time_range=args.time_range,
            allow_empty=args.allow_empty,
        )
    except CheckError as exc:
        print(f"check_dashboards: refused: {exc}", file=sys.stderr)
        return 2

    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / REPORT_NAME).write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    totals = summary["totals"]
    for line in failures(summary):
        print(f"check_dashboards: FAIL {line}", file=sys.stderr)
    print(
        f"check_dashboards: {totals['runs']} runs, {totals['panel_targets']} panel targets: "
        f"{totals['with_rows']} with rows, {totals['empty']} empty, "
        f"{totals['empty_allowed']} empty (allowed), {totals['errors']} errors, "
        f"{totals['annotation_errors']} annotation errors"
    )
    return exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
