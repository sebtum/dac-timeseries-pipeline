# Data Dictionary

## `data/raw/dac_raw_timeseries.csv`

Long format, one reading per row:

| column | meaning |
|---|---|
| `timestamp` | ISO 8601. Different sources are logged by different systems — don't assume they all use the same timezone convention without checking. |
| `experiment_id` | `EXP_001` .. `EXP_006` |
| `source` | which subsystem/logger produced the reading: `ambient`, `absorber`, `hydrolyzer`, `plant` |
| `signal` | see table below |
| `value` | numeric for most signals; a few are categorical strings (noted below) |
| `quality` | `GOOD` / `UNCERTAIN` / `BAD`, as flagged at acquisition time. This is not exhaustive — the absence of a BAD flag is not a guarantee that a value is trustworthy. |

Sampling rate is not the same for every signal, and isn't necessarily perfectly constant
even within one signal — check actual intervals in the data rather than assuming a fixed
rate throughout.

## `data/raw/experiments.json`

Per-experiment metadata: `experiment_id`, `start_time`, `end_time`, `duration_s`,
`current_setpoint_nominal_A`, `air_flow_nominal_m3h`, `solvent_flow_nominal_Lmin`,
`operator`, `sorbent_batch`, `notes`. Not every field is populated for every experiment.

## Signals

### Ambient (`source = ambient`, roughly 1 sample/min)

| signal | unit | typical range |
|---|---|---|
| `ambient_temperature` | °C | roughly -5 to 30 |
| `relative_humidity` | % | roughly 20 to 100 |
| `ambient_pressure` | hPa | roughly 990 to 1030 |
| `available_solar_power` | kW | 0 up to ~550, depends on time of day |

### Absorber (`source = absorber`, mixed rates — see below)

| signal | unit | typical range |
|---|---|---|
| `air_flow` | m³/h | roughly 1000 to 2500 |
| `co2_in_ppm` | ppm | roughly 400 to 430 (ambient outdoor air) |
| `co2_out_ppm` | ppm | roughly 50 to 200 |
| `solvent_flow` | L/min | roughly 7 to 10 |
| `solvent_temperature` | °C | roughly 5 to 40 |
| `solvent_pH` | — | roughly 6 to 9 |
| `pressure_drop` | mbar | roughly 10 to 65, scales with air flow |

### Hydrolyzer (`source = hydrolyzer`, mixed rates — see below)

| signal | unit | typical range |
|---|---|---|
| `current_setpoint` | A | 0 to ~260 (commanded value) |
| `current` | A | 0 to ~260 (measured, follows setpoint with some lag) |
| `voltage` | V | roughly 60 to 130 (stack terminal voltage) |
| `power` | W | 0 up to ~35000 |
| `acid_pH` | — | roughly 0.5 to 4 |
| `base_pH` | — | roughly 10 to 13.5 |
| `conductivity` | mS/cm | roughly 150 to 240 |
| `electrolyte_temperature` | °C | roughly 0 to 45 |
| `flow` | L/min | roughly 25 to 55 (electrolyte loop, distinct from `solvent_flow`) |
| `pressure` | bar | roughly 2 to 3 |

### Plant (`source = plant`, event-based — a row is written when the value changes)

| signal | values | meaning |
|---|---|---|
| `pump_speed` | rpm, roughly 450–650 | solvent pump drive speed |
| `fan_speed` | rpm, roughly 800–1600 | absorber fan drive speed |
| `valve_state` | `OPEN` / `CLOSED` (categorical) | main process valve |
| `process_state` | `STARTUP` / `STEADY_STATE` / `LOAD_CHANGE` / `SHUTDOWN` (categorical) | plant-level phase |

## Sampling rates (nominal)

- **~1 Hz**: `current_setpoint`, `current`, `voltage`, `power`, `flow`, `pressure`,
  `air_flow`, `pump_speed`, `fan_speed`
- **~0.5 Hz**: `co2_in_ppm`, `co2_out_ppm`, `solvent_flow`, `pressure_drop`
- **~0.2 Hz**: `acid_pH`, `base_pH`, `solvent_pH`, `conductivity`, `electrolyte_temperature`,
  `solvent_temperature`
- **~1/60 Hz**: `ambient_temperature`, `relative_humidity`, `ambient_pressure`,
  `available_solar_power`
- **event-based**: `valve_state`, `process_state` — written on change, not polled

## Notes

- `power`, `voltage`, and `current` are independently measured/logged signals — you should
  be able to check how well they agree with each other rather than assuming they always will.
- `flow` (hydrolyzer electrolyte loop) and `solvent_flow` (absorber loop) are two different
  physical loops — don't conflate them.
- Sensor identity and experiment identity are carried as columns (`experiment_id`, `source`,
  `signal`), not encoded into a combined name — worth thinking about when you design the
  InfluxDB schema.
