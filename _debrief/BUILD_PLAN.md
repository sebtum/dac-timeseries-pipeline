<!--
This is the master build/design plan for the exercise. It contains the full defect list,
the physical model, and which experiment is the "trap" — i.e. it is a spoiler document.
It lives in _debrief/ specifically because CLAUDE.md already forbids reading anything in
this directory during the working session (P0/P1). Do not move or copy this content
anywhere outside _debrief/.

Canonical source: C:\Users\sebas\.claude\plans\ich-bereite-mich-auf-async-sketch.md
-->

# Phlair Interview Simulation — Systems & Data Infrastructure

> **Handoff note for a fresh session**
> Working directory: `C:\Users\sebas\Dev\phlair` (empty at plan time).
> Execute build phases **B1–B6** below. Do **not** write a solution to the task — the point
> is that Sebastian solves it. After B6, stop and hand control back; he starts the
> 60-minute working session himself (phases P0–P3).

## Context

Sebastian is preparing for a technical interview at Phlair (Direct Air Capture) for a
Systems & Data Infrastructure role. The real job touches Beckhoff PLCs, OPC-UA, InfluxDB,
PostgreSQL, Python, Grafana, experiment data, data quality and automation.

He wants a realistic 2-hour exercise: 60 min hands-on work on a deliberately messy
industrial time-series dataset, then 60 min of adversarial technical discussion and a
scored evaluation. The focus is explicitly **not** ML — it is the path
`raw data → TSDB → data quality → processing → derived metrics → experiment comparison → Grafana`,
with ML only as a closing discussion topic.

Decisions already made by the user:
- Materials and discussion in **English**.
- **No infra provided** — no docker-compose. Setting up InfluxDB/Grafana is part of the work.
- Raw data as **one long-format CSV** (`timestamp, experiment_id, source, signal, value, quality`).
- **Coaching mode**, not silent proctoring: this is the first practice run, and Claude is
  allowed in the real interview, so we work step by step together. The adversarial
  challenge round and the 1–10 scoring still happen at the end.

## Environment facts

- Python 3.14.4 installed; `pandas`, `numpy`, `influxdb_client` **not** installed.
- Docker 24.0.6 available (candidate can use it for InfluxDB/Grafana during the exercise).
- Consequence: **the generator must be pure-stdlib** (`random`, `math`, `csv`, `json`,
  `datetime`) so it always runs. Candidate-side dependencies are installed in P0.

---

# Part I — Build phases (executed by Claude, before the exercise)

## B1 — Repo skeleton and ground rules

Target layout:

```
C:\Users\sebas\Dev\phlair\
  README.md                     # how to run the exercise; ground rules
  CLAUDE.md                     # see "CLAUDE.md" section below — NO spoilers
  .gitignore                    # ignores data/raw/*.csv (50 MB), .venv, __pycache__
  task/
    TASK.md                     # problem statement, deliverables (NO hints)
    DATA_DICTIONARY.md          # signals, units, plausible ranges, sampling rates
  data/raw/
    dac_raw_timeseries.csv      # single long-format raw file (~600k rows, ~50 MB)
    dac_raw_timeseries.sha256   # checksum, committed — proves raw data never mutated
    experiments.json            # deliberately INCOMPLETE experiment metadata
  generator/
    generate_dataset.py         # stdlib-only, seeded (SEED=20260727), reproducible
  _debrief/                     # OFF LIMITS until the debrief
    ANSWER_KEY.md
    defect_manifest.json        # machine-generated, exact timestamps
    INTERVIEW_QUESTIONS.md
```

Also in B1: `git init` + initial commit (local only — see "Git and GitHub" below).

## B2 — Generator core: clean physics first

Write `generate_dataset.py` producing **physically consistent, defect-free** data for all
six experiments. Verify the physics here, before any mess is added — otherwise a generator
bug is indistinguishable from an injected defect.

### Physical model (plausible, not a real Phlair model)

- **Solar**: diurnal bell × Ornstein-Uhlenbeck-style cloud noise.
- **Hydrolyzer**: `current` follows `current_setpoint` via first-order lag (τ ≈ 25–60 s)
  plus a slew-rate limit. `voltage = V0 + b·ln(i/i0) + i·R(T)`, with `R` falling as
  `electrolyte_temperature` rises → cell voltage drops as the stack warms up.
  `power = voltage × current × n_cells`.
- **Electrolyte temperature**: heat balance — ohmic dissipation in, cooling toward ambient.
- **pH tanks**: first-order mixing. Base/acid production ∝ current (Faraday); consumption ∝
  solvent regeneration draw. So `acid_pH` falls / `base_pH` rises with load, with lag —
  this is what makes "how does pH react to a load change?" answerable.
- **Absorber**: capture efficiency from an NTU-style law
  `η = η_max·(1 − exp(−k·(solvent_flow/air_flow)^0.5 · f(solvent_pH) · g(solvent_temperature)))`.
  Higher air flow → shorter residence time → lower η but higher absolute capture rate.
  This is the deliberate rate-vs-efficiency trap.
