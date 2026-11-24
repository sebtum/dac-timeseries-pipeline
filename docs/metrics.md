# Derived metrics: one entry per number, and how it is made

Metrics version `m4-v1`, built from accepted readings of cleaning policy `m3-v1`. Decisions and
rejected options: [ADR-0016](decisions/ADR-0016-derived-metrics.md). The numbers live in
[`pipeline/metrics.py`](../pipeline/metrics.py); a unit test (`tests/unit/test_metrics_doc.py`)
reads the entries and the constants table below and fails if a unit, a name or a value differs
from that file.

## In short

Every experiment gets 13 metrics (energy, capture, energy per kilogram of CO2, and four data
quality shares) and four derived time series. A derived value exists at an instant only when every
input is an accepted reading at that instant. Nothing is filled, clamped, smoothed or scaled up.
When readings are missing, the number is still reported, with a coverage (how much of the
experiment it is based on) and a label (`complete`, `partial` or `none`).

Details: the batch job is `python -m scripts.metrics`, run after cleaning. It reads accepted
readings only (`verdict = accepted` in `readings_processed`), one experiment window at a time.
It writes four series to InfluxDB (`metrics_series`) and two small tables to Postgres
(`experiment_metrics`, `signal_quality`), and a summary `reports/metrics_summary.json` that follows
`contracts/metrics_summary.schema.json`. Fingerprint of the constants table: it begins
`ac004cdd` (`METRICS_FINGERPRINT`, the SHA-256 of the canonical JSON of the 10 constants).

## 1. The constants

Every number the rules read is one of these ten, in one declared table (`POLICY`). A changed
number is a new metrics version, and a test fails if one changes without it. The meaning column
says what the number controls.

| Constant | Value | Meaning |
|---|---|---|
| `power_max_spacing_s` | 2 | Longest spacing between two power points that is bridged (2 x the 1 s nominal). A longer spacing is a gap. |
| `capture_max_spacing_s` | 4 | Same for the capture and efficiency series (2 x the 2 s nominal). |
| `ambient_max_age_s` | 120 | An ambient reading is usable at an instant when it is at most this old (2 x the 60 s nominal). |
| `power_tol_rel` | 0.01 | Relative part of the power cross-check tolerance. |
| `power_tol_w` | 10 | Absolute part of the power cross-check tolerance, in watts. |
| `complete_coverage` | 0.95 | A metric with coverage at or above this is `complete`. |
| `co2_molar_mass_kg_per_mol` | 0.04401 | Molar mass of CO2, to turn parts per million by volume into kilograms. |
| `gas_constant_j_per_mol_k` | 8.314462618 | Gas constant, for the density of the air at ambient conditions. |
| `sec_floor_kwh_per_kg` | 0.1 | Plausibility floor for energy per kilogram of CO2. |
| `energy_agreement_rel` | 0.01 | Largest accepted relative difference between computed and logged energy. |

Details: three physical conversions that cannot change are plain module constants and are not in
the fingerprint, because they are not choices: 273.15 (degrees Celsius to kelvin), 100 (hPa to
Pa) and 1e-6 (ppm to a fraction). The unit scalings (3.6e6 W s per kWh, 3600 s per hour) are
module constants too. A spacing equal to the limit is bridged; one nanosecond more is not. Ambient
age is compared the same way: 120 s is used, 120 s plus 1 ns is not.

## 2. How the pieces fit together

### Which readings go in

Only accepted readings are inputs. A reading the cleaning step excluded (a bad flag, an impossible
value, a spike, a stuck stretch) is not used, and it is not replaced by anything. A derived value at
an instant exists only when every input is accepted at that instant.

Details: small negative currents stay (cleaning decision 4), so computed power can be slightly
negative. Metrics read `readings_processed` for one policy version (`--policy-version`, default
`m3-v1`).

### Alignment: how signals of different rates meet

| Signals | Rule | Why |
|---|---|---|
| voltage, current, power (1 Hz) | Join on the exact same instant. | They share their instants, so no resampling is needed. |
| `co2_in_ppm`, `co2_out_ppm`, `air_flow` | Join on the exact same instant, at the 0.5 Hz instants of the two CO2 signals. | The two CO2 signals share their instants and air flow (1 Hz) has a reading at each of them. |
| ambient temperature and pressure (once a minute) | As-of: the latest accepted reading at or before the instant, if it is at most 120 s old. Otherwise no value. | A slow signal is carried to the next fast instant. Interpolating between two readings would invent values. |

