"""Quality made visible on the "Experiment detail" dashboard, on the clean fixture (S6.18, S6.19).

The fixture `tests/fixtures/clean/readings.csv` (one experiment, EXP_001, 600 s from
2026-05-04T08:00:00Z, defects planted at stated instants; see `tests/e2e/test_clean_cli.py` for
the full list) goes through ingest and clean into a throwaway InfluxDB database. The dashboard's
own SQL is then run through a temporary Grafana datasource, exactly as written in
`grafana/dashboards/experiment.json` with the variables filled in (the hidden ones from the
dashboard's Postgres queries, against a throwaway schema), and compared with plain queries of
the tables.

Planted facts used here, in seconds after the start:

  voltage      590 readings (no point from +400 to +409); a spike at +120 (140.0) and a BAD 140.0
               at +500, so 588 accepted and two excluded; one gap from +399 to +410.
  air_flow     600 readings; from +360 to +599 the noise collapses: a flatline of 240 readings.
  solvent_temperature  one flatline of 40 readings from +100 to +295.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from pipeline.grafana_check import interpolate
from tests.e2e.grafana_helpers import (
    REPO_ROOT,
    drop_pg_schema,
    prepare_pg_schema,
    run_pipeline,
    temp_influx_datasource,
)
from tests.e2e.helpers import query
from tests.e2e.test_dashboard_experiment import (
    ANNOTATION,
    column,
    dashboard,
    resolve_values,
    run_target,
    windows_ms,
)

pytestmark = [pytest.mark.influx, pytest.mark.postgres, pytest.mark.grafana]

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "clean"
EXPERIMENT = "EXP_001"
POLICY = "m3-v1"
METADATA_KEYS = (
    "current_setpoint_nominal_A",
    "air_flow_nominal_m3h",
    "solvent_flow_nominal_Lmin",
    "operator",
    "sorbent_batch",
    "notes",
)


@dataclass
class Cleaned:
    database: str
    schema: str
    influx_uid: str
    doc: dict
    grafana: object
    window: tuple[int, int]


@pytest.fixture(scope="module")
def cleaned(grafana, module_db, tmp_path_factory):
    work = tmp_path_factory.mktemp("work")
    # The fixture's experiments file has only id and times; the Postgres loader needs the rest.
    rows = json.loads((FIXTURES / "experiments.json").read_text(encoding="utf-8"))
    window = windows_ms(FIXTURES / "experiments.json")[EXPERIMENT]
    for row in rows:
        row["duration_s"] = round((window[1] - window[0]) / 1000)
        for key in METADATA_KEYS:
            row.setdefault(key, None)
    loadable = work / "experiments_loadable.json"
    loadable.write_text(json.dumps(rows), encoding="utf-8")

    schema = f"m6_e2e_{uuid.uuid4().hex[:10]}"
    try:
        prepare_pg_schema(schema, loadable)
        run_pipeline(FIXTURES, module_db, schema, work, steps=("ingest", "clean"))
        with temp_influx_datasource(module_db) as uid:
            yield Cleaned(module_db, schema, uid, dashboard(), grafana, window)
    finally:
        drop_pg_schema(schema)


def values_for(cleaned: Cleaned, signal: str) -> dict[str, str]:
    return resolve_values(
        cleaned.grafana,
        cleaned.doc,
        influx_uid=cleaned.influx_uid,
        schema=cleaned.schema,
        experiment=EXPERIMENT,
        signal=signal,
        window=cleaned.window,
    )


def offset_s(epoch_ms: float, cleaned: Cleaned) -> float:
    return (epoch_ms - cleaned.window[0]) / 1000


def plain_offset_s(time_text: str, cleaned: Cleaned) -> float:
    """Seconds after the start of a plain-query `time` (`2026-05-04 08:02:00`, UTC)."""
    moment = datetime.strptime(time_text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return moment.timestamp() - cleaned.window[0] / 1000


def run_annotation(cleaned: Cleaned, signal: str):
    """The annotation query of the dashboard for one signal, over the experiment's window."""
    entry = next(a for a in cleaned.doc["annotations"]["list"] if a["name"] == ANNOTATION)
    values = values_for(cleaned, signal)
    sql = interpolate(entry["target"]["rawSql"], values)
    result = cleaned.grafana.query(
        cleaned.influx_uid,
        {"refId": "Anno", "rawSql": sql, "format": "table", "rawQuery": True},
        *cleaned.window,
    )
    assert result.error is None, result.error
    return result


