# Debrief Question Bank & Scoring Rubric

For use after the 60-minute working session. Ask questions from here in whatever order the
candidate's presentation makes natural — don't just read down the list. Push back on
answers; don't accept a claim just because it sounds confident. The goal is to find out
what they actually understand vs. what pattern-matches to a plausible-sounding answer.

---

## Data modeling (InfluxDB)

- Why did you choose this measurement/tag/field split? Walk me through one row end to end.
- Why is `experiment_id` a tag and not a field? (Or: why did you make it a field?) What
  breaks if you got that backwards?
- How do you handle high tag cardinality if this scaled to hundreds of experiments and
  thousands of sensors?
- Where do raw values live in your model, and how do you guarantee they're never mutated
  by the processing pipeline?
- How would you model the fact that `quality` applies per-value, not per-signal?
- What happens to your schema if a new signal shows up next month that you didn't design for?

## Ingestion & robustness

- Walk me through what happens if you run your ingestion script twice on the same file.
  Is it idempotent? How do you know?
- What happens when data arrives late — after you've already computed and published a KPI
  for that time window?
- The file has out-of-order rows and duplicate timestamps. Which did you actually handle,
  and how did you verify it worked rather than just assuming your code was right?
- What would you change if this had to ingest from a live OPC-UA subscription instead of a
  static CSV?
- How would this scale to 100x more sensors? What's the first thing that breaks?
- What happens if a PLC config change silently changes a signal's unit or tag name
  mid-stream? (Did they notice the EXP_004 air_flow unit change, and if so, how?)

## Data quality & cleaning

- Which signals did you interpolate across gaps, and which did you refuse to? What's the
  actual rule, not just "it felt right"?
- What would you do with a 30-minute gap? Does your answer change if it's in the middle of
  a load-change transient vs. steady state?
- How do you detect a stuck sensor, given that every individual value it reports is
  individually plausible?
- How do you tell a real outlier from a real (but sudden) process event? What's your
  false-positive risk?
- Why does a pH signal deserve different handling than a plant alarm/state signal, or an
  integrated energy total? Be specific — not just "they're different types of data."
- Can your filter or smoothing choice hide a real transient? How would you know if it did?
- How do you handle `UNCERTAIN` differently from `BAD`? Did you actually implement that
  distinction, or just filter on `quality == 'GOOD'`?
- Where does the raw noisy value go once you've cleaned/filtered a signal? Is it still
  recoverable?
- EXP_006 has zero BAD/UNCERTAIN flags and looks like the best experiment on a naive
  average. Did you catch that, and if not, walk through how you'd catch it now.

## Experiment analysis & causal reasoning

- Which experiment actually captures the most CO2 per unit energy? Defend the number.
- How would you check whether Experiment A is *really* better than Experiment B, versus
  the difference being noise, a data quality artifact, or a confound (e.g. different
  ambient conditions)?
- Which of your conclusions are causal, and which are just correlations you're reading as
  causal?
- What metadata would you need but don't have, to make a clean comparison? (Missing
  operator/sorbent_batch/notes fields should come up here.)
- Air flow and capture rate vs. capture efficiency point in different directions in this
  data — which one matters for the question "should we run more air through it"? Does the
  answer depend on what you're optimizing for (total CO2/day vs. CO2 per m3 of air)?
- How would `experiment_time` alignment change your answer versus comparing on wall-clock
  time?

## Visualization / Grafana

- What would a scientist actually do with this dashboard on day one? Walk me through a
  realistic session.
- Why did you choose these panels and not others? What did you deliberately leave out?
- How does your dashboard show a scientist when a seemingly great result shouldn't be
  trusted? Would EXP_006's inflated efficiency have been visible from your dashboard alone,
  before you dug into the raw data?
- What's the difference between showing data quality *for its own sake* vs. making it
  actionable inside the same view where someone is looking at a KPI?

## ML as an extension (only after the deterministic pipeline is solid)

For each proposal, push: **what problem does this solve that a rule or a simple statistic
can't?** Require a baseline before anything more complex, and require they've thought about
failure modes (what happens when the model is wrong and nobody notices).

- Anomaly detection — how is this different from the threshold/variance checks you already
  built? When would a learned model actually catch something a rule wouldn't?
- Soft sensors — which signal here would actually benefit from this? What's the fallback
  when the soft sensor's own inputs are degraded?
- Predictive maintenance — what's the target label? Where would training data even come
  from with six experiments?
- Time-to-target prediction — concretely, time to what target? Is this better than a
  simple extrapolation from the current lag/time-constant?
- Experiment outcome prediction — with six experiments total, is there remotely enough
  data? What would change your mind about whether this is premature?
- Forecasting (solar power, short-term CO2 production, a degradation KPI) — what decision
  does the forecast actually inform, and does that decision need a forecast or just a
  threshold on the current trend?

If they jump straight to a sophisticated model without discussing a baseline, push on that
directly.

---

## Scoring

Score 1–10 in each category. For every weakness found, classify it as one of:

- **Critical error** — wrong in a way that would mislead a real scientist (e.g. reporting
  EXP_006 as the best performer without flagging why that's unreliable; treating raw and
  processed values as interchangeable).
- **Acceptable for a 60-minute prototype** — a real gap, but the kind any reasonable
  engineer leaves for later given the time constraint (e.g. Grafana dashboard is a design
  doc, not a running instance; only some signals got type-specific cleaning treatment).
- **Must fix before production** — not wrong today, but would need to be addressed before
  this touched real plant data (e.g. no idempotency handling, no schema versioning story,
  hardcoded thresholds with no operator override).

### Categories

1. **Data modeling** — InfluxDB schema quality, tag/field reasoning, cardinality awareness.
2. **Time-series understanding** — sampling rates, alignment, windowing, resampling choices.
3. **Data quality** — did they find the actual defects (or a reasonable subset), and handle
   them sensibly rather than just dropping anything that looked odd?
4. **Python / data processing** — code correctness, clarity, reasonable use of the time
   available.
5. **Physical reasoning** — did they sanity-check results against physics (P=UI, CO2 mass
   balance, plausible ranges) rather than trusting numbers at face value?
6. **Experiment analysis** — real, defensible findings vs. surface-level plotting.
7. **Grafana / visualization** — does the design (or build) actually serve a scientist's
   workflow?
8. **Software architecture** — structure, separation of raw/processed/quality, extensibility.
9. **Trade-off handling** — explicit prioritization under time pressure, clear reasoning for
   what got cut and why.
10. **Technical communication** — can they defend decisions under pushback, and update their
    position when shown a flaw, rather than just re-asserting the original answer?

Weight #3 (data quality) and #9 (trade-offs) most heavily — they're the actual point of this
exercise, more than any specific technology choice.
