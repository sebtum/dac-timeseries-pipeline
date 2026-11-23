"""Retry rules and the exit codes of a whole run, against a stand-in for InfluxDB.

S2.23 (wrong fingerprint), S2.24 (missing database), S2.26 (retry, then stop) and S2.27
(summary matches the contract, including for refused runs). The real-database halves of
S2.23-S2.25 are in `tests/e2e/test_ingest_cli.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import jsonschema
import pytest
import urllib3

from pipeline.ingest_influx import DatabaseCheckFailed, WriteFailed, is_retryable, send_with_retry
from scripts.ingest import Config, Deps, run

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "ingest"
SCHEMA = json.loads((REPO_ROOT / "contracts" / "ingest_summary.schema.json").read_text("utf-8"))
EXAMPLE = REPO_ROOT / "contracts" / "examples" / "ingest_summary.example.json"
ENV = {"INFLUX_HOST": "http://stand-in:8181", "INFLUX_TOKEN": "token"}


class Refused(Exception):
    """Stands in for the client's ApiException: carries an HTTP status."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


def connection_error() -> Exception:
    return urllib3.exceptions.NewConnectionError(None, "connection refused")


# ---- retry rules (decision 11) -------------------------------------------------------------


def test_connection_errors_are_retried_three_times_then_the_batch_fails():  # S2.26
    calls, sleeps = [], []

    def always_down(body: str) -> None:
        calls.append(body)
        raise connection_error()

    with pytest.raises(WriteFailed) as caught:
        send_with_retry(always_down, "lines", sleep=sleeps.append)
    assert len(calls) == 4
    assert sleeps == [1, 2, 4]
    assert caught.value.attempts == 4


def test_a_server_error_is_retried_and_success_after_failures_returns():
    outcomes = [Refused(503), Refused(500), None]
    sleeps = []

    def flaky(body: str) -> None:
        result = outcomes.pop(0)
        if result:
            raise result

    assert send_with_retry(flaky, "lines", sleep=sleeps.append) == 3
    assert sleeps == [1, 2]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_a_refused_line_fails_at_once_because_resending_cannot_help(status):
    calls = []

    def refused(body: str) -> None:
        calls.append(body)
        raise Refused(status)

    with pytest.raises(WriteFailed) as caught:
        send_with_retry(refused, "lines", sleep=lambda s: pytest.fail("must not wait"))
    assert len(calls) == 1 and caught.value.attempts == 1


def test_retry_classification():
    assert is_retryable(connection_error())
    assert is_retryable(ConnectionResetError())
    assert is_retryable(TimeoutError())
    assert is_retryable(Refused(502))
    assert not is_retryable(Refused(400))
    assert not is_retryable(ValueError("bug"))


# ---- a stand-in database -------------------------------------------------------------------

_LINE = re.compile(
    r"^(readings_numeric|readings_state),experiment_id=([^,]+),source=([^,]+),signal=(\S+) "
)


class StandIn:
    """Records writes and answers the count-back from what was written."""

    def __init__(self, *, fail_with=None, undercount=False):
        self.bodies: list[str] = []
        self.fail_with = fail_with
        self.undercount = undercount
        self.closed = False

    def write(self, body: str) -> None:
        if self.fail_with:
            raise self.fail_with()
        self.bodies.append(body)

    def count_points(self, table, experiment_id, first, last):
        counts: dict[tuple[str, str], int] = {}
        for body in self.bodies:
            for line in body.split("\n"):
                match = _LINE.match(line)
                if match and match[1] == table and match[2] == experiment_id:
                    key = (match[3], match[4])
                    counts[key] = counts.get(key, 0) + 1
        if self.undercount and counts:
            self.undercount = False  # lose exactly one point, once
            counts[sorted(counts)[0]] -= 1
        return counts

    def close(self) -> None:
        self.closed = True


def deps_for(stand_in: StandIn, *, databases=("dac_raw",), sleeps=None, chunk_size=7) -> Deps:
    return Deps(
        list_databases=lambda host, token: list(databases),
        gateway_factory=lambda host, token, database: stand_in,
        sleep=(sleeps if sleeps is not None else []).append,
        chunk_size=chunk_size,  # small, so the external sort really spills to disk
        env=ENV,
    )


def fixture_config(tmp_path: Path, **overrides) -> Config:
    settings = {
        "csv_path": FIXTURES / "slice.csv",
        "experiments_path": FIXTURES / "experiments.json",
        "sha256_path": FIXTURES / "slice.sha256",
        "database": "dac_raw",
        "report_dir": tmp_path / "out",
        "batch_size": 10_000,
    }
    settings.update(overrides)
    return Config(**settings)


