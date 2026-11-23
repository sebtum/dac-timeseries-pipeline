# Post-ingest profile

Counts, distributions and samples of the stored readings. Nothing here labels a reading.

- Database: `dac_raw`; windows from `data/raw/experiments.json`.
- Every query is limited to one experiment's window (start included, end excluded).
- Floats are rounded to 9 significant digits. `stddev` is the sample standard deviation.
- Percentiles are exact. Intervals and runs are in seconds.
- `unmatched` counts points of the first-named signal with no partner at that instant.

## Experiments

| experiment | start | end |
|---|---|---|
| EXP_001 | 2026-05-04T08:00:00Z | 2026-05-04T10:00:00Z |
| EXP_002 | 2026-05-11T09:00:00Z | 2026-05-11T11:00:00Z |
| EXP_003 | 2026-05-18T07:30:00Z | 2026-05-18T09:30:00Z |
| EXP_004 | 2026-03-02T08:00:00Z | 2026-03-02T10:00:00Z |
| EXP_005 | 2026-06-15T06:00:00Z | 2026-06-15T08:00:00Z |
| EXP_006 | 2026-04-20T10:00:00Z | 2026-04-20T12:00:00Z |

## Span probe

| from | to | answered | count | sum of per-experiment counts | message file |
|---|---|---|---|---|---|
| 2026-03-02T08:00:00Z | 2026-06-15T08:00:00Z | yes | 519906 | 519906 | n/a |

## EXP_001

### Values

| source | signal | unit | points | no value | GOOD | UNCERTAIN | BAD | min | p05 | median | mean | p95 | max | stddev | doc. min | doc. max | below doc. min | above doc. max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| absorber | air_flow | m³/h | 7200 | 0 | 7200 | 0 | 0 | 1170.6 | 1186.6 | 1200 | 1200.00622 | 1213.4 | 1227.2 | 8.10748362 | 1000 | 2500 | 0 | 0 |
| absorber | co2_in_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 415.4 | 418 | 420 | 420.012083 | 422 | 423.7 | 1.18822887 | 400 | 430 | 0 | 0 |
| absorber | co2_out_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 103.1 | 105.6 | 107.8 | 107.724667 | 109.7 | 111.8 | 1.26830576 | 50 | 200 | 0 | 0 |
| absorber | pressure_drop | mbar | 3600 | 0 | 3600 | 0 | 0 | 14.18 | 14.7895 | 15.23 | 15.2272333 | 15.7 | 16.12 | 0.280578058 | 10 | 65 | 0 | 0 |
| absorber | solvent_flow | L/min | 3600 | 0 | 3600 | 0 | 0 | 7.43 | 7.75 | 8 | 8.00012778 | 8.25 | 8.61 | 0.152013933 | 7 | 10 | 0 | 0 |
| absorber | solvent_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 7.374 | 7.55 | 7.649 | 7.64557639 | 7.73305 | 7.813 | 0.0571101955 | 6 | 9 | 0 | 0 |
| absorber | solvent_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 25.89 | 29.348 | 31.58 | 31.400875 | 32.86 | 33.57 | 1.15734038 | 5 | 40 | 0 | 0 |
| ambient | ambient_pressure | hPa | 120 | 0 | 120 | 0 | 0 | 1014.62 | 1014.759 | 1015.06 | 1015.07542 | 1015.4 | 1015.59 | 0.195555214 | 990 | 1030 | 0 | 0 |
| ambient | ambient_temperature | °C | 120 | 0 | 120 | 0 | 0 | 21.92 | 22.2975 | 23.65 | 23.5961667 | 24.8115 | 25.04 | 0.848634279 | -5 | 30 | 0 | 0 |
| ambient | available_solar_power | kW | 120 | 0 | 120 | 0 | 0 | 181.3 | 216.6055 | 312.47 | 310.998583 | 428.665 | 445.42 | 66.977733 | 0 | 550 | 0 | 0 |
| ambient | relative_humidity | % | 120 | 0 | 120 | 0 | 0 | 37.9 | 41.18 | 44.4 | 44.5633333 | 48.22 | 50.1 | 2.25451679 | 20 | 100 | 0 | 0 |
| hydrolyzer | acid_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 1.766 | 1.941 | 2.054 | 2.0561625 | 2.1641 | 2.578 | 0.0836579537 | 0.5 | 4 | 0 | 0 |
| hydrolyzer | base_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 11.422 | 11.9658 | 12.099 | 12.0915264 | 12.21705 | 12.411 | 0.103291228 | 10 | 13.5 | 0 | 0 |
| hydrolyzer | conductivity | mS/cm | 1440 | 0 | 1380 | 0 | 60 | 50 | 181.87 | 223 | 214.577917 | 229.5 | 239.8 | 35.1960578 | 150 | 240 | 60 | 0 |
| hydrolyzer | current | A | 7126 | 0 | 7126 | 0 | 0 | -0.48 | 136.1575 | 150 | 148.663584 | 159.495 | 210.66 | 22.3753456 | 0 | 260 | 19 | 0 |
| hydrolyzer | current_setpoint | A | 7200 | 0 | 7200 | 0 | 0 | 0 | 150 | 150 | 148.760417 | 150 | 210 | 23.5208313 | 0 | 260 | 0 | 0 |
| hydrolyzer | electrolyte_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 22.81 | 32.276 | 42.885 | 41.5162778 | 45.321 | 47.4 | 4.04179331 | 0 | 45 | 0 | 88 |
| hydrolyzer | flow | L/min | 7200 | 0 | 7200 | 0 | 0 | 29.27 | 40.67 | 42 | 41.88735 | 43.2 | 47.8 | 1.82005443 | 25 | 55 | 0 | 0 |
| hydrolyzer | power | W | 7126 | 0 | 7126 | 0 | 0 | -33 | 13661.725 | 15120.2 | 15169.8683 | 21089.825 | 23334 | 2718.73827 | 0 | 35000 | 20 | 0 |
| hydrolyzer | pressure | bar | 7200 | 0 | 7200 | 0 | 0 | 2.246 | 2.53095 | 2.6 | 2.59688028 | 2.668 | 2.818 | 0.0536597979 | 2 | 3 | 0 | 0 |
| hydrolyzer | voltage | V | 7126 | 0 | 7126 | 0 | 0 | 68.19 | 99.4425 | 100.73 | 100.753901 | 105.1775 | 412 | 5.79500167 | 60 | 130 | 0 | 1 |
| plant | fan_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 881.5 | 891.7 | 900 | 900.000486 | 908.2 | 920 | 5.00186475 | 800 | 1600 | 0 | 0 |
| plant | pump_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 508.7 | 515 | 520 | 520.009194 | 525 | 530.8 | 3.01656793 | 450 | 650 | 0 | 0 |

### Text signals

| source | signal | points | no value | GOOD | UNCERTAIN | BAD | values |
|---|---|---|---|---|---|---|---|
| plant | process_state | 7 | 0 | 7 | 0 | 0 | LOAD_CHANGE: 2, SHUTDOWN: 1, STARTUP: 1, STEADY_STATE: 3 |
| plant | valve_state | 3 | 0 | 3 | 0 | 0 | CLOSED: 2, OPEN: 1 |

### Intervals between points (seconds)

| signal | nominal | count | min | median | p95 | max | over 2x nominal | over 10x nominal | seconds in over-2x | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| air_flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:01Z (1 s) |
| co2_in_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:02Z (2 s) |
| co2_out_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:02Z (2 s) |
| pressure_drop | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:02Z (2 s) |
| solvent_flow | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:02Z (2 s) |
| solvent_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:05Z (5 s) |
| solvent_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:05Z (5 s) |
| ambient_pressure | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:01:00Z (60 s) |
| ambient_temperature | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:01:00Z (60 s) |
| available_solar_power | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:01:00Z (60 s) |
| relative_humidity | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:01:00Z (60 s) |
| acid_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:05Z (5 s) |
| base_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:05Z (5 s) |
| conductivity | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:05Z (5 s) |
| current | 1 | 7125 | 1 | 1 | 1 | 29 | 4 | 3 | 78 | 2026-05-04T09:31:39Z to 2026-05-04T09:32:08Z (29 s) |
| current_setpoint | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:01Z (1 s) |
| electrolyte_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:05Z (5 s) |
| flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:01Z (1 s) |
| power | 1 | 7125 | 1 | 1 | 1 | 29 | 4 | 3 | 78 | 2026-05-04T09:31:39Z to 2026-05-04T09:32:08Z (29 s) |
| pressure | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:01Z (1 s) |
| voltage | 1 | 7125 | 1 | 1 | 1 | 29 | 4 | 3 | 78 | 2026-05-04T09:31:39Z to 2026-05-04T09:32:08Z (29 s) |
| fan_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:01Z (1 s) |
| process_state | n/a | 6 | 133 | 158.5 | 3312.75 | 3467 | n/a | n/a | n/a | 2026-05-04T08:57:13Z to 2026-05-04T09:55:00Z (3467 s) |
| pump_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:01Z (1 s) |
| valve_state | n/a | 2 | 20 | 3585 | 6793.5 | 7150 | n/a | n/a | n/a | 2026-05-04T08:00:20Z to 2026-05-04T09:59:30Z (7150 s) |

### Runs of identical values

| signal | runs | median samples | max samples | max seconds | longest run |
|---|---|---|---|---|---|
| air_flow | 7176 | 1 | 2 | 1 | 2026-05-04T08:04:12Z to 2026-05-04T08:04:13Z: 2 samples of 1188.8 |
| co2_in_ppm | 3527 | 1 | 3 | 4 | 2026-05-04T08:27:20Z to 2026-05-04T08:27:24Z: 3 samples of 420.3 |
| co2_out_ppm | 3459 | 1 | 3 | 4 | 2026-05-04T08:29:56Z to 2026-05-04T08:30:00Z: 3 samples of 106.8 |
| pressure_drop | 3539 | 1 | 2 | 2 | 2026-05-04T08:00:44Z to 2026-05-04T08:00:46Z: 2 samples of 15.23 |
| solvent_flow | 3526 | 1 | 3 | 4 | 2026-05-04T08:19:54Z to 2026-05-04T08:19:58Z: 3 samples of 8 |
| solvent_pH | 1428 | 1 | 3 | 10 | 2026-05-04T09:28:35Z to 2026-05-04T09:28:45Z: 3 samples of 7.601 |
| solvent_temperature | 1425 | 1 | 2 | 5 | 2026-05-04T08:11:35Z to 2026-05-04T08:11:40Z: 2 samples of 30.69 |
| ambient_pressure | 112 | 1 | 3 | 120 | 2026-05-04T08:49:00Z to 2026-05-04T08:51:00Z: 3 samples of 1015.09 |
| ambient_temperature | 118 | 1 | 2 | 60 | 2026-05-04T08:41:00Z to 2026-05-04T08:42:00Z: 2 samples of 22.98 |
| available_solar_power | 120 | 1 | 1 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:00Z: 1 samples of 200.71 |
| relative_humidity | 118 | 1 | 2 | 60 | 2026-05-04T08:05:00Z to 2026-05-04T08:06:00Z: 2 samples of 46.9 |
| acid_pH | 1434 | 1 | 2 | 5 | 2026-05-04T08:20:05Z to 2026-05-04T08:20:10Z: 2 samples of 2.033 |
| base_pH | 1433 | 1 | 2 | 5 | 2026-05-04T08:08:15Z to 2026-05-04T08:08:20Z: 2 samples of 12.054 |
| conductivity | 1364 | 1 | 60 | 295 | 2026-05-04T09:00:00Z to 2026-05-04T09:04:55Z: 60 samples of 50 |
| current | 7055 | 1 | 3 | 2 | 2026-05-04T08:44:49Z to 2026-05-04T08:44:51Z: 3 samples of 149.91 |
| current_setpoint | 303 | 1 | 3601 | 3600 | 2026-05-04T08:55:00Z to 2026-05-04T09:55:00Z: 3601 samples of 150 |
| electrolyte_temperature | 1422 | 1 | 2 | 5 | 2026-05-04T08:21:35Z to 2026-05-04T08:21:40Z: 2 samples of 40.59 |
| flow | 7155 | 1 | 2 | 1 | 2026-05-04T08:08:51Z to 2026-05-04T08:08:52Z: 2 samples of 41.7 |
| power | 7117 | 1 | 2 | 1 | 2026-05-04T08:23:20Z to 2026-05-04T08:23:21Z: 2 samples of 15165.2 |
| pressure | 7141 | 1 | 2 | 1 | 2026-05-04T08:00:48Z to 2026-05-04T08:00:49Z: 2 samples of 2.341 |
| voltage | 6965 | 1 | 3 | 2 | 2026-05-04T08:03:14Z to 2026-05-04T08:03:16Z: 3 samples of 105.31 |
| fan_speed | 7156 | 1 | 3 | 2 | 2026-05-04T09:30:39Z to 2026-05-04T09:30:41Z: 3 samples of 904.8 |
| process_state | 7 | 1 | 1 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:00Z: 1 samples of STARTUP |
| pump_speed | 7129 | 1 | 2 | 1 | 2026-05-04T08:03:40Z to 2026-05-04T08:03:41Z: 2 samples of 521.7 |
| valve_state | 3 | 1 | 1 | 0 | 2026-05-04T08:00:00Z to 2026-05-04T08:00:00Z: 1 samples of CLOSED |

