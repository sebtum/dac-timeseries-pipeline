# ADR-0002 — Grafana as the visualisation layer

Status: Given (constraint)
Milestone: —   Deliverable: G   Date: 2026-08-11

## Context

`task/TASK.md` deliverable G names Grafana explicitly: "Build a running dashboard a scientist
would actually use to compare experiments". Imposed, not chosen.

What the dashboard has to do, from the brief:

- Experiment selector.
- KPI summary.
- Relevant time-series.
- Overlay of multiple experiments on a **common** time axis — experiments started at
  different wall-clock times, so the overlay needs an aligned axis, not raw timestamps.
- Make data quality visible rather than hidden.

The overlay requirement is the one that discriminates between the options below: most
dashboard tools assume the x-axis is wall-clock time.

## Options considered

### Option 1 — Grafana (the given)
Advantages: first-class InfluxDB datasource; template variables give the experiment selector
almost for free; dashboards are JSON, so they can live in git and be provisioned as code;
mixed panel types (stat tiles, time-series, state timelines) suit a KPI-plus-signals layout;
the tool a plant engineer would actually already have.
Caveats: strongly wall-clock oriented — plotting on a relative `experiment_time` axis takes
deliberate work, either in the query or in the stored data model; editing in the UI and
exporting JSON afterwards drifts from what's committed unless provisioning is enforced;
expressing "this value exists but is untrustworthy" needs a chosen convention, it isn't free.

### Option 2 — Influx UI's built-in dashboards
Advantages: nothing extra to run; zero integration work.
Caveats: much weaker panel library and templating; no realistic provisioning-as-code story;
not what the brief asked for, and not what a plant would deploy.

### Option 3 — Python app (Streamlit / Dash / Panel)
Advantages: total freedom over the x-axis, so relative-time overlay is trivial; arbitrary
Python for derived metrics and quality shading; one language across the whole project.
Caveats: you build and maintain a web app; no alerting, no auth, no provisioning story out of
the box; every panel is code; it's an analysis tool for one person rather than shared plant
infrastructure.

### Option 4 — Jupyter notebook with matplotlib/plotly
Advantages: fastest path to a picture; best medium for a one-off analytical narrative.
Caveats: not "running" in any operational sense; no live data, no selector, no reuse by a
scientist who doesn't run notebooks; fails the brief's "actually use" test.

## Decision

Grafana, as imposed by the brief.

## Why

Grafana is the only option that satisfies all four constraints this project actually has at
once: shared operational use rather than one person's laptop, reading **both** datasources,
provisioning from committed files, and no bespoke application to maintain.

Each alternative fails on a specific one, not on general quality:

- **Influx UI** structurally cannot see half the system. Experiment metadata lives in
  PostgreSQL (ADR-0005), so the metadata-driven experiment selector is not merely awkward
  there — it's impossible. That disqualifies it before any judgement about panel quality.
- **A Python app** would mean reimplementing infrastructure that already exists — auth,
  sharing, alerting, datasource management, dashboards as versioned artifacts — and the result
  would be a single-user analysis tool rather than shared plant infrastructure. The objection
  is not the effort; it's that the effort buys something worse.
- **Jupyter is not a competing option at all.** It's a complement, and a real lab has both: a
  notebook is the right medium for a one-off deep dive by someone comfortable in Python, and
  the wrong medium for a dashboard a scientist opens repeatedly without touching code. Choosing
  Grafana here doesn't displace notebooks; it covers the requirement notebooks don't.

The cost, stated up front rather than discovered later: Grafana is wall-clock oriented, so the
common-time-axis overlay the brief explicitly asks for is the one thing this choice makes
harder. That work is real and is tracked in M5/M6.

Also relevant to the query language in ADR-0004: Grafana's **official** InfluxDB datasource
absorbed the v3 Flight SQL plugin, so SQL against InfluxDB 3 is a first-class path. The
standalone `grafana-flightsql-datasource` plugin is no longer actively developed, so building
on it would have been building on something already abandoned.

## Consequences

- The common-time-axis overlay becomes a design constraint that reaches back into the data
  model — how alignment is represented is decided in M1/M5, not deferred to M6.
- Dashboards are JSON, so they can be committed and provisioned; whether they are is an M6
  and CI decision.
- Making quality visible requires an explicit convention agreed in M3, since Grafana has no
  native notion of a per-point quality flag.

## Assumptions relied on

A-01

## Defense

Grafana was in the brief, and it's also the only thing that meets all the constraints at once:
it's shared rather than one person's laptop, it reads both InfluxDB and the Postgres metadata,
and the dashboards are JSON so they're provisioned from the repo instead of clicked into
existence. The Influx UI is out structurally — the metadata is in Postgres, so it can't drive
the experiment selector at all. A Streamlit app would have meant rebuilding auth, sharing and
provisioning to end up with a single-user tool. Notebooks I'd keep, but as a complement — they
answer one-off questions, they aren't a dashboard a scientist opens every morning. What it
costs me is the time axis: Grafana thinks in wall-clock, and the brief wants six experiments
overlaid on a common relative axis, so that alignment is work I have to do rather than get.
