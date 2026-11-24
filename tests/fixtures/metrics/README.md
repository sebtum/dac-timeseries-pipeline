# Metrics fixture

One experiment, `EXP_001`, 2026-05-04T08:00:00Z to 08:10:00Z (600 s), built by
`make_fixture.py` (stdlib only, no randomness, no import from `pipeline/`). It is the input of
`tests/e2e/test_metrics_cli.py`: ingest, clean, then `python -m scripts.metrics`. Every expected
number in that test is a literal taken from this file, derived by hand from the construction
below and cross-checked with the plain arithmetic script at the end (which imports nothing from
`pipeline/`). `readings.sha256` is the SHA-256 of `readings.csv`; git must not touch line endings
(`.gitattributes`: `tests/fixtures/** -text`).

## Construction

Noise is a fixed alternation of plus and minus half the signal's declared normal step
(`pipeline/cleaning_policy.py`), plus at an even position. Position means the second for 1 Hz
signals and the reading index for slower ones (a 0.5 Hz signal sampled at even seconds would
otherwise always be plus, a constant that cleaning calls a flatline). So every step equals the
normal step: nothing is flat, nothing is a spike, and cleaning accepts every normal reading.
`+k` is k seconds after 08:00:00.

| Signal | Rate | Values | Planted |
|---|---|---|---|
| voltage | 1 Hz | 100 +- 0.075 V | no rows +300..+310 (589 rows) |
| current | 1 Hz | 150 +- 0.15 A | no rows +300..+310, +450, +451; BAD at +100 (587 rows) |
| power | 1 Hz | voltage x current, exact decimal | +250 W at +200; no rows +300..+310 (589 rows) |
| co2_in_ppm | 0.5 Hz, even seconds | 420 +- 0.55 ppm | BAD at +500, +502 (300 rows) |
| co2_out_ppm | 0.5 Hz, even seconds | 105 +- 0.4 ppm | UNCERTAIN at +400 (300 rows) |
| air_flow | 1 Hz | 1200 +- 3.775 m3/h | none (600 rows) |
| ambient_temperature | whole minutes | 15 +- 0.065 degC | no rows +300, +360 (8 rows) |
| ambient_pressure | whole minutes | 1013.25 +- 0.03 hPa | no rows +300, +360 (8 rows) |
| process_state | on change | STARTUP at 0, STEADY_STATE at +60 | 2 rows |

Total 589 + 587 + 589 + 300 + 300 + 600 + 8 + 8 + 2 = 2983 rows. Cleaning (checked) excludes
exactly four: current +100 (flag_bad), co2_out +400 (flag_uncertain), co2_in +500 and +502
(flag_bad); 2979 accepted.

Exact values used below: voltage 100.075 V at even seconds and 99.925 V at odd seconds; current
150.15 A and 149.85 A. So voltage x current is

- even second: 100.075 x 150.15 = 15026.26125 W
- odd second: 99.925 x 149.85 = 14973.76125 W
- mean of the two: 15000.01125 W; difference 52.5 W.

## Power (S4.1, S4.2)

- `power_computed` needs voltage and current both accepted. Voltage has 589 instants; remove
  the three where current is not accepted (+100 BAD, +450, +451): **586 rows**. None at +100,
  +300..+310, +450, +451.
- `power_residual` needs power, voltage and current accepted: power has 589 instants, the same
  three are removed: **586 rows**. Every residual is 0 (to float rounding, about 1e-12) except
  +200: 250 W.
- power_check: **586 compared**. Tolerance at +200: 0.01 x 15026.26125 + 10 = 160.26 W, and 250
  exceeds it; every other residual is about 0. So **585 within tolerance** (fraction
  585/586 = 0.998293515), **max |residual| 250 W**, median about 0, p95 about 0.

## Energy (S4.4, S4.5)

Trapezoid rule over bridged spacings (a spacing of at most 2 s is bridged).

- `power_computed` instants: 0..99, 101..299, 311..449, 452..599. Bridged spacings: 99 one-second
  spacings in 0..99, one 2 s spacing 99 -> 101, 198 in 101..299, 138 in 311..449, 147 in
  452..599. Not bridged: 299 -> 311 (12 s) and 449 -> 452 (3 s). Covered seconds
  99 + 2 + 198 + 138 + 147 = **584**, coverage 584/600 = 0.973333, status complete.
- Each one-second spacing joins an even and an odd second, so its area is 15000.01125 W s. The
  2 s spacing joins two odd seconds, so its area is 2 x 14973.76125 = 29947.5225 W s. There are
  582 one-second spacings (584 - 2). Integral = 582 x 15000.01125 + 29947.5225
  = 8730006.5475 + 29947.5225 = 8759954.07 W s.
