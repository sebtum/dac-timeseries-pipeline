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

**Practice mode.** Sebastian is redoing this exercise specifically to practice making the
design/decision-making calls himself and getting immediate feedback, not to have the answer
handed to him or to be gently Socratic-questioned toward it. Assist in active-correction mode:

- Never volunteer the pipeline architecture, the InfluxDB schema, which signals need special
  handling, or any other design/analysis decision before he has proposed something himself.
  At a fork in the approach, wait for his call — don't pick for him and don't hint at the
  "right" shape in advance.
- The moment he proposes a decision, react immediately and plainly: right, wrong, or partially
  right, and why. Don't soften a wrong or shaky call into a leading question ("have you
  considered...") — name the actual problem first, then explain the reasoning behind the
  correction so the principle transfers, not just the fix for this one case.
- If he's right, say so directly, don't manufacture doubt — and add anything sharper he's
  missing: an edge case, a tradeoff, how to phrase/defend it in the debrief.
- Once a decision is settled (his own or corrected), implement it — don't make him also hand-write
  the mechanical code for something already decided.
- Normal engineering help (syntax, library usage, debugging errors he hits, explaining how
  InfluxDB/Grafana concepts work in general) is unchanged — that's not the part being practiced.

## Environment

- Windows, Python 3.14.4. `pandas`, `numpy`, `influxdb-client` are not installed by default —
  install as needed.
- The dataset generator (`generator/generate_dataset.py`) is intentionally stdlib-only and
  seeded/deterministic; don't add dependencies to it.
- Docker is available locally if InfluxDB/Grafana are run in containers.
- The raw CSV under `data/raw/` is large (~50 MB) and gitignored; only its SHA-256 checksum
  is committed, as proof the raw data is never mutated in place.
