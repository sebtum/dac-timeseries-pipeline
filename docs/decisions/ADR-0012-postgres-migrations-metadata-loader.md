# ADR-0012 — Postgres migrations, and an `experiments.json` loader with per-field provenance

Status: Accepted
Milestone: M1   Deliverable: A, F   Date: 2026-08-30

## Context

ADR-0005 chose PostgreSQL for experiment metadata and left two things for M1: how the schema
arrives, and how `experiments.json` gets into it. ADR-0009 already narrowed the first
(exception 3) and `ROADMAP.md:94` requires "Postgres metadata schema migration runs clean" as a
CI check, so a migration path is required rather than optional. U-14 recorded the remainder.

Facts that constrain the choice:

- **`docker-entrypoint-initdb.d/*.sql` runs only against an empty data volume** and silently
  no-ops otherwise. Any schema change after M1 would appear to be applied and would not be. That
  is the class of silent failure this whole project is about, which is why ADR-0009 excluded it.
- **PostgreSQL has transactional DDL.** A migration that fails mid-way rolls back completely,
  leaving no half-applied schema. This is a property of Postgres specifically, not of migrations
  in general — it is what makes a small hand-rolled runner safe here.
- **The metadata is corrigible, and that is the entire reason it is in Postgres.** ADR-0005:
  `EXP_003` has a null `notes`, `EXP_005` a null `sorbent_batch`, `EXP_006` a null `operator`, and
  those get filled in later. `experiments.json` stays the immutable source of truth under
  `data/raw/`; **Postgres is where corrections land.**
- The dataset is six rows and ten columns. Nothing here is a scale problem.

## Options considered

### Schema delivery

#### Option 1 — `docker-entrypoint-initdb.d` init SQL
Advantages: zero code; runs automatically on container start; already supported by the image.
Caveats: runs only on an empty volume and silently does nothing otherwise, so it cannot carry any
post-M1 change; fails `ROADMAP.md:94` outright. Excluded by ADR-0009 exception 3.

#### Option 2 — A dedicated migration tool (Alembic, sqlx, Flyway)
Advantages: battle-tested; handles ordering, checksums, locking and rollback semantics; nobody has
to defend the framework itself in review.
Caveats: Alembic pulls SQLAlchemy for a six-row schema with no ORM anywhere else in the project;
its autogenerate flow expects models this project does not have; a second configuration surface
and a second mental model for what is currently three tables.

#### Option 3 — Versioned SQL files run by a small Python runner
Advantages: the migrations *are* plain SQL, so they are reviewable and portable and say exactly
what they do; the runner is ~50 lines; applied versions tracked in a table so re-runs are no-ops;
one transaction per migration is genuinely safe on Postgres; CI runs it against a clean database
to satisfy `ROADMAP.md:94`.
Caveats: a hand-rolled framework is a thing to maintain and to defend; three properties have to be
built deliberately or it is worse than a real tool (ordering, an advisory lock, a checksum).

### Protecting corrections from the loader

#### Option A — Plain upsert (`SET col = EXCLUDED.col`)
Advantages: one statement; obviously idempotent in the naive sense.
Caveats: **destroys the capability ADR-0005 was written to provide.** `experiments.json` still says
`"sorbent_batch": null` for `EXP_005`; a re-run writes that null over the correction. It happens on
a routine re-run, which is exactly when nobody is watching.

#### Option B — Null-guarded upsert (`COALESCE(EXCLUDED.col, e.col)`)
Advantages: one keyword; fixes the null case completely; no schema change.
Caveats: only protects against nulls. If the file holds a *wrong non-null* value and someone has
corrected it in Postgres, the next run overwrites the correction and Option B is silent about it.

