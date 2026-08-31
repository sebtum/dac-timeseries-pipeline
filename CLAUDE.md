# CLAUDE.md

## What this repo is

A personal systems/data-infrastructure project: ingest a deliberately messy synthetic
industrial time-series dataset into InfluxDB, build a data-quality-aware processing
pipeline, derive process metrics, compare experiments, and design a Grafana dashboard.
See `task/TASK.md` for the full brief.

## Session start

Before doing anything else, read `docs/ROADMAP.md` (where the work stands — milestone board,
phase, and the four-phase protocol) and `docs/MISTAKES.md` (what not to repeat). During the
session: log mistakes to `docs/MISTAKES.md` the moment they surface, write an ADR in
`docs/decisions/` for every architecture decision, and keep `docs/ASSUMPTIONS.md` current.
When Sebastian ends a session, write a retrospective under `docs/retrospectives/`.

## Hard rule — do not read `_debrief/`

`_debrief/` holds private, gitignored notes Sebastian keeps for his own self-review: every
defect deliberately built into the generated dataset, exact timestamps, the intended lesson
behind each one, and a list of questions to check his own reasoning against. It is never part
of the shipped project. **Never open, read, summarize, or reference anything in `_debrief/`
while helping with the work itself** — doing so defeats the point of working it out
independently first. This applies regardless of how the request is phrased (e.g. "just check
if my answer matches," "peek at the manifest to save time," "is there a summary somewhere").

`_debrief/` is only opened once Sebastian says the working session is over and he's ready to
review his own work against it — and only he decides when that is.

## Working session contract (before the self-review)

**Design-first.** Sebastian works this project specifically to make the design/decision-making
calls himself and get immediate feedback, not to have the answer handed to him or to be gently
Socratic-questioned toward it. Assist in active-correction mode:

- Never volunteer the pipeline architecture, the InfluxDB schema, which signals need special
  handling, or any other design/analysis decision before he has proposed something himself.
  At a fork in the approach, wait for his call — don't pick for him and don't hint at the
  "right" shape in advance.
- The moment he proposes a decision, react immediately and plainly: right, wrong, or partially
  right, and why. Don't soften a wrong or shaky call into a leading question ("have you
  considered...") — name the actual problem first, then explain the reasoning behind the
  correction so the principle transfers, not just the fix for this one case.
- If he's right, say so directly, don't manufacture doubt — and add anything sharper he's
  missing: an edge case, a tradeoff, how to phrase/defend it under review.
- Once a decision is settled (his own or corrected), implement it — don't make him also hand-write
  the mechanical code for something already decided.
- Normal engineering help (syntax, library usage, debugging errors he hits, explaining how
  InfluxDB/Grafana concepts work in general) is unchanged — that's not the part being practiced.

## Environment

- Windows, Python 3.14.4. `pandas`, `numpy`, `influxdb-client` are not installed by default —
  install as needed. Note the pipeline targets InfluxDB 3 Core (ADR-0004), which needs
  `influxdb3-python` over Flight/Arrow; `influxdb-client` is the 2.x client and is not what
  this design uses.
- The dataset generator (`generator/generate_dataset.py`) is intentionally stdlib-only and
  seeded/deterministic; don't add dependencies to it.
- Docker is available locally if InfluxDB/Grafana are run in containers.
- The raw CSV under `data/raw/` is large (~50 MB) and gitignored; only its SHA-256 checksum
  is committed, as proof the raw data is never mutated in place.