- **energy_kwh = 8759954.07 / 3.6e6 = 2.433320575 kWh.**
- **mean_power_kw = 2.433320575 / (584 / 3600) = 14.99992135 kW.**
- Logged power exists at 0..299 and 311..599 (589 instants, all accepted): covered 299 + 288 =
  **587** s, coverage 587/600 = 0.978333. All 587 spacings are one second, so the integral is
  587 x 15000.01125 + 250 (the +250 W at +200 adds 125 W s from each of its two spacings) =
  8805006.60375 + 250 = 8805256.60375 W s; **energy_logged_kwh = 2.445904612 kWh**.
- Overlap of the two covered sets: [0, 299], [311, 449], [452, 599] = 584 s (the logged power
  at +450 and +451 lies outside, where computed power has no cover). Computed over the overlap:
  8759954.07 W s. Logged over the overlap: the logged series has a point at +100 (value
  15026.26125) where the computed series has none (it is interpolated between 99 and 101, both
  14973.76125), so the logged integral over 99..101 is 30000.0225 against 29947.5225: +52.5 W s.
  Plus the +250 at +200. Logged over the overlap = 8759954.07 + 302.5 = 8760256.57 W s.
- **energy_relative_difference = 302.5 / 8759954.07 = 3.4532e-05** (3.453214453e-05), coverage
  584/600. Below the 0.01 limit, so `energy_agreement` passes.

## Capture efficiency (S4.7)

- co2_in accepted at 298 of the 300 even seconds (not +500, +502); co2_out at 299 (not +400).
  Both accepted: 300 - 3 = **297 instants** (none at +400, +500, +502).
- Value `(in - out) / in`. At an even reading index (second 0, 4, 8, ...): (420.55 - 105.4) /
  420.55 = 0.749375817; at an odd index (2, 6, ...): (419.45 - 104.6) / 419.45 = 0.750625820.
  148 of the 297 instants have an even index, 149 an odd one. Sum = 222.7508681, **mean =
  0.7500029228**. No value is at or below 0, so `at_or_below_zero` is 0.
- Coverage (spacing at most 4 s bridged): 0..398 contiguous (398 s), 398 -> 402 is 4 s and is
  bridged, 402..498 (96 s), so 0..498 = 498 s; 498 -> 504 is 6 s, not bridged; 504..598 = 94 s.
  Covered **592** s, coverage 592/600 = 0.986667, complete.

## Capture rate, CO2 captured and inlet (S4.9)

- The rate at instant t is `air_flow x (in - out) x 1e-6 x p x M / (R x T)` with p = ambient
  pressure x 100 Pa, T = ambient temperature + 273.15 K, M = 0.04401, R = 8.314462618, using the
  latest ambient reading at or before t if it is at most 120 s old.
- Ambient readings: 0, 60, 120, 180, 240, then 420, 480, 540. For t between 240 and 360 the
  latest reading is +240, age t - 240 <= 120, used (+360 has age 120: used). From +362 to +418
  the latest is still +240 with age 122 s or more: no value. From +420 the reading at +420 is
  used.
- Instants with both CO2 readings accepted: 297. Remove the even seconds +362, +364, ..., +418
  (29 of them), of which +400 is already outside the 297: 297 - 28 = **269 capture_rate rows**.
  The scenario text S4.9 says 268; that number counts +400 twice (once for the UNCERTAIN co2_out
  and once for the missing ambient). Written as 269 here and in the e2e test (see the T3 report,
  Problems). The series is 0..360 (181 instants), 420..498 (40), 504..598 (48).
- Covered seconds (4 s bridged): [0, 360] 360 s, [420, 498] 78 s, [504, 598] 94 s = **532**,
  coverage 532/600 = 0.886667, status partial.
- Air flow at even seconds is 1203.775 (second parity). Examples: rate at +0 (index even, minute
  index 0 even: T = 15.065 degC, p = 1013.28 hPa) = 0.70598050 kg/h; at +2 (index odd, same
  ambient) = 0.70530846; at +420 (minute 7, odd: T = 14.935, p = 1013.22) = 0.70625726; at +422
  = 0.70558495. The inlet rate at +0 is 0.94209138 kg/h.
- Trapezoid over the bridged spacings divided by 3600: **co2_captured_kg = 0.1042968609**,
  **co2_inlet_kg = 0.1390624812**, **capture_rate_mean_kg_h = 0.1042968609 / (532 / 3600) =
  0.7057682316 kg/h**. Captured is below inlet, so `capture_below_inlet` passes.