def read_summary(config: Config) -> dict:
    summary = json.loads((config.report_dir / "ingest_summary.json").read_text("utf-8"))
    jsonschema.validate(summary, SCHEMA)  # S2.27, whatever the outcome
    return summary


# ---- the whole run, with a stand-in ----------------------------------------------------------


def test_fixture_run_balances_and_exits_with_findings(tmp_path):  # S2.21 numbers, by hand
    config = fixture_config(tmp_path)
    stand_in = StandIn()
    assert run(config, deps_for(stand_in)) == 1
    summary = read_summary(config)
    assert summary["status"] == "completed_with_findings"
    assert summary["totals"] == {
        "csv_rows": 36,
        "saved": 21,
        "exact_copies": 1,
        "conflict_losers": 6,
        "rejected": 8,
        "balanced": True,
    }
    assert all(s["balanced"] for s in summary["series"])
    assert summary["conflicts_written"] == 6
    assert stand_in.closed


def test_the_external_sort_chunk_size_does_not_change_the_result(tmp_path):
    results = []
    for chunk_size in (3, 7, 50_000):
        config = fixture_config(tmp_path / str(chunk_size))
        run(config, deps_for(StandIn(), chunk_size=chunk_size))
        summary = read_summary(config)
        for key in ("started_at", "duration_s", "rows_per_second"):
            summary["timing"].pop(key)
        results.append(json.dumps(summary, sort_keys=True))
    assert len(set(results)) == 1


def test_batches_follow_batch_size(tmp_path):
    config = fixture_config(tmp_path, batch_size=10)
    stand_in = StandIn()
    run(config, deps_for(stand_in))
    assert len(stand_in.bodies) == 3  # 27 lines = 21 readings + 6 conflicts
    assert read_summary(config)["timing"]["batches"] == 3


def test_a_write_that_never_works_exits_3_after_four_tries(tmp_path):  # S2.26
    config = fixture_config(tmp_path)
    calls = []

    class Down(StandIn):
        def write(self, body):
            calls.append(body)
            raise connection_error()

    sleeps: list[float] = []
    assert run(config, deps_for(Down(), sleeps=sleeps)) == 3
    assert len(calls) == 4 and sleeps == [1, 2, 4]
    summary = read_summary(config)
    assert summary["status"] == "write_failed" and summary["exit_code"] == 3
    assert summary["totals"] is None and summary["series"] == []


def test_a_refused_line_exits_3_without_retry(tmp_path):  # S2.25, unit half
    config = fixture_config(tmp_path)
    sleeps: list[float] = []
    stand_in = StandIn(fail_with=lambda: Refused(400))
    assert run(config, deps_for(stand_in, sleeps=sleeps)) == 3
    assert sleeps == []


def test_counts_that_do_not_balance_exit_4(tmp_path):
    config = fixture_config(tmp_path)
    assert run(config, deps_for(StandIn(undercount=True))) == 4
    summary = read_summary(config)
    assert summary["status"] == "reconciliation_failed"
    assert summary["totals"]["balanced"] is False
    assert sum(1 for s in summary["series"] if not s["balanced"]) == 1


# ---- refusals: nothing written -----------------------------------------------------------------


def test_wrong_fingerprint_stops_before_any_write(tmp_path):  # S2.23
    csv_path = tmp_path / "slice.csv"
    data = bytearray((FIXTURES / "slice.csv").read_bytes())
    data[-3] ^= 1  # one changed byte
    csv_path.write_bytes(bytes(data))
    config = fixture_config(tmp_path, csv_path=csv_path)
    stand_in = StandIn()
    assert run(config, deps_for(stand_in)) == 2
    summary = read_summary(config)
    assert summary["status"] == "refused" and summary["refusal_reason"] == "checksum_mismatch"
    assert summary["input"]["checksum_ok"] is False
    assert stand_in.bodies == []
    assert (config.report_dir / "ingest_rejects.csv").read_text("utf-8").count("\n") == 1


