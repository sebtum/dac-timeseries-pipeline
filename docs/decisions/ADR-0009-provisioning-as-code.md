# ADR-0009 — Provisioning as code, added per milestone, with three named exceptions

Status: Accepted
Milestone: M0   Deliverable: — (cross-cutting)   Date: 2026-08-23

## Context

`ROADMAP.md:100-104` defines CD for this project as *the stack as code* rather than deployment,
since there is no environment to ship to: the compose file, Influx databases and retention
provisioned on startup, and Grafana datasources and dashboards loaded from committed files rather
than clicked into existence. The stated motivation is that "a dashboard that exists only inside a
container volume can't be handed to anyone."

What was never decided is **how much of that is committed, and from when.** ADR-0008 settled the
runtime; this settles what the runtime is configured *by*.

Facts that constrain the choice:

- **InfluxDB 3 Core has no declarative database configuration.** There is no file that can be
  mounted to define databases or retention — creation is via CLI or HTTP API only. "As code" here
  therefore always means *an idempotent script*, never a config file.
- **Core mints its admin token on first boot.** A token cannot be a committed literal. (The precise
  mechanism — whether it can be captured non-interactively, and whether running without auth
  locally is preferable — is **not verified**; see U-13.)
- **PostgreSQL's `docker-entrypoint-initdb.d/*.sql` runs only on an empty data volume.** On an
  existing volume it silently does nothing.
- **Grafana provisions datasources from mounted YAML**, which is its native and well-supported
  path. Dashboards can also be provisioned from committed JSON, but **provisioned dashboards are
  read-only in the UI unless `allowUiUpdates: true`**.
- The M0 CI increment specified in `ROADMAP.md:91` is "lint + format check, dependency install from
  a pinned manifest" — none of which touches the dataset, so U-02 (the gitignored CSV) does not
  block it.

## Options considered

### Option 1 — Everything provisioned as code, all of it committed up front
Advantages: one decision, no per-milestone bookkeeping; the full stack is reproducible from an
empty checkout on day one; nothing is ever "temporarily by hand" and then forgotten.
Caveats: most of it configures services that do not exist yet under ADR-0008's progressive rule,
so it is untested config for the same reason placeholder services were rejected there; it forces a
Grafana dashboard decision at M0 that cannot sensibly be made until M6.

### Option 2 — Policy decided now, layers added at the milestone that first needs them
Advantages: mirrors both ADR-0008 and the incremental CI pattern already chosen in
`ROADMAP.md:85-98`, so the repository has one consistent rhythm rather than three; every
provisioning artifact is exercised by the milestone that introduces it; the *policy* is settled
now, so no milestone gets to quietly decide "by hand this once".
Caveats: requires discipline — a layer deferred is a layer that can be forgotten; the milestone
board has to carry the obligation.

### Option 3 — Compose only; databases, schema and Grafana configured by hand
Advantages: fastest to a working stack; no scripts to write or debug; fine while there is exactly
one operator on one machine.
Caveats: fails the requirement that motivated the CD framing — the interesting state (retention
policies, the metadata schema, the dashboard) is precisely the part that would exist only inside a
volume; rebuilding after a `docker compose down -v` means redoing it from memory, and memory is
where undocumented decisions go to die.

### Option 4 — Decide nothing now; revisit at M1
Advantages: no premature commitment; the pre-ingest census needs no stack at all.
Caveats: M1 is exactly the milestone that would be under pressure to skip it, and "we'll make it
reproducible later" is the failure mode this repository already reverted once (`2266be2`).

## Decision

**Option 2: everything is provisioned as code, the policy is fixed now, and each layer is
committed at the milestone that first needs it — with three exceptions that are not about speed.**

| Layer | As-code artifact | Lands at |
|---|---|---|
| Container topology | `docker-compose.yml`, pinned tags (ADR-0008) | M1 |
| Influx databases + retention | idempotent init script (CLI/HTTP — no config file exists) | M1 |
| Influx auth token | generated at startup into a gitignored `.env` by a committed script | M1 (pending U-13) |
| Postgres schema | migration, not init SQL (see exception 3) | M1 (pending U-14) |
| Grafana datasources | `provisioning/datasources/*.yaml`, mounted | M6 |
| Grafana dashboards | exported JSON, committed **after** M6 builds them (see exception 2) | end of M6 |
| CI (lint, format, pinned manifest) | `requirements.txt`, ruff config, Actions workflow | M0 |

### Exception 1 — Secrets are not code; their generation is

InfluxDB 3 Core mints its admin token on first boot and it cannot be a committed literal. So one
link in the chain is necessarily generated at runtime into a gitignored `.env` that the other
services read. The claim must be stated precisely — *everything except the secret, whose
generation is scripted* — because the unqualified version ("the whole stack is as code") is
falsifiable in a single question, and being caught on it costs more than the qualification does.