#### Option C — Per-field provenance
Advantages: distinguishes "loader-owned" from "manually corrected" per field, so it protects
against both the null case and the wrong-non-null case; yields an audit trail (who, when) for free;
makes "which values are trusted human input" a queryable fact rather than folklore.
Caveats: an extra table, a function and a trigger for six rows; and it is only as good as the
discipline that records provenance — a hand-maintained provenance row that someone forgets
reproduces the original bug behind more machinery.

## Decision

**Option 3 for schema, Option C for the loader.**

Versioned SQL files in `migrations/`, applied by a small Python runner that tracks applied versions
in a table and wraps each migration in a transaction. It stays deliberately minimal; **the trigger
for replacing it with Alembic is the first migration that needs data backfill in Python, branching,
or a down-migration** — anything beyond ordered forward-only SQL.

`experiments.json` is **bootstrap/reference data, not schema state**, loaded by a separate
idempotent loader keyed on `experiment_id` with upsert semantics and **no hard deletes** — a row
disappearing from the JSON never removes a row that time-series data references; explicit
deactivation is used if removal semantics are ever needed.

Provenance is recorded **by trigger, never by hand**:

```sql
CREATE TYPE field_source AS ENUM ('loader', 'manual_override');

CREATE TABLE experiment_field_source (
    experiment_id text NOT NULL REFERENCES experiment (experiment_id) ON DELETE CASCADE,
    field_name    text NOT NULL,
    source        field_source NOT NULL,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    text        NOT NULL DEFAULT current_user,
    PRIMARY KEY (experiment_id, field_name)
);

CREATE FUNCTION is_manual(p_exp text, p_field text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM experiment_field_source
        WHERE experiment_id = p_exp AND field_name = p_field
          AND source = 'manual_override'
    );
$$;

CREATE FUNCTION record_experiment_provenance() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    src field_source := CASE
        WHEN current_setting('app.actor', true) = 'loader' THEN 'loader'
        ELSE 'manual_override'          -- unset session variable ⇒ protect (fail safe)
    END;
    f text;
BEGIN
    FOREACH f IN ARRAY ARRAY['operator', 'sorbent_batch', 'notes',
                             'current_setpoint_nominal_a', 'air_flow_nominal_m3h',
                             'solvent_flow_nominal_lmin']
    LOOP
        IF to_jsonb(NEW) -> f IS DISTINCT FROM to_jsonb(OLD) -> f THEN
            INSERT INTO experiment_field_source (experiment_id, field_name, source)
            VALUES (NEW.experiment_id, f, src)
            ON CONFLICT (experiment_id, field_name) DO UPDATE
                SET source = EXCLUDED.source, updated_at = now(), updated_by = current_user;
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER experiment_provenance
AFTER UPDATE ON experiment
FOR EACH ROW EXECUTE FUNCTION record_experiment_provenance();
```

The loader sets `SET LOCAL app.actor = 'loader'` and then upserts with one `CASE` per correctable
column:

```sql
ON CONFLICT (experiment_id) DO UPDATE SET
    operator = CASE WHEN is_manual(e.experiment_id, 'operator')
                    THEN e.operator ELSE EXCLUDED.operator END,
    ...
```

## Why

**Init SQL is disqualified by a property, not a preference.** It stops applying the moment there is
data in the volume, and it does so silently. Everything else about it is convenient and irrelevant.

**A hand-rolled runner beats Alembic *here* because the schema is plain SQL and stays plain SQL.**
Alembic's value is autogenerate and rich revision graphs, both of which assume an ORM and a schema
that churns. This project has three tables, no ORM, and forward-only migrations. Pulling SQLAlchemy
in to manage that would be a larger dependency than the thing it manages. The honest counter is
that hand-rolled migration frameworks are a classic mistake, which is why the replacement trigger
is written into this ADR rather than left to judgement.

**Postgres's transactional DDL is what makes the small runner defensible.** On MySQL the same
design would leave half-applied schemas after a failure and would need real tooling. It is worth
saying that out loud, because "I wrote my own migration runner" invites the question and
"transactional DDL means a failed migration leaves no trace" is the answer.

