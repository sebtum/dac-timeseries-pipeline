# Ingest report

Status: **ok** (exit code 0)

- File: `data/raw/dac_raw_timeseries.csv`
- SHA-256 expected: `9f791b426d70f82c4047a75bad50f1dfd8a7a5f79ca5a0ddad5a33db8852553f`
- SHA-256 actual: `9f791b426d70f82c4047a75bad50f1dfd8a7a5f79ca5a0ddad5a33db8852553f`
- Fingerprint matches: True
- Database: `dac_raw`
- Data rows read: 520005

## Totals

| CSV rows | Saved | Exact copies | Conflict losers | Rejected | Balanced |
|---|---|---|---|---|---|
| 520005 | 519980 | 15 | 10 | 0 | True |

`CSV rows = saved + exact copies + conflict losers + rejected`. `Saved` is counted back from InfluxDB, not counted on write.

Series: 150, unbalanced: 0.

## Rejected rows

None.

## Conflicts

Rows written to `readings_conflicts`: 10

## Out-of-order rows

Total: 30 (counted, stored normally).

| Experiment | Source | Signal | Rows |
|---|---|---|---|
| EXP_002 | absorber | solvent_pH | 1 |
| EXP_002 | hydrolyzer | current_setpoint | 1 |
| EXP_002 | hydrolyzer | electrolyte_temperature | 1 |
| EXP_002 | hydrolyzer | flow | 2 |
| EXP_002 | hydrolyzer | power | 2 |
| EXP_002 | hydrolyzer | pressure | 1 |
| EXP_002 | hydrolyzer | voltage | 2 |
| EXP_002 | plant | fan_speed | 1 |
| EXP_002 | plant | pump_speed | 2 |
| EXP_005 | absorber | air_flow | 1 |
| EXP_005 | hydrolyzer | current | 1 |
| EXP_005 | hydrolyzer | flow | 1 |
| EXP_005 | hydrolyzer | power | 1 |
| EXP_005 | hydrolyzer | pressure | 1 |
| EXP_005 | hydrolyzer | voltage | 1 |
| EXP_005 | plant | fan_speed | 1 |
| EXP_005 | plant | pump_speed | 1 |
| EXP_005 | plant | valve_state | 1 |
| EXP_006 | absorber | air_flow | 1 |
| EXP_006 | absorber | pressure_drop | 1 |
| EXP_006 | hydrolyzer | current_setpoint | 1 |
| EXP_006 | hydrolyzer | electrolyte_temperature | 1 |
| EXP_006 | hydrolyzer | flow | 1 |
| EXP_006 | hydrolyzer | power | 1 |
| EXP_006 | plant | fan_speed | 2 |

## Timestamp offsets as written

| Source | Offsets |
|---|---|
| absorber | Z |
| ambient | +02:00 |
| hydrolyzer | Z |
| plant | Z |

## Experiment window check

First reading minus experiment start, last reading minus experiment end (seconds). Window is start inclusive, end exclusive. Readings outside: 0.

| Experiment | Source | First vs start (s) | Last vs end (s) | Outside |
|---|---|---|---|---|
| EXP_001 | absorber | 0.0 | -1.0 | 0 |
| EXP_001 | ambient | 0.0 | -60.0 | 0 |
| EXP_001 | hydrolyzer | 0.0 | -1.0 | 0 |
| EXP_001 | plant | 0.0 | -1.0 | 0 |
| EXP_002 | absorber | 0.0 | -1.0 | 0 |
| EXP_002 | ambient | 0.0 | -60.0 | 0 |
| EXP_002 | hydrolyzer | 0.0 | -1.0 | 0 |
| EXP_002 | plant | 0.0 | -1.0 | 0 |
| EXP_003 | absorber | 0.0 | -1.0 | 0 |
| EXP_003 | ambient | 0.0 | -60.0 | 0 |
| EXP_003 | hydrolyzer | 0.0 | -1.0 | 0 |
| EXP_003 | plant | 0.0 | -1.0 | 0 |
| EXP_004 | absorber | 0.0 | -1.0 | 0 |
| EXP_004 | ambient | 0.0 | -60.0 | 0 |
| EXP_004 | hydrolyzer | 0.0 | -1.0 | 0 |
| EXP_004 | plant | 0.0 | -1.0 | 0 |
| EXP_005 | absorber | 0.0 | -1.0 | 0 |
| EXP_005 | ambient | 0.0 | -60.0 | 0 |
| EXP_005 | hydrolyzer | 0.0 | -1.0 | 0 |
| EXP_005 | plant | 0.0 | -1.0 | 0 |
| EXP_006 | absorber | 0.0 | -1.0 | 0 |
| EXP_006 | ambient | 0.0 | -60.0 | 0 |
| EXP_006 | hydrolyzer | 0.0 | -1.0 | 0 |
| EXP_006 | plant | 0.0 | -1.0 | 0 |

## Timing

- Started: 2026-11-23T13:38:35.074648+00:00
- Duration: 72.107 s
- Rows per second: 7211.5
- Batch size: 10000, batches sent: 52
- fingerprint check: 0.2 s
- read, validate, sort: 16.1 s
- resolve and write: 53.7 s
- count back: 1.9 s