### Step-to-step change (each value minus the previous)

| signal | count | mean | stddev | median abs | p95 abs | max abs |
|---|---|---|---|---|---|---|
| air_flow | 7199 | -0.00102792054 | 11.3844631 | 7.7 | 22.3 | 43.1 |
| co2_in_ppm | 3599 | 0.000666851903 | 1.68916193 | 1.1 | 3.3 | 5.7 |
| co2_out_ppm | 3599 | 0.00119477633 | 1.13707602 | 0.8 | 2.2 | 4.1 |
| pressure_drop | 3599 | 0.000183384273 | 0.359453788 | 0.24 | 0.701 | 1.26 |
| solvent_flow | 3599 | 8.33564879e-06 | 0.212810999 | 0.14 | 0.42 | 0.86 |
| solvent_pH | 1439 | 8.75608061e-05 | 0.0721988203 | 0.049 | 0.138 | 0.264 |
| solvent_temperature | 1439 | 0.00478804726 | 0.440128719 | 0.3 | 0.861 | 1.62 |
| ambient_pressure | 119 | 0.00512605042 | 0.0814161266 | 0.06 | 0.16 | 0.25 |
| ambient_temperature | 119 | 0.021092437 | 0.201909486 | 0.12 | 0.392 | 0.63 |
| available_solar_power | 119 | 1.3705042 | 20.6631374 | 15.22 | 38.217 | 61.04 |
| relative_humidity | 119 | -0.0420168067 | 1.88232167 | 1.3 | 3.72 | 5.6 |
| acid_pH | 1439 | -5.90687978e-05 | 0.0701693956 | 0.047 | 0.141 | 0.231 |
| base_pH | 1439 | 0.000173036831 | 0.07057348 | 0.047 | 0.136 | 0.286 |
| conductivity | 1439 | 0.0176511466 | 7.08827175 | 1.8 | 5.6 | 174.7 |
| current | 7125 | 0.00245754386 | 0.498201717 | 0.31 | 0.91 | 4.57 |
| current_setpoint | 7199 | 6.94540908e-05 | 2.03384635 | 0 | 0 | 150 |
| electrolyte_temperature | 1439 | 0.01095205 | 0.281811145 | 0.19 | 0.55 | 0.92 |
| flow | 7199 | 0.000218085845 | 0.564235678 | 0.38 | 1.11 | 2.04 |
| power | 7125 | 0.179508772 | 117.859773 | 37.2 | 113.38 | 6049.8 |
| pressure | 7199 | 1.30573691e-05 | 0.0422485711 | 0.029 | 0.081 | 0.195 |
| voltage | 7125 | 0.000684912281 | 5.21567987 | 0.15 | 0.43 | 311.24 |
| fan_speed | 7199 | -0.00148631754 | 7.09840464 | 4.8 | 13.81 | 27.3 |
| pump_speed | 7199 | -0.000805667454 | 4.26780687 | 2.9 | 8.4 | 17.1 |

### Relationship: power vs voltage x current

| measure | value |
|---|---|
| instants_matched | 7126 |
| instants_unmatched | 0 |
| corr | 0.937352522 |
| residual_mean | 95.0611409 |
| residual_stddev | 954.084011 |
| residual_median | 0.0192 |
| residual_p05 | -0.8676 |
| residual_p95 | 0.9484 |
| residual_max_abs | 46699.16 |
| relative_residual_median | 2.65333293e-05 |
| relative_residual_p95 | 7.11451909e-05 |
| power_zero_instants | 0 |
| slope | 0.956918542 |
| intercept | 744.505814 |
| r2 | 0.87862975 |

### Relationship: co2 out vs co2 in

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | 0.00907053093 |
| ratio_median | 0.256550738 |
| ratio_p05 | 0.251424299 |
| ratio_p95 | 0.261369076 |
| out_at_or_above_in | 0 |

### Relationship: current vs current setpoint

| measure | value |
|---|---|
| instants_matched | 7126 |
| instants_unmatched | 0 |
| corr | 0.925960091 |
| difference_mean | -0.0839601459 |
| difference_stddev | 8.94092774 |
| difference_median | 0.01 |
| difference_max_abs | 145.84 |
| best_lag_s | 24 |
| corr_at_best_lag | 0.971193234 |

### Relationship: pressure drop vs air flow

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | 0.0210987994 |
| slope_air_flow | 0.000728158176 |
| intercept_air_flow | 14.3535137 |
| r2_air_flow | 0.000445159336 |
| slope_air_flow_sq | 3.00576825e-07 |
| intercept_air_flow_sq | 14.7944524 |
| r2_air_flow_sq | 0.000436884422 |

## EXP_002

### Values

| source | signal | unit | points | no value | GOOD | UNCERTAIN | BAD | min | p05 | median | mean | p95 | max | stddev | doc. min | doc. max | below doc. min | above doc. max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| absorber | air_flow | m³/h | 7200 | 0 | 7200 | 0 | 0 | 1170.6 | 1186.9 | 1200 | 1200.18032 | 1213.3 | 1232.4 | 8.02872587 | 1000 | 2500 | 0 | 0 |
| absorber | co2_in_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 415.5 | 418 | 420 | 419.990694 | 421.9 | 424.9 | 1.21281917 | 400 | 430 | 0 | 0 |
| absorber | co2_out_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 104.2 | 106 | 107.7 | 107.690778 | 109.4 | 111.1 | 1.04308595 | 50 | 200 | 0 | 0 |
| absorber | pressure_drop | mbar | 3600 | 0 | 3600 | 0 | 0 | 14.41 | 14.77 | 15.22 | 15.2208083 | 15.69 | 16.23 | 0.278948303 | 10 | 65 | 0 | 0 |
| absorber | solvent_flow | L/min | 3600 | 0 | 3600 | 0 | 0 | 7.43 | 7.76 | 8 | 8.00077778 | 8.25 | 8.5 | 0.151259988 | 7 | 10 | 0 | 0 |
| absorber | solvent_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 7.393 | 7.63395 | 7.748 | 7.74297431 | 7.83705 | 7.951 | 0.0666232708 | 6 | 9 | 0 | 0 |
| absorber | solvent_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 26.59 | 31.2095 | 32.99 | 32.8092083 | 33.89 | 34.38 | 0.970243981 | 5 | 40 | 0 | 0 |
| ambient | ambient_pressure | hPa | 120 | 0 | 120 | 0 | 0 | 1011.7 | 1011.919 | 1012.18 | 1012.17217 | 1012.401 | 1012.55 | 0.151470014 | 990 | 1030 | 0 | 0 |
| ambient | ambient_temperature | °C | 120 | 0 | 120 | 0 | 0 | 23.87 | 24.098 | 25.07 | 24.9984167 | 25.7305 | 25.97 | 0.549821966 | -5 | 30 | 0 | 0 |
| ambient | available_solar_power | kW | 120 | 0 | 120 | 0 | 0 | 274.06 | 306.4175 | 373.31 | 382.448917 | 496.657 | 532.62 | 57.1238512 | 0 | 550 | 0 | 0 |
| ambient | relative_humidity | % | 120 | 0 | 120 | 0 | 0 | 33.2 | 33.9 | 36.95 | 37.1258333 | 40.805 | 41.9 | 1.97452242 | 20 | 100 | 0 | 0 |
| hydrolyzer | acid_pH | n/a | 1344 | 0 | 1344 | 0 | 0 | 1.358 | 1.61115 | 1.75 | 1.76158259 | 1.92685 | 2.583 | 0.126972218 | 0.5 | 4 | 0 | 0 |
| hydrolyzer | base_pH | n/a | 1344 | 0 | 1344 | 0 | 0 | 11.455 | 12.2533 | 12.499 | 12.4862165 | 12.6714 | 12.99 | 0.164109279 | 10 | 13.5 | 0 | 0 |
| hydrolyzer | conductivity | mS/cm | 1344 | 0 | 1344 | 0 | 0 | 174 | 231.045 | 258.6 | 255.991295 | 270.84 | 285.3 | 13.6387497 | 150 | 240 | 0 | 1240 |
| hydrolyzer | current | A | 6720 | 0 | 6720 | 0 | 0 | -0.42 | 218.969 | 249.99 | 247.601807 | 276.2445 | 350.55 | 38.4990919 | 0 | 260 | 15 | 375 |
| hydrolyzer | current_setpoint | A | 6720 | 0 | 6720 | 0 | 0 | 0 | 250 | 250 | 247.786458 | 250 | 350 | 40.5734656 | 0 | 260 | 0 | 300 |
| hydrolyzer | electrolyte_temperature | °C | 1344 | 0 | 1344 | 0 | 0 | 23.82 | 42.264 | 59.63 | 57.7730804 | 65.0425 | 68.41 | 7.038212 | 0 | 45 | 0 | 1263 |
| hydrolyzer | flow | L/min | 6720 | 0 | 6720 | 0 | 0 | 29.04 | 47.2875 | 49.99 | 49.8025804 | 52.302 | 58.91 | 3.09981933 | 25 | 55 | 0 | 281 |
| hydrolyzer | power | W | 6720 | 0 | 6720 | 0 | 0 | -28.5 | 24426.16 | 27627.65 | 27631.6383 | 30754.77 | 42604.2 | 4925.17112 | 0 | 35000 | 15 | 296 |
| hydrolyzer | pressure | bar | 6720 | 0 | 6720 | 0 | 0 | 2.245 | 2.716 | 2.8 | 2.79535997 | 2.88005 | 3.074 | 0.0822672168 | 2 | 3 | 0 | 103 |
| hydrolyzer | voltage | V | 6720 | 0 | 6720 | 0 | 0 | 68.13 | 107.04 | 110.49 | 110.770159 | 120.93 | 124.73 | 6.17827744 | 60 | 130 | 0 | 0 |
| plant | fan_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 879.8 | 891.6 | 900 | 899.952931 | 908.2 | 917.6 | 5.05182749 | 800 | 1600 | 0 | 0 |
| plant | pump_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 509.5 | 515 | 520 | 519.998792 | 524.9 | 531.3 | 3.01076043 | 450 | 650 | 0 | 0 |

### Text signals

| source | signal | points | no value | GOOD | UNCERTAIN | BAD | values |
|---|---|---|---|---|---|---|---|
| plant | process_state | 7 | 0 | 7 | 0 | 0 | LOAD_CHANGE: 2, SHUTDOWN: 1, STARTUP: 1, STEADY_STATE: 3 |
| plant | valve_state | 3 | 0 | 3 | 0 | 0 | CLOSED: 2, OPEN: 1 |

### Intervals between points (seconds)

