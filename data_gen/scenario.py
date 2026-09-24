"""Golden demo scenario for Plant Brain. ALL DATA IS SYNTHETIC.

Everything the demo and the evaluation depend on is pinned here as constants,
so the story reproduces exactly regardless of the random background data.

Story
-----
Hydraulic Press P3 (line L3) has a recurring DE-bearing wear pattern:
vibration creeps up ~18% over ~36 h, then temperature follows (lag ~12 h),
then things accelerate until the operator stops the machine at ~48 h.

  E1  day 14  Ravi K. (T01, retiring) replaces bearing + switches grease LG-2 -> HT-3   RESOLVED
  J1  day 40  Arjun D. (T04, junior) replaces bearing only                           RECURRED
  E2  day 49  recurrence exactly 9 days after J1 closed; Ravi does bearing + grease     RESOLVED
  E3  day 72  Ravi, bearing + grease again                                              RESOLVED
  LIVE day 89 (final day) the same precursor starts at 00:00 -> demo moment.

Ravi's fix is written clearly in exactly ONE handover note (day 49, shift B).
Fragments appear in other notes / work orders.

Decoys on the final day (must NOT match P3's bearing history):
  D1  CNC2  coolant blockage: temperature ramp, vibration flat
  D2  CV2   belt slip: vibration *step* (not ramp), current oscillation, temperature flat
"""
from datetime import datetime, timedelta

SEED = 42
START = datetime(2026, 6, 3)  # day 0, 00:00 plant local time (IST, stored as NTZ)
DAYS = 90
FINAL_DAY = DAYS - 1          # day 89 = 2026-08-31
STEP_MIN = 5


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return START + timedelta(days=day, hours=hour, minutes=minute)


# --- Bearing-wear shape (hours from onset) -------------------------------------
BEARING_PRECURSOR_H = 48      # onset -> operator stops machine / WO reported
BEARING_PHASE_A_H = 36        # vibration +18% linearly over first 36 h
BEARING_VIB_PHASE_A = 0.18
BEARING_VIB_AT_FAILURE = 0.35  # threshold used by the failure-window estimate
BEARING_TEMP_LAG_H = 12
BEARING_TEMP_PHASE_A_C = 8.0
BEARING_TEMP_AT_FAILURE_C = 15.0

GOLDEN_ASSET = "P3"
RAVI = "T01"
ARJUN = "T04"

# Golden P3 episodes. reported = onset + 48 h; downtime = reported -> closed.
GOLDEN_EVENTS = [
    dict(key="E1", onset=at(12, 6), closed=at(14, 12), tech=RAVI,
         parts="BRG-6312:1;LUB-HT3:1", outcome="RESOLVED",
         note="P3 vib badh raha tha 2 din se, temp bhi. DE brg 6312 gone. replaced + grease changed. ok"),
    dict(key="J1", onset=at(38, 10), closed=at(40, 13), tech=ARJUN,
         parts="BRG-6312:1", outcome="RECURRED",
         note="P3 DE side brg making noise, vib high. replaced brg 6312. trial run ok, vib normal ab. closed"),
    dict(key="E2", onset=at(47, 13), closed=at(49, 19), tech=RAVI,
         parts="BRG-6312:1;LUB-HT3:1", outcome="RESOLVED",
         note=("P3 same brg problem again - 9 din pehle sirf brg badla tha (Arjun), grease purana LG-2 hi tha "
               "isliye wapas aaya. brg 6312 + HT-3 grease dono kiye. flushed old grease fully.")),
    dict(key="E3", onset=at(70, 20), closed=at(73, 2), tech=RAVI,
         parts="BRG-6312:1;LUB-HT3:1", outcome="RESOLVED",
         note="P3 brg again, pattern same (vib up then temp). brg+HT3 done. told Anjali to keep 2 brg in stock"),
]
for _e in GOLDEN_EVENTS:
    _e["reported"] = _e["onset"] + timedelta(hours=BEARING_PRECURSOR_H)

LIVE_ONSET = at(FINAL_DAY, 0)   # P3 precursor starts on the final day, still running at end of data

DECOYS = [
    dict(key="D1", asset="CNC2", mode="COOLANT_BLOCKAGE", onset=at(FINAL_DAY, 4), dur_h=16),
    dict(key="D2", asset="CV2", mode="BELT_SLIP", onset=at(FINAL_DAY, 15), dur_h=6),
]

# --- Handover text ------------------------------------------------------------
CLEAR_FIX_PHRASE = "switch grease from LG-2 to HT-3"

