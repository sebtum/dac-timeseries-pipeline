-- Derived metrics per experiment and per signal (M4, decision 14).
--
-- Two small summary tables written by `python -m scripts.metrics`, one row per metric and one per
-- signal for each experiment, version and run. They outlive the raw-data retention on purpose
-- (they are summaries, not readings). Both are upserted in one transaction per run, so a rerun
-- overwrites identical rows and a failed run leaves nothing partial.
--
-- Every experiment_id references `experiment`, so a metric can be joined to the experiment
-- metadata (current_setpoint_nominal_a and the other setpoints). No ON DELETE action: an
-- experiment with metrics cannot be removed by accident (the loader never deletes anyway).
--
-- `metrics_version` and `policy_version` are two separate things: the first names the formulas
-- (pipeline/metrics.py), the second the cleaning rule set the inputs came from.

CREATE TABLE experiment_metrics (
    experiment_id    text NOT NULL REFERENCES experiment (experiment_id),
    metrics_version  text NOT NULL,
    policy_version   text NOT NULL,
    metric           text NOT NULL,
    -- NULL when the metric cannot be computed (status 'none').
    value            double precision,
    unit             text NOT NULL,
    -- The four data-quality shares have no coverage and no status.
    coverage         double precision,
    status           text CHECK (status IN ('complete', 'partial', 'none')),
    PRIMARY KEY (experiment_id, metrics_version, metric)
);

CREATE TABLE signal_quality (
    experiment_id      text NOT NULL REFERENCES experiment (experiment_id),
    metrics_version    text NOT NULL,
    policy_version     text NOT NULL,
    source             text NOT NULL,
    signal             text NOT NULL,
    -- NULL for the on-change state signals, which have no polling interval.
    nominal_interval_s double precision,
    present            integer NOT NULL,
    expected           integer,
    accepted           integer NOT NULL,
    bad                integer NOT NULL,
    uncertain          integer NOT NULL,
    -- Each share is NULL when its denominator is 0.
    completeness       double precision,
    valid_fraction     double precision,
    bad_fraction       double precision,
    uncertain_fraction double precision,
    PRIMARY KEY (experiment_id, metrics_version, source, signal)
);
