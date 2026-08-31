# ADR-0006 — Time-series data model: tags, fields, and the numeric/state table split

Status: Accepted
Milestone: M1   Deliverable: A   Date: 2026-08-22

## Context

`data/raw/dac_raw_timeseries.csv` is long format — `timestamp, experiment_id, source, signal,
value, quality` — and deliverable A asks what becomes a measurement, a tag and a field.
`task/DATA_DICTIONARY.md` closes with a deliberate nudge: "sensor identity and experiment
identity are carried as columns, not encoded into a combined name — worth thinking about when
you design the InfluxDB schema."

Facts established by a read-only scan of the raw CSV before deciding:

- **520,005 rows.**
- **25 distinct `(source, signal)` pairs**, and signal names are unique across sources — there
  are exactly 25 distinct signal names too, so `signal` alone identifies a series within an
  experiment. (`flow` and `solvent_flow` are separately named, as the dictionary warns.)
- Six experiments → `6 × 25` = **150 series** under the tag set below.
- Quality flags: `GOOD` 519,675 / `UNCERTAIN` 230 / `BAD` 100 — **0.06% non-GOOD**.

The constraint that shapes the rest of this ADR:

- **In InfluxDB 3, a column's type is fixed by its first write, per `(table, column)`.**
  23 of the 25 signals are numeric. Two — `valve_state` (`OPEN`/`CLOSED`) and `process_state`
  (`STARTUP`/`STEADY_STATE`/`LOAD_CHANGE`/`SHUTDOWN`) — are categorical strings. A single
  `value` field cannot hold both. This is not a preference; it is a hard write-time failure.
- InfluxDB 3 has **no per-series index**. Storage is Parquet with a sort key, so the familiar
  2.x argument that tag cardinality inflates an in-memory index does not literally apply here.

## Options considered

### Option 1 — One table, one `value` field, categoricals encoded as integers
`process_state` → 0..3, `valve_state` → 0/1, with the code→label mapping held in Postgres
alongside experiment metadata (ADR-0005).
Advantages: one table, one column type, one ingest and cleaning code path, no nullable columns,
zero write-time type-conflict risk; a numeric column is compact.
Caveats: **the database never holds what the sensor reported**, so deliverable A's "raw values
must be preserved unchanged" would rest entirely on a gitignored CSV outside the system;
the encoding invents an ordering that does not exist, and nothing stops `mean(value)` over a
window spanning `STARTUP` and `LOAD_CHANGE` from returning `1.7` — a string column would have
refused; the code→label mapping ends up duplicated in Postgres *and* in Grafana's dashboard
JSON value mappings, because Grafana does not join datasources in a normal panel (ADR-0005),
and two copies drift.

### Option 2 — One table, two nullable value columns (`value_num` float, `value_str` string)
Advantages: keeps the CSV's long shape end to end; raw strings stored as strings; one table.
Caveats: every row carries a null column; every query has to know which column a signal lives
in; the schema advertises a generality the data does not have — 23 signals will never populate
`value_str`.

### Option 3 — Wide: one table per source, one column per signal
Four tables (`ambient`, `absorber`, `hydrolyzer`, `plant`); `signal` stops being a tag.
Advantages: every column natively typed; naturally compact for signals sampled together.
Caveats: requires pivoting the long CSV at ingest, which is a transformation before the data
lands; signals within a source are sampled at different rates (`air_flow` at ~1 Hz,
`pressure_drop` at ~0.5 Hz, `solvent_pH` at ~0.2 Hz), so rows would be mostly sparse; adding a
signal becomes a schema migration rather than a new tag value.

### Option 4 — Two tables split by value type
`readings_numeric` (float `value`) and `readings_state` (string `value`), same tag set on both.
Advantages: raw values stored exactly as reported, strings as strings; no nulls; no type
conflict; `signal` stays a tag so adding a signal is data, not schema; Grafana's state-timeline
panel renders string states natively, needing no value mappings and no second copy of any
mapping.
Caveats: a query wanting both tables needs a union; two ingest paths.

## Decision

**Two tables split by value type, with ingest storing values exactly as they appear in the CSV.**

