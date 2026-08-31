# ADR-0003 — Python for ingestion and processing

Status: Accepted
Milestone: —   Deliverable: B, C, D, E, F   Date: 2026-08-12

> One open item: the rebuttal to "a pandas pipeline won't survive months of 1 Hz data" is not
> yet decided. Tracked as U-06.

## Context

Unlike ADR-0001 and ADR-0002, this one is an actual choice. `task/TASK.md` deliverable B says
only "Python is fine for this" — permitted, not required. Nothing in the brief constrains the
processing language at all.

Facts bearing on it:

- Environment is Windows, Python 3.14.4; `pandas` 3.0.5, `numpy` 2.5.1 and `influxdb-client`
  are already installed (`CLAUDE.md`).
- **The installed client is the wrong one.** `influxdb_client` is the 2.x client; ADR-0004
  chose InfluxDB 3 Core, which is reached over Flight/Arrow via `influxdb3-python`. Whatever
  language is chosen, that dependency changes.
- Input is a 32 MB / 520 k-row CSV — small enough to hold in memory whole, so the choice is
  not forced by scale at this size.
- The brief's stated target is "months of high-resolution electrochemical data", which is
  several orders of magnitude larger than the sample.
- `generator/generate_dataset.py` is deliberately stdlib-only; that constraint applies to the
  generator alone, not to the pipeline.

## Options considered

### Option 1 — Python (pandas / numpy + `influxdb3-python`)
Advantages: already the environment's language; pandas suits the resample / interpolate /
rolling-window operations that deliverable D implies; the official v3 client handles batching
and retries and returns Arrow, which pandas consumes directly; the same language covers
ingestion, processing, analysis and any test suite; it is also the language the InfluxDB 3
Processing Engine runs, so the downsampling plugin ADR-0004 commits us to building is Python
either way.
Caveats: slowest of the options per row — irrelevant at this dataset's 520k rows, material at
the scale the brief projects. The real limit is **memory, not speed**: a naive pandas pipeline
over months of 1 Hz data doesn't run slowly, it raises `MemoryError`. That has to be answered
deliberately rather than assumed. Dependency management on Windows also adds setup friction a
compiled binary wouldn't have.

### Option 2 — Telegraf, configuration-driven
Influx's own agent, with a `file`/`csv` input plugin and processor plugins.
Advantages: no ingestion code to write or maintain; built for exactly this transport job;
the same agent is what would run on the edge device in deliverable H, so the story is
consistent end to end.
Caveats: the transformations in C and D go well past what processor plugins express
comfortably; quality-flag logic and per-signal handling rules would end up as awkward config
or a plugin anyway; debugging config is worse than debugging code.

### Option 3 — Go or Rust
Advantages: far faster and far lighter per row; a single static binary is easy to ship to an
edge device; genuine concurrency for parallel ingest.
Caveats: no analytical ecosystem comparable to pandas for the exploratory half (M0, M5);
much slower to write, and this project is graded on decisions rather than throughput; not in
the installed environment.

### Option 4 — Influx CLI / line-protocol bulk write
Advantages: fastest possible path to getting raw bytes into the database.
Caveats: covers deliverable B only; contributes nothing to C, D, E or F, so a second tool is
needed regardless.

## Decision

Python (pandas/numpy + `influxdb3-python`) for ingestion, quality/cleaning, derived metrics and
analysis — accepted knowing it is the slowest option per row.

## Why

**It covers every phase.** One language runs ingestion, the quality and cleaning rules, the
derived metrics, the comparison analysis and the tests, with no handoff between stages and no
second toolchain to justify. Nothing else on the list does that: Option 4 covers ingestion only,
and Option 2 covers ingestion and light transformation before falling over.

**It allows exploration.** M0 reconnaissance and M5 comparison are exploratory by nature — you
don't know in advance which checks matter or which comparisons the data supports. pandas is
built for that iteration; a compiled language makes every question a rebuild, and a
configuration file makes most questions unaskable.

**It goes beyond what plugins can express.** Telegraf's processor plugins handle transport and
simple transformation. Deliverables C and D need per-signal conditional logic that attaches a
*reason* to every exclusion and treats a pH signal differently from a plant state signal from
an integrated energy value. That is not processor configuration; expressing it in Telegraf
means writing a plugin, which is writing code with worse ergonomics and a worse test story.

**And it's the language the database itself runs.** ADR-0004 commits to building downsampling
on the InfluxDB 3 Processing Engine, which executes Python plugins in-process. So Python is not
only the pipeline language — it's the in-database language too. One language, including inside
the store.

The cost accepted: it is the slowest option per row. At 520k rows that is irrelevant. At the
scale the brief projects it is not, and the binding constraint there is memory rather than
speed — see Consequences and U-06.

## Consequences

- One language across B–F, and across the Processing Engine plugin as well; no context switch
  between ingestion, analysis and in-database processing.
- **Memory, not speed, is the scaling limit.** A pandas pipeline that outgrows RAM does not
  degrade, it fails outright. Chunking, per-experiment processing, or pushing aggregation into
  the database is therefore a design question in M2/M3, not an optimisation to defer. **The
  answer is not yet decided (U-06)** — and it is the most predictable challenge this choice
  invites.
- The dependency is `influxdb3-python`, not the installed `influxdb_client`. The environment
  needs updating and `CLAUDE.md` says otherwise.
- The edge-device story in M7 (H) may well name a different tool than the one used here — that
  gap needs an explicit answer, not silence.
- Dependencies must be pinned for CI to be reproducible.

## Assumptions relied on

A-01

## Defense

Python, and I picked it knowing it's the slowest option per row. It covers every phase —
ingestion, the quality rules, the metrics, the comparison, the tests — in one language with no
handoff, and the exploratory parts genuinely need pandas, because I didn't know in advance
which checks would matter. Telegraf would have handled the transport, but the quality pipeline
attaches a reason to every excluded sample and treats each signal differently, which isn't
processor config — you'd end up writing a plugin anyway. And since InfluxDB 3's Processing
Engine runs Python, the downsampling I have to build is Python too, so it's one language right
into the database.

> ⚠ **Still owed:** the answer to "that pipeline won't survive months of 1 Hz data". The
> correct framing is that the limit is memory, not speed — it fails rather than slows — but the
> mitigation has not been decided. See U-06.
