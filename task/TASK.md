# Systems & Data Infrastructure — Project Brief

## Background

This project is built around a Direct Air Capture (DAC) pilot plant. Simplified, the
process has three stages:

1. **Absorption** — air is contacted with a basic sorbent that picks up CO2.
2. **Desorption** — the CO2-loaded sorbent is treated with acid, releasing the CO2.
3. **Regeneration** — an electrochemical hydrolyzer regenerates the acid and base
   using electrical power. The hydrolyzer can vary its output depending on available
   renewable power.

You are given raw sensor data from six pilot-scale experiments run under different
operating conditions. The job is to turn that raw data into something a scientist could
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
noise, quality flags, timing quirks, and so on. Part of the project is discovering what's
actually in the data and deciding how to handle it. There's no single correct answer, but
you should be able to justify each choice you make and say what you'd do differently with
more time.

The six experiments differ in operating conditions (e.g. hydrolyzer current setpoint, air
flow, ambient conditions). Not every experiment is equally trustworthy or equally easy to
compare to the others — figuring out which comparisons the data actually supports is part
of the task.

## Deliverables

Work through all of the following.

**A. Time-series data model.** Design how this data should live in InfluxDB: what's a
measurement, what's a tag, what's a field, how experiment/component/sensor identity is
represented. Raw values must be preserved unchanged somewhere in your model. Also address
cost/scalability directly: months of high-resolution electrochemical data adds up — what's
your retention/downsampling/tiering strategy, and what stays at full resolution vs. gets
rolled up over time?

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
analysis. Come with at least a few concrete findings, not just plots — in particular, come
with a specific, evidenced answer for how flow and pressure relate to hydrolyzer (cell)
voltage; that's the relationship most worth having a sharp answer for.

**G. Grafana dashboard.** Build a running dashboard a scientist would actually use to compare
experiments: experiment selector, KPI summary, relevant time-series, an overlay of multiple
experiments on a common time axis, and something that makes data quality visible rather than
hidden.

## Format

Scripts, a notebook, an actual running InfluxDB/Grafana setup — whatever gets each deliverable
to a working state. `H` and `I` below are design/verbal by nature, not as a fallback for
running out of time; everything in `A`–`G` should end up as something you can actually run or
click through, not just described.

## Extended topics

The deliverables above assume the raw CSV as a given starting point. These two go one layer
further up the stack — treat them as open-ended design/discussion, not something to build.

**H. Edge ingestion & resilience (design only).** The raw CSV is, in effect, what already
landed in a local historian/buffer on an industrial PC at the plant. Design the layer
upstream of it: how does that edge device get data from the plant's control system, how does
it forward data onward, how does it survive a loss of connectivity without losing data, and
how is that link secured? There's no real OPC-UA server or PLC to connect to here, so this
stays a design exercise — but come with a specific architecture, not just component names,
and be ready to defend the failure-mode handling in particular. Also design for "system
health" as its own concern, separate from whether an individual value is clean: how would you
know the pipeline itself is alive vs. silently stalled — heartbeats, staleness alarms, a
watchdog? Name the failure mode where every point still looks individually fine but the
pipeline has actually stopped moving data.

**I. Cloud scaling narrative (verbal).** Talk through how your design would change if it had
to run on AWS instead of on your laptop/local Docker setup — for each piece (ingestion,
storage, processing, dashboarding), what becomes a managed service, what stays custom, and
what changes about how failures are handled once it's cloud/multi-tenant rather than one box
you control end to end. No need to actually stand any of this up.

**J. Presentation walkthrough (verbal).** Once the rest is in whatever state you've reached,
prepare a short walkthrough as if presenting to a technical stakeholder: why this specific
PLC-to-cloud flow (not just what it is), and a concrete walk-through of comparing a voltage
spike from one experiment against another — show exactly how your system gets from raw
telemetry to that comparison without the scientist manually aligning anything themselves.