# ------------------------------------------------------------------------------------- S6.18


def test_s6_18_excluded_readings_are_drawn_at_their_raw_value_beside_the_accepted_line(cleaned):
    values = values_for(cleaned, "voltage")
    _sql, result = run_target(
        cleaned.grafana, cleaned.doc, "${signal}: accepted and excluded", values, cleaned.window
    )
    assert result.fields == ["time", "accepted", "excluded (raw value)"]
    times = column(result, "time")
    accepted = column(result, "accepted")
    excluded = column(result, "excluded (raw value)")

    assert sum(v is not None for v in accepted) == 588
    drawn = [
        (offset_s(t, cleaned), v) for t, v in zip(times, excluded, strict=True) if v is not None
    ]
    assert drawn == [(120.0, 140.0), (500.0, 140.0)]
    # a reading is one verdict or the other: never both in the same row
    assert not [
        t
        for t, a, e in zip(times, accepted, excluded, strict=True)
        if a is not None and e is not None
    ]
    # one row per reading of the series (590), so the target is never empty
    assert result.rows == 590


def test_s6_18_a_flatline_excludes_every_reading_of_the_run_and_the_line_stops(cleaned):
    values = values_for(cleaned, "air_flow")
    _sql, result = run_target(
        cleaned.grafana, cleaned.doc, "${signal}: accepted and excluded", values, cleaned.window
    )
    times = column(result, "time")
    accepted = column(result, "accepted")
    excluded = column(result, "excluded (raw value)")
    assert sum(v is not None for v in accepted) == 360
    assert sum(v is not None for v in excluded) == 240
    first_excluded = min(
        offset_s(t, cleaned) for t, v in zip(times, excluded, strict=True) if v is not None
    )
    last_accepted = max(
        offset_s(t, cleaned) for t, v in zip(times, accepted, strict=True) if v is not None
    )
    assert (last_accepted, first_excluded) == (359.0, 360.0)


def test_s6_18_the_excluded_table_equals_a_plain_query_of_the_readings(cleaned):
    values = values_for(cleaned, "voltage")
    _sql, result = run_target(
        cleaned.grafana, cleaned.doc, "Excluded readings", values, cleaned.window
    )
    assert result.fields == ["time", "signal", "value_raw", "quality", "reason", "flags"]
    shown = list(
        zip(
            (offset_s(t, cleaned) for t in column(result, "time")),
            column(result, "signal"),
            column(result, "value_raw"),
            column(result, "quality"),
            column(result, "reason"),
            column(result, "flags"),
            strict=True,
        )
    )

    plain = query(
        cleaned.database,
        "SELECT time, signal, value_raw, quality, reason, flags FROM readings_processed "
        f"WHERE experiment_id = '{EXPERIMENT}' AND policy_version = '{POLICY}' "
        "AND verdict = 'excluded' ORDER BY time, signal",
    )
    expected = [
        (
            plain_offset_s(r["time"], cleaned),
            r["signal"],
            r["value_raw"],
            r["quality"],
            r["reason"],
            r["flags"],
        )
        for r in plain
    ]
    assert shown == expected
    # the construction: 297 excluded readings, one of them (the unknown state) in the state table
    assert len(shown) == 296
    assert Counter(reason for *_rest, reason, _flags in shown) == {
        "flatline": 280,
        "flag_bad": 11,
        "no_value": 1,
        "flag_uncertain": 1,
        "outside_physical_limits": 1,
        "conflicting_duplicate": 1,
        "spike": 1,
    }
    voltage = [(t, v, q, reason) for t, signal, v, q, reason, _f in shown if signal == "voltage"]
    assert voltage == [(120.0, 140.0, "GOOD", "spike"), (500.0, 140.0, "BAD", "flag_bad")]
    # a reading with no value is listed too, with an empty raw value
    assert [row for row in shown if row[4] == "no_value"] == [
        (60.0, "current", None, "GOOD", "no_value", "no_value")
    ]


