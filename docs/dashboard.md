# Dashboards: what each one shows, and how quality is made visible

Two Grafana dashboards, committed as JSON under [`grafana/dashboards/`](../grafana/dashboards/) and
provisioned read-only. Decisions and rejected options:
[ADR-0018](decisions/ADR-0018-grafana-dashboards.md). A unit test
(`tests/unit/test_dashboard_doc.py`) reads the JSON files and fails if a panel title, a variable, a
uid or a colour rule below differs from them.

## In short

The compare dashboard puts the experiments side by side: what each run was, its numbers, which
pairs of runs can fairly be compared, an overlay of one signal or metric on "minutes since start",
and how much of the data was usable. The detail dashboard takes one experiment at a time: its
phases, one signal with the readings the cleaning step threw out drawn beside the accepted line, the
electrical and capture series, and the quality tables. Bad data is shown, not hidden: an excluded
reading is a red point at the value the sensor reported, and gaps and stuck stretches are marked.

No panel states a finding. The comparability table and the steady-state numbers are the committed
results of the comparison step, not conclusions from it.

Details: both dashboards read InfluxDB (`dac_raw`) through the datasource `influx-dac` and Postgres
through `pg-dac`, both provisioned from
[`grafana/provisioning/`](../grafana/provisioning/). Every InfluxDB query filters the cleaning
policy version (and the metrics version for derived series) through hidden constant variables, and
is bounded by the window of the selected experiments from Postgres. Nothing is written to either
store by a dashboard. Dashboard files are the only source: the provider has `allowUiUpdates: false`
and `disableDeletion: true`, so an edit made in the browser cannot be saved.

## 1. The two dashboards

| Dashboard | uid | File | Folder | Use it to |
|---|---|---|---|---|
| Compare experiments | `dac-compare` | `grafana/dashboards/compare.json` | DAC | See the runs side by side, check which pairs may be compared, overlay one signal on a shared clock. |
| Experiment detail | `dac-experiment` | `grafana/dashboards/experiment.json` | DAC | Look inside one run: phases, one signal with its excluded readings, gaps, quality. |

Details: the compare dashboard's "Experiments" table links each experiment id to the detail
dashboard, with the experiment and its own time window already selected. The detail dashboard
opens on EXP_001's window and has a link, "Jump to this experiment's window", that resets the time
picker to the selected experiment.

## 2. Compare experiments (`dac-compare`)

### Variables

Hidden variables carry the fixed versions and the shared window arithmetic. The shown ones are the
three selectors at the top.

| Variable | Type | Shown | Selection | Default |
|---|---|---|---|---|
| `influx` | datasource | no | - | influx-dac |
| `pg` | datasource | no | - | pg-dac |
| `pg_schema` | constant | no | - | public |
| `policy_version` | constant | no | - | m3-v1 |
| `metrics_version` | constant | no | - | m4-v1 |
| `compare_version` | constant | no | - | m5-v1 |
| `experiment` | query | yes | multi-value with All | All |
| `windows` | query | no | - | computed |
| `span_from` | query | no | - | computed |
| `span_to` | query | no | - | computed |
| `signal` | query | yes | single | voltage |
| `metric` | custom | yes | single | capture_efficiency |

Details: `windows` is one row, the selected experiments as `('<id>', <start_ns>, <end_ns>)` joined
by commas, which the overlay and the exclusion-count queries join on. `span_from` and `span_to` are
the earliest start and the latest end of the selection. `signal` lists the 23 numeric signals from
`signal_quality`. `metric` is one of `power_computed`, `power_residual`, `capture_efficiency`,
`capture_rate`.

### Panels

