import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20260727

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

N_CELLS = 36
V0 = 1.9
B_VOLT = 0.12
I0 = 40.0
R0 = 0.0046
T_REF = 45.0
K_R = 0.00006
R_MIN = 0.0015

C_THERMAL = 50000.0
K_HEAT = 0.15
K_COOL = 120.0

TAU_CURRENT = 35.0
SLEW_MAX = 8.0
TAU_PH = 90.0
TAU_SOLVENT_TEMP = 200.0
TAU_SOLVENT_PH = 150.0
TAU_FLOW = 20.0
TAU_PRESSURE = 25.0
TAU_CONDUCTIVITY = 60.0
TAU_PUMP = 15.0
TAU_FAN = 15.0

ETA_MAX = 0.88
K_ETA = 23.0
K_PD = 1.0417e-5

EXPERIMENTS = [
    dict(id="EXP_001", start=datetime(2026, 5, 4, 8, 0, 0, tzinfo=timezone.utc), duration_s=7200,
         current_nominal_A=150.0, follow_solar=False, air_flow_nominal=1200.0, solvent_flow_nominal=8.0,
         ambient_base_temp_C=18.0, ambient_temp_amplitude_C=8.0, ambient_base_humidity=55.0,
         ambient_base_pressure_hPa=1015.0, solar_peak_kW=480.0,
         operator="J. Nguyen", sorbent_batch="SB-2026-014", notes="Baseline reference run, nominal conditions."),
    dict(id="EXP_002", start=datetime(2026, 5, 11, 9, 0, 0, tzinfo=timezone.utc), duration_s=7200,
         current_nominal_A=250.0, follow_solar=False, air_flow_nominal=1200.0, solvent_flow_nominal=8.0,
         ambient_base_temp_C=19.0, ambient_temp_amplitude_C=7.0, ambient_base_humidity=50.0,
         ambient_base_pressure_hPa=1012.0, solar_peak_kW=500.0,
         operator="J. Nguyen", sorbent_batch="SB-2026-014", notes="Elevated hydrolyzer current density vs. baseline."),
    dict(id="EXP_003", start=datetime(2026, 5, 18, 7, 30, 0, tzinfo=timezone.utc), duration_s=7200,
         current_nominal_A=150.0, follow_solar=False, air_flow_nominal=2400.0, solvent_flow_nominal=8.0,
         ambient_base_temp_C=17.0, ambient_temp_amplitude_C=9.0, ambient_base_humidity=48.0,
         ambient_base_pressure_hPa=1017.0, solar_peak_kW=510.0,
         operator="M. Alvarez", sorbent_batch="SB-2026-015", notes="Doubled air flow vs. baseline."),
    dict(id="EXP_004", start=datetime(2026, 3, 2, 8, 0, 0, tzinfo=timezone.utc), duration_s=7200,
         current_nominal_A=150.0, follow_solar=False, air_flow_nominal=1200.0, solvent_flow_nominal=8.0,
         ambient_base_temp_C=2.0, ambient_temp_amplitude_C=4.0, ambient_base_humidity=85.0,
         ambient_base_pressure_hPa=1008.0, solar_peak_kW=250.0,
         operator="M. Alvarez", sorbent_batch="SB-2026-011", notes="Cold-ambient, high-humidity conditions."),
    dict(id="EXP_005", start=datetime(2026, 6, 15, 6, 0, 0, tzinfo=timezone.utc), duration_s=7200,
         current_nominal_A=150.0, follow_solar=True, air_flow_nominal=1200.0, solvent_flow_nominal=8.0,
         ambient_base_temp_C=16.0, ambient_temp_amplitude_C=10.0, ambient_base_humidity=45.0,
         ambient_base_pressure_hPa=1014.0, solar_peak_kW=560.0,
         operator="J. Nguyen", sorbent_batch="SB-2026-016", notes="Hydrolyzer setpoint tracks available solar power."),
    dict(id="EXP_006", start=datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc), duration_s=7200,
         current_nominal_A=150.0, follow_solar=False, air_flow_nominal=1200.0, solvent_flow_nominal=9.5,
         ambient_base_temp_C=20.0, ambient_temp_amplitude_C=7.0, ambient_base_humidity=52.0,
         ambient_base_pressure_hPa=1013.0, solar_peak_kW=470.0,
         operator="R. Kovac", sorbent_batch="SB-2026-015", notes="Slightly richer solvent flow vs. baseline."),
]

