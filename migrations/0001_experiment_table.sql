-- The experiment table (ADR-0005, ADR-0012).
--
-- experiment_id/start_time/end_time/duration_s are structural identity, set once at load
-- time and never hand-corrected — they stay NOT NULL. Every other column is one of the six
-- the provenance trigger (0002) protects from a routine loader re-run silently overwriting a
-- manual correction, and at least one real experiment has each of them null
-- (EXP_003.notes, EXP_005.sorbent_batch, EXP_006.operator) — nullable rather than defaulted,
-- so the load preserves that.

CREATE TABLE experiment (
    experiment_id               text PRIMARY KEY,
    start_time                  timestamptz NOT NULL,
    end_time                    timestamptz NOT NULL,
    duration_s                  integer NOT NULL,
    current_setpoint_nominal_a  double precision,
    air_flow_nominal_m3h        double precision,
    solvent_flow_nominal_lmin   double precision,
    operator                    text,
    sorbent_batch               text,
    notes                       text
);
