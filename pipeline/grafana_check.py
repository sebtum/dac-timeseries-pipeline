"""Static lint and live run of the committed Grafana dashboards (M6 decision 8).

Two jobs, both over the dashboard JSON files under `grafana/dashboards`:

1. `lint` needs no running service. It reports unresolved references: a datasource that is
   neither a dashboard datasource variable (`${influx}`, `${pg}`) nor a provisioned uid, a
   `$name` / `${name}` / `${name:fmt}` that is no declared variable and no Grafana macro
   (`$__...`), a format outside the four the checker understands, and duplicate panel ids.
2. `run_check` resolves the dashboard variables itself and posts every panel target and every
   annotation query to Grafana's `/api/ds/query`, then reports the rows each one returned. A
   dashboard that only looks right in the UI is not enough: the numbers behind it are what the
   checker pins.

Variables are resolved the way a browser would, but deterministically: overrides first, then
constants, custom lists and datasource variables, and query variables run through Grafana, in
the order of the dashboard's `templating.list`. The time range is derived from Postgres (the
selected experiments' windows), so `$__timeFilter(time)` and friends are expanded by Grafana
itself, as in the browser.

Only the standard library and PyYAML are used (the lint reads the provisioned datasource uids
from the provisioning YAML).
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
DEFAULT_DATASOURCES_YAML = (
    REPO_ROOT / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
)

FORMATS = frozenset({"raw", "sqlstring", "csv"})
SELECTION_VARIABLE = "experiment"
BUILTIN_DATASOURCES = frozenset({"-- Grafana --", "-- Mixed --", "grafana"})
DATASOURCE_VARIABLES = frozenset({"influx", "pg"})
TIME_RANGES = ("window", "span", "fixed")

_VAR_RE = re.compile(
    r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_.]*)(?::(?P<fmt>[^}]*))?\}"
    r"|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
)
_DS_VARIABLE_RE = re.compile(r"^\$\{?(influx|pg)\}?$")


class CheckError(RuntimeError):
    """Something the caller must fix; the CLI turns it into exit code 2."""


# ----------------------------------------------------------------------------- reading files


def load_dashboard(path: str | Path) -> dict:
    """Parse one dashboard JSON file; a missing or malformed file is a `CheckError`."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CheckError(f"cannot read dashboard {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CheckError(f"dashboard {path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise CheckError(f"dashboard {path} is not a JSON object")
    return doc


def provisioned_uids(datasources_yaml_path: str | Path) -> set[str]:
    """The `uid` of every datasource in a provisioning file."""
    path = Path(datasources_yaml_path)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CheckError(f"cannot read datasource provisioning {path}: {exc}") from exc
    entries = doc.get("datasources") or []
    return {str(entry["uid"]) for entry in entries if isinstance(entry, dict) and entry.get("uid")}


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    """`KEY=VALUE` lines of a `.env` file; {} when it does not exist."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


# ------------------------------------------------------------------------ variables in text


def variables_used(text: str) -> set[tuple[str, str | None]]:
    """`(name, format)` of every `$name`, `${name}` and `${name:fmt}` in `text`.

    Grafana's own names (`$__timeFilter(...)`, `${__from}`, `${__data.fields.x}`) are macros, not
    dashboard variables, and are left out. A plain `$name` has format `None`.
    """
    found: set[tuple[str, str | None]] = set()
    for match in _VAR_RE.finditer(text):
        name = match.group("braced") or match.group("plain")
        if name.startswith("__"):
            continue
        found.add((name, match.group("fmt")))
    return found


def interpolate(text: str, values: dict[str, str | list[str]]) -> str:
    """Replace the dashboard variables in `text` the way the checker's queries need them.

    `$name` and `${name}` give the value (a list joined by `,`); `:raw` and `:csv` the same;
    `:sqlstring` single-quotes each value (a `'` doubled) and joins by `,`. `$__...` macros are
    left for Grafana. An unknown name or an unknown format raises `CheckError` naming it.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group("braced") or match.group("plain")
        if name.startswith("__"):
            return match.group(0)
        fmt = match.group("fmt")
        if fmt is not None and fmt not in FORMATS:
            raise CheckError(f"unknown format {fmt!r} for variable {name!r} in {_excerpt(text)}")
        if name not in values:
            raise CheckError(f"unknown variable {name!r} in {_excerpt(text)}")
        raw = values[name]
        items = [str(v) for v in raw] if isinstance(raw, list | tuple) else [str(raw)]
        if fmt == "sqlstring":
            return ",".join("'" + item.replace("'", "''") + "'" for item in items)
        return ",".join(items)

    return _VAR_RE.sub(replace, text)


def _excerpt(text: str, limit: int = 80) -> str:
    one_line = " ".join(text.split())
    return repr(one_line if len(one_line) <= limit else one_line[: limit - 3] + "...")


# ------------------------------------------------------------------------- walking a dashboard


def _all_panels(doc: dict) -> list[dict]:
    """Every panel, including the ones nested in rows, in document order."""
    out: list[dict] = []

    def walk(panels: Iterable[Any]) -> None:
        for panel in panels or []:
            if not isinstance(panel, dict):
                continue
            out.append(panel)
            walk(panel.get("panels") or [])

    walk(doc.get("panels") or [])
    return out


def panel_targets(doc: dict) -> list[tuple[dict, dict]]:
    """`(panel, target)` for every target of every panel, in panel-id order.

    Panels inside rows are included. Targets keep their order within a panel.
    """
    pairs: list[tuple[dict, dict]] = []
    for panel in sorted(_all_panels(doc), key=lambda p: (p.get("id", 0), p.get("title", ""))):
        pairs.extend((panel, target) for target in panel.get("targets") or [])
    return pairs


def _templating(doc: dict) -> list[dict]:
    return list((doc.get("templating") or {}).get("list") or [])


def _annotation_entries(doc: dict) -> list[dict]:
    entries = (doc.get("annotations") or {}).get("list") or []
    return [e for e in entries if isinstance(e, dict) and not e.get("builtIn")]


def _strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _ds_uid(ref: Any) -> str | None:
    if isinstance(ref, dict):
        uid = ref.get("uid")
        return str(uid) if uid is not None else None
    if isinstance(ref, str):
        return ref
    return None


# ------------------------------------------------------------------------------------ lint


def lint(doc: dict, uids: set[str]) -> list[str]:
    """Problems found in one dashboard; an empty list means clean. Needs no running service."""
    problems: list[str] = []
    allowed_ds = set(uids) | BUILTIN_DATASOURCES

    def check_ds(where: str, ref: Any, *, required: bool) -> None:
        uid = _ds_uid(ref)
        if uid is None:
            if required:
                problems.append(f"{where}: no datasource")
            return
        if _DS_VARIABLE_RE.match(uid) or uid in allowed_ds:
            return
        problems.append(
            f"{where}: datasource uid {uid!r} is not ${{influx}}, ${{pg}} or a provisioned uid"
        )

    if not isinstance(doc.get("uid"), str) or not doc["uid"]:
        problems.append("dashboard has no uid")

    variables = _templating(doc)
    names = [v.get("name") for v in variables]
    declared = {n for n in names if isinstance(n, str)}
    for name in sorted({n for n in names if names.count(n) > 1 and n}):
        problems.append(f"variable {name!r} is declared more than once")

    # panels: ids and datasources
    seen_ids: dict[int, str] = {}
    for panel in _all_panels(doc):
        title = panel.get("title", "")
        where = f"panel {panel.get('id', '?')} {title!r}"
        panel_id = panel.get("id")
        if not isinstance(panel_id, int):
            problems.append(f"{where}: no integer id")
        elif panel_id in seen_ids:
            problems.append(f"{where}: panel id {panel_id} is also used by {seen_ids[panel_id]!r}")
        else:
            seen_ids[panel_id] = title
        targets = panel.get("targets") or []
        panel_ref = panel.get("datasource")
        if panel_ref is not None:
            check_ds(where, panel_ref, required=False)
        ref_ids: set[str] = set()
        for target in targets:
            ref_id = target.get("refId")
            if not ref_id:
                problems.append(f"{where}: a target has no refId")
            elif ref_id in ref_ids:
                problems.append(f"{where}: refId {ref_id!r} is used twice")
            else:
                ref_ids.add(ref_id)
            if target.get("datasource") is not None:
                check_ds(f"{where} target {ref_id}", target["datasource"], required=False)
            elif panel_ref is None or _ds_uid(panel_ref) == "-- Mixed --":
                problems.append(f"{where} target {ref_id}: no datasource")

    # annotations
    for entry in _annotation_entries(doc):
        check_ds(f"annotation {entry.get('name', '?')!r}", entry.get("datasource"), required=True)

    # variables: datasource of query variables, and use before declaration
    for index, variable in enumerate(variables):
        name = variable.get("name", "?")
        if variable.get("type") == "query":
            check_ds(f"variable {name!r}", variable.get("datasource"), required=True)
        if variable.get("type") in ("query", "custom", "constant"):
            earlier = {v.get("name") for v in variables[:index]}
            for text in _strings(variable.get("query")):
                for used, _fmt in variables_used(text):
                    if used in declared and used not in earlier:
                        problems.append(
                            f"variable {name!r}: uses {used!r}, which is declared later"
                        )

    # every variable used anywhere is declared, in a known format
    reported: set[tuple[str, str | None]] = set()
    for text in _strings(doc):
        for name, fmt in sorted(variables_used(text), key=lambda t: (t[0], t[1] or "")):
            if (name, fmt) in reported:
                continue
            reported.add((name, fmt))
            if name not in declared:
                problems.append(f"variable {name!r} is used but not declared ({_excerpt(text)})")
            elif fmt is not None and fmt not in FORMATS:
                problems.append(
                    f"variable {name!r} uses format {fmt!r}; allowed: none, raw, sqlstring, csv"
                )
    return problems


def lint_uniqueness(docs: dict[str, dict]) -> list[str]:
    """Dashboard uids must be unique across files (`docs`: file label -> parsed dashboard)."""
    owners: dict[str, list[str]] = {}
    for label, doc in docs.items():
        uid = doc.get("uid")
        if isinstance(uid, str) and uid:
            owners.setdefault(uid, []).append(label)
    return [
        f"dashboard uid {uid!r} is used by {', '.join(sorted(labels))}"
        for uid, labels in sorted(owners.items())
        if len(labels) > 1
    ]


# --------------------------------------------------------------------------------- Grafana


@dataclass
class QueryResult:
    """What one query returned: total rows over all frames, field names, error text.

    `columns` holds the values of the first frame (one list per field) for the callers that need
    them (variable queries, the time range); the contract does not.
    """

    rows: int
    fields: list[str]
    error: str | None
    columns: list[list[Any]] = field(default_factory=list)


def to_epoch_ms(value: str | int | float | datetime) -> int:
    """An RFC 3339 string, an aware datetime or epoch milliseconds, as epoch milliseconds."""
    if isinstance(value, bool):
        raise CheckError(f"not an instant: {value!r}")
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CheckError(f"not an RFC 3339 instant: {value!r}") from exc
    if value.tzinfo is None:
        raise CheckError(f"instant without a time zone: {value!r}")
    return round(value.timestamp() * 1000)


def format_instant(epoch_ms: int) -> str:
    """Epoch milliseconds as an RFC 3339 UTC string ending in Z."""
    moment = datetime.fromtimestamp(epoch_ms / 1000, UTC)
    text = moment.strftime("%Y-%m-%dT%H:%M:%S")
    if epoch_ms % 1000:
        text += f".{epoch_ms % 1000:03d}"
    return text + "Z"


class GrafanaClient:
    """A small client for the parts of Grafana's HTTP API the checks need (basic auth)."""

    def __init__(self, url: str, user: str, password: str, timeout: float = 120.0):
        self.url = url.rstrip("/")
        self._authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.timeout = timeout
        self.queries = 0
        self._types: dict[str, str] = {}

    # -- plumbing

    def api(
        self, method: str, path: str, body: Any = None, *, auth: bool = True
    ) -> tuple[int, Any]:
        """One request; returns `(status, parsed JSON or text)`. HTTP errors are returned, not
        raised. A server that cannot be reached raises `CheckError`."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            headers["Authorization"] = self._authorization
        request = urllib.request.Request(  # noqa: S310
            self.url + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise CheckError(f"Grafana not reachable at {self.url}: {exc}") from exc
        text = raw.decode("utf-8", errors="replace")
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            return status, text

    # -- health and login

    def health(self) -> dict:
        """`/api/health` of the server, after proving the login works (`/api/user`)."""
        status, body = self.api("GET", "/api/health", auth=False)
        if status != 200 or not isinstance(body, dict):
            raise CheckError(f"Grafana health at {self.url} answered {status}: {body!r}")
        status, _ = self.api("GET", "/api/user")
        if status in (401, 403):
            raise CheckError(f"Grafana login refused at {self.url} (HTTP {status})")
        if status != 200:
            raise CheckError(f"Grafana login check answered HTTP {status}")
        return body

    def version(self) -> str:
        status, body = self.api("GET", "/api/health", auth=False)
        if status != 200 or not isinstance(body, dict) or not body.get("version"):
            raise CheckError(f"cannot read the Grafana version (HTTP {status})")
        return str(body["version"])

    # -- datasources

    def datasources(self) -> list[dict]:
        status, body = self.api("GET", "/api/datasources")
        if status != 200 or not isinstance(body, list):
            raise CheckError(f"listing datasources answered HTTP {status}: {body!r}")
        return body

    def datasource_health(self, uid: str) -> dict:
        status, body = self.api("GET", f"/api/datasources/uid/{urllib.parse.quote(uid)}/health")
        if not isinstance(body, dict):
            raise CheckError(f"datasource {uid!r} health answered HTTP {status}: {body!r}")
        return {"http": status, **body}

    def datasource_kind(self, uid: str) -> str:
        """`influx` or `pg`, from the datasource's type."""
        if uid not in self._types:
            status, body = self.api("GET", f"/api/datasources/uid/{urllib.parse.quote(uid)}")
            if status != 200 or not isinstance(body, dict):
                raise CheckError(f"unknown datasource uid {uid!r} (HTTP {status})")
            self._types[uid] = str(body.get("type", ""))
        kind = self._types[uid]
        if kind == "influxdb":
            return "influx"
        if "postgres" in kind:
            return "pg"
        raise CheckError(
            f"datasource {uid!r} has type {kind!r}; only InfluxDB and Postgres are used"
        )

    def create_influx_datasource(self, name: str, database: str) -> str:
        """A temporary InfluxDB (SQL mode) datasource on `database`; returns its uid.

        The URL and connection options are copied from the provisioned `influx-dac` datasource, so
        the new one reaches InfluxDB the way that one does; only the database differs. The token
        is `INFLUX_TOKEN` from the process environment or `.env`.
        """
        token = os.environ.get("INFLUX_TOKEN") or read_env().get("INFLUX_TOKEN", "")
        if not token:
            raise CheckError("INFLUX_TOKEN is not set (environment or .env)")
        status, template = self.api("GET", "/api/datasources/uid/influx-dac")
        if status != 200 or not isinstance(template, dict):
            raise CheckError(f"the provisioned datasource influx-dac is missing (HTTP {status})")
        json_data = {**(template.get("jsonData") or {}), "dbName": database}
        status, body = self.api(
            "POST",
            "/api/datasources",
            {
                "name": name,
                "type": "influxdb",
                "access": "proxy",
                "url": template["url"],
                "jsonData": json_data,
                "secureJsonData": {"token": token},
            },
        )
        if status != 200 or not isinstance(body, dict) or "datasource" not in body:
            raise CheckError(f"creating datasource {name!r} answered HTTP {status}: {body!r}")
        return str(body["datasource"]["uid"])

    def delete_datasource(self, uid: str) -> None:
        status, body = self.api("DELETE", f"/api/datasources/uid/{urllib.parse.quote(uid)}")
        if status not in (200, 404):
            raise CheckError(f"deleting datasource {uid!r} answered HTTP {status}: {body!r}")
        self._types.pop(uid, None)

    # -- queries

    def query(
        self,
        datasource_uid: str,
        target: dict,
        time_from: str | int | float | datetime,
        time_to: str | int | float | datetime,
    ) -> QueryResult:
        """Run one target through `/api/ds/query`. A query that fails gives `error`, not a raise."""
        self.queries += 1
        ref_id = str(target.get("refId") or "A")
        ds_type = {"influx": "influxdb", "pg": "grafana-postgresql-datasource"}.get(
            self.datasource_kind(datasource_uid)
        )
        query = {
            "intervalMs": 1000,
            "maxDataPoints": 1000,
            **target,
            "refId": ref_id,
            "datasource": {"uid": datasource_uid, "type": self._types.get(datasource_uid, ds_type)},
        }
        status, body = self.api(
            "POST",
            "/api/ds/query",
            {
                "queries": [query],
                "from": str(to_epoch_ms(time_from)),
                "to": str(to_epoch_ms(time_to)),
            },
        )
        if status in (401, 403):
            raise CheckError(f"Grafana login refused (HTTP {status})")
        result = (body.get("results") or {}).get(ref_id) if isinstance(body, dict) else None
        if not isinstance(result, dict):
            return QueryResult(0, [], f"HTTP {status}: {_excerpt(str(body), 300)}")
        if result.get("error"):
            return QueryResult(0, [], str(result["error"]))
        if status != 200:
            return QueryResult(0, [], f"HTTP {status}")
        rows, names, columns = 0, [], []
        for index, frame in enumerate(result.get("frames") or []):
            values = (frame.get("data") or {}).get("values") or []
            rows += len(values[0]) if values else 0
            for fld in (frame.get("schema") or {}).get("fields") or []:
                if fld.get("name") not in names:
                    names.append(fld.get("name"))
            if index == 0:
                columns = values
        return QueryResult(rows, names, None, columns)


# ----------------------------------------------------------------------- variable resolution


def _query_sql(query: Any) -> str:
    if isinstance(query, dict):
        query = query.get("rawSql") or query.get("query")
    if not isinstance(query, str) or not query.strip():
        raise CheckError("a query variable has no SQL")
    return query


@dataclass
class _Context:
    """What one run needs to resolve variables: the client and the fixed inputs."""

    client: Any
    overrides: dict[str, str]
    time_range: str  # window | span | a "FROM,TO" pair
    fixed: tuple[int, int] | None
    queries: int = 0

    def run(self, uid: str, target: dict, time_from: int, time_to: int) -> QueryResult:
        self.queries += 1
        return self.client.query(uid, target, time_from, time_to)


def _stringify(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _split_override(variable: dict, text: str) -> str | list[str]:
    return [p.strip() for p in text.split(",") if p.strip()] if variable.get("multi") else text


def _current(variable: dict) -> str | list[str] | None:
    current = variable.get("current") or {}
    value = current.get("value")
    if isinstance(value, list):
        return [str(v) for v in value]
    return None if value is None else str(value)


def _query_variable_options(
    ctx: _Context, variable: dict, values: dict, time_from: int, time_to: int
) -> list[str]:
    name = variable.get("name", "?")
    sql = interpolate(_query_sql(variable.get("query")), values)
    uid = _ds_uid(variable.get("datasource"))
    if uid is None:
        raise CheckError(f"query variable {name!r} has no datasource")
    uid = interpolate(uid, values)
    result = ctx.run(
        uid,
        {"refId": "A", "rawSql": sql, "format": "table", "rawQuery": True, "editorMode": "code"},
        time_from,
        time_to,
    )
    if result.error:
        raise CheckError(f"variable {name!r} failed: {result.error}")
    if not result.columns or not result.columns[0]:
        raise CheckError(f"variable {name!r} returned no rows ({_excerpt(sql)})")
    column = result.columns[0]
    if "__value" in result.fields:
        column = result.columns[result.fields.index("__value")]
    return [_stringify(v) for v in column if v is not None]


def _window(ctx: _Context, values: dict, selection: list[str]) -> tuple[int, int]:
    """The time range of a run: fixed, the selection's window, or the span of all experiments."""
    if ctx.fixed is not None:
        return ctx.fixed
    for needed in ("pg", "pg_schema"):
        if needed not in values:
            raise CheckError(f"the time range needs the variable {needed!r}, which is not declared")
    schema = str(values["pg_schema"])
    sql = f"SELECT MIN(start_time) AS t0, MAX(end_time) AS t1 FROM {schema}.experiment"  # noqa: S608
    if ctx.time_range == "window":
        quoted = ",".join("'" + e.replace("'", "''") + "'" for e in selection)
        sql += f" WHERE experiment_id IN ({quoted})"
    result = ctx.run(
        str(values["pg"]),
        {"refId": "A", "rawSql": sql, "format": "table", "rawQuery": True, "editorMode": "code"},
        0,
        to_epoch_ms(datetime.now(UTC)),
    )
    if result.error:
        raise CheckError(f"reading the experiment windows failed: {result.error}")
    if len(result.columns) < 2 or not result.columns[0] or result.columns[0][0] is None:
        raise CheckError(f"no experiment window found for {selection or 'all experiments'}")
    start, end = int(result.columns[0][0]), int(result.columns[1][0])
    if end <= start:
        raise CheckError(f"the experiment window is empty ({format_instant(start)})")
    return start, end


def _resolve(
    ctx: _Context,
    doc: dict,
    *,
    selection: list[str] | None,
    forced: dict[str, str],
    discover: dict[str, list[str]] | None = None,
) -> tuple[dict[str, str | list[str]], tuple[int, int]]:
    """Variable values (and the run's time range) for one run of one dashboard.

    `selection` None is the discovery pass: the `experiment` variable is run like any other
    query variable and its options recorded in `discover`. In a real pass the selection is its
    value and the time range is computed as soon as a later query variable needs it.
    """
    values: dict[str, str | list[str]] = {}
    window: tuple[int, int] | None = None
    start_of_time = (0, to_epoch_ms(datetime.now(UTC)))
    for variable in _templating(doc):
        name = variable.get("name")
        kind = variable.get("type")
        if not name or kind == "adhoc":
            continue
        if name in forced:
            values[name] = forced[name]
            continue
        if name == SELECTION_VARIABLE and selection is not None:
            values[name] = list(selection) if variable.get("multi") else selection[0]
            continue
        if name in ctx.overrides:
            values[name] = _split_override(variable, ctx.overrides[name])
            continue
        if kind == "constant":
            values[name] = interpolate(str(variable.get("query", _current(variable) or "")), values)
        elif kind == "datasource":
            current = _current(variable)
            values[name] = current[0] if isinstance(current, list) else (current or "")
            if not values[name]:
                raise CheckError(f"datasource variable {name!r} has no default value")
        elif kind == "custom":
            options = [o.strip() for o in str(variable.get("query", "")).split(",") if o.strip()]
            if discover is not None:
                discover[name] = options
            current = _current(variable)
            chosen = current if current else (options[0] if options else "")
            values[name] = chosen
        elif kind == "query":
            if selection is None:
                time_from, time_to = start_of_time
            else:
                if window is None:
                    window = _window(ctx, values, selection)
                time_from, time_to = window
            options = _query_variable_options(ctx, variable, values, time_from, time_to)
            if discover is not None:
                discover[name] = options
            current = _current(variable)
            if variable.get("multi"):
                if isinstance(current, list) and set(current) <= set(options):
                    values[name] = current
                else:
                    values[name] = list(options)
            elif isinstance(current, str) and current in options:
                values[name] = current
            else:
                # a query variable that returns one row (windows, span_from ...) takes it
                values[name] = options[0]
        else:
            current = _current(variable)
            values[name] = current if current is not None else str(variable.get("query", ""))
    if selection is None:
        return values, start_of_time
    if window is None:
        window = _window(ctx, values, selection)
    return values, window


# -------------------------------------------------------------------------------- the run


def _interpolate_node(node: Any, values: dict) -> Any:
    if isinstance(node, str):
        return interpolate(node, values)
    if isinstance(node, dict):
        return {k: _interpolate_node(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_interpolate_node(v, values) for v in node]
    return node


def _annotation_target(entry: dict) -> dict:
    target = entry.get("target")
    if isinstance(target, dict):
        return {"refId": "Anno", **target}
    sql = entry.get("rawSql") or entry.get("rawQuery") or entry.get("query")
    if isinstance(sql, str) and sql.strip():
        return {"refId": "Anno", "rawSql": sql, "format": "table", "rawQuery": True}
    raise CheckError(f"annotation {entry.get('name')!r} has no query")


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _target_record(
    ctx: _Context,
    panel: dict,
    target: dict,
    values: dict,
    window: tuple[int, int],
) -> dict:
    ref = target.get("datasource")
    if ref is None or _ds_uid(ref) == "-- Mixed --":
        ref = panel.get("datasource")
    uid = _ds_uid(ref)
    if uid is None:
        raise CheckError(
            f"panel {panel.get('title')!r} target {target.get('refId')}: no datasource"
        )
    uid = interpolate(uid, values)
    body = {k: v for k, v in _interpolate_node(target, values).items() if k != "datasource"}
    result = ctx.run(uid, body, *window)
    return {
        "ref_id": str(target.get("refId") or "A"),
        "datasource": ctx.client.datasource_kind(uid),
        "rows": 0 if result.error else result.rows,
        "fields": [] if result.error else list(result.fields),
        "error": result.error,
    }


def _run_dashboard(
    ctx: _Context,
    doc: dict,
    *,
    selection: list[str],
    sweep: dict[str, str],
    allow_empty: set[str],
) -> dict:
    values, window = _resolve(ctx, doc, selection=selection, forced=sweep)
    panels: dict[int, dict] = {}
    for panel, target in panel_targets(doc):
        if target.get("hide"):
            continue
        entry = panels.setdefault(
            panel["id"],
            {
                "panel_id": panel["id"],
                "title": panel.get("title", ""),
                "type": panel.get("type", ""),
                "empty_allowed": panel.get("title", "") in allow_empty,
                "targets": [],
            },
        )
        entry["targets"].append(_target_record(ctx, panel, target, values, window))
    annotations = []
    for entry in _annotation_entries(doc):
        if entry.get("enable") is False:
            continue
        target = _annotation_target(entry)
        uid = interpolate(_ds_uid(entry.get("datasource")) or "", values)
        record = _target_record(
            ctx,
            {"title": entry.get("name")},
            {**target, "datasource": {"uid": uid}},
            values,
            window,
        )
        annotations.append(
            {
                "name": entry.get("name", ""),
                "datasource": record["datasource"],
                "rows": record["rows"],
                "error": record["error"],
            }
        )
    for entry in panels.values():
        entry["targets"].sort(key=lambda t: t["ref_id"])
    return {
        "dashboard_uid": doc["uid"],
        "dashboard_title": doc.get("title", ""),
        "selection": sorted(selection),
        "sweep": dict(sweep),
        "time_from": format_instant(window[0]),
        "time_to": format_instant(window[1]),
        "panels": [panels[i] for i in sorted(panels)],
        "annotations": sorted(annotations, key=lambda a: a["name"]),
    }


def parse_time_range(text: str) -> tuple[str, tuple[int, int] | None]:
    """`window`, `span` or `FROM,TO` -> (mode, fixed range in epoch ms or None)."""
    if text in ("window", "span"):
        return text, None
    parts = text.split(",")
    if len(parts) != 2:
        raise CheckError(f"--time-range must be window, span or FROM,TO (got {text!r})")
    start, end = to_epoch_ms(parts[0]), to_epoch_ms(parts[1])
    if end <= start:
        raise CheckError(f"--time-range ends before it starts: {text!r}")
    return "fixed", (start, end)


def run_check(
    client: Any,
    dashboards: list[tuple[Path, dict]],
    *,
    experiments: list[str] | None = None,
    overrides: dict[str, str] | None = None,
    sweep: list[str] | None = None,
    time_range: str = "window",
    allow_empty: Iterable[str] = (),
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Run every selection of every dashboard against Grafana; return the summary.

    `dashboards` is `[(path, parsed dashboard)]`. The summary follows
    `contracts/dashboard_check.schema.json`. Raises `CheckError` for anything that makes the
    run meaningless (unknown experiment, a variable query that fails, a bad override).
    """
    started = time.monotonic()
    overrides = dict(overrides or {})
    sweep = list(sweep or [])
    allow = set(allow_empty)
    mode, fixed = parse_time_range(time_range)
    ctx = _Context(client, overrides, mode, fixed)

    declared = {v.get("name") for _, doc in dashboards for v in _templating(doc)}
    for name in sorted(set(overrides) | set(sweep)):
        if name not in declared:
            raise CheckError(f"variable {name!r} is declared in none of the dashboards")

    runs: list[dict] = []
    for _path, doc in dashboards:
        discovered: dict[str, list[str]] = {}
        _resolve(ctx, doc, selection=None, forced={}, discover=discovered)
        variable_names = {v.get("name"): v for v in _templating(doc)}
        if SELECTION_VARIABLE not in variable_names:
            raise CheckError(f"dashboard {doc.get('uid')!r} has no {SELECTION_VARIABLE!r} variable")
        available = discovered.get(SELECTION_VARIABLE, [])
        chosen = sorted(set(experiments)) if experiments else sorted(available)
        unknown = [e for e in chosen if e not in available]
        if unknown:
            raise CheckError(f"unknown experiment {unknown[0]!r}; known: {', '.join(available)}")
        selections = [[e] for e in chosen]
        if variable_names[SELECTION_VARIABLE].get("multi") and len(chosen) > 1:
            selections.append(list(chosen))

        swept = [name for name in sweep if name in variable_names]
        for name in swept:
            if not discovered.get(name):
                raise CheckError(f"cannot sweep {name!r}: it has no list of values")
        combos = (
            [
                dict(zip(swept, combo, strict=True))
                for combo in product(*(discovered[n] for n in swept))
            ]
            if swept
            else [{}]
        )
        for selection in selections:
            for combo in combos:
                runs.append(
                    _run_dashboard(ctx, doc, selection=selection, sweep=combo, allow_empty=allow)
                )

    runs.sort(
        key=lambda r: (
            r["dashboard_uid"],
            r["selection"],
            sorted(r["sweep"].items()),
            r["time_from"],
        )
    )
    totals = {
        "runs": len(runs),
        "panel_targets": 0,
        "with_rows": 0,
        "empty": 0,
        "empty_allowed": 0,
        "errors": 0,
        "annotation_errors": 0,
    }
    for run in runs:
        for panel in run["panels"]:
            for target in panel["targets"]:
                totals["panel_targets"] += 1
                if target["error"]:
                    totals["errors"] += 1
                elif target["rows"] > 0:
                    totals["with_rows"] += 1
                elif panel["empty_allowed"]:
                    totals["empty_allowed"] += 1
                else:
                    totals["empty"] += 1
        totals["annotation_errors"] += sum(1 for a in run["annotations"] if a["error"])
    return {
        "schema_version": 1,
        "grafana_version": client.version(),
        "source": {
            "dashboards": [_repo_relative(p, repo_root) for p, _ in dashboards],
            "overrides": overrides,
            "sweep": sweep,
            "time_range": mode,
            "allow_empty": sorted(allow),
        },
        "runs": runs,
        "totals": totals,
        "timing": {"seconds": round(time.monotonic() - started, 3), "queries": ctx.queries},
    }


def exit_code(summary: dict) -> int:
    """0 when every panel target had rows and nothing failed; 1 otherwise."""
    totals = summary["totals"]
    return 1 if totals["errors"] or totals["empty"] or totals["annotation_errors"] else 0


def failures(summary: dict) -> list[str]:
    """One line per failing target or annotation, naming the dashboard, selection and panel."""
    lines: list[str] = []
    for run in summary["runs"]:
        where = f"{run['dashboard_uid']} [{', '.join(run['selection'])}]"
        if run["sweep"]:
            where += " " + ", ".join(f"{k}={v}" for k, v in sorted(run["sweep"].items()))
        for panel in run["panels"]:
            for target in panel["targets"]:
                name = f"panel {panel['panel_id']} {panel['title']!r}"
                head = f"{where} {name} target {target['ref_id']}"
                if target["error"]:
                    lines.append(f"{head}: error: {target['error']}")
                elif target["rows"] == 0 and not panel["empty_allowed"]:
                    lines.append(f"{head}: no rows")
        for annotation in run["annotations"]:
            if annotation["error"]:
                lines.append(
                    f"{where} annotation {annotation['name']!r}: error: {annotation['error']}"
                )
    return lines


ClientFactory = Callable[[str, str, str], Any]
