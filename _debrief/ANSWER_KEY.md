# Answer Key

Ground truth for every defect injected into `data/raw/dac_raw_timeseries.csv` and
`data/raw/experiments.json`. Generated from `_debrief/defect_manifest.json`, which the
generator writes automatically — timestamps here are exact, not approximate.

**Do not open this before the 60-minute working session is over.**

---

## The headline result: naive vs. corrected capture efficiency

The single most important number in this dataset. `capture efficiency = 1 - avg(co2_out_ppm) / avg(co2_in_ppm)`,
computed two ways per experiment:

| Experiment | Naive (raw average) | Corrected (excludes the flagged stuck window) | Data completeness | BAD/UNCERTAIN flags |
|---|---|---|---|---|
| EXP_001 | 74.4% | 74.4% | 99.8% | 60 BAD |
| EXP_002 | 74.4% | 74.4% | 96.3% | 0 |
| EXP_003 | 64.8% | 64.8% | 100.0% | 40 BAD |
| EXP_004 | 77.6% | 77.6% | 100.0% | 200 UNCERTAIN |
| EXP_005 | 75.3% | 75.3% | 100.0% | 30 UNCERTAIN |
| **EXP_006** | **83.5%** ← naive winner | **75.8%** ← roughly average | 92.6% | **0** |

If you rank experiments by a naive per-experiment average of `co2_in`/`co2_out`, **EXP_006
wins outright** — and by a comfortable margin (83.5% vs. the next-best 77.6%). That ranking
is wrong. EXP_006's `co2_out_ppm` sensor is frozen at exactly 38.0 ppm for 45 minutes
(2026-04-20T11:00:00Z to 2026-04-20T11:45:00Z), and **every one of those samples is still
flagged `GOOD`** — there is no quality flag to filter on. A pipeline that only trusts
`quality != BAD` will happily keep 100% of EXP_006's rows and never notice.

The only way to catch this is to notice that a real sensor doesn't hold an exact constant
value for 45 minutes while everything else in the process keeps moving (zero rolling
variance), or to notice that this experiment's data completeness (92.6%, driven by a
separate 32-minute absorber outage from 10:18–10:50) is worse than everything else in the
set, which should raise the bar for trusting anything else surprising about it.

Once that window is excluded, EXP_006's corrected efficiency (75.8%) lands almost exactly on
its true underlying value (75.7%, from the clean pre-defect generation) — i.e. it's an
**unremarkable, roughly average experiment**, not the best one.

**The actual best performer is EXP_004** (cold ambient, high humidity) at ~77.5-77.6% —
consistent with hydroxide-based CO2 absorption generally favoring lower solvent
temperature. This is a real, defensible finding, and it's less dramatic than EXP_006's fake
number, which is exactly the point: the trap isn't that EXP_006 looks *impossibly* good
(that would be easy to distrust), it's that it looks *plausibly, moderately* better —
enough to win a naive ranking without raising obvious alarm.

---

## EXP_001 — baseline

| Type | Window (UTC) | What | Why it's there |
|---|---|---|---|
| short_gap | 08:10:00–08:10:15 (15s) | `current`, `voltage`, `power` dropout | Short enough to interpolate defensibly. |
| short_gap | 08:30:00–08:30:25 (25s) | same 3 signals | Same. |
| short_gap | 09:10:00–09:10:06 (6s) | same 3 signals | Same. |
| short_gap | 09:31:40–09:32:08 (28s) | same 3 signals | Same. |
| outlier | 08:41:40 (single sample) | `voltage` = 412 V | Single-sample spike; rolling median/z-score catches it. `quality` stays GOOD. |
| bad_quality | 09:00:00–09:05:00 (5 min, 60 samples) | `conductivity` pinned to 50.0, flagged BAD | Flagged at the source — keep for audit, exclude from calculations. |
| physical_inconsistency | 09:23:20–09:25:20 (2 min, 120 samples) | `power` inflated ~40% above `voltage x current` | `quality` stays GOOD; neither `voltage` nor `current` alone looks wrong — only the cross-check catches it. |

## EXP_002 — high current density

| Type | Window (UTC) | What | Why it's there |
|---|---|---|---|
| long_gap | 10:06:00–10:14:00 (8 min, ~3264 samples) | full `hydrolyzer` source outage | Long enough that interpolation is not defensible; drives completeness down to 96.3%. |
| physical_inconsistency | 09:33:20 (single sample) | `current` forced to 0 A while `power` stays ~29 kW | Neither signal alone is statistically odd; only the combination is impossible. |
| duplicate_timestamp | throughout | 15 rows duplicated exactly | Same timestamp/signal/value twice — safe to drop with simple exact-duplicate detection. |

Intended finding: higher current density captures more CO2 in absolute terms, but specific
energy consumption is worse (voltage rises faster than linearly with current), so this is
*not* the most energy-efficient experiment even though it processes the most current.

## EXP_003 — high air flow

| Type | Window (UTC) | What | Why it's there |
|---|---|---|---|
| stuck_sensor | 08:30:00–08:50:00 (20 min, 240 samples) | `solvent_temperature` frozen at 30.22°C | `quality` stays GOOD; zero variance is the tell. |
| outlier | 07:55:00 (single sample) | `solvent_pH` = 27.4 | Outside the physically possible 0–14 range; a hard-limits check alone catches it. |
| physical_inconsistency | 08:53:20 (single sample) | `fan_speed` forced to 0 while `air_flow` stays ~2400 m3/h | `air_flow` itself looks completely normal. |
| bad_quality | 08:06:40–08:10:00 (200 samples) | `acid_pH` pinned to 4.800, flagged BAD | Flagged at the source. |

