# Systems & Data Infrastructure — Practice Exercise

## Background

Phlair operates Direct Air Capture (DAC) plants. Simplified, the process has three stages:

1. **Absorption** — air is contacted with a basic sorbent that picks up CO2.
2. **Desorption** — the CO2-loaded sorbent is treated with acid, releasing the CO2.
3. **Regeneration** — an electrochemical hydrolyzer regenerates the acid and base
   using electrical power. The hydrolyzer can vary its output depending on available
   renewable power.

You are given raw sensor data from six pilot-scale experiments run under different
operating conditions. Your job is to turn that raw data into something a scientist could
actually use to compare experiments and trust the results.

## What you have

- `data/raw/dac_raw_timeseries.csv` — long-format raw sensor readings across all six
  experiments: `timestamp, experiment_id, source, signal, value, quality`.
- `data/raw/experiments.json` — per-experiment metadata.
- `task/DATA_DICTIONARY.md` — what each signal means, its unit, and its typical range.

Read the data dictionary before writing any code — it documents things about the data
(sampling rates, timestamp conventions, logger groupings) that matter for how you ingest
and process it.

## About the data

This is raw industrial time-series data, not a cleaned dataset. Treat it the way you would
treat a historian export from a real PLC/OPC-UA system: it was not curated for you. You
should expect the kinds of problems that come with real acquisition systems — gaps, sensor
noise, quality flags, timing quirks, and so on. Part of the exercise is discovering what's
actually in the data and deciding how to handle it. There's no single correct answer, but
you should be able to justify each choice you make and say what you'd do differently with
more time.

The six experiments differ in operating conditions (e.g. hydrolyzer current setpoint, air
flow, ambient conditions). Not every experiment is equally trustworthy or equally easy to
compare to the others — figuring out which comparisons the data actually supports is part
of the task.

## Deliverables

Work through as much of this as you can in the time available. Prioritization is part of
what's being evaluated — it's fine (expected, even) not to finish everything.

**A. Time-series data model.** Design how this data should live in InfluxDB: what's a
measurement, what's a tag, what's a field, how experiment/component/sensor identity is
represented. Raw values must be preserved unchanged somewhere in your model.

**B. Ingestion.** Get the raw CSV into InfluxDB. Python is fine for this.

**C. Data quality pipeline.** Don't silently drop or silently "fix" data. Make data quality
visible — e.g. distinguish a raw value, a processed value, a quality flag, and a reason. A
questionable reading should still be there; it should just be excludable from calculations
that need trustworthy input.

**D. Cleaning and processing.** Decide how to handle: missing values, gaps, duplicates,
out-of-order samples, flagged-bad data, outliers, sensor noise, stuck sensors, and signals
sampled at different rates. Not every signal should be treated the same way — be ready to
explain why a pH signal, a plant alarm/state signal, and an integrated energy value might
need different handling.

**E. Derived metrics**, computed per experiment where it makes sense:
   - Electrical power: `P(t) = U(t) x I(t)`
   - Energy: `E = integral of P(t) dt`
   - Capture efficiency: roughly `eta = (CO2_in - CO2_out) / CO2_in`
   - CO2 capture rate, from gas flow and CO2 concentration
   - Specific energy consumption: energy per unit of CO2 captured
   - Data-quality metrics: e.g. data completeness, valid-sample percentage,
     bad-quality percentage

**F. Experiment comparison.** Experiments started at different wall-clock times — align
them (e.g. `experiment_time = timestamp - experiment_start`) so they're comparable. Use
process phases (startup / steady-state / load-change / shutdown) if that helps your
analysis. Come with at least a few concrete findings, not just plots.

**G. Grafana dashboard design.** Sketch (or build, if you have time) a dashboard a scientist
would actually use to compare experiments: experiment selector, KPI summary, relevant
time-series, an overlay of multiple experiments on a common time axis, and something that
makes data quality visible rather than hidden.

## Format

Whatever gets you furthest fastest — scripts, a notebook, an actual running InfluxDB/Grafana
setup, or written design notes for the parts you don't get to implement. If you run out of
time on something, a clear note on what you'd do next is worth more than a rushed
half-implementation.

## Time budget

Open-book, 60 minutes. You will not finish all of this — that's by design. Stop when the
clock runs out, whatever state you're in, and be ready to walk through what you built, why,
and what you'd change.
