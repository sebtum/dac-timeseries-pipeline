# ADR-0015 — Cleaning and quality pipeline: one verdict per reading, kept beside the raw value

Status: Accepted
Milestone: M3   Deliverable: C, D   Date: 2026-11-23

## Context

In plain words: the raw data holds readings we should not trust (a voltage of 412 V, a pH of 27.4,
a sensor that froze for an hour). The brief says not to delete or silently fix them. So every
reading gets a verdict (accepted or excluded) and a reason, written beside its raw value. Anything
that needs trustworthy input, like the rollup, then reads only the accepted readings.

Details: M2 stored 519,980 points; M2.5 measured them (`reports/post_ingest_profile.json`) without
judging any. M3 is where readings are judged. Four questions were open: where processed data lives
(U-09), whether quality stays a dense field (U-10), whether cleaning reads InfluxDB or the CSV
(U-12), and where the rollup runs (U-04). The nine defect kinds of the brief are in
[`docs/cleaning_policy.md`](../cleaning_policy.md) with one rule or one reason each; this ADR
records why the pipeline is built the way it is. The 27 decisions below were made on 2026-11-23
while planning M3 (1 to 23) and at the re-plan after the calibration stop (24 to 27).

Two facts about InfluxDB 3 Core 3.11.2 were measured on the running server before the code relied
on them (MISTAKES.md E-06, never trust documentation for a server's live behaviour):

| # | Behaviour | What it forced |
|---|---|---|
| 1 | A later write of the same key (same table, tags and time) **without** a field **keeps the old field value**. Probe: a point written with `value=2.5`, then rewritten without `value`, still reads 2.5. | Re-runs only overwrite correctly when a row's set of fields is the same every time. The read-back also counts the rows that carry a value and compares that with the accepted count, so a leftover value cannot hide. Rollup limit below. |
| 2 | An **empty string field is stored and read back as `""`** (length 0). | An accepted row uses `""` for `reason` and `flags`. The fallback in the plan (the literal `none`) was not needed. |

## Decision

Note on the `Rejected` column: for decisions 5, 8, 9, 11, 13, 14, 16, 17 and 19 to 22 the plan
recorded no rejected option. The cell was written at the write-up as the obvious alternative, not
as a deliberation that took place at the time. The other cells come from the plan.

### Where the verdict lives, and what it looks like (decisions 2 to 5, 7, 8, 10, 17)

| # | Decision | Rejected |
|---|---|---|
| 2 | Processed data goes in three new tables **inside the raw database** (`readings_processed`, `state_intervals`, `quality_intervals`). The raw tables are never written. Processed data can only be rebuilt while raw exists, so it must expire with raw; sharing the database makes that structural. It also keeps Core's fifth database slot free (A-04). Closes U-09. Known wart: the name `dac_raw` now also holds derived tables. | A fourth database `dac_processed`: its retention could drift from raw's, and it uses the last free slot. |
| 3 | **Dense**: one processed row per raw reading, raw value and acquisition flag copied alongside. Equal counts per series is the proof that nothing was dropped, and one query shows raw, processed, flag and reason together. Closes U-10. | A sparse exceptions table where "no row" means good: it cannot prove nothing was dropped. |
| 4 | **Processed value = raw value when accepted, absent when excluded.** No clamping, filling, smoothing or signed-zero normalisation. | Clamping small negative currents (down to -0.69 A) to 0: that is a silent fix. They are accepted with a note. |
| 5 | Cleaning **reads InfluxDB, not the CSV**: the surface the profile measured and the one a real system would have. Closes U-12. | Re-read the CSV: would work from a different surface than the analysis that justified the rules. |
| 7 | `policy_version` is a **tag** on all three tables. A new rule set writes new series beside the old ones instead of partly overwriting them. A unit test pins a SHA-256 fingerprint of the declared table to the version string. | Version as a field: the old series would be overwritten in place (see the measured behaviour above). |
| 8 | **Reason codes in priority order:** `no_value`, `flag_bad`, `flag_uncertain`, `outside_physical_limits`, `unknown_state`, `conflicting_duplicate`, `spike`, `flatline`. The first that fires is `reason`; every code that fires goes in `flags`, with the note last. UNCERTAIN is excluded because ADR-0011 already treats it as BAD. | A numeric score: not machine-readable as a reason. |
| 10 | **A typical-range violation is a note, never an exclusion.** EXP_002's 350 A is the experiment's design. | Exclude everything outside the data dictionary's range: removes real experiments. |
| 17 | Every instant with a row in `readings_conflicts` is excluded as `conflicting_duplicate`. The kept value was chosen by a rule, not by evidence (ADR-0013). Exact copies are unaffected. | Trust the kept value. |

### The rules (decisions 9, 11 to 14, 16, 24 to 26)

| # | Decision | Rejected |
|---|---|---|
| 9 | **Physical limits** are declared per signal and always contain the documented typical range (unit-tested). Bounds are inclusive. They stand in for instrument spans we do not have (A-05). | Limits learned from the data: the data is what we are judging. |
| 11 | **Spike = Hampel filter.** Take up to 5 usable readings on each side in time order, median `m` and MAD of those plus the reading. Spike when `\|x - m\| > max(5 x 1.4826 x MAD, 10 x step)`. Only readings with a value inside the limits are tested. Not applied to the setpoint or state signals. A median keeps a step, so a step or ramp is not a spike. | Fixed threshold from the mean and standard deviation: one outlier inflates both and hides itself. |
| 12 | **Flatline = variability collapse, defined on steps.** A step is flat when `\|change\| < 0.2 x step`. It is flagged when more than half of the steps within `h = max(5, ceil(30 / nominal))` on each side are flat. A reading is flatline when it is an end of a flagged step, so an exact run of n flags exactly n. Not applied to the setpoint or state signals. | A median-of-window statistic (ambiguous by one reading at each end of a run); a plain exact-run length (misses noise collapse, EXP_004 air flow). |
| 13 | **Step per signal = median over the six experiments** of the profile's `differences.median_abs`, declared in the policy table and checked against the profile at 9 digits by a unit test. | Mean, or the pooled value: one degraded experiment would move it. |
| 14 | **Gaps:** a spacing over 2 x nominal between consecutive points of a polled series is one `quality_intervals` row (`kind = gap`). Never filled. On-change signals get none. A run of consecutive flatline readings is one row `kind = flatline`. | Fill or interpolate: invents data. |
| 16 | **State signals:** each event becomes one `state_intervals` row lasting until the next event of the series, the last one until the experiment end, with no expiry. A value outside the declared set is `unknown_state`. Excluded events keep their interval. | A staleness horizon on states: the on-change mistake (C-01). |
| 24 | **Amendment to 12.** A flagged flat step must also sit in an **unbroken run of at least 5 flat steps** (`FLAT_MIN_RUN = 5`). | Raising the 0.2 fraction: would also weaken noise-collapse detection. |
| 25 | **Amendment to 12.** For `available_solar_power` a step is flat only when its change is **exactly 0** and the two values are not both 0.0. Replaces the night-zero special case. | Exempt solar from flatline (misses a frozen sensor); accept the dawn hit (excludes good data). |
| 26 | **EXP_006 fan speed 839.2 at 11:10:17 is a real spike** and joins the expected list. Its reason stays `conflicting_duplicate` (priority); `spike` is in its flags. | Hide it: the rules found a real feature. |

Details: why 24 and 25 exist is in "Calibration" below. Measured at the re-plan: a minimum run of 5
removes the pH and ambient-pressure hits and leaves the five expected flatline features with
identical counts (60, 240, 40, 3,600 and 1,350); a minimum of 3 leaves 3 readings of the pressure
hit and 8 leaves 11 of the solar hit. No run length fixes the solar dawn ramp, because a smooth ramp
is flat by the step definition; that is why decision 25 changes the yardstick, not the length. The
solar step size grows with its level (EXP_005 starts at 0 kW, steps near 1 kW per minute at 08:00,
20 to 30 by 09:30), while the declared 12.255 is a median over runs that mostly start at 100 to
400 kW. Decision 26 keeps `POLICY_VERSION` at `m3-v1`, because nothing had been written under
it; the fingerprint was re-pinned to the amended table.

### Rollup (decision 18, with an addendum to ADR-0011)

| # | Decision | Rejected |
|---|---|---|
| 18 | The rollup is a **separate command run after cleaning, an external Python job** (`python -m scripts.rollup`). It reads `readings_processed` for one policy version, one experiment window at a time. The "all" columns are over points with a raw value; the included columns are over `verdict = accepted`. A point with no value is counted in a new column `count_no_value` and never crashes the run. Closes U-04. | A Processing Engine plugin: needs a plugin-enabled server to test, and scheduling belongs to deliverable H. |

Details: the addendum to ADR-0011 is not a reversal. The column set stays; one column is added
(`count_no_value`); the inclusion predicate that ADR-0011 left injected is now the cleaning
verdict; and the open question where the rollup runs is answered (external job). The M1 draft
predicate (`quality == 'GOOD'`) is gone from the driver. Aggregation is in Python on a plain SELECT
pull, not in SQL, because Core sums vary in the last bits between runs (ADR-0014).

### How it is run and proven (decisions 6, 15, 19 to 22, 27)

| # | Decision | Rejected |
|---|---|---|
| 6 | **One series of one experiment at a time.** Memory is bounded by one series window (at most 7,200 points). Narrows U-06. | One pull for everything. Time-chunked processing for continuous data is a next step. |
| 15 | The two Core behaviours above are **measured first**, and both results are recorded here. | Trust the documentation (E-06). |
| 19 | **Expected real-data results are pinned before the rules run.** An extra spike or flatline found at calibration comes back to planning as a narrow question; thresholds are not tuned silently. | Tune until the numbers look right. |
| 20 | **Calibrate before scaling:** EXP_001, then EXP_004, then all six, each against a plain-Python recompute from a SELECT pull, before anything is written. | Run at full scale and look. |
| 21 | Exit codes for clean: 0 written and balanced; 2 refused, nothing written (database missing and never created, raw tables missing, experiments file unreadable); 3 a query or write failed; 4 written but the read-back counts do not balance. Rollup: 0, 2, 3, same meaning. 70 is an internal error. | One non-zero code. |
| 22 | Branch `m3-cleaning`, cut from `m2.5-profiling` after the M2.5 commit. Commit and push at the end; merge waits for approval. | Merge as we go. |
| 27 | **M3 runs as five tasks, each by its own agent**, in waves: rules and rollup in parallel, then fixture, Influx layer and CLI, then real data, then the write-up. Replaces the plan's first choice of one piece. | One session: contexts grow long. |

## Calibration: four unexpected hits and how the re-plan resolved them

The plan pinned every expected feature of the real data before the rules ran (decision 19). The
first calibration, read-only on `dac_raw`, matched every pinned count exactly (412.0, pH 27.4 and
-50.0 outside limits; the fan, pump and current spikes; 240, 1,350, 3,600, 60 and 40 flatline
readings; 200 and 30 UNCERTAIN; 10 conflict instants; gaps equal to the profile's). It also found
four things that were not on the list. Execute stopped, changed no threshold and asked.

| # | Where | What fired | What it was | How it was resolved |
|---|---|---|---|---|
| 1 | EXP_001 solvent pH, 09:28:10 and 09:28:15 | flatline, 2 readings | Chance: scattered small steps on a smooth signal (7 of 13 flat). | Decision 24 (run of at least 5). |
| 2 | EXP_005 ambient pressure, 07:40 to 07:44 | flatline, 5 readings | Same cause: smooth signal, steps of 0.01 and 0.00 against a threshold of 0.012. | Decision 24. |
| 3 | EXP_005 solar power, 06:00 to 06:24 | flatline, 25 readings | The dawn ramp (steps 0.8 to 5 kW) is slower than 0.2 x 12.255. | Decision 25 (exact repeat only). |
| 4 | EXP_006 fan speed, 11:10:17 | `spike` in flags | A real spike: 839.2 among readings near 900, the kept value of a conflict pair. | Decision 26 (accepted, added to the list). |

Details: with the amended rules, a second calibration on EXP_001, EXP_004 and all six found 0
mismatches between `pipeline.cleaning` and an independent plain-Python recompute (verdicts, gaps
and flatline intervals). Spikes appear in flags only in the four expected places and flatline only
in the five expected series. Raw 519,980 = accepted 514,443 + excluded 5,537; excluded by reason:
`flag_bad` 100, `flag_uncertain` 230, `outside_physical_limits` 4, `conflicting_duplicate` 10,
`spike` 3, `flatline` 5,190. The run was reproduced on a fresh private stack: the summary is
identical except `timing`.

## Why

The brief's test of this milestone is "a questionable reading should still be there; it should
just be excludable". Dense rows with raw, processed, flag, verdict and reason side by side are the
simplest structure for which that is a `WHERE` clause and the arithmetic (raw count = accepted +
excluded, per series) is a proof, not a claim. The rules are chosen to be explainable per signal
and independent of the data they judge: the limits are declared, the step is the median of a
measured profile, and nothing is learned at run time. The two amendments exist because the
pre-pinned list was a real test, and it failed in a way that taught something: a flatline rule
defined on step size needs a unit that fits the signal, and a smooth signal gives chance flat
steps.

## Consequences

- Any query can select accepted readings with `verdict = 'accepted' AND policy_version = 'm3-v1'`
  and can see the reason for every other reading. The rollup already does.
- Changing a number changes the fingerprint test; the version must be bumped; new rows sit beside
  the old ones. Old policy-version rows are not deleted automatically.
- Storage: 519,906 rows in `readings_processed`, 74 in `state_intervals`, 34 in
  `quality_intervals`, all in `dac_raw`; they expire with raw.
- A cleaning run takes about 41 s (263 queries). The real-data rollup takes about 12 minutes for
  16,256 buckets.
- The EXP_004 air-flow hour (3,600 readings) is excluded, so metrics over EXP_004 lose an hour of
  air flow. That is a cleaning call and affects the comparison milestone.

## Limits

- **Bursts.** A burst of more than 5 bad readings looks like a step to the Hampel rule and is not
  caught as a spike. Limits or flatline may still catch it.
- **Solar frozen with noise.** A solar sensor frozen with a little added noise is not caught by the
  exact-repeat rule.
- **Thresholds are a first calibration** on six 2-hour runs (5 robust standard deviations, floor
  of 10 steps, flat fraction 0.2, windows, run of 5). A longer or noisier data set may need them
  re-set, which is a policy-version change.
- **EXP_004 air flow is treated as a sensor fault.** For 09:00 to 10:00 fan speed, pressure drop
  and outlet CO2 are unchanged while the air-flow reading drops about 60 times and its noise
  collapses to about 0.4 against a normal step of 7.55. That is a cleaning call, not a finding;
  M5 may revisit it.
- **Rollup stale field.** Because a later write without a field keeps the old one, if the rows of
  a bucket under the same policy version changed so that its included count fell to 0, a re-run
  would keep the old `mean`, `std` and `median`. The design avoids it by construction: cleaning is
  deterministic and every rule change bumps the version, so rows of one version never change.
  Consumers read `mean`, `std` and `median` only where `count_included > 0`. A rebuild after a
  policy change into a fresh table is a next step.
- **Rollup speed.** It takes about 12 minutes on the real data (about 2 minutes per experiment) and
  prints only when an experiment finishes. The streaming read is the likely cost; it was not
  profiled.
- **Database slots.** Core allows 5 databases and 4 already exist when the end-to-end test runs.
  So the rollup test writes into the same throwaway database as the cleaning, not a second one.
- **One series window at a time.** Continuous data needs time-chunked processing with an overlap of
  one flatline window on each side; that is a next step (rest of U-06).

## Assumptions relied on

A-04 (five databases), A-05 (physical limits stand in for instrument spans), the M3 threshold
calibration assumption (see `../ASSUMPTIONS.md`). Closes U-04, U-09, U-10, U-12; narrows U-06.

## Related

ADR-0006 (tables and tags), ADR-0007 and ADR-0013 (conflicts), ADR-0011 (rollup, addendum below),
ADR-0014 (profile, engine quirks). MISTAKES.md C-01 (on-change signals), C-02, C-03, E-06. Policy
table and reasons: [`docs/cleaning_policy.md`](../cleaning_policy.md). Schema:
[`docs/schema.md`](../schema.md).

## Defense

"Every reading is kept and judged, not edited. A reading gets a verdict and the first reason that
fired, and the raw value sits in the same row, so one query shows what came in, what we use and
why. I can prove nothing was dropped by counting: for each of the 150 series, raw equals accepted
plus excluded, and the raw tables are counted before and after. The rules use numbers declared in
one table, measured from the profile, so I can explain each line: limits are physical, the step is
the median of a measurement, and a spike or a stuck sensor is defined against that step. I did not
tune to taste: I wrote down what the data should show before running anything, the first run
matched all of it and found four things I had not listed, and I stopped, explained each, and
changed the rule for a stated reason. The honest limits are that the thresholds come from six
two-hour runs, that I treat one air-flow hour as a sensor fault, and that a long burst of bad
readings would pass as a step."
