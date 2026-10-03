---
name: card-extractor
description: Turn messy maintenance text (shift handover notes, work-order or closing notes, with typos, abbreviations and Hinglish) into cited Plant Brain knowledge cards with Snowflake Cortex AI_COMPLETE, and show the new cards and graph links. Use when asked to capture, learn from or extract knowledge from a note, or to check what the Brain knows about a source.
tools:
- sql_execute
- snowflake_sql_execute
---

# When to Use
- "Learn from this handover note: …", "Capture this note", "What cards came out of HN-…?"
- Step 3 of the workflow, the **learning loop**: new text in, new knowledge out.

# What This Skill Provides
**Input** = a new note, as written on the shop floor.
**Processing** = the note lands in `RAW.HANDOVER_NOTES`; `BRAIN.EXTRACT_NEW_CARDS()` sends **only unprocessed text**
(cached by MD5 hash) to Cortex `AI_COMPLETE` with a JSON schema, then refreshes the Cortex Search docs.
**Output** = typed, cited cards in `BRAIN.CARDS` (FIX / GOTCHA / SYMPTOM_PATTERN / CONVENTION) and links in `BRAIN.EDGES`.
All data is synthetic (fictional plant).

# Instructions
1. **Store the note** under the next demo id (`HN-9001`, `HN-9002`, …; ids `HN-9xxx` are demo notes, which
   `snowflake/demo_reset.sql` removes). Ask for the author if not given (technician ids T01–T08; default `T06`).
   Double any single quotes inside the note.
   ```sql
   SELECT COALESCE(MAX(note_id), 'HN-9000') AS last_demo_id FROM PLANT_BRAIN.RAW.HANDOVER_NOTES WHERE note_id LIKE 'HN-9%';
   INSERT INTO PLANT_BRAIN.RAW.HANDOVER_NOTES
     (note_id, created_at, shift_date, shift, note_type, line_id, author_technician_id, note_text)
   VALUES ('<NEXT_ID>', '2026-09-01 06:00:00', '2026-08-31', 'C', 'SHIFT', 'ALL', '<AUTHOR>', '<NOTE TEXT>');
   ```
2. **Extract** (processes only new or changed text; costs one AI_COMPLETE call for this note):
   ```sql
   CALL PLANT_BRAIN.BRAIN.EXTRACT_NEW_CARDS();
   ```
3. **Show the output**:
   ```sql
   SELECT card_id, card_type, asset_id, failure_mode, outcome, source_excerpt, confidence
   FROM PLANT_BRAIN.BRAIN.CARDS WHERE source_id = '<NEXT_ID>' ORDER BY card_id;
   SELECT relation, to_type, to_id FROM PLANT_BRAIN.BRAIN.EDGES
   WHERE from_id IN (SELECT card_id FROM PLANT_BRAIN.BRAIN.CARDS WHERE source_id = '<NEXT_ID>');
   ```
4. Summarise in at most 5 lines: each card's type, what it says (an exact quote) and its `[card_id]`; note any
   Hinglish you interpreted (e.g. "mat badhao" = don't increase, "warna" = otherwise). If no cards came out, say
   the note was routine chatter.
5. To prove it is searchable, run one Cortex Search query on the asset (the service refreshes on its target lag;
   `BRAIN.CARDS` shows the card immediately).

To learn from a **work-order closing note**, use `$work-order-drafter` step 4 (`APP.CLOSE_JOB`). It calls the same
extraction.

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
