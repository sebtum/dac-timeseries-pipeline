# ADR-0018 — Grafana dashboards: committed JSON provisioned read-only, one clock in the query, quality drawn not hidden

Status: Accepted
Milestone: M6   Deliverable: G   Date: 2026-11-25

This is the record of M6. Decisions 1 to 18 were made while planning (2026-11-24) and approved by
Sebastian with the plan. The sections "What the spike showed" and "Decided at execute" list what
execute found and added. Decision 1 replaces one exception of ADR-0009 (see its addendum).

## Context

In plain words: the brief asks for a Grafana dashboard with an experiment selector, KPIs, an overlay
of the experiments on a common time axis, and data quality that is visible rather than hidden. The
six experiments start on six different dates, the readings sit in InfluxDB and the experiment
metadata in Postgres, and Grafana does not join two datasources in a normal panel. So the dashboard
has to shift each experiment to its own start inside the query, take the start from Postgres, and
draw the excluded readings next to the accepted ones.

Details: M3 stored every reading with a verdict (ADR-0015), M4 the derived series (ADR-0016), M5 the
steady KPIs and pair comparability as a file (ADR-0017). M6 reads all of that and writes no
InfluxDB row. Its only write is three small Postgres tables (migration `0004`) that carry the M5
summary to Grafana. The panels and variables are listed in [`docs/dashboard.md`](../dashboard.md),
which a test keeps equal to the JSON. The numbering below is that of the milestone record.

## Decision

Where the plan recorded no rejected option, the cell says so. It does not add one that was not
weighed at the time.

### Scope and mode (decisions 1 to 3)

| # | Decision | Rejected |
|---|---|---|
| 1 | **Dashboards are committed JSON, provisioned read-only from the start** (`allowUiUpdates: false`, `disableDeletion: true`). Replaces ADR-0009 exception 2 ("build in the UI, export at the end"): agents build the dashboards and nobody clicks in the UI, so its premise no longer holds. The checker (decision 8) and rendered screenshots (decision 10) replace the UI check. Approved by Sebastian as a major decision. | UI first, export last (ADR-0009 exception 2). |
| 2 | **M5 counts as done for starting M6.** Its newest verify block had no defects and the merged commit only added that block. The findings stay a draft. | None recorded. |
| 3 | **Mode standard, judge verify, six tasks run by agents.** Wave 1: stack and checker with the loader; wave 2: the two dashboards; wave 3: real data; wave 4: this write-up. A bug found by a later task is reported to the owner, not patched outside the finder's files. | Full mode (no new risk class; dashboards are checked by query and screenshot). |

### The stack (decisions 4 to 6, 16, 17)