- `co2_out_ppm = co2_in_ppm·(1 − η)`; `co2_in_ppm ≈ 420` with diurnal drift + noise.
- `pressure_drop ∝ air_flow²·(1 + fouling)`.
- A **Faraday consistency link** between hydrolyzer current and CO₂ released — a strong
  candidate can cross-check capture rate against electrochemical production.

### Process phases

`STARTUP → STEADY_STATE → LOAD_CHANGE (setpoint steps) → STEADY_STATE → SHUTDOWN`,
emitted as the `process_state` signal so phase-aware analysis is possible.

### Six experiments (~2 h each, different wall-clock start times and dates)

| ID | Character | What it teaches |
|----|-----------|-----------------|
| EXP_001 | Baseline, warm day, steady setpoint | reference case |
| EXP_002 | High current density | higher capture, *worse* specific energy (V rises) |
| EXP_003 | High air flow | high absolute capture rate, low efficiency % |
| EXP_004 | Cold ambient, high humidity | better absorption, slow warm-up, high initial V |
| EXP_005 | Solar-following, fluctuating setpoint | transients, step response, pH oscillation |
| EXP_006 | The trap | *looks* the best on naive KPIs, data is untrustworthy |

Different start times force `experiment_time = timestamp − experiment_start` alignment.

### Sampling rates

- 1 Hz: `current_setpoint, current, voltage, power, flow, pressure, air_flow, pump_speed, fan_speed`
- 0.5 Hz: `co2_in_ppm, co2_out_ppm, solvent_flow, pressure_drop`
- 0.2 Hz: `acid_pH, base_pH, solvent_pH, conductivity, electrolyte_temperature, solvent_temperature`
- 1/60 Hz: `ambient_temperature, relative_humidity, ambient_pressure, available_solar_power`
- Event-based: `valve_state, process_state`

`value` is a string column — numeric for most signals, categorical for `valve_state` /
`process_state`. Mixed dtypes are intentional.

Write rows streaming via `csv.writer`; never build the full table in memory.

## B3 — Defect injection layer

A **separate stage** applied on top of B2's clean signal. Every injected defect appends an
entry to `_debrief/defect_manifest.json` (signal, experiment, exact start/end timestamps,
defect type, intended lesson) so the answer key has real timestamps rather than prose.

1. **Short gaps** (5–30 s) in electrical signals — interpolation defensible.
2. **Long gaps**: one 8 min gap (EXP_002), one 32 min gap (EXP_006) — must invalidate, not interpolate.
3. **Quality flags** `GOOD / UNCERTAIN / BAD`, with BAD rows carrying plausible-but-wrong values.
4. **Outliers**: single-sample spikes — `voltage=412 V`, `solvent_pH=27.4`, `pressure=−3.1 bar`,
   `electrolyte_temperature=−50 °C`.
5. **Noise**: realistic per-sensor noise (pH ±0.05, conductivity, CO₂ analyzers).
6. **Stuck sensors**: `co2_out_ppm` frozen at 38.0 ppm for 45 min in EXP_006 (this is what
   fakes ~91 % efficiency); `solvent_temperature` frozen in EXP_003.
7. **Duplicate timestamps**: both exact duplicates *and* same-timestamp-different-value
   conflicts (the nastier case — forces an explicit dedup policy).
8. **Out-of-order**: a block of late-arriving rows appended at the end of the file, plus
   interleaved late arrivals mid-file.
9. **Physical inconsistencies** (statistically unremarkable, physically impossible):
   `current=0` with `power=12 kW`; `fan_speed=0` with `air_flow=1800`; `power ≠ U·I` by ~40 %
   over one window; `valve_state=CLOSED` with high `solvent_flow`; `pump_speed=0` with flow > 0.
10. **Unit change**: `air_flow` logged in Nm³/min instead of m³/h for EXP_004, `quality=GOOD` —
    simulates a PLC config change. Subtle; ties to the "what if PLC config changes?" question.
11. **Timezone trap**: the ambient logger writes local time with `+02:00` offset while every
    other source writes UTC `Z`. Discoverable from the data; hinted at only as
    "signals come from different loggers" in the data dictionary.
12. **Missing metadata**: `experiments.json` lacks fields for some experiments (no operator
    note, no sorbent batch, no target setpoint) → feeds "what metadata do you miss?".

## B4 — Task documentation (no spoilers)

`task/TASK.md` — problem statement, variable overview, technical constraints, deliverables
**only**. No hints, no defect list. Deliverables requested:

- **A.** InfluxDB data model (measurement/tag/field/timestamp; where `experiment_id`,
  component and sensor live; raw data preserved unchanged).
- **B.** Ingestion of the raw CSV into InfluxDB (Python).
- **C.** Data-quality pipeline exposing `raw value / processed value / quality flag / reason` —
  nothing silently deleted.
- **D.** Cleaning and processing, with **signal-specific** justification (a pH signal, an
  alarm state and an integrated energy must not be treated identically).
