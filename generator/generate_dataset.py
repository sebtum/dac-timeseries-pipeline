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


def write_experiments_metadata(path):
    data = []
    for cfg in EXPERIMENTS:
        end = cfg["start"] + timedelta(seconds=cfg["duration_s"])
        data.append(dict(
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
        ))
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "dac_raw_timeseries.csv"

    total_rows = 0
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "experiment_id", "source", "signal", "value", "quality"])
        for cfg in EXPERIMENTS:
            rng = random.Random(f"{SEED}-{cfg['id']}")
            true_series, ambient_series = simulate_true_series(cfg, rng)
            records = sample_experiment(cfg, true_series, ambient_series, rng)
            writer.writerows(records)
            total_rows += len(records)
            avg_current = sum(r["current"] for r in true_series) / len(true_series)
            avg_co2_out = sum(r["co2_out_ppm"] for r in true_series) / len(true_series)
            avg_eta = 1.0 - avg_co2_out / 420.0
            print(f"{cfg['id']}: {len(records):>7} rows | avg current {avg_current:6.1f} A "
                  f"| avg capture efficiency {avg_eta * 100:5.1f}%")

    write_experiments_metadata(OUT_DIR / "experiments.json")

    print(f"\nTotal rows written: {total_rows}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