# The ONE clear note (day 49, shift B, written by Ravi), buried in chatter.
CLEAR_NOTE = dict(
    day=49, shift="B", author=RAVI,
    text=("Handover B shift. L3 mostly ok, CV3 running slow due to material. "
          "IMPORTANT P3 NOTE (pls read): when P3 vibration starts creeping up slowly over 1-2 days and then "
          "temperature also starts rising, it is the DE bearing (6312) failing. Fix = replace bearing AND "
          "switch grease from LG-2 to HT-3 high-temp grade, flush old grease fully. Only bearing change does NOT "
          "hold - today it came back in 9 days after bearing-only job. Keep min 2 bearings + HT-3 in store. - Ravi. "
          "Baaki sab normal, canteen AC not working again."),
)

# Fragments appended to ordinary shift notes (day, shift, author, text).
FRAGMENTS = [
    (14, "B", "T02", "P3 back in prodn after Ravi bhai ne brg change kiya, grease bhi kuch alag daala."),
    (40, "B", "T04", "P3 brg done by Arjun, running."),
    (50, "A", "T03", "P3 ok. Ravi bol raha tha lube change karo warna phir se aayega - note kar lo sab."),
    (73, "A", "T07", "P3 back after brg+grease night mein. Ravi says same old story."),
    (80, "C", "T05", "P3 thoda noisy lag raha tha, chkd vib ok. false alarm."),
]

# Other tribal knowledge buried in chatter: (day, shift, author, asset, card_type, failure_mode, text, key_excerpt)
GOTCHAS = [
    (22, "C", "T02", "CV1", "GOTCHA", "MOTOR_OVERHEAT",
     "CV1 belt tension - dont overtighten beyond the yellow mark, motor trips on overload (happened twice).",
     "dont overtighten beyond the yellow mark"),
    (31, "A", "T06", "AC2", "GOTCHA", "VALVE_STICKING",
     "AC2 auto drain valve sticks, drain manually every shift start otherwise water goes in line and L3 pneumatics act up.",
     "drain manually every shift start"),
    (45, "B", "T05", "CNC3", "CONVENTION", None,
     "CNC3 after any power cut do ref return (home) first, else alarm 1041 and axis crash risk.",
     "do ref return (home) first"),
    (58, "A", "T02", "P1", "GOTCHA", "SEAL_LEAK",
     "P1 seal kit - use the viton one from rack B, nitrile one fails in 2-3 days at our temp.",
     "use the viton one from rack B"),
    (63, "B", "T03", "CNC1", "CONVENTION", None,
     "CNC1 new firmware v4.2 - spindle warmup program 10 min is mandatory now before first job.",
     "spindle warmup program 10 min is mandatory"),
]

# Asset change log (feeds the staleness stretch feature). (day, hour, asset, change_type, description)
ASSET_CHANGES = [
    (14, 12, "P3", "PART_REPLACEMENT", "DE bearing 6312 replaced (WO E1)"),
    (14, 12, "P3", "LUBRICANT_CHANGE", "Bearing grease grade LG-2 -> HT-3"),
    (40, 13, "P3", "PART_REPLACEMENT", "DE bearing 6312 replaced (WO J1)"),
    (49, 19, "P3", "PART_REPLACEMENT", "DE bearing 6312 replaced (WO E2)"),
    (49, 19, "P3", "LUBRICANT_CHANGE", "Old grease flushed, HT-3 re-applied"),
    (73, 2, "P3", "PART_REPLACEMENT", "DE bearing 6312 replaced (WO E3)"),
    (20, 10, "CNC3", "FIRMWARE_UPDATE", "Controller firmware v3.8 -> v3.9"),
    (25, 9, "CNC2", "PART_REPLACEMENT", "Spindle cartridge rebuilt"),
    (35, 11, "CV3", "PART_REPLACEMENT", "Drive belt replaced"),
    (44, 10, "AC1", "FIRMWARE_UPDATE", "Compressor controller firmware v2.1 -> v2.2"),
    (58, 9, "P1", "PART_REPLACEMENT", "Main cylinder seal kit type changed nitrile -> viton"),
    (60, 10, "CV1", "PART_REPLACEMENT", "Drive motor replaced (same rating)"),
    (62, 8, "CNC1", "FIRMWARE_UPDATE", "Controller firmware v4.1 -> v4.2"),
    (77, 11, "AC2", "PART_REPLACEMENT", "Auto drain valve replaced with new model"),
    (84, 10, "CNC4", "FIRMWARE_UPDATE", "Controller firmware v4.1 -> v4.2"),
]

# Asset-days whose OEE is pinned in answer_key.json.
OEE_KEY_DAYS = [("P3", 14), ("CNC1", 30), ("CV2", FINAL_DAY)]
