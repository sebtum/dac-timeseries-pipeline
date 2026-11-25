-- Steady-state KPIs and pair comparability per comparison version (M6, decision 13).
--
-- Three small tables written by `python -m scripts.load_comparison` from the committed
-- `comparison_summary.json` (M5), so Grafana can read them. Values are copied from the summary
-- unchanged; nothing is computed here. The loader replaces all rows of one `compare_version` in
-- one transaction, so a rerun writes identical rows and rows of other versions are untouched.
--
-- `comparison_kpi` is one row per experiment and KPI. `comparison_pair` is one row per pair of
-- experiments with a < b (the summary lists every pair once, in that order).
-- `comparison_pair_kpi` is one row per pair and KPI and goes with its pair: removing a pair
-- removes its KPI rows.
--
-- `differing` holds the factor names that differ, in factor order, comma-separated; the empty
-- string when none differ.
--
-- The experiment ids reference `experiment`, so a comparison row can be joined to the experiment
-- metadata. No ON DELETE action there: an experiment with comparison rows cannot be removed by
-- accident.

CREATE TABLE comparison_kpi (
    experiment_id    text NOT NULL REFERENCES experiment (experiment_id),
    compare_version  text NOT NULL,
    kpi              text NOT NULL,
    policy_version   text NOT NULL,
    metrics_version  text NOT NULL,
    value            double precision,
    unit             text NOT NULL,
    coverage         double precision,
    status           text NOT NULL CHECK (status IN ('complete', 'partial', 'none')),
    interval_low     double precision,
    interval_high    double precision,
    PRIMARY KEY (experiment_id, compare_version, kpi)
);

CREATE TABLE comparison_pair (
    a                  text NOT NULL REFERENCES experiment (experiment_id),
    b                  text NOT NULL REFERENCES experiment (experiment_id),
    compare_version    text NOT NULL,
    conditions_status  text NOT NULL CHECK (conditions_status IN ('same_conditions', 'supported', 'confounded')),
    differing          text NOT NULL,  -- factor names in factor order, comma-separated; '' when none
    PRIMARY KEY (a, b, compare_version),
    CHECK (a < b)
);

CREATE TABLE comparison_pair_kpi (
    a                text NOT NULL,
    b                text NOT NULL,
    compare_version  text NOT NULL,
    kpi              text NOT NULL,
    unit             text NOT NULL,
    difference       double precision,
    interval_low     double precision,
    interval_high    double precision,
    excludes_zero    boolean,
    coverage_status  text NOT NULL CHECK (coverage_status IN ('both_complete', 'partial_coverage', 'not_available')),
    PRIMARY KEY (a, b, compare_version, kpi),
    FOREIGN KEY (a, b, compare_version) REFERENCES comparison_pair (a, b, compare_version) ON DELETE CASCADE
);
