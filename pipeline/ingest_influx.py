"""The InfluxDB side of ingest: database check, batched synchronous writes, retry, count-back.

Four rules, each from `.workflow/dac.md` Decisions:

- **Never create a database** (decision 1). A write to a missing database creates it, with no
  retention, using one of Core's five slots; this was observed on 3.11.2 while building M2.
  So existence is checked first, over the same HTTP API the init script uses.
- **Atomic batches** (decision 12). The client is built with `accept_partial=False` on the v3
  `write_lp` endpoint: a batch with one line the server refuses saves nothing. Observed on
  3.11.2: with `accept_partial=True` the good lines of the same batch are saved, and the
  client's default endpoint (v2) is all-or-nothing whatever the flag says.
- **Synchronous writes**: `write_type=synchronous`, `no_sync=False`, so a returned call means
  the points are in the write-ahead log. No callbacks, no "how many were saved?" guessing.
- **Retry only what can heal** (decision 11): connection errors and server 5xx, 3 retries
  after 1, 2 and 4 seconds, so 4 tries in all. A 4xx means the line itself is refused; sending
  it again cannot help, so it fails at once.

The count-back (`count_points`) asks InfluxDB, one day-sized window at a time, how many points
each series holds. A single query over March-June would hit Core's ~72 hour query limit.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import urllib3
from influxdb_client_3 import InfluxDBClient3, WriteOptions, write_client_options
from influxdb_client_3.write_client.client.write_api import WriteType

RETRY_DELAYS_S = (1, 2, 4)
COUNT_WINDOW = timedelta(hours=24)
WRITE_TIMEOUT_MS = 60_000
HTTP_TIMEOUT_S = 10


class WriteFailed(Exception):
    """A batch that could not be saved. `attempts` is how many times it was sent."""

    def __init__(self, attempts: int, cause: BaseException) -> None:
        super().__init__(f"write failed after {attempts} attempt(s): {cause}")
        self.attempts = attempts
        self.cause = cause


class DatabaseCheckFailed(Exception):
    """The database list could not be read. `kind` is `unreachable` or `refused`."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def is_retryable(exc: BaseException) -> bool:
    """Connection-level errors and server 5xx can heal; a refused line (4xx) cannot."""
    if isinstance(exc, ConnectionError | TimeoutError | urllib3.exceptions.HTTPError):
        return True
    status = getattr(exc, "status", None)
    return isinstance(status, int) and status >= 500


def send_with_retry(
    write: Callable[[str], None],
    body: str,
    sleep: Callable[[float], None] = time.sleep,
    delays: tuple[float, ...] = RETRY_DELAYS_S,
) -> int:
    """Send one batch; returns the number of attempts used. Raises `WriteFailed`."""
    attempts = 0
    while True:
        attempts += 1
        try:
            write(body)
            return attempts
        except Exception as exc:
            if not is_retryable(exc) or attempts > len(delays):
                raise WriteFailed(attempts, exc) from exc
            sleep(delays[attempts - 1])


def list_databases(host: str, token: str) -> list[str]:
    """Names of the databases on the server, internal ones included."""
    request = urllib.request.Request(  # noqa: S310
        f"{host}/api/v3/configure/database?format=json",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:  # noqa: S310
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise DatabaseCheckFailed("refused", f"HTTP {exc.code} from {host}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise DatabaseCheckFailed("unreachable", f"{host}: {exc}") from exc
    return [entry["iox::database"] for entry in payload]


class InfluxGateway:
    """Writes and reads one database. Built only after the database is known to exist."""

    def __init__(self, host: str, token: str, database: str) -> None:
        self.database = database
        options = WriteOptions(
            write_type=WriteType.synchronous,
            write_precision="ns",
            no_sync=False,
            accept_partial=False,
            use_v2_api=False,
            timeout=WRITE_TIMEOUT_MS,
        )
        self._client = InfluxDBClient3(
            host=host,
            token=token,
            database=database,
            write_client_options=write_client_options(write_options=options),
        )

    def write(self, body: str) -> None:
        """Save one batch of line protocol, or raise and save none of it."""
        self._client.write(record=body)

    def count_points(
        self, table: str, experiment_id: str, first: datetime, last: datetime
    ) -> dict[tuple[str, str], int]:
        """Points per `(source, signal)` of one experiment with `first <= time <= last`."""
        sql = (
            f"SELECT source, signal, COUNT(*) AS n FROM {table} "  # noqa: S608 - fixed table name
            "WHERE experiment_id = $exp AND time >= $start AND time < $end "
            "GROUP BY source, signal"
        )
        counts: dict[tuple[str, str], int] = {}
        end = last + timedelta(microseconds=1)
        start = first
        while start < end:
            window_end = min(start + COUNT_WINDOW, end)
            result = self._client.query(
                sql,
                language="sql",
                query_parameters={
                    "exp": experiment_id,
                    "start": start.astimezone(UTC).isoformat(),
                    "end": window_end.astimezone(UTC).isoformat(),
                },
            )
            sources = result.column("source").to_pylist()
            signals = result.column("signal").to_pylist()
            numbers = result.column("n").to_pylist()
            for source, signal, number in zip(sources, signals, numbers, strict=True):
                counts[(source, signal)] = counts.get((source, signal), 0) + int(number)
            start = window_end
        return counts

    def close(self) -> None:
        self._client.close()
