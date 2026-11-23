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

## Working session contract (changed 2026-11-23)

**Claude decides, Sebastian verifies on reports.** The earlier design-first contract (Sebastian
proposes every call, Claude reacts) was replaced on 2026-11-23 so the project can be finished.
Decisions made under the old contract (ADR-0001 … ADR-0012, `MISTAKES.md` C-entries) stay as
they are.

- Claude makes design and implementation decisions, implements them, and records each one with
  its reasoning and the rejected option, so it can be defended in review.
- **Major decisions need Sebastian's approval before they are acted on.** Major means any of:
  - it reverses or replaces an existing ADR;
  - it is hard to undo: a database retention setting, deleting or overwriting data, rewriting git
    history, merging to `master`;
  - it changes scope: dropping or shrinking a deliverable from `task/TASK.md`;
  - it is a headline claim Sebastian will present: the M5 findings, especially the
    flow/pressure-vs-voltage answer.
  Everything else Claude decides without waiting.
- Each milestone ends with a short report in the two-layer format (plain summary, then
  `Details:`), opened in the doc viewer. Sebastian reviews it there. Claude keeps going on the
  next milestone while he reviews, and folds any correction back in.
- Commit per milestone on a feature branch, and push it so CI runs. Merging to `master` waits
  for approval.
- Wrong calls Sebastian catches in review still go into `MISTAKES.md`.

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
