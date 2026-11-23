"""Unit tests for the post-ingest profile (M2.5): pure functions and the CLI with a fake server.

No InfluxDB here. The fake gateway answers by query label, so the paths a live server cannot be
made to take on demand (a refused span probe, a failing query) are exercised exactly.
"""

from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

import jsonschema
import pytest

from pipeline import profiling, profiling_sql
from pipeline.ingest_influx import DatabaseCheckFailed
from pipeline.profiling import (
    best_lag,
    fit_line,
    instant_text,
    pearson,
    relationship_fits,
    render_markdown,
    shape_intervals,
    shape_runs,
    shape_series,
    sig9,
)
from pipeline.profiling_sql import QueryFailed
from pipeline.signals import (
    DOCUMENTED_RANGE,
    NOMINAL_INTERVAL_S,
    NUMERIC_TABLE,
    STATE_SIGNALS,
    STATE_TABLE,
    TABLE_FOR,
)
from scripts import post_ingest_profile as cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "post_ingest_profile.schema.json").read_text(encoding="utf-8")
)
VERDICT_WORDS = re.compile(
    r"stuck|suspicious|anomal|outlier|invalid|corrupt|error|wrong|fail|noise", re.IGNORECASE
)
NS = 1_000_000_000


# ---------------------------------------------------------------------------- declared tables


def test_the_tables_cover_the_23_numeric_pairs_and_not_the_2_text_pairs():  # M2.5 decision 6
    numeric = {pair for pair, table in TABLE_FOR.items() if table == NUMERIC_TABLE}
    text = {pair for pair, table in TABLE_FOR.items() if table == STATE_TABLE}
    assert len(numeric) == 23 and len(text) == 2
    assert set(NOMINAL_INTERVAL_S) == numeric
    assert set(DOCUMENTED_RANGE) == numeric
    assert {signal for _source, signal in text} == set(STATE_SIGNALS)


def test_the_nominal_rates_follow_the_data_dictionary():
    by_rate: dict[float, set[str]] = {}
    for (_source, signal), seconds in NOMINAL_INTERVAL_S.items():
        by_rate.setdefault(seconds, set()).add(signal)
    assert {rate: len(signals) for rate, signals in by_rate.items()} == {
        1.0: 9,
        2.0: 4,
        5.0: 6,
        60.0: 4,
    }
    assert "ambient_temperature" in by_rate[60.0] and "co2_in_ppm" in by_rate[2.0]


def test_every_documented_range_is_ordered_and_the_ph_signals_have_no_unit():
    for low, high, _unit in DOCUMENTED_RANGE.values():
        assert low < high
    pairs_without_unit = {
        pair[1] for pair, (_l, _h, unit) in DOCUMENTED_RANGE.items() if unit is None
    }
    assert pairs_without_unit == {"solvent_pH", "acid_pH", "base_pH"}


# ---------------------------------------------------------------------------- numbers


def test_rounding_keeps_nine_significant_digits_and_drops_float_noise():
    assert sig9(0.0199999999999996) == 0.02
    assert sig9(123456.78912345) == 123456.789
    assert sig9(1 / 3) == 0.333333333
    assert sig9(5) == 5 and isinstance(sig9(5), int)
    assert sig9(None) is None and sig9(float("nan")) is None and sig9(float("inf")) is None
    assert sig9(0.0) == 0.0


def test_instants_print_as_utc_text_with_only_the_decimals_they_need():
    assert instant_text(1_777_881_600 * NS) == "2026-05-04T08:00:00Z"
    assert instant_text(1_777_881_600 * NS + 500_000_000) == "2026-05-04T08:00:00.5Z"
    assert instant_text(1_777_881_600 * NS + 1_000) == "2026-05-04T08:00:00.000001Z"


# ---------------------------------------------------------------------------- lag and fits


def shifted_pair(delay_s: int, seconds: int = 120, seed: int = 5):
    rng = random.Random(seed)
    setpoint = {k * NS: float(rng.randint(100, 200)) for k in range(seconds)}
    current = {t + delay_s * NS: v for t, v in setpoint.items()}
    return current, setpoint


def test_the_lag_of_a_delayed_copy_is_found():  # S25.10, as a unit
    current, setpoint = shifted_pair(3)
    assert best_lag(current, setpoint) == (3, 1.0)


def test_no_delay_gives_lag_zero():
    current, setpoint = shifted_pair(0)
    assert best_lag(current, setpoint) == (0, 1.0)


