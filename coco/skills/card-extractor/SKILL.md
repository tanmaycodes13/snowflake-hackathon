---
name: card-extractor
description: Rules for turning messy maintenance text (work-order resolution notes, shift handover notes, closing notes) into Plant Brain knowledge cards. Use when writing or changing the extraction prompt in snowflake/04_cards.sql, the mock extractor in mocks/cortex.py, or when checking extracted cards.
---

# Card extractor

A **knowledge card** is one reusable piece of maintenance knowledge with a citation.
Schema: `card_type, asset_id, failure_mode, symptom_summary, action_taken, parts, outcome, source_excerpt, confidence`
(+ `author_technician_id, source_type, source_id, created_at` from the source row).

## Card types
| Type | Means | Cue words (incl. Hinglish) |
|---|---|---|
| FIX | an action that fixed a problem | replaced, changed, chngd, repl, "Fix =", badla, done |
| GOTCHA | a warning, or something that did NOT work | not hold, dont, otherwise, **warna** (otherwise), **sirf** (only), **wapas aaya** (came back), fails in |
| SYMPTOM_PATTERN | how a failure shows up in advance | when … starts, creeping, then temperature, root cause looks like |
| CONVENTION | a standing rule / practice | mandatory, always, keep min, do X first |

## Rules
1. **Extract only what the text states.** Never infer a fix that isn't written. Never invent part numbers.
2. `source_excerpt` must be an **exact substring** of the source (≤ 220 chars); it is the citation.
3. `asset_id` ∈ {CNC1–CNC4, P1–P3, AC1, AC2, CV1–CV3} or null. In handover notes, a sentence without an asset
   inherits the last asset mentioned earlier in the same note.
4. `failure_mode` ∈ the 10 codes in `RAW.FAILURE_MODES` or null. Keyword priority: motor trip/overload → MOTOR_OVERHEAT
   before belt → BELT_SLIP; brg/bearing/grease/lube → BEARING_WEAR; seal/leak → SEAL_LEAK; valve → VALVE_STICKING.
5. `outcome` only as stated: RESOLVED (incl. a fix the author presents as the working fix: "Fix = …", "use X") /
   RECURRED ("came back", "wapas", "phir se") / UNKNOWN.
   **Do not** mark a fix RECURRED from its own text; recurrence across work orders is derived later by the graph
   (`BRAIN.CARDS` view: same asset + failure mode re-opened within 14 days).
6. Chatter (targets, canteen, housekeeping, "PM done", "running ok") yields **no card**.
7. One sentence may yield several cards; one note usually yields 0–4.
8. Work orders: every CORRECTIVE work order yields one FIX card from its resolution note (parts from `parts_used`),
   plus GOTCHA cards for warning sentences inside it.
9. Never re-extract an unchanged source: the log key is `(source_type, source_id, MD5(text))`.

## Worked example (the golden note HN-0163)
> "…when P3 vibration starts creeping up slowly over 1-2 days and then temperature also starts rising, it is the DE
> bearing (6312) failing. Fix = replace bearing AND switch grease from LG-2 to HT-3 high-temp grade, flush old grease
> fully. Only bearing change does NOT hold - today it came back in 9 days after bearing-only job. Keep min 2 bearings…"

→ SYMPTOM_PATTERN (vibration then temperature), FIX RESOLVED ("Fix = replace bearing AND switch grease…"),
GOTCHA RECURRED ("Only bearing change does NOT hold…"), CONVENTION ("Keep min 2 bearings + HT-3 in store").

## Verify
`python scripts/run_checks.py` (mock) / `--snowflake`: cards C1–C12 from `data_gen/answer_key.json` must exist.