| Id | Title | Type | Source | What it shows |
|---|---|---|---|---|
| 1 | `Experiments` | table | Postgres | One row per selected experiment: times, setpoint, flows, operator, sorbent batch, notes. The id links to the detail dashboard. |
| 2 | `Whole-run KPIs` | table | Postgres | The 13 whole-run metrics per experiment with unit, coverage and a coloured status. |
| 3 | `Steady-state KPIs (95 % interval)` | table | Postgres | The five steady-state numbers per experiment with their interval, coverage and a coloured status. |
| 4 | `Which pairs can be compared` | table | Postgres | Pairs with at least one selected end, a coloured conditions status and the factors that differ. |
| 5 | `Steady KPI differences by pair` | table | Postgres | Difference (b minus a) with its interval, whether it excludes zero, and a coloured coverage label. |
| 6 | `Overlay: ${signal} in minutes since start` | xychart | InfluxDB | Accepted readings of the chosen signal, one line per experiment, on minutes since that experiment's start. |
| 7 | `Overlay: ${metric} in minutes since start` | xychart | InfluxDB | The chosen derived metric, same axis. |
| 8 | `Data quality per experiment` | table | Postgres | Completeness, valid, bad and uncertain shares per experiment, coloured. |
| 9 | `Excluded readings by reason` | barchart | InfluxDB | Count of excluded readings per experiment and reason. An experiment with none has no bar. |

Details: the overlay does the clock shift in the query. Each row's x value is the reading's time in
nanoseconds minus the experiment's start from Postgres, divided by 60 seconds, so the six runs,
which start on six different dates, share one axis at full resolution (at most 6 x 7,200 points).
Excluded readings are not drawn in the overlay; they are in panel 9 and on the detail dashboard.

## 3. Experiment detail (`dac-experiment`)

### Variables

| Variable | Type | Shown | Selection | Default |
|---|---|---|---|---|
| `influx` | datasource | no | - | influx-dac |
| `pg` | datasource | no | - | pg-dac |
| `pg_schema` | constant | no | - | public |
| `policy_version` | constant | no | - | m3-v1 |
| `metrics_version` | constant | no | - | m4-v1 |
| `compare_version` | constant | no | - | m5-v1 |
| `experiment` | query | yes | single | EXP_001 |
| `windows` | query | no | - | computed |
| `span_from` | query | no | - | computed |
| `span_to` | query | no | - | computed |
| `signal` | query | yes | single | voltage |
| `from_ms` | query | no | - | computed |
| `to_ms` | query | no | - | computed |

Details: `from_ms` and `to_ms` are the selected experiment's start and end in epoch milliseconds,
used by the jump link. The default time range is EXP_001's window. Every InfluxDB query has the
experiment id, the half-open window `[span_from, span_to)` and Grafana's time filter, so the time
picker can only narrow what is shown.

### Panels

| Id | Title | Type | Source | What it shows |
|---|---|---|---|---|
| 1 | `Experiment` | table | Postgres | The selected experiment's metadata, with the jump link. |
| 2 | `Process phases` | state-timeline | InfluxDB | Every `process_state` and `valve_state` event with its raw value. |
| 3 | `${signal}: accepted and excluded` | timeseries | InfluxDB | Accepted readings as a line, excluded readings as red points at their raw value. |
| 4 | `Electrical: voltage, current, power` | timeseries | InfluxDB | Accepted voltage, current and logged power, and the computed power. |
| 5 | `Power residual (logged − computed)` | timeseries | InfluxDB | Logged power minus voltage times current, in watts. |
| 6 | `Capture: CO2 in and out` | timeseries | InfluxDB | Accepted CO2 at the inlet and outlet. |
| 7 | `Capture efficiency and rate` | timeseries | InfluxDB | The two derived capture series. |
| 8 | `Signal quality` | table | Postgres | One row per signal of the experiment, completeness and valid share coloured. |
| 9 | `Gaps and stuck stretches` | table | InfluxDB | Every gap and stuck stretch of every signal of the experiment. |
| 10 | `Excluded readings` | table | InfluxDB | Every excluded reading with its reason and raw value, at most 1,000, newest last. |

The title of panel 5 uses the true minus sign (U+2212), not a hyphen.

