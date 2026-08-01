"""Clean raw_reading -> reading_processed, inside InfluxDB.

Queries raw points from the `dac_raw` bucket, applies per-signal-type quality/cleaning
logic in pandas, and writes processed points to the `dac_processed` bucket (measurement
`reading_processed`). Source and sink are both InfluxDB -- Python here is the transform
engine, not the analysis environment. "Sampling and experimenting with Python" is a
separate, later step against the already-cleaned `reading_processed` measurement.

Gaps that exceed the max-interpolatable threshold are NOT represented as synthetic Influx
points (a gap has no timestamp of its own to attach a point-level status to) -- they're
written to data_quality_intervals.csv instead, matching the Postgres
`data_quality_intervals` table in design/schema_and_dashboard.md.

Per-signal-type handling:
  - event-based (source == "plant"): pump_speed, fan_speed, valve_state, process_state. A
    row is only written on change, so a long run of one value is the expected shape of the
    signal, not a stuck sensor. No gap/stuck/outlier logic -- pass-through, with BAD
    quality still excluded.
  - continuous numeric (ambient/absorber/hydrolyzer): polled at a nominal rate (see
    task/DATA_DICTIONARY.md). Subject to gap flagging (relative to that signal's nominal
    interval), stuck-sensor detection (implausibly long run of an *exact* repeated value),
    and rolling z-score outlier detection.
"""

import argparse
import csv
import os

import numpy as np
import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

EVENT_BASED_SOURCE = "plant"

# commanded/setpoint signals: designed to hold exactly constant between operator/controller
# changes, so a long flat run is normal, not a stuck sensor -- confirmed against a raw
# sample (current_setpoint: 302 unique values / 7200 samples, runs up to 3601 long).
# z-score outlier detection is skipped too: it assumes continuity around a slowly-varying
# mean, which doesn't hold across a deliberate step-change. Gap-checking still applies.
SETPOINT_SIGNALS = {"current_setpoint"}

GAP_FACTOR = 5        # a gap counts as GAP_EXCEEDS_MAX beyond GAP_FACTOR x nominal interval
STUCK_MIN_RUN = 20     # consecutive identical raw values => STUCK
OUTLIER_WINDOW = 60    # rolling window size (samples) for z-score
OUTLIER_Z = 4.0

# nominal sampling interval in seconds, from task/DATA_DICTIONARY.md
NOMINAL_INTERVAL_S = {
    "current_setpoint": 1, "current": 1, "voltage": 1, "power": 1, "flow": 1,
    "pressure": 1, "air_flow": 1, "pump_speed": 1, "fan_speed": 1,
    "co2_in_ppm": 2, "co2_out_ppm": 2, "solvent_flow": 2, "pressure_drop": 2,
    "acid_pH": 5, "base_pH": 5, "solvent_pH": 5, "conductivity": 5,
    "electrolyte_temperature": 5, "solvent_temperature": 5,
    "ambient_temperature": 60, "relative_humidity": 60, "ambient_pressure": 60,
    "available_solar_power": 60,
}


def fetch_raw(client: InfluxDBClient, bucket: str) -> pd.DataFrame:
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: 1970-01-01T00:00:00Z)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    tables = client.query_api().query_data_frame(query)
    df = pd.concat(tables, ignore_index=True) if isinstance(tables, list) else tables
    for col in ("value", "value_str"):
        if col not in df.columns:
            df[col] = np.nan
    df = df[["_time", "experiment_id", "source", "signal", "quality", "value", "value_str"]]
    return df.rename(columns={"_time": "time"})