Intended finding: doubling air flow vs. baseline gives a *higher absolute* CO2 capture rate
but *lower* capture efficiency (64.8%, the lowest of all six) — shorter residence time per
air molecule. Rate and efficiency trade off against each other; "best" depends on which one
the question is actually asking about.

## EXP_004 — cold ambient, high humidity

| Type | Window (UTC) | What | Why it's there |
|---|---|---|---|
| outlier | 08:16:40 (single sample) | `pressure` = -3.1 bar | Negative gauge pressure is impossible here; hard-limits check. |
| unit_change | 09:00:00 onward (3600 samples) | `air_flow` silently switches from m3/h to Nm3/min | `quality` stays GOOD throughout. `pressure_drop` is generated from the true, unchanged air flow and stays normal, so cross-checking it against the reported `air_flow` after 09:00 shows they've become inconsistent — that mismatch is the tell, not the absolute value of `air_flow` alone. |
| physical_inconsistency | 09:15:00 (single sample) | `pump_speed` forced to 0 while `solvent_flow` stays normal | `solvent_flow` alone looks unremarkable. |
| uncertain_quality | 08:33:20–08:36:40 (200 samples) | `pressure` flagged UNCERTAIN, value unchanged | UNCERTAIN != wrong — a per-calculation decision, not a blanket drop. |

Intended finding: this is the **true best-efficiency experiment** (~77.5%), consistent with
absorption chemistry that favors lower temperature. Also has the slowest hydrolyzer warm-up
and highest initial voltage of any experiment, due to the cold electrolyte.

## EXP_005 — solar-following, fluctuating setpoint

| Type | Window (UTC) | What | Why it's there |
|---|---|---|---|
| outlier | 07:06:40 (single sample) | `electrolyte_temperature` = -50°C | Physically implausible for an operating stack. |
| physical_inconsistency | 06:41:40–06:42:25 (45s) | spurious `valve_state = CLOSED` while `solvent_flow` keeps flowing | `solvent_flow` alone looks normal; only cross-checking against `valve_state` reveals it. |
| out_of_order | 06:46:40–06:49:40 (3 min, 1440 rows) | this whole window is moved to the end of the file | Simulates a delayed batch upload; ingestion must not assume the file is time-sorted. |
| uncertain_quality | 06:00:00–06:30:00 (30 samples) | `ambient_pressure` flagged UNCERTAIN | Low-stakes signal — reasonable to just note this rather than build special handling. |

Intended finding: current visibly lags its setpoint (first-order response with a slew
limit), and `acid_pH`/`base_pH` shift and lag behind load changes. Good experiment for a
step-response / time-constant discussion. `process_state` should show frequent
`LOAD_CHANGE` segments as the setpoint tracks available solar power.

## EXP_006 — the trap

See the KPI table above. In addition:

| Type | Window (UTC) | What | Why it's there |
|---|---|---|---|
| long_gap | 10:18:00–10:50:00 (32 min, ~6528 samples) | full `absorber` source outage | Drives completeness to 92.6%, the worst of all six experiments. |
| stuck_sensor | 11:00:00–11:45:00 (45 min, 1350 samples) | `co2_out_ppm` frozen at 38.0 ppm, quality GOOD | The trap. See KPI table. |
| duplicate_timestamp | throughout | 10 timestamps with two conflicting values | Not exact duplicates — requires an explicit tie-break policy. |
| out_of_order | throughout | ~20 rows locally shuffled | Minor jitter, not a big delayed batch — still breaks anything assuming strict ordering. |

## Missing metadata (`data/raw/experiments.json`)

| Experiment | Missing field |
|---|---|
| EXP_003 | `notes` |
| EXP_005 | `sorbent_batch` |
| EXP_006 | `operator` |

Worth noticing on its own: the experiment with the worst data quality (EXP_006) is also the
one missing operator attribution — realistic, and a legitimate second-order flag ("sloppy
logging correlates with sloppy operation") if a candidate makes that connection, though it
shouldn't be over-read as proof of anything by itself.

## Systematic, not localized: the timezone offset

Every row with `source = ambient` has a timestamp ending in `+02:00` instead of the `Z`
(UTC) suffix every other source uses — across **all six experiments**, not just one. It's
the same instant, correctly expressed with an explicit offset, so a timezone-aware parser
handles it fine. A naive string-comparison join between `ambient` and any other source will
silently misalign by 2 hours. This is the one defect explicitly hinted at in
`task/DATA_DICTIONARY.md` ("different sources... don't assume they all use the same timezone
convention") — worth noting whether the candidate caught the hint or found it empirically.

## Noise (not a discrete event — present throughout)

Every numeric signal carries independent, per-signal Gaussian measurement noise (e.g. pH
signals ±0.05, conductivity ±2 mS/cm, current ±0.3 A). This isn't logged in the manifest
since it's a baseline characteristic of the whole dataset, not an injected anomaly — but it's
exactly what makes the stuck-sensor defects detectable (real sensors have irreducible noise;
a sensor reading the *identical* value for many consecutive samples is the anomaly).
`voltage`, `current`, and `power` share the same noise draw within each 1-second sample
specifically so that `power == voltage x current` holds to rounding precision on clean rows
— which is what makes the deliberate ~40% EXP_001 mismatch and the EXP_002
current-forced-to-zero case detectable as inconsistencies rather than just more noise.
