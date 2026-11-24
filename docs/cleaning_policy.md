# Cleaning policy: one row per signal, and why

Policy version `m3-v1`. Decisions and rejected options: [ADR-0015](decisions/ADR-0015-cleaning-and-quality-pipeline.md).
The numbers live in [`pipeline/cleaning_policy.py`](../pipeline/cleaning_policy.py); a unit test
(`tests/unit/test_policy_doc.py`) reads the table below and fails if it differs from that file.

## In short

Every stored reading gets a verdict: accepted or excluded. An excluded reading stays in the
database with its raw value and a reason. Nothing is deleted, filled in, smoothed or clamped.
Each signal has its own limits and its own "normal step", because a pH, a plant state and a
voltage do not behave alike.

Details: the verdict is written beside the raw value in `readings_processed` (numeric signals) and
`state_intervals` (the two state signals). A reading is excluded exactly when its `reason` is
not empty. The reason is the first rule that fired; `flags` lists every rule that fired.

## 1. The policy table

Read it as: "for this signal, a value outside Limit low to Limit high is impossible and is
excluded; a step much bigger than Step that does not hold is a spike; a long stretch of steps
much smaller than Step is a stuck sensor". Units and typical ranges are from
`task/DATA_DICTIONARY.md`. Numbers are plain decimals so a test can compare them.

| Source | Signal | Class | Nominal s | Limit low | Limit high | Typical low | Typical high | Step | Spike | Flatline | Exact repeat | Half-window | Gaps | Allowed values |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ambient | ambient_temperature | measured | 60 | -40 | 60 | -5 | 30 | 0.13 | yes | yes | no | 5 | yes | - |
| ambient | relative_humidity | measured | 60 | 0 | 100 | 20 | 100 | 1.4 | yes | yes | no | 5 | yes | - |
| ambient | ambient_pressure | measured | 60 | 900 | 1100 | 990 | 1030 | 0.06 | yes | yes | no | 5 | yes | - |
| ambient | available_solar_power | measured | 60 | 0 | 1000 | 0 | 550 | 12.255 | yes | yes | yes | 5 | yes | - |
| absorber | air_flow | measured | 1 | 0 | 5000 | 1000 | 2500 | 7.55 | yes | yes | no | 30 | yes | - |
| absorber | co2_in_ppm | measured | 2 | 0 | 5000 | 400 | 430 | 1.1 | yes | yes | no | 15 | yes | - |
| absorber | co2_out_ppm | measured | 2 | 0 | 5000 | 50 | 200 | 0.8 | yes | yes | no | 15 | yes | - |
| absorber | solvent_flow | measured | 2 | 0 | 50 | 7 | 10 | 0.14 | yes | yes | no | 15 | yes | - |
| absorber | solvent_temperature | measured | 5 | -10 | 100 | 5 | 40 | 0.285 | yes | yes | no | 6 | yes | - |
| absorber | solvent_pH | measured | 5 | 0 | 14 | 6 | 9 | 0.0485 | yes | yes | no | 6 | yes | - |
| absorber | pressure_drop | measured | 2 | 0 | 200 | 10 | 65 | 0.24 | yes | yes | no | 15 | yes | - |
| hydrolyzer | current_setpoint | commanded | 1 | 0 | 500 | 0 | 260 | 0 | no | no | no | - | yes | - |
| hydrolyzer | current | measured | 1 | -2 | 500 | 0 | 260 | 0.3 | yes | yes | no | 30 | yes | - |
| hydrolyzer | voltage | measured | 1 | 0 | 200 | 60 | 130 | 0.15 | yes | yes | no | 30 | yes | - |
| hydrolyzer | power | measured | 1 | -100 | 60000 | 0 | 35000 | 37.65 | yes | yes | no | 30 | yes | - |
| hydrolyzer | acid_pH | measured | 5 | 0 | 14 | 0.5 | 4 | 0.047 | yes | yes | no | 6 | yes | - |
| hydrolyzer | base_pH | measured | 5 | 0 | 14 | 10 | 13.5 | 0.0475 | yes | yes | no | 6 | yes | - |
| hydrolyzer | conductivity | measured | 5 | 0 | 1000 | 150 | 240 | 1.85 | yes | yes | no | 6 | yes | - |
| hydrolyzer | electrolyte_temperature | measured | 5 | -10 | 100 | 0 | 45 | 0.19 | yes | yes | no | 6 | yes | - |
| hydrolyzer | flow | measured | 1 | 0 | 200 | 25 | 55 | 0.38 | yes | yes | no | 30 | yes | - |
| hydrolyzer | pressure | measured | 1 | 0 | 10 | 2 | 3 | 0.029 | yes | yes | no | 30 | yes | - |
| plant | pump_speed | measured | 1 | 0 | 2000 | 450 | 650 | 2.9 | yes | yes | no | 30 | yes | - |
| plant | fan_speed | measured | 1 | 0 | 3000 | 800 | 1600 | 4.8 | yes | yes | no | 30 | yes | - |
| plant | valve_state | state | - | - | - | - | - | - | no | no | no | - | no | CLOSED, OPEN |
| plant | process_state | state | - | - | - | - | - | - | no | no | no | - | no | LOAD_CHANGE, SHUTDOWN, STARTUP, STEADY_STATE |

