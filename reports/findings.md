# Draft findings: flow and pressure against cell voltage, and what else the data shows

Status: draft, awaiting Sebastian's approval

Summary: in this run the data does not let us say that electrolyte flow or pressure changes the cell voltage, and it does not let us say they do not. The honest result is `not_resolved`. Five findings follow, each with the command and the SQL behind it. These are claims about six single runs, not about the plant in general.

How to read this file: each number is followed by a hidden reference comment that points into `reports/comparison_summary.json`. A unit test (`tests/unit/test_findings_doc.py`) opens the summary, follows every reference and checks that the written number is the referenced value rounded to the digits written. A number without a reference fails the test. The method is in [`docs/comparison.md`](../docs/comparison.md); the milestone report is [`reports/M5.md`](M5.md).

One run per condition: every claim below is worded "in this run" and none says what caused what. A difference between two runs cannot be separated from day-to-day variation (assumption on one run per condition in `docs/ASSUMPTIONS.md`).

## Flow and pressure against cell voltage

The answer, in plain words: in this run, no effect of flow or pressure on the cell voltage was found that this data can separate from noise. For the hydrolyzer (electrolyte flow in L/min and pressure in bar, with current and electrolyte temperature held fixed in the same regression) the evidence is `not_resolved` for both. For the absorber (air flow and pressure drop) it is `not_resolved` for both too. All eight evidence rows (two models, two windows, two terms) are `not_resolved`. That is not evidence that there is no effect. It means the intervals are too wide, or the experiments disagree, for a claim either way.

### Finding 1: Hydrolyzer model, electrolyte flow and pressure

Claim: In this run, the hydrolyzer data does not show an effect of electrolyte flow or pressure on the cell voltage once current and electrolyte temperature are held fixed. In the steady windows the interval for each of them includes zero in every experiment, so the evidence status is `not_resolved` <!-- ref: voltage_evidence/model=hydrolyzer,window=steady,term=flow/status --> for flow and `not_resolved` <!-- ref: voltage_evidence/model=hydrolyzer,window=steady,term=pressure/status --> for pressure. This is not evidence of no effect.

Details: the model is voltage ~ 1 + current + electrolyte_temperature + flow + pressure, fitted by least squares on the instants that fall inside the steady windows (each starts 60 s after a steady-state phase begins). Each coefficient has a 95 percent interval from a block bootstrap (120 s blocks, 1000 resamples), because 1 s readings are not independent. An interval that excludes zero would count; none does. The number of experiments whose flow interval excludes zero is 0 <!-- ref: voltage_evidence/model=hydrolyzer,window=steady,term=flow/experiments_excluding_zero --> of 6 <!-- ref: voltage_evidence/model=hydrolyzer,window=steady,term=flow/experiments_testable -->, and for pressure 0 <!-- ref: voltage_evidence/model=hydrolyzer,window=steady,term=pressure/experiments_excluding_zero --> of 6 <!-- ref: voltage_evidence/model=hydrolyzer,window=steady,term=pressure/experiments_testable -->. The pooled steady fit (all six experiments, one intercept each) gives flow -0.0068 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient --> V per L/min with an interval from -0.0328 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/interval_low --> to 0.0156 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/interval_high -->, and pressure 0.200 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=pressure/coefficient --> V per bar from -0.044 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=pressure/interval_low --> to 0.455 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=pressure/interval_high -->. Both pooled intervals include zero.

Command: `python -m scripts.compare --report-dir reports`

