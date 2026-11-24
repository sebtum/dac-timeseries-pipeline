"""Unit tests for `python -m scripts.clean` and its InfluxDB layer, with a fake gateway.

No InfluxDB here: `FakeGateway` stores the lines the run writes and answers the read-back from
them, so every exit code (0, 2, 3, 4, 70) and the line protocol can be checked without a server.
The live run is `tests/e2e/test_clean_cli.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pyarrow as pa
import pytest

from pipeline.cleaning import Interval, RawPoint, Verdict
from pipeline.cleaning_influx import (
    PROCESSED_TABLE,
    QUALITY_INTERVALS_TABLE,
    STATE_INTERVALS_TABLE,
    CleaningGateway,
    processed_line,
    quality_interval_line,
    series_lines,
    state_line,
    window_params,
)
from pipeline.cleaning_policy import POLICY_VERSION
from pipeline.ingest_influx import DatabaseCheckFailed
from pipeline.profiling_sql import QueryFailed
from scripts import clean

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "cleaning_summary.schema.json").read_text(encoding="utf-8")
)

START_NS = 1_777_881_600 * 10**9  # 2026-05-04T08:00:00Z
NS = 10**9
VOLTAGE = ("hydrolyzer", "voltage")
PROCESS_STATE = ("plant", "process_state")
ENV = {"INFLUX_HOST": "http://influx.invalid", "INFLUX_TOKEN": "token"}
WRITTEN_TABLES = {PROCESSED_TABLE, STATE_INTERVALS_TABLE, QUALITY_INTERVALS_TABLE}


def voltage_points() -> list[RawPoint]:
    """60 readings, 1 Hz, alternating 99.925 / 100.075, a spike of 140 at +30 s."""
    points = []
    for k in range(60):
        value = 140.0 if k == 30 else (100.075 if k % 2 == 0 else 99.925)
        points.append(RawPoint(START_NS + k * NS, value, "GOOD"))
    return points


def state_points() -> list[RawPoint]:
    return [
        RawPoint(START_NS, "STARTUP", "GOOD"),
        RawPoint(START_NS + 20 * NS, "WARMUP", "GOOD"),
    ]


class FakeGateway:
    """In-memory stand-in for `CleaningGateway`; reads back what it was asked to write."""

    def __init__(
        self,
        *,
        write_error: Exception | None = None,
        pull_error: Exception | None = None,
        short_series: str | None = None,
        extra_with_value: str | None = None,
        raw_shift: bool = False,
        tables: set[str] | None = None,
        extra_series: tuple[str, str] | None = None,
    ) -> None:
        self.queries = 0
        self.write_error = write_error
        self.pull_error = pull_error
        self.short_series = short_series
        self.extra_with_value = extra_with_value
        self.raw_shift = raw_shift
        self._tables = {"readings_numeric", "readings_state"} if tables is None else tables
        self.extra_series = extra_series
        self.write_calls = 0
        self.lines: list[str] = []
        self.closed = False
        self._raw_calls = 0

    def tables(self) -> set[str]:
        self.queries += 1
        return self._tables | {line.split(",", 1)[0] for line in self.lines}

    def series_keys(self, table, experiment_id, start, end):
        self.queries += 1
        if table == "readings_numeric":
            keys = [VOLTAGE]
            if self.extra_series is not None:
                keys.append(self.extra_series)
            return keys
        return [PROCESS_STATE]

    def pull(self, table, experiment_id, source, signal, start, end):
        self.queries += 1
        if self.pull_error is not None:
            raise self.pull_error
        return voltage_points() if signal == "voltage" else state_points()

    def conflict_instants(self, experiment_id, start, end):
        self.queries += 1
        return set()

    def count_raw(self, table, experiment_id, start, end):
        self.queries += 1
        self._raw_calls += 1
        shift = 1 if self.raw_shift and self._raw_calls > 2 else 0
        if table == "readings_numeric":
            return {VOLTAGE: 60 + shift}
        if table == "readings_state":
            return {PROCESS_STATE: 2}
        return {}

    def count_processed(self, table, experiment_id, start, end, policy_version):
        self.queries += 1
        counts: dict[tuple[str, str], list[int]] = {}
        for line in self.lines:
            head, fields, _time = line.rsplit(" ", 2)
            measurement, *tag_parts = head.split(",")
            if measurement != table:
                continue
            tags = dict(part.split("=", 1) for part in tag_parts)
            entry = counts.setdefault((tags["source"], tags["signal"]), [0, 0])
            entry[0] += 1
            entry[1] += any(f.startswith("value=") for f in fields.split(","))
        out = {}
        for pair, (rows, with_value) in counts.items():
            if self.short_series == pair[1]:
                rows -= 1
            if self.extra_with_value == pair[1]:
                with_value += 1
            out[pair] = (rows, with_value)
        return out

    def write(self, body: str) -> None:
        self.write_calls += 1
        if self.write_error is not None:
            raise self.write_error
        self.lines.extend(body.split("\n"))

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def experiments(tmp_path) -> Path:
    path = tmp_path / "experiments.json"
    path.write_text(
        json.dumps(
            [
                {
                    "experiment_id": "EXP_001",
                    "start_time": "2026-05-04T08:00:00Z",
                    "end_time": "2026-05-04T08:01:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def report_dir(tmp_path) -> Path:
    path = tmp_path / "report"
    path.mkdir()
    return path


def run_clean(experiments, report_dir, gateway=None, **deps):
    gateway = gateway or FakeGateway()
    sleeps: list[float] = []
    settings = {
        "list_databases": lambda host, token: ["_internal", "dac_raw"],
        "gateway_factory": lambda host, token, database: gateway,
        "env": ENV,
        "sleep": sleeps.append,
    }
    settings.update(deps)
    config = clean.Config(database="dac_raw", experiments_path=experiments, report_dir=report_dir)
    code = clean.run(config, clean.Deps(**settings))
    return code, gateway, sleeps


def summary_of(report_dir: Path) -> dict:
    return json.loads((report_dir / "cleaning_summary.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------ exit 0


def test_balanced_run_exits_0_and_writes_both_outputs(experiments, report_dir):
    code, gateway, _ = run_clean(experiments, report_dir)
    assert code == 0
    summary = summary_of(report_dir)
    jsonschema.Draft202012Validator(SCHEMA).validate(summary)
    assert summary["reconciliation"] == {
        "balanced": True,
        "series_checked": 2,
        "unbalanced": [],
        "raw_unchanged": True,
    }
    assert summary["totals"]["raw_points"] == 62
    assert summary["totals"]["processed_points"] == 62
    assert summary["timing"]["points_written"] == len(gateway.lines)
    assert "Cleaning report" in (report_dir / "cleaning_report.md").read_text(encoding="utf-8")
    assert gateway.closed


def test_run_writes_only_the_three_processed_tables(experiments, report_dir):
    _code, gateway, _ = run_clean(experiments, report_dir)
    written = {line.split(",", 1)[0] for line in gateway.lines}
    assert written == {PROCESSED_TABLE, STATE_INTERVALS_TABLE}  # no gap or flatline in the data
    assert written <= WRITTEN_TABLES


def test_one_processed_row_per_reading_and_the_spike_is_excluded(experiments, report_dir):
    _code, gateway, _ = run_clean(experiments, report_dir)
    voltage = [
        ln for ln in gateway.lines if ln.startswith(f"{PROCESSED_TABLE},") and "voltage" in ln
    ]
    assert len(voltage) == 60
    spike = next(ln for ln in voltage if ln.endswith(f" {START_NS + 30 * NS}"))
    assert 'verdict="excluded"' in spike and 'reason="spike"' in spike
    assert ",value=" not in spike and " value=" not in spike


# ------------------------------------------------------------------------------ exit 3


def test_exit_3_write_fails_and_writes_no_summary(experiments, report_dir):
    """S3.21: a gateway that fails on a write."""
    gateway = FakeGateway(write_error=RuntimeError("write refused"))
    code, _, sleeps = run_clean(experiments, report_dir, gateway)
    assert code == 3
    assert list(report_dir.iterdir()) == []
    assert gateway.write_calls == 1  # a refused line is not retried
    assert sleeps == []
    assert gateway.closed


def test_exit_3_connection_error_is_retried_then_fails(experiments, report_dir):
    gateway = FakeGateway(write_error=ConnectionError("reset"))
    code, _, sleeps = run_clean(experiments, report_dir, gateway)
    assert code == 3
    assert gateway.write_calls == 4
    assert sleeps == [1, 2, 4]
    assert list(report_dir.iterdir()) == []


def test_exit_3_query_fails_and_writes_nothing(experiments, report_dir):
    gateway = FakeGateway(pull_error=QueryFailed("pull", RuntimeError("flight error")))
    code, _, _ = run_clean(experiments, report_dir, gateway)
    assert code == 3
    assert list(report_dir.iterdir()) == []
    assert gateway.write_calls == 0


# ------------------------------------------------------------------------------ exit 4


def test_exit_4_read_back_one_short_for_one_series(experiments, report_dir):
    """S3.22: the read-back finds one processed point fewer than was written for one series."""
    gateway = FakeGateway(short_series="voltage")
    code, _, _ = run_clean(experiments, report_dir, gateway)
    assert code == 4
    summary = summary_of(report_dir)
    jsonschema.Draft202012Validator(SCHEMA).validate(summary)
    assert summary["reconciliation"]["balanced"] is False
    assert summary["reconciliation"]["unbalanced"] == [
        {
            "experiment_id": "EXP_001",
            "source": "hydrolyzer",
            "signal": "voltage",
            "raw_points": 60,
            "processed_points": 59,
        }
    ]
    assert (report_dir / "cleaning_report.md").exists()


def test_exit_4_a_row_carries_a_value_it_should_not(experiments, report_dir):
    """A stale value (Core keeps an old field when a rewrite omits it) breaks the balance."""
    gateway = FakeGateway(extra_with_value="process_state")
    code, _, _ = run_clean(experiments, report_dir, gateway)
    assert code == 4
    unbalanced = summary_of(report_dir)["reconciliation"]["unbalanced"]
    assert [u["signal"] for u in unbalanced] == ["process_state"]


def test_exit_4_when_the_raw_tables_moved_during_the_run(experiments, report_dir):
    gateway = FakeGateway(raw_shift=True)
    code, _, _ = run_clean(experiments, report_dir, gateway)
    assert code == 4
    reconciliation = summary_of(report_dir)["reconciliation"]
    assert reconciliation["raw_unchanged"] is False
    assert reconciliation["balanced"] is True


# ------------------------------------------------------------------------------ exit 2


def test_exit_2_database_missing_is_not_created(experiments, report_dir):
    built = []
    code, _, _ = run_clean(
        experiments,
        report_dir,
        list_databases=lambda host, token: ["_internal"],
        gateway_factory=lambda *args: built.append(args),
    )
    assert code == 2
    assert built == []  # no gateway, so nothing could write (and so create) the database
    assert list(report_dir.iterdir()) == []


def test_exit_2_experiments_file_unreadable(tmp_path, report_dir):
    code, gateway, _ = run_clean(tmp_path / "missing.json", report_dir)
    assert code == 2
    assert gateway.write_calls == 0
    assert list(report_dir.iterdir()) == []


def test_exit_2_experiments_file_is_not_json(tmp_path, report_dir):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code, _, _ = run_clean(bad, report_dir)
    assert code == 2


def test_exit_2_raw_tables_missing(experiments, report_dir):
    gateway = FakeGateway(tables=set())
    code, _, _ = run_clean(experiments, report_dir, gateway)
    assert code == 2
    assert gateway.write_calls == 0
    assert list(report_dir.iterdir()) == []


def test_exit_2_a_series_the_policy_does_not_know(experiments, report_dir):
    gateway = FakeGateway(extra_series=("plant", "mystery"))
    code, _, _ = run_clean(experiments, report_dir, gateway)
    assert code == 2
    assert gateway.write_calls == 0  # decided before the first write
    assert list(report_dir.iterdir()) == []


def test_exit_2_influx_not_configured(experiments, report_dir):
    code, _, _ = run_clean(experiments, report_dir, env={"INFLUX_HOST": "", "INFLUX_TOKEN": ""})
    assert code == 2


def test_exit_2_influx_unreachable(experiments, report_dir):
    def unreachable(host, token):
        raise DatabaseCheckFailed("unreachable", "no route")

    code, _, _ = run_clean(experiments, report_dir, list_databases=unreachable)
    assert code == 2
    assert list(report_dir.iterdir()) == []


def test_main_turns_a_bug_into_exit_70(experiments, report_dir, monkeypatch):
    def boom(config, deps=None):
        raise RuntimeError("bug")

    monkeypatch.setattr(clean, "run", boom)
    assert clean.main(["--experiments", str(experiments), "--report-dir", str(report_dir)]) == 70


def test_parse_args_defaults_and_overrides(tmp_path):
    default = clean.parse_args([])
    assert default.database == "dac_raw"
    assert default.experiments_path == REPO_ROOT / "data" / "raw" / "experiments.json"
    assert default.report_dir == REPO_ROOT / "reports"
    chosen = clean.parse_args(
        [
            "--database",
            "x",
            "--experiments",
            str(tmp_path / "e.json"),
            "--report-dir",
            str(tmp_path),
        ]
    )
    assert (chosen.database, chosen.experiments_path, chosen.report_dir) == (
        "x",
        tmp_path / "e.json",
        tmp_path,
    )


# ------------------------------------------------------------------------------ line protocol

ACCEPTED = Verdict(reason="", flags=())
EXCLUDED_SPIKE = Verdict(reason="spike", flags=("spike", "outside_typical_range"))
NO_VALUE = Verdict(reason="no_value", flags=("no_value",))
TAGS = f"experiment_id=EXP_001,source=hydrolyzer,signal=voltage,policy_version={POLICY_VERSION}"


def test_accepted_row_carries_raw_value_value_and_empty_reason_and_flags():
    line = processed_line(
        "EXP_001", VOLTAGE, POLICY_VERSION, RawPoint(START_NS, 100.73, "GOOD"), ACCEPTED
    )
    assert line == (
        f"{PROCESSED_TABLE},{TAGS} value_raw=100.73,value=100.73,"
        f'quality="GOOD",verdict="accepted",reason="",flags="" {START_NS}'
    )


def test_excluded_row_has_value_raw_but_no_value():
    line = processed_line(
        "EXP_001", VOLTAGE, POLICY_VERSION, RawPoint(START_NS, 140.0, "BAD"), EXCLUDED_SPIKE
    )
    assert "value_raw=140.0," in line
    assert ",value=" not in line
    assert 'verdict="excluded",reason="spike",flags="spike,outside_typical_range"' in line
    assert 'quality="BAD"' in line


def test_a_point_without_a_value_has_neither_field():
    line = processed_line(
        "EXP_001", VOLTAGE, POLICY_VERSION, RawPoint(START_NS, None, "GOOD"), NO_VALUE
    )
    assert "value_raw" not in line and "value=" not in line
    assert 'reason="no_value"' in line


def test_whole_numbers_are_written_as_floats_not_integers():
    line = processed_line(
        "EXP_001", VOLTAGE, POLICY_VERSION, RawPoint(START_NS, 150, "GOOD"), ACCEPTED
    )
    assert "value_raw=150.0,value=150.0," in line


def test_tags_and_text_are_escaped():
    line = processed_line(
        "EXP 1,a=b",
        ("src x", "sig,y"),
        "v 1",
        RawPoint(START_NS, 1.0, 'Q"UOTE'),
        ACCEPTED,
    )
    assert line.startswith(
        r"readings_processed,experiment_id=EXP\ 1\,a\=b,source=src\ x,signal=sig\,y,"
        r"policy_version=v\ 1 "
    )
    assert 'quality="Q\\"UOTE"' in line


def test_state_row_has_text_values_interval_end_and_seconds():
    span = Interval(START_NS, START_NS + 120 * NS, 1)
    line = state_line(
        "EXP_001",
        PROCESS_STATE,
        POLICY_VERSION,
        RawPoint(START_NS, "STARTUP", "GOOD"),
        ACCEPTED,
        span,
    )
    assert line.startswith(f"{STATE_INTERVALS_TABLE},experiment_id=EXP_001,source=plant,")
    assert 'value_raw="STARTUP",value="STARTUP",' in line
    assert f"end_ns={START_NS + 120 * NS}i,seconds=120.0 {START_NS}" in line


def test_excluded_state_row_keeps_its_interval_and_has_no_value():
    span = Interval(START_NS, START_NS + 60 * NS, 1)
    verdict = Verdict(reason="unknown_state", flags=("unknown_state",))
    line = state_line(
        "EXP_001",
        PROCESS_STATE,
        POLICY_VERSION,
        RawPoint(START_NS, "WARMUP", "GOOD"),
        verdict,
        span,
    )
    assert 'value_raw="WARMUP",' in line
    assert ",value=" not in line
    assert "end_ns=" in line and "seconds=60.0" in line


def test_quality_interval_row_has_kind_tag_and_the_interval_fields():
    line = quality_interval_line(
        "EXP_001", VOLTAGE, POLICY_VERSION, "gap", Interval(START_NS, START_NS + 11 * NS)
    )
    assert line == (
        f"{QUALITY_INTERVALS_TABLE},{TAGS},kind=gap "
        f"end_ns={START_NS + 11 * NS}i,seconds=11.0,points=0i {START_NS}"
    )


def test_series_lines_order_rows_then_gaps_then_flatlines():
    points = [RawPoint(START_NS + k * NS, 1.0, "GOOD") for k in range(2)]
    gap = Interval(START_NS, START_NS + 11 * NS)
    flat = Interval(START_NS, START_NS + NS, 2)
    lines = series_lines(
        "EXP_001", VOLTAGE, POLICY_VERSION, points, [ACCEPTED, ACCEPTED], None, [gap], [flat]
    )
    assert [ln.split(",", 1)[0] for ln in lines] == [PROCESSED_TABLE] * 2 + [
        QUALITY_INTERVALS_TABLE
    ] * 2
    assert "kind=gap" in lines[2] and "kind=flatline" in lines[3]


def test_series_lines_for_a_state_series_use_state_intervals():
    points = state_points()
    spans = [
        Interval(START_NS, START_NS + 20 * NS, 1),
        Interval(START_NS + 20 * NS, START_NS + 60 * NS, 1),
    ]
    lines = series_lines(
        "EXP_001", PROCESS_STATE, POLICY_VERSION, points, [ACCEPTED, ACCEPTED], spans, None, None
    )
    assert [ln.split(",", 1)[0] for ln in lines] == [STATE_INTERVALS_TABLE] * 2


# ------------------------------------------------------------------------------ the gateway


class FakeClient:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def query(self, sql, language, query_parameters):
        self.calls.append((sql, query_parameters))
        if self.error is not None:
            raise self.error
        return self.result(sql) if callable(self.result) else self.result


def gateway_with(client: FakeClient) -> CleaningGateway:
    gateway = object.__new__(CleaningGateway)
    gateway._client = client
    gateway.queries = 0
    return gateway


def test_window_params_are_utc_and_half_open_bounds():
    start = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
    end = datetime(2026, 5, 4, 8, 10, tzinfo=UTC)
    assert window_params("EXP_001", start, end) == {
        "exp": "EXP_001",
        "start": "2026-05-04T08:00:00+00:00",
        "end": "2026-05-04T08:10:00+00:00",
    }


def test_a_failing_query_becomes_query_failed_and_is_counted():
    gateway = gateway_with(FakeClient(error=RuntimeError("down")))
    with pytest.raises(QueryFailed):
        gateway.tables()
    assert gateway.queries == 1


def test_pull_returns_raw_points_with_missing_values_as_none():
    table = pa.table(
        {
            "time": pa.array([START_NS, START_NS + NS], pa.timestamp("ns")),
            "value": pa.array([1.5, None], pa.float64()),
            "quality": ["GOOD", "BAD"],
        }
    )
    client = FakeClient(table)
    gateway = gateway_with(client)
    start = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
    points = gateway.pull("readings_numeric", "EXP_001", "hydrolyzer", "voltage", start, start)
    assert points == [RawPoint(START_NS, 1.5, "GOOD"), RawPoint(START_NS + NS, None, "BAD")]
    sql, params = client.calls[0]
    assert "ORDER BY time" in sql and "time >= $start AND time < $end" in sql
    assert params["src"] == "hydrolyzer" and params["sig"] == "voltage"


def test_count_processed_without_a_value_column_counts_zero_with_value():
    def answer(sql):
        if "information_schema.columns" in sql:
            return pa.table({"column_name": pa.array([], pa.string())})
        assert "COUNT(value)" not in sql
        return pa.table({"source": ["plant"], "signal": ["x"], "n": [3], "v": [0]})

    gateway = gateway_with(FakeClient(answer))
    start = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
    counts = gateway.count_processed(STATE_INTERVALS_TABLE, "EXP_001", start, start, "m3-v1")
    assert counts == {("plant", "x"): (3, 0)}


def test_count_processed_with_a_value_column_counts_rows_that_carry_one():
    def answer(sql):
        if "information_schema.columns" in sql:
            return pa.table({"column_name": ["value"]})
        assert "COUNT(value) AS v" in sql and "policy_version = $pv" in sql
        return pa.table({"source": ["plant"], "signal": ["x"], "n": [3], "v": [2]})

    gateway = gateway_with(FakeClient(answer))
    start = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
    counts = gateway.count_processed(PROCESSED_TABLE, "EXP_001", start, start, "m3-v1")
    assert counts == {("plant", "x"): (3, 2)}
