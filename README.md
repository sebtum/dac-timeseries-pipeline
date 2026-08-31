# DAC Process Data Pipeline

A personal systems/data-infrastructure project: turn a messy synthetic industrial
time-series dataset into trustworthy, comparable experiment metrics and a Grafana
dashboard design for a Direct Air Capture (DAC) pilot plant.

## Layout

```
task/            Start here. TASK.md is the brief, DATA_DICTIONARY.md documents the signals.
data/raw/        The raw dataset (generated — see below). Never edit these files by hand.
generator/       Produces data/raw/. You shouldn't need to touch this.
```

## Ground rules

1. Raw data is immutable. Whatever pipeline you build, `data/raw/dac_raw_timeseries.csv`
   itself should never be edited or overwritten.
2. Work through the deliverables in `task/TASK.md`; partial, prioritized work beats a rushed
   pass at all of them — see `docs/ROADMAP.md` for current scope and status.

## Setup

```
pip install pandas numpy influxdb-client
python generator/generate_dataset.py
```

This writes `data/raw/dac_raw_timeseries.csv`, `data/raw/dac_raw_timeseries.sha256`, and
`data/raw/experiments.json`. Optionally start InfluxDB and Grafana (e.g. via Docker) — setting
those up is part of the project.

Read `task/TASK.md` and `task/DATA_DICTIONARY.md` to get started.
