# ADR-0014 — Post-ingest profiling: what is measured, where it runs, and what this engine gets wrong

Status: Accepted
Milestone: M2.5   Deliverable: C, D (added scope)   Date: 2026-11-23

## Context

ADR-0010 settled that everything ingestion does not destroy is measured after ingestion, in the
database, and that the profile only measures: no verdict words, no thresholds that label a
reading (MISTAKES.md C-01, C-02). This ADR records how that was built: what is measured, which
part runs in SQL and which in Python, and the four ways InfluxDB 3 Core 3.11.2 (DataFusion 51)
gave a wrong or unstable number during calibration. Each of those was found by comparing the
SQL against a plain `SELECT` pull measured in Python (the standing "sample before scale" rule),
not by reading documentation (MISTAKES.md E-06).

The command is `python -m scripts.post_ingest_profile`. It writes `post_ingest_profile.json`
(contract: `contracts/post_ingest_profile.schema.json`), `post_ingest_profile.md` (the same
numbers as tables), and `post_ingest_profile_span_probe.txt` only if the server refuses the
full-span query. It never writes to InfluxDB.

## Decision

| # | Decision | Rejected |
|---|---|---|
| 1 | Every profiling query is bounded to one experiment's window, start included and end excluded, taken from `experiments.json`. | One query over March to June. |
| 2 | One extra query, the span probe: `COUNT(*)` over the earliest start to the latest end. It is recorded whether the server answers or refuses. A refusal's message goes to its own `.txt` file and never changes the exit code. | Assume the roughly 72-hour limit; raise the file limit blindly. |
| 3 | SQL does the per-value measures: range, spacing, gaps, runs, step-to-step change, residuals, ratios, differences. | Pandas over the whole table (E-01). |
| 4 | Python does the fitted lines (correlation, slope, intercept, R squared) and the lag, on pairs pulled for one experiment (at most about 7,200 rows per series). Sums use `math.fsum`. | SQL `CORR` and `REGR_*`: see engine quirk 4. |
| 5 | Percentiles are computed exactly in SQL by weighting the two neighbouring ranks in double precision (`percentile_sql`). | `PERCENTILE_CONT` (engine quirk 3); `approx_percentile_cont` (not exact, not stable). |
| 6 | Series are paired on the exact same instant. `instants_matched` counts pairs. `instants_unmatched` counts points of the first-named signal (power, outlet CO2, current, pressure drop) that found no partner. | Nearest-neighbour join: hides clock drift. |
| 7 | Nominal interval and documented range are declared tables in `pipeline/signals.py`, copied from the data dictionary. A unit test checks they cover the 23 numeric pairs and none of the 2 text pairs. | Parse the dictionary at run time. |
| 8 | Gaps are measured, not judged: intervals over 2 and over 10 times nominal, seconds spent in over-2x intervals, the five longest. Not applied to on-change signals, which have no nominal rate (C-01). | One threshold that labels readings. |
| 9 | The step-to-step check is named `differences`, not "noise", because the verdict-word search includes that word. | Call it noise. |
| 10 | Floats are rounded to 9 significant digits and all lists are sorted, so a re-run is byte-identical except the `timing` block. | Raw floats. |
| 11 | Files are written only at the end. A failed query exits 3 and writes nothing. Exit 2 means refused: database missing (never created), no readings, experiments file unreadable, server not configured or not reachable. | Write as you go. |

### Definitions that were not spelled out

- `stddev` is the sample standard deviation (n - 1); one value gives null.
- Percentiles use linear interpolation at position `p * (n - 1)`, the same as NumPy's default.
- Runs and step-to-step change look only at points that hold a value. A point with no value
  neither breaks a run nor starts one; it is counted in `points_without_value`. Intervals count
  every point, with or without a value.
- `seconds_in_over_2x` is the whole length of each over-2x interval, not the excess.
- `relative_residual_*` is the absolute residual divided by power, for power above zero.
- The lag search shifts the setpoint later by 0 to 60 whole seconds; the reading of the current
  at `t` is paired with the setpoint at exactly `t - k`. Ties go to the smaller shift.
- `-0.0` is treated as `0.0` before any comparison with a documented bound (engine quirk 2).

### Engine quirks found by calibration

