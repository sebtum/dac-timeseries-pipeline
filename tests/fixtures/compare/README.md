# Compare fixture

Three experiments of 1,200 s each, built by `make_fixture.py` (stdlib only, deterministic, no import
from `pipeline/`). It is the input of the M5 end-to-end test (`tests/e2e/test_compare_cli.py`):
ingest, clean, metrics, then `python -m scripts.compare`. A voltage relationship is planted in the
hydrolyzer signals so the comparison can be checked against known coefficients. Every expected
number below is derived from the construction or computed in plain arithmetic from `readings.csv`
(no pipeline code), not read from a pipeline output. `readings.sha256` is the SHA-256 of
`readings.csv` (`tests/fixtures/.gitattributes` pins `tests/fixtures/** -text`, so git never
touches line endings; the directory is covered). Rebuild: `python tests/fixtures/compare/make_fixture.py`
twice gives byte-identical files.

33,315 rows (11,105 per experiment, header excluded). `quality` is `GOOD` everywhere except one
reading.

## Experiments (`experiments.json`)

| Experiment | Start (Z) | Setpoint (A) | Air flow (m3/h) | Solvent flow (L/min) | Batch | Operator | Notes |
|---|---|---|---|---|---|---|---|
| EXP_001 | 2026-05-04T08:00:00 | 150 | 1200 | 8.0 | SB-A | Op A | null |
| EXP_002 | 2026-05-11T09:00:00 | 200 | 1200 | 8.0 | SB-A | Op A | null |
| EXP_003 | 2026-05-18T07:30:00 | 150 | 2400 | 8.0 | SB-B | Op B | null |

End time is start + 1,200 s. The file has the shape of `data/raw/experiments.json`.

## Construction

Times are seconds after the experiment's start (`+k`). Noise is a fixed alternation of plus and
minus half the signal's declared normal step (`pipeline/cleaning_policy.py`), plus at an even
reading index (the second for 1 Hz signals). So every step equals the normal step: nothing is flat
or a spike, and cleaning accepts every normal reading.

| Signal | Rate | Values |
|---|---|---|
| process_state | on change | STARTUP +0, STEADY_STATE +120, LOAD_CHANGE +600, STEADY_STATE +660, SHUTDOWN +1140 |
| current_setpoint | 1 Hz | nominal; nominal + 20 A for +600 to +659; no noise |
| current | 1 Hz | setpoint +- 0.15 A (3 decimals) |
| flow | 1 Hz | 40 L/min + triangle wave (period 300 s, amplitude 2) +- 0.19 (3 decimals) |
| pressure | 1 Hz | 2.5 bar + triangle wave (period 420 s, amplitude 0.1) +- 0.0145 (4 decimals) |
| electrolyte_temperature | 0.2 Hz | 35 degC + 0.005 per s +- 0.095 (3 decimals) |
| voltage | 1 Hz | see below (6 decimals) |
| power | 1 Hz | voltage x current, exact decimal (9 decimals) |
| air_flow | 1 Hz | nominal +- 3.775 m3/h |
| pressure_drop | 0.5 Hz, even seconds | 15 x (nominal air flow / 1200)^2 +- 0.12 mbar (15 for EXP_001/002, 60 for EXP_003) |
| co2_in_ppm | 0.5 Hz | 420 +- 0.55 |
| co2_out_ppm | 0.5 Hz | 105 +- 0.4 |
| solvent_flow | 0.5 Hz | 8.0 +- 0.07 |
| ambient_temperature | once a minute | 15 +- 0.065 |
| relative_humidity | once a minute | 50 +- 0.7 |
| ambient_pressure | once a minute | 1013.25 +- 0.03 |

The triangle waves start at 0 and rise first. Voltage:

```
voltage = 40 + 0.3 * current - 0.2 * flow + 3.0 * pressure - 0.1 * T + e
```

`T` is the electrolyte temperature reading the as-of join pairs with that instant (the latest
reading at or before it, so at most 4 s old), and `e` is
`random.Random("compare-fixture").uniform(-0.05, 0.05)`, one draw per second, the same sequence in
each experiment (so EXP_001 and EXP_003, which share a setpoint, have identical hydrolyzer
signals). Every input is rounded to the decimals above before the voltage is computed from it.

Planted exclusion: EXP_001 voltage at +300 s (2026-05-04T08:05:00Z) is `BAD` (value as normal,
80.641757).

## Cleaning check (S5.12)