Column meanings:

| Column | Meaning |
|---|---|
| Class | `measured`: a sensor reading. `commanded`: a value someone set (the current setpoint). `state`: a label written when it changes. |
| Nominal s | Seconds between readings, from the data dictionary. `-` for state signals: they have no rate. |
| Limit low, Limit high | Physical limits, both ends inclusive. A value outside is impossible for this plant and is excluded. |
| Typical low, Typical high | The data dictionary's "roughly" range. Outside it is only a note, never an exclusion. |
| Step | The signal's normal reading-to-reading change: the median over the six experiments of the profile's median absolute difference. |
| Spike | Whether the spike rule applies. |
| Flatline | Whether the stuck-sensor rule applies. |
| Exact repeat | Solar only: a step counts as flat only when the value repeats exactly. |
| Half-window | Flatline looks at this many steps on each side of a step (about 30 seconds, at least 5 steps). `-` where flatline does not apply. |
| Gaps | Whether a spacing over 2 x nominal is recorded as a gap. |
| Allowed values | The only values a state signal may take. |

Details: 25 rows = 23 numeric + 2 state, one per `(source, signal)` pair. Limits are inclusive
(`low <= value <= high`). The step column is checked against `reports/post_ingest_profile.json`
at 9 significant digits by `tests/unit/test_cleaning_policy.py`, so it cannot drift from the
measured data. The half-window is `max(5, ceil(30 / nominal))`. The setpoint's step of 0 is its
profile median (a held value), and it is not used by any rule.

### Constants every numeric signal shares

| Constant | Value | Used for |
|---|---|---|
| spike_half_window | 5 | Neighbours on each side that a spike is compared with |
| spike_robust_factor | 5.0 | A spike must deviate by more than this times the neighbours' robust spread |
| spike_mad_scale | 1.4826 | Turns the median absolute deviation into a standard-deviation-sized number |
| spike_floor_steps | 10.0 | A spike must also deviate by more than this times the signal's Step |
| flat_fraction | 0.2 | A step is flat when it is smaller than this times Step |
| flat_window_seconds | 30.0 | Flatline window length in seconds |
| flat_min_half_window | 5 | Fewest steps on each side of the flatline window |
| flat_min_run | 5 | Fewest flat steps in an unbroken row for a flatline |
| gap_factor | 2.0 | A spacing over this times the nominal interval is a gap |

## 2. Reason codes, in priority order

Every reading gets at most one reason: the first one that fires in this order. `flags` lists all
that fired, in the same order, with the note last.

| Order | Reason | Plain meaning |
|---|---|---|
| 1 | `no_value` | The reading was saved empty. |
| 2 | `flag_bad` | The instrument marked it BAD. |
| 3 | `flag_uncertain` | The instrument marked it UNCERTAIN. Treated like BAD, as ADR-0011 already did. |
| 4 | `outside_physical_limits` | The value is impossible for this plant. |
| 5 | `unknown_state` | A state signal said something not in its list of allowed values. |
| 6 | `conflicting_duplicate` | Two readings claimed this instant with different content. |
| 7 | `spike` | A single reading far from its neighbours. |
| 8 | `flatline` | Part of a stretch where the signal stopped moving. |
| note | `outside_typical_range` | Possible, but outside the dictionary's usual range. Kept. |

Details: an instant that has a row in `readings_conflicts` is excluded as `conflicting_duplicate`
(the kept value was chosen by a rule, not by evidence; ADR-0013). Exact copies are collapsed at
ingest and are unaffected. A reading outside the physical limits never also carries `spike` or
`flatline`: those two rules look only at readings that have a value inside the limits.

## 3. The rules, and why some signals are exempt

### Physical limits

A value outside the limits is excluded as `outside_physical_limits`. The limits are wide on
purpose: they say "this cannot be real for this plant", not "this is unusual". They always
contain the documented typical range (a unit test checks it). Real hits: EXP_001 voltage 412.0,
EXP_003 solvent pH 27.4, EXP_005 electrolyte temperature -50.0 and EXP_004 pressure -3.1 (4 in all).

Details: we do not have instrument spans, so these limits stand in for them (A-05 in
`docs/ASSUMPTIONS.md`). A pH is bounded 0 to 14 by chemistry, not by a sensor. `current` allows
down to -2 A because the real data holds small negative readings (down to -0.69 A) that are
measurement offset around zero, not faults.

