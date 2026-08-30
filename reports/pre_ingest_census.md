# Pre-ingest census

Source: `data/raw/dac_raw_timeseries.csv`

Counts, distributions and samples only. See ADR-0010 for scope, ADR-0007 for the
collision-detection method reused here in detection-only mode (U-15). Collision
detection sorts via a bounded external merge sort (chunk size 50000) — see
`pipeline/collisions.py` and MISTAKES.md E-03.

## Checksum

- committed: `9f791b426d70f82c4047a75bad50f1dfd8a7a5f79ca5a0ddad5a33db8852553f`
- computed:  `9f791b426d70f82c4047a75bad50f1dfd8a7a5f79ca5a0ddad5a33db8852553f`
- equal: `True`

## Row counts

- total data rows: 520005
- distinct series (experiment_id, source, signal): 150

| experiment_id | source | signal | rows |
|---|---|---|---|
| EXP_001 | absorber | air_flow | 7200 |
| EXP_001 | absorber | co2_in_ppm | 3600 |
| EXP_001 | absorber | co2_out_ppm | 3600 |
| EXP_001 | absorber | pressure_drop | 3600 |
| EXP_001 | absorber | solvent_flow | 3600 |
| EXP_001 | absorber | solvent_pH | 1440 |
| EXP_001 | absorber | solvent_temperature | 1440 |
| EXP_001 | ambient | ambient_pressure | 120 |
| EXP_001 | ambient | ambient_temperature | 120 |
| EXP_001 | ambient | available_solar_power | 120 |
| EXP_001 | ambient | relative_humidity | 120 |
| EXP_001 | hydrolyzer | acid_pH | 1440 |
| EXP_001 | hydrolyzer | base_pH | 1440 |
| EXP_001 | hydrolyzer | conductivity | 1440 |
| EXP_001 | hydrolyzer | current | 7126 |
| EXP_001 | hydrolyzer | current_setpoint | 7200 |
| EXP_001 | hydrolyzer | electrolyte_temperature | 1440 |
| EXP_001 | hydrolyzer | flow | 7200 |
| EXP_001 | hydrolyzer | power | 7126 |
| EXP_001 | hydrolyzer | pressure | 7200 |
| EXP_001 | hydrolyzer | voltage | 7126 |
| EXP_001 | plant | fan_speed | 7200 |
| EXP_001 | plant | process_state | 7 |
| EXP_001 | plant | pump_speed | 7200 |
| EXP_001 | plant | valve_state | 3 |
| EXP_002 | absorber | air_flow | 7200 |
| EXP_002 | absorber | co2_in_ppm | 3600 |
| EXP_002 | absorber | co2_out_ppm | 3600 |
| EXP_002 | absorber | pressure_drop | 3600 |
| EXP_002 | absorber | solvent_flow | 3600 |
| EXP_002 | absorber | solvent_pH | 1441 |
| EXP_002 | absorber | solvent_temperature | 1440 |
| EXP_002 | ambient | ambient_pressure | 120 |
| EXP_002 | ambient | ambient_temperature | 120 |
| EXP_002 | ambient | available_solar_power | 120 |
| EXP_002 | ambient | relative_humidity | 120 |
| EXP_002 | hydrolyzer | acid_pH | 1344 |
| EXP_002 | hydrolyzer | base_pH | 1344 |
| EXP_002 | hydrolyzer | conductivity | 1344 |
| EXP_002 | hydrolyzer | current | 6720 |
| EXP_002 | hydrolyzer | current_setpoint | 6721 |
| EXP_002 | hydrolyzer | electrolyte_temperature | 1345 |
| EXP_002 | hydrolyzer | flow | 6722 |
| EXP_002 | hydrolyzer | power | 6723 |
| EXP_002 | hydrolyzer | pressure | 6721 |
| EXP_002 | hydrolyzer | voltage | 6722 |
| EXP_002 | plant | fan_speed | 7201 |
| EXP_002 | plant | process_state | 7 |
| EXP_002 | plant | pump_speed | 7203 |
| EXP_002 | plant | valve_state | 3 |
| EXP_003 | absorber | air_flow | 7200 |
| EXP_003 | absorber | co2_in_ppm | 3600 |
| EXP_003 | absorber | co2_out_ppm | 3600 |
| EXP_003 | absorber | pressure_drop | 3600 |
| EXP_003 | absorber | solvent_flow | 3600 |
| EXP_003 | absorber | solvent_pH | 1440 |
| EXP_003 | absorber | solvent_temperature | 1440 |
| EXP_003 | ambient | ambient_pressure | 120 |
| EXP_003 | ambient | ambient_temperature | 120 |
| EXP_003 | ambient | available_solar_power | 120 |
| EXP_003 | ambient | relative_humidity | 120 |
| EXP_003 | hydrolyzer | acid_pH | 1440 |
| EXP_003 | hydrolyzer | base_pH | 1440 |
| EXP_003 | hydrolyzer | conductivity | 1440 |
| EXP_003 | hydrolyzer | current | 7200 |
| EXP_003 | hydrolyzer | current_setpoint | 7200 |
| EXP_003 | hydrolyzer | electrolyte_temperature | 1440 |
| EXP_003 | hydrolyzer | flow | 7200 |
| EXP_003 | hydrolyzer | power | 7200 |
| EXP_003 | hydrolyzer | pressure | 7200 |
| EXP_003 | hydrolyzer | voltage | 7200 |
| EXP_003 | plant | fan_speed | 7200 |
| EXP_003 | plant | process_state | 7 |
| EXP_003 | plant | pump_speed | 7200 |
| EXP_003 | plant | valve_state | 3 |
| EXP_004 | absorber | air_flow | 7200 |
| EXP_004 | absorber | co2_in_ppm | 3600 |
| EXP_004 | absorber | co2_out_ppm | 3600 |
| EXP_004 | absorber | pressure_drop | 3600 |
| EXP_004 | absorber | solvent_flow | 3600 |
| EXP_004 | absorber | solvent_pH | 1440 |
| EXP_004 | absorber | solvent_temperature | 1440 |
| EXP_004 | ambient | ambient_pressure | 120 |
| EXP_004 | ambient | ambient_temperature | 120 |
| EXP_004 | ambient | available_solar_power | 120 |
| EXP_004 | ambient | relative_humidity | 120 |
| EXP_004 | hydrolyzer | acid_pH | 1440 |
| EXP_004 | hydrolyzer | base_pH | 1440 |
| EXP_004 | hydrolyzer | conductivity | 1440 |
| EXP_004 | hydrolyzer | current | 7200 |
| EXP_004 | hydrolyzer | current_setpoint | 7200 |
| EXP_004 | hydrolyzer | electrolyte_temperature | 1440 |
| EXP_004 | hydrolyzer | flow | 7200 |
| EXP_004 | hydrolyzer | power | 7200 |
| EXP_004 | hydrolyzer | pressure | 7200 |
| EXP_004 | hydrolyzer | voltage | 7200 |
| EXP_004 | plant | fan_speed | 7200 |
| EXP_004 | plant | process_state | 7 |
| EXP_004 | plant | pump_speed | 7200 |
| EXP_004 | plant | valve_state | 3 |
| EXP_005 | absorber | air_flow | 7200 |
| EXP_005 | absorber | co2_in_ppm | 3600 |
| EXP_005 | absorber | co2_out_ppm | 3600 |
| EXP_005 | absorber | pressure_drop | 3600 |
| EXP_005 | absorber | solvent_flow | 3600 |
| EXP_005 | absorber | solvent_pH | 1440 |
| EXP_005 | absorber | solvent_temperature | 1440 |
| EXP_005 | ambient | ambient_pressure | 120 |
| EXP_005 | ambient | ambient_temperature | 120 |
| EXP_005 | ambient | available_solar_power | 120 |
| EXP_005 | ambient | relative_humidity | 120 |
| EXP_005 | hydrolyzer | acid_pH | 1440 |
| EXP_005 | hydrolyzer | base_pH | 1440 |
| EXP_005 | hydrolyzer | conductivity | 1440 |
| EXP_005 | hydrolyzer | current | 7200 |
| EXP_005 | hydrolyzer | current_setpoint | 7200 |
| EXP_005 | hydrolyzer | electrolyte_temperature | 1440 |
| EXP_005 | hydrolyzer | flow | 7200 |
| EXP_005 | hydrolyzer | power | 7200 |
| EXP_005 | hydrolyzer | pressure | 7200 |
| EXP_005 | hydrolyzer | voltage | 7200 |
| EXP_005 | plant | fan_speed | 7200 |
| EXP_005 | plant | process_state | 19 |
| EXP_005 | plant | pump_speed | 7200 |
| EXP_005 | plant | valve_state | 5 |
| EXP_006 | absorber | air_flow | 5281 |
| EXP_006 | absorber | co2_in_ppm | 2640 |
| EXP_006 | absorber | co2_out_ppm | 2640 |
| EXP_006 | absorber | pressure_drop | 2641 |
| EXP_006 | absorber | solvent_flow | 2640 |
| EXP_006 | absorber | solvent_pH | 1056 |
| EXP_006 | absorber | solvent_temperature | 1056 |
| EXP_006 | ambient | ambient_pressure | 120 |
| EXP_006 | ambient | ambient_temperature | 120 |
| EXP_006 | ambient | available_solar_power | 120 |
| EXP_006 | ambient | relative_humidity | 120 |
| EXP_006 | hydrolyzer | acid_pH | 1440 |
| EXP_006 | hydrolyzer | base_pH | 1440 |
| EXP_006 | hydrolyzer | conductivity | 1440 |
| EXP_006 | hydrolyzer | current | 7200 |
| EXP_006 | hydrolyzer | current_setpoint | 7201 |
| EXP_006 | hydrolyzer | electrolyte_temperature | 1441 |
| EXP_006 | hydrolyzer | flow | 7202 |
| EXP_006 | hydrolyzer | power | 7201 |
| EXP_006 | hydrolyzer | pressure | 7200 |
| EXP_006 | hydrolyzer | voltage | 7200 |
| EXP_006 | plant | fan_speed | 7203 |
| EXP_006 | plant | process_state | 7 |
| EXP_006 | plant | pump_speed | 7200 |
| EXP_006 | plant | valve_state | 3 |