# ------------------------------------------------------------------------------------- S6.19


def test_s6_19_a_gap_is_one_region_from_its_start_to_its_end(cleaned):
    result = run_annotation(cleaned, "voltage")
    assert result.fields == ["time", "timeend", "text", "tags"]
    assert result.rows == 1
    assert offset_s(column(result, "time")[0], cleaned) == 399.0
    assert offset_s(column(result, "timeend")[0], cleaned) == 410.0
    text = column(result, "text")[0]
    assert text.startswith("gap ") and text.endswith(" s") and float(text[4:-2]) == 11.0
    assert column(result, "tags")[0] == "gap"


def test_s6_19_a_stuck_stretch_is_one_region_per_signal(cleaned):
    air_flow = run_annotation(cleaned, "air_flow")
    assert air_flow.rows == 1
    assert offset_s(column(air_flow, "time")[0], cleaned) == 360.0
    assert offset_s(column(air_flow, "timeend")[0], cleaned) == 599.0
    assert column(air_flow, "tags")[0] == "flatline"
    assert column(air_flow, "text")[0].startswith("flatline ")

    temperature = run_annotation(cleaned, "solvent_temperature")
    assert temperature.rows == 1
    assert offset_s(column(temperature, "time")[0], cleaned) == 100.0
    assert offset_s(column(temperature, "timeend")[0], cleaned) == 295.0
    assert column(temperature, "tags")[0] == "flatline"
    assert float(column(temperature, "text")[0].split()[1]) == 195.0


def test_s6_19_a_signal_without_an_interval_has_no_region(cleaned):
    assert run_annotation(cleaned, "current").rows == 0
    assert run_annotation(cleaned, "pressure").rows == 0


def test_s6_19_the_regions_equal_the_quality_intervals_table(cleaned):
    """Every region is a row of `quality_intervals`: start, end (from `end_ns`) and kind."""
    plain = query(
        cleaned.database,
        "SELECT time, end_ns, signal, kind, seconds, points FROM quality_intervals "
        f"WHERE experiment_id = '{EXPERIMENT}' AND policy_version = '{POLICY}' "
        "ORDER BY signal, time",
    )
    assert [(r["signal"], r["kind"], r["points"]) for r in plain] == [
        ("air_flow", "flatline", 240),
        ("solvent_temperature", "flatline", 40),
        ("voltage", "gap", 0),
    ]
    for row in plain:
        region = run_annotation(cleaned, row["signal"])
        assert region.rows == 1, row["signal"]
        assert column(region, "time")[0] == pytest.approx(
            cleaned.window[0] + plain_offset_s(row["time"], cleaned) * 1000
        )
        assert column(region, "timeend")[0] == row["end_ns"] // 1_000_000
        assert column(region, "tags")[0] == row["kind"]


def test_s6_19_the_interval_table_lists_every_quality_interval_of_the_experiment(cleaned):
    values = values_for(cleaned, "voltage")
    _sql, result = run_target(
        cleaned.grafana, cleaned.doc, "Gaps and stuck stretches", values, cleaned.window
    )
    assert result.fields == ["signal", "kind", "start", "seconds", "points"]
    shown = list(
        zip(
            column(result, "signal"),
            column(result, "kind"),
            (offset_s(t, cleaned) for t in column(result, "start")),
            column(result, "seconds"),
            column(result, "points"),
            strict=True,
        )
    )
    plain = query(
        cleaned.database,
        "SELECT signal, kind, time, seconds, points FROM quality_intervals "
        f"WHERE experiment_id = '{EXPERIMENT}' AND policy_version = '{POLICY}' "
        "ORDER BY time, signal",
    )
    assert shown == [
        (r["signal"], r["kind"], plain_offset_s(r["time"], cleaned), r["seconds"], r["points"])
        for r in plain
    ]
    assert shown == [
        ("solvent_temperature", "flatline", 100.0, 195.0, 40),
        ("air_flow", "flatline", 360.0, 239.0, 240),
        ("voltage", "gap", 399.0, 11.0, 0),
    ]