- **E.** Derived metrics per experiment: `P = U·I`, `E = ∫P dt`, capture efficiency,
  CO₂ capture rate, specific energy consumption, plus `data_completeness`,
  `valid_sample_percentage`, `bad_quality_percentage`.
- **F.** Experiment comparison on `experiment_time`, phase-aware where useful.
- **G.** Grafana dashboard design (experiment selector, KPI row, time-series, overlay,
  data-quality panel) — a written design counts; a running dashboard is a bonus.

TASK.md states explicitly that **finishing everything in 60 minutes is not expected** —
prioritisation and stated trade-offs are part of the evaluation.

`task/DATA_DICTIONARY.md` — signals, units, nominal ranges, sampling rates, and the neutral
note that signals arrive from different loggers. It must not reveal which signals are broken.

## B5 — Debrief materials

- `_debrief/ANSWER_KEY.md` — every injected defect with exact timestamps (from the manifest),
  why it was planted, and what a good answer looks like. Includes the naive-vs-corrected KPI
  table for all six experiments, so the EXP_006 trap can be shown numerically.
- `_debrief/INTERVIEW_QUESTIONS.md` — the adversarial question bank (Part 7 of the brief)
  plus the 1–10 scoring rubric and the
  *critical error / acceptable for a prototype / must fix before production* classification.

## B6 — Verification

1. `python generator/generate_dataset.py` completes and prints a summary
   (rows written, per-experiment row counts, defects injected).
2. `data/raw/dac_raw_timeseries.csv` exists, is non-empty, header is
   `timestamp,experiment_id,source,signal,value,quality`.
3. Sanity checks via a short read-only stdlib script: 6 distinct `experiment_id`s;
   `quality` ∈ {GOOD, UNCERTAIN, BAD}; duplicate timestamps present; at least one row pair
   out of chronological order; at least one `+02:00` timestamp present.
4. Physics spot-check on EXP_001: `power ≈ voltage × current × n_cells` for GOOD rows outside
   the injected-inconsistency windows; `co2_out_ppm < co2_in_ppm`.
5. **The trap must actually work**: EXP_006's naive capture efficiency ranks best while its
   completeness ranks worst. Verify numerically, not by assumption.
6. Re-run the generator; output must be byte-identical (seed determinism).
7. Write `dac_raw_timeseries.sha256` and commit it.

---

# Part II — Exercise phases (run by Sebastian)

## P0 — Setup (not counted against the 60 min)

`pip install pandas numpy influxdb-client`; optionally start InfluxDB + Grafana in Docker.
Run the generator once. Read `TASK.md` and `DATA_DICTIONARY.md`.

## P1 — 60 min working session (coaching mode)

Sebastian drives, decides the priorities and the architecture. Claude works step by step
with him as the interview-permitted assistant: implementing what he specifies, asking what
he wants at each fork, and flagging when a decision needs a justification he'd have to
defend. Claude does not hand him the defect list or the "right" pipeline design, and does
not read `_debrief/`.

## P2 — 60 min debrief (adversarial)

He presents. Claude switches into the Phlair-engineer role and runs the question bank
adversarially — tag cardinality, interpolation choices, filters hiding transients,
idempotency, late data, 100× scaling, causation vs correlation, and which conclusions the
data quality does *not* support. Then ML-as-extension, always demanding "what does the model
solve that a rule or a statistic cannot?", baselines before deep learning.

## P3 — Scoring

1–10 on: data modelling, time-series understanding, data quality, Python/data processing,
physical reasoning, experiment analysis, Grafana/visualisation, software architecture,
trade-off handling, technical communication. Each finding classified as *critical error* /
*acceptable for a 60-min prototype* / *must be fixed before production*.

---

# CLAUDE.md — yes, and it matters here

Because Claude is allowed during the exercise (and in the real interview), a root
`CLAUDE.md` is auto-loaded into every session in this directory. That makes it a control
surface, not decoration. It should contain:

- What this repo is (an interview exercise, not production code).
- **The hard rule: never read or reference `_debrief/`** during P0–P1. Without this, a
  future session will helpfully open the answer key and destroy the exercise.
- Coaching-mode contract for P1: implement what Sebastian specifies, ask at forks, don't
  volunteer the architecture.
- Environment notes (Python 3.14, stdlib-only generator, deps installed in P0).

It must contain **no** description of the injected defects — anything written there is
visible to the session helping him solve the task.

# Git and GitHub — local git yes, GitHub no

Not required for the exercise, but a local repo earns its keep:

- The brief's own question *"how do you guarantee raw data is preserved?"* becomes
  demonstrable: commit the dataset's **SHA-256** (not the 50 MB CSV — `.gitignore` it) and
  re-check it after the pipeline runs.
- Clean reset between practice runs, and a visible commit history of how he prioritised
  under time pressure — useful material for the P2 discussion.

A GitHub remote adds nothing for a local practice session: the 50 MB CSV is awkward to push,
and there is no collaborator. Worth reconsidering only if he later wants to show the
finished solution to the actual interviewers — then push the code and the checksum, keep the
generated data out.