```
readings_numeric                        readings_state
  tags:   experiment_id, source, signal   tags:   experiment_id, source, signal
  fields: value    float64                fields: value    string
          quality  string                         quality  string
  23 signals                              valve_state, process_state
```

`quality` is a **field on both tables, not a tag.**

## Why

Two independent arguments land on the same layout.

**Raw preservation has to be demonstrable, not asserted.** The M1 verify criterion is explicit
that "raw preserved unchanged" is shown by query. Option 1 fails it: encode `STEADY_STATE` to
`1` at ingest and the only unmodified copy of that reading is a gitignored CSV. That is a thin
answer under questioning, and it also destroys the evidence needed later to defend the encoding
itself. Get raw in unchanged; transform downstream.

**The type constraint is per column, not per table.** Once that is stated plainly, the split
follows immediately and Option 2's nulls and Option 3's pivot both look like work done to avoid
a constraint that a second table simply satisfies. Option 3 additionally requires transforming
at ingest — the same objection as Option 1 in a different costume — and its sparsity is not
incidental: signals inside one source genuinely do not share a sample rate.

On `quality` as a field rather than a tag: **tags carry identity, fields carry observation.**
Quality describes one reading at one instant, not what the series *is*. As a tag it makes series
membership depend on data content, so a single physical sensor fragments into a GOOD series and
a BAD series and any continuous read of it silently splits. The v3-specific version of this
argument matters, because the familiar one is wrong here: with no per-series index there is no
index to explode, but tags are the sort/partition key, and keying on a data-dependent value
fragments storage layout for no query benefit.

Cardinality is quantified rather than hand-waved: 150 series, growing linearly in experiment
count only. It is not a constraint at this scale, and saying so with the number is stronger than
treating it as a looming risk.

## Consequences

- **Cross-table queries need a union.** Rare in practice: `process_state` is used to *window*
  numeric data, and that windowing happens in the analysis layer rather than in one SQL
  statement. Where it does matter, it is a `UNION ALL` over two tables with identical tag sets.
- **Two ingest paths**, dispatched on whether the signal is categorical. Trivial, but it is a
  branch that must be driven by a declared list of categorical signals, not by "does this parse
  as a float" — the latter would silently reroute a corrupt numeric reading into the state
  table.
- **Adding a signal is data, not migration.** A new signal is a new tag value in an existing
  table, unless it is a new *categorical* signal, which is still just a new tag value in
  `readings_state`.
- **`quality` as a dense field is 99.94% redundant.** Accepted for now because it makes
  exclusion a `WHERE` clause on the same row, which is exactly what deliverable C asks for. The
  alternative — a sparse exceptions table where absence means good — is registered as U-09 and
  deferred to M3, because "no row" must then unambiguously mean *good* and never *no data*.
- **Raw preservation is now provable by query**, which is what M1 requires, and the raw CSV plus
  its committed SHA-256 becomes a second line of defence rather than the only one.
- The measurement/tag/field split is settled; **what is *not* settled here** is where processed
  values, pipeline quality verdicts and exclusion reasons live (U-09). That is a separate axis
  from this one and belongs to M3.

## Assumptions relied on

A-01, A-02

## Related

ADR-0004 (InfluxDB 3 Core, SQL), ADR-0005 (Postgres for experiment metadata),
ADR-0007 (duplicate resolution and ingest idempotency).

## Defense

The data is long format, so experiment, source and signal are tags and the reading is the field
— that's 150 series across six experiments, and it grows linearly in experiments only, so
cardinality isn't a constraint at this scale. The one thing that forced a real decision is that
two of the 25 signals are categorical strings and a column's type is fixed on first write, so a
single `value` field can't hold both. I considered encoding the states as integers, and rejected
it: that transforms data at ingest, which means the database never holds what the sensor
actually reported, and it invents an ordering where `mean()` over a state column returns a
number that looks fine and means nothing. So there are two tables split by value type, and raw
preservation is something I can show you with a query rather than assert. Quality is a field,
not a tag — it describes a reading, not a series, and as a tag it would split one sensor into
separate series whenever the flag changed.