def test_a_tie_goes_to_the_smaller_shift():
    # Alternating values repeat every 2 s, so shifts 0, 2, 4, ... all correlate at exactly 1.0.
    setpoint = {k * NS: float(k % 2) for k in range(60)}
    current = dict(setpoint)
    assert best_lag(current, setpoint) == (0, 1.0)
    # Delayed by 3 s the same series also matches at shift 1, 3, 5, ...: the smallest is 1.
    delayed = {t + 3 * NS: v for t, v in setpoint.items()}
    assert best_lag(delayed, setpoint) == (1, 1.0)


def test_a_flat_series_has_no_lag():
    flat = {k * NS: 5.0 for k in range(30)}
    assert best_lag(flat, flat) == (None, None)
    assert best_lag({}, {}) == (None, None)


def test_the_lag_search_stops_at_sixty_seconds():
    current, setpoint = shifted_pair(75, seconds=200)
    lag, _corr = best_lag(current, setpoint)
    assert lag is not None and lag <= 60 and lag != 75


def test_pearson_edge_cases():
    assert pearson([1.0], [2.0]) is None
    assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
    assert pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    assert pearson([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)


def test_a_perfect_line_is_recovered():
    fit = fit_line([1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0])
    assert fit["slope"] == pytest.approx(2.0) and fit["intercept"] == pytest.approx(1.0)
    assert fit["corr"] == pytest.approx(1.0) and fit["r2"] == pytest.approx(1.0)


def test_a_fit_does_not_depend_on_the_order_of_the_pairs():
    # The reason the fits are done here and not in SQL: the same pairs, any order, same bits,
    # even for an intercept that is a tiny difference of large numbers.
    rng = random.Random(11)
    xs = [30_000 + rng.uniform(-9000, 9000) for _ in range(500)]
    ys = [x + rng.uniform(-1, 1) for x in xs]
    pairs = list(zip(xs, ys, strict=True))
    first = fit_line(xs, ys)
    for seed in range(5):
        random.Random(seed).shuffle(pairs)
        again = fit_line([p[0] for p in pairs], [p[1] for p in pairs])
        assert again == first


def test_a_fit_without_spread_says_so():
    assert fit_line([1.0], [2.0])["slope"] is None
    flat_x = fit_line([2.0, 2.0, 2.0], [1.0, 2.0, 3.0])
    assert flat_x["slope"] is None and flat_x["corr"] is None
    flat_y = fit_line([1.0, 2.0, 3.0], [4.0, 4.0, 4.0])
    assert flat_y["slope"] == 0 and flat_y["corr"] is None


def test_relationship_fits_pair_readings_on_the_exact_same_instant():
    power = {0: 10.0, NS: 20.0, 2 * NS: 30.0}
    voltage = {0: 2.0, NS: 4.0}  # no reading at 2 s
    current = {0: 5.0, NS: 5.0, 2 * NS: 5.0}
    fits = relationship_fits(
        "power_vs_voltage_x_current", {"power": power, "voltage": voltage, "current": current}
    )
    assert fits["slope"] == pytest.approx(1.0) and fits["intercept"] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        relationship_fits("nonsense", {})


# ---------------------------------------------------------------------------- shaping


def test_on_change_series_get_no_nominal_counts():  # S25.2, as a unit
    row = {"n": 2, "dt_min": 40 * NS, "dt_median": 45 * NS, "dt_p95": 49.5 * NS, "dt_max": 50 * NS}
    shaped = shape_intervals(("plant", "process_state"), row, [])
    assert shaped["count"] == 2 and shaped["median"] == 45 and shaped["max"] == 50
    assert shaped["over_2x_nominal"] is None
    assert shaped["over_10x_nominal"] is None and shaped["seconds_in_over_2x"] is None


def test_polled_series_report_nominal_counts_and_the_longest_intervals():  # S25.1, as a unit
    row = {
        "n": 109,
        "dt_min": NS,
        "dt_median": NS,
        "dt_p95": NS,
        "dt_max": 11 * NS,
        "over2": 1,
        "over10": 1,
        "secs2": 11 * NS,
    }
    longest = [{"t0": 1_777_881_649 * NS, "t1": 1_777_881_660 * NS}]
    shaped = shape_intervals(("hydrolyzer", "voltage"), row, longest)
    assert (shaped["over_2x_nominal"], shaped["over_10x_nominal"]) == (1, 1)
    assert shaped["seconds_in_over_2x"] == 11
    assert shaped["longest"] == [
        {"start": "2026-05-04T08:00:49Z", "end": "2026-05-04T08:01:00Z", "seconds": 11}
    ]


def test_an_empty_measure_shapes_to_zero_counts_and_nulls():
    runs = shape_runs(None, [])
    assert runs == {
        "count": 0,
        "median_samples": None,
        "max_samples": None,
        "max_seconds": None,
        "longest": [],
    }
    assert shape_intervals(("hydrolyzer", "voltage"), None, [])["seconds_in_over_2x"] == 0


def one_series_basics(**overrides):
    row = {
        "source": "hydrolyzer",
        "signal": "voltage",
        "points": 3,
        "points_without_value": 0,
        "q_good": 3,
        "q_uncertain": 0,
        "q_bad": 0,
        "v_min": 1.0,
        "v_max": 3.0,
        "v_mean": 2.0,
        "v_stddev": 1.0,
        "v_median": 2.0,
        "v_p05": 1.1,
        "v_p95": 2.9,
        "below": 3,
        "above": 0,
    }
    return row | overrides


def test_a_text_series_carries_states_and_no_value_statistics():
    basics = one_series_basics(source="plant", signal="process_state")
    states = [
        {"source": "plant", "signal": "process_state", "value": "STARTUP", "n": 2},
        {"source": "plant", "signal": "process_state", "value": "SHUTDOWN", "n": 1},
    ]
    [shaped] = shape_series("EXP_X", STATE_TABLE, [basics], states, [], [], [], [], [])
    assert shaped["values"] is None and shaped["differences"] is None
    assert shaped["states"] == {"SHUTDOWN": 1, "STARTUP": 2}
    assert shaped["nominal_interval_s"] is None and shaped["unit"] is None


def test_numeric_series_get_the_declared_range_and_unit():
    [shaped] = shape_series("EXP_X", NUMERIC_TABLE, [one_series_basics()], [], [], [], [], [], [])
    assert (shaped["documented_min"], shaped["documented_max"], shaped["unit"]) == (60, 130, "V")
    assert shaped["values"]["below_documented_min"] == 3 and shaped["states"] is None


# ---------------------------------------------------------------------------- SQL guards


def all_sql() -> list[str]:
    queries = [
        profiling_sql.basics_sql(NUMERIC_TABLE),
        profiling_sql.basics_sql(STATE_TABLE),
        profiling_sql.values_percentiles_sql(),
        profiling_sql.states_sql(),
        profiling_sql.differences_sql(),
        profiling_sql.differences_percentile_sql(),
    ]
    for table in (NUMERIC_TABLE, STATE_TABLE):
        queries += [
            profiling_sql.intervals_sql(table),
            profiling_sql.intervals_percentile_sql(table),
            profiling_sql.intervals_longest_sql(table),
            profiling_sql.runs_sql(table),
            profiling_sql.runs_longest_sql(table),
        ]
    for sqls, _dependent in profiling_sql.RELATIONSHIPS.values():
        queries += sqls
    return queries


def test_no_query_uses_the_two_constructs_this_engine_gets_wrong():
    # Core 3.11.2 (DataFusion 51): COUNT(*) FILTER counts rows whose condition is NULL, and
    # PERCENTILE_CONT interpolates at float32 precision. Both found by the M2.5 calibration.
    for sql in all_sql():
        assert "FILTER (" not in sql.upper().replace("FILTER(", "FILTER (")
        assert "PERCENTILE_CONT(" not in sql.upper()


def test_no_query_writes_and_every_query_is_bounded_to_one_experiment_window():
    for sql in all_sql():
        assert re.match(r"^\s*(WITH|SELECT)\b", sql, re.IGNORECASE)
        assert not re.search(r"\b(INSERT|DELETE|UPDATE|DROP|CREATE|ALTER)\b", sql, re.IGNORECASE)
        assert "$exp" in sql and "$start" in sql and "$end" in sql


def test_signed_zero_is_normalised_before_comparing():
    # -0.0 < 0 is true on this engine; the real file has one -0.00 reading.
    sql = profiling_sql.basics_sql(NUMERIC_TABLE)
    assert "value + 0.0 <" in sql and "value + 0.0 >" in sql
    assert "value + 0.0" in profiling_sql.runs_sql(NUMERIC_TABLE)
    assert "value + 0.0" not in profiling_sql.runs_sql(STATE_TABLE)


def test_the_percentile_helper_weights_the_two_neighbouring_ranks():
    sql = profiling_sql.percentile_sql("SELECT 1.5 AS x", {"p95": 0.95}, ())
    assert "ROW_NUMBER() OVER (ORDER BY x)" in sql and "0.95" in sql and "GROUP BY" not in sql
    grouped = profiling_sql.percentile_sql("SELECT a, 1.5 AS x", {"p": 0.5}, ("a",))
    assert "PARTITION BY a" in grouped and grouped.endswith("GROUP BY a")


# ---------------------------------------------------------------------------- the CLI, fake server


EXPERIMENTS = [
    {
        "experiment_id": "EXP_A",
        "start_time": "2026-05-04T08:00:00Z",
        "end_time": "2026-05-04T10:00:00Z",
    }
]


class FakeGateway:
    """Answers each query by label. A label mapped to an exception raises it."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.queries = 0
        self.closed = False

    def rows(self, label, sql, params=None):  # noqa: ARG002
        self.queries += 1
        answer = self.answers.get(label, [])
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def close(self):
        self.closed = True


def happy_answers() -> dict[str, object]:
    return {
        "tables": [{"table_name": "readings_numeric"}],
        "basics readings_numeric": [one_series_basics()],
        "span_probe": [{"n": 3}],
    }


def run_cli(tmp_path, answers, *, databases=("dac_raw",), experiments=EXPERIMENTS, env=None):
    experiments_path = tmp_path / "experiments.json"
    if experiments is not None:
        experiments_path.write_text(json.dumps(experiments), encoding="utf-8")
    gateway = FakeGateway(answers)
    deps = cli.Deps(
        list_databases=lambda _host, _token: list(databases),
        gateway_factory=lambda _h, _t, _d: gateway,
        env={"INFLUX_HOST": "http://fake", "INFLUX_TOKEN": "t"} if env is None else env,
    )
    config = cli.Config(
        database="dac_raw", experiments_path=experiments_path, report_dir=tmp_path / "out"
    )
    return cli.run(config, deps), gateway, tmp_path / "out"


def test_a_clean_run_writes_both_files_and_matches_the_contract(tmp_path):
    code, gateway, out = run_cli(tmp_path, happy_answers())
    assert code == 0 and gateway.closed
    profile = json.loads((out / "post_ingest_profile.json").read_text("utf-8"))
    jsonschema.validate(profile, SCHEMA)
    assert profile["span_probe"]["succeeded"] is True and profile["span_probe"]["count"] == 3
    assert profile["span_probe"]["sum_of_per_experiment_counts"] == 3
    assert profile["timing"]["queries"] == gateway.queries
    assert (out / "post_ingest_profile.md").is_file()
    assert not (out / "post_ingest_profile_span_probe.txt").exists()


def test_a_refused_span_probe_is_recorded_and_the_profile_still_completes(tmp_path):  # S25.14
    answers = happy_answers() | {
        "span_probe": QueryFailed(
            "span_probe", RuntimeError("query would scan 1234 files, limit 432")
        )
    }
    code, _gateway, out = run_cli(tmp_path, answers)
    assert code == 0
    profile = json.loads((out / "post_ingest_profile.json").read_text("utf-8"))
    jsonschema.validate(profile, SCHEMA)
    probe = profile["span_probe"]
    assert probe["succeeded"] is False and probe["count"] is None
    assert probe["message_file"] == "post_ingest_profile_span_probe.txt"
    assert "limit 432" in (out / "post_ingest_profile_span_probe.txt").read_text("utf-8")
    # The server's words live only in the .txt, so the profile itself stays free of them.
    assert not VERDICT_WORDS.search((out / "post_ingest_profile.json").read_text("utf-8"))


def test_a_failing_query_writes_nothing_and_exits_3(tmp_path):  # S25.16
    answers = happy_answers() | {"runs readings_numeric": QueryFailed("runs", RuntimeError("boom"))}
    code, gateway, out = run_cli(tmp_path, answers)
    assert code == 3 and gateway.closed
    assert not out.exists()


def test_a_failing_probe_is_the_only_query_that_may_fail(tmp_path):
    answers = happy_answers() | {"differences": QueryFailed("differences", RuntimeError("boom"))}
    code, _gateway, out = run_cli(tmp_path, answers)
    assert code == 3 and not out.exists()


def test_a_missing_database_is_refused(tmp_path):  # S25.15, as a unit
    code, gateway, out = run_cli(tmp_path, happy_answers(), databases=("other",))
    assert code == 2 and not out.exists() and gateway.queries == 0


def test_an_unreadable_experiments_file_is_refused(tmp_path):
    (tmp_path / "experiments.json").write_text("{not json", encoding="utf-8")
    code, _gateway, out = run_cli(tmp_path, happy_answers(), experiments=None)
    assert code == 2 and not out.exists()


def test_an_empty_experiments_file_is_refused(tmp_path):
    code, _gateway, out = run_cli(tmp_path, happy_answers(), experiments=[])
    assert code == 2 and not out.exists()


def test_no_readings_table_is_refused(tmp_path):
    code, _gateway, out = run_cli(tmp_path, happy_answers() | {"tables": []})
    assert code == 2 and not out.exists()


def test_no_readings_in_any_window_is_refused(tmp_path):
    code, _gateway, out = run_cli(tmp_path, happy_answers() | {"basics readings_numeric": []})
    assert code == 2 and not out.exists()


def test_missing_influx_settings_are_refused(tmp_path):
    code, _gateway, out = run_cli(tmp_path, happy_answers(), env={})
    assert code == 2 and not out.exists()


def test_an_unreachable_server_is_refused(tmp_path):
    def unreachable(_host, _token):
        raise DatabaseCheckFailed("unreachable", "connection refused")

    experiments_path = tmp_path / "experiments.json"
    experiments_path.write_text(json.dumps(EXPERIMENTS), encoding="utf-8")
    deps = cli.Deps(
        list_databases=unreachable, env={"INFLUX_HOST": "http://x", "INFLUX_TOKEN": "t"}
    )
    config = cli.Config(experiments_path=experiments_path, report_dir=tmp_path / "out")
    assert cli.run(config, deps) == 2 and not (tmp_path / "out").exists()


def test_a_stale_probe_message_is_removed_when_the_probe_succeeds(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "post_ingest_profile_span_probe.txt").write_text("old message", encoding="utf-8")
    code, _gateway, _out = run_cli(tmp_path, happy_answers())
    assert code == 0 and not (out / "post_ingest_profile_span_probe.txt").exists()


# ---------------------------------------------------------------------------- the markdown


def sample_profile() -> dict:
    basics = one_series_basics()
    series = shape_series("EXP_A", NUMERIC_TABLE, [basics], [], [], [], [], [], [])
    return profiling.build_profile(
        database="dac_raw",
        experiments_file="data/raw/experiments.json",
        experiments=[
            {
                "experiment_id": "EXP_A",
                "start": "2026-05-04T08:00:00Z",
                "end": "2026-05-04T10:00:00Z",
            }
        ],
        span_probe={
            "start": "2026-05-04T08:00:00Z",
            "end": "2026-05-04T10:00:00Z",
            "succeeded": True,
            "count": 3,
            "sum_of_per_experiment_counts": 3,
            "message_file": None,
        },
        series=series,
        relationships=[],
        seconds=1.5,
        queries=10,
    )


def test_the_markdown_is_made_of_tables_and_has_no_verdict_words():
    text = render_markdown(sample_profile())
    assert text.startswith("# Post-ingest profile")
    assert "| source | signal | unit | points |" in text and "## EXP_A" in text
    assert not VERDICT_WORDS.search(text)


def test_a_profile_without_timing_is_comparable():
    one, two = sample_profile(), sample_profile()
    two["timing"] = {"seconds": 99.0, "queries": 10}
    assert profiling.without_timing(one) == profiling.without_timing(two)


# ---------------------------------------------------------------------------- the committed profile


def test_the_committed_real_profile_matches_the_contract_and_covers_the_data():  # S25.20, S25.19
    path = REPO_ROOT / "reports" / "post_ingest_profile.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(profile, SCHEMA)
    assert len(profile["experiments"]) == 6 and len(profile["series"]) == 150
    assert len(profile["relationships"]) == 24
    assert sum(s["points"] for s in profile["series"]) == 519_980
    assert profile["span_probe"]["sum_of_per_experiment_counts"] == 519_906
    assert not VERDICT_WORDS.search(path.read_text(encoding="utf-8"))
    assert not VERDICT_WORDS.search(
        (REPO_ROOT / "reports" / "post_ingest_profile.md").read_text(encoding="utf-8")
    )


def test_a_float_never_reaches_the_json_with_more_than_nine_digits():
    profile = json.loads(
        (REPO_ROOT / "reports" / "post_ingest_profile.json").read_text(encoding="utf-8")
    )

    def walk(node):
        if isinstance(node, dict):
            for child in node.values():
                yield from walk(child)
        elif isinstance(node, list):
            for child in node:
                yield from walk(child)
        elif isinstance(node, float):
            yield node

    for number in walk(profile["series"] + profile["relationships"]):
        assert not math.isnan(number) and number == float(f"{number:.9g}")