| signal | nominal | count | min | median | p95 | max | over 2x nominal | over 10x nominal | seconds in over-2x | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| air_flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:01Z (1 s) |
| co2_in_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:02Z (2 s) |
| co2_out_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:02Z (2 s) |
| pressure_drop | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:02Z (2 s) |
| solvent_flow | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:02Z (2 s) |
| solvent_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:05Z (5 s) |
| solvent_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:05Z (5 s) |
| ambient_pressure | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:01:00Z (60 s) |
| ambient_temperature | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:01:00Z (60 s) |
| available_solar_power | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:01:00Z (60 s) |
| relative_humidity | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:01:00Z (60 s) |
| acid_pH | 5 | 1343 | 5 | 5 | 5 | 485 | 1 | 1 | 485 | 2026-05-11T10:05:55Z to 2026-05-11T10:14:00Z (485 s) |
| base_pH | 5 | 1343 | 5 | 5 | 5 | 485 | 1 | 1 | 485 | 2026-05-11T10:05:55Z to 2026-05-11T10:14:00Z (485 s) |
| conductivity | 5 | 1343 | 5 | 5 | 5 | 485 | 1 | 1 | 485 | 2026-05-11T10:05:55Z to 2026-05-11T10:14:00Z (485 s) |
| current | 1 | 6719 | 1 | 1 | 1 | 481 | 1 | 1 | 481 | 2026-05-11T10:05:59Z to 2026-05-11T10:14:00Z (481 s) |
| current_setpoint | 1 | 6719 | 1 | 1 | 1 | 481 | 1 | 1 | 481 | 2026-05-11T10:05:59Z to 2026-05-11T10:14:00Z (481 s) |
| electrolyte_temperature | 5 | 1343 | 5 | 5 | 5 | 485 | 1 | 1 | 485 | 2026-05-11T10:05:55Z to 2026-05-11T10:14:00Z (485 s) |
| flow | 1 | 6719 | 1 | 1 | 1 | 481 | 1 | 1 | 481 | 2026-05-11T10:05:59Z to 2026-05-11T10:14:00Z (481 s) |
| power | 1 | 6719 | 1 | 1 | 1 | 481 | 1 | 1 | 481 | 2026-05-11T10:05:59Z to 2026-05-11T10:14:00Z (481 s) |
| pressure | 1 | 6719 | 1 | 1 | 1 | 481 | 1 | 1 | 481 | 2026-05-11T10:05:59Z to 2026-05-11T10:14:00Z (481 s) |
| voltage | 1 | 6719 | 1 | 1 | 1 | 481 | 1 | 1 | 481 | 2026-05-11T10:05:59Z to 2026-05-11T10:14:00Z (481 s) |
| fan_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:01Z (1 s) |
| process_state | n/a | 6 | 150 | 150 | 3300 | 3450 | n/a | n/a | n/a | 2026-05-11T09:57:30Z to 2026-05-11T10:55:00Z (3450 s) |
| pump_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:01Z (1 s) |
| valve_state | n/a | 2 | 20 | 3585 | 6793.5 | 7150 | n/a | n/a | n/a | 2026-05-11T09:00:20Z to 2026-05-11T10:59:30Z (7150 s) |

### Runs of identical values

| signal | runs | median samples | max samples | max seconds | longest run |
|---|---|---|---|---|---|
| air_flow | 7175 | 1 | 2 | 1 | 2026-05-11T09:04:07Z to 2026-05-11T09:04:08Z: 2 samples of 1197.6 |
| co2_in_ppm | 3511 | 1 | 3 | 4 | 2026-05-11T10:06:30Z to 2026-05-11T10:06:34Z: 3 samples of 419.5 |
| co2_out_ppm | 3479 | 1 | 3 | 4 | 2026-05-11T09:40:18Z to 2026-05-11T09:40:22Z: 3 samples of 107.7 |
| pressure_drop | 3564 | 1 | 2 | 2 | 2026-05-11T09:02:22Z to 2026-05-11T09:02:24Z: 2 samples of 15.1 |
| solvent_flow | 3549 | 1 | 3 | 4 | 2026-05-11T09:13:12Z to 2026-05-11T09:13:16Z: 3 samples of 8.11 |
| solvent_pH | 1432 | 1 | 2 | 5 | 2026-05-11T09:02:05Z to 2026-05-11T09:02:10Z: 2 samples of 7.506 |
| solvent_temperature | 1426 | 1 | 2 | 5 | 2026-05-11T09:09:10Z to 2026-05-11T09:09:15Z: 2 samples of 31.69 |
| ambient_pressure | 119 | 1 | 2 | 60 | 2026-05-11T09:24:00Z to 2026-05-11T09:25:00Z: 2 samples of 1012.35 |
| ambient_temperature | 119 | 1 | 2 | 60 | 2026-05-11T09:06:00Z to 2026-05-11T09:07:00Z: 2 samples of 24.06 |
| available_solar_power | 120 | 1 | 1 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:00Z: 1 samples of 314.75 |
| relative_humidity | 117 | 1 | 2 | 60 | 2026-05-11T09:50:00Z to 2026-05-11T09:51:00Z: 2 samples of 37.8 |
| acid_pH | 1334 | 1 | 2 | 5 | 2026-05-11T09:01:10Z to 2026-05-11T09:01:15Z: 2 samples of 2.324 |
| base_pH | 1335 | 1 | 2 | 5 | 2026-05-11T09:01:30Z to 2026-05-11T09:01:35Z: 2 samples of 11.784 |
| conductivity | 1329 | 1 | 3 | 10 | 2026-05-11T09:58:25Z to 2026-05-11T09:58:35Z: 3 samples of 265.5 |
| current | 6671 | 1 | 2 | 1 | 2026-05-11T09:02:08Z to 2026-05-11T09:02:09Z: 2 samples of 236.31 |
| current_setpoint | 303 | 1 | 3121 | 3600 | 2026-05-11T09:55:00Z to 2026-05-11T10:55:00Z: 3121 samples of 250 |
| electrolyte_temperature | 1327 | 1 | 2 | 5 | 2026-05-11T09:06:00Z to 2026-05-11T09:06:05Z: 2 samples of 43.24 |
| flow | 6679 | 1 | 2 | 1 | 2026-05-11T09:00:50Z to 2026-05-11T09:00:51Z: 2 samples of 34.57 |
| power | 6717 | 1 | 2 | 1 | 2026-05-11T09:17:30Z to 2026-05-11T09:17:31Z: 2 samples of 27995.7 |
| pressure | 6668 | 1 | 2 | 1 | 2026-05-11T09:00:25Z to 2026-05-11T09:00:26Z: 2 samples of 2.285 |
| voltage | 6590 | 1 | 2 | 1 | 2026-05-11T09:00:17Z to 2026-05-11T09:00:18Z: 2 samples of 68.16 |
| fan_speed | 7164 | 1 | 2 | 1 | 2026-05-11T09:04:34Z to 2026-05-11T09:04:35Z: 2 samples of 895.8 |
| process_state | 7 | 1 | 1 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:00Z: 1 samples of STARTUP |
| pump_speed | 7139 | 1 | 2 | 1 | 2026-05-11T09:01:16Z to 2026-05-11T09:01:17Z: 2 samples of 519.7 |
| valve_state | 3 | 1 | 1 | 0 | 2026-05-11T09:00:00Z to 2026-05-11T09:00:00Z: 1 samples of CLOSED |

### Step-to-step change (each value minus the previous)

| signal | count | mean | stddev | median abs | p95 abs | max abs |
|---|---|---|---|---|---|---|
| air_flow | 7199 | -6.94540908e-05 | 11.4213419 | 7.7 | 22.3 | 48.9 |
| co2_in_ppm | 3599 | -0.000166712976 | 1.70294026 | 1.1 | 3.4 | 6.6 |
| co2_out_ppm | 3599 | 0.0013614893 | 1.13103466 | 0.8 | 2.2 | 4.6 |
| pressure_drop | 3599 | 0.000158377327 | 0.351796394 | 0.24 | 0.69 | 1.24 |
| solvent_flow | 3599 | 2.7785496e-05 | 0.216802652 | 0.15 | 0.42 | 0.75 |
| solvent_pH | 1439 | 0.000134815844 | 0.0706420675 | 0.047 | 0.14 | 0.256 |
| solvent_temperature | 1439 | 0.0053161918 | 0.425579725 | 0.29 | 0.85 | 1.41 |
| ambient_pressure | 119 | 0.0012605042 | 0.081537707 | 0.06 | 0.141 | 0.19 |
| ambient_temperature | 119 | 0.0124369748 | 0.223731704 | 0.16 | 0.411 | 0.69 |
| available_solar_power | 119 | 0.747478992 | 25.9799169 | 15.31 | 52.954 | 70.41 |
| relative_humidity | 119 | -0.0554621849 | 2.18553401 | 1.4 | 4.36 | 6.2 |
| acid_pH | 1343 | -0.000226358898 | 0.0670906764 | 0.045 | 0.1339 | 0.22 |
| base_pH | 1343 | 0.000256142964 | 0.0720961432 | 0.047 | 0.144 | 0.24 |
| conductivity | 1343 | 0.0333581534 | 2.9315776 | 2 | 5.7 | 11.5 |
| current | 6719 | 0.00434737312 | 4.3537358 | 0.31 | 1.03 | 249.76 |
| current_setpoint | 6719 | 0.000123530287 | 3.50875338 | 0 | 0 | 250 |
| electrolyte_temperature | 1343 | 0.020461653 | 0.28548037 | 0.19 | 0.56 | 0.88 |
| flow | 6719 | 0.00042565858 | 0.569325526 | 0.38 | 1.12 | 2.14 |
| power | 6719 | 0.327935705 | 90.6475436 | 52.2 | 162.43 | 595.9 |
| pressure | 6719 | 1.42878405e-05 | 0.0416737078 | 0.028 | 0.081 | 0.148 |
| voltage | 6719 | 0.00103735675 | 0.235050453 | 0.15 | 0.44 | 2.15 |
| fan_speed | 7199 | -0.000666759272 | 7.18417533 | 4.8 | 14.1 | 32.6 |
| pump_speed | 7199 | -0.000430615363 | 4.24752856 | 2.9 | 8.2 | 17.1 |

### Relationship: power vs voltage x current

| measure | value |
|---|---|
| instants_matched | 6720 |
| instants_unmatched | 0 |
| corr | 0.997661731 |
| residual_mean | 4.13677775 |
| residual_stddev | 337.398614 |
| residual_median | 0.0276 |
| residual_p05 | -1.254435 |
| residual_p95 | 1.32177 |
| residual_max_abs | 27658.4 |
| relative_residual_median | 2.26720879e-05 |
| relative_residual_p95 | 5.28094547e-05 |
| power_zero_instants | 0 |
| slope | 0.99533554 |
| intercept | 133.004146 |
| r2 | 0.99532893 |

### Relationship: co2 out vs co2 in

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | 0.00624446149 |
| ratio_median | 0.256431636 |
| ratio_p05 | 0.252194335 |
| ratio_p95 | 0.260724539 |
| out_at_or_above_in | 0 |

### Relationship: current vs current setpoint

| measure | value |
|---|---|
| instants_matched | 6720 |
| instants_unmatched | 0 |
| corr | 0.923062045 |
| difference_mean | -0.184651786 |
| difference_stddev | 15.6417261 |
| difference_median | 0 |
| difference_max_abs | 250 |
| best_lag_s | 23 |
| corr_at_best_lag | 0.967641729 |

### Relationship: pressure drop vs air flow

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | 0.0103475303 |
| slope_air_flow | 0.00035661272 |
| intercept_air_flow | 14.7927679 |
| r2_air_flow | 0.000107071383 |
| slope_air_flow_sq | 1.46477934e-07 |
| intercept_air_flow_sq | 15.0097668 |
| r2_air_flow_sq | 0.000104066091 |

## EXP_003

### Values