## Energy per kg CO2 (S4.10 on this data)

- Power covered [0, 299], [311, 449], [452, 599]; capture covered [0, 360], [420, 498],
  [504, 598]. Overlap: [0, 299], [311, 360], [420, 449], [452, 498], [504, 598] = 299 + 49 + 29 +
  46 + 94 = **517 s**, coverage 517/600 = 0.861667, status partial.
- `power_computed` integrated exactly over the overlap (interpolated ends): 2.154153699 kWh.
  `capture_rate` over the same overlap: 0.1013564917 kg.
- **sec_kwh_per_kg = 2.154153699 / 0.1013564917 = 21.25323857 kWh/kg.** Above the 0.10 floor.

## Data quality (S4.12, S4.13)

| Signal | present | expected | accepted | bad | uncertain | completeness |
|---|---|---|---|---|---|---|
| current | 587 | 600 | 586 | 1 | 0 | 587/600 |
| voltage | 589 | 600 | 589 | 0 | 0 | 589/600 |
| power | 589 | 600 | 589 | 0 | 0 | 589/600 |
| co2_in_ppm | 300 | 300 | 298 | 2 | 0 | 1 |
| co2_out_ppm | 300 | 300 | 299 | 0 | 1 | 1 |
| air_flow | 600 | 600 | 600 | 0 | 0 | 1 |
| ambient_temperature | 8 | 10 | 8 | 0 | 0 | 0.8 |
| ambient_pressure | 8 | 10 | 8 | 0 | 0 | 0.8 |
| process_state | 2 | null | 2 | 0 | 0 | null |
| flow (and every other signal with no rows) | 0 | its expected count (flow 600) | 0 | 0 | 0 | 0, fractions null |

- Expected = floor(600 / nominal): 1 s signals 600, 2 s signals 300, 5 s signals 120, 60 s
  signals 10. 23 polled pairs: 9 x 600 + 4 x 300 + 6 x 120 + 4 x 10 = 5400 + 1200 + 720 + 40 =
  **7360**. The two state signals have no expected count.
- Present over all 25: 589 + 587 + 589 + 300 + 300 + 600 + 8 + 8 + 2 = **2983**; polled only
  (without process_state): 2981.
- **completeness = 2981 / 7360 = 0.405027174**; **valid_fraction = 2979 / 2983 = 0.998659068**
  (2983 - 4 excluded); **bad_fraction = 3 / 2983 = 0.001005699** (current +100, co2_in +500,
  +502); **uncertain_fraction = 1 / 2983 = 0.000335233** (co2_out +400).

## Plausibility

All four pass: efficiency mean 0.75 is in [0, 1]; captured 0.1043 kg <= inlet 0.1391 kg; energy
per kg 21.25 >= 0.10; |relative difference| 3.45e-05 <= 0.01. Exit code 0.

## Arithmetic check

Plain Python on the construction, `decimal` for exactness, no import from `pipeline/`. It
prints the numbers above.