SOURCE_OF = {
    "ambient_temperature": "ambient", "relative_humidity": "ambient",
    "ambient_pressure": "ambient", "available_solar_power": "ambient",
    "air_flow": "absorber", "co2_in_ppm": "absorber", "co2_out_ppm": "absorber",
    "solvent_flow": "absorber", "solvent_temperature": "absorber", "solvent_pH": "absorber",
    "pressure_drop": "absorber",
    "current_setpoint": "hydrolyzer", "current": "hydrolyzer", "voltage": "hydrolyzer",
    "power": "hydrolyzer", "acid_pH": "hydrolyzer", "base_pH": "hydrolyzer",
    "conductivity": "hydrolyzer", "electrolyte_temperature": "hydrolyzer",
    "flow": "hydrolyzer", "pressure": "hydrolyzer",
    "pump_speed": "plant", "fan_speed": "plant", "valve_state": "plant", "process_state": "plant",
}

DECIMALS = {
    "current_setpoint": 2, "current": 2, "voltage": 2, "power": 1, "flow": 2, "pressure": 3,
    "air_flow": 1, "pump_speed": 1, "fan_speed": 1,
    "co2_in_ppm": 1, "co2_out_ppm": 1, "solvent_flow": 2, "pressure_drop": 2,
    "acid_pH": 3, "base_pH": 3, "solvent_pH": 3, "conductivity": 1,
    "electrolyte_temperature": 2, "solvent_temperature": 2,
    "ambient_temperature": 2, "relative_humidity": 1, "ambient_pressure": 2, "available_solar_power": 2,
}

NOISE_STD = {
    "current": 0.3, "voltage": 0.15, "flow": 0.4, "pressure": 0.03, "air_flow": 8.0,
    "pump_speed": 3.0, "fan_speed": 5.0, "co2_in_ppm": 1.2, "co2_out_ppm": 0.8,
    "solvent_flow": 0.15, "pressure_drop": 0.25, "acid_pH": 0.05, "base_pH": 0.05,
    "solvent_pH": 0.05, "conductivity": 2.0, "electrolyte_temperature": 0.2,
    "solvent_temperature": 0.3,
}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def build_ambient_series(cfg, rng):
    n_minutes = cfg["duration_s"] // 60 + 2
    series = []
    cloud = 1.0
    pressure = cfg["ambient_base_pressure_hPa"]
    start = cfg["start"]
    for m in range(n_minutes):
        t = start + timedelta(minutes=m)
        hour = t.hour + t.minute / 60.0 + t.second / 3600.0
        bell = max(0.0, math.sin(math.pi * (hour - 6) / 12)) ** 1.2 if 6 <= hour <= 18 else 0.0
        cloud = clamp(cloud + 0.15 * (1.0 - cloud) + 0.06 * rng.gauss(0, 1), 0.0, 1.15)
        solar = max(0.0, cfg["solar_peak_kW"] * bell * cloud)
        temperature = (cfg["ambient_base_temp_C"]
                       + cfg["ambient_temp_amplitude_C"] * math.sin(math.pi * (hour - 6) / 12)
                       + rng.gauss(0, 0.15))
        humidity = clamp(cfg["ambient_base_humidity"] - 15 * math.sin(math.pi * (hour - 6) / 12)
                          + rng.gauss(0, 1.5), 15.0, 100.0)
        pressure = clamp(pressure + 0.02 * (cfg["ambient_base_pressure_hPa"] - pressure)
                          + rng.gauss(0, 0.08), 950.0, 1050.0)
        series.append(dict(solar_kW=solar, temperature_C=temperature,
                            humidity_pct=humidity, pressure_hPa=pressure))
    return series


def setpoint_at(t, cfg, amb):
    if cfg["follow_solar"]:
        base = clamp(40.0 + 0.32 * amb["solar_kW"], 20.0, 230.0)
    else:
        base = cfg["current_nominal_A"]
        if 3000 <= t < 3300:
            base = cfg["current_nominal_A"] * 1.4
    if t < 30:
        return 0.0
    if t >= cfg["duration_s"] - 300:
        frac = max(0.0, (cfg["duration_s"] - t) / 300.0)
        return base * frac
    return base