Run with the real commands into a throwaway database: `python -m scripts.ingest --csv
tests/fixtures/compare/readings.csv --experiments tests/fixtures/compare/experiments.json --sha256
tests/fixtures/compare/readings.sha256 --database <throwaway> --report-dir <tmp>` (exit 0, 33,315
saved), then `python -m scripts.clean --database <throwaway> --experiments
tests/fixtures/compare/experiments.json --report-dir <tmp>`. Result: 33,315 raw points, 33,314
accepted, **1 excluded**: EXP_001 voltage at +300 s, reason `flag_bad`, value_raw 80.641757. No
other flag fired (no `outside_typical_range` note either), 0 gap intervals, 0 flatline intervals.
Every accepted row has empty flags.

## Phases and windows (S5.2, S5.13)

Every experiment has the same 5 phases. Window = `[start + 60 s, end)` of the phase when that is
non-empty (settle margin 60 s).

| Phase | State | Start | End | Window |
|---|---|---|---|---|
| 0 | STARTUP | 0 | 120 | [60, 120) |
| 1 | STEADY_STATE | 120 | 600 | [180, 600) |
| 2 | LOAD_CHANGE | 600 | 660 | none (60 s, not more than the margin) |
| 3 | STEADY_STATE | 660 | 1140 | [720, 1140) |
| 4 | SHUTDOWN | 1140 | 1200 | none |

Steady windows: [180, 600) and [720, 1140), `steady_seconds` = 420 + 420 = **840**. The whole-run
window is [0, 1200).

## Fit instants (S5.14)

Hydrolyzer model: voltage, current, flow, pressure at the same second, electrolyte temperature
as-of (at most 10 s old; always 0 to 4 s here, readings every 5 s from +0). Only the planted
reading is missing.

| Model, window | EXP_001 | EXP_002 | EXP_003 | Pooled |
|---|---|---|---|---|
| hydrolyzer, steady | **839** | **840** | **840** | 2,519 |
| hydrolyzer, whole_run | 1,199 | 1,200 | 1,200 | 3,599 |
| absorber, steady | 419 | 420 | 420 | 1,259 |
| absorber, whole_run | 599 | 600 | 600 | 1,799 |

EXP_001 steady is 839 because +300 is in [180, 600). The absorber model uses the 0.5 Hz
pressure_drop instants (even seconds) where voltage, current and air_flow also exist.

**The absorber fits are not testable by construction.** At even seconds the alternation is always
plus, so `current` and `air_flow` are constants at every pressure_drop instant (current 150.15,
200.15, 150.15 A; air_flow 1203.775 or 2403.775). In the whole-run window current takes two values
(setpoint and setpoint + 20) but air_flow is still constant. A constant predictor makes the normal
matrix singular, so every absorber fit is `testable: false` and evidence for the absorber terms is
`not_testable`. The same constants make the per-experiment pressure_drop-on-air_flow fit
degenerate (no air_flow variation); only the across-experiments line (3 points: 1200 -> 15,
1200 -> 15, 2400 -> 60) is meaningful. Nothing in S5.13 to S5.16 relies on the absorber fits.

## Planted coefficients

voltage = 40 + **0.3** current (V/A) **- 0.2** flow (V per L/min) **+ 3.0** pressure (V/bar)
**- 0.1** electrolyte_temperature (V/degC), plus e in [-0.05, 0.05].

## Construction checks: plain OLS on the CSV (not pipeline output)

A short plain-Python OLS (normal equations on centred columns, Gaussian elimination, `math.fsum`;
no pipeline import) on the accepted rows, joined as in the fit instants above. These show the
construction can recover the planted values and the predictors are independent enough. The
pipeline's own numbers are a separate result and are compared against these only to within the
tolerances of S5.14.

Hydrolyzer, steady window (coefficients in the order current, electrolyte_temperature, flow,
pressure; R2 0.99169 for every experiment):

| Experiment | Instants | current | electrolyte_temperature | flow | pressure |
|---|---|---|---|---|---|
| EXP_001 | 839 | 0.2972 | -0.0999 | -0.1997 | 3.0052 |
| EXP_002 | 840 | 0.2973 | -0.0999 | -0.1997 | 3.0050 |
| EXP_003 | 840 | 0.2973 | -0.0999 | -0.1997 | 3.0050 |
| pooled (one intercept per experiment) | 2,519 | 0.2973 | -0.0999 | -0.1997 | 3.0051 |

VIF (1 / (1 - R2 of the term on the other three)), steady window, EXP_001 / EXP_002 / EXP_003:
current 1.092 / 1.091 / 1.091, electrolyte_temperature 1.037 / 1.037 / 1.037, flow 1.031 / 1.031 /
1.031, pressure 1.100 / 1.100 / 1.100. All far under 10, so flow and pressure are separable.

