"""Ingest data/raw/dac_raw_timeseries.csv into InfluxDB unchanged, as `raw_reading` points.

Schema: design/schema_and_dashboard.md
    measurement=raw_reading
    tags:   experiment_id, source, signal
    fields: value (float, or string for categorical signals), quality

Known limitation: InfluxDB identifies a point by (measurement, tag set, timestamp). If the
raw CSV has two rows with the same experiment_id/source/signal/timestamp, the second write
overwrites the first — the raw bucket would then silently lose one of them, which conflicts
with "raw preserved unchanged". Not handled here; check for such collisions before trusting
this ingestion path 1:1, e.g.:
    df.duplicated(subset=["experiment_id", "source", "signal", "timestamp"]).sum()
"""

import argparse
import csv
import os
from datetime import datetime, timezone

from influxdb_client import Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# signals whose `value` is categorical (string), not numeric — see task/DATA_DICTIONARY.md
CATEGORICAL_SIGNALS = {"valve_state", "process_state"}


def parse_timestamp(raw: str) -> datetime:
    """ISO 8601 with either a 'Z' or an explicit offset; normalized to UTC.

    Sources log different conventions (see task/DATA_DICTIONARY.md) — normalizing the
    instant here does not touch the numeric value, it only fixes how the timestamp is
    represented.
    """
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def row_to_point(row: dict) -> tuple[Point, bool]:
    """Build a Point for one CSV row. Returns (point, had_parse_fallback).

    InfluxDB enforces one type per (measurement, field name) across the *whole* measurement,
    not just within a series/tag-set — mixing a float and a string under the same field name
    anywhere in `raw_reading` is a hard write-time conflict. So numeric and categorical
    signals cannot both live in a `value` field; categorical signals (and any row that fails
    to parse as a number) go into `value_str` instead.
    """
    signal = row["signal"]
    p = (
        Point("raw_reading")
        .tag("experiment_id", row["experiment_id"])
        .tag("source", row["source"])
        .tag("signal", signal)
        .field("quality", row["quality"])
        .time(parse_timestamp(row["timestamp"]), WritePrecision.NS)
    )

    if signal in CATEGORICAL_SIGNALS:
        return p.field("value_str", row["value"]), False

    try:
        return p.field("value", float(row["value"])), False
    except ValueError:
        # Unexpected non-numeric value on a signal we expect to be numeric. Don't drop the
        # row and don't write it into `value` (type conflict) — preserve it under the same
        # string field categorical signals use, and surface a count so it doesn't pass
        # silently.
        return p.field("value_str", row["value"]), True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default="data/raw/dac_raw_timeseries.csv")
    ap.add_argument("--url", default=os.environ.get("INFLUXDB_URL", "http://localhost:8086"))
    ap.add_argument("--token", default=os.environ.get("INFLUXDB_TOKEN", ""))
    ap.add_argument("--org", default=os.environ.get("INFLUXDB_ORG", "phlair"))
    ap.add_argument("--bucket", default=os.environ.get("INFLUXDB_BUCKET", "dac_raw"))
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=None, help="only ingest first N rows (testing)")
    ap.add_argument("--dry-run", action="store_true", help="build points, skip the DB write")
    args = ap.parse_args()

    write_api = None
    client = None
    if not args.dry_run:
        from influxdb_client import InfluxDBClient

        client = InfluxDBClient(url=args.url, token=args.token, org=args.org)
        write_api = client.write_api(write_options=SYNCHRONOUS)

    batch: list[Point] = []
    total = 0
    fallbacks = 0

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if args.limit and i >= args.limit:
                break

            point, fell_back = row_to_point(row)
            fallbacks += fell_back
            batch.append(point)

            if len(batch) >= args.batch_size:
                if write_api:
                    write_api.write(bucket=args.bucket, record=batch)
                total += len(batch)
                batch = []
                print(f"  {'validated' if args.dry_run else 'wrote'} {total} points", end="\r")

        if batch:
            if write_api:
                write_api.write(bucket=args.bucket, record=batch)
            total += len(batch)

    mode = "Dry run — no data written." if args.dry_run else f"Wrote to bucket '{args.bucket}'."
    print(f"\n{mode} {total} points, {fallbacks} value-parse fallbacks (see value_str field).")

    if client:
        client.close()


if __name__ == "__main__":
    main()
