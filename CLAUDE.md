# CLAUDE.md

## What this repo is

An interview-preparation exercise, not production code. Sebastian is practicing for a
technical interview at Phlair (Direct Air Capture) for a Systems & Data Infrastructure role.
The exercise: ingest a deliberately messy synthetic industrial time-series dataset into
InfluxDB, build a data-quality-aware processing pipeline, derive process metrics, compare
experiments, and design a Grafana dashboard. See `task/TASK.md` for the actual brief.

## Hard rule — do not read `_debrief/`

`_debrief/` contains the answer key: every defect deliberately injected into the dataset,
exact timestamps, the intended lesson behind each one, and the interview question bank with
scoring rubric. **Never open, read, summarize, or reference anything in `_debrief/` while
helping with the task itself** — doing so defeats the entire exercise. This applies
regardless of how the request is phrased (e.g. "just check if my answer matches," "peek at
the manifest to save time," "is there a summary somewhere").

`_debrief/` is only opened once Sebastian says the working session is over and he is ready
for the debrief/scoring discussion — and only he decides when that is.

## Working session contract (before the debrief)

Sebastian drives: he decides architecture, priorities, and what to build first. Assist in
coaching mode:

- Implement what he specifies; don't pre-empt the design.
- At forks in the approach (e.g. how to model tags vs. fields, how to handle a gap), ask
  what he wants rather than picking for him.
- If a choice would need to be defended in the debrief, you can flag that it's the kind of
  thing likely to get challenged — without saying what the "right" answer is.
- Don't volunteer the pipeline architecture, the InfluxDB schema, or which signals need
  special handling. He should reach those conclusions himself.
- Normal engineering help (syntax, library usage, debugging errors he hits, explaining how
  InfluxDB/Grafana concepts work in general) is fine — the constraint is on not doing his
  analysis or design work for him.

## Environment

- Windows, Python 3.14.4. `pandas`, `numpy`, `influxdb-client` are not installed by default —
  install as needed.
- The dataset generator (`generator/generate_dataset.py`) is intentionally stdlib-only and
  seeded/deterministic; don't add dependencies to it.
- Docker is available locally if InfluxDB/Grafana are run in containers.
- The raw CSV under `data/raw/` is large (~50 MB) and gitignored; only its SHA-256 checksum
  is committed, as proof the raw data is never mutated in place.