```python
"""Hand computation of the metrics fixture from the construction alone (no pipeline imports)."""

import math
from decimal import Decimal as D


# --- construction
def vi(k):  # exact V and I at second k
    v = D("100") + (D("0.075") if k % 2 == 0 else -D("0.075"))
    i = D("150") + (D("0.15") if k % 2 == 0 else -D("0.15"))
    return v, i


no_el = set(range(300, 311))
volt_t = [k for k in range(600) if k not in no_el]
cur_ok = [k for k in volt_t if k not in (100, 450, 451)]
pow_t = list(volt_t)
power_computed = {k: vi(k)[0] * vi(k)[1] for k in cur_ok}
power_logged = {k: vi(k)[0] * vi(k)[1] + (250 if k == 200 else 0) for k in pow_t}
print(
    "power_computed rows",
    len(power_computed),
    "residual rows",
    len([k for k in pow_t if k in power_computed]),
)
res = {k: power_logged[k] - power_computed[k] for k in power_computed}
print(
    "max abs residual",
    max(abs(r) for r in res.values()),
    "nonzero",
    sum(1 for r in res.values() if r != 0),
)
within = sum(1 for k, r in res.items() if abs(r) <= D("0.01") * abs(power_computed[k]) + 10)
print("within", within, "limit at 200", D("0.01") * power_computed[200] + 10)


def trapz(series, maxs):
    ts = sorted(series)
    areas, cov = [], 0
    for a, b in zip(ts, ts[1:]):
        if b - a <= maxs:
            areas.append((series[a] + series[b]) / 2 * (b - a))
            cov += b - a
    return sum(areas), cov


E, cE = trapz(power_computed, 2)
L, cL = trapz(power_logged, 2)
print("E_ws", E, "cov", cE, "kWh", E / D("3600000"))
print("L_ws", L, "cov", cL, "kWh", L / D("3600000"))
print("mean kW", (E / D("3600000")) / (D(cE) / 3600))


def intervals(series, maxs):
    ts = sorted(series)
    out = []
    for a, b in zip(ts, ts[1:]):
        if b - a <= maxs:
            if out and out[-1][1] == a:
                out[-1] = (out[-1][0], b)
            else:
                out.append((a, b))
    return out


def ov(x, y):
    out = []
    for a0, a1 in x:
        for b0, b1 in y:
            s, e = max(a0, b0), min(a1, b1)
            if e > s:
                out.append((s, e))
    return sorted(out)


def val(series, t):
    if t in series:
        return series[t]
    ts = sorted(series)
    lo = max(x for x in ts if x < t)
    hi = min(x for x in ts if x > t)
    return series[lo] + (series[hi] - series[lo]) * D(t - lo) / D(hi - lo)


def integ_over(series, ivs):
    tot = D(0)
    for s, e in ivs:
        pts = [s] + [t for t in sorted(series) if s < t < e] + [e]
        for a, b in zip(pts, pts[1:]):
            tot += (val(series, a) + val(series, b)) / 2 * (b - a)
    return tot


pc, lc = intervals(power_computed, 2), intervals(power_logged, 2)
o = ov(pc, lc)
print("energy overlap", o, sum(e - s for s, e in o))
ec, el = integ_over(power_computed, o), integ_over(power_logged, o)
print("overlap E computed", ec, "logged", el, "rel diff", (el - ec) / ec)

# --- capture
co2_t = list(range(0, 600, 2))


def cin(k):
    i = k // 2
    return D("420") + (D("0.55") if i % 2 == 0 else -D("0.55"))


def cout(k):
    i = k // 2
    return D("105") + (D("0.4") if i % 2 == 0 else -D("0.4"))


def flow(k):
    return D("1200") + (D("3.775") if k % 2 == 0 else -D("3.775"))


amb_t = [60 * m for m in range(10) if 60 * m not in (300, 360)]


def temp(m):
    return D("15") + (D("0.065") if m % 2 == 0 else -D("0.065"))


def pres(m):
    return D("1013.25") + (D("0.03") if m % 2 == 0 else -D("0.03"))


cin_ok = [k for k in co2_t if k not in (500, 502)]
cout_ok = [k for k in co2_t if k != 400]
eff_t = [k for k in co2_t if k in cin_ok and k in cout_ok]
eff = {k: (cin(k) - cout(k)) / cin(k) for k in eff_t}
print("efficiency rows", len(eff), "mean", sum(eff.values()) / len(eff), "cov", trapz(eff, 4)[1])
M, R = D("0.04401"), D("8.314462618")


def ambient(k):
    prior = [t for t in amb_t if t <= k]
    if not prior or k - prior[-1] > 120:
        return None
    m = prior[-1] // 60
    return temp(m), pres(m)


rate, inlet = {}, {}
for k in eff_t:
    a = ambient(k)
    if a is None:
        continue
    t, p = a
    dens = p * 100 * M / (R * (t + D("273.15")))
    rate[k] = flow(k) * (cin(k) - cout(k)) * D("1e-6") * dens
    inlet[k] = flow(k) * cin(k) * D("1e-6") * dens
print(
    "capture rows",
    len(rate),
    "first/last missing",
    [k for k in eff_t if k not in rate][:3],
    [k for k in eff_t if k not in rate][-3:],
)
cap_ws, cap_s = trapz(rate, 4)
inl_ws, inl_s = trapz(inlet, 4)
cap_kg, inl_kg = cap_ws / 3600, inl_ws / 3600
print(
    "captured kg", cap_kg, "inlet kg", inl_kg, "cov", cap_s, "mean kg/h", cap_kg / (D(cap_s) / 3600)
)
cc = intervals(rate, 4)
print("capture intervals", cc)
so = ov(pc, cc)
print("sec overlap", so, sum(e - s for s, e in so))
sec_kwh = integ_over(power_computed, so) / D("3600000")
sec_kg = integ_over(rate, so) / 3600
print("sec kwh", sec_kwh, "kg", sec_kg, "sec", sec_kwh / sec_kg)
print("rate first", rate[0], "rate 362?", 362 in rate, "rate 360", rate[360])
print("power_computed[0], [1]", power_computed[0], power_computed[1])
```
