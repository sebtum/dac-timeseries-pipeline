# ADR-0008 — Local runtime: Docker Compose, pinned tags, services added progressively

Status: Accepted
Milestone: M0   Deliverable: A, B, G   Date: 2026-08-23

## Context

Which services this project uses was already settled: InfluxDB 3 Core queried with SQL
(ADR-0004), PostgreSQL for experiment metadata (ADR-0005), Grafana for visualisation
(ADR-0002). **How they run** was never decided. `docs/decisions/README.md` carried it as an
explicit open item ("Pending, to be added by Sebastian: Docker / local runtime").

Facts that constrain the choice:

- **Nothing needs a running service yet.** The pre-ingest census (ADR-0010) reads the source
  file and writes counts; it touches no database.
- **The first milestone that needs any service is M1, and it needs two at once** — InfluxDB
  (databases, retention, the downsampling mechanism of U-04) and PostgreSQL (the
  `experiments.json` metadata load of ADR-0005). Grafana is not needed until M6.
- `.gitignore` already reserves `influxdb-data/` and `grafana-data/`, which *presumes*
  containers with local volumes without ever having decided it.
- `influxdb:latest` has pointed at 3 Core since 27 May 2026. The tag does not identify a
  product line.
- Host is Windows 11; Docker is available (`CLAUDE.md`).

## Options considered

### Option 1 — Native installs on the host
Advantages: no container layer to reason about; direct access to data directories and logs; one
less thing between the process and the disk.
Caveats: the setup is not reproducible from the repository — it lives in whatever was clicked
through on this machine, so it cannot be handed to anyone, which is the explicit point of the CD
framing in `ROADMAP.md:100-104`; InfluxDB 3 Core on Windows is the least-travelled install path
of the three; changing a version means an uninstall.

### Option 2 — Containers started by documented `docker run` commands
Advantages: containerised without a compose file; each invocation is visible in full; trivial to
start exactly one service.
Caveats: the topology — networks, volume names, dependency order, environment — lives in prose in
a README rather than in a file anything can execute; two services that must talk to each other
need a manually created network; a README drifts from what was actually run and nothing notices.

### Option 3 — Compose with all three services present from the start, unused ones as placeholders
Advantages: the eventual full topology is visible from day one; adding a service later is
uncommenting rather than authoring.
Caveats: **a service nobody starts is untested configuration.** A Grafana block written in August
is never exercised until M6, by which point its image tag, environment variables and provisioning
paths have drifted from anything real — and it fails at exactly the moment it is first needed. A
commented-out block is worse: it is not even parsed, so it cannot be wrong in a way anything
detects.

### Option 4 — Compose, pinned image tags, services added at the milestone that first needs them
Advantages: the topology is a committed, executable file; a service enters the file only when
something immediately exercises it, so every block in the file is known to work; pinned tags make
the stack reproducible across rebuilds; named volumes match the paths `.gitignore` already
reserves; compose supplies the network for free, which M1 needs the moment Influx and Postgres
coexist.
Caveats: the compose file does not exist until M1, so this ADR decides a shape without producing
an artifact; adding a service later is a real edit rather than an uncomment; compose is itself a
dependency, though a near-universal one.

## Decision

**Docker Compose, with explicitly pinned image tags, and services added to the file at the
milestone that first needs them. No placeholder or commented-out services.**

The file is created at M1, when InfluxDB and PostgreSQL are both first required. Grafana is added
at M6.

## Why

The "start with one container, graduate to compose when there are several" instinct is reasonable
in general but does not apply here, because **the single-container case never occurs.** Nothing
needs a service before M1, and M1 needs two simultaneously. Compose's marginal cost over
`docker run` is therefore paid on the first day anything runs at all — there is no interval during
which the simpler option would have been simpler. That alone decides Option 4 over Option 2.

Against Option 3, the argument is that **an unexercised service definition is a liability, not a
head start.** Writing the Grafana block now buys nothing that writing it at M6 does not, and costs
the months of drift in between. The general principle: configuration that nothing executes is not
tested, and untested configuration reliably fails at the moment it is first depended upon. Adding
a service at its milestone costs a few lines and is validated immediately by the work that
motivated it.

Option 1 fails the requirement that generated the CD framing in the first place — a setup that
exists only as host state cannot be handed to anyone, and "it works on my laptop" is precisely
what committing the stack as code is meant to eliminate.

On pinning: `influxdb:latest` has pointed at 3 Core since 27 May 2026, having previously pointed
at the 2.x line. A `latest` tag here does not merely change a version, it changes the storage
engine and the query language. That is not a risk to be managed by pinning; it is the reason
pinning is the only defensible option.

## Consequences

- **No compose file exists until M1.** This ADR is a decision without an artifact — intentional
  under the progressive rule, but it means the decision must be re-read at M1 rather than inferred
  from a file.
- **Image tags are explicit versions, never `latest`**, for InfluxDB, Postgres and Grafana alike.
  Renewing a pin becomes a deliberate, reviewable commit.
- **Named volumes match the `.gitignore` reservations** (`influxdb-data/`, `grafana-data/`), so
  local state stays out of the repository without further thought.
- **Compose supplies the service network**, which is what lets Grafana reach InfluxDB by service
  name at M6 without manual network creation.
- **The host is Windows**, so any bind mount has to survive Windows path semantics. Named volumes
  avoid most of this; the exceptions are the provisioning directories mounted read-only at M1/M6
  (ADR-0009).
- Interacts with ADR-0009: the compose file is itself the first artifact of the
  provisioning-as-code policy, so the two decisions are separable in principle but arrive together
  in practice.
- **Not yet verified:** how InfluxDB 3 Core handles its admin token on first container start
  (U-13). That is a compose-shaping question and must be resolved before the file is written.

## Assumptions relied on

A-01 (untimed scope), A-02 (Core is adequate)

## Related

ADR-0002 (Grafana), ADR-0004 (InfluxDB 3 Core), ADR-0005 (Postgres), ADR-0009 (provisioning as
code). Open unknown created here: U-13.

## Defense

Everything runs in Docker Compose with pinned image tags, and services go into the file at the
milestone that first needs them rather than all up front. The reason it is compose and not a
couple of `docker run` lines is that there is no point in this project where I need exactly one
container — the first thing that needs a service needs InfluxDB and Postgres together, so I would
be hand-creating a network on day one anyway. I deliberately did not stub out the Grafana service
in advance: a service definition nothing ever starts is untested config, and it drifts until it
breaks at exactly the moment you first depend on it. On pinning, `influxdb:latest` has pointed at
3 Core since May 2026 and at the 2.x line before that — an unpinned tag there does not change a
version number, it changes the storage engine and the query language underneath you.