### Exception 2 — Grafana dashboards are M6's output, not its input

Provisioned dashboards are read-only in the UI unless `allowUiUpdates: true`, and a dashboard
worth using cannot be hand-authored as JSON — the real workflow is interactive. So the order is
**build in the UI → export JSON → commit → provision**, and the as-code artifact arrives at the
*end* of M6 rather than the beginning. Datasources are the opposite case: pure configuration with
no creative content, provisioned from the day Grafana enters the compose file.

This is the one place where as-code has a genuine cost, and the cost is not first-build effort but
**iteration speed** — a provisioned read-only dashboard makes the edit loop painful precisely
while the dashboard is being designed.

### Exception 3 — Init SQL is provisioning, not migration

`docker-entrypoint-initdb.d/*.sql` runs only against an empty data volume and silently no-ops
otherwise. Using it would mean schema changes after M1 appear to be applied and are not — a silent
failure, which is the class of defect this whole exercise is about. `ROADMAP.md:92` already asks
for "Postgres metadata schema migration runs clean", so a migration path is required rather than
optional. Which mechanism is U-14.

### CI increment timing

The M0 CI increment lands **before** any profiling or ingest code, not after. It is unblocked:
lint, format and dependency install never read the dataset, so U-02 does not apply — U-02 becomes
live at M2's ingest smoke test, which is the first check that needs actual data.

## Why

The decisive argument for per-milestone over up-front is the same one that decided ADR-0008, and
consistency between them matters more than either in isolation: **configuration that nothing
executes is not tested.** Committing Grafana provisioning in August, to be first run in M6, has the
identical failure mode as stubbing a Grafana service into compose. Option 1 is Option 3 of
ADR-0008 wearing different clothes.

Option 3 is rejected on what it leaves out rather than what it does. The parts it defers to manual
work — retention policies, the metadata schema, the dashboard — are exactly the parts that carry
the design decisions. Losing a container is cheap; losing the reasoning encoded in a retention
policy is not, and a `docker compose down -v` is one keystroke.

The general rule the three exceptions are instances of: **anything you would otherwise have to
remember to click gets committed; anything that is itself a milestone's creative output gets
committed after that milestone produces it; secrets are never committed but their generation is.**

## Consequences

- **The milestone board carries the obligation.** A layer deferred is a layer that can be
  forgotten, so each milestone's Execute section must name its provisioning artifact, the way each
  already names its CI increment.
- **A gitignored `.env` becomes load-bearing.** Anyone cloning the repository runs the bootstrap
  script before anything works; that script and its documentation are the reproducibility story,
  and if it is wrong the "as code" claim is hollow.
- **`docker compose down -v` must be survivable.** That is the real test of this decision, and it
  should be run deliberately at least once rather than discovered accidentally.
- **The dashboard round-trip has to actually happen.** Exception 2 defers the commit to the end of
  M6, which is precisely when the temptation to declare victory is highest. The M6 verify criteria
  already require committed JSON and screenshots.
- **A lint-only CI job proves very little today.** Its value is that M2's ingest test has somewhere
  to land and that the profiling code is written under lint discipline from line one — not that it
  catches anything now. Overselling it in the debrief would be worse than omitting it.
- **The pinned manifest is not ceremony.** Profile numbers committed as evidence are only evidence
  if the version that produced them is known; `requirements.txt` is a precondition for the
  reconnaissance output meaning anything later.
- Two mechanisms remain unverified and block M1: U-13 (Core token bootstrap) and U-14 (Postgres
  migration mechanism).

## Assumptions relied on

A-01 (untimed scope — the per-milestone discipline would not survive a 60-minute clock)

## Related

ADR-0008 (local runtime). Open unknowns created here: U-13, U-14. Narrows U-02.

## Debrief answer

The whole stack is provisioned as code — compose file, Influx database and retention creation,
Postgres schema, Grafana datasources — and each piece is committed at the milestone that first
needs it rather than all up front, because config that nothing runs is untested config. There are
three honest exceptions. Secrets can't be committed, so the Influx admin token is generated at
startup into a gitignored `.env` by a script that *is* committed — I'd rather say "everything
except the secret, whose generation is scripted" than make a claim that falls over in one
question. Grafana dashboards are the output of the dashboard milestone, not its input: provisioned
dashboards are read-only in the UI, and you can't usefully hand-author dashboard JSON, so the flow
is build, export, commit, provision. And Postgres init SQL only runs on an empty volume, which
means it silently stops applying the moment there's data — so schema changes go through migrations,
not the entrypoint directory. The rule underneath all three is: anything you'd otherwise have to
remember to click gets committed, anything that's a milestone's creative output gets committed
after it exists, and secrets are never committed but their generation is.