### Annotation

| Annotation | Panels | Colour |
|---|---|---|
| `Gaps and stuck stretches` | 3 | amber |

Details: the annotation reads `quality_intervals` for the selected experiment and signal and draws
each row as a region from its start to its end. It applies to panel 3 only, so the other series are
not crossed by regions of a signal they do not show.

## 4. Quality conventions

Quality is part of the picture, not a separate page. The colours are a display choice. They are not
a rule of the cleaning step and not a verdict. Where this document says amber it means Grafana's
`orange` (and, in one table, the hex value `#EAB839`, a yellower step of the same warning colour).

### Status words

| Panel | Column | Value | Colour |
|---|---|---|---|
| Whole-run KPIs | status | complete | green |
| Whole-run KPIs | status | partial | amber |
| Whole-run KPIs | status | none | red |
| Steady-state KPIs (95 % interval) | status | complete | green |
| Steady-state KPIs (95 % interval) | status | partial | amber |
| Steady-state KPIs (95 % interval) | status | none | red |
| Which pairs can be compared | conditions_status | same_conditions | green |
| Which pairs can be compared | conditions_status | supported | green |
| Which pairs can be compared | conditions_status | confounded | amber |
| Steady KPI differences by pair | coverage_status | both_complete | green |
| Steady KPI differences by pair | coverage_status | partial_coverage | amber |
| Steady KPI differences by pair | coverage_status | not_available | red |
| Gaps and stuck stretches | kind | gap | grey |
| Gaps and stuck stretches | kind | flatline | amber |
| Process phases | (any column) | STARTUP | blue |
| Process phases | (any column) | STEADY_STATE | green |
| Process phases | (any column) | LOAD_CHANGE | amber |
| Process phases | (any column) | SHUTDOWN | grey |

Details: a `confounded` pair is amber, not red, because it is not an error: it means two or more
conditions differ, and the "differing" column says which. The last four rows colour the phase
timeline; its colour mapping is set for the whole panel, so it applies to whatever column holds the
state. The pair status words are those of [`comparison.md`](comparison.md).

### Fractions

| Panel | Column | Colour steps |
|---|---|---|
| Data quality per experiment | completeness | red; amber from 0.5; green from 0.95 |
| Data quality per experiment | valid_fraction | red; amber from 0.5; green from 0.95 |
| Data quality per experiment | bad_fraction | green; amber from 0.05; red from 0.5 |
| Data quality per experiment | uncertain_fraction | green; amber from 0.05; red from 0.5 |
| Signal quality | completeness | red; amber from 0.5; green from 0.95 |
| Signal quality | valid_fraction | red; amber from 0.5; green from 0.95 |

Details: the 0.95 is the same number the metrics step uses for a `complete` label
(`COMPLETE_COVERAGE` in `pipeline/metrics.py`); a unit test checks that they are equal. The steps
are display only: nothing is stored or decided from them. The bad and uncertain rows are mirrored
(low is good) and the 0.05 and 0.5 are a display choice made for this dashboard; the plan named
thresholds for completeness and valid only. Signal quality colours completeness and valid only.

### Series and regions

| Series | Panel | Colour | Drawn as |
|---|---|---|---|
| accepted | `${signal}: accepted and excluded` | blue | line |
| excluded (raw value) | `${signal}: accepted and excluded` | red | points |

Details: the excluded series is the reading's raw value (`value_raw`), so a spike or an impossible
value shows where the sensor put it, not where the line is. One query returns both series as
columns, null where the reading has the other verdict, so a signal with no exclusions still has a
non-empty query. The annotation is amber for every kind of region: Grafana 13 has no colour per
annotation row, so the grey for a gap and the amber for a flatline appear in the "kind" column of
the table "Gaps and stuck stretches", and the region on the plot carries the kind in its text and
tag.

## 5. What you see when data is missing