| source | signal | unit | points | no value | GOOD | UNCERTAIN | BAD | min | p05 | median | mean | p95 | max | stddev | doc. min | doc. max | below doc. min | above doc. max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| absorber | air_flow | m³/h | 7200 | 0 | 7200 | 0 | 0 | 2373.4 | 2387.1 | 2400 | 2399.99429 | 2413.1 | 2434.2 | 7.94464383 | 1000 | 2500 | 0 | 0 |
| absorber | co2_in_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 415.6 | 418 | 420 | 420.002417 | 422 | 424 | 1.20603154 | 400 | 430 | 0 | 0 |
| absorber | co2_out_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 142.4 | 145.2 | 147.7 | 147.769194 | 150.4 | 152.6 | 1.63330283 | 50 | 200 | 0 | 0 |
| absorber | pressure_drop | mbar | 3600 | 0 | 3600 | 0 | 0 | 59.26 | 59.99 | 60.91 | 60.9016556 | 61.83 | 62.61 | 0.573616202 | 10 | 65 | 0 | 0 |
| absorber | solvent_flow | L/min | 3600 | 0 | 3600 | 0 | 0 | 7.53 | 7.76 | 8 | 8.00364167 | 8.25 | 8.57 | 0.149426576 | 7 | 10 | 0 | 0 |
| absorber | solvent_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 7.397 | 7.554 | 7.648 | 7.66046111 | 7.736 | 27.4 | 0.523709444 | 6 | 9 | 0 | 1 |
| absorber | solvent_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 24.91 | 27.91 | 30.22 | 30.1360486 | 32 | 32.77 | 1.30950044 | 5 | 40 | 0 | 0 |
| ambient | ambient_pressure | hPa | 120 | 0 | 120 | 0 | 0 | 1016.87 | 1016.969 | 1017.4 | 1017.3755 | 1017.6405 | 1017.73 | 0.183924765 | 990 | 1030 | 0 | 0 |
| ambient | ambient_temperature | °C | 120 | 0 | 120 | 0 | 0 | 20.48 | 20.721 | 22.48 | 22.40075 | 23.9805 | 24.22 | 1.07899748 | -5 | 30 | 0 | 0 |
| ambient | available_solar_power | kW | 120 | 0 | 120 | 0 | 0 | 148.34 | 172.2205 | 307.34 | 288.4725 | 403.0685 | 418.41 | 80.4820199 | 0 | 550 | 0 | 0 |
| ambient | relative_humidity | % | 120 | 0 | 120 | 0 | 0 | 34.2 | 34.9 | 38.8 | 38.8708333 | 42.72 | 45.2 | 2.35594709 | 20 | 100 | 0 | 0 |
| hydrolyzer | acid_pH | n/a | 1440 | 0 | 1400 | 0 | 40 | 1.805 | 1.938 | 2.054 | 2.13197917 | 2.30805 | 4.8 | 0.459113367 | 0.5 | 4 | 0 | 40 |
| hydrolyzer | base_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 11.354 | 11.958 | 12.103 | 12.0922243 | 12.21805 | 12.402 | 0.101855041 | 10 | 13.5 | 0 | 0 |
| hydrolyzer | conductivity | mS/cm | 1440 | 0 | 1440 | 0 | 0 | 174.9 | 206.995 | 222 | 220.523403 | 228.805 | 239.6 | 7.76144412 | 150 | 240 | 0 | 0 |
| hydrolyzer | current | A | 7200 | 0 | 7200 | 0 | 0 | -0.66 | 136.9025 | 149.995 | 148.670883 | 158.8485 | 210.44 | 22.250139 | 0 | 260 | 16 | 0 |
| hydrolyzer | current_setpoint | A | 7200 | 0 | 7200 | 0 | 0 | 0 | 150 | 150 | 148.760417 | 150 | 210 | 23.5208313 | 0 | 260 | 0 | 0 |
| hydrolyzer | electrolyte_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 21.54 | 31.019 | 41.85 | 40.3784306 | 44.231 | 46.28 | 4.09040478 | 0 | 45 | 0 | 39 |
| hydrolyzer | flow | L/min | 7200 | 0 | 7200 | 0 | 0 | 29.42 | 40.689 | 42 | 41.8894486 | 43.2 | 47.87 | 1.8250176 | 25 | 55 | 0 | 0 |
| hydrolyzer | power | W | 7200 | 0 | 7200 | 0 | 0 | -45.3 | 13793.14 | 15169.1 | 15125.1865 | 16114.425 | 23459.4 | 2605.46541 | 0 | 35000 | 16 | 0 |
| hydrolyzer | pressure | bar | 7200 | 0 | 7200 | 0 | 0 | 2.229 | 2.53 | 2.6 | 2.59703056 | 2.666 | 2.823 | 0.0538725573 | 2 | 3 | 0 | 0 |
| hydrolyzer | voltage | V | 7200 | 0 | 7200 | 0 | 0 | 68.13 | 99.8395 | 101.08 | 101.085307 | 105.51 | 111.98 | 4.51833194 | 60 | 130 | 0 | 0 |
| plant | fan_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 0 | 1492 | 1500.1 | 1499.84819 | 1508.3 | 1519.7 | 18.3732031 | 800 | 1600 | 1 | 0 |
| plant | pump_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 509.6 | 515.1 | 520 | 519.994042 | 524.905 | 532.5 | 2.99272894 | 450 | 650 | 0 | 0 |

### Text signals

| source | signal | points | no value | GOOD | UNCERTAIN | BAD | values |
|---|---|---|---|---|---|---|---|
| plant | process_state | 7 | 0 | 7 | 0 | 0 | LOAD_CHANGE: 2, SHUTDOWN: 1, STARTUP: 1, STEADY_STATE: 3 |
| plant | valve_state | 3 | 0 | 3 | 0 | 0 | CLOSED: 2, OPEN: 1 |

### Intervals between points (seconds)

| signal | nominal | count | min | median | p95 | max | over 2x nominal | over 10x nominal | seconds in over-2x | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| air_flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| co2_in_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:02Z (2 s) |
| co2_out_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:02Z (2 s) |
| pressure_drop | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:02Z (2 s) |
| solvent_flow | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:02Z (2 s) |
| solvent_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:05Z (5 s) |
| solvent_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:05Z (5 s) |
| ambient_pressure | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:31:00Z (60 s) |
| ambient_temperature | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:31:00Z (60 s) |
| available_solar_power | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:31:00Z (60 s) |
| relative_humidity | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:31:00Z (60 s) |
| acid_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:05Z (5 s) |
| base_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:05Z (5 s) |
| conductivity | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:05Z (5 s) |
| current | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| current_setpoint | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| electrolyte_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:05Z (5 s) |
| flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| power | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| pressure | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| voltage | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| fan_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| process_state | n/a | 6 | 133 | 158.5 | 3312.75 | 3467 | n/a | n/a | n/a | 2026-05-18T08:27:13Z to 2026-05-18T09:25:00Z (3467 s) |
| pump_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:01Z (1 s) |
| valve_state | n/a | 2 | 20 | 3585 | 6793.5 | 7150 | n/a | n/a | n/a | 2026-05-18T07:30:20Z to 2026-05-18T09:29:30Z (7150 s) |

### Runs of identical values

| signal | runs | median samples | max samples | max seconds | longest run |
|---|---|---|---|---|---|
| air_flow | 7172 | 1 | 2 | 1 | 2026-05-18T07:32:10Z to 2026-05-18T07:32:11Z: 2 samples of 2395.7 |
| co2_in_ppm | 3513 | 1 | 3 | 4 | 2026-05-18T08:04:38Z to 2026-05-18T08:04:42Z: 3 samples of 420.3 |
| co2_out_ppm | 3479 | 1 | 3 | 4 | 2026-05-18T07:33:44Z to 2026-05-18T07:33:48Z: 3 samples of 145.4 |
| pressure_drop | 3559 | 1 | 3 | 4 | 2026-05-18T08:04:10Z to 2026-05-18T08:04:14Z: 3 samples of 60.49 |
| solvent_flow | 3531 | 1 | 2 | 2 | 2026-05-18T07:35:00Z to 2026-05-18T07:35:02Z: 2 samples of 7.98 |
| solvent_pH | 1433 | 1 | 2 | 5 | 2026-05-18T07:45:05Z to 2026-05-18T07:45:10Z: 2 samples of 7.685 |
| solvent_temperature | 1190 | 1 | 240 | 1195 | 2026-05-18T08:30:00Z to 2026-05-18T08:49:55Z: 240 samples of 30.22 |
| ambient_pressure | 116 | 1 | 2 | 60 | 2026-05-18T07:46:00Z to 2026-05-18T07:47:00Z: 2 samples of 1017.28 |
| ambient_temperature | 118 | 1 | 2 | 60 | 2026-05-18T08:31:00Z to 2026-05-18T08:32:00Z: 2 samples of 22.52 |
| available_solar_power | 120 | 1 | 1 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:00Z: 1 samples of 158.87 |
| relative_humidity | 114 | 1 | 2 | 60 | 2026-05-18T07:50:00Z to 2026-05-18T07:51:00Z: 2 samples of 40.9 |
| acid_pH | 1389 | 1 | 40 | 195 | 2026-05-18T08:06:40Z to 2026-05-18T08:09:55Z: 40 samples of 4.8 |
| base_pH | 1435 | 1 | 2 | 5 | 2026-05-18T08:37:15Z to 2026-05-18T08:37:20Z: 2 samples of 12.086 |
| conductivity | 1418 | 1 | 3 | 10 | 2026-05-18T07:41:35Z to 2026-05-18T07:41:45Z: 3 samples of 214.7 |
| current | 7132 | 1 | 3 | 2 | 2026-05-18T07:58:53Z to 2026-05-18T07:58:55Z: 3 samples of 149.9 |
| current_setpoint | 303 | 1 | 3601 | 3600 | 2026-05-18T08:25:00Z to 2026-05-18T09:25:00Z: 3601 samples of 150 |
| electrolyte_temperature | 1421 | 1 | 2 | 5 | 2026-05-18T07:48:00Z to 2026-05-18T07:48:05Z: 2 samples of 38.66 |
| flow | 7157 | 1 | 3 | 2 | 2026-05-18T07:50:26Z to 2026-05-18T07:50:28Z: 3 samples of 42.16 |
| power | 7197 | 1 | 2 | 1 | 2026-05-18T07:30:26Z to 2026-05-18T07:30:27Z: 2 samples of 8.1 |
| pressure | 7139 | 1 | 2 | 1 | 2026-05-18T07:31:43Z to 2026-05-18T07:31:44Z: 2 samples of 2.53 |
| voltage | 7079 | 1 | 3 | 2 | 2026-05-18T07:52:18Z to 2026-05-18T07:52:20Z: 3 samples of 101.61 |
| fan_speed | 7165 | 1 | 3 | 2 | 2026-05-18T08:18:28Z to 2026-05-18T08:18:30Z: 3 samples of 1498.5 |
| process_state | 7 | 1 | 1 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:00Z: 1 samples of STARTUP |
| pump_speed | 7122 | 1 | 2 | 1 | 2026-05-18T07:31:35Z to 2026-05-18T07:31:36Z: 2 samples of 522.3 |
| valve_state | 3 | 1 | 1 | 0 | 2026-05-18T07:30:00Z to 2026-05-18T07:30:00Z: 1 samples of CLOSED |

### Step-to-step change (each value minus the previous)

| signal | count | mean | stddev | median abs | p95 abs | max abs |
|---|---|---|---|---|---|---|
| air_flow | 7199 | -0.000597305181 | 11.1558602 | 7.4 | 21.9 | 43.2 |
| co2_in_ppm | 3599 | 0.000111141984 | 1.69777836 | 1.1 | 3.4 | 6 |
| co2_out_ppm | 3599 | 0.00158377327 | 1.12106776 | 0.8 | 2.2 | 4.2 |
| pressure_drop | 3599 | 0.000444567936 | 0.358331664 | 0.24 | 0.7 | 1.26 |
| solvent_flow | 3599 | 2.7785496e-05 | 0.21136997 | 0.14 | 0.41 | 0.82 |
| solvent_pH | 1439 | 4.1695622e-06 | 0.740382276 | 0.05 | 0.137 | 19.774 |
| solvent_temperature | 1439 | 0.00501042391 | 0.388140941 | 0.22 | 0.801 | 1.37 |
| ambient_pressure | 119 | 0.00294117647 | 0.086184203 | 0.06 | 0.161 | 0.21 |
| ambient_temperature | 119 | 0.0310084034 | 0.20320481 | 0.15 | 0.4 | 0.49 |
| available_solar_power | 119 | 1.92210084 | 14.9538965 | 9.85 | 30.331 | 59.07 |
| relative_humidity | 119 | -0.0403361345 | 1.95990831 | 1.5 | 3.41 | 4.1 |
| acid_pH | 1439 | -0.000125086866 | 0.124403851 | 0.045 | 0.138 | 2.835 |
| base_pH | 1439 | 0.000146629604 | 0.0714501979 | 0.047 | 0.1401 | 0.242 |
| conductivity | 1439 | 0.0187630299 | 2.89957714 | 2 | 5.6 | 9.5 |
| current | 7199 | 0.00241978053 | 0.493828212 | 0.3 | 0.89 | 4.48 |
| current_setpoint | 7199 | 6.94540908e-05 | 2.03384635 | 0 | 0 | 150 |
| electrolyte_temperature | 1439 | 0.0111952745 | 0.289566296 | 0.19 | 0.59 | 1.26 |
| flow | 7199 | 0.000348659536 | 0.568526809 | 0.38 | 1.12 | 2.05 |
| power | 7199 | 0.177191277 | 60.0247521 | 37.4 | 114.3 | 367.1 |
| pressure | 7199 | 4.58397e-06 | 0.0427438835 | 0.029 | 0.084 | 0.164 |
| voltage | 7199 | 0.000662592027 | 0.219696404 | 0.14 | 0.42 | 1.37 |
| fan_speed | 7199 | 0.000180580636 | 26.018249 | 4.8 | 14 | 1501.2 |
| pump_speed | 7199 | -0.000638977636 | 4.19193972 | 2.8 | 8.3 | 18.1 |

### Relationship: power vs voltage x current

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.99999998 |
| residual_mean | -0.0104400278 |
| residual_stddev | 0.521940306 |
| residual_median | -0.0104 |
| residual_p05 | -0.878405 |
| residual_p95 | 0.86221 |
| residual_max_abs | 1.5604 |
| relative_residual_median | 2.55858819e-05 |
| relative_residual_p95 | 6.64142991e-05 |
| power_zero_instants | 0 |
| slope | 0.999999214 |
| intercept | 0.00144751331 |
| r2 | 0.99999996 |