1. **`COUNT(*) FILTER (WHERE condition)` counts a row whose condition is NULL.** A missing value
   or the first interval of a series was counted as "below the bound" or "over 2x nominal".
   Found as `over_2x` one too high on almost every series and `below` 20 against 19. All
   conditional counts use `COUNT(CASE WHEN condition THEN 1 END)`.
2. **`-0.0` sorts before `0.0` and is not equal to it.** `-0.0 < 0` is true and `-0.0 = 0` is
   false. The real file has one `-0.00` current reading. It would have been counted below the
   documented minimum of 0, which counts a sign, not a value. Comparisons use `value + 0.0`.
3. **`PERCENTILE_CONT` interpolates at roughly float32 precision.** 0.95 of `0.0, 0.39, 0.41`
   gives 0.40799998, not 0.408; the error grows with the gap between neighbouring values and
   showed in the 8th digit of p95 on real series. `MEDIAN` is not affected. Percentiles are
   computed by `percentile_sql` instead and checked against a Python reference to the 9th digit.
4. **Parallel sums differ in the last bits between runs.** A fitted intercept is a small
   difference of large numbers (about 0.001 from terms near 30,000), so the 9th digit of
   `regr_intercept` changed between two runs on the same data (two of 24 relationships). That
   would break the byte-identical re-run. Fits are done in Python with exactly rounded sums.
   Other SQL aggregates (mean, standard deviation) also vary in the last bits, but by about
   1e-15 relative, far below the 9th digit, and three real runs gave identical output.

## Why

The profile has one job: give Sebastian numbers he can cite and a later milestone numbers it can
build on, without any of them being a decision. So everything is a count, a distribution or a
sample, and every number that can be checked independently was: all 150 series and 24
relationships on the real data were recomputed in Python from plain `SELECT` pulls and agree to
the 9th digit (0 mismatches over 6 experiments).

Decision 4 moves one measure group out of SQL. ADR-0010 and the plan said relationships run in
SQL and only the lag is pulled. That held for everything except the fits, where the engine's
last-bit instability showed through. The plan already allowed a per-measure fallback to a pull
(M2.5 decision 4) if a window query did not work on this server, with the output shape unchanged.
This is that fallback, applied to correlation, slope, intercept and R squared; the residuals,
ratios and differences stay in SQL.

## Consequences

- The profile describes **stored data**, not source data (ADR-0010). A value-level ingest bug
  would be profiled faithfully, not caught. The count reconciliation in M2 guards row counts only.
- **U-05 is narrowed.** The span probe asked for all numeric points from 2026-03-02T08:00Z to
  2026-06-15T08:00Z (105 days) in one query and the server answered: 519,906, equal to the sum of
  the six per-experiment counts. So on this data the roughly 72-hour limit did not stop a
  105-day query. Why it did not was not investigated; ADR-0004 ties the limit to a file count
  and block size, so a data set with many more files may behave differently. U-05 stays open only
  for Grafana's wide time picker (M6) and the overlay (M5).
- A full real run takes about 16 s and 188 queries, native Windows, local Docker.
- The four engine quirks are pinned by unit tests that read the SQL text (`FILTER (` and
  `PERCENTILE_CONT(` must not appear, signed zero is normalised), and the two that change numbers
  are also exercised by the fixture end to end. A server upgrade that fixes one of them will not
  break the profile; it only makes the workaround unnecessary.
- M3 reads this profile for its per-signal rules. The profile does not suggest any.

## Assumptions relied on

U-05 (narrowed here, still open for M6); A-02 (Core is adequate).

## Related

ADR-0004 (Core, SQL, the 72-hour claim), ADR-0006 (schema), ADR-0010 (where profiling runs),
ADR-0013 (ingestion; the empty-value and signed-zero points it stores). MISTAKES.md C-01, C-02,
E-01, E-06.

## Defense

"The profile is a read-only report of what ingest stored. Every query is one experiment's
two-hour window, so the roughly 72-hour limit never applies, and I measured it once anyway with
a single 105-day query: it was answered. Anything the database can aggregate is aggregated
there; anything the engine got wrong, I found by recomputing it from a plain pull and fixed in
a way a test would catch: two of the aggregates it offers returned wrong or unstable digits on
this version, so percentiles are computed by rank and the fitted lines in Python with exact
sums. A second run gives the same bytes. And nothing in the output is a verdict: a voltage of
412 against a documented maximum of 130 is a count, and what to do about it is M3."