### Typical range is a note, not an exclusion

A reading outside the dictionary's typical range but inside the physical limits is accepted and
carries the note `outside_typical_range`. The reason is the data: EXP_002 was run with a current
up to 350.55 A against a typical 260 A, and EXP_004's air flow runs below 1,000 m3/h for an hour.
Excluding them would remove the experiment's own design. In total 10,242 readings carry the note.

### Spike

One reading that sits far from its neighbours is a spike. For each reading we take up to 5
usable readings on each side, find their median and spread, and call the reading a spike when it
is more than 5 robust standard deviations away **and** more than 10 times the signal's normal
step away. A step that holds, or a ramp, is not a spike, because the median moves with it.

Details: the rule is a Hampel filter. `|x - m| > max(5 x 1.4826 x MAD, 10 x Step)`, where `m` and
`MAD` are the median and median absolute deviation of the window (the reading plus up to 5
neighbours each side, taken from readings with a value inside the limits). It is not applied to
the setpoint or the state signals. A burst of more than 5 bad readings looks like a step to this
rule and is not caught as a spike (a limit, section 8). Real hits: EXP_003 fan speed 0.0,
EXP_004 pump speed 0.0, EXP_002 current 0.0 at 2026-05-11T09:33:20Z, and EXP_006 fan speed 839.2
at 11:10:17 (3 excluded as `spike`; the fourth is excluded first as `conflicting_duplicate`).

### Flatline (stuck sensor)

A stuck sensor stops moving. We call a reading flatline when it belongs to a stretch where
almost every step is far smaller than the signal's normal step, and at least 5 such small steps
come in an unbroken row. This catches an exactly repeated value and also a sensor whose noise
collapsed. A run of 3 equal readings is not a flatline.

Details: step `j` (reading `j` to `j+1`) is flat when `|change| < 0.2 x Step`. A flat step is
flagged when more than half of the steps within the half-window on each side are flat, and it sits
in an unbroken run of at least 5 flat steps. A reading is flatline when it is an end of a flagged
step, so an exact run of n readings flags exactly those n. Rejected: raising the 0.2 fraction
(would also weaken noise-collapse detection). Real hits, all with the flatline flag: EXP_003
solvent temperature 240 readings of 30.22, EXP_006 outlet CO2 1,350 readings of 38.0, EXP_004 air
flow 3,600 readings below 1,000 m3/h, EXP_001 conductivity 60 readings of 50.0 and EXP_003 acid pH
40 readings of 4.8. The last two are also BAD at acquisition, so their reason is `flag_bad`.

### Solar power: exact repeats only

For `available_solar_power` a step is flat only when the value repeats exactly, and never when
both values are 0.0 (night). The reason is that solar power rises from 0 kW at dawn in steps far
smaller than its daytime step, so a fraction of the declared step would call a normal dawn ramp
"stuck". A frozen sensor repeats one value, so exact repeat is the right test. Limit: a solar
sensor frozen with a little added noise would not be caught.

### Current setpoint: exempt from spike and flatline

A setpoint is a command, held on purpose for minutes and changed in jumps. A held value is not a
stuck sensor and a jump is not a spike. It still gets the limit check, the flag check and the
gap check.

### State signals: exempt from spike, flatline and gaps

`valve_state` and `process_state` are labels written when they change. They have no sampling rate,
so a long silence is not a gap (the on-change staleness mistake, C-01 in `docs/MISTAKES.md`).
A state is true until the next event, with no expiry; the last one lasts to the experiment end.
Each event becomes one interval row. A label outside the allowed list is `unknown_state`.
Numbers cannot be "spiky" and a label cannot "flatline", so those rules do not apply.

### Gaps

A spacing over 2 x nominal between two consecutive readings of a polled signal becomes one row in
`quality_intervals` (`kind = gap`, from the earlier reading to the later). A gap is never filled and
no reading is invented. On the real data: 29 gaps, 18,519 s in all (EXP_001: 4 gaps, 78 s in all, on
current, power and voltage; EXP_002: one gap of 481 to 485 s on all 10 hydrolyzer signals; EXP_006:
one gap of 1,921 to 1,925 s on 7 absorber signals).

## 4. The nine kinds of defect in the brief