## Per series

| Experiment | Source | Signal | CSV rows | Saved | Copies | Losers | Rejected |
|---|---|---|---|---|---|---|---|
| EXP_001 | absorber | air_flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_001 | absorber | co2_in_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_001 | absorber | co2_out_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_001 | absorber | pressure_drop | 3600 | 3600 | 0 | 0 | 0 |
| EXP_001 | absorber | solvent_flow | 3600 | 3600 | 0 | 0 | 0 |
| EXP_001 | absorber | solvent_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_001 | absorber | solvent_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_001 | ambient | ambient_pressure | 120 | 120 | 0 | 0 | 0 |
| EXP_001 | ambient | ambient_temperature | 120 | 120 | 0 | 0 | 0 |
| EXP_001 | ambient | available_solar_power | 120 | 120 | 0 | 0 | 0 |
| EXP_001 | ambient | relative_humidity | 120 | 120 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | acid_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | base_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | conductivity | 1440 | 1440 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | current | 7126 | 7126 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | current_setpoint | 7200 | 7200 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | electrolyte_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | power | 7126 | 7126 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | pressure | 7200 | 7200 | 0 | 0 | 0 |
| EXP_001 | hydrolyzer | voltage | 7126 | 7126 | 0 | 0 | 0 |
| EXP_001 | plant | fan_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_001 | plant | process_state | 7 | 7 | 0 | 0 | 0 |
| EXP_001 | plant | pump_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_001 | plant | valve_state | 3 | 3 | 0 | 0 | 0 |
| EXP_002 | absorber | air_flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_002 | absorber | co2_in_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_002 | absorber | co2_out_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_002 | absorber | pressure_drop | 3600 | 3600 | 0 | 0 | 0 |
| EXP_002 | absorber | solvent_flow | 3600 | 3600 | 0 | 0 | 0 |
| EXP_002 | absorber | solvent_pH | 1441 | 1440 | 1 | 0 | 0 |
| EXP_002 | absorber | solvent_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_002 | ambient | ambient_pressure | 120 | 120 | 0 | 0 | 0 |
| EXP_002 | ambient | ambient_temperature | 120 | 120 | 0 | 0 | 0 |
| EXP_002 | ambient | available_solar_power | 120 | 120 | 0 | 0 | 0 |
| EXP_002 | ambient | relative_humidity | 120 | 120 | 0 | 0 | 0 |
| EXP_002 | hydrolyzer | acid_pH | 1344 | 1344 | 0 | 0 | 0 |
| EXP_002 | hydrolyzer | base_pH | 1344 | 1344 | 0 | 0 | 0 |
| EXP_002 | hydrolyzer | conductivity | 1344 | 1344 | 0 | 0 | 0 |
| EXP_002 | hydrolyzer | current | 6720 | 6720 | 0 | 0 | 0 |
| EXP_002 | hydrolyzer | current_setpoint | 6721 | 6720 | 1 | 0 | 0 |
| EXP_002 | hydrolyzer | electrolyte_temperature | 1345 | 1344 | 1 | 0 | 0 |
| EXP_002 | hydrolyzer | flow | 6722 | 6720 | 2 | 0 | 0 |
| EXP_002 | hydrolyzer | power | 6723 | 6720 | 3 | 0 | 0 |
| EXP_002 | hydrolyzer | pressure | 6721 | 6720 | 1 | 0 | 0 |
| EXP_002 | hydrolyzer | voltage | 6722 | 6720 | 2 | 0 | 0 |
| EXP_002 | plant | fan_speed | 7201 | 7200 | 1 | 0 | 0 |
| EXP_002 | plant | process_state | 7 | 7 | 0 | 0 | 0 |
| EXP_002 | plant | pump_speed | 7203 | 7200 | 3 | 0 | 0 |
| EXP_002 | plant | valve_state | 3 | 3 | 0 | 0 | 0 |
| EXP_003 | absorber | air_flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | absorber | co2_in_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_003 | absorber | co2_out_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_003 | absorber | pressure_drop | 3600 | 3600 | 0 | 0 | 0 |
| EXP_003 | absorber | solvent_flow | 3600 | 3600 | 0 | 0 | 0 |
| EXP_003 | absorber | solvent_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_003 | absorber | solvent_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_003 | ambient | ambient_pressure | 120 | 120 | 0 | 0 | 0 |
| EXP_003 | ambient | ambient_temperature | 120 | 120 | 0 | 0 | 0 |
| EXP_003 | ambient | available_solar_power | 120 | 120 | 0 | 0 | 0 |
| EXP_003 | ambient | relative_humidity | 120 | 120 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | acid_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | base_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | conductivity | 1440 | 1440 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | current | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | current_setpoint | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | electrolyte_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | power | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | pressure | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | hydrolyzer | voltage | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | plant | fan_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | plant | process_state | 7 | 7 | 0 | 0 | 0 |
| EXP_003 | plant | pump_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_003 | plant | valve_state | 3 | 3 | 0 | 0 | 0 |
| EXP_004 | absorber | air_flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | absorber | co2_in_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_004 | absorber | co2_out_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_004 | absorber | pressure_drop | 3600 | 3600 | 0 | 0 | 0 |
| EXP_004 | absorber | solvent_flow | 3600 | 3600 | 0 | 0 | 0 |
| EXP_004 | absorber | solvent_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_004 | absorber | solvent_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_004 | ambient | ambient_pressure | 120 | 120 | 0 | 0 | 0 |
| EXP_004 | ambient | ambient_temperature | 120 | 120 | 0 | 0 | 0 |
| EXP_004 | ambient | available_solar_power | 120 | 120 | 0 | 0 | 0 |
| EXP_004 | ambient | relative_humidity | 120 | 120 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | acid_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | base_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | conductivity | 1440 | 1440 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | current | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | current_setpoint | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | electrolyte_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | power | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | pressure | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | hydrolyzer | voltage | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | plant | fan_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | plant | process_state | 7 | 7 | 0 | 0 | 0 |
| EXP_004 | plant | pump_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_004 | plant | valve_state | 3 | 3 | 0 | 0 | 0 |
| EXP_005 | absorber | air_flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | absorber | co2_in_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_005 | absorber | co2_out_ppm | 3600 | 3600 | 0 | 0 | 0 |
| EXP_005 | absorber | pressure_drop | 3600 | 3600 | 0 | 0 | 0 |
| EXP_005 | absorber | solvent_flow | 3600 | 3600 | 0 | 0 | 0 |
| EXP_005 | absorber | solvent_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_005 | absorber | solvent_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_005 | ambient | ambient_pressure | 120 | 120 | 0 | 0 | 0 |
| EXP_005 | ambient | ambient_temperature | 120 | 120 | 0 | 0 | 0 |
| EXP_005 | ambient | available_solar_power | 120 | 120 | 0 | 0 | 0 |
| EXP_005 | ambient | relative_humidity | 120 | 120 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | acid_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | base_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | conductivity | 1440 | 1440 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | current | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | current_setpoint | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | electrolyte_temperature | 1440 | 1440 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | flow | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | power | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | pressure | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | hydrolyzer | voltage | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | plant | fan_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | plant | process_state | 19 | 19 | 0 | 0 | 0 |
| EXP_005 | plant | pump_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_005 | plant | valve_state | 5 | 5 | 0 | 0 | 0 |
| EXP_006 | absorber | air_flow | 5281 | 5280 | 0 | 1 | 0 |
| EXP_006 | absorber | co2_in_ppm | 2640 | 2640 | 0 | 0 | 0 |
| EXP_006 | absorber | co2_out_ppm | 2640 | 2640 | 0 | 0 | 0 |
| EXP_006 | absorber | pressure_drop | 2641 | 2640 | 0 | 1 | 0 |
| EXP_006 | absorber | solvent_flow | 2640 | 2640 | 0 | 0 | 0 |
| EXP_006 | absorber | solvent_pH | 1056 | 1056 | 0 | 0 | 0 |
| EXP_006 | absorber | solvent_temperature | 1056 | 1056 | 0 | 0 | 0 |
| EXP_006 | ambient | ambient_pressure | 120 | 120 | 0 | 0 | 0 |
| EXP_006 | ambient | ambient_temperature | 120 | 120 | 0 | 0 | 0 |
| EXP_006 | ambient | available_solar_power | 120 | 120 | 0 | 0 | 0 |
| EXP_006 | ambient | relative_humidity | 120 | 120 | 0 | 0 | 0 |
| EXP_006 | hydrolyzer | acid_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_006 | hydrolyzer | base_pH | 1440 | 1440 | 0 | 0 | 0 |
| EXP_006 | hydrolyzer | conductivity | 1440 | 1440 | 0 | 0 | 0 |
| EXP_006 | hydrolyzer | current | 7200 | 7200 | 0 | 0 | 0 |
| EXP_006 | hydrolyzer | current_setpoint | 7201 | 7200 | 0 | 1 | 0 |
| EXP_006 | hydrolyzer | electrolyte_temperature | 1441 | 1440 | 0 | 1 | 0 |
| EXP_006 | hydrolyzer | flow | 7202 | 7200 | 0 | 2 | 0 |
| EXP_006 | hydrolyzer | power | 7201 | 7200 | 0 | 1 | 0 |
| EXP_006 | hydrolyzer | pressure | 7200 | 7200 | 0 | 0 | 0 |
| EXP_006 | hydrolyzer | voltage | 7200 | 7200 | 0 | 0 | 0 |
| EXP_006 | plant | fan_speed | 7203 | 7200 | 0 | 3 | 0 |
| EXP_006 | plant | process_state | 7 | 7 | 0 | 0 | 0 |
| EXP_006 | plant | pump_speed | 7200 | 7200 | 0 | 0 | 0 |
| EXP_006 | plant | valve_state | 3 | 3 | 0 | 0 | 0 |