def simulate_true_series(cfg, rng):
    duration = cfg["duration_s"]
    ambient_series = build_ambient_series(cfg, rng)

    current = 0.0
    electrolyte_temperature = cfg["ambient_base_temp_C"] + 5.0
    acid_pH = 2.5
    base_pH = 11.5
    solvent_temperature = cfg["ambient_base_temp_C"] + 8.0
    solvent_pH = 7.5
    flow = 30.0
    pressure = 2.3
    conductivity = 180.0
    pump_speed = 200.0 + 40.0 * cfg["solvent_flow_nominal"]
    fan_speed = 300.0 + 0.5 * cfg["air_flow_nominal"]

    phase = "STARTUP"
    last_stable_setpoint = 0.0
    settle_counter = 0

    true_series = []
    for t in range(duration):
        amb = ambient_series[t // 60]
        sp = setpoint_at(t, cfg, amb)

        if t >= duration - 300:
            phase = "SHUTDOWN"
        elif t < 150:
            phase = "STARTUP"
        else:
            if phase == "STARTUP":
                phase = "STEADY_STATE"
                last_stable_setpoint = sp
            if phase != "LOAD_CHANGE" and abs(sp - last_stable_setpoint) > 10.0:
                phase = "LOAD_CHANGE"
                settle_counter = 0
            if phase == "LOAD_CHANGE":
                if abs(current - sp) < 3.0:
                    settle_counter += 1
                else:
                    settle_counter = 0
                if settle_counter >= 30:
                    phase = "STEADY_STATE"
                    last_stable_setpoint = sp
                    settle_counter = 0

        valve_state = "CLOSED" if (t < 20 or t >= duration - 30) else "OPEN"

        d_current = clamp((sp - current) / TAU_CURRENT, -SLEW_MAX, SLEW_MAX)
        current = max(0.0, current + d_current)

        r_t = clamp(R0 - K_R * (electrolyte_temperature - T_REF), R_MIN, R0 * 2)
        v_cell = V0 + B_VOLT * math.log(current / I0 + 1.0) + current * r_t
        voltage = N_CELLS * v_cell
        power_internal = voltage * current

        electrolyte_temperature += (K_HEAT * power_internal
                                     - K_COOL * (electrolyte_temperature - amb["temperature_C"])) / C_THERMAL

        acid_target = clamp(2.5 - 0.003 * current, 0.5, 4.0)
        acid_pH += (acid_target - acid_pH) / TAU_PH
        base_target = clamp(11.5 + 0.004 * current, 10.0, 13.5)
        base_pH += (base_target - base_pH) / TAU_PH

        solvent_temp_target = amb["temperature_C"] + 8.0
        solvent_temperature += (solvent_temp_target - solvent_temperature) / TAU_SOLVENT_TEMP

        solvent_ph_target = 7.5 + 0.25 * (base_pH - 11.5)
        solvent_pH += (solvent_ph_target - solvent_pH) / TAU_SOLVENT_PH

        flow += (30.0 + 0.08 * current - flow) / TAU_FLOW
        pressure += (2.3 + 0.002 * current - pressure) / TAU_PRESSURE
        conductivity += (180.0 + 0.15 * current + 1.2 * (electrolyte_temperature - 25.0)
                          - conductivity) / TAU_CONDUCTIVITY
        pump_speed += (200.0 + 40.0 * cfg["solvent_flow_nominal"] - pump_speed) / TAU_PUMP
        fan_speed += (300.0 + 0.5 * cfg["air_flow_nominal"] - fan_speed) / TAU_FAN

        f_mod = clamp(1.0 + 0.15 * (solvent_pH - 7.6), 0.5, 1.4)
        g_mod = clamp(1.15 - 0.01 * abs(solvent_temperature - 15.0), 0.7, 1.15)
        ratio = math.sqrt(cfg["solvent_flow_nominal"] / cfg["air_flow_nominal"])
        eta = clamp(ETA_MAX * (1.0 - math.exp(-K_ETA * ratio * f_mod * g_mod)), 0.05, 0.95)

        fouling = 0.03 * (t / duration)
        pressure_drop = K_PD * cfg["air_flow_nominal"] ** 2 * (1.0 + fouling)

        co2_in = 420.0
        co2_out = co2_in * (1.0 - eta)

        true_series.append(dict(
            current_setpoint=sp, current=current, voltage=voltage,
            flow=flow, pressure=pressure, air_flow=cfg["air_flow_nominal"],
            pump_speed=pump_speed, fan_speed=fan_speed,
            co2_in_ppm=co2_in, co2_out_ppm=co2_out,
            solvent_flow=cfg["solvent_flow_nominal"], pressure_drop=pressure_drop,
            acid_pH=acid_pH, base_pH=base_pH, solvent_pH=solvent_pH,
            conductivity=conductivity, electrolyte_temperature=electrolyte_temperature,
            solvent_temperature=solvent_temperature,
            phase=phase, valve_state=valve_state,
        ))

    return true_series, ambient_series


def fmt(signal, value):
    return f"{value:.{DECIMALS.get(signal, 3)}f}"


def sample_experiment(cfg, true_series, ambient_series, rng):
    records = []
    start = cfg["start"]
    duration = cfg["duration_s"]

    def ts(t):
        return (start + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%SZ")

    hz1_other = ["current_setpoint", "flow", "pressure", "air_flow", "pump_speed", "fan_speed"]
    for t in range(0, duration, 1):
        true = true_series[t]
        ts_t = ts(t)
        # current/voltage/power share one noise draw each so power == current * voltage
        # holds for the reported values, matching the P = U x I check the task expects.
        cur_val = true["current"] + rng.gauss(0, NOISE_STD["current"])
        volt_val = true["voltage"] + rng.gauss(0, NOISE_STD["voltage"])
        power_val = cur_val * volt_val
        records.append((ts_t, cfg["id"], SOURCE_OF["current"], "current", fmt("current", cur_val), "GOOD"))
        records.append((ts_t, cfg["id"], SOURCE_OF["voltage"], "voltage", fmt("voltage", volt_val), "GOOD"))
        records.append((ts_t, cfg["id"], SOURCE_OF["power"], "power", fmt("power", power_val), "GOOD"))
        for signal in hz1_other:
            noise = 0.0 if signal == "current_setpoint" else rng.gauss(0, NOISE_STD.get(signal, 0.0))
            value = true[signal] + noise
            records.append((ts_t, cfg["id"], SOURCE_OF[signal], signal, fmt(signal, value), "GOOD"))

    hz_half = ["co2_in_ppm", "co2_out_ppm", "solvent_flow", "pressure_drop"]
    for t in range(0, duration, 2):
        true = true_series[t]
        ts_t = ts(t)
        for signal in hz_half:
            value = true[signal] + rng.gauss(0, NOISE_STD.get(signal, 0.0))
            records.append((ts_t, cfg["id"], SOURCE_OF[signal], signal, fmt(signal, value), "GOOD"))

    hz_02 = ["acid_pH", "base_pH", "solvent_pH", "conductivity",
             "electrolyte_temperature", "solvent_temperature"]
    for t in range(0, duration, 5):
        true = true_series[t]
        ts_t = ts(t)
        for signal in hz_02:
            value = true[signal] + rng.gauss(0, NOISE_STD.get(signal, 0.0))
            records.append((ts_t, cfg["id"], SOURCE_OF[signal], signal, fmt(signal, value), "GOOD"))

    for m in range(0, duration // 60):
        amb = ambient_series[m]
        ts_t = ts(m * 60)
        records.append((ts_t, cfg["id"], "ambient", "ambient_temperature",
                         fmt("ambient_temperature", amb["temperature_C"]), "GOOD"))
        records.append((ts_t, cfg["id"], "ambient", "relative_humidity",
                         fmt("relative_humidity", amb["humidity_pct"]), "GOOD"))
        records.append((ts_t, cfg["id"], "ambient", "ambient_pressure",
                         fmt("ambient_pressure", amb["pressure_hPa"]), "GOOD"))
        records.append((ts_t, cfg["id"], "ambient", "available_solar_power",
                         fmt("available_solar_power", amb["solar_kW"]), "GOOD"))

    prev_phase = None
    prev_valve = None
    for t in range(0, duration, 1):
        true = true_series[t]
        if true["phase"] != prev_phase:
            records.append((ts(t), cfg["id"], "plant", "process_state", true["phase"], "GOOD"))
            prev_phase = true["phase"]
        if true["valve_state"] != prev_valve:
            records.append((ts(t), cfg["id"], "plant", "valve_state", true["valve_state"], "GOOD"))
            prev_valve = true["valve_state"]

    records.sort(key=lambda r: (r[0], r[3]))
    return records


def parse_ts(ts_str):
    return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def fmt_ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def log_defect(manifest, kind, exp, source, signal, start, end, description, lesson):
    manifest.append(dict(
        type=kind, experiment_id=exp, source=source, signal=signal,
        start_ts=fmt_ts(start) if isinstance(start, datetime) else start,
        end_ts=fmt_ts(end) if isinstance(end, datetime) else end,
        description=description, lesson=lesson,
    ))


def remove_rows(records, predicate):
    kept, removed = [], 0
    for r in records:
        if predicate(r):
            removed += 1
        else:
            kept.append(r)
    return kept, removed


def in_window(r, source, signal, t0, t1):
    return r[2] == source and r[3] == signal and t0 <= parse_ts(r[0]) < t1


def set_quality_window(records, source, signal, t0, t1, quality, new_value=None):
    count = 0
    for r in records:
        if in_window(r, source, signal, t0, t1):
            r[5] = quality
            if new_value is not None:
                r[4] = new_value
            count += 1
    return count


def set_single_value(records, source, signal, t, value):
    best = None
    for r in records:
        if r[2] == source and r[3] == signal:
            if best is None or abs((parse_ts(r[0]) - t).total_seconds()) < \
                    abs((parse_ts(best[0]) - t).total_seconds()):
                best = r
    if best is not None:
        best[4] = value
    return best


def freeze_window(records, source, signal, t0, t1, freeze_value=None):
    matches = [r for r in records if in_window(r, source, signal, t0, t1)]
    matches.sort(key=lambda r: parse_ts(r[0]))
    if not matches:
        return 0, freeze_value
    value = freeze_value if freeze_value is not None else matches[0][4]
    for r in matches:
        r[4] = value
    return len(matches), value


def scale_window(records, source, signal, t0, t1, factor, decimals):
    count = 0
    for r in records:
        if in_window(r, source, signal, t0, t1):
            r[4] = f"{float(r[4]) * factor:.{decimals}f}"
            count += 1
    return count


def duplicate_exact(records, rng, n):
    if not records:
        return records
    picks = [records[rng.randrange(len(records))] for _ in range(n)]
    return records + [list(p) for p in picks]


def duplicate_conflicting(records, rng, n, jitter_frac):
    numeric = [r for r in records if r[3] not in ("valve_state", "process_state")]
    if not numeric:
        return records
    picks = rng.sample(numeric, min(n, len(numeric)))
    extra = []
    for r in picks:
        jittered = float(r[4]) * (1.0 + rng.uniform(-jitter_frac, jitter_frac))
        decimals = len(r[4].split(".")[1]) if "." in r[4] else 0
        extra.append([r[0], r[1], r[2], r[3], f"{jittered:.{decimals}f}", "GOOD"])
    return records + extra


def move_block_to_end(records, signals, t0, t1):
    moved, kept = [], []
    for r in records:
        if r[3] in signals and t0 <= parse_ts(r[0]) < t1:
            moved.append(r)
        else:
            kept.append(r)
    return kept + moved, len(moved)


def interleave_shuffle(records, rng, n):
    for _ in range(n):
        i = rng.randrange(len(records) - 10)
        j = i + rng.randint(4, 9)
        records[i], records[j] = records[j], records[i]
    return records


def apply_unit_change(records, source, signal, t_from, factor, decimals):
    count = 0
    for r in records:
        if r[2] == source and r[3] == signal and parse_ts(r[0]) >= t_from:
            r[4] = f"{float(r[4]) * factor:.{decimals}f}"
            count += 1
    return count


def apply_ambient_timezone(records):
    for r in records:
        if r[2] == "ambient":
            local_dt = parse_ts(r[0]) + timedelta(hours=2)
            r[0] = local_dt.strftime("%Y-%m-%dT%H:%M:%S") + "+02:00"
    return records


def inject_defects(cfg, records, rng, manifest):
    exp = cfg["id"]
    start = cfg["start"]
    records = [list(r) for r in records]

    if exp == "EXP_001":
        for w0, w1 in [(600, 615), (1800, 1825), (4200, 4206), (5500, 5528)]:
            t0, t1 = start + timedelta(seconds=w0), start + timedelta(seconds=w1)
            for signal in ("current", "voltage", "power"):
                records, removed = remove_rows(
                    records, lambda r, s=signal, a=t0, b=t1: in_window(r, "hydrolyzer", s, a, b))
                log_defect(manifest, "short_gap", exp, "hydrolyzer", signal, t0, t1,
                           f"{w1 - w0}s dropout, {removed} samples removed",
                           "Short enough that linear interpolation across the gap is defensible.")

        t = start + timedelta(seconds=2500)
        set_single_value(records, "hydrolyzer", "voltage", t, "412.00")
        log_defect(manifest, "outlier", exp, "hydrolyzer", "voltage", t, t,
                   "Single-sample voltage spike to 412 V",
                   "A single-sample spike, not a real transient; a rolling median or z-score check "
                   "should catch it without needing a physical-limits table.")

        t0, t1 = start + timedelta(seconds=3600), start + timedelta(seconds=3900)
        n = set_quality_window(records, "hydrolyzer", "conductivity", t0, t1, "BAD", new_value="50.0")
        log_defect(manifest, "bad_quality", exp, "hydrolyzer", "conductivity", t0, t1,
                   f"{n} samples pinned to an implausibly low reading and flagged BAD",
                   "Flagged at the source; keep the value for audit but exclude it from any "
                   "efficiency/energy calculation.")

        t0, t1 = start + timedelta(seconds=5000), start + timedelta(seconds=5120)
        n = scale_window(records, "hydrolyzer", "power", t0, t1, 1.4, 1)
        log_defect(manifest, "physical_inconsistency", exp, "hydrolyzer", "power", t0, t1,
                   f"power inflated ~40% above voltage*current for {n} samples, quality stays GOOD",
                   "power != voltage * current is not a statistical outlier if power stays within its "
                   "normal range - it is a physical consistency check the candidate has to compute "
                   "deliberately, not something a range check will find.")

    elif exp == "EXP_002":
        t0, t1 = start + timedelta(seconds=3960), start + timedelta(seconds=4440)
        records, removed = remove_rows(records, lambda r: r[2] == "hydrolyzer" and t0 <= parse_ts(r[0]) < t1)
        log_defect(manifest, "long_gap", exp, "hydrolyzer", "*", t0, t1,
                   f"8-minute full outage of the hydrolyzer data source ({removed} samples removed)",
                   "Long enough that interpolation is not defensible; the window must be excluded "
                   "from derived metrics, not filled in.")

        t = start + timedelta(seconds=2000)
        set_single_value(records, "hydrolyzer", "current", t, "0.00")
        log_defect(manifest, "physical_inconsistency", exp, "hydrolyzer", "current", t, t,
                   "current forced to 0 A while power stays near its normal ~29 kW",
                   "current = 0 with nonzero power is not statistically unusual for either signal alone "
                   "- only the combination is physically impossible.")

        records = duplicate_exact(records, rng, 15)
        log_defect(manifest, "duplicate_timestamp", exp, "*", "*",
                   start, start + timedelta(seconds=cfg["duration_s"]),
                   "15 rows duplicated exactly (same timestamp, signal and value)",
                   "Simple exact-duplicate detection (drop identical rows) is safe here.")

    elif exp == "EXP_003":
        t0, t1 = start + timedelta(seconds=3600), start + timedelta(seconds=4800)
        n, value = freeze_window(records, "absorber", "solvent_temperature", t0, t1)
        log_defect(manifest, "stuck_sensor", exp, "absorber", "solvent_temperature", t0, t1,
                   f"{n} samples frozen at {value} while the process kept evolving, quality stays GOOD",
                   "Noise disappearing entirely is itself the signature; a rolling-variance check "
                   "catches it even though every individual value looks plausible.")

        t = start + timedelta(seconds=1500)
        set_single_value(records, "absorber", "solvent_pH", t, "27.400")
        log_defect(manifest, "outlier", exp, "absorber", "solvent_pH", t, t,
                   "Single-sample solvent_pH spike to 27.4 (outside the physically possible 0-14 range)",
                   "Physically impossible on its own - doesn't even need a statistical test, "
                   "just a hard-limits check.")

        t = start + timedelta(seconds=5000)
        set_single_value(records, "plant", "fan_speed", t, "0.0")
        log_defect(manifest, "physical_inconsistency", exp, "plant", "fan_speed", t, t,
                   "fan_speed forced to 0 while air_flow stays at its normal ~2400 m3/h",
                   "air_flow is untouched and looks completely normal - only cross-checking it "
                   "against fan_speed reveals the inconsistency.")

        t0, t1 = start + timedelta(seconds=2200), start + timedelta(seconds=2400)
        n = set_quality_window(records, "hydrolyzer", "acid_pH", t0, t1, "BAD", new_value="4.800")
        log_defect(manifest, "bad_quality", exp, "hydrolyzer", "acid_pH", t0, t1,
                   f"{n} samples pinned to a value inconsistent with the current level, flagged BAD",
                   "Flagged at the source; keep for audit, exclude from process analysis.")

    elif exp == "EXP_004":
        t = start + timedelta(seconds=1000)
        set_single_value(records, "hydrolyzer", "pressure", t, "-3.100")
        log_defect(manifest, "outlier", exp, "hydrolyzer", "pressure", t, t,
                   "Single-sample pressure spike to -3.1 bar (negative gauge pressure isn't possible here)",
                   "Physically impossible value; a hard-limits check catches it independent of statistics.")

        t_from = start + timedelta(seconds=3600)
        n = apply_unit_change(records, "absorber", "air_flow", t_from, 1.0 / 60.0, 2)
        log_defect(manifest, "unit_change", exp, "absorber", "air_flow",
                   t_from, start + timedelta(seconds=cfg["duration_s"]),
                   f"{n} air_flow samples silently switch from m3/h to Nm3/min partway through the run, "
                   f"quality stays GOOD",
                   "pressure_drop is generated from the true, unchanged air flow and stays normal "
                   "throughout, so cross-checking pressure_drop against the reported air_flow shows "
                   "they've become inconsistent with each other after the switch.")

        t = start + timedelta(seconds=4500)
        set_single_value(records, "plant", "pump_speed", t, "0.0")
        log_defect(manifest, "physical_inconsistency", exp, "plant", "pump_speed", t, t,
                   "pump_speed forced to 0 while solvent_flow stays at its normal level",
                   "solvent_flow alone looks unremarkable; only checking it against pump_speed "
                   "reveals the inconsistency.")

        t0, t1 = start + timedelta(seconds=2000), start + timedelta(seconds=2200)
        n = set_quality_window(records, "hydrolyzer", "pressure", t0, t1, "UNCERTAIN")
        log_defect(manifest, "uncertain_quality", exp, "hydrolyzer", "pressure", t0, t1,
                   f"{n} samples flagged UNCERTAIN, value left unchanged",
                   "UNCERTAIN is not the same as wrong; the candidate has to decide per-calculation "
                   "whether to include or exclude these rather than blanket-dropping them like BAD.")

    elif exp == "EXP_005":
        t = start + timedelta(seconds=4000)
        set_single_value(records, "hydrolyzer", "electrolyte_temperature", t, "-50.00")
        log_defect(manifest, "outlier", exp, "hydrolyzer", "electrolyte_temperature", t, t,
                   "Single-sample electrolyte_temperature spike to -50 C",
                   "Physically implausible for an operating electrolyzer; a hard-limits or "
                   "rolling-median check catches it.")

        t_close = start + timedelta(seconds=2500)
        t_open = t_close + timedelta(seconds=45)
        records.append([fmt_ts(t_close), exp, "plant", "valve_state", "CLOSED", "GOOD"])
        records.append([fmt_ts(t_open), exp, "plant", "valve_state", "OPEN", "GOOD"])
        log_defect(manifest, "physical_inconsistency", exp, "plant", "valve_state", t_close, t_open,
                   "valve_state reports CLOSED for 45s while solvent_flow keeps flowing normally",
                   "solvent_flow itself is untouched and unremarkable; the inconsistency only shows "
                   "up when cross-checked against valve_state.")

        t0, t1 = start + timedelta(seconds=2800), start + timedelta(seconds=2980)
        records, moved = move_block_to_end(
            records, {"current", "voltage", "power", "flow", "pressure",
                      "air_flow", "pump_speed", "fan_speed"}, t0, t1)
        log_defect(manifest, "out_of_order", exp, "hydrolyzer/plant", "*", t0, t1,
                   f"{moved} rows from this window arrive as a late batch appended at the end of the file",
                   "Ingestion must not assume the file is time-sorted; sort (or upsert by timestamp) "
                   "before computing anything windowed.")

        t0, t1 = start, start + timedelta(seconds=1800)
        n = set_quality_window(records, "ambient", "ambient_pressure", t0, t1, "UNCERTAIN")
        log_defect(manifest, "uncertain_quality", exp, "ambient", "ambient_pressure", t0, t1,
                   f"{n} samples flagged UNCERTAIN during a suspected weather-station recalibration",
                   "Low-stakes signal; a reasonable candidate may choose to just note this rather "
                   "than build special handling for it.")

    elif exp == "EXP_006":
        t0, t1 = start + timedelta(seconds=1080), start + timedelta(seconds=3000)
        records, removed = remove_rows(records, lambda r: r[2] == "absorber" and t0 <= parse_ts(r[0]) < t1)
        log_defect(manifest, "long_gap", exp, "absorber", "*", t0, t1,
                   f"32-minute full outage of the absorber data source ({removed} samples removed)",
                   "Long enough that interpolation is not defensible; also directly hurts this "
                   "experiment's data_completeness score.")

        t0, t1 = start + timedelta(seconds=3600), start + timedelta(seconds=6300)
        n, value = freeze_window(records, "absorber", "co2_out_ppm", t0, t1, freeze_value="38.0")
        log_defect(manifest, "stuck_sensor", exp, "absorber", "co2_out_ppm", t0, t1,
                   f"{n} samples frozen at {value} ppm, quality stays GOOD",
                   "With co2_in ~420 ppm this makes naive capture efficiency look like ~91% for this "
                   "stretch - the single biggest trap in the dataset. A naive per-experiment average "
                   "ranks this experiment as the best performer; a completeness/variance-aware "
                   "analysis should disqualify or heavily discount it instead.")

        records = duplicate_conflicting(records, rng, 10, 0.08)
        log_defect(manifest, "duplicate_timestamp", exp, "*", "*",
                   start, start + timedelta(seconds=cfg["duration_s"]),
                   "10 timestamps carry two rows for the same signal with different values",
                   "Exact-duplicate dropping does not resolve this; it requires an explicit tie-break "
                   "policy (last-write-wins, average, or flag-both-suspect).")

        records = interleave_shuffle(records, rng, 20)
        log_defect(manifest, "out_of_order", exp, "*", "*",
                   start, start + timedelta(seconds=cfg["duration_s"]),
                   "~20 rows locally shuffled a few positions out of chronological order",
                   "Simulates minor network/queueing jitter rather than a large delayed batch; "
                   "still breaks any code that assumes strict file ordering.")

    records = apply_ambient_timezone(records)
    return records


def write_experiments_metadata(path, manifest):
    missing_fields = {
        "EXP_003": ("notes",),
        "EXP_005": ("sorbent_batch",),
        "EXP_006": ("operator",),
    }
    data = []
    for cfg in EXPERIMENTS:
        end = cfg["start"] + timedelta(seconds=cfg["duration_s"])
        record = dict(
            experiment_id=cfg["id"],
            start_time=cfg["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_time=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            duration_s=cfg["duration_s"],
            current_setpoint_nominal_A=cfg["current_nominal_A"],
            air_flow_nominal_m3h=cfg["air_flow_nominal"],
            solvent_flow_nominal_Lmin=cfg["solvent_flow_nominal"],
            operator=cfg["operator"],
            sorbent_batch=cfg["sorbent_batch"],
            notes=cfg["notes"],
        )
        for field in missing_fields.get(cfg["id"], ()):
            record[field] = None
            log_defect(manifest, "missing_metadata", cfg["id"], "experiments.json", field, None, None,
                       f"{field} was not recorded for this run",
                       "Forces an explicit decision about what a clean experiment comparison requires "
                       "and whether missing context should block a conclusion.")
        data.append(record)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "dac_raw_timeseries.csv"
    manifest = []

    total_rows = 0
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "experiment_id", "source", "signal", "value", "quality"])
        for cfg in EXPERIMENTS:
            rng = random.Random(f"{SEED}-{cfg['id']}")
            true_series, ambient_series = simulate_true_series(cfg, rng)
            records = sample_experiment(cfg, true_series, ambient_series, rng)
            records = inject_defects(cfg, records, rng, manifest)
            writer.writerows(records)
            total_rows += len(records)
            avg_current = sum(r["current"] for r in true_series) / len(true_series)
            avg_co2_out = sum(r["co2_out_ppm"] for r in true_series) / len(true_series)
            avg_eta = 1.0 - avg_co2_out / 420.0
            print(f"{cfg['id']}: {len(records):>7} rows | avg current {avg_current:6.1f} A "
                  f"| true (pre-defect) capture efficiency {avg_eta * 100:5.1f}%")

    write_experiments_metadata(OUT_DIR / "experiments.json", manifest)

    debrief_dir = Path(__file__).resolve().parent.parent / "_debrief"
    debrief_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = debrief_dir / "defect_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nTotal rows written: {total_rows}")
    print(f"Defects logged: {len(manifest)}")
    print(f"CSV: {csv_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