| # | Decision | Rejected |
|---|---|---|
| 4 | **Grafana in compose**, service `grafana`, container `${GRAFANA_CONTAINER_NAME:-dac-grafana}`, port `${GRAFANA_PORT:-3000}:3000`, named volume `grafana-data`, two read-only bind mounts for the provisioning and dashboard directories (config files, not data, so ADR-0008's bind-mount concern does not apply). Admin login and every secret reach Grafana as environment variables from `.env`. `depends_on` both stores healthy. | Anonymous viewer access (auth stays on locally, ADR-0009). |
| 5 | **Two datasources, fixed uids, provisioned:** `influx-dac` (built-in `influxdb` type, SQL mode over Flight, database `dac_raw`, insecure gRPC because the local server has no TLS) and `pg-dac` (Postgres, `sslmode=disable`). Dashboards provider: folder "DAC", `allowUiUpdates: false`, `disableDeletion: true`. | The FlightSQL plugin (ADR-0002). |
| 6 | **Start order.** Grafana reads the InfluxDB token once, at start, so `scripts/verify_stack.py up` starts `influxdb` and `postgres`, bootstraps the token, migrates, initialises and loads the experiments, then starts `grafana` and waits for `/api/health` and both datasource health checks. A second `up` keeps everything usable (MISTAKES E-08). The private stack's Grafana is on the port base plus 2. The README gives the same order for the dev stack. | None recorded. |
| 16 | **PyYAML pinned** in `requirements.txt`, so the lint can read the provisioned uids from the YAML. | None recorded. |
| 17 | **CI increment.** The lint runs in the unit suite. The integration job starts Grafana with `docker run --network host`, the provisioning and dashboard directories mounted, after the token bootstrap, so the `grafana`-marked tests run (a skip is a failure there). The contract example of the check output is validated in the lint job. | None recorded. |

### The overlay and the checker (decisions 7 to 11, 14)

| # | Decision | Rejected |
|---|---|---|
| 7 | **Overlay = query-time experiment time, start from Postgres.** A hidden Postgres variable `windows` renders the selected experiments as a SQL list `('EXP_001', <start_ns>, <end_ns>), ...`. The InfluxDB query joins on it and returns `experiment_time_min = (time_ns - start_ns) / 6e10`, drawn by an XY chart after a "partition by values" transformation on `experiment_id`. Full resolution, at most 6 x 7,200 points. | A stored aligned table (copies data; puts metadata into InfluxDB, against ADR-0006); a time series on fake 1970 timestamps (wrong dates in tooltips); start = first reading (shifts silently when it is missing); the Mixed datasource with join transformations (ADR-0005's fallback, kept in reserve by decision 11). |
| 8 | **A checker**, `python -m scripts.check_dashboards`: a static lint with no services (datasource uids, every variable used is declared and declared before use, unique panel ids and uids, allowed formats) and a live run that resolves the variables itself and posts every panel target and annotation query to `/api/ds/query`. Exit 0 every target returned rows, 1 a target empty or failed, 2 refused. Output `dashboard_check.json`, with a contract under `contracts/`. | None recorded. |
| 9 | **Tests never touch `dac_raw`.** End-to-end tests create a throwaway InfluxDB database, a temporary Grafana datasource pointing at it and a throwaway Postgres schema, and pass them to the checker as variable overrides. | None recorded. |
| 10 | **Screenshots by the Grafana image renderer**, compose service `renderer` under the profile `render`. `python -m scripts.screenshot_dashboards` saves four PNGs. | A browser driver (not installed; one more toolchain). |
| 11 | **Spike first, with a stop rule.** Before any panel, on the pinned images against Core 3.11.2: the datasource health and a `SELECT`; the VALUES join with time-to-integer arithmetic; a region annotation from `quality_intervals`; `$__timeFilter` expansion. If one failed and no variant of the same mechanism worked, the work stops and comes back as a question; no mechanism is swapped silently. | None recorded. |
| 14 | **U-05 measured.** The checker's `--time-range span` runs the detail dashboard with the picker from the earliest start to the latest end of all experiments; rows must equal the window run for every target. | None recorded. |

### Quality and KPIs (decisions 12, 13, 15)

| # | Decision | Rejected |
|---|---|---|
| 12 | **Quality made visible.** Accepted values as lines; excluded readings as red points at `value_raw` (series "excluded (raw value)"); gap rows grey and flatline rows orange; status colours complete green, partial amber, none red; fractions green at 0.95 or more, amber at 0.5 or more, red below (display only; the 0.95 is M4's `COMPLETE_COVERAGE`); comparability `same_conditions` and `supported` green, `confounded` amber with the differing factors shown. | None recorded. |
| 13 | **Steady KPIs and comparability go to Postgres** through `python -m scripts.load_comparison` and migration `0004_comparison.sql`: three tables (`comparison_kpi`, `comparison_pair`, `comparison_pair_kpi`). The loader validates the summary against its contract, deletes that `compare_version`'s rows and inserts the summary's in one transaction, then reads the counts back. Exit 0 written and read back, 2 refused, 3 write failed and rolled back, 4 read-back differs. `scripts.compare` stays read-only (ADR-0017, decision 4). | Grafana reading the JSON file; the compare command writing Postgres. |
| 15 | **No finding is pinned in a scenario** (MISTAKES E-09). Real-data scenarios pin completeness, equality with plain pulls and reproducibility. The one exception, read from committed data while planning: EXP_005 has no gap and no stuck stretch, so its table of gaps is correctly empty. | None recorded. |

### Branch (decision 18)

| # | Decision | Rejected |
|---|---|---|
| 18 | **Branch `m6-dashboard`, cut from `master`.** Commit and push at the end of M6; the merge waits for approval. | None recorded. |

## Images

The images are pinned to an exact tag and recorded with their digest (decision 4 and ADR-0008: no
`latest`). Both were pulled at execute.

| Image | Tag | Digest |
|---|---|---|
| `grafana/grafana` | 13.3.2 | `sha256:81556409ba48b2b922e0adb69a2511337d8ba7578f11962eefa6149a2d815101` |
| `grafana/grafana-image-renderer` | v5.12.11 | `sha256:cfa6c8f63e6d626f90208f2880f15bd5facc279daec1b9bb642af07aa850d95e` |

Details: the plan said "newest stable 12.x or later that passes the spike". 13.x was chosen over
12.4.16, which was not tested. The spike passed on 13.3.2, so it is not known whether 12.4.16 would
also pass.

## What the spike showed

The spike (decision 11) ran on the pinned images against Core 3.11.2 before any panel was written.
All four items passed and no mechanism was swapped.

| Item | Result | Working syntax |
|---|---|---|
| (a) Datasource health and a query | Both provisioned datasources report OK. `/api/ds/query` accepts `{refId, rawSql, format: "table"}`. | `{"refId": "A", "rawSql": "...", "format": "table"}` |
| (b) The VALUES join with time arithmetic | Runs unchanged. | `WITH w(experiment_id, t0, t1) AS (VALUES ...)` and `CAST(r.time AS BIGINT)` |
| (c) A region annotation from `quality_intervals` | Works with the end converted by a function. `CAST(end_ns AS TIMESTAMP)` overflows. | `to_timestamp_nanos(end_ns) AS timeend` |
| (d) `$__timeFilter(time)` | Expands to RFC 3339 literals, the end inclusive, also with an alias. | `$__timeFilter(time)`; the queries add `time >= span_from AND time < span_to` for a half-open window |

## Decided at execute

These calls were made while building. Each can be overturned. None reverses an ADR other than the
approved decision 1.

| # | What was decided | Why |
|---|---|---|
| 19 | **The renderer needs a token.** Grafana 13 refuses to start with a rendering server and the default token, so `GF_RENDERING_RENDERER_TOKEN` and the renderer's `AUTH_TOKEN` both come from `GRAFANA_RENDERER_TOKEN`. | Grafana 13 refuses the default token. |
| 20 | **The Postgres datasource type is `grafana-postgresql-datasource`.** | The panel datasources of both dashboards carry this type. |
| 21 | **The XY chart uses `mapping: auto` with `series: []`.** | With `seriesMapping` or `dims` Grafana 13 migrates the panel to one manual series and only the first experiment draws. Found in a rendered screenshot; a test pins it. |
| 22 | **Every InfluxDB query uses the half-open window** `time >= span_from AND time < span_to`, plus `$__timeFilter`. | The experiment window is `[start, end)`, and the end of `$__timeFilter` is inclusive (spike item d). |
| 23 | **"Accepted and excluded" is one target with two columns** (`accepted` from `value`, `excluded (raw value)` from `value_raw`, each null for the other verdict). Process phases are one target with `process_state` and `valve_state` columns. The excluded readings table is the newest 1,000, ascending. | With both columns in one target, a signal with no exclusions is not an empty target (plan, panel on accepted and excluded readings). |
| 24 | **The legend uses a `${__field.labels.experiment_id}` display-name override; the exclusion chart is a bar chart over a `groupingToMatrix` transform.** The `windows` variable of the compare dashboard converts the start with `(extract(epoch FROM t) * 1000000)::bigint * 1000`. | Implementation forms; no alternative was recorded. |
| 25 | **Completeness in the compare dashboard is the sum present over the sum expected of the polled signals.** | As in the plan's panel inventory; no alternative was recorded. |
| 26 | **The lint also rejects a variable used before it is declared, a repeated `refId`, a repeated variable name and a dashboard uid shared by two files.** `GRAFANA_*` process variables override `.env` for the checker. The dashboards mount nested in the `grafana-data` volume path. | Static checks that need no service; the checker's live run covers the rest. |
| 27 | **The first compare panel was raised from 6 to 8 grid rows**, and the panels below were shifted by 2 (layout only, no query change). | A static render clipped it to 4 of the 6 experiment rows. |

## Deviations and limits

What differs from the plan, or does not work as a reader might expect.

| # | What | Consequence |
|---|---|---|
| 1 | **Grafana 13 has no colour per annotation row.** Decision 12 asked for grey gaps and orange flatlines as regions. The annotation is one orange entry, limited to panel 3 of the detail dashboard; the kind is in the text and tags. Gap grey and flatline orange are applied in the "kind" column of the table of gaps and stuck stretches only. | The plot marks regions in one colour; the table carries the grey and orange. A reader who wants two colours on the plot needs two annotations (one per kind), which was not built. |
| 2 | **A database with no gap and no flatline has no `quality_intervals` table** (Core creates a table with its first row). The table "Gaps and stuck stretches" and the annotation then return an error instead of an empty list. | The real data has 34 intervals and is unaffected. The compare fixture is such a case, and its test writes one row for a made-up experiment id so the panel is empty rather than failing. A zero-interval database showing an error is a known gap (next steps). |
| 3 | **The bad and uncertain fraction thresholds are mirrored** (green below 0.05, amber below 0.5, red above). Decision 12 names thresholds for completeness and valid only. | A display choice. The numbers 0.05 and 0.5 are not a policy. |
| 4 | **The first compare table is 8 rows high, not 6** (decision 27). | Layout only. |
| 5 | **The colour thresholds are display only.** Nothing is stored or decided from them. The 0.95 equals `COMPLETE_COVERAGE`, and a test checks that. | If the metrics step changes its limit, the dashboard does not follow by itself; the test fails and the dashboard is edited. |

## Consequences

What this makes easy: the dashboards are reviewable text; a rebuild from an empty volume gives the
same dashboards; every panel query is run by the checker for every experiment and every numeric
signal (299 runs, 3,105 panel queries, 3,082 with rows, 23 empty and allowed, 0 errors); the overlay
needs no stored copy of the data. What it makes hard: editing a dashboard means editing JSON and
rerunning the checker, because the UI cannot save. What it forecloses: a quick fix in the browser.

What a reader can disagree with: the colour steps (display only); the amber for `confounded` (not
red, because it is not an error); the single annotation colour; the choice to read raw data on a
wide time picker (see U-05 below); the 8-row first table.

## Assumptions relied on

U-05 (the wide time picker). It is now closed for this data set: the detail dashboard run with the
picker over all 105 days returned the same rows as the window run for every panel query (1,794
entries compared, 0 differences). The caveat is scale: at plant scale a months-wide picker should
read the 1-minute rollup (`dac_rollup`), not raw. See [`../ASSUMPTIONS.md`](../ASSUMPTIONS.md).
A-09 (one run per condition) shapes what the comparability table may say.

## Defense

When asked "why JSON and not click it together": "Provisioned dashboards are read-only in the
browser, and nobody here builds them by hand, so the JSON is the only source and a rebuild gives the
same thing. The check for it is a program that posts every panel query to Grafana for every
experiment and every signal, and a screenshot, not my memory of clicking." When asked how six runs
on six dates share an axis: "The query subtracts each experiment's start, read from Postgres, from
every reading's time, so the axis is minutes since start and the points are full resolution. Nothing
is stored." When asked where the bad data went: "It is drawn. Excluded readings are red points at
the value the sensor reported, next to the accepted line, and gaps and stuck stretches are marked
and listed." When asked what is not done: the click-through is for the reviewer, GitHub Actions has
not run, and a database with no gaps at all shows an error in one table.
