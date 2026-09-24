"""Plant Brain synthetic data generator. ALL DATA IS SYNTHETIC.

Deterministic (seed=42), standard library only, so output is byte-identical
across machines and Python 3.10+ versions.

Usage:
    python data_gen/generate.py            # write CSVs + answer_key.json to data_gen/
    python data_gen/generate.py --verify   # regenerate in memory and assert scenario invariants
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenario as S  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
TS_FMT = "%Y-%m-%d %H:%M:%S"
N_STEPS = S.DAYS * 24 * 60 // S.STEP_MIN  # 25,920 readings per asset
END = S.START + timedelta(days=S.DAYS)


def rng(*parts) -> random.Random:
    """Independent, stable RNG per concern (str seeding is PYTHONHASHSEED-independent)."""
    return random.Random("-".join(str(p) for p in (S.SEED,) + parts))


def ts(d: datetime) -> str:
    return d.strftime(TS_FMT)


def idx(d: datetime) -> int:
    return int((d - S.START).total_seconds() // (S.STEP_MIN * 60))


# =============================================================================
# Static reference data
# =============================================================================
ASSET_TYPES = {
    #            vib mm/s, temp C, pressure bar, current A
    "CNC_MILL": dict(vib=2.2, temp=38.0, pressure=None, current=18.0),
    "HYDRAULIC_PRESS": dict(vib=3.0, temp=45.0, pressure=180.0, current=42.0),
    "AIR_COMPRESSOR": dict(vib=2.6, temp=70.0, pressure=7.5, current=55.0),
    "CONVEYOR": dict(vib=1.8, temp=35.0, pressure=None, current=9.0),
}

ASSETS = [
    # asset_id, name, type, line, install_date, firmware, model, ideal_cycle_s (None = utility, no OEE)
    ("CNC1", "CNC Vertical Mill 1", "CNC_MILL", "L1", "2019-03-14", "v4.1", "VMC-850", 95),
    ("CNC2", "CNC Vertical Mill 2", "CNC_MILL", "L1", "2019-03-14", "v4.1", "VMC-850", 110),
    ("CNC3", "CNC Vertical Mill 3", "CNC_MILL", "L2", "2021-07-02", "v3.8", "VMC-640", 80),
    ("CNC4", "CNC Vertical Mill 4", "CNC_MILL", "L2", "2022-01-19", "v4.1", "VMC-850", 120),
    ("P1", "Hydraulic Press 1 (250T)", "HYDRAULIC_PRESS", "L1", "2016-11-08", "v1.6", "HP-250", 12),
    ("P2", "Hydraulic Press 2 (250T)", "HYDRAULIC_PRESS", "L2", "2017-05-22", "v1.6", "HP-250", 12),
    ("P3", "Hydraulic Press 3 (315T)", "HYDRAULIC_PRESS", "L3", "2014-09-30", "v1.4", "HP-315", 14),
    ("AC1", "Screw Air Compressor 1", "AIR_COMPRESSOR", "L1", "2018-02-12", "v2.1", "SC-37", None),
    ("AC2", "Screw Air Compressor 2", "AIR_COMPRESSOR", "L3", "2015-08-03", "v1.9", "SC-37", None),
    ("CV1", "Transfer Conveyor 1", "CONVEYOR", "L1", "2018-06-01", "n/a", "BC-12", 20),
    ("CV2", "Transfer Conveyor 2", "CONVEYOR", "L2", "2018-06-01", "n/a", "BC-12", 20),
    ("CV3", "Transfer Conveyor 3", "CONVEYOR", "L3", "2020-10-15", "n/a", "BC-12", 20),
]
ASSET_BY_ID = {a[0]: a for a in ASSETS}

FAILURE_MODES = [
    # id, code, name, applicable types, primary sensors, signature, threshold rule, typical precursor h
    ("FM01", "BEARING_WEAR", "Bearing wear", "CNC_MILL|HYDRAULIC_PRESS|AIR_COMPRESSOR|CONVEYOR",
     "vibration_rms|temperature_c", "Vibration ramps up ~18% over ~36 h, temperature follows with ~12 h lag, then both accelerate",
     "vibration_rms >= 1.35 x 7-day baseline", 48),
    ("FM02", "SEAL_LEAK", "Hydraulic seal leak", "HYDRAULIC_PRESS",
     "pressure_bar|current_a", "Pressure drifts down ~8% over ~24 h while motor current rises to compensate",
     "pressure_bar <= 0.92 x baseline", 24),
    ("FM03", "SPINDLE_MISALIGNMENT", "Spindle misalignment", "CNC_MILL",
     "vibration_rms|current_a", "Vibration steps up ~20% then creeps; spindle current rises ~5%",
     "vibration_rms >= 1.30 x baseline", 30),
    ("FM04", "BELT_SLIP", "Belt slip", "CONVEYOR",
     "vibration_rms|current_a", "Sudden vibration step (~+22%) with erratic motor current; temperature flat",
     "current_a stddev >= 3 x baseline", 6),
    ("FM05", "VALVE_STICKING", "Valve sticking", "HYDRAULIC_PRESS|AIR_COMPRESSOR",
     "pressure_bar", "Pressure oscillation amplitude grows over ~12 h",
     "pressure_bar stddev >= 4 x baseline", 12),
    ("FM06", "COOLANT_BLOCKAGE", "Coolant blockage", "CNC_MILL",
     "temperature_c", "Spindle temperature ramps ~+10 C over ~16 h with vibration unchanged",
     "temperature_c >= baseline + 10 C", 16),
    ("FM07", "MOTOR_OVERHEAT", "Drive motor overheating", "CONVEYOR|AIR_COMPRESSOR",
     "temperature_c|current_a", "Temperature and current rise together over ~18 h",
     "temperature_c >= baseline + 12 C", 18),
    ("FM08", "AIR_FILTER_CLOG", "Intake filter clogging", "AIR_COMPRESSOR",
     "pressure_bar|current_a", "Discharge pressure sags ~6% over ~2 days, current rises ~6%",
     "pressure_bar <= 0.94 x baseline", 48),
    ("FM09", "TOOL_WEAR", "Cutting tool / holder wear", "CNC_MILL",
     "current_a|vibration_rms", "Spindle current creeps up ~8% over ~24 h, slight vibration rise",
     "current_a >= 1.08 x baseline", 24),
    ("FM10", "OIL_CONTAMINATION", "Hydraulic oil contamination", "HYDRAULIC_PRESS",
     "temperature_c|pressure_bar", "Oil temperature creeps +6 C over ~2 days, pressure gets noisy",
     "temperature_c >= baseline + 6 C", 48),
]
FM_ID = {f[1]: f[0] for f in FAILURE_MODES}
FM_TYPES = {f[1]: f[3].split("|") for f in FAILURE_MODES}
FM_PRECURSOR_H = {f[1]: f[7] for f in FAILURE_MODES}

TECHNICIANS = [
    # id, name, seniority, years, skills (asset types), shift pattern, retiring_2027
    ("T01", "Ravi Kulkarni", "SENIOR", 31, "HYDRAULIC_PRESS|AIR_COMPRESSOR", "ROTATING", True),
    ("T02", "Suresh Patil", "SENIOR", 28, "CONVEYOR|HYDRAULIC_PRESS", "ROTATING", True),
    ("T03", "Meena Joshi", "MID", 11, "CNC_MILL|AIR_COMPRESSOR", "ROTATING", False),
    ("T04", "Arjun Deshmukh", "JUNIOR", 2, "HYDRAULIC_PRESS|CONVEYOR", "ROTATING", False),
    ("T05", "Farhan Shaikh", "MID", 8, "CNC_MILL", "ROTATING", False),
    ("T06", "Priya Nair", "MID", 6, "CONVEYOR|AIR_COMPRESSOR", "ROTATING", False),
    ("T07", "Vikram Rao", "MID", 9, "CNC_MILL|HYDRAULIC_PRESS", "ROTATING", False),
    ("T08", "Sneha Gaikwad", "JUNIOR", 1, "CNC_MILL|CONVEYOR", "ROTATING", False),
]
TECH_NAME = {t[0]: t[1] for t in TECHNICIANS}
TECH_FIRST = {t[0]: t[1].split()[0] for t in TECHNICIANS}

SPARE_PARTS = [
    # part_id, description, asset types, stock, reorder point, lead time days, unit cost INR
    ("BRG-6312", "Deep groove ball bearing 6312 (press DE)", "HYDRAULIC_PRESS", 1, 2, 21, 6800),
    ("BRG-6205", "Deep groove ball bearing 6205 (conveyor roller)", "CONVEYOR", 14, 6, 7, 450),
    ("BRG-7014", "Angular contact bearing 7014 (spindle)", "CNC_MILL", 3, 2, 30, 18500),
    ("BRG-6308", "Deep groove ball bearing 6308 (compressor motor)", "AIR_COMPRESSOR", 4, 2, 10, 2100),
    ("LUB-HT3", "High-temp bearing grease HT-3, 18 kg drum", "HYDRAULIC_PRESS", 1, 2, 10, 9200),
    ("LUB-LG2", "General bearing grease LG-2, 18 kg drum", "ALL", 6, 2, 5, 4100),
    ("OIL-HLP46", "Hydraulic oil HLP-46, 210 L barrel", "HYDRAULIC_PRESS", 5, 2, 7, 38000),
    ("OIL-COMP46", "Compressor oil, 20 L", "AIR_COMPRESSOR", 8, 3, 7, 7600),
    ("SEAL-P250-V", "Main cylinder seal kit (viton), HP-250", "HYDRAULIC_PRESS", 2, 2, 25, 14500),
    ("SEAL-P250-N", "Main cylinder seal kit (nitrile), HP-250", "HYDRAULIC_PRESS", 5, 2, 10, 6200),
    ("SEAL-P315-V", "Main cylinder seal kit (viton), HP-315", "HYDRAULIC_PRESS", 1, 1, 25, 17800),
    ("VLV-DCV-10", "Directional control valve NG10", "HYDRAULIC_PRESS", 1, 1, 35, 42000),
    ("VLV-DRN-AC", "Auto drain valve, compressor", "AIR_COMPRESSOR", 1, 1, 14, 5600),
    ("VLV-MPV-AC", "Minimum pressure valve kit", "AIR_COMPRESSOR", 2, 1, 21, 9800),
    ("FLT-AIR-SC37", "Air intake filter SC-37", "AIR_COMPRESSOR", 6, 3, 7, 3200),
    ("FLT-OIL-SC37", "Oil filter SC-37", "AIR_COMPRESSOR", 5, 3, 7, 1900),
    ("FLT-SEP-SC37", "Air/oil separator SC-37", "AIR_COMPRESSOR", 2, 1, 21, 12500),
    ("FLT-HYD-10", "Hydraulic return filter 10 micron", "HYDRAULIC_PRESS", 7, 3, 10, 2800),
    ("FLT-CLNT", "Coolant line filter", "CNC_MILL", 10, 4, 5, 650),
    ("BLT-CV-12", "Conveyor drive belt BC-12", "CONVEYOR", 2, 2, 12, 8900),
    ("BLT-VB-B52", "V-belt B52", "AIR_COMPRESSOR", 6, 2, 5, 780),
    ("MTR-CV-2K2", "Conveyor drive motor 2.2 kW", "CONVEYOR", 1, 1, 28, 31000),
    ("TNS-CV", "Belt tensioner assembly", "CONVEYOR", 2, 1, 14, 5400),
    ("RLR-CV", "Idler roller", "CONVEYOR", 20, 8, 7, 1100),
    ("CPL-JAW-38", "Jaw coupling spider 38", "ALL", 9, 3, 5, 520),
    ("SPN-CART-850", "Spindle cartridge VMC-850 (exchange)", "CNC_MILL", 0, 1, 45, 285000),
    ("HLD-BT40", "BT40 tool holder", "CNC_MILL", 12, 6, 10, 4800),
    ("PLL-DRAW", "Drawbar pull-stud set", "CNC_MILL", 4, 2, 14, 3600),
    ("INS-CNMG", "Carbide insert CNMG (box of 10)", "CNC_MILL", 30, 15, 5, 3900),
    ("PMP-CLNT", "Coolant pump 0.37 kW", "CNC_MILL", 1, 1, 21, 12800),
    ("NZL-CLNT", "Coolant nozzle set", "CNC_MILL", 8, 4, 5, 900),
    ("SNS-VIB", "Vibration sensor (accelerometer)", "ALL", 3, 2, 21, 14000),
    ("SNS-TMP-PT100", "PT100 temperature probe", "ALL", 5, 2, 10, 2300),
    ("SNS-PRS", "Pressure transducer 0-250 bar", "HYDRAULIC_PRESS", 2, 1, 21, 11200),
    ("CNT-3P-32", "Contactor 3-pole 32 A", "ALL", 4, 2, 7, 2600),
    ("OLR-25", "Thermal overload relay 17-25 A", "ALL", 3, 2, 7, 1800),
    ("FUS-HRC-63", "HRC fuse 63 A", "ALL", 15, 6, 5, 240),
    ("HOS-HYD-12", "Hydraulic hose 1/2in assembly", "HYDRAULIC_PRESS", 6, 3, 7, 2200),
    ("GKT-KIT-P", "Press gasket kit", "HYDRAULIC_PRESS", 3, 2, 14, 3100),
    ("SCR-AIR-KIT", "Screw element service kit", "AIR_COMPRESSOR", 1, 1, 30, 46000),
]

MODE_PARTS = {
    ("BEARING_WEAR", "CNC_MILL"): ["BRG-7014:1"],
    ("BEARING_WEAR", "AIR_COMPRESSOR"): ["BRG-6308:1", "LUB-LG2:1"],
    ("BEARING_WEAR", "CONVEYOR"): ["BRG-6205:2"],
    ("SEAL_LEAK", "HYDRAULIC_PRESS"): ["SEAL-P250-N:1", "OIL-HLP46:1"],
    ("SPINDLE_MISALIGNMENT", "CNC_MILL"): ["CPL-JAW-38:1"],
    ("BELT_SLIP", "CONVEYOR"): ["BLT-CV-12:1"],
    ("VALVE_STICKING", "HYDRAULIC_PRESS"): ["VLV-DCV-10:1"],
    ("VALVE_STICKING", "AIR_COMPRESSOR"): ["VLV-MPV-AC:1"],
    ("COOLANT_BLOCKAGE", "CNC_MILL"): ["FLT-CLNT:1", "NZL-CLNT:1"],
    ("MOTOR_OVERHEAT", "CONVEYOR"): ["OLR-25:1"],
    ("MOTOR_OVERHEAT", "AIR_COMPRESSOR"): ["BLT-VB-B52:2"],
    ("AIR_FILTER_CLOG", "AIR_COMPRESSOR"): ["FLT-AIR-SC37:1"],
    ("TOOL_WEAR", "CNC_MILL"): ["HLD-BT40:1", "INS-CNMG:1"],
    ("OIL_CONTAMINATION", "HYDRAULIC_PRESS"): ["FLT-HYD-10:1", "OIL-HLP46:1"],
}

# =============================================================================
# Messy human text
# =============================================================================
ABBREV = [("bearing", "brg"), ("changed", "chngd"), ("replaced", "repl"), ("vibration", "vib"),
          ("temperature", "temp"), ("production", "prodn"), ("maintenance", "mntc"), ("please", "pls"),
          ("checked", "chkd"), ("tomorrow", "tmrw"), ("pressure", "press."), ("because", "bcoz"),
          ("running", "rnng"), ("problem", "prob")]
HINGLISH = ["theek hai.", "kal dekhte hain.", "abhi chal raha hai.", "bol diya supervisor ko.",
            "dhyan rakhna.", "sab normal.", "thoda noise hai par ok.", "baaki sab theek.",
            "chai break extend hua.", "jaldi kar diya.", "Anjali ma'am ko inform kiya."]

WO_TEMPLATES = {
    "BEARING_WEAR": ["{a} bearing noise, vibration high. replaced bearing. trial ok",
                     "{a} brg gone, changed bearing and greased. running normal",
                     "{a} abnormal sound from bearing side, bearing replaced, alignment checked"],
    "SEAL_LEAK": ["{a} oil leak from main cyl seal. seal kit replaced, leak stopped, oil topped up",
                  "hyd leakage {a} - seal changed, topped up oil 20L, pressure ok now",
                  "{a} pressure not holding, found seal damaged. replaced seal kit."],
    "SPINDLE_MISALIGNMENT": ["{a} spindle vibration high, realigned spindle + coupling spider replaced",
                             "{a} chatter marks on job, spindle alignment checked and corrected"],
    "BELT_SLIP": ["{a} belt slipping, belt replaced and tension set",
                  "{a} conveyor jerking, belt worn. new belt fitted, tension adjusted"],
    "VALVE_STICKING": ["{a} pressure fluctuating, valve sticking. valve cleaned/replaced",
                       "{a} valve stuck intermittently, replaced valve, pressure stable"],
    "COOLANT_BLOCKAGE": ["{a} spindle temp high, coolant line choked. filter + nozzles cleaned/replaced",
                         "{a} coolant flow low, blockage in line, flushed and filter changed"],
    "MOTOR_OVERHEAT": ["{a} motor tripping on overload, temp high. checked, overload relay replaced",
                       "{a} motor hot, belt/cooling checked, relay changed, running ok"],
    "AIR_FILTER_CLOG": ["{a} discharge pressure low, intake filter choked. filter replaced",
                        "{a} air filter dirty, replaced. pressure back to normal"],
    "TOOL_WEAR": ["{a} spindle load high, tool holder worn. holder + inserts changed",
                  "{a} surface finish bad, tool worn out. replaced"],
    "OIL_CONTAMINATION": ["{a} oil temp high and oil looks milky. return filter changed, oil top up",
                          "{a} hyd oil contaminated, filter replaced, partial oil change done"],
}
PM_TEMPLATES = ["{a} PM done - greasing, bolts tightened, filters cleaned.",
                "{a} monthly PM completed. all ok.",
                "{a} PM: lubrication done, belts chkd, no abnormality.",
                "{a} preventive maint done as per checklist.",
                "{a} PM - cleaning + lube + electrical tightness chk done."]
INSP_TEMPLATES = ["{a} inspection done, no issue found.",
                  "{a} routine inspection - vib and temp readings normal.",
                  "{a} walkdown inspection ok, minor oil seepage noted, monitor."]

CHATTER = ["L1 target achieved.", "L2 short by {n} pcs due to material delay.", "L3 running ok.",
           "Material for L2 came late.", "Housekeeping done near L1.", "Safety talk done at shift start.",
           "Canteen AC not working.", "Forklift battery low, informed stores.", "Power dip at {h}:{m}, all restarted ok.",
           "Visitors from customer audit in afternoon.", "QC hold on 2 bins at L3, cleared later.",
           "Compressed air pressure bit low in morning.", "New operator trainee on L2.",
           "Tool crib closed early.", "Scrap bin full at L1, called housekeeping.", "L1 changeover took {n} min.",
           "Coolant topped up on CNC machines.", "All machines running at shift end.", "Gate pass issue for contractor."]


CASUAL = {  # how people actually describe problems in a handover
    "BEARING_WEAR": ["noise from brg side", "abnormal sound", "vib issue"],
    "SEAL_LEAK": ["oil leak", "leakage", "pressure not holding"],
    "SPINDLE_MISALIGNMENT": ["spindle vib", "chatter marks on job"],
    "BELT_SLIP": ["belt slipping", "conveyor jerking"],
    "VALVE_STICKING": ["pressure fluctuating", "valve issue"],
    "COOLANT_BLOCKAGE": ["coolant not coming", "spindle hot"],
    "MOTOR_OVERHEAT": ["motor tripping", "motor hot"],
    "AIR_FILTER_CLOG": ["air pressure low", "low discharge"],
    "TOOL_WEAR": ["finish problem", "spindle load high"],
    "OIL_CONTAMINATION": ["oil temp high", "oil looks milky"],
}


def messify(text: str, r: random.Random, hinglish_p: float = 0.35) -> str:
    for full, short in ABBREV:
        if full in text and r.random() < 0.6:
            text = text.replace(full, short)
    words = text.split(" ")
    for i, w in enumerate(words):
        if len(w) > 4 and w.isalpha() and r.random() < 0.04:
            j = r.randrange(len(w) - 1)
            words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    text = " ".join(words)
    if r.random() < 0.3:
        text = text.lower()
    if r.random() < hinglish_p:
        text = text + " " + r.choice(HINGLISH)
    return text


# =============================================================================
# Events (maintenance history) — golden + background
# =============================================================================
def overlaps(a0, a1, b0, b1, buffer=timedelta(0)):
    return a0 < b1 + buffer and b0 < a1 + buffer


def build_events():
    """Return (events, work_orders). Each event drives sensors and/or downtime."""
    events = []  # dict(asset, mode, onset, reported, closed, kind, shape_scale, tech, parts, note, key)

    for g in S.GOLDEN_EVENTS:
        events.append(dict(asset=S.GOLDEN_ASSET, mode="BEARING_WEAR", onset=g["onset"], reported=g["reported"],
                           closed=g["closed"], kind="CORRECTIVE", scale=1.0, dur_scale=1.0, tech=g["tech"],
                           parts=g["parts"], note=g["note"], key=g["key"], priority="HIGH"))

    # Reserved windows where nothing else may happen on an asset.
    reserved = {a[0]: [] for a in ASSETS}
    for e in events:  # keep 2 days before each golden onset clean (baseline for pattern matching)
        reserved[e["asset"]].append((e["onset"] - timedelta(days=2), e["closed"]))
    quiet_from = S.at(S.FINAL_DAY - 3, 0)  # keep the last days clean for the live demo
    for d in S.DECOYS:
        reserved[d["asset"]].append((d["onset"], END))
    reserved[S.GOLDEN_ASSET].append((S.LIVE_ONSET, END))

    def free(asset, t0, t1, buffer_h=12):
        return all(not overlaps(t0, t1, r0, r1, timedelta(hours=buffer_h)) for r0, r1 in reserved[asset])

    # Preventive maintenance + inspections: every asset roughly every 11 days, shift A.
    r = rng("pm")
    for a in ASSETS:
        aid, atype = a[0], a[2]
        day = r.randint(1, 10)
        while day < S.FINAL_DAY - 3:
            for shift_try in range(6):
                t0 = S.at(day + shift_try, 8, r.choice([0, 30]))
                dur = timedelta(minutes=r.choice([45, 60, 90, 120]))
                if free(aid, t0, t0 + dur, buffer_h=6) and t0 + dur < quiet_from:
                    kind = "INSPECTION" if r.random() < 0.3 else "PREVENTIVE"
                    techs = [t[0] for t in TECHNICIANS if atype in t[4]]
                    tech = r.choice(techs)
                    tmpl = r.choice(INSP_TEMPLATES if kind == "INSPECTION" else PM_TEMPLATES)
                    parts = "LUB-LG2:1" if kind == "PREVENTIVE" and "greas" in tmpl and aid != "P3" else ""
                    events.append(dict(asset=aid, mode=None, onset=None, reported=t0, closed=t0 + dur, kind=kind,
                                       tech=tech, parts=parts, note=messify(tmpl.format(a=aid), r, 0.2),
                                       key=None, priority="LOW"))
                    reserved[aid].append((t0, t0 + dur))
                    break
            day += r.randint(9, 13)

    # Corrective (breakdown) background events: 50, most with a sensor precursor.
    r = rng("corrective")
    weights = {a[0]: 1.0 for a in ASSETS}
    target, attempts = 50, 0
    n = 0
    while n < target and attempts < 5000:
        attempts += 1
        aid = r.choices([a[0] for a in ASSETS], weights=[weights[a[0]] for a in ASSETS])[0]
        atype = ASSET_BY_ID[aid][2]
        modes = [m for m, types in FM_TYPES.items() if atype in types]
        if atype == "HYDRAULIC_PRESS":
            modes = [m for m in modes if m != "BEARING_WEAR"]  # keep P3's pattern unique among presses
        mode = r.choice(modes)
        sudden = r.random() < 0.2
        dur_scale = r.uniform(0.8, 1.2)
        precursor = timedelta(hours=0 if sudden else FM_PRECURSOR_H[mode] * dur_scale)
        reported = S.at(r.randint(3, S.FINAL_DAY - 6), r.randint(0, 23), r.choice([0, 15, 30, 45]))
        onset = reported - precursor
        repair = timedelta(minutes=r.choice([60, 90, 120, 150, 180, 240, 300, 360]))
        closed = reported + repair
        if onset < S.START + timedelta(days=1) or closed > quiet_from or not free(aid, onset, closed, 24):
            continue
        techs = [t[0] for t in TECHNICIANS if atype in t[4]]
        tech = r.choice(techs)
        parts = r.choice([MODE_PARTS[(mode, atype)], MODE_PARTS[(mode, atype)][:1]])
        note = messify(r.choice(WO_TEMPLATES[mode]).format(a=aid), r)
        events.append(dict(asset=aid, mode=mode, onset=None if sudden else onset, reported=reported, closed=closed,
                           kind="CORRECTIVE", scale=r.uniform(0.85, 1.15), dur_scale=dur_scale, tech=tech,
                           parts=";".join(parts), note=note, key=None,
                           priority=r.choice(["HIGH", "MEDIUM", "MEDIUM"])))
        reserved[aid].append((onset, closed))
        n += 1
    assert n == target, f"could only place {n} corrective events"

    # Work orders, numbered chronologically by reported time.
    events.sort(key=lambda e: (e["reported"], e["asset"]))
    r = rng("wo")
    work_orders = []
    for i, e in enumerate(events, start=1):
        e["wo_id"] = f"WO-2026-{i:04d}"
        started = e["reported"] + (timedelta(minutes=r.choice([10, 15, 20, 30])) if e["kind"] == "CORRECTIVE"
                                   else timedelta(0))
        # Planner's failure-mode code is sometimes left blank on corrective WOs (realism).
        fm_code = e["mode"] if e["mode"] and (e["key"] or r.random() > 0.12) else ""
        work_orders.append(dict(
            wo_id=e["wo_id"], asset_id=e["asset"], wo_type=e["kind"], priority=e["priority"],
            failure_mode_code=fm_code, reported_at=ts(e["reported"]), started_at=ts(started),
            closed_at=ts(e["closed"]),
            downtime_min=int((e["closed"] - e["reported"]).total_seconds() // 60),
            technician_id=e["tech"], parts_used=e["parts"], resolution_note=e["note"], status="CLOSED"))
    return events, work_orders


# =============================================================================
# Sensor readings
# =============================================================================
def shape(mode: str, h: float, dur: float, scale: float):
    """Deviation at h hours after onset. Returns (dvib_frac, dtemp_c, dpress_frac, dcurr_frac, vib_noise_x,
    press_noise_x, curr_noise_x). For ongoing events h is clamped by the caller."""
    x = max(0.0, min(h / dur, 1.0))
    z = (0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    if mode == "BEARING_WEAR":
        a = S.BEARING_PHASE_A_H / S.BEARING_PRECURSOR_H * dur
        lag = S.BEARING_TEMP_LAG_H / S.BEARING_PRECURSOR_H * dur
        if h <= a:
            vib = S.BEARING_VIB_PHASE_A * h / a
        else:
            vib = S.BEARING_VIB_PHASE_A + (S.BEARING_VIB_AT_FAILURE - S.BEARING_VIB_PHASE_A) * min((h - a) / (dur - a), 1)
        if h < lag:
            temp = 0.0
        elif h <= a:
            temp = S.BEARING_TEMP_PHASE_A_C * (h - lag) / (a - lag)
        else:
            temp = S.BEARING_TEMP_PHASE_A_C + (S.BEARING_TEMP_AT_FAILURE_C - S.BEARING_TEMP_PHASE_A_C) * min((h - a) / (dur - a), 1)
        curr = 0.02 * max(0.0, min((h - a) / (dur - a), 1)) if h > a else 0.0
        return (vib * scale, temp * scale, 0.0, curr, 1.0, 1.0, 1.0)
    if mode == "SEAL_LEAK":
        return (0.0, 0.0, -0.08 * x * scale, 0.04 * x * scale, 1.0, 1.0, 1.0)
    if mode == "SPINDLE_MISALIGNMENT":
        return ((0.20 + 0.10 * x) * scale, 0.0, 0.0, 0.05 * x * scale, 1.0, 1.0, 1.0)
    if mode == "BELT_SLIP":
        return (0.22 * scale, 0.0, 0.0, 0.0, 2.0, 1.0, 4.0)
    if mode == "VALVE_STICKING":
        return (0.0, 0.0, 0.0, 0.0, 1.0, 1.0 + 4.0 * x * scale, 1.0)
    if mode == "COOLANT_BLOCKAGE":
        return (0.0, 10.0 * x * scale, 0.0, 0.0, 1.0, 1.0, 1.0)
    if mode == "MOTOR_OVERHEAT":
        return (0.0, 12.0 * x * scale, 0.0, 0.08 * x * scale, 1.0, 1.0, 1.0)
    if mode == "AIR_FILTER_CLOG":
        return (0.0, 0.0, -0.06 * x * scale, 0.06 * x * scale, 1.0, 1.0, 1.0)
    if mode == "TOOL_WEAR":
        return (0.05 * x * scale, 0.0, 0.0, 0.08 * x * scale, 1.0, 1.0, 1.0)
    if mode == "OIL_CONTAMINATION":
        return (0.0, 6.0 * x * scale, 0.0, 0.0, 1.0, 2.0, 1.0)
    return z


def build_sensors(events):
    # Per-asset effect windows: (start_idx, end_idx, fn(h) -> shape tuple) and downtime masks.
    effects = {a[0]: [] for a in ASSETS}
    down = {a[0]: [] for a in ASSETS}
    for e in events:
        if e["kind"] == "CORRECTIVE":
            if e["onset"] is not None:
                dur = FM_PRECURSOR_H[e["mode"]] * e["dur_scale"]
                effects[e["asset"]].append((idx(e["onset"]), idx(e["reported"]), e["onset"], e["mode"], dur, e["scale"]))
            down[e["asset"]].append((idx(e["reported"]), idx(e["closed"])))
        else:
            down[e["asset"]].append((idx(e["reported"]), idx(e["closed"])))
    effects[S.GOLDEN_ASSET].append((idx(S.LIVE_ONSET), N_STEPS, S.LIVE_ONSET, "BEARING_WEAR",
                                    float(S.BEARING_PRECURSOR_H), 1.0))
    for d in S.DECOYS:
        effects[d["asset"]].append((idx(d["onset"]), N_STEPS, d["onset"], d["mode"], float(d["dur_h"]), 1.0))

    rows = []
    for a in ASSETS:
        aid, atype = a[0], a[2]
        base = ASSET_TYPES[atype]
        r = rng("sensor", aid)
        jit = {k: (v * r.uniform(0.95, 1.05) if v is not None else None) for k, v in base.items()}
        day_offset = [r.gauss(0, 0.005) for _ in range(S.DAYS + 1)]
        phase = r.uniform(-1.0, 1.0)
        down_mask = bytearray(N_STEPS)
        for s0, s1 in down[aid]:
            for i in range(max(0, s0), min(N_STEPS, s1)):
                down_mask[i] = 1
        eff_by_idx = {}
        for s0, s1, onset, mode, dur, scale in effects[aid]:
            for i in range(max(0, s0), min(N_STEPS, s1)):
                h = i * S.STEP_MIN / 60 - (onset - S.START).total_seconds() / 3600
                eff_by_idx[i] = shape(mode, h, dur, scale)
        for i in range(N_STEPS):
            t = S.START + timedelta(minutes=S.STEP_MIN * i)
            hour = t.hour + t.minute / 60
            ambient = 2.5 * math.sin(2 * math.pi * (hour - 9 + phase) / 24)
            load = 1 + 0.03 * math.sin(2 * math.pi * (hour - 10 + phase) / 24) + day_offset[i // 288]
            dv, dt, dp, dc, nv, np_, nc = eff_by_idx.get(i, (0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0))
            if down_mask[i]:
                vib = jit["vib"] * 0.12 * (1 + r.gauss(0, 0.05))
                temp = jit["temp"] * 0.8 + ambient + r.gauss(0, 0.4)
                pres = jit["pressure"] * 0.05 * (1 + r.gauss(0, 0.05)) if jit["pressure"] else None
                cur = jit["current"] * 0.06 * (1 + r.gauss(0, 0.05))
            else:
                vib = jit["vib"] * load * (1 + dv) * (1 + r.gauss(0, 0.02 * nv))
                temp = jit["temp"] + ambient + dt + r.gauss(0, 0.4)
                pres = jit["pressure"] * (1 + dp) * (1 + r.gauss(0, 0.008 * np_)) if jit["pressure"] else None
                cur = jit["current"] * load * (1 + dc) * (1 + r.gauss(0, 0.015 * nc))
            rows.append((aid, ts(t), f"{vib:.3f}", f"{temp:.2f}", "" if pres is None else f"{pres:.2f}", f"{cur:.2f}"))
    return rows


# =============================================================================
# Handover notes
# =============================================================================
SHIFTS = {"A": 6, "B": 14, "C": 22}


def shift_window(day: int, shift: str):
    s = S.at(day, SHIFTS[shift])
    return s, s + timedelta(hours=8)


def build_handover(events):
    r = rng("handover")
    notes = []
    fragments = {(d, s): (a, t) for d, s, a, t in S.FRAGMENTS}
    gotchas = {(g[0], g[1]): g for g in S.GOTCHAS}
    for day in range(S.DAYS):
        for shift in "ABC":
            s0, s1 = shift_window(day, shift)
            if s0 >= END:
                continue
            if (day, shift) == (S.CLEAR_NOTE["day"], S.CLEAR_NOTE["shift"]):
                notes.append([s1, S.CLEAR_NOTE["author"], S.CLEAR_NOTE["text"], "SHIFT"])
                continue
            author = r.choice([t[0] for t in TECHNICIANS])
            parts = []
            opener = r.choice([f"Handover {shift} shift.", f"{shift} shift handover -", "", f"Shift {shift}:"])
            if opener:
                parts.append(opener)
            for c in r.sample(CHATTER, r.randint(1, 3)):
                parts.append(c.format(n=r.randint(15, 90), h=r.randint(0, 23), m=f"{r.randint(0, 59):02d}"))
            extra = []
            for e in events:
                if e["key"] is not None:
                    continue  # golden episodes are narrated only via the pinned fragments
                if e["kind"] == "CORRECTIVE" and s0 <= e["reported"] < s1:
                    label = r.choice(CASUAL[e["mode"]])
                    parts.append(f"{e['asset']} {label} reported, {TECH_FIRST[e['tech']]} attending.")
                    if r.random() < 0.45:
                        extra.append(e)
                elif e["kind"] == "CORRECTIVE" and s0 <= e["closed"] < s1:
                    parts.append(r.choice([f"{e['asset']} back in production.", f"{e['asset']} running after repair."]))
                elif e["kind"] != "CORRECTIVE" and s0 <= e["reported"] < s1 and r.random() < 0.5:
                    parts.append(f"{e['asset']} PM done.")
            text = messify(" ".join(parts), r)
            if (day, shift) in gotchas:
                g = gotchas[(day, shift)]
                author = g[2]
                cut = r.randint(1, max(1, len(parts) - 1))
                text = messify(" ".join(parts[:cut]), r, 0) + " " + g[6] + " " + messify(" ".join(parts[cut:]), r)
            if (day, shift) in fragments:
                author, frag = fragments[(day, shift)]
                text = text + " " + frag
            notes.append([s1, author, text.strip(), "SHIFT"])
            for e in extra:
                t = min(s1 - timedelta(minutes=5), e["reported"] + timedelta(hours=r.randint(1, 4)))
                upd = messify(r.choice([f"{e['asset']} update: parts arranged, work in progress.",
                                        f"{e['asset']} update - still checking, may take more time.",
                                        f"addl note {e['asset']}: root cause looks like {(e['mode'] or 'unknown').lower().replace('_', ' ')}."]), r)
                notes.append([t, e["tech"], upd, "ADHOC"])
    notes.sort(key=lambda n: n[0])
    out = []
    for i, (t, author, text, kind) in enumerate(notes, start=1):
        # shift_date/shift are derived from created_at (end of shift or ad-hoc time).
        start = t - timedelta(minutes=1)
        hour = start.hour
        shift = "A" if 6 <= hour < 14 else ("B" if 14 <= hour < 22 else "C")
        shift_date = (start - timedelta(hours=6) if shift == "C" and hour < 6 else start).date()
        line = next((ASSET_BY_ID[x][3] for x in ASSET_BY_ID if f"{x} " in text), "ALL")
        out.append(dict(note_id=f"HN-{i:04d}", created_at=ts(t), shift_date=str(shift_date), shift=shift,
                        note_type=kind, line_id=line if kind == "ADHOC" else "ALL",
                        author_technician_id=author, note_text=text))
    return out


# =============================================================================
# Production log (OEE inputs) — production assets only; compressors are utilities.
# =============================================================================
def minutes_overlap(a0, a1, b0, b1):
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds() / 60)


def build_production(events):
    r = rng("production")
    rows = []
    for a in ASSETS:
        aid, ideal = a[0], a[7]
        if ideal is None:
            continue
        evs = [e for e in events if e["asset"] == aid]
        for day in range(S.DAYS):
            for shift in "ABC":
                s0, s1 = shift_window(day, shift)
                if s1 > END:
                    continue  # final C shift crosses end of data
                planned = 450.0 - sum(minutes_overlap(s0, s1, e["reported"], e["closed"]) for e in evs if e["kind"] != "CORRECTIVE")
                breakdown = sum(minutes_overlap(s0, s1, e["reported"], e["closed"]) for e in evs if e["kind"] == "CORRECTIVE")
                minor = r.randint(0, 20)
                planned = max(0.0, planned)
                run = max(0.0, planned - breakdown - minor)
                perf = r.uniform(0.86, 0.96)
                total = int(run * 60 / ideal * perf)
                good = int(round(total * r.uniform(0.965, 0.995)))
                rows.append(dict(asset_id=aid, line_id=a[3], shift_date=str(s0.date()), shift=shift,
                                 planned_time_min=int(round(planned)), run_time_min=int(round(run)),
                                 downtime_min=int(round(planned - run)), ideal_cycle_time_s=ideal,
                                 total_count=total, good_count=good))
    return rows


def oee(rows, asset, date):
    rs = [x for x in rows if x["asset_id"] == asset and x["shift_date"] == date]
    planned = sum(x["planned_time_min"] for x in rs)
    run = sum(x["run_time_min"] for x in rs)
    total = sum(x["total_count"] for x in rs)
    good = sum(x["good_count"] for x in rs)
    ideal_s = sum(x["ideal_cycle_time_s"] * x["total_count"] for x in rs)
    A = run / planned if planned else 0.0
    P = ideal_s / (run * 60) if run else 0.0
    Q = good / total if total else 0.0
    return dict(asset_id=asset, date=date, availability=round(A, 4), performance=round(P, 4),
                quality=round(Q, 4), oee=round(A * P * Q, 4))


# =============================================================================
# Assemble everything
# =============================================================================
def generate():
    events, work_orders = build_events()
    sensors = build_sensors(events)
    handover = build_handover(events)
    production = build_production(events)

    tables = {
        "assets": (["asset_id", "asset_name", "asset_type", "line_id", "install_date", "firmware_version",
                    "model", "ideal_cycle_time_s", "criticality"],
                   [list(a[:7]) + ["" if a[7] is None else a[7], "A" if a[2] in ("HYDRAULIC_PRESS", "AIR_COMPRESSOR") else "B"]
                    for a in ASSETS]),
        "failure_modes": (["failure_mode_id", "code", "name", "applicable_asset_types", "primary_sensors",
                           "signature_description", "threshold_rule", "typical_precursor_h"],
                          [list(f) for f in FAILURE_MODES]),
        "technicians": (["technician_id", "full_name", "seniority", "years_experience", "skills", "shift_pattern",
                         "retiring_2027"], [list(t[:6]) + [str(t[6]).upper()] for t in TECHNICIANS]),
        "spare_parts": (["part_id", "description", "asset_types", "stock_qty", "reorder_point", "lead_time_days",
                         "unit_cost_inr"], [list(p) for p in SPARE_PARTS]),
        "asset_changes": (["change_id", "asset_id", "changed_at", "change_type", "description"],
                          [[f"AC-{i:03d}", c[2], ts(S.at(c[0], c[1])), c[3], c[4]]
                           for i, c in enumerate(sorted(S.ASSET_CHANGES, key=lambda c: (c[0], c[1], c[2])), start=1)]),
        "work_orders": (list(work_orders[0].keys()), [list(w.values()) for w in work_orders]),
        "handover_notes": (list(handover[0].keys()), [list(h.values()) for h in handover]),
        "production_log": (list(production[0].keys()), [list(p.values()) for p in production]),
        "sensor_readings": (["asset_id", "ts", "vibration_rms", "temperature_c", "pressure_bar", "current_a"], sensors),
    }
    answer_key = build_answer_key(events, work_orders, handover, production)
    return tables, answer_key, events


def build_answer_key(events, work_orders, handover, production):
    wo = {e["key"]: e["wo_id"] for e in events if e["key"]}
    clear = next(h for h in handover if S.CLEAR_FIX_PHRASE in h["note_text"])
    gotcha_notes = {}
    for g in S.GOTCHAS:
        gotcha_notes[g[3]] = next(h["note_id"] for h in handover if g[7] in h["note_text"])
    p3_fm = "BEARING_WEAR"
    cards = [
        dict(ref="C1", card_type="FIX", asset_id="P3", failure_mode=p3_fm, outcome="RESOLVED",
             author_technician_id=S.RAVI, source_type="HANDOVER_NOTE", source_id=clear["note_id"],
             excerpt_contains="switch grease from LG-2 to HT-3", must_mention=["bearing", "HT-3"]),
        dict(ref="C2", card_type="GOTCHA", asset_id="P3", failure_mode=p3_fm, outcome="RECURRED",
             author_technician_id=S.RAVI, source_type="HANDOVER_NOTE", source_id=clear["note_id"],
             excerpt_contains="Only bearing change does NOT hold", must_mention=["bearing", "9 days"]),
        dict(ref="C3", card_type="SYMPTOM_PATTERN", asset_id="P3", failure_mode=p3_fm, outcome="UNKNOWN",
             author_technician_id=S.RAVI, source_type="HANDOVER_NOTE", source_id=clear["note_id"],
             excerpt_contains="temperature also starts rising", must_mention=["vibration", "temperature"]),
    ]
    for ref, key in (("C4", "E1"), ("C5", "J1"), ("C6", "E2"), ("C7", "E3")):
        g = next(x for x in S.GOLDEN_EVENTS if x["key"] == key)
        cards.append(dict(ref=ref, card_type="FIX", asset_id="P3", failure_mode=p3_fm, outcome=g["outcome"],
                          author_technician_id=g["tech"], source_type="WORK_ORDER", source_id=wo[key],
                          excerpt_contains=g["note"][:40],
                          must_mention=["bearing"] + ([] if key == "J1" else ["grease"]),
                          outcome_derivation=("recurrence rule: same asset + failure mode re-opened within 14 days"
                                              if key == "J1" else "stated in note")))
    for i, g in enumerate(S.GOTCHAS, start=8):
        cards.append(dict(ref=f"C{i}", card_type=g[4], asset_id=g[3], failure_mode=g[5], outcome="UNKNOWN",
                          author_technician_id=g[2], source_type="HANDOVER_NOTE", source_id=gotcha_notes[g[3]],
                          excerpt_contains=g[7], must_mention=[]))

    def win(e):
        return dict(key=e["key"], wo_id=e["wo_id"], onset=ts(e["onset"]), reported=ts(e["reported"]),
                    closed=ts(e["closed"]), technician_id=e["tech"])

    live_h = (END - timedelta(minutes=S.STEP_MIN) - S.LIVE_ONSET).total_seconds() / 3600
    vib_now = S.BEARING_VIB_PHASE_A * live_h / S.BEARING_PHASE_A_H
    phase_a_slope = S.BEARING_VIB_PHASE_A / S.BEARING_PHASE_A_H
    return {
        "_notice": "SYNTHETIC DATA. Generated by data_gen/generate.py (seed=42). Do not edit by hand.",
        "time_range": dict(start=ts(S.START), end_exclusive=ts(END), final_day=str((S.START + timedelta(days=S.FINAL_DAY)).date())),
        "expected_cards": cards,
        "expected_edges": [
            dict(from_ref="C6", to_ref="C5", relation="CONTRADICTS",
                 why="E2 is the recurrence 9 days after J1's bearing-only fix"),
            dict(from_ref="C1", to_ref="C5", relation="SUPERSEDES",
                 why="Ravi's documented fix (bearing + grease) supersedes bearing-only"),
        ],
        "golden_anomaly": dict(
            asset_id="P3", failure_mode=p3_fm, onset=ts(S.LIVE_ONSET), sensors=["vibration_rms", "temperature_c"],
            signature=dict(vib_rise_pct_at_end=round(100 * vib_now, 1), vib_slope_pct_per_h=round(100 * phase_a_slope, 3),
                           temp_lag_h=S.BEARING_TEMP_LAG_H, hours_observed=round(live_h, 2)),
            historical_matches=[win(e) for e in events if e["key"]],
            expected_episode_keys=["E1", "E2", "E3"],
            failure_window=dict(
                threshold="vibration_rms >= 1.35 x baseline",
                linear_extrapolation_h=round((S.BEARING_VIB_AT_FAILURE - vib_now) / phase_a_slope, 1),
                historical_analog_h=round(S.BEARING_PRECURSOR_H - live_h, 1),
                note="Estimate only. Linear extrapolation of the phase-A slope is the optimistic (high) bound; "
                     "historical episodes accelerated and failed at ~48 h from onset (low bound)."),
            expected_top3_retrieval=[
                dict(source_type="HANDOVER_NOTE", source_id=clear["note_id"], why="Ravi's explicit fix + gotcha + pattern"),
                dict(source_type="WORK_ORDER", source_id=wo["E2"], why="recurrence after bearing-only fix; bearing + HT-3"),
                dict(source_type="WORK_ORDER", source_id=wo["J1"], why="the bearing-only attempt that recurred (gotcha)"),
            ],
            hit_at_3_rule="PASS if the HANDOVER_NOTE card above is in the top 3",
            recommended_technician=S.RAVI,
            required_parts=["BRG-6312", "LUB-HT3"],
        ),
        "decoys": [dict(key=d["key"], asset_id=d["asset"], true_failure_mode=d["mode"], onset=ts(d["onset"]),
                        should_match_p3_bearing=False) for d in S.DECOYS],
        "expected_oee": [oee(production, a, str((S.START + timedelta(days=d)).date())) for a, d in S.OEE_KEY_DAYS],
        "oee_formula": "A = sum(run)/sum(planned); P = sum(ideal_cycle_s*total)/(sum(run)*60); Q = sum(good)/sum(total); OEE = A*P*Q (per asset per shift_date)",
    }


def to_csv_bytes(header, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def serialize(tables, answer_key):
    files = {f"{name}.csv": to_csv_bytes(h, rows) for name, (h, rows) in tables.items()}
    ak = (json.dumps(answer_key, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return files, ak


# =============================================================================
# Verification
# =============================================================================
def verify(tables, answer_key, events, files, ak_bytes):
    failures = []

    def check(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            failures.append(msg)

    n = {k: len(v[1]) for k, v in tables.items()}
    print("Row counts:", json.dumps(n))
    check(n["assets"] == 12, "12 assets")
    check(n["technicians"] == 8 and sum(t[6] for t in TECHNICIANS) == 2, "8 technicians, 2 retiring_2027")
    check(n["failure_modes"] == 10, "10 failure modes")
    check(n["sensor_readings"] == 12 * N_STEPS, f"sensor_readings == {12 * N_STEPS}")
    check(140 <= n["work_orders"] <= 160, "work_orders ~150")
    check(270 <= n["handover_notes"] <= 330, "handover_notes ~300")
    check(35 <= n["spare_parts"] <= 45, "spare_parts ~40")
    check(12 <= n["asset_changes"] <= 18, "asset_changes ~15")

    wo_hdr, wo_rows = tables["work_orders"]
    wos = [dict(zip(wo_hdr, r)) for r in wo_rows]
    p3b = [w for w in wos if w["asset_id"] == "P3" and w["failure_mode_code"] == "BEARING_WEAR"]
    check(len(p3b) == 4, "exactly 4 P3 BEARING_WEAR work orders (3 Ravi + 1 junior)")
    ravi = [w for w in p3b if w["technician_id"] == S.RAVI]
    check(len(ravi) == 3 and all("LUB-HT3" in w["parts_used"] and "BRG-6312" in w["parts_used"] for w in ravi),
          "Ravi fixed P3 3 times, each with bearing + HT-3 grease")
    jr = [w for w in p3b if w["technician_id"] == S.ARJUN]
    check(len(jr) == 1 and jr[0]["parts_used"] == "BRG-6312:1", "junior did one bearing-only fix")
    e2 = next(w for w in p3b if w["wo_id"] == next(e["wo_id"] for e in events if e["key"] == "E2"))
    gap = datetime.strptime(e2["reported_at"], TS_FMT) - datetime.strptime(jr[0]["closed_at"], TS_FMT)
    check(gap == timedelta(days=9), f"recurrence gap after bearing-only fix is 9 days (got {gap})")
    check(not any(w["asset_id"] in ("P1", "P2") and w["failure_mode_code"] == "BEARING_WEAR" for w in wos),
          "no bearing-wear history on P1/P2 (P3 pattern is unique among presses)")

    # Sensor invariants
    s_hdr, s_rows = tables["sensor_readings"]
    by_asset = {}
    for row in s_rows:
        by_asset.setdefault(row[0], []).append(row)

    def series(asset, col):
        c = s_hdr.index(col)
        return [float(r[c]) if r[c] != "" else None for r in by_asset[asset]]

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs)

    vib, temp = series("P3", "vibration_rms"), series("P3", "temperature_c")
    for e in [e for e in events if e["key"]]:
        # Compare each window to the same clock time before onset (removes the daily cycle).
        o = idx(e["onset"])
        w36, w6 = slice(o + 34 * 12, o + 36 * 12), slice(o + 5 * 12, o + 7 * 12)
        b36, b6 = slice(w36.start - 48 * 12, w36.stop - 48 * 12), slice(w6.start - 24 * 12, w6.stop - 24 * 12)
        v36 = mean(vib[w36]) / mean(vib[b36])
        t6 = mean(temp[w6]) - mean(temp[b6])
        t36 = mean(temp[w36]) - mean(temp[b36])
        check(1.15 <= v36 <= 1.21, f"{e['key']}: P3 vibration +{100 * (v36 - 1):.1f}% at 36 h (~18%)")
        check(abs(t6) < 1.5 and 6.0 <= t36 <= 10.0, f"{e['key']}: temperature follows (+{t6:.1f} C at 6 h, +{t36:.1f} C at 36 h)")
    o = idx(S.LIVE_ONSET)
    live_v = mean(vib[-24:]) / mean(vib[-24 - 288:-288])
    live_t = mean(temp[-24:]) - mean(temp[-24 - 288:-288])
    check(1.09 <= live_v <= 1.15, f"LIVE: P3 vibration +{100 * (live_v - 1):.1f}% after ~24 h on final day")
    check(2.0 <= live_t <= 6.0, f"LIVE: P3 temperature starting to follow (+{live_t:.1f} C)")

    for d in S.DECOYS:
        o = idx(d["onset"])
        v, t = series(d["asset"], "vibration_rms"), series(d["asset"], "temperature_c")
        vr, tr = mean(v[-24:]) / mean(v[o - 288:o]), mean(t[-24:]) - mean(t[o - 288:o])
        if d["mode"] == "COOLANT_BLOCKAGE":
            check(tr >= 7 and abs(vr - 1) < 0.06, f"{d['key']} {d['asset']}: temp +{tr:.1f} C, vibration flat ({vr:.3f})")
        else:
            c = series(d["asset"], "current_a")
            sd = lambda xs: (sum((x - mean(xs)) ** 2 for x in xs) / len(xs)) ** 0.5  # noqa: E731
            check(vr >= 1.15 and abs(tr) < 2.0 and sd(c[-24:]) > 2.5 * sd(c[o - 288:o - 240]),
                  f"{d['key']} {d['asset']}: vibration step x{vr:.2f}, temp flat ({tr:+.1f} C), erratic current")

    quiet = S.at(S.FINAL_DAY - 3, 0)
    noisy = []
    for a in ASSETS:
        if a[0] in {S.GOLDEN_ASSET} | {d["asset"] for d in S.DECOYS}:
            continue
        q = idx(quiet)
        v, t = series(a[0], "vibration_rms"), series(a[0], "temperature_c")
        base_v, base_t = mean(v[q - 7 * 288:q]), mean(t[q - 7 * 288:q])
        for k in range(q, N_STEPS - 24, 24):
            if abs(mean(v[k:k + 24]) / base_v - 1) > 0.08 or abs(mean(t[k:k + 24]) - base_t) > 4:
                noisy.append(a[0])
                break
    check(not noisy, f"no other asset drifts in the final 3 days {noisy or ''}")

    # Handover invariants
    h_hdr, h_rows = tables["handover_notes"]
    texts = [r[h_hdr.index("note_text")] for r in h_rows]
    check(sum(S.CLEAR_FIX_PHRASE in t for t in texts) == 1, "clear fix written in exactly ONE handover note")
    check("lube change karo warna phir se aayega" in " ".join(texts), "Hinglish fragment present")
    frag = [t for t in texts if "P3" in t and any(k in t.lower() for k in ("grease", "lube", "brg"))
            and S.CLEAR_FIX_PHRASE not in t]
    check(len(frag) >= 3, f"fix appears in fragments elsewhere ({len(frag)} notes)")
    for g in S.GOTCHAS:
        check(sum(g[7] in t for t in texts) == 1, f"gotcha buried once: {g[3]} '{g[7]}'")

    # OEE answer key recomputes
    p_hdr, p_rows = tables["production_log"]
    prod = [dict(zip(p_hdr, r)) for r in p_rows]
    for exp in answer_key["expected_oee"]:
        got = oee(prod, exp["asset_id"], exp["date"])
        check(got == exp, f"OEE {exp['asset_id']} {exp['date']} = {exp['oee']}")
    p3_14 = answer_key["expected_oee"][0]
    check(p3_14["availability"] < 0.8, "P3 availability dips on E1 breakdown day")

    # Determinism: a second in-memory generation must be byte-identical.
    t2, ak2, _ = generate()
    files2, ak2_bytes = serialize(t2, ak2)
    same = all(hashlib.sha256(files[k]).digest() == hashlib.sha256(files2[k]).digest() for k in files) and ak_bytes == ak2_bytes
    check(same, "deterministic: regeneration is byte-identical")
    on_disk = HERE / "answer_key.json"
    if on_disk.exists():
        check(on_disk.read_bytes() == ak_bytes, "committed answer_key.json matches generator output")
    return failures


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true", help="assert golden-scenario invariants (writes nothing)")
    args = ap.parse_args()
    tables, answer_key, events = generate()
    files, ak_bytes = serialize(tables, answer_key)
    if args.verify:
        failures = verify(tables, answer_key, events, files, ak_bytes)
        print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
        sys.exit(1 if failures else 0)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
        print(f"wrote {OUT / name}  ({len(data) / 1e6:.2f} MB)")
    (HERE / "answer_key.json").write_bytes(ak_bytes)
    print(f"wrote {HERE / 'answer_key.json'}")
    print("checksums:", {k: hashlib.sha256(v).hexdigest()[:12] for k, v in files.items()})


if __name__ == "__main__":
    main()