## Duplicate / collision census

Groups of 2+ rows sharing (experiment_id, source, signal, timestamp), detected by
sorting on that key and comparing adjacent rows (ADR-0007). Three candidate
definitions of "same value" (U-08) are each reported separately.

- total collision groups: 25
- total rows involved: 50
- group size distribution: {2: 25}
- groups equal under raw string equality: 15 / 25
- groups equal under float() exact equality (numeric groups only): 15 / 25
- groups equal under float tolerance 1e-6 (numeric groups only): 15 / 25
- groups where quality differs between rows: 0
- groups on declared categorical signals ['process_state', 'valve_state']: 0

Collision groups per series (top 15 by count):

| experiment_id | source | signal | groups |
|---|---|---|---|
| EXP_002 | hydrolyzer | power | 3 |
| EXP_002 | plant | pump_speed | 3 |
| EXP_006 | plant | fan_speed | 3 |
| EXP_002 | hydrolyzer | flow | 2 |
| EXP_002 | hydrolyzer | voltage | 2 |
| EXP_006 | hydrolyzer | flow | 2 |
| EXP_002 | absorber | solvent_pH | 1 |
| EXP_002 | hydrolyzer | current_setpoint | 1 |
| EXP_002 | hydrolyzer | electrolyte_temperature | 1 |
| EXP_002 | hydrolyzer | pressure | 1 |
| EXP_002 | plant | fan_speed | 1 |
| EXP_006 | absorber | air_flow | 1 |
| EXP_006 | absorber | pressure_drop | 1 |
| EXP_006 | hydrolyzer | current_setpoint | 1 |
| EXP_006 | hydrolyzer | electrolyte_temperature | 1 |