def test_missing_database_is_refused_not_created(tmp_path):  # S2.24
    config = fixture_config(tmp_path, database="dac_missing")
    created = []
    deps = deps_for(StandIn(), databases=("dac_raw", "_internal"))
    deps.gateway_factory = lambda *args: created.append(args)
    assert run(config, deps) == 2
    assert read_summary(config)["refusal_reason"] == "database_missing"
    assert created == []


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("no_csv", "file_missing"),
        ("no_sha", "sha256_file_missing"),
        ("bad_sha", "sha256_file_invalid"),
        ("bad_header", "bad_header"),
        ("bad_experiments", "experiments_unreadable"),
        ("empty_csv", "bad_header"),
    ],
)
def test_other_refusals_are_named_and_still_produce_a_valid_summary(tmp_path, setup, reason):
    csv_path = tmp_path / "in.csv"
    sha_path = tmp_path / "in.sha256"
    experiments_path = tmp_path / "experiments.json"
    shutil.copy(FIXTURES / "experiments.json", experiments_path)
    body = (FIXTURES / "slice.csv").read_bytes()
    if setup == "bad_header":
        body = body.replace(b"timestamp,", b"time,", 1)
    if setup == "empty_csv":
        body = b""
    csv_path.write_bytes(body)
    sha_path.write_text(hashlib.sha256(body).hexdigest() + "  in.csv\n", encoding="utf-8")
    if setup == "no_csv":
        csv_path.unlink()
    if setup == "no_sha":
        sha_path.unlink()
    if setup == "bad_sha":
        sha_path.write_text("not a hash\n", encoding="utf-8")
    if setup == "bad_experiments":
        experiments_path.write_text("{not json", encoding="utf-8")
    config = fixture_config(
        tmp_path, csv_path=csv_path, sha256_path=sha_path, experiments_path=experiments_path
    )
    stand_in = StandIn()
    assert run(config, deps_for(stand_in)) == 2
    assert read_summary(config)["refusal_reason"] == reason
    assert stand_in.bodies == []


@pytest.mark.parametrize(
    ("raised", "reason"),
    [
        (DatabaseCheckFailed("unreachable", "no route"), "influx_unreachable"),
        (DatabaseCheckFailed("refused", "HTTP 401"), "influx_refused"),
    ],
)
def test_an_unreachable_or_refusing_server_is_a_refusal(tmp_path, raised, reason):
    config = fixture_config(tmp_path)
    deps = deps_for(StandIn())

    def fail(host, token):
        raise raised

    deps.list_databases = fail
    assert run(config, deps) == 2
    assert read_summary(config)["refusal_reason"] == reason


def test_missing_credentials_are_a_refusal(tmp_path):
    config = fixture_config(tmp_path)
    deps = deps_for(StandIn())
    deps.env = {}
    assert run(config, deps) == 2
    assert read_summary(config)["refusal_reason"] == "influx_not_configured"


def test_a_header_only_file_is_clean(tmp_path):
    csv_path = tmp_path / "empty.csv"
    body = b"timestamp,experiment_id,source,signal,value,quality\n"
    csv_path.write_bytes(body)
    sha_path = tmp_path / "empty.sha256"
    sha_path.write_text(hashlib.sha256(body).hexdigest() + "  empty.csv\n", encoding="utf-8")
    config = fixture_config(tmp_path, csv_path=csv_path, sha256_path=sha_path)
    assert run(config, deps_for(StandIn())) == 0
    summary = read_summary(config)
    assert summary["totals"]["csv_rows"] == 0 and summary["status"] == "ok"


# ---- the contract -------------------------------------------------------------------------------


def test_the_contract_example_validates():  # S2.27, the committed example
    jsonschema.validate(json.loads(EXAMPLE.read_text("utf-8")), SCHEMA)


def test_every_reject_reason_the_code_can_emit_is_in_the_contract():
    from pipeline.ingest import REJECT_REASONS

    allowed = set(SCHEMA["properties"]["rejects_by_reason"]["propertyNames"]["enum"])
    assert set(REJECT_REASONS) == allowed


def test_rejects_file_lists_every_rejected_row_with_its_number_and_reason(tmp_path):  # S2.9
    config = fixture_config(tmp_path)
    run(config, deps_for(StandIn()))
    import csv

    with (config.report_dir / "ingest_rejects.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(int(r["row_number"]), r["reason"]) for r in rows] == [
        (25, "missing_offset"),
        (26, "precision_too_fine"),
        (27, "bad_number"),
        (28, "unknown_signal"),
        (29, "unknown_experiment"),
        (30, "bad_quality"),
        (31, "malformed_row"),
        (33, "bad_timestamp"),
    ]


def test_fixture_checksum_matches_the_committed_sha256_file():
    """Guards `.gitattributes`: if git ever rewrote the fixture's line endings, this fails."""
    expected = (FIXTURES / "slice.sha256").read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256((FIXTURES / "slice.csv").read_bytes()).hexdigest() == expected
    assert b"\r" not in (FIXTURES / "slice.csv").read_bytes()