### Relationship: co2 out vs co2 in

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | 0.00393096071 |
| ratio_median | 0.351692895 |
| ratio_p05 | 0.345454329 |
| ratio_p95 | 0.358472554 |
| out_at_or_above_in | 0 |

### Relationship: current vs current setpoint

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.925865289 |
| difference_mean | -0.0895333333 |
| difference_stddev | 8.90001351 |
| difference_median | 0 |
| difference_max_abs | 145.61 |
| best_lag_s | 24 |
| corr_at_best_lag | 0.971199158 |

### Relationship: pressure drop vs air flow

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | -0.0484080063 |
| slope_air_flow | -0.00342636963 |
| intercept_air_flow | 69.1252898 |
| r2_air_flow | 0.00234333507 |
| slope_air_flow_sq | -7.13505448e-07 |
| intercept_air_flow_sq | 65.0118407 |
| r2_air_flow_sq | 0.00234190774 |

## EXP_004

### Values

| source | signal | unit | points | no value | GOOD | UNCERTAIN | BAD | min | p05 | median | mean | p95 | max | stddev | doc. min | doc. max | below doc. min | above doc. max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| absorber | air_flow | m³/h | 7200 | 0 | 7200 | 0 | 0 | 19.53 | 19.83 | 595.225 | 610.011721 | 1210.1 | 1227.3 | 590.077445 | 1000 | 2500 | 3600 | 0 |
| absorber | co2_in_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 415.6 | 418 | 420 | 420.011306 | 422 | 424.4 | 1.18902196 | 400 | 430 | 0 | 0 |
| absorber | co2_out_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 91.1 | 92.7 | 94.2 | 94.2826111 | 96.1 | 100 | 1.11482115 | 50 | 200 | 0 | 0 |
| absorber | pressure_drop | mbar | 3600 | 0 | 3600 | 0 | 0 | 14.26 | 14.76 | 15.22 | 15.2239 | 15.7 | 16.17 | 0.282745463 | 10 | 65 | 0 | 0 |
| absorber | solvent_flow | L/min | 3600 | 0 | 3600 | 0 | 0 | 7.45 | 7.76 | 8.01 | 8.00449444 | 8.25 | 8.54 | 0.151492418 | 7 | 10 | 0 | 0 |
| absorber | solvent_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 7.446 | 7.55295 | 7.649 | 7.64520486 | 7.734 | 7.801 | 0.0555272571 | 6 | 9 | 0 | 0 |
| absorber | solvent_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 9.84 | 11.66 | 12.77 | 12.7007847 | 13.6 | 14.16 | 0.635227282 | 5 | 40 | 0 | 0 |
| ambient | ambient_pressure | hPa | 120 | 0 | 120 | 0 | 0 | 1006.83 | 1006.9575 | 1007.685 | 1007.66542 | 1008.162 | 1008.3 | 0.339606534 | 990 | 1030 | 0 | 0 |
| ambient | ambient_temperature | °C | 120 | 0 | 120 | 0 | 0 | 3.97 | 4.0695 | 4.805 | 4.78783333 | 5.49 | 5.61 | 0.446580252 | -5 | 30 | 0 | 0 |
| ambient | available_solar_power | kW | 120 | 0 | 120 | 0 | 0 | 94.88 | 112.014 | 156.16 | 159.480917 | 211.568 | 227.12 | 29.9262672 | 0 | 550 | 0 | 0 |
| ambient | relative_humidity | % | 120 | 0 | 120 | 0 | 0 | 69.7 | 71.3 | 74.25 | 74.3766667 | 77.81 | 80.9 | 2.08184361 | 20 | 100 | 0 | 0 |
| hydrolyzer | acid_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 1.724 | 1.946 | 2.048 | 2.05463125 | 2.169 | 2.559 | 0.0848407051 | 0.5 | 4 | 0 | 0 |
| hydrolyzer | base_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 11.41 | 11.96795 | 12.097 | 12.0913576 | 12.22805 | 12.411 | 0.103230377 | 10 | 13.5 | 0 | 0 |
| hydrolyzer | conductivity | mS/cm | 1440 | 0 | 1440 | 0 | 0 | 167.1 | 187.39 | 202 | 200.986181 | 209.505 | 220.8 | 6.80361343 | 150 | 240 | 0 | 0 |
| hydrolyzer | current | A | 7200 | 0 | 7200 | 0 | 0 | -0.64 | 137.0745 | 149.99 | 148.672015 | 158.888 | 211.02 | 22.2492847 | 0 | 260 | 13 | 0 |
| hydrolyzer | current_setpoint | A | 7200 | 0 | 7200 | 0 | 0 | 0 | 150 | 150 | 148.760417 | 150 | 210 | 23.5208313 | 0 | 260 | 0 | 0 |
| hydrolyzer | electrolyte_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 6.39 | 15.766 | 24.92 | 23.9329514 | 28.051 | 30.21 | 3.70522653 | 0 | 45 | 0 | 0 |
| hydrolyzer | flow | L/min | 7200 | 0 | 7200 | 0 | 0 | 29.41 | 40.6695 | 42 | 41.8944722 | 43.1805 | 47.75 | 1.82528384 | 25 | 55 | 0 | 0 |
| hydrolyzer | power | W | 7200 | 0 | 7200 | 0 | 0 | -43.4 | 14493.13 | 15980.8 | 15926.8184 | 17011.615 | 24997.8 | 2789.64171 | 0 | 35000 | 13 | 0 |
| hydrolyzer | pressure | bar | 7200 | 0 | 7000 | 200 | 0 | -3.1 | 2.534 | 2.6 | 2.59594583 | 2.668 | 2.799 | 0.0861188934 | 2 | 3 | 1 | 0 |
| hydrolyzer | voltage | V | 7200 | 0 | 7200 | 0 | 0 | 68.12 | 105.099 | 106.52 | 106.362818 | 110.49 | 119.3 | 5.22875976 | 60 | 130 | 0 | 0 |
| plant | fan_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 881.8 | 891.9 | 899.9 | 900.00825 | 908.2 | 916.4 | 4.97319318 | 800 | 1600 | 0 | 0 |
| plant | pump_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 0 | 515 | 520 | 519.923819 | 525 | 530.6 | 6.82004315 | 450 | 650 | 1 | 0 |

### Text signals

| source | signal | points | no value | GOOD | UNCERTAIN | BAD | values |
|---|---|---|---|---|---|---|---|
| plant | process_state | 7 | 0 | 7 | 0 | 0 | LOAD_CHANGE: 2, SHUTDOWN: 1, STARTUP: 1, STEADY_STATE: 3 |
| plant | valve_state | 3 | 0 | 3 | 0 | 0 | CLOSED: 2, OPEN: 1 |

### Intervals between points (seconds)

| signal | nominal | count | min | median | p95 | max | over 2x nominal | over 10x nominal | seconds in over-2x | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| air_flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| co2_in_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:02Z (2 s) |
| co2_out_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:02Z (2 s) |
| pressure_drop | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:02Z (2 s) |
| solvent_flow | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:02Z (2 s) |
| solvent_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:05Z (5 s) |
| solvent_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:05Z (5 s) |
| ambient_pressure | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:01:00Z (60 s) |
| ambient_temperature | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:01:00Z (60 s) |
| available_solar_power | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:01:00Z (60 s) |
| relative_humidity | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:01:00Z (60 s) |
| acid_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:05Z (5 s) |
| base_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:05Z (5 s) |
| conductivity | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:05Z (5 s) |
| current | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| current_setpoint | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| electrolyte_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:05Z (5 s) |
| flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| power | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| pressure | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| voltage | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| fan_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| process_state | n/a | 6 | 133 | 158.5 | 3312.75 | 3467 | n/a | n/a | n/a | 2026-03-02T08:57:13Z to 2026-03-02T09:55:00Z (3467 s) |
| pump_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:01Z (1 s) |
| valve_state | n/a | 2 | 20 | 3585 | 6793.5 | 7150 | n/a | n/a | n/a | 2026-03-02T08:00:20Z to 2026-03-02T09:59:30Z (7150 s) |

### Runs of identical values

| signal | runs | median samples | max samples | max seconds | longest run |
|---|---|---|---|---|---|
| air_flow | 7106 | 1 | 3 | 2 | 2026-03-02T09:22:18Z to 2026-03-02T09:22:20Z: 3 samples of 20.05 |
| co2_in_ppm | 3519 | 1 | 2 | 2 | 2026-03-02T08:04:50Z to 2026-03-02T08:04:52Z: 2 samples of 418.8 |
| co2_out_ppm | 3466 | 1 | 3 | 4 | 2026-03-02T08:05:42Z to 2026-03-02T08:05:46Z: 3 samples of 94.8 |
| pressure_drop | 3559 | 1 | 2 | 2 | 2026-03-02T08:13:48Z to 2026-03-02T08:13:50Z: 2 samples of 14.97 |
| solvent_flow | 3531 | 1 | 3 | 4 | 2026-03-02T08:07:32Z to 2026-03-02T08:07:36Z: 3 samples of 8.1 |
| solvent_pH | 1430 | 1 | 2 | 5 | 2026-03-02T08:12:40Z to 2026-03-02T08:12:45Z: 2 samples of 7.635 |
| solvent_temperature | 1417 | 1 | 2 | 5 | 2026-03-02T08:04:50Z to 2026-03-02T08:04:55Z: 2 samples of 11.54 |
| ambient_pressure | 110 | 1 | 2 | 60 | 2026-03-02T08:04:00Z to 2026-03-02T08:05:00Z: 2 samples of 1007.95 |
| ambient_temperature | 116 | 1 | 2 | 60 | 2026-03-02T08:30:00Z to 2026-03-02T08:31:00Z: 2 samples of 4.47 |
| available_solar_power | 120 | 1 | 1 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:00Z: 1 samples of 112.08 |
| relative_humidity | 115 | 1 | 2 | 60 | 2026-03-02T08:01:00Z to 2026-03-02T08:02:00Z: 2 samples of 75.2 |
| acid_pH | 1430 | 1 | 2 | 5 | 2026-03-02T08:01:45Z to 2026-03-02T08:01:50Z: 2 samples of 2.328 |
| base_pH | 1428 | 1 | 2 | 5 | 2026-03-02T08:06:30Z to 2026-03-02T08:06:35Z: 2 samples of 12.064 |
| conductivity | 1420 | 1 | 2 | 5 | 2026-03-02T08:01:45Z to 2026-03-02T08:01:50Z: 2 samples of 173.3 |
| current | 7130 | 1 | 2 | 1 | 2026-03-02T08:03:13Z to 2026-03-02T08:03:14Z: 2 samples of 148.73 |
| current_setpoint | 303 | 1 | 3601 | 3600 | 2026-03-02T08:55:00Z to 2026-03-02T09:55:00Z: 3601 samples of 150 |
| electrolyte_temperature | 1423 | 1 | 2 | 5 | 2026-03-02T08:03:20Z to 2026-03-02T08:03:25Z: 2 samples of 11.6 |
| flow | 7154 | 1 | 2 | 1 | 2026-03-02T08:00:11Z to 2026-03-02T08:00:12Z: 2 samples of 29.77 |
| power | 7192 | 1 | 2 | 1 | 2026-03-02T08:40:08Z to 2026-03-02T08:40:09Z: 2 samples of 16005.2 |
| pressure | 7144 | 1 | 3 | 2 | 2026-03-02T09:00:05Z to 2026-03-02T09:00:07Z: 3 samples of 2.597 |
| voltage | 7060 | 1 | 3 | 2 | 2026-03-02T09:44:42Z to 2026-03-02T09:44:44Z: 3 samples of 106.3 |
| fan_speed | 7165 | 1 | 2 | 1 | 2026-03-02T08:03:17Z to 2026-03-02T08:03:18Z: 2 samples of 901.6 |
| process_state | 7 | 1 | 1 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:00Z: 1 samples of STARTUP |
| pump_speed | 7134 | 1 | 3 | 2 | 2026-03-02T08:48:35Z to 2026-03-02T08:48:37Z: 3 samples of 518.3 |
| valve_state | 3 | 1 | 1 | 0 | 2026-03-02T08:00:00Z to 2026-03-02T08:00:00Z: 1 samples of CLOSED |

### Step-to-step change (each value minus the previous)