**Per-field provenance over the `COALESCE` trick, because the cheap fix only covers half the
failure.** The null case is the one that is obvious from the data; the dangerous one is a *wrong
non-null* value in the file overwriting a human correction, which `COALESCE` does not touch. Since
ADR-0005's whole justification is "metadata is corrigible and Postgres is where corrections live",
a loader that can silently revert a correction under any circumstance undermines the ADR that
created it.

**The trigger is the load-bearing part, not polish.** Provenance that must be inserted by hand
alongside each correction *will* be forgotten, and the next loader run then reverts the correction
— the original bug, now with more machinery in front of it. Recording it automatically, with an
unset session variable defaulting to `manual_override`, makes the safe outcome the default and the
unsafe one impossible to reach by omission.

**`to_jsonb(NEW) -> f IS DISTINCT FROM to_jsonb(OLD) -> f`** is used rather than per-column
comparison because `IS DISTINCT FROM` handles null-to-value and value-to-null correctly, where `<>`
would return null and skip the row.

## Consequences

- **The runner must build three things or it is worse than a real tool**: deterministic ordering,
  a Postgres advisory lock so two concurrent runners cannot race, and a checksum per applied
  migration so a file edited after being applied is detected instead of silently skipped.
- **Once a field is `manual_override`, the loader can never update it again** — even from a
  genuinely corrected `experiments.json`. This is the accepted cost. The documented escape hatch
  is `DELETE FROM experiment_field_source WHERE experiment_id = … AND field_name = …`, which hands
  the field back to the loader.
- **A correction made with the session variable accidentally set to `'loader'` is recorded as
  loader-owned** and will be reverted on the next run. Minor, and the reason the loader is the only
  code path that sets it.
- **Provenance covers only the columns named in the trigger's array.** Adding a correctable column
  means adding it there too, or it is silently unprotected. That coupling is the price of a static
  list and should be covered by a test.
- **CI can assert "migration runs clean"** against a throwaway database, which is what
  `ROADMAP.md:94` asks for, plus a re-run assertion that the second application is a no-op.
- **Nullable columns are required** so `EXP_003.notes`, `EXP_005.sorbent_batch` and
  `EXP_006.operator` survive the load as NULL rather than being defaulted — already an M1 verify
  criterion.
- ADR-0005's remaining M1 question — which metadata fields, if any, are duplicated into InfluxDB
  tags — is **answered as "none"** by ADR-0011's tiering design: pinned ranges reference experiment
  metadata through Postgres, so no nominal parameter needs to become a tag and the 150-series
  cardinality from ADR-0006 is unchanged.

## Assumptions relied on

A-01

## Related

ADR-0005 (Postgres for experiment metadata — this resolves its "left open for M1"), ADR-0009
(provisioning as code, exception 3), ADR-0011 (Postgres as the producer of pinned interval
metadata). Resolves U-14.

## Defense

Schema changes go through versioned SQL files applied by a small Python runner that records what it
has applied — not the container's `initdb` directory, because that only runs on an empty volume and
silently stops applying the moment there is data, which is the worst possible failure mode for a
schema. I kept the runner hand-rolled rather than pulling in Alembic because the schema is three
tables of plain SQL with no ORM behind it, and Postgres has transactional DDL so a failed migration
leaves nothing half-applied; the trigger for switching to a real tool is the first migration that
needs branching or a Python backfill. The part I'd actually highlight is the loader. `experiments.json`
has nulls in it — three of the six runs are missing a field — and Postgres is specifically where
someone fills those in later, so a plain upsert would write the file's null straight back over the
correction on the next routine run. I record provenance per field with a trigger, so a value a human
changed is marked as a manual override and the loader skips it. I used provenance rather than just
coalescing nulls because coalescing only protects against nulls, and the case that actually worries
me is the file holding a wrong non-null value that overwrites someone's correction silently.