Sample groups equal under raw string equality (up to 5):

```
  series=EXP_002/absorber/solvent_pH
    row=140868 ts='2026-05-11T10:16:05Z' value='7.755' quality='GOOD'
    row=173188 ts='2026-05-11T10:16:05Z' value='7.755' quality='GOOD'
  series=EXP_002/hydrolyzer/current_setpoint
    row=109859 ts='2026-05-11T09:29:32Z' value='250.00' quality='GOOD'
    row=173183 ts='2026-05-11T09:29:32Z' value='250.00' quality='GOOD'
  series=EXP_002/hydrolyzer/electrolyte_temperature
    row=140862 ts='2026-05-11T10:16:05Z' value='59.84' quality='GOOD'
    row=173180 ts='2026-05-11T10:16:05Z' value='59.84' quality='GOOD'
  series=EXP_002/hydrolyzer/flow
    row=113822 ts='2026-05-11T09:34:55Z' value='49.61' quality='GOOD'
    row=173179 ts='2026-05-11T09:34:55Z' value='49.61' quality='GOOD'
  series=EXP_002/hydrolyzer/flow
    row=130117 ts='2026-05-11T09:57:03Z' value='50.96' quality='GOOD'
    row=173176 ts='2026-05-11T09:57:03Z' value='50.96' quality='GOOD'
```

Sample groups differing under raw string equality (up to 5):