| signal | count | mean | stddev | median abs | p95 abs | max abs |
|---|---|---|---|---|---|---|
| air_flow | 7199 | -0.164081122 | 16.0106917 | 0.4 | 18.7 | 1178.12 |
| co2_in_ppm | 3599 | -0.00013892748 | 1.68048422 | 1.1 | 3.3 | 7.3 |
| co2_out_ppm | 3599 | -0.000889135871 | 1.13349592 | 0.8 | 2.2 | 3.8 |
| pressure_drop | 3599 | 0.000130591831 | 0.356354152 | 0.24 | 0.71 | 1.48 |
| solvent_flow | 3599 | -9.44706863e-05 | 0.209380733 | 0.14 | 0.41 | 0.76 |
| solvent_pH | 1439 | 9.72897846e-05 | 0.0683881704 | 0.045 | 0.138 | 0.231 |
| solvent_temperature | 1439 | 0.00252258513 | 0.42555743 | 0.28 | 0.821 | 1.51 |
| ambient_pressure | 119 | -0.0101680672 | 0.0779828664 | 0.05 | 0.141 | 0.21 |
| ambient_temperature | 119 | 0.0107563025 | 0.201612818 | 0.14 | 0.363 | 0.51 |
| available_solar_power | 119 | 0.63697479 | 11.2580329 | 8.25 | 21.869 | 24.41 |
| relative_humidity | 119 | -0.0411764706 | 2.03496603 | 1.3 | 3.42 | 6.7 |
| acid_pH | 1439 | -4.10006949e-05 | 0.0718180584 | 0.049 | 0.1381 | 0.263 |
| base_pH | 1439 | 0.000110493398 | 0.0727471541 | 0.049 | 0.1432 | 0.24 |
| conductivity | 1439 | 0.00618485059 | 2.76386063 | 1.7 | 5.5 | 10.4 |
| current | 7199 | 0.00235727184 | 0.501478849 | 0.3 | 0.93 | 4.48 |
| current_setpoint | 7199 | 6.94540908e-05 | 2.03384635 | 0 | 0 | 150 |
| electrolyte_temperature | 1439 | 0.00930507297 | 0.287238428 | 0.19 | 0.571 | 0.9 |
| flow | 7199 | 0.000281983609 | 0.553658615 | 0.37 | 1.081 | 2.15 |
| power | 7199 | 0.173996388 | 63.0636604 | 39.4 | 122.01 | 356.5 |
| pressure | 7199 | 1.47242673e-05 | 0.1044467 | 0.029 | 0.085 | 5.71 |
| voltage | 7199 | 0.000729267954 | 0.225431226 | 0.15 | 0.44 | 1.69 |
| fan_speed | 7199 | 0.00162522573 | 6.96903853 | 4.8 | 13.6 | 29.2 |
| pump_speed | 7199 | 0.000194471454 | 9.67373163 | 2.9 | 8.3 | 524.2 |

### Relationship: power vs voltage x current

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.999999982 |
| residual_mean | 0.00337370833 |
| residual_stddev | 0.532917165 |
| residual_median | 0.00515 |
| residual_p05 | -0.88523 |
| residual_p95 | 0.89143 |
| residual_max_abs | 1.4548 |
| relative_residual_median | 2.49521709e-05 |
| relative_residual_p95 | 6.47029952e-05 |
| power_zero_instants | 0 |
| slope | 1.00000207 |
| intercept | -0.0295761128 |
| r2 | 0.999999964 |

### Relationship: co2 out vs co2 in

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | 0.0108722718 |
| ratio_median | 0.224251096 |
| ratio_p05 | 0.220581229 |
| ratio_p95 | 0.229116945 |
| out_at_or_above_in | 0 |

### Relationship: current vs current setpoint

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.925892699 |
| difference_mean | -0.0884013889 |
| difference_stddev | 8.89835625 |
| difference_median | 0 |
| difference_max_abs | 145.73 |
| best_lag_s | 24 |
| corr_at_best_lag | 0.97125274 |

### Relationship: pressure drop vs air flow

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | -0.408591841 |
| slope_air_flow | -0.000195767905 |
| intercept_air_flow | 15.3433228 |
| r2_air_flow | 0.166947293 |
| slope_air_flow_sq | -1.6037173e-07 |
| intercept_air_flow_sq | 15.3394122 |
| r2_air_flow_sq | 0.166824144 |

## EXP_005

### Values

| source | signal | unit | points | no value | GOOD | UNCERTAIN | BAD | min | p05 | median | mean | p95 | max | stddev | doc. min | doc. max | below doc. min | above doc. max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| absorber | air_flow | m³/h | 7200 | 0 | 7200 | 0 | 0 | 1170.7 | 1187 | 1199.9 | 1199.88285 | 1212.6 | 1229.5 | 7.90149815 | 1000 | 2500 | 0 | 0 |
| absorber | co2_in_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 415.3 | 418 | 420 | 419.990472 | 422 | 424.5 | 1.19978038 | 400 | 430 | 0 | 0 |
| absorber | co2_out_ppm | ppm | 3600 | 0 | 3600 | 0 | 0 | 99.9 | 101.5 | 103.7 | 103.728556 | 105.9 | 108.1 | 1.34974548 | 50 | 200 | 0 | 0 |
| absorber | pressure_drop | mbar | 3600 | 0 | 3600 | 0 | 0 | 14.15 | 14.74 | 15.22 | 15.2197889 | 15.69 | 16.11 | 0.283896615 | 10 | 65 | 0 | 0 |
| absorber | solvent_flow | L/min | 3600 | 0 | 3600 | 0 | 0 | 7.47 | 7.76 | 8 | 8.00227778 | 8.25 | 8.53 | 0.149820048 | 7 | 10 | 0 | 0 |
| absorber | solvent_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 7.356 | 7.47895 | 7.568 | 7.56834375 | 7.658 | 7.735 | 0.054956277 | 6 | 9 | 0 | 0 |
| absorber | solvent_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 23.29 | 24.15 | 26.42 | 26.4099097 | 28.69 | 29.42 | 1.47895322 | 5 | 40 | 0 | 0 |
| ambient | ambient_pressure | hPa | 120 | 0 | 90 | 30 | 0 | 1013.49 | 1013.659 | 1014.275 | 1014.20517 | 1014.6805 | 1014.92 | 0.349984353 | 990 | 1030 | 0 | 0 |
| ambient | ambient_temperature | °C | 120 | 0 | 120 | 0 | 0 | 15.92 | 16.2595 | 18.585 | 18.545 | 20.691 | 21.18 | 1.45731594 | -5 | 30 | 0 | 0 |
| ambient | available_solar_power | kW | 120 | 0 | 120 | 0 | 0 | 0 | 6.995 | 101.38 | 104.054667 | 208.869 | 242.75 | 65.7391483 | 0 | 550 | 0 | 0 |
| ambient | relative_humidity | % | 120 | 0 | 120 | 0 | 0 | 35.9 | 37.195 | 41.25 | 41.1591667 | 45.005 | 46.4 | 2.4662255 | 20 | 100 | 0 | 0 |
| hydrolyzer | acid_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 2.062 | 2.15695 | 2.289 | 2.29038403 | 2.4291 | 2.554 | 0.0834717108 | 0.5 | 4 | 0 | 0 |
| hydrolyzer | base_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 11.433 | 11.60995 | 11.788 | 11.7813083 | 11.942 | 12.034 | 0.102067172 | 10 | 13.5 | 0 | 0 |
| hydrolyzer | conductivity | mS/cm | 1440 | 0 | 1440 | 0 | 0 | 173.8 | 179.6 | 191.7 | 191.642639 | 204.3 | 210.3 | 7.90679118 | 150 | 240 | 0 | 0 |
| hydrolyzer | current | A | 7200 | 0 | 7200 | 0 | 0 | -0.6 | 41.1495 | 70.805 | 70.8691819 | 104.146 | 116.18 | 21.4102489 | 0 | 260 | 17 | 0 |
| hydrolyzer | current_setpoint | A | 7200 | 0 | 7200 | 0 | 0 | 0 | 41.38 | 70.43 | 70.9237986 | 103.351 | 117.68 | 21.4843362 | 0 | 260 | 0 | 0 |
| hydrolyzer | electrolyte_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | -50 | 20.36 | 25.81 | 25.8483472 | 32.31 | 32.84 | 4.4002633 | 0 | 45 | 1 | 0 |
| hydrolyzer | flow | L/min | 7200 | 0 | 7200 | 0 | 0 | 29.2 | 33.05 | 35.76 | 35.6656806 | 38.43 | 40.15 | 1.75611577 | 25 | 55 | 0 | 0 |
| hydrolyzer | power | W | 7200 | 0 | 7200 | 0 | 0 | -41 | 3313.375 | 6187.65 | 6283.22803 | 9815.035 | 11238.6 | 2179.6839 | 0 | 35000 | 17 | 0 |
| hydrolyzer | pressure | bar | 7200 | 0 | 7200 | 0 | 0 | 2.255 | 2.353 | 2.443 | 2.44125444 | 2.526 | 2.6 | 0.0530971033 | 2 | 3 | 0 | 0 |
| hydrolyzer | voltage | V | 7200 | 0 | 7200 | 0 | 0 | 68.15 | 80.43 | 87.48 | 87.2158597 | 94.3225 | 97.1 | 4.80014918 | 60 | 130 | 0 | 0 |
| plant | fan_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 881.7 | 891.8 | 899.9 | 899.958903 | 908.2 | 917.8 | 4.97737023 | 800 | 1600 | 0 | 0 |
| plant | pump_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 508.2 | 515 | 519.9 | 519.974028 | 525 | 532 | 3.05823515 | 450 | 650 | 0 | 0 |

### Text signals

| source | signal | points | no value | GOOD | UNCERTAIN | BAD | values |
|---|---|---|---|---|---|---|---|
| plant | process_state | 19 | 0 | 19 | 0 | 0 | LOAD_CHANGE: 8, SHUTDOWN: 1, STARTUP: 1, STEADY_STATE: 9 |
| plant | valve_state | 5 | 0 | 5 | 0 | 0 | CLOSED: 3, OPEN: 2 |

### Intervals between points (seconds)

| signal | nominal | count | min | median | p95 | max | over 2x nominal | over 10x nominal | seconds in over-2x | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| air_flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| co2_in_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:02Z (2 s) |
| co2_out_ppm | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:02Z (2 s) |
| pressure_drop | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:02Z (2 s) |
| solvent_flow | 2 | 3599 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:02Z (2 s) |
| solvent_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:05Z (5 s) |
| solvent_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:05Z (5 s) |
| ambient_pressure | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:01:00Z (60 s) |
| ambient_temperature | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:01:00Z (60 s) |
| available_solar_power | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:01:00Z (60 s) |
| relative_humidity | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:01:00Z (60 s) |
| acid_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:05Z (5 s) |
| base_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:05Z (5 s) |
| conductivity | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:05Z (5 s) |
| current | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| current_setpoint | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| electrolyte_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:05Z (5 s) |
| flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| power | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| pressure | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| voltage | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| fan_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| process_state | n/a | 18 | 29 | 131.5 | 1392 | 1630 | n/a | n/a | n/a | 2026-06-15T07:08:50Z to 2026-06-15T07:36:00Z (1630 s) |
| pump_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:01Z (1 s) |
| valve_state | n/a | 4 | 20 | 1262.5 | 4303.25 | 4625 | n/a | n/a | n/a | 2026-06-15T06:42:25Z to 2026-06-15T07:59:30Z (4625 s) |

### Runs of identical values