| Defect | What we do | Why | Real data |
|---|---|---|---|
| Missing values | A point saved without a value gets `no_value` and is excluded. | It is "a row with no value", different from "no row". | 0 points without a value |
| Gaps | Recorded as intervals in `quality_intervals`. Never filled. | Filling would invent data. | 29 gaps, 18,519 s |
| Duplicates | Ingest keeps one reading per instant (exact copies collapse; a conflict keeps the better flag, then the smaller value) and stores the loser in `readings_conflicts`. Cleaning excludes every conflicted instant. | The kept value was chosen by a rule, not by evidence. | 15 exact copies, 10 conflicts excluded |
| Out-of-order samples | No rule needed. InfluxDB stores by time, and cleaning reads in time order. Ingest counted them. | Arrival order describes transport, not the value. | 30 rows out of order at ingest |
| Flagged-bad data | BAD and UNCERTAIN are both excluded. | A flag is the instrument's own statement; UNCERTAIN is treated as BAD (ADR-0011). | 100 BAD, 230 UNCERTAIN |
| Outliers | Impossible values are excluded by the physical limits; isolated far values by the spike rule. Unusual but possible values stay, with a note. | Excluding by "typical" would remove a real experiment's design. | 4 outside limits, 4 spikes, 10,242 notes |
| Sensor noise | Kept. Never smoothed. | Smoothing changes raw values, which the brief forbids doing silently. Noise is also the signal comparisons will need. Noise that disappears is caught as flatline. | Not a count |
| Stuck sensors | The flatline rule (exact repeat for solar). | See section 3. | 5 runs, 5,290 readings flagged |
| Differing sample rates | Nothing is resampled. Each signal keeps its own nominal interval for gaps and flatline. | A common grid belongs to the metric that needs it (M4). | 4 rates plus on-change |

Details: out-of-order rows are counted in `reports/ingest_summary.json` (30 in all). Spikes: 4
readings carry the flag, 3 have it as their reason. Flatline: 5,290 readings carry the flag, 5,190
have it as their reason (the other 100 are BAD, which has higher priority). Real counts are from
`reports/cleaning_summary.json`.

## 5. Why a pH, a plant state and an integrated energy value are not treated alike

| Kind | Example | How it is handled | Why |
|---|---|---|---|
| A bounded measurement | `solvent_pH` | Limits 0 to 14, spike and flatline apply, gaps are recorded. | Chemistry bounds it. It is polled steadily, and a stuck pH probe is a real failure, so it needs the stuck-sensor rule. |
| A state | `process_state` | Not numeric. Carried forward from one event to the next with no expiry. No spike, flatline or gap rules. Only the allowed list is checked. | It is written on change. Silence means "no change", not "no data". Averaging or expiring it would be meaningless. |
| An integrated energy value | Energy = integral of power over time | There is no energy signal in the data dictionary or the data. It is derived in M4 from `power`. The integration uses only accepted samples. | An integral adds every error to a running total and never forgets it. A bad reading must be left out before integrating, and missing stretches must be labelled, not hidden. |

Details: the data dictionary lists no energy signal; `task/TASK.md` defines energy as an integral
of power and deliverable E computes it. So M3 does not store or judge an energy value. It decides
which `power` readings are accepted, and records gaps and excluded stretches so M4 can say how
complete each integral is. How M4 integrates over an excluded stretch is M4's decision.

## 6. Alignment rule M4 will use

This is the rule M4 will use to put signals of different rates on one time axis. M3 only
supplies the accepted readings and the gap intervals; it does not resample.

| Signal kind | Value at time t |
|---|---|
| Polled signal | The latest accepted reading at or before t, if it is not older than 2 x that signal's nominal interval. Otherwise missing. |
| State signal | The state of the latest event at or before t, carried forward with no expiry, until the experiment end. |

Details: 2 x nominal is the same limit that defines a gap, so "missing" in an aligned series means
"inside a recorded gap or an excluded stretch". M4 may refine this, and any change to it is M4's
decision to record.

## 7. Where the numbers come from

- **Step:** the median over the six experiments of the profile's median absolute difference (so one
  degraded experiment cannot move it).
- **Limits:** declared by hand and wide. No instrument spans exist (A-05).
- **Calibration:** the rules were checked on the real data in plain Python against an independent
  recompute, with 0 mismatches. The thresholds are a first calibration on six 2-hour runs
  (ASSUMPTIONS.md).
- **Version:** `POLICY_VERSION = m3-v1` is a tag on every processed row. A unit test pins a SHA-256
  fingerprint of the whole table to that version string, so changing a number without bumping the
  version fails the test.

## 8. Known limits

- A burst of more than 5 bad readings in a row looks like a step to the spike rule and is not
  caught as a spike. Limits or flatline may still catch it.
- A solar sensor frozen with a little added noise is not caught by the exact-repeat rule.
- The thresholds were set on six 2-hour runs. A longer or noisier data set may need them re-set,
  which is a new policy version.
- EXP_004 air flow from 09:00 to 10:00 is excluded as a stuck sensor: fan speed, pressure drop and
  outlet CO2 did not change while the reading dropped about 60 times. That is a cleaning call, and
  the comparison milestone may revisit it.
- A short exact run (about 12 readings) inside a 1 Hz noisy signal is not flagged, because the
  majority window is 61 steps wide.