Hydrolyzer, whole-run window (R2 0.99951): current 0.3002, electrolyte_temperature -0.1000, flow
-0.2004, pressure 3.0124 (EXP_001; EXP_002 and EXP_003 within 0.0002); VIFs between 1.03 and 1.08.

Why current reads 0.297 and not 0.3 in the steady windows: current is the setpoint plus the 0.15 A
alternation, so its only variation there is the alternation, and e (up to 0.05 V) is of similar
size to that term (0.3 x 0.15 = 0.045 V). The flow and pressure terms have far more variation.

A plain block bootstrap of the steady fit (blocks of 120 s inside each window, 8 blocks, 1,000
resamples, seed text as in M5 decision 10, plain rows; an emulation, not the pipeline's code)
gave 95 percent intervals of about flow [-0.204, -0.199] and pressure [2.966, 3.055] for each
experiment, 0 singular resamples. Both exclude zero.

## Steady-state KPIs (S5.15), computed from the CSV

`voltage_mean_v`: mean of the accepted voltage at the instants in the steady windows. `mean_power_kw`:
trapezoid integral of power_computed (accepted voltage x accepted current, exact decimals) over its
covered intervals (spacing at most 2 s) inside the steady windows, divided by the covered seconds
and by 1,000. Coverage = covered seconds / 840. Covered seconds are 419 + 419 = 838 for both, in
every experiment: the instants run 180..599 and 720..1139, and in EXP_001 the missing +300 leaves
a 2 s spacing (299 to 301), which is bridged.

| Experiment | Voltage instants | Sum of voltage (V) | voltage_mean_v (V) | Power integral (W s) | mean_power_kw (kW) | Coverage | Status |
|---|---|---|---|---|---|---|---|
| EXP_001 | 839 | 67730.042578 | 80.72710676758 | 10147367.581691625 | 12.10903052708 | 838/840 = 0.997619048 | complete |
| EXP_002 | 840 | 80410.684335 | 95.72700516071 | 16043872.315697825 | 19.14543235763 | 838/840 = 0.997619048 | complete |
| EXP_003 | 840 | 67810.684335 | 80.72700516071 | 10147405.756122825 | 12.10907608129 | 838/840 = 0.997619048 | complete |

(voltage_mean_v = sum / instants; mean_power_kw = integral / 838 / 1000.) 9 significant digits:
80.7271068, 95.7270052, 80.7270052 V; 12.1090305, 19.1454324, 12.1090761 kW.

EXP_002 minus EXP_001 voltage_mean_v = 14.99989839 V (planted: 0.3 x 50 A = 15 V, less 0.0001 from
the one excluded reading). EXP_003 minus EXP_001 = -0.00010161 V. EXP_001 and EXP_003 have the
same hydrolyzer signals (the same sequences and setpoint), so they differ only by the planted
exclusion. EXP_003 differs from EXP_001 in air flow, batch and operator, none of which enters the
voltage model.

## Measured conditions and comparability (S5.16)

Measured over the steady windows from accepted readings (medians; the median of an even count of
the alternating values is their midpoint):

| Experiment | current_setpoint (A) | profile | air_flow (m3/h) | solvent_flow (L/min) | ambient_temperature (degC) | relative_humidity (%) | sorbent_batch |
|---|---|---|---|---|---|---|---|
| EXP_001 | 150 | constant | 1200 | 8.0 | 15.0 | 50.0 | SB-A |
| EXP_002 | 200 | constant | 1200 | 8.0 | 15.0 | 50.0 | SB-A |
| EXP_003 | 150 | constant | 2400 | 8.0 | 15.0 | 50.0 | SB-B |

The setpoint is constant inside the steady windows (the +20 A step is in the load-change phase,
which is outside them). Ambient has 14 readings in the steady windows (7 plus, 7 minus), so the
medians are exactly 15 and 50.

| Pair | Status | Differing factors | Recorded differences |
|---|---|---|---|
| EXP_001 - EXP_002 | supported | current_setpoint | none (same operator) |
| EXP_001 - EXP_003 | confounded | air_flow, sorbent_batch | operator (Op A vs Op B) |
| EXP_002 - EXP_003 | confounded | current_setpoint, air_flow, sorbent_batch | operator |

(150 vs 200 A differs: 50 > 0.05 x 200. 1200 vs 2400 m3/h differs. Humidity, ambient temperature,
solvent flow and profile do not differ.)

Hydrolyzer evidence expected from the construction: flow negative and pressure positive, status
`supported` (three testable fits, all intervals exclude zero with the same sign).
