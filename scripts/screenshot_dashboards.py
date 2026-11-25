"""Render the four pinned dashboard views to PNG through the Grafana image renderer.

    python -m scripts.screenshot_dashboards [--out DIR] [--width PX] [--height PX]

Grafana (with the renderer service from `docker compose --profile render up -d renderer`) comes
from `.env`: `GRAFANA_URL`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`. The images are fetched
from `/render/d/<uid>` (whole dashboard) and `/render/d-solo/<uid>` (one panel), with the same
variables and time range the dashboards use when they are opened by hand.

Views (file name: what it shows):

- `compare-all.png`: `dac-compare`, every experiment selected, signal voltage, whole dashboard.
- `compare-overlay-voltage.png`: panel C6 of `dac-compare` alone, all six experiments, voltage.
- `experiment-exp001-voltage.png`: `dac-experiment`, EXP_001 over its window, signal voltage.
- `experiment-exp004-air-flow.png`: `dac-experiment`, EXP_004 over its window, signal air_flow.

`--height` defaults to 1000 px for the single-panel and detail views and to the full dashboard
height (the renderer's `height=-1`) for `compare-all.png`, which is taller than any screen; an
explicit `--height` (a pixel count, or -1 for the full page) applies to every view. Experiment
windows come from Postgres `experiment` through Grafana's own datasource, not from a copy here.

Every image is fetched and checked (PNG header, requested width) before the first file is
written. Exit 0: all four saved. Exit 2: Grafana or the renderer unreachable, a render refused or
not a PNG, or a bad setting; nothing saved.

Standard library only; no InfluxDB or Postgres write.
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pipeline.grafana_check import ENV_PATH, REPO_ROOT, read_env

DEFAULT_OUT = REPO_ROOT / "docs" / "screenshots" / "m6"
DEFAULT_WIDTH = 1600
DEFAULT_HEIGHT = 1000
FULL_PAGE = -1
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
RENDER_TIMEOUT_S = 300
PG_DATASOURCE = {"uid": "pg-dac", "type": "grafana-postgresql-datasource"}
COMPARE_UID = "dac-compare"
EXPERIMENT_UID = "dac-experiment"
OVERLAY_PANEL_ID = 6  # C6 `Overlay: ${signal} in minutes since start`


class ScreenshotError(Exception):
    """A refusal: nothing is saved."""


@dataclass(frozen=True)
class View:
    filename: str
    path: str  # `/render/d/<uid>` or `/render/d-solo/<uid>`
    params: dict[str, str]
    experiment: str | None = None  # window taken from Postgres when set
    default_height: int = DEFAULT_HEIGHT


VIEWS = (
    View(
        "compare-all.png",
        f"/render/d/{COMPARE_UID}",
        {"var-experiment": "All", "var-signal": "voltage"},
        default_height=FULL_PAGE,
    ),
    View(
        "compare-overlay-voltage.png",
        f"/render/d-solo/{COMPARE_UID}",
        {"var-experiment": "All", "var-signal": "voltage", "panelId": str(OVERLAY_PANEL_ID)},
    ),
    View(
        "experiment-exp001-voltage.png",
        f"/render/d/{EXPERIMENT_UID}",
        {"var-experiment": "EXP_001", "var-signal": "voltage"},
        experiment="EXP_001",
    ),
    View(
        "experiment-exp004-air-flow.png",
        f"/render/d/{EXPERIMENT_UID}",
        {"var-experiment": "EXP_004", "var-signal": "air_flow"},
        experiment="EXP_004",
    ),
)


class Grafana:
    def __init__(self, url: str, user: str, password: str) -> None:
        self.url = url.rstrip("/")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def get(self, path_and_query: str) -> bytes:
        request = urllib.request.Request(self.url + path_and_query, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=RENDER_TIMEOUT_S) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode("utf-8", "replace").strip()
            if detail.startswith("<"):  # Grafana's HTML error page says nothing useful
                detail = "renderer not reachable or render failed (is the `render` profile up?)"
            raise ScreenshotError(
                f"HTTP {exc.code} from {path_and_query.split('?')[0]}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ScreenshotError(f"cannot reach Grafana at {self.url}: {exc}") from exc

    def post_json(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode()
        request = urllib.request.Request(
            self.url + path,
            data=data,
            headers={**self.headers, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ScreenshotError(f"HTTP {exc.code} from {path}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ScreenshotError(f"cannot reach Grafana at {self.url}: {exc}") from exc

    def experiment_window_ms(self, experiment_id: str) -> tuple[int, int]:
        """Start and end of an experiment in epoch ms, read from Postgres through Grafana."""
        sql = (
            "SELECT (extract(epoch FROM start_time) * 1000)::bigint AS from_ms, "
            "(extract(epoch FROM end_time) * 1000)::bigint AS to_ms "
            f"FROM experiment WHERE experiment_id = '{experiment_id}'"
        )
        body = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": PG_DATASOURCE,
                    "rawSql": sql,
                    "format": "table",
                    "rawQuery": True,
                    "editorMode": "code",
                }
            ],
            "from": "0",
            "to": "4102444800000",
        }
        result = self.post_json("/api/ds/query", body).get("results", {}).get("A", {})
        try:
            values = result["frames"][0]["data"]["values"]
            return int(values[0][0]), int(values[1][0])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ScreenshotError(
                f"no window for {experiment_id} in Postgres experiment: {result.get('error')}"
            ) from exc


def png_width(data: bytes) -> int:
    if not data.startswith(PNG_MAGIC) or len(data) < 24:
        raise ScreenshotError("the renderer did not return a PNG")
    return struct.unpack(">I", data[16:20])[0]


def render(grafana: Grafana, view: View, width: int, height: int | None) -> bytes:
    params = {"orgId": "1", **view.params, "kiosk": "1"}
    if view.experiment:
        params["from"], params["to"] = (
            str(v) for v in grafana.experiment_window_ms(view.experiment)
        )
    params["width"] = str(width)
    params["height"] = str(view.default_height if height is None else height)
    data = grafana.get(f"{view.path}?{urllib.parse.urlencode(params)}")
    got = png_width(data)
    if got != width:
        raise ScreenshotError(f"{view.filename} is {got} px wide, expected {width}")
    return data


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.screenshot_dashboards", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="image width in px")
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="image height in px; -1 = full dashboard (default: 1000, full for compare-all)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.width < 100 or (
            args.height is not None and args.height != FULL_PAGE and args.height < 100
        ):
            raise ScreenshotError(
                "--width and --height must be at least 100 px (--height -1: full)"
            )
        env = read_env(ENV_PATH)
        user, password = env.get("GRAFANA_ADMIN_USER", ""), env.get("GRAFANA_ADMIN_PASSWORD", "")
        if not user or not password:
            raise ScreenshotError("GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD are not set (.env)")
        grafana = Grafana(env.get("GRAFANA_URL", "http://localhost:3000"), user, password)
        images: dict[str, bytes] = {}
        for view in VIEWS:
            data = render(grafana, view, args.width, args.height)
            images[view.filename] = data
            print(f"screenshot_dashboards: rendered {view.filename} ({len(data)} bytes)")
    except ScreenshotError as exc:
        print(f"screenshot_dashboards: refused: {exc}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in images.items():
        (args.out / name).write_bytes(data)
    print(f"screenshot_dashboards: saved {len(images)} images to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