| Case | What the dashboard does |
|---|---|
| A signal with no excluded readings | The "excluded (raw value)" series is empty and no red point is drawn; the query still returns rows. |
| An experiment with no gap and no stuck stretch (EXP_005 in the real data) | "Gaps and stuck stretches" is an empty table. This is the one panel the checker allows to be empty. |
| A database with no gap or stuck stretch for any experiment | The table `quality_intervals` does not exist yet (Core creates a table with its first row), so the table and the annotation show an error instead of an empty list. The real data has 34 intervals and is not affected. |
| An experiment with no exclusions | No bar in "Excluded readings by reason"; the table "Excluded readings" is empty. |
| A hole in a derived series | Not drawn: a derived value exists only where every input was accepted. Nothing is filled. |

Details: the experiment EXP_004 shows the clearest case. Its air flow from 09:00Z to 10:00Z is
excluded as a flat stretch (3,600 readings, all reason `flatline`). On the detail dashboard with
signal `air_flow` the amber region covers that hour and the red points sit along the bottom edge.
The red points are at the raw value, about 20, while the accepted line before 09:00 is near 1200
(the comparison step found a raw median of 20.0 after 09:00Z), so they sit near zero on a plot that
runs to 1400. Narrowing the time picker to that hour separates the points.

## 6. Running the checks

The checker needs the stack up and the data loaded (see the README for the order). It reads
`GRAFANA_URL`, `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` from `.env`.

```bash
python -m scripts.load_comparison                    # steady KPIs and pairs into Postgres (0004)
python -m scripts.check_dashboards --sweep signal --allow-empty "Gaps and stuck stretches"
python -m scripts.check_dashboards --dashboard grafana/dashboards/experiment.json \
    --time-range span --allow-empty "Gaps and stuck stretches"
docker compose --profile render up -d renderer
python -m scripts.screenshot_dashboards              # docs/screenshots/m6/*.png
```

| Command | What it does | Exit codes |
|---|---|---|
| `scripts.check_dashboards` | Lints both files, then posts every panel query and annotation query to Grafana for each experiment alone (and all together on the compare dashboard), and writes `reports/dashboard_check.json`. With `--sweep signal` it runs every numeric signal. | 0 every panel query returned rows (allowed titles exempt); 1 an empty or failed panel query; 2 refused, nothing written |
| `--time-range span` | Runs the detail dashboard with the time picker from the earliest start to the latest end of all experiments. | same |
| `scripts.screenshot_dashboards` | Renders four views through the image renderer. | 0 all saved; 2 renderer unreachable, nothing saved |

Details: the committed result [`reports/dashboard_check.json`](../reports/dashboard_check.json) is
299 runs, 3,105 panel queries, 3,082 with rows, 23 empty and allowed (all "Gaps and stuck
stretches" of EXP_005, where a plain count of `quality_intervals` is 0), 0 errors. The four
screenshots are in [`docs/screenshots/m6/`](screenshots/m6/): `compare-all.png`,
`compare-overlay-voltage.png`, `experiment-exp001-voltage.png` and
`experiment-exp004-air-flow.png`, each 1600 px wide.

## 7. Limits

| Limit | Why it matters |
|---|---|
| The wide time picker reads raw data | On this data set the detail dashboard with the picker over all 105 days returned the same rows as the experiment window for every panel query. At plant scale a months-wide picker should read the 1-minute rollup (`dac_rollup`) instead; no panel does that yet. |
| One annotation colour | Grafana 13 has no colour per annotation row; gap and flatline colours are in the table only. |
| No data, no table | A database with no gap or flatline has no `quality_intervals` table, so two queries error there. |
| Mirrored bad and uncertain thresholds | A display choice, not a policy. |
| Static renders clip tables | A table taller than its panel shows its first rows only; open the dashboard to scroll. |
| Logins are admin | Both datasources use the admin InfluxDB token and the Postgres owner login; read-only logins are a next step. |
| No finding is shown | The flow and pressure against voltage answer stays in `reports/findings.md` until it is approved. |