| signal | runs | median samples | max samples | max seconds | longest run |
|---|---|---|---|---|---|
| air_flow | 7172 | 1 | 2 | 1 | 2026-06-15T06:05:04Z to 2026-06-15T06:05:05Z: 2 samples of 1194.9 |
| co2_in_ppm | 3513 | 1 | 3 | 4 | 2026-06-15T06:13:08Z to 2026-06-15T06:13:12Z: 3 samples of 419.8 |
| co2_out_ppm | 3481 | 1 | 3 | 4 | 2026-06-15T06:13:18Z to 2026-06-15T06:13:22Z: 3 samples of 102 |
| pressure_drop | 3571 | 1 | 3 | 4 | 2026-06-15T07:44:26Z to 2026-06-15T07:44:30Z: 3 samples of 15.41 |
| solvent_flow | 3538 | 1 | 3 | 4 | 2026-06-15T06:28:20Z to 2026-06-15T06:28:24Z: 3 samples of 8.07 |
| solvent_pH | 1429 | 1 | 2 | 5 | 2026-06-15T06:08:55Z to 2026-06-15T06:09:00Z: 2 samples of 7.567 |
| solvent_temperature | 1428 | 1 | 2 | 5 | 2026-06-15T06:07:30Z to 2026-06-15T06:07:35Z: 2 samples of 24.31 |
| ambient_pressure | 114 | 1 | 2 | 60 | 2026-06-15T06:17:00Z to 2026-06-15T06:18:00Z: 2 samples of 1014.47 |
| ambient_temperature | 114 | 1 | 2 | 60 | 2026-06-15T06:02:00Z to 2026-06-15T06:03:00Z: 2 samples of 16.25 |
| available_solar_power | 120 | 1 | 1 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:00Z: 1 samples of 0 |
| relative_humidity | 119 | 1 | 2 | 60 | 2026-06-15T07:50:00Z to 2026-06-15T07:51:00Z: 2 samples of 38.9 |
| acid_pH | 1434 | 1 | 2 | 5 | 2026-06-15T06:16:15Z to 2026-06-15T06:16:20Z: 2 samples of 2.391 |
| base_pH | 1431 | 1 | 2 | 5 | 2026-06-15T06:03:40Z to 2026-06-15T06:03:45Z: 2 samples of 11.624 |
| conductivity | 1417 | 1 | 2 | 5 | 2026-06-15T06:05:15Z to 2026-06-15T06:05:20Z: 2 samples of 181.4 |
| current | 7121 | 1 | 2 | 1 | 2026-06-15T06:02:51Z to 2026-06-15T06:02:52Z: 2 samples of 40.11 |
| current_setpoint | 416 | 1 | 60 | 59 | 2026-06-15T06:01:00Z to 2026-06-15T06:01:59Z: 60 samples of 40.25 |
| electrolyte_temperature | 1418 | 1 | 3 | 10 | 2026-06-15T07:28:35Z to 2026-06-15T07:28:45Z: 3 samples of 29.28 |
| flow | 7144 | 1 | 3 | 2 | 2026-06-15T07:16:12Z to 2026-06-15T07:16:14Z: 3 samples of 36.59 |
| power | 7189 | 1 | 2 | 1 | 2026-06-15T06:04:50Z to 2026-06-15T06:04:51Z: 2 samples of 3299.7 |
| pressure | 7139 | 1 | 2 | 1 | 2026-06-15T06:00:24Z to 2026-06-15T06:00:25Z: 2 samples of 2.273 |
| voltage | 7072 | 1 | 3 | 2 | 2026-06-15T06:13:58Z to 2026-06-15T06:14:00Z: 3 samples of 81.55 |
| fan_speed | 7164 | 1 | 2 | 1 | 2026-06-15T06:17:28Z to 2026-06-15T06:17:29Z: 2 samples of 906.8 |
| process_state | 19 | 1 | 1 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:00Z: 1 samples of STARTUP |
| pump_speed | 7128 | 1 | 2 | 1 | 2026-06-15T06:03:00Z to 2026-06-15T06:03:01Z: 2 samples of 519.6 |
| valve_state | 5 | 1 | 1 | 0 | 2026-06-15T06:00:00Z to 2026-06-15T06:00:00Z: 1 samples of CLOSED |

### Step-to-step change (each value minus the previous)

| signal | count | mean | stddev | median abs | p95 abs | max abs |
|---|---|---|---|---|---|---|
| air_flow | 7199 | -0.000402833727 | 11.2635156 | 7.5 | 22.3 | 42.9 |
| co2_in_ppm | 3599 | 0.000361211448 | 1.69278703 | 1.1 | 3.3 | 6.8 |
| co2_out_ppm | 3599 | 0.00119477633 | 1.12468201 | 0.8 | 2.2 | 4.2 |
| pressure_drop | 3599 | 0.000175048625 | 0.362052848 | 0.24 | 0.72 | 1.21 |
| solvent_flow | 3599 | 1.66712976e-05 | 0.210442504 | 0.14 | 0.411 | 0.77 |
| solvent_pH | 1439 | 4.86448923e-05 | 0.0688640423 | 0.048 | 0.134 | 0.219 |
| solvent_temperature | 1439 | 0.00326615705 | 0.43193958 | 0.29 | 0.84 | 1.42 |
| ambient_pressure | 119 | 0.00764705882 | 0.08679516 | 0.06 | 0.17 | 0.26 |
| ambient_temperature | 119 | 0.0442016807 | 0.194332826 | 0.12 | 0.361 | 0.64 |
| available_solar_power | 119 | 1.75428571 | 9.01228235 | 3.58 | 20.07 | 34.04 |
| relative_humidity | 119 | -0.0705882353 | 1.95432389 | 1.4 | 3.61 | 4.3 |
| acid_pH | 1439 | -0.000111188325 | 0.0716196889 | 0.047 | 0.138 | 0.251 |
| base_pH | 1439 | 0.000154968728 | 0.0717670007 | 0.048 | 0.138 | 0.248 |
| conductivity | 1439 | 0.00674079222 | 2.82031235 | 1.9 | 5.6 | 9.5 |
| current | 7199 | 0.0017724684 | 0.435341633 | 0.3 | 0.85 | 1.8 |
| current_setpoint | 7199 | 5.00069454e-05 | 0.603814261 | 0 | 0.34 | 40 |
| electrolyte_temperature | 1439 | 0.00626824183 | 2.86815718 | 0.18 | 0.54 | 76.81 |
| flow | 7199 | 0.000151409918 | 0.566370521 | 0.38 | 1.11 | 2.43 |
| power | 7199 | 0.128490068 | 41.2212213 | 27.5 | 80.9 | 155.1 |
| pressure | 7199 | 5.2785109e-06 | 0.0422991467 | 0.028 | 0.083 | 0.156 |
| voltage | 7199 | 0.000566745381 | 0.218195728 | 0.15 | 0.43 | 0.77 |
| fan_speed | 7199 | -0.001069593 | 6.99305893 | 4.8 | 13.6 | 26.2 |
| pump_speed | 7199 | 0.000236143909 | 4.32633737 | 2.9 | 8.4 | 17.8 |

### Relationship: power vs voltage x current

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.999999988 |
| residual_mean | 0.000251777778 |
| residual_stddev | 0.334413507 |
| residual_median | -0.0078 |
| residual_p05 | -0.54341 |
| residual_p95 | 0.554 |
| residual_max_abs | 0.9515 |
| relative_residual_median | 4.08847849e-05 |
| relative_residual_p95 | 0.000114696812 |
| power_zero_instants | 0 |
| slope | 1.00000081 |
| intercept | -0.00481483563 |
| r2 | 0.999999976 |

### Relationship: co2 out vs co2 in

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | -0.01043039 |
| ratio_median | 0.246932764 |
| ratio_p05 | 0.241625089 |
| ratio_p95 | 0.252381066 |
| out_at_or_above_in | 0 |

### Relationship: current vs current setpoint

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.988433074 |
| difference_mean | -0.0546166667 |
| difference_stddev | 3.26293016 |
| difference_median | -0.2 |
| difference_max_abs | 38.98 |
| best_lag_s | 27 |
| corr_at_best_lag | 0.996982953 |

### Relationship: pressure drop vs air flow

| measure | value |
|---|---|
| instants_matched | 3600 |
| instants_unmatched | 0 |
| corr | -0.00296817222 |
| slope_air_flow | -0.000107857258 |
| intercept_air_flow | 15.3492035 |
| r2_air_flow | 8.81004633e-06 |
| slope_air_flow_sq | -4.12986594e-08 |
| intercept_air_flow_sq | 15.2792485 |
| r2_air_flow_sq | 7.44135197e-06 |

## EXP_006

### Values

| source | signal | unit | points | no value | GOOD | UNCERTAIN | BAD | min | p05 | median | mean | p95 | max | stddev | doc. min | doc. max | below doc. min | above doc. max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| absorber | air_flow | m³/h | 5280 | 0 | 5280 | 0 | 0 | 1172 | 1187.095 | 1200 | 1200.10117 | 1213.305 | 1234 | 7.91996588 | 1000 | 2500 | 0 | 0 |
| absorber | co2_in_ppm | ppm | 2640 | 0 | 2640 | 0 | 0 | 415.8 | 417.9 | 420 | 420.009886 | 422 | 424.7 | 1.20856987 | 400 | 430 | 0 | 0 |
| absorber | co2_out_ppm | ppm | 2640 | 0 | 2640 | 0 | 0 | 38 | 38 | 38 | 69.1730682 | 103.2 | 105.2 | 31.9062716 | 50 | 200 | 1350 | 0 |
| absorber | pressure_drop | mbar | 2640 | 0 | 2640 | 0 | 0 | 14.31 | 14.77 | 15.28 | 15.2654242 | 15.72 | 16.07 | 0.285316763 | 10 | 65 | 0 | 0 |
| absorber | solvent_flow | L/min | 2640 | 0 | 2640 | 0 | 0 | 9.07 | 9.27 | 9.5 | 9.50173106 | 9.74 | 10 | 0.142993214 | 7 | 10 | 0 | 0 |
| absorber | solvent_pH | n/a | 1056 | 0 | 1056 | 0 | 0 | 7.452 | 7.542 | 7.65 | 7.6459858 | 7.736 | 7.811 | 0.0602711156 | 6 | 9 | 0 | 0 |
| absorber | solvent_temperature | °C | 1056 | 0 | 1056 | 0 | 0 | 28.02 | 32.4825 | 34.785 | 34.5133144 | 35.39 | 35.84 | 1.07934797 | 5 | 40 | 0 | 0 |
| ambient | ambient_pressure | hPa | 120 | 0 | 120 | 0 | 0 | 1012.51 | 1012.649 | 1012.935 | 1012.9285 | 1013.1525 | 1013.44 | 0.171731909 | 990 | 1030 | 0 | 0 |
| ambient | ambient_temperature | °C | 120 | 0 | 120 | 0 | 0 | 25.97 | 26.1685 | 26.75 | 26.6950833 | 27.14 | 27.29 | 0.318742265 | -5 | 30 | 0 | 0 |
| ambient | available_solar_power | kW | 120 | 0 | 120 | 0 | 0 | 328.62 | 358.483 | 422.255 | 423.340833 | 493.6055 | 507.83 | 42.4880311 | 0 | 550 | 0 | 0 |
| ambient | relative_humidity | % | 120 | 0 | 120 | 0 | 0 | 33 | 34.8 | 37.7 | 37.6941667 | 40.215 | 41.9 | 1.68579312 | 20 | 100 | 0 | 0 |
| hydrolyzer | acid_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 1.791 | 1.949 | 2.052 | 2.05773542 | 2.18105 | 2.598 | 0.0842287588 | 0.5 | 4 | 0 | 0 |
| hydrolyzer | base_pH | n/a | 1440 | 0 | 1440 | 0 | 0 | 11.402 | 11.96095 | 12.099 | 12.0905285 | 12.215 | 12.44 | 0.103726939 | 10 | 13.5 | 0 | 0 |
| hydrolyzer | conductivity | mS/cm | 1440 | 0 | 1440 | 0 | 0 | 177.6 | 211.49 | 226.9 | 225.435972 | 234.21 | 243.4 | 7.98950739 | 150 | 240 | 0 | 12 |
| hydrolyzer | current | A | 7200 | 0 | 7200 | 0 | 0 | -0.69 | 136.9785 | 150 | 148.677967 | 159.012 | 210.63 | 22.2540894 | 0 | 260 | 17 | 0 |
| hydrolyzer | current_setpoint | A | 7200 | 0 | 7200 | 0 | 0 | 0 | 150 | 150 | 148.759532 | 150 | 210 | 23.5209045 | 0 | 260 | 0 | 0 |
| hydrolyzer | electrolyte_temperature | °C | 1440 | 0 | 1440 | 0 | 0 | 24.65 | 35.317 | 45.49 | 44.4393611 | 48.5635 | 50.56 | 4.02904987 | 0 | 45 | 0 | 994 |
| hydrolyzer | flow | L/min | 7200 | 0 | 7200 | 0 | 0 | 29.28 | 40.68 | 42 | 41.8914528 | 43.15 | 47.94 | 1.8271991 | 25 | 55 | 0 | 0 |
| hydrolyzer | power | W | 7200 | 0 | 7200 | 0 | 0 | -47.3 | 13675.65 | 14979.2 | 14925.5877 | 15896.1 | 23068.5 | 2552.58669 | 0 | 35000 | 17 | 0 |
| hydrolyzer | pressure | bar | 7200 | 0 | 7200 | 0 | 0 | 2.225 | 2.529 | 2.6 | 2.59721833 | 2.67 | 2.824 | 0.0541504015 | 2 | 3 | 0 | 0 |
| hydrolyzer | voltage | V | 7200 | 0 | 7200 | 0 | 0 | 68.09 | 98.57 | 99.84 | 99.7731028 | 104.26 | 110.05 | 4.28160164 | 60 | 130 | 0 | 0 |
| plant | fan_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 839.2 | 891.9 | 900 | 900.008597 | 908.2 | 920.7 | 5.04891365 | 800 | 1600 | 0 | 0 |
| plant | pump_speed | rpm | 7200 | 0 | 7200 | 0 | 0 | 568.7 | 575 | 580 | 579.988361 | 585 | 592 | 3.01936944 | 450 | 650 | 0 | 0 |