Details: the same rule as the alignment rule in `cleaning_policy.md` section 6 (2 x nominal), with
exact-instant joins added for signals that share instants (the profile found 0 unmatched instants
among the three CO2 and air-flow signals). Rejected: resampling onto a grid, and linear
interpolation of ambient values (both fill).

### Gap rule: what an integral may bridge

The metrics that add up over time (energy, captured CO2) use the trapezoid rule over consecutive
derived points. A spacing longer than twice the nominal spacing is a gap and is not bridged: it adds
nothing to the integral and nothing to the covered time. The result is never scaled up to the full
duration.

| Series | Nominal spacing | Longest bridged spacing |
|---|---|---|
| power (`power_computed`, logged power) | 1 s | 2 s |
| capture (`capture_rate`, inlet, `capture_efficiency`) | 2 s | 4 s |

Details: covered seconds are the sum of the bridged spacings, summed with `math.fsum`. Example: a
600 s run with 16 s not bridged gives an energy over 584 s and a coverage of 0.9733. The mean of
capture efficiency is a plain mean over its instants, but its coverage uses the same 4 s rule.

### Label rule: complete, partial or none

Every metric is an object `{value, unit, coverage, status}`. Coverage is covered seconds divided by
the experiment length. The label is `complete` at 0.95 or more, `partial` below that, and `none`
exactly when the value is null. The value is always reported when it can be computed. Whether a
`partial` number is good enough to compare is M5's decision, not this step's.

Details: coverage is 0.0 with status `none` when no time is covered. The four data-quality shares
have coverage and status null (they are shares of counts, not integrals over time). The coverage of
each metric is given in its entry below.

## 3. The 13 metrics

### Energy and power

#### `energy_kwh`

How much electrical energy the electrolyser took in, from voltage times current added up over time.

Details: the trapezoid integral of `power_computed` over bridged spacings, in W s, divided by 3.6e6.
Null when nothing is covered.

- **Unit:** `kWh`
- **Inputs:** accepted `voltage` and `current`.
- **Alignment:** same instant.
- **Gap rule:** a spacing above 2 s is not bridged.
- **Label rule:** coverage = covered seconds of `power_computed` / experiment length.

#### `energy_logged_kwh`

The same energy, but from the power value the plant logged itself. It is the independent second
opinion on `energy_kwh`.

Details: the trapezoid integral of the accepted logged `power` over bridged spacings, divided by
3.6e6. Integrated over its own covered time, which can differ from the computed series by a few
readings.

- **Unit:** `kWh`
- **Inputs:** accepted `power`.
- **Alignment:** none needed (one signal).
- **Gap rule:** a spacing above 2 s is not bridged.
- **Label rule:** coverage = covered seconds of the logged power / experiment length.

#### `energy_relative_difference`

How far the logged energy is from the computed energy, as a fraction of the computed energy. A
number near 0 means the two agree.