SQL (the pulls behind it; `$exp`, `$start`, `$end` are one experiment's window):

```sql
-- one accepted series of one experiment window (voltage, current, flow, pressure,
-- electrolyte_temperature, air_flow, pressure_drop, ...); $sig names the signal
SELECT time, value FROM readings_processed
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time

-- the phases of the experiment (process_state), which set the steady windows
SELECT time, end_ns, value FROM state_intervals
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time

-- Postgres: the metadata and the window of each experiment
SELECT * FROM experiment WHERE experiment_id = ANY(%s)
```

Numbers (steady windows, V per unit of the term; VIF is the collinearity measure, 10 or more means not separable):

| Experiment | flow coefficient | flow low | flow high | pressure coefficient | pressure low | pressure high | flow VIF |
|---|---|---|---|---|---|---|---|
| EXP_001 | 0.0140 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=flow/coefficient --> | -0.0023 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=flow/interval_low --> | 0.0244 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=flow/interval_high --> | 0.045 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=pressure/coefficient --> | -0.148 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=pressure/interval_low --> | 0.150 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=pressure/interval_high --> | 3.42 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/terms/name=flow/vif --> |
| EXP_002 | 0.0059 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=flow/coefficient --> | -0.0080 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=flow/interval_low --> | 0.0164 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=flow/interval_high --> | 0.015 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=pressure/coefficient --> | -0.139 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=pressure/interval_low --> | 0.154 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=pressure/interval_high --> | 7.20 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_002/terms/name=flow/vif --> |
| EXP_003 | -0.0009 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=flow/coefficient --> | -0.0153 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=flow/interval_low --> | 0.0080 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=flow/interval_high --> | -0.019 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=pressure/coefficient --> | -0.165 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=pressure/interval_low --> | 0.097 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=pressure/interval_high --> | 3.34 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_003/terms/name=flow/vif --> |
| EXP_004 | 0.0091 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=flow/coefficient --> | -0.0063 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=flow/interval_low --> | 0.0191 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=flow/interval_high --> | 0.085 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=pressure/coefficient --> | -0.074 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=pressure/interval_low --> | 0.191 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=pressure/interval_high --> | 3.61 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_004/terms/name=flow/vif --> |
| EXP_005 | 0.0085 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=flow/coefficient --> | -0.0112 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=flow/interval_low --> | 0.0258 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=flow/interval_high --> | 0.106 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=pressure/coefficient --> | -0.106 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=pressure/interval_low --> | 0.316 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=pressure/interval_high --> | 14.31 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=flow/vif --> |
| EXP_006 | 0.0094 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=flow/coefficient --> | -0.0040 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=flow/interval_low --> | 0.0176 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=flow/interval_high --> | -0.009 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=pressure/coefficient --> | -0.154 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=pressure/interval_low --> | 0.133 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=pressure/interval_high --> | 3.40 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_006/terms/name=flow/vif --> |
| pooled | -0.0068 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/coefficient --> | -0.0328 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/interval_low --> | 0.0156 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/interval_high --> | 0.200 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=pressure/coefficient --> | -0.044 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=pressure/interval_low --> | 0.455 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=pressure/interval_high --> | 5.74 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=pooled/terms/name=flow/vif --> |

How small the terms are: removing flow and pressure together lowers the model's R squared by at most 1.39e-05 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_001/joint/r2_drop --> in a steady fit (the largest of the six, EXP_001). Current and electrolyte temperature carry the voltage in these windows.

Whole-run fits do not change the answer, and they cannot be read as findings. In all six experiments the whole-run flow term is not separable from the others (flow VIF from 14.3 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=EXP_003/terms/name=flow/vif --> to 28.7 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=EXP_002/terms/name=flow/vif -->, pooled 18.0 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=pooled/terms/name=flow/vif -->), because flow follows current through the load changes. The whole-run evidence is also `not_resolved` <!-- ref: voltage_evidence/model=hydrolyzer,window=whole_run,term=flow/status --> for flow (1 <!-- ref: voltage_evidence/model=hydrolyzer,window=whole_run,term=flow/experiments_excluding_zero --> of six excludes zero, EXP_005) and `not_resolved` <!-- ref: voltage_evidence/model=hydrolyzer,window=whole_run,term=pressure/status --> for pressure.

Weakest result: EXP_005 has strongly autocorrelated residuals (see Limits and sources), so its intervals are probably too narrow. Its one whole-run flow interval that excludes zero (from 0.001 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=EXP_005/terms/name=flow/interval_low --> to 0.138 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=EXP_005/terms/name=flow/interval_high --> V per L/min) is the least reliable of the lot. Its steady-window flow VIF is 14.3 <!-- ref: voltage_models/model=hydrolyzer,window=steady,scope=EXP_005/terms/name=flow/vif -->, so even the steady fit for that run is not separable.

### Finding 2: Absorber model, air flow and pressure drop

Claim: In this run, the absorber data does not show an effect of air flow or pressure drop on the cell voltage once current and electrolyte temperature are held fixed. A few intervals exclude zero, but they do not agree with each other, so the evidence status is `not_resolved` <!-- ref: voltage_evidence/model=absorber,window=steady,term=air_flow/status --> for air flow and `not_resolved` <!-- ref: voltage_evidence/model=absorber,window=steady,term=pressure_drop/status --> for pressure drop.

Details: the same model and the same method as the first finding, with air flow (m3/h) and pressure drop (mbar) in place of flow and pressure, at the instants of the pressure-drop readings (one every 2 s). In the steady windows the air-flow interval excludes zero in 1 <!-- ref: voltage_evidence/model=absorber,window=steady,term=air_flow/experiments_excluding_zero --> of 6 <!-- ref: voltage_evidence/model=absorber,window=steady,term=air_flow/experiments_testable --> experiments (EXP_001, a tiny positive coefficient) and the pressure-drop interval in 2 <!-- ref: voltage_evidence/model=absorber,window=steady,term=pressure_drop/experiments_excluding_zero --> of 6 <!-- ref: voltage_evidence/model=absorber,window=steady,term=pressure_drop/experiments_testable --> (EXP_003 and EXP_005, both negative). The pooled steady pressure-drop interval, from 0.027 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=pressure_drop/interval_low --> to 0.413 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=pressure_drop/interval_high --> V per mbar, excludes zero too, but its sign is positive (0.248 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=pressure_drop/coefficient -->), the opposite of the two experiments above. A sign that flips between the pooled fit and the experiments is not a stable effect. EXP_005's result is the weakest (see Limits and sources). The pooled air-flow interval, from -0.00013 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=air_flow/interval_low --> to 0.00313 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=air_flow/interval_high --> V per m3/h, includes zero.

Command: `python -m scripts.compare --report-dir reports`

SQL (the same pulls as the first finding, with `$sig` set to `air_flow` and `pressure_drop`):

```sql
-- one accepted series of one experiment window (voltage, current, flow, pressure,
-- electrolyte_temperature, air_flow, pressure_drop, ...); $sig names the signal
SELECT time, value FROM readings_processed
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time

-- the phases of the experiment (process_state), which set the steady windows
SELECT time, end_ns, value FROM state_intervals
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time
```

Numbers (steady windows, V per unit of the term):

| Experiment | air_flow coefficient | air_flow low | air_flow high | pressure_drop coefficient | pressure_drop low | pressure_drop high | air_flow VIF |
|---|---|---|---|---|---|---|---|
| EXP_001 | 0.00082 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=air_flow/coefficient --> | 0.00012 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=air_flow/interval_low --> | 0.00148 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=air_flow/interval_high --> | -0.003 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=pressure_drop/coefficient --> | -0.027 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=pressure_drop/interval_low --> | 0.017 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_001/terms/name=air_flow/vif --> |
| EXP_002 | 0.00003 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=air_flow/coefficient --> | -0.00060 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=air_flow/interval_low --> | 0.00071 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=air_flow/interval_high --> | 0.003 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=pressure_drop/coefficient --> | -0.016 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=pressure_drop/interval_low --> | 0.021 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_002/terms/name=air_flow/vif --> |
| EXP_003 | 0.00016 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=air_flow/coefficient --> | -0.00055 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=air_flow/interval_low --> | 0.00082 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=air_flow/interval_high --> | -0.021 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=pressure_drop/coefficient --> | -0.040 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=pressure_drop/interval_low --> | -0.008 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_003/terms/name=air_flow/vif --> |
| EXP_004 | 0.00012 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=air_flow/coefficient --> | -0.00083 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=air_flow/interval_low --> | 0.00105 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=air_flow/interval_high --> | -0.021 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=pressure_drop/coefficient --> | -0.049 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=pressure_drop/interval_low --> | 0.010 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_004/terms/name=air_flow/vif --> |
| EXP_005 | 0.00015 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=air_flow/coefficient --> | -0.00116 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=air_flow/interval_low --> | 0.00143 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=air_flow/interval_high --> | -0.036 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=pressure_drop/coefficient --> | -0.069 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=pressure_drop/interval_low --> | -0.006 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_005/terms/name=air_flow/vif --> |
| EXP_006 | -0.00094 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=air_flow/coefficient --> | -0.00200 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=air_flow/interval_low --> | 0.00012 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=air_flow/interval_high --> | -0.007 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=pressure_drop/coefficient --> | -0.035 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=pressure_drop/interval_low --> | 0.018 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=EXP_006/terms/name=air_flow/vif --> |
| pooled | 0.00160 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=air_flow/coefficient --> | -0.00013 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=air_flow/interval_low --> | 0.00313 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=air_flow/interval_high --> | 0.248 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=pressure_drop/coefficient --> | 0.027 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=pressure_drop/interval_low --> | 0.413 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=pressure_drop/interval_high --> | 1.00 <!-- ref: voltage_models/model=absorber,window=steady,scope=pooled/terms/name=air_flow/vif --> |

Whole-run absorber fits are separable (VIF near 1) and give the same picture: air flow excludes zero in 0 <!-- ref: voltage_evidence/model=absorber,window=whole_run,term=air_flow/experiments_excluding_zero --> of six and pressure drop in 1 <!-- ref: voltage_evidence/model=absorber,window=whole_run,term=pressure_drop/experiments_excluding_zero --> of six, with status `not_resolved` <!-- ref: voltage_evidence/model=absorber,window=whole_run,term=air_flow/status --> and `not_resolved` <!-- ref: voltage_evidence/model=absorber,window=whole_run,term=pressure_drop/status -->.

## Other findings from the numbers

### Finding 3: The EXP_004 air-flow drop looks like a sensor fault, not a flow change

Claim: In this run, the raw air-flow reading in EXP_004 changed by -98.3 % <!-- ref: airflow_check/signals/signal=air_flow/relative_change --> after 09:00Z, while fan speed, pressure drop, inlet and outlet CO2 and capture efficiency did not move. That fits a sensor fault, and it fits the cleaning step's decision to exclude that hour. It is not proof: there is no second air-flow instrument.

Details: the check compares medians before and after 09:00Z inside the EXP_004 window. The raw air flow has a median of 1200.1 <!-- ref: airflow_check/signals/signal=air_flow/before_median --> m3/h before and 20.0 <!-- ref: airflow_check/signals/signal=air_flow/after_median --> after, from 3600 <!-- ref: airflow_check/signals/signal=air_flow/before_points --> raw points on each side (the raw value is read from every row, accepted or not, because cleaning excluded the second hour). A real fall of that size would be expected to show up in the other signals; the table says it did not.

Command: `python -m scripts.compare --report-dir reports`

SQL:

```sql
-- the air flow before and after 09:00Z is read from the raw value of every row, accepted or not
SELECT time, value_raw FROM readings_processed
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
ORDER BY time

-- fan_speed, pressure_drop, co2_in_ppm, co2_out_ppm: accepted rows only
SELECT time, value FROM readings_processed
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time

-- capture_efficiency comes from the metrics step
SELECT time, value FROM metrics_series
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND metric = $metric AND metrics_version = $mv AND policy_version = $pv
  AND value IS NOT NULL
ORDER BY time
```

Numbers (median before 09:00Z, median after, relative change = (after - before) / before):

| Signal | Source | Median before | Median after | Change |
|---|---|---|---|---|
| air_flow | raw value | 1200.1 <!-- ref: airflow_check/signals/signal=air_flow/before_median --> | 20.0 <!-- ref: airflow_check/signals/signal=air_flow/after_median --> | -98.3 % <!-- ref: airflow_check/signals/signal=air_flow/relative_change --> |
| fan_speed | accepted | 899.9 <!-- ref: airflow_check/signals/signal=fan_speed/before_median --> | 900.1 <!-- ref: airflow_check/signals/signal=fan_speed/after_median --> | 0.02 % <!-- ref: airflow_check/signals/signal=fan_speed/relative_change --> |
| pressure_drop | accepted | 15.11 <!-- ref: airflow_check/signals/signal=pressure_drop/before_median --> | 15.33 <!-- ref: airflow_check/signals/signal=pressure_drop/after_median --> | 1.5 % <!-- ref: airflow_check/signals/signal=pressure_drop/relative_change --> |
| co2_in_ppm | accepted | 420.0 <!-- ref: airflow_check/signals/signal=co2_in_ppm/before_median --> | 420.0 <!-- ref: airflow_check/signals/signal=co2_in_ppm/after_median --> | 0.0 % <!-- ref: airflow_check/signals/signal=co2_in_ppm/relative_change --> |
| co2_out_ppm | accepted | 94.6 <!-- ref: airflow_check/signals/signal=co2_out_ppm/before_median --> | 93.8 <!-- ref: airflow_check/signals/signal=co2_out_ppm/after_median --> | -0.85 % <!-- ref: airflow_check/signals/signal=co2_out_ppm/relative_change --> |
| capture_efficiency | metrics series | 0.775 <!-- ref: airflow_check/signals/signal=capture_efficiency/before_median --> | 0.777 <!-- ref: airflow_check/signals/signal=capture_efficiency/after_median --> | 0.24 % <!-- ref: airflow_check/signals/signal=capture_efficiency/relative_change --> |

Limits: this is one experiment and one instrument. It supports the assumption on the air-flow sensor fault in `docs/ASSUMPTIONS.md`; it does not close it. The pressure drop did not fall either, yet the next finding shows that pressure drop follows air flow only across experiments. So the unchanged pressure drop is weaker support than the unchanged fan speed and CO2.

### Finding 4: Pressure drop does not follow air flow within an experiment

Claim: In this run, inside any one experiment the pressure drop does not follow the air flow: R squared is at most 1.84e-03 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_003/r2_air_flow -->, and allowing a time lag of up to 60 s does not rescue it. Across experiments the pressure drop does follow the air flow, but there are only two air-flow levels, so that line rests on one contrast.

Details: for each experiment, over the steady windows at the instants where both exist, the pressure drop is fitted against air flow (a straight line, and a quadratic term as a check). The best lag found by searching 0 to 60 s runs from 17 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_002/best_lag_s --> s to 58 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_001/best_lag_s --> s, and the correlation at the best lag is small in every experiment (the largest in size is -0.061 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_004/corr_at_best_lag -->, EXP_004). A best lag picked from 61 candidates on noise is expected to land anywhere, so it is not a finding. Across experiments the line through the six medians has slope 0.0381 <!-- ref: pressure_drop_check/across/slope --> mbar per m3/h and R squared 0.999998 <!-- ref: pressure_drop_check/across/r2 -->, but the six points sit at two air-flow levels: 1200 <!-- ref: pressure_drop_check/across/points/experiment_id=EXP_001/air_flow_median --> m3/h (five experiments; EXP_001's pressure drop is 15.22 <!-- ref: pressure_drop_check/across/points/experiment_id=EXP_001/pressure_drop_median --> mbar) and 2400 <!-- ref: pressure_drop_check/across/points/experiment_id=EXP_003/air_flow_median --> m3/h (EXP_003 only, 60.92 <!-- ref: pressure_drop_check/across/points/experiment_id=EXP_003/pressure_drop_median --> mbar). A line through two clusters always fits well; it shows that the two levels differ, not what happens in between.

Command: `python -m scripts.compare --report-dir reports`

SQL (accepted pressure drop and air flow, as in the first finding with `$sig` set to each):

```sql
-- one accepted series of one experiment window (voltage, current, flow, pressure,
-- electrolyte_temperature, air_flow, pressure_drop, ...); $sig names the signal
SELECT time, value FROM readings_processed
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time
```

Numbers (per experiment, steady windows):

| Experiment | Instants | R squared, straight line | Best lag (s) | Correlation at best lag |
|---|---|---|---|---|
| EXP_001 | 3151 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_001/instants --> | 4.23e-04 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_001/r2_air_flow --> | 58 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_001/best_lag_s --> | 0.042 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_001/corr_at_best_lag --> |
| EXP_002 | 3135 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_002/instants --> | 1.14e-04 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_002/r2_air_flow --> | 17 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_002/best_lag_s --> | -0.039 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_002/corr_at_best_lag --> |
| EXP_003 | 3151 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_003/instants --> | 1.84e-03 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_003/r2_air_flow --> | 38 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_003/best_lag_s --> | -0.051 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_003/corr_at_best_lag --> |
| EXP_004 | 1501 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_004/instants --> | 7.46e-04 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_004/r2_air_flow --> | 18 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_004/best_lag_s --> | -0.061 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_004/corr_at_best_lag --> |
| EXP_005 | 2865 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_005/instants --> | 4.27e-06 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_005/r2_air_flow --> | 58 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_005/best_lag_s --> | 0.057 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_005/corr_at_best_lag --> |
| EXP_006 | 2189 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_006/instants --> | 9.30e-04 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_006/r2_air_flow --> | 21 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_006/best_lag_s --> | -0.046 <!-- ref: pressure_drop_check/per_experiment/experiment_id=EXP_006/corr_at_best_lag --> |

### Finding 5: Only one pair of experiments can be compared, and its numbers carry coverage warnings

Claim: In this run, only EXP_001 against EXP_002 is a supported comparison: the two differ in one recorded condition, the current setpoint (150 <!-- ref: comparisons/a=EXP_001,b=EXP_002/factors/factor=current_setpoint/a --> A against 250 <!-- ref: comparisons/a=EXP_001,b=EXP_002/factors/factor=current_setpoint/b --> A). The other 14 of 15 pairs differ in two or more conditions and are confounded. For the supported pair, EXP_002 read higher in voltage, power and energy per kilogram of CO2, with partial coverage on three of the five KPIs.

Details: conditions are measured from accepted readings in the steady windows (medians) and from metadata. Two experiments are "supported" for comparison when exactly one factor differs, "confounded" when two or more do. The supported pair's status is `supported` <!-- ref: comparisons/a=EXP_001,b=EXP_002/conditions_status -->. Each KPI difference is EXP_002 minus EXP_001, with a 95 percent block-bootstrap interval of the difference. A KPI is labelled partial when it rests on less than 95 percent of the steady seconds. The same sorbent batch and the same nominal air and solvent flow hold in both runs; the runs were a week apart, so day-to-day variation is not excluded.

Command: `python -m scripts.compare --report-dir reports`

SQL:

```sql
-- the KPI series: power_computed, capture_rate, capture_efficiency
SELECT time, value FROM metrics_series
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND metric = $metric AND metrics_version = $mv AND policy_version = $pv
  AND value IS NOT NULL
ORDER BY time

-- voltage and the factors (current_setpoint, air_flow, solvent_flow, ambient_temperature,
-- relative_humidity): accepted rows, as in the first finding
SELECT time, value FROM readings_processed
WHERE experiment_id = $exp AND time >= $start AND time < $end
  AND signal = $sig AND policy_version = $pv
  AND verdict = 'accepted' AND value IS NOT NULL
ORDER BY time

-- Postgres: the 13 whole-run metrics of each experiment
SELECT experiment_id, metric, value, unit, coverage, status
FROM experiment_metrics
WHERE metrics_version = %s AND experiment_id = ANY(%s)
ORDER BY experiment_id, metric
```

Numbers (EXP_002 minus EXP_001, steady windows):

| KPI | Difference | Low | High | Interval excludes zero | Coverage label |
|---|---|---|---|---|---|
| voltage_mean_v (V) | 10.15 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=voltage_mean_v/difference --> | 9.38 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=voltage_mean_v/interval_low --> | 11.03 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=voltage_mean_v/interval_high --> | yes | `partial_coverage` <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=voltage_mean_v/coverage_status --> |
| mean_power_kw (kW) | 12.73 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=mean_power_kw/difference --> | 12.24 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=mean_power_kw/interval_low --> | 13.30 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=mean_power_kw/interval_high --> | yes | `partial_coverage` <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=mean_power_kw/coverage_status --> |
| capture_rate_mean_kg_h (kg/h) | -0.00483 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_rate_mean_kg_h/difference --> | -0.00606 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_rate_mean_kg_h/interval_low --> | -0.00363 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_rate_mean_kg_h/interval_high --> | yes | `both_complete` <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_rate_mean_kg_h/coverage_status --> |
| capture_efficiency_mean (fraction) | 0.00007 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_efficiency_mean/difference --> | -0.00063 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_efficiency_mean/interval_low --> | 0.00076 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_efficiency_mean/interval_high --> | no | `both_complete` <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=capture_efficiency_mean/coverage_status --> |
| sec_kwh_per_kg (kWh/kg) | 19.05 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=sec_kwh_per_kg/difference --> | 18.41 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=sec_kwh_per_kg/interval_low --> | 19.87 <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=sec_kwh_per_kg/interval_high --> | yes | `partial_coverage` <!-- ref: comparisons/a=EXP_001,b=EXP_002/kpis/name=sec_kwh_per_kg/coverage_status --> |

Coverage warnings: a steady KPI is partial when its coverage is under 95 percent. In this run these are partial:

| Experiment | KPI | Coverage | Label |
|---|---|---|---|
| EXP_002 | voltage_mean_v | 0.923 <!-- ref: experiments/experiment_id=EXP_002/kpis/voltage_mean_v/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_002/kpis/voltage_mean_v/status --> |
| EXP_002 | mean_power_kw | 0.923 <!-- ref: experiments/experiment_id=EXP_002/kpis/mean_power_kw/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_002/kpis/mean_power_kw/status --> |
| EXP_002 | sec_kwh_per_kg | 0.922 <!-- ref: experiments/experiment_id=EXP_002/kpis/sec_kwh_per_kg/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_002/kpis/sec_kwh_per_kg/status --> |
| EXP_004 | capture_rate_mean_kg_h | 0.475 <!-- ref: experiments/experiment_id=EXP_004/kpis/capture_rate_mean_kg_h/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_004/kpis/capture_rate_mean_kg_h/status --> |
| EXP_004 | sec_kwh_per_kg | 0.475 <!-- ref: experiments/experiment_id=EXP_004/kpis/sec_kwh_per_kg/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_004/kpis/sec_kwh_per_kg/status --> |
| EXP_005 | capture_rate_mean_kg_h | 0.735 <!-- ref: experiments/experiment_id=EXP_005/kpis/capture_rate_mean_kg_h/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_005/kpis/capture_rate_mean_kg_h/status --> |
| EXP_005 | sec_kwh_per_kg | 0.735 <!-- ref: experiments/experiment_id=EXP_005/kpis/sec_kwh_per_kg/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_005/kpis/sec_kwh_per_kg/status --> |
| EXP_006 | capture_rate_mean_kg_h | 0.266 <!-- ref: experiments/experiment_id=EXP_006/kpis/capture_rate_mean_kg_h/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_006/kpis/capture_rate_mean_kg_h/status --> |
| EXP_006 | capture_efficiency_mean | 0.266 <!-- ref: experiments/experiment_id=EXP_006/kpis/capture_efficiency_mean/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_006/kpis/capture_efficiency_mean/status --> |
| EXP_006 | sec_kwh_per_kg | 0.266 <!-- ref: experiments/experiment_id=EXP_006/kpis/sec_kwh_per_kg/coverage --> | `partial` <!-- ref: experiments/experiment_id=EXP_006/kpis/sec_kwh_per_kg/status --> |

Why they are partial (from the metrics report): EXP_002 has a gap in its hydrolyzer signals; EXP_004 lost its air-flow hour to cleaning (capture needs air flow); EXP_005 has no ambient pressure for its first part; EXP_006 has stuck outlet-CO2 readings and a gap. These are cleaning and data-gap calls, not findings about the plant.

## Comparisons the data does not support

Each item below is something a reader might want to say and that this data cannot back up, with the reason.

### Pairs of experiments that differ in two or more conditions

Reason: with two or more differences, a gap between the two runs cannot be assigned to one of them. Fourteen pairs:

| Pair | Conditions that differ |
|---|---|
| EXP_001 vs EXP_003 | air_flow, sorbent_batch |
| EXP_001 vs EXP_004 | ambient_temperature, relative_humidity, sorbent_batch |
| EXP_001 vs EXP_005 | current_setpoint, current_setpoint_profile, ambient_temperature, sorbent_batch |
| EXP_001 vs EXP_006 | solvent_flow, sorbent_batch |
| EXP_002 vs EXP_003 | current_setpoint, air_flow, sorbent_batch |
| EXP_002 vs EXP_004 | current_setpoint, ambient_temperature, relative_humidity, sorbent_batch |
| EXP_002 vs EXP_005 | current_setpoint, current_setpoint_profile, ambient_temperature, sorbent_batch |
| EXP_002 vs EXP_006 | current_setpoint, solvent_flow, sorbent_batch |
| EXP_003 vs EXP_004 | air_flow, ambient_temperature, relative_humidity, sorbent_batch |
| EXP_003 vs EXP_005 | current_setpoint, current_setpoint_profile, air_flow, sorbent_batch |
| EXP_003 vs EXP_006 | air_flow, solvent_flow |
| EXP_004 vs EXP_005 | current_setpoint, current_setpoint_profile, ambient_temperature, relative_humidity, sorbent_batch |
| EXP_004 vs EXP_006 | solvent_flow, ambient_temperature, relative_humidity, sorbent_batch |
| EXP_005 vs EXP_006 | current_setpoint, current_setpoint_profile, solvent_flow, ambient_temperature, sorbent_batch |

### Other comparisons and claims that are not supported

| Claim | Why the data does not support it |
|---|---|
| Any statement that a condition caused a difference | One run per condition: a difference between two runs cannot be separated from day-to-day variation, sorbent batch or operator. Findings are worded "in this run". |
| Whole-run pooled flow or pressure effect on voltage | Not separable: the pooled whole-run flow VIF is 18.0 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=pooled/terms/name=flow/vif -->, above the limit of 10 <!-- ref: parameters/vif_limit -->, because flow follows current through the load changes. Only the joint effect could be cited, and it is 2.56e-04 <!-- ref: voltage_models/model=hydrolyzer,window=whole_run,scope=pooled/joint/r2_drop --> of R squared. |
| An absorber air-flow effect from the across-experiment contrast | Only two air-flow levels exist, and the higher one is EXP_003 alone, which also differs from EXP_001 in air_flow, sorbent_batch. |
| An absorber pressure-drop effect on voltage | The pooled interval excludes zero with a positive sign while EXP_003 and EXP_005 exclude zero with a negative sign (Finding 2): not consistent. |
| Capture-rate, efficiency or energy-per-kilogram comparisons that involve EXP_004, EXP_005 or EXP_006 | Partial coverage: for example EXP_006 capture rests on 0.266 <!-- ref: experiments/experiment_id=EXP_006/kpis/capture_rate_mean_kg_h/coverage --> of its steady seconds. They would be partial against any partner. |
| The EXP_002 against EXP_001 voltage, power and energy-per-kilogram differences as exact values | Partial coverage on EXP_002 (0.923 <!-- ref: experiments/experiment_id=EXP_002/kpis/voltage_mean_v/coverage -->): read them as the size of the gap, not as precise numbers. |
| Comparisons that rely on EXP_005's intervals | EXP_005's residuals are strongly autocorrelated, so its intervals are probably too narrow. Its varying current setpoint also differs from every other run. |
| Anything the summary marks as not testable | Nothing: all 28 fits were testable. Where a result is weak the reason is stated above (not separable, intervals include zero, or confounded). |

## Limits and sources

Every number in the sections above comes from `reports/comparison_summary.json`. The numbers in this section do not; their source is named next to them.

- EXP_005 residual autocorrelation: the lag-1 correlation of the residuals between 120 s blocks (hydrolyzer model, steady windows) is 0.87 for EXP_005, and between -0.15 and 0.12 for the other five. Source: the execute log of the comparison milestone (`.workflow/dac.log.md`), measured while building; it is not in the summary. It was measured on the hydrolyzer fit; the absorber fit of EXP_005 was not measured and is read with the same caution.
- The comparison tool was recomputed independently in plain Python (no pipeline imports) from the same database, with 0 differences at 9 digits (execute log). That checks the arithmetic, not the model.
- Six runs of 2 hours, one run per condition. The intervals describe resampling noise inside each run, not the spread between days.

