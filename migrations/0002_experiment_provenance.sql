-- Per-field provenance for the experiment table (ADR-0012, Option C).
--
-- Distinguishes "loader-owned" from "manually corrected" per correctable field, so the
-- experiments.json loader (T7) can skip a field a human has since corrected instead of
-- silently reverting it on the next routine run. Recorded by trigger, never by hand: an
-- unset `app.actor` session variable defaults to 'manual_override' (fail-safe), and only the
-- loader sets it to 'loader'.
--
-- `IS DISTINCT FROM` (not `<>`) is used per-field below because `<>` returns NULL, not true,
-- when either side is NULL, which would silently skip exactly the null-to-value and
-- value-to-null transitions this table exists to catch.

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

-- The array below is the entire scope of what this table protects (ADR-0012
-- consequences: "provenance covers only the columns named in the trigger's array"). Adding a
-- correctable column to 0001 (or a later migration) means adding it here too, or it is
-- silently unprotected — T7 tests this coupling directly against `information_schema`.
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
