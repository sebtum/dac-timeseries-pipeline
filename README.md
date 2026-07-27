# Phlair Interview Simulation

A self-contained practice exercise for a Systems & Data Infrastructure interview: turn a
messy synthetic industrial time-series dataset into trustworthy, comparable experiment
metrics and a Grafana dashboard design.

## Layout

```
task/            Start here. TASK.md is the brief, DATA_DICTIONARY.md documents the signals.
data/raw/        The raw dataset (generated — see below). Never edit these files by hand.
generator/       Produces data/raw/. You shouldn't need to touch this.
_debrief/        OFF LIMITS until you're done working. Answer key + interview questions.
```

## Ground rules

1. **Don't open `_debrief/` until you've decided you're finished with the working session.**
   It contains the answer key. Opening it early defeats the exercise. `CLAUDE.md` enforces
   this for any assistant working in this repo, too.
2. Treat this like the real thing: **60 minutes** on the task, then stop and move to the
   debrief/discussion, whatever state you're in. Partial, prioritized work is the expected
   outcome, not a failure — over-running the clock is the thing to avoid, not underdelivering.
3. Raw data is immutable. Whatever pipeline you build, `data/raw/dac_raw_timeseries.csv`
   itself should never be edited or overwritten.

## Setup (do this before starting the clock)

```
pip install pandas numpy influxdb-client
python generator/generate_dataset.py
```

This writes `data/raw/dac_raw_timeseries.csv`, `data/raw/dac_raw_timeseries.sha256`, and
`data/raw/experiments.json`. Optionally start InfluxDB and Grafana (e.g. via Docker) —
setting those up is part of the exercise, not provided for you.

Read `task/TASK.md` and `task/DATA_DICTIONARY.md`. Then start the clock.