```
  series=EXP_006/absorber/air_flow
    row=503884 ts='2026-04-20T11:38:06Z' value='1209.4' quality='GOOD'
    row=520001 ts='2026-04-20T11:38:06Z' value='1223.4' quality='GOOD'
  series=EXP_006/absorber/pressure_drop
    row=512819 ts='2026-04-20T11:50:14Z' value='15.06' quality='GOOD'
    row=520003 ts='2026-04-20T11:50:14Z' value='14.37' quality='GOOD'
  series=EXP_006/hydrolyzer/current_setpoint
    row=496794 ts='2026-04-20T11:28:28Z' value='150.00' quality='GOOD'
    row=520000 ts='2026-04-20T11:28:28Z' value='143.63' quality='GOOD'
  series=EXP_006/hydrolyzer/electrolyte_temperature
    row=463335 ts='2026-04-20T10:40:20Z' value='45.05' quality='GOOD'
    row=519997 ts='2026-04-20T10:40:20Z' value='46.30' quality='GOOD'
  series=EXP_006/hydrolyzer/flow
    row=454381 ts='2026-04-20T10:23:30Z' value='42.05' quality='GOOD'
    row=519998 ts='2026-04-20T10:23:30Z' value='41.88' quality='GOOD'
```

## Out-of-order arrivals

A row whose timestamp is earlier than the previous row seen for the same series,
in file order — evidence erased once storage sorts by time.

- total out-of-order rows: 30

By series (top 15):

| experiment_id | source | signal | count |
|---|---|---|---|
| EXP_002 | hydrolyzer | voltage | 2 |
| EXP_002 | hydrolyzer | flow | 2 |
| EXP_002 | plant | pump_speed | 2 |
| EXP_002 | hydrolyzer | power | 2 |
| EXP_006 | plant | fan_speed | 2 |
| EXP_002 | hydrolyzer | electrolyte_temperature | 1 |
| EXP_002 | hydrolyzer | pressure | 1 |
| EXP_002 | hydrolyzer | current_setpoint | 1 |
| EXP_002 | plant | fan_speed | 1 |
| EXP_002 | absorber | solvent_pH | 1 |
| EXP_005 | plant | valve_state | 1 |
| EXP_005 | absorber | air_flow | 1 |
| EXP_005 | hydrolyzer | current | 1 |
| EXP_005 | plant | fan_speed | 1 |
| EXP_005 | hydrolyzer | flow | 1 |

Sample instances (up to 5):

```
  {'series': ('EXP_002', 'hydrolyzer', 'voltage'), 'prev_row': 173174, 'prev_timestamp': '2026-05-11T10:59:59Z', 'this_row': 173175, 'this_timestamp': '2026-05-11T10:23:51Z'}
  {'series': ('EXP_002', 'hydrolyzer', 'flow'), 'prev_row': 173170, 'prev_timestamp': '2026-05-11T10:59:59Z', 'this_row': 173176, 'this_timestamp': '2026-05-11T09:57:03Z'}
  {'series': ('EXP_002', 'plant', 'pump_speed'), 'prev_row': 173173, 'prev_timestamp': '2026-05-11T10:59:59Z', 'this_row': 173177, 'this_timestamp': '2026-05-11T10:49:02Z'}
  {'series': ('EXP_002', 'plant', 'pump_speed'), 'prev_row': 173177, 'prev_timestamp': '2026-05-11T10:49:02Z', 'this_row': 173178, 'this_timestamp': '2026-05-11T09:18:24Z'}
  {'series': ('EXP_002', 'hydrolyzer', 'flow'), 'prev_row': 173176, 'prev_timestamp': '2026-05-11T09:57:03Z', 'this_row': 173179, 'this_timestamp': '2026-05-11T09:34:55Z'}
```

## Timestamp string-format variants

Digits collapsed to 'D' so distinct punctuation/timezone shapes group together.

| source | shape | count | example |
|---|---|---|---|
| absorber | `DDDD-DD-DDTDD:DD:DDZ` | 140355 | `2026-05-04T08:00:00Z` |
| ambient | `DDDD-DD-DDTDD:DD:DD+DD:DD` | 2880 | `2026-05-04T10:00:00+02:00` |
| hydrolyzer | `DDDD-DD-DDTDD:DD:DDZ` | 290289 | `2026-05-04T08:00:00Z` |
| plant | `DDDD-DD-DDTDD:DD:DDZ` | 86481 | `2026-05-04T08:00:00Z` |

Unparseable timestamps: 0

## Empty / non-parseable values and non-numeric signals

- rows with empty value: 0

Signals declared categorical (ADR-0006): ['process_state', 'valve_state']

Signals with at least one non-empty, non-float value, and the distinct raw values
seen (count each):

- `process_state`: {'STEADY_STATE': 24, 'LOAD_CHANGE': 18, 'STARTUP': 6, 'SHUTDOWN': 6}
- `valve_state`: {'CLOSED': 13, 'OPEN': 7}