### Text signals

| source | signal | points | no value | GOOD | UNCERTAIN | BAD | values |
|---|---|---|---|---|---|---|---|
| plant | process_state | 7 | 0 | 7 | 0 | 0 | LOAD_CHANGE: 2, SHUTDOWN: 1, STARTUP: 1, STEADY_STATE: 3 |
| plant | valve_state | 3 | 0 | 3 | 0 | 0 | CLOSED: 2, OPEN: 1 |

### Intervals between points (seconds)

| signal | nominal | count | min | median | p95 | max | over 2x nominal | over 10x nominal | seconds in over-2x | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| air_flow | 1 | 5279 | 1 | 1 | 1 | 1921 | 1 | 1 | 1921 | 2026-04-20T10:17:59Z to 2026-04-20T10:50:00Z (1921 s) |
| co2_in_ppm | 2 | 2639 | 2 | 2 | 2 | 1922 | 1 | 1 | 1922 | 2026-04-20T10:17:58Z to 2026-04-20T10:50:00Z (1922 s) |
| co2_out_ppm | 2 | 2639 | 2 | 2 | 2 | 1922 | 1 | 1 | 1922 | 2026-04-20T10:17:58Z to 2026-04-20T10:50:00Z (1922 s) |
| pressure_drop | 2 | 2639 | 2 | 2 | 2 | 1922 | 1 | 1 | 1922 | 2026-04-20T10:17:58Z to 2026-04-20T10:50:00Z (1922 s) |
| solvent_flow | 2 | 2639 | 2 | 2 | 2 | 1922 | 1 | 1 | 1922 | 2026-04-20T10:17:58Z to 2026-04-20T10:50:00Z (1922 s) |
| solvent_pH | 5 | 1055 | 5 | 5 | 5 | 1925 | 1 | 1 | 1925 | 2026-04-20T10:17:55Z to 2026-04-20T10:50:00Z (1925 s) |
| solvent_temperature | 5 | 1055 | 5 | 5 | 5 | 1925 | 1 | 1 | 1925 | 2026-04-20T10:17:55Z to 2026-04-20T10:50:00Z (1925 s) |
| ambient_pressure | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:01:00Z (60 s) |
| ambient_temperature | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:01:00Z (60 s) |
| available_solar_power | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:01:00Z (60 s) |
| relative_humidity | 60 | 119 | 60 | 60 | 60 | 60 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:01:00Z (60 s) |
| acid_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:05Z (5 s) |
| base_pH | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:05Z (5 s) |
| conductivity | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:05Z (5 s) |
| current | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| current_setpoint | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| electrolyte_temperature | 5 | 1439 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:05Z (5 s) |
| flow | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| power | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| pressure | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| voltage | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| fan_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| process_state | n/a | 6 | 133 | 158.5 | 3312.75 | 3467 | n/a | n/a | n/a | 2026-04-20T10:57:13Z to 2026-04-20T11:55:00Z (3467 s) |
| pump_speed | 1 | 7199 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:01Z (1 s) |
| valve_state | n/a | 2 | 20 | 3585 | 6793.5 | 7150 | n/a | n/a | n/a | 2026-04-20T10:00:20Z to 2026-04-20T11:59:30Z (7150 s) |

### Runs of identical values

| signal | runs | median samples | max samples | max seconds | longest run |
|---|---|---|---|---|---|
| air_flow | 5262 | 1 | 2 | 1 | 2026-04-20T10:00:42Z to 2026-04-20T10:00:43Z: 2 samples of 1201.4 |
| co2_in_ppm | 2559 | 1 | 3 | 4 | 2026-04-20T10:11:36Z to 2026-04-20T10:11:40Z: 3 samples of 419.7 |
| co2_out_ppm | 1244 | 1 | 1350 | 2698 | 2026-04-20T11:00:00Z to 2026-04-20T11:44:58Z: 1350 samples of 38 |
| pressure_drop | 2606 | 1 | 2 | 2 | 2026-04-20T10:02:52Z to 2026-04-20T10:02:54Z: 2 samples of 15.14 |
| solvent_flow | 2602 | 1 | 2 | 2 | 2026-04-20T10:00:42Z to 2026-04-20T10:00:44Z: 2 samples of 9.5 |
| solvent_pH | 1052 | 1 | 2 | 5 | 2026-04-20T11:10:30Z to 2026-04-20T11:10:35Z: 2 samples of 7.647 |
| solvent_temperature | 1046 | 1 | 2 | 5 | 2026-04-20T10:01:45Z to 2026-04-20T10:01:50Z: 2 samples of 30.62 |
| ambient_pressure | 118 | 1 | 2 | 60 | 2026-04-20T10:22:00Z to 2026-04-20T10:23:00Z: 2 samples of 1013.05 |
| ambient_temperature | 117 | 1 | 2 | 60 | 2026-04-20T10:45:00Z to 2026-04-20T10:46:00Z: 2 samples of 26.71 |
| available_solar_power | 120 | 1 | 1 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:00Z: 1 samples of 398.44 |
| relative_humidity | 120 | 1 | 1 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:00Z: 1 samples of 37.1 |
| acid_pH | 1429 | 1 | 3 | 10 | 2026-04-20T10:58:25Z to 2026-04-20T10:58:35Z: 3 samples of 2.059 |
| base_pH | 1434 | 1 | 2 | 5 | 2026-04-20T10:02:10Z to 2026-04-20T10:02:15Z: 2 samples of 11.82 |
| conductivity | 1413 | 1 | 3 | 10 | 2026-04-20T10:43:30Z to 2026-04-20T10:43:40Z: 3 samples of 227 |
| current | 7135 | 1 | 3 | 2 | 2026-04-20T11:54:48Z to 2026-04-20T11:54:50Z: 3 samples of 149.9 |
| current_setpoint | 305 | 1 | 2970 | 2969 | 2026-04-20T10:00:30Z to 2026-04-20T10:49:59Z: 2970 samples of 150 |
| electrolyte_temperature | 1417 | 1 | 3 | 10 | 2026-04-20T11:00:00Z to 2026-04-20T11:00:10Z: 3 samples of 48.28 |
| flow | 7145 | 1 | 2 | 1 | 2026-04-20T10:01:18Z to 2026-04-20T10:01:19Z: 2 samples of 36.86 |
| power | 7194 | 1 | 2 | 1 | 2026-04-20T10:27:07Z to 2026-04-20T10:27:08Z: 2 samples of 15049.4 |
| pressure | 7131 | 1 | 3 | 2 | 2026-04-20T11:00:13Z to 2026-04-20T11:00:15Z: 3 samples of 2.605 |
| voltage | 7077 | 1 | 3 | 2 | 2026-04-20T11:30:41Z to 2026-04-20T11:30:43Z: 3 samples of 99.83 |
| fan_speed | 7156 | 1 | 2 | 1 | 2026-04-20T10:01:28Z to 2026-04-20T10:01:29Z: 2 samples of 904.3 |
| process_state | 7 | 1 | 1 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:00Z: 1 samples of STARTUP |
| pump_speed | 7141 | 1 | 2 | 1 | 2026-04-20T10:04:29Z to 2026-04-20T10:04:30Z: 2 samples of 581.7 |
| valve_state | 3 | 1 | 1 | 0 | 2026-04-20T10:00:00Z to 2026-04-20T10:00:00Z: 1 samples of CLOSED |

### Step-to-step change (each value minus the previous)

| signal | count | mean | stddev | median abs | p95 abs | max abs |
|---|---|---|---|---|---|---|
| air_flow | 5279 | -0.000606175412 | 11.2922042 | 7.6 | 22.3 | 38.1 |
| co2_in_ppm | 2639 | 0.0010989011 | 1.72629694 | 1.1 | 3.4 | 6.9 |
| co2_out_ppm | 2639 | 0.00227358848 | 1.94609759 | 0 | 1.9 | 64.9 |
| pressure_drop | 2639 | 0.000162940508 | 0.348462468 | 0.23 | 0.68 | 1.38 |
| solvent_flow | 2639 | -9.09435392e-05 | 0.200503515 | 0.14 | 0.39 | 0.82 |
| solvent_pH | 1055 | 3.79146919e-06 | 0.0716100683 | 0.05 | 0.136 | 0.277 |
| solvent_temperature | 1055 | 0.00627488152 | 0.422232546 | 0.28 | 0.82 | 1.59 |
| ambient_pressure | 119 | -0.00386554622 | 0.0962439454 | 0.05 | 0.171 | 0.35 |
| ambient_temperature | 119 | 0.00915966387 | 0.175042754 | 0.12 | 0.34 | 0.47 |
| available_solar_power | 119 | 0.32092437 | 23.4017508 | 14.66 | 45.909 | 59.67 |
| relative_humidity | 119 | 0.00420168067 | 2.19700856 | 1.6 | 4.12 | 6.3 |
| acid_pH | 1439 | -2.2237665e-05 | 0.0725087654 | 0.049 | 0.1411 | 0.268 |
| base_pH | 1439 | 0.000220986796 | 0.0714802156 | 0.049 | 0.14 | 0.287 |
| conductivity | 1439 | 0.0186935372 | 2.71715909 | 1.8 | 5.5 | 8.6 |
| current | 7199 | 0.00245589665 | 0.499820665 | 0.3 | 0.91 | 4.39 |
| current_setpoint | 7199 | 6.94540908e-05 | 2.03661618 | 0 | 0 | 150 |
| electrolyte_temperature | 1439 | 0.0113968033 | 0.280087276 | 0.18 | 0.55 | 1.11 |
| flow | 7199 | 0.000298652591 | 0.56641042 | 0.37 | 1.12 | 2.35 |
| power | 7199 | 0.179330463 | 60.6026773 | 37.9 | 113.91 | 362.9 |
| pressure | 7199 | -5.55632727e-06 | 0.0431826149 | 0.029 | 0.085 | 0.194 |
| voltage | 7199 | 0.000602861509 | 0.222153816 | 0.15 | 0.43 | 1.45 |
| fan_speed | 7199 | -0.00158355327 | 7.10329125 | 4.8 | 13.6 | 70.2 |
| pump_speed | 7199 | -0.000541741909 | 4.25041142 | 2.9 | 8.4 | 17 |

### Relationship: power vs voltage x current

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.999999979 |
| residual_mean | -0.0121135833 |
| residual_stddev | 0.521356872 |
| residual_median | -0.00615 |
| residual_p05 | -0.887405 |
| residual_p95 | 0.84625 |
| residual_max_abs | 1.4984 |
| relative_residual_median | 2.58868953e-05 |
| relative_residual_p95 | 6.75926528e-05 |
| power_zero_instants | 1 |
| slope | 0.999999113 |
| intercept | 0.00112544526 |
| r2 | 0.999999958 |

### Relationship: co2 out vs co2 in

| measure | value |
|---|---|
| instants_matched | 2640 |
| instants_unmatched | 0 |
| corr | -0.00418992875 |
| ratio_median | 0.0909961686 |
| ratio_p05 | 0.0901542112 |
| ratio_p95 | 0.245856396 |
| out_at_or_above_in | 0 |

### Relationship: current vs current setpoint

| measure | value |
|---|---|
| instants_matched | 7200 |
| instants_unmatched | 0 |
| corr | 0.925994482 |
| difference_mean | -0.0815652778 |
| difference_stddev | 8.89264703 |
| difference_median | 0.01 |
| difference_max_abs | 145.79 |
| best_lag_s | 24 |
| corr_at_best_lag | 0.97121312 |

### Relationship: pressure drop vs air flow

| measure | value |
|---|---|
| instants_matched | 2640 |
| instants_unmatched | 0 |
| corr | -0.0259043278 |
| slope_air_flow | -0.000927397213 |
| intercept_air_flow | 16.3785237 |
| r2_air_flow | 0.000671034201 |
| slope_air_flow_sq | -3.87992334e-07 |
| intercept_air_flow_sq | 15.8243816 |
| r2_air_flow_sq | 0.000676796477 |

## Timing

188 queries, 15.617 s.