def clean_series(g: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    g = g.sort_values("time").reset_index(drop=True)
    is_event_based = g["source"].iloc[0] == EVENT_BASED_SOURCE
    is_categorical = g["value_str"].notna().any()

    g["value_raw"] = g["value_str"] if is_categorical else g["value"]
    g["quality_raw"] = g["quality"]
    g["status"] = "VALID"
    g["reason"] = pd.NA
    g["value_clean"] = g["value_raw"]

    bad = g["quality_raw"] == "BAD"
    g.loc[bad, "status"] = "EXCLUDED_BAD"
    g.loc[bad, "reason"] = "quality=BAD at source"
    g.loc[bad, "value_clean"] = None

    gap_intervals: list[dict] = []

    if not is_event_based and not is_categorical:
        signal = g["signal"].iloc[0]
        experiment_id = g["experiment_id"].iloc[0]
        source = g["source"].iloc[0]
        nominal = NOMINAL_INTERVAL_S.get(signal, 5)
        max_gap = GAP_FACTOR * nominal

        gap_s = g["time"].diff().dt.total_seconds()
        for i in g.index[gap_s > max_gap]:
            gap_intervals.append({
                "experiment_id": experiment_id, "source": source, "signal": signal,
                "start_time": g["time"].iloc[i - 1].isoformat(),
                "end_time": g["time"].iloc[i].isoformat(),
                "interval_type": "GAP_EXCEEDS_MAX",
                "reason": f"gap {gap_s.iloc[i]:.0f}s > max {max_gap}s "
                          f"({GAP_FACTOR}x nominal {nominal}s)",
                "method": None,
            })

        ok = ~bad
        stuck = pd.Series(False, index=g.index)

        if signal not in SETPOINT_SIGNALS:
            run_id = g["value"].ne(g["value"].shift()).cumsum()
            run_len = g.groupby(run_id)["value"].transform("size")
            stuck = ok & (run_len >= STUCK_MIN_RUN)
            g.loc[stuck, "status"] = "STUCK"
            g.loc[stuck, "reason"] = f"identical value for >= {STUCK_MIN_RUN} consecutive samples"
            g.loc[stuck, "value_clean"] = None

            roll = g["value"].rolling(OUTLIER_WINDOW, min_periods=10, center=True)
            roll_std = roll.std()
            z = (g["value"] - roll.mean()) / roll_std
            outlier = ok & ~stuck & (roll_std > 0) & (z.abs() > OUTLIER_Z)
            g.loc[outlier, "status"] = "EXCLUDED_OUTLIER"
            g.loc[outlier, "reason"] = f"|z|>{OUTLIER_Z} vs rolling {OUTLIER_WINDOW}-sample window"
            g.loc[outlier, "value_clean"] = None

    return g, gap_intervals


def to_point(row) -> Point:
    p = (
        Point("reading_processed")
        .tag("experiment_id", row.experiment_id)
        .tag("source", row.source)
        .tag("signal", row.signal)
        .field("quality_raw", row.quality_raw)
        .field("status", row.status)
        .time(row.time.to_pydatetime(), WritePrecision.NS)
    )
    # same InfluxDB constraint hit during raw ingestion: one type per field name across the
    # whole measurement, so numeric vs. categorical values need separate field names.
    if isinstance(row.value_raw, str):
        p = p.field("value_raw_str", row.value_raw)
        if pd.notna(row.value_clean):
            p = p.field("value_clean_str", row.value_clean)
    else:
        p = p.field("value_raw", float(row.value_raw))
        if pd.notna(row.value_clean):
            p = p.field("value_clean", float(row.value_clean))
    if pd.notna(row.reason):
        p = p.field("reason", row.reason)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=os.environ.get("INFLUXDB_URL", "http://localhost:8086"))
    ap.add_argument("--token", default=os.environ.get("INFLUXDB_TOKEN", ""))
    ap.add_argument("--org", default=os.environ.get("INFLUXDB_ORG", "phlair"))
    ap.add_argument("--raw-bucket", default="dac_raw")
    ap.add_argument("--processed-bucket", default="dac_processed")
    ap.add_argument("--intervals-csv", default="data/processed/data_quality_intervals.csv")
    ap.add_argument("--batch-size", type=int, default=5000)
    args = ap.parse_args()

    client = InfluxDBClient(url=args.url, token=args.token, org=args.org)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("Fetching raw points...")
    raw = fetch_raw(client, args.raw_bucket)
    print(f"  {len(raw)} raw points across {raw.groupby(['experiment_id','source','signal']).ngroups} series")

    processed_frames = []
    all_gap_intervals: list[dict] = []
    for _, g in raw.groupby(["experiment_id", "source", "signal"], sort=False):
        cleaned, gaps = clean_series(g)
        processed_frames.append(cleaned)
        all_gap_intervals.extend(gaps)

    processed = pd.concat(processed_frames, ignore_index=True)
    print(f"  {len(processed)} processed points, {len(all_gap_intervals)} gap intervals flagged")
    print(processed["status"].value_counts().to_string())

    batch: list[Point] = []
    total = 0
    for row in processed.itertuples(index=False):
        batch.append(to_point(row))
        if len(batch) >= args.batch_size:
            write_api.write(bucket=args.processed_bucket, record=batch)
            total += len(batch)
            batch = []
            print(f"  wrote {total} points", end="\r")
    if batch:
        write_api.write(bucket=args.processed_bucket, record=batch)
        total += len(batch)
    print(f"\nWrote {total} points to bucket '{args.processed_bucket}'.")

    os.makedirs(os.path.dirname(args.intervals_csv), exist_ok=True)
    with open(args.intervals_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["experiment_id", "source", "signal", "start_time", "end_time",
                      "interval_type", "reason", "method"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_gap_intervals)
    print(f"Wrote {len(all_gap_intervals)} gap intervals to {args.intervals_csv}")

    client.close()


if __name__ == "__main__":
    main()