Details: `(E_logged - E_computed) / E_computed`, with both energies integrated over the overlap of
the two covered-interval sets, so that one reading more or less in one of them does not show as
disagreement. Each series is integrated exactly over the overlap (its piecewise-linear line,
clipped at the overlap's ends). Null when the overlap is empty or `E_computed` is 0. Positive means
the logged power is higher.

- **Unit:** `fraction`
- **Inputs:** accepted `voltage`, `current` and `power`.
- **Alignment:** same instant; the two series are compared over the time both are covered.
- **Gap rule:** a spacing above 2 s is not bridged, in either series.
- **Label rule:** coverage = overlap seconds / experiment length.

#### `mean_power_kw`

The average power over the time that was covered.

Details: `energy_kwh / (covered seconds / 3600)`. Null when `energy_kwh` is null.

- **Unit:** `kW`
- **Inputs:** the same as `energy_kwh`.
- **Alignment:** same instant.
- **Gap rule:** a spacing above 2 s is not bridged.
- **Label rule:** coverage = covered seconds of `power_computed` / experiment length (same as
  `energy_kwh`).

### CO2 capture

#### `capture_efficiency_mean`

On average, which share of the CO2 going in was taken out.

Details: the plain mean (`math.fsum` over the count) of the `capture_efficiency` series,
`(co2_in - co2_out) / co2_in`. It is not weighted by air flow. Values at or below 0 are kept and
counted (`efficiency_check.at_or_below_zero`). An instant with `co2_in` equal to 0 is skipped.

- **Unit:** `fraction`
- **Inputs:** accepted `co2_in_ppm` and `co2_out_ppm`.
- **Alignment:** same instant (the 0.5 Hz instants).
- **Gap rule:** coverage uses a spacing above 4 s as a gap; the mean itself is over all instants.
- **Label rule:** coverage = covered seconds of the efficiency series / experiment length.

#### `co2_captured_kg`

How much CO2 was removed from the air in the covered time.

Details: the trapezoid integral of the `capture_rate` series over bridged spacings, divided by 3600
(kg/h times seconds to kg). Null when nothing is covered.

- **Unit:** `kg`
- **Inputs:** accepted `co2_in_ppm`, `co2_out_ppm`, `air_flow`, `ambient_temperature` and
  `ambient_pressure`.
- **Alignment:** CO2 and air flow on the same instant; ambient as-of within 120 s.
- **Gap rule:** a spacing above 4 s is not bridged.
- **Label rule:** coverage = covered seconds of the capture series / experiment length.

#### `co2_inlet_kg`

How much CO2 went into the absorber in the covered time. It is the ceiling for `co2_captured_kg`.

Details: the same integral, with the inlet concentration `co2_in` alone instead of `co2_in -
co2_out`. It uses the capture series' instants, so both totals cover the same time.

- **Unit:** `kg`
- **Inputs:** the same as `co2_captured_kg`.
- **Alignment:** same as `co2_captured_kg`.
- **Gap rule:** a spacing above 4 s is not bridged.
- **Label rule:** coverage = covered seconds of the capture series / experiment length.

#### `capture_rate_mean_kg_h`

The average rate at which CO2 was removed, in the covered time.

Details: `co2_captured_kg / (covered seconds / 3600)`. Null when `co2_captured_kg` is null.

- **Unit:** `kg/h`
- **Inputs:** the same as `co2_captured_kg`.
- **Alignment:** same as `co2_captured_kg`.
- **Gap rule:** a spacing above 4 s is not bridged.
- **Label rule:** coverage = covered seconds of the capture series / experiment length (same as
  `co2_captured_kg`).

#### `sec_kwh_per_kg`

How much electrical energy it took to capture one kilogram of CO2 (specific energy consumption).
Energy and CO2 are taken from the same stretch of time, so the ratio compares like with like.

Details: energy of `power_computed` over the overlap of the power covered time and the capture
covered time, divided by the CO2 captured over that same overlap. Each series is integrated exactly
over the overlap (piecewise-linear line, clipped at the ends). Null when the overlap is empty or the
captured CO2 over it is 0 or less. Rejected: total energy divided by total CO2 over different
covered times.

- **Unit:** `kWh/kg`
- **Inputs:** everything in `energy_kwh` and `co2_captured_kg`.
- **Alignment:** as for each of the two.
- **Gap rule:** a spacing above 2 s (power) or 4 s (capture) is not bridged.
- **Label rule:** coverage = overlap seconds / experiment length. It can be below both of its
  inputs' coverage.

### Data quality shares

The four shares count readings, not time. They say how much of what was expected is there and how
much of what is there was usable. They come from counts per signal (section 5), so a signal with no
readings is still listed.

#### `completeness`

How many readings are there compared with how many a steady sensor would have produced.

Details: the sum of `present` divided by the sum of `expected` over the polled signals.
`present` is every processed row, whatever its verdict; `expected` is `floor(duration / nominal
interval)`. The two on-change state signals have no expected count and are left out of this share.
Null when the denominator is 0.

- **Unit:** `fraction`
- **Inputs:** processed row counts of all 23 polled signals.
- **Alignment:** none.
- **Gap rule:** none; a gap shows up as a lower count.
- **Label rule:** coverage and status are null.

#### `valid_fraction`

The share of readings that were accepted by cleaning.

Details: the sum of `accepted` divided by the sum of `present` over all 25 signals. Null when no
reading is present.

- **Unit:** `fraction`
- **Inputs:** processed row counts of all 25 signals.
- **Alignment:** none.
- **Gap rule:** none.
- **Label rule:** coverage and status are null.

#### `bad_fraction`

The share of readings the instrument itself marked BAD.

Details: the sum of `bad` (acquisition quality `BAD`) divided by the sum of `present` over all 25
signals. It counts the instrument's flag, not the cleaning verdict. Null when no reading is present.

- **Unit:** `fraction`
- **Inputs:** processed row counts of all 25 signals.
- **Alignment:** none.
- **Gap rule:** none.
- **Label rule:** coverage and status are null.

#### `uncertain_fraction`

The share of readings the instrument marked UNCERTAIN.

Details: the sum of `uncertain` (acquisition quality `UNCERTAIN`) divided by the sum of `present`
over all 25 signals. Null when no reading is present.

- **Unit:** `fraction`
- **Inputs:** processed row counts of all 25 signals.
- **Alignment:** none.
- **Gap rule:** none.
- **Label rule:** coverage and status are null.

## 4. The four derived series

The series are written to InfluxDB in the table `metrics_series` (tags `experiment_id`, `metric`,
`metrics_version`, `policy_version`; one float field `value`; time is the instant). A point exists
only where the value exists. They are what the integrals are made from, and what a dashboard can
plot.

#### `power_computed`

Voltage times current at each instant where both were accepted.

Details: `voltage x current`, in watts.

- **Unit:** `W`
- **Inputs:** accepted `voltage` and `current`.
- **Alignment:** same instant.
- **Gap rule:** none for the series itself; its integral bridges up to 2 s.
- **Label rule:** none (it is a series, not a summary).

#### `power_residual`

How far the logged power is from voltage times current, at each instant where all three were
accepted.

Details: `power - voltage x current`, in watts. It is signed: positive when the logged power is
higher.

- **Unit:** `W`
- **Inputs:** accepted `power`, `voltage` and `current`.
- **Alignment:** same instant.
- **Gap rule:** none.
- **Label rule:** none.

#### `capture_efficiency`

The share of CO2 removed, at each instant where both CO2 readings were accepted.

Details: `(co2_in - co2_out) / co2_in`. Values at or below 0 are kept. An instant with `co2_in` equal
to 0 is skipped.

- **Unit:** `fraction`
- **Inputs:** accepted `co2_in_ppm` and `co2_out_ppm`.
- **Alignment:** same instant.
- **Gap rule:** none for the series itself; its coverage bridges up to 4 s.
- **Label rule:** none.

#### `capture_rate`

How fast CO2 was removed, at each instant where CO2 in, CO2 out, air flow, ambient temperature and
ambient pressure were all available.

Details: `air_flow [m3/h] x (co2_in - co2_out) [ppm] x 1e-6 x p x M / (R x T)`, with `p` the ambient
pressure in Pa (hPa x 100), `T` the ambient temperature in K (degrees Celsius + 273.15), `M` the
molar mass of CO2 and `R` the gas constant from the constants table. The same formula with `co2_in`
alone gives the inlet rate used by `co2_inlet_kg`. Rejected: a fixed standard density (about 12 %
off across the ambient range of -5 to 30 degrees Celsius).

- **Unit:** `kg/h`
- **Inputs:** accepted `co2_in_ppm`, `co2_out_ppm`, `air_flow`, `ambient_temperature` and
  `ambient_pressure`.
- **Alignment:** CO2 and air flow on the same instant; ambient as-of within 120 s.
- **Gap rule:** none for the series itself; its integral bridges up to 4 s.
- **Label rule:** none.

Details: the capture formula assumes air flow in actual cubic metres per hour at ambient conditions,
ppm by volume, humidity ignored and outlet volume equal to inlet volume (assumption A-08 in
`ASSUMPTIONS.md`). If the meter reports normal cubic metres instead, the capture rate is off by the
ratio of the ambient to the standard air density, up to about 12 %.

## 5. The power cross-check

The data dictionary invites comparing the logged `power` with voltage times current. The summary
reports that comparison for each experiment under `power_check`.

| Measure | What it is |
|---|---|
| `instants_compared` | Instants where power, voltage and current are all accepted. |
| `within_tolerance` | Of those, instants where `abs(residual) <= 0.01 x abs(voltage x current) + 10` (watts). |
| `within_tolerance_fraction` | `within_tolerance / instants_compared`. |
| `residual_median_w` | The median of the SIGNED residual. |
| `residual_p95_abs_w` | The 95th percentile of the ABSOLUTE residual (linear interpolation between order statistics). |
| `residual_max_abs_w` | The largest ABSOLUTE residual. |

Details: be careful with the first of the three residual statistics. `residual_median_w` is the
median of the signed residual, so it says whether the logged power sits above (positive) or below
(negative) voltage times current in the middle of the distribution; it can be near 0 while large
errors of both signs exist. `residual_p95_abs_w` and `residual_max_abs_w` are of the absolute
residual, so they never say which side. The tolerance uses the two constants `power_tol_rel` and
`power_tol_w`. The summary also reports `efficiency_check` (`instants`, `at_or_below_zero`).

## 6. Plausibility checks

Four checks per experiment test whether the numbers are physically possible. They are sanity
checks, not findings. A check that fails turns the exit code to 1, and the outputs are still
written. A check on a null metric has `passed` null.

| Check | Passes when | Limit |
|---|---|---|
| `efficiency_in_unit_interval` | `0 <= capture_efficiency_mean <= 1` | 1 |
| `capture_below_inlet` | `co2_captured_kg <= co2_inlet_kg` | `co2_inlet_kg` (0.0 when it is null) |
| `sec_above_floor` | `sec_kwh_per_kg >= sec_floor_kwh_per_kg` | 0.1, below the minimum work of separating CO2 from air |
| `energy_agreement` | `abs(energy_relative_difference) <= energy_agreement_rel` | 0.01 |

Details: the contract wants a number in `limit`, so `capture_below_inlet` reports 0.0 with `passed`
null when the inlet total is null. Raw-data estimates before the run gave 9 to 43 kWh/kg; the run
reports its numbers and claims nothing beyond them.

## 7. Data quality per signal

For every experiment and for all 25 declared signal pairs (a pair with no readings is listed with
`present` 0), the summary holds:

| Field | Meaning |
|---|---|
| `present` | Processed rows, whatever their verdict (`readings_processed`, or `state_intervals` for the two state signals). |
| `expected` | `floor(duration / nominal interval)` for polled signals. Null for on-change state signals (the on-change staleness mistake, C-01 in `MISTAKES.md`: silence means no change, not no data). |
| `accepted` | Rows with verdict `accepted`. |
| `bad`, `uncertain` | Rows whose acquisition quality is BAD or UNCERTAIN. |
| `completeness` | `present / expected` (null when `expected` is null or 0). |
| `valid_fraction` | `accepted / present`. |
| `bad_fraction`, `uncertain_fraction` | `bad / present`, `uncertain / present` (null when `present` is 0). |

Details: the counts come from a SQL `GROUP BY` over both processed tables (no `FILTER` clause). The
experiment-level shares in section 3 are sums over these rows.

## 8. Why an integrated energy value is not treated like a pH or a state

| Kind | Example | How it is handled here | Why |
|---|---|---|---|
| An integral | `energy_kwh`, `co2_captured_kg` | Needs covered time. Added up only over bridged spacings; the covered time is reported as coverage; nothing is scaled up or filled. | An integral adds every reading into one running total, so a missing stretch changes it by a large amount. The honest answer is the total over what was seen, with the share of time that is. |
| A level at an instant | `solvent_pH`, `capture_efficiency_mean` | A value of the signal at an instant. Reported from the readings that exist; coverage and labels say how many. Nothing is added up over time, so there is nothing to bridge. | A pH reading is a statement about one moment. A missing minute does not change the readings of the other minutes. |
| A state | `process_state` | Not used in any metric. Where needed it is carried forward until the next event (cleaning policy section 6). | A state is true until the next event. Averaging it is meaningless. |

Details: this is the M4 half of the pH, state and energy contrast written in
`cleaning_policy.md` section 5. Cleaning decided which `power` readings are accepted; this step
decides what an integral over them means when stretches are missing. The answer is: report it over
the covered time, say how much that is, and never fill.

## 9. What a number here is not

- **Not a finding.** These numbers are inputs for the comparison milestone (M5). The run states
  them and checks them for physical possibility. It does not say which experiment is better, and no
  claim is made about flow or pressure against voltage.
- **Not comparable by default.** A metric with status `partial` rests on a smaller part of its
  experiment. Whether two experiments can be set side by side is M5's decision.
- **Not a measurement of the plant's truth.** A cleaning call (for example, the excluded EXP_004
  air-flow hour) lowers the coverage of the capture metrics for that experiment. It is a cleaning
  call, not a finding about the plant.
- **Not tuned.** The constants and the expected labels were written down in the plan before the
  real run. A different label would have stopped the run, not changed a constant.

Details: the capture metrics rest on assumption A-08 (actual cubic metres per hour, humidity
ignored). The real-run numbers and the things to review are in [`reports/M4.md`](../reports/M4.md).
