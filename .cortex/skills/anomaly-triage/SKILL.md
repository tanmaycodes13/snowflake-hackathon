---
name: anomaly-triage
description: Triage the plant's active sensor anomalies for Plant Brain. Finds active anomalies, explains which past failures each one matches, gives the failure-window estimate, and recalls the cited fix and "don't do this" warnings from the knowledge cards. Use when asked what needs attention, what is wrong with a machine, or how a problem was fixed before.
tools:
- sql_execute
- snowflake_sql_execute
---

# When to Use
- "What needs attention in the plant right now?", "Triage the active anomalies", "What's wrong with P3?"
- Before drafting a work order (the next skill in the workflow is `$work-order-drafter`).

# What This Skill Provides
Step 1 of the Plant Brain workflow: **Input** = the live sensor-derived anomalies in Snowflake.
**Processing** = deterministic SQL (z-score + slope, signature matching) plus Cortex Search over knowledge cards.
**Output** = a short, cited triage report per anomaly.
All data is synthetic (fictional plant). Database `PLANT_BRAIN`, warehouse `PB_WH`, role `PB_ROLE`.

# Instructions
Run these steps with the SQL tool, in order. Show the user each query's key rows as you go: the visible processing is part of the demo.

1. **Active anomalies, by priority**
   ```sql
   SELECT a.anomaly_id, a.asset_id, a.line_id, a.sensors, a.vib_shape, a.duration_h,
          ROUND(a.vib_rise_pct, 1) AS vib_rise_pct, ROUND(a.temp_rise_c, 1) AS temp_rise_c,
          f.failure_mode AS matched_failure_mode, f.n_matches,
          ROUND(f.eta_low_h) AS eta_low_h, ROUND(f.eta_high_h) AS eta_high_h,
          CASE WHEN f.eta_low_h <= 48 THEN 'CRITICAL' ELSE a.severity END AS priority
   FROM PLANT_BRAIN.BRAIN.ANOMALIES a
   LEFT JOIN PLANT_BRAIN.BRAIN.FAILURE_WINDOWS f ON f.anomaly_id = a.anomaly_id
   WHERE a.is_active
   ORDER BY CASE WHEN f.eta_low_h <= 48 THEN 0 ELSE 1 END, a.asset_id;
   ```
2. **History match for the top anomaly** (replace `<ANOMALY_ID>`):
   ```sql
   SELECT m.wo_id, m.failure_mode, ROUND(m.score, 2) AS score, m.is_match, t.full_name AS fixed_by
   FROM PLANT_BRAIN.BRAIN.ANOMALY_MATCHES m
   LEFT JOIN PLANT_BRAIN.RAW.TECHNICIANS t ON t.technician_id = m.technician_id
   WHERE m.anomaly_id = '<ANOMALY_ID>' ORDER BY m.score DESC;
   ```
3. **Recall with Cortex Search**, filtered to the asset (replace `<ASSET>` and the failure mode words):
   ```sql
   SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW('PLANT_BRAIN.BRAIN.CARD_SEARCH',
     '{"query": "<ASSET> vibration rising then temperature bearing wear fix what worked what did not",
       "columns": ["card_id","card_type","outcome","source_id","source_excerpt"],
       "filter": {"@eq": {"asset_id": "<ASSET>"}}, "limit": 6}') AS results;
   ```
4. **Graph-derived warnings**: fixes that did not hold (the text alone can't show this):
   ```sql
   SELECT card_id, source_id, author_name, outcome_basis
   FROM PLANT_BRAIN.BRAIN.CARDS
   WHERE asset_id = '<ASSET>' AND outcome = 'RECURRED' AND card_type = 'FIX';
   ```

## Output format
For the top (CRITICAL) anomaly, write at most 8 lines:
- **What:** asset, sensors, rise, duration, priority.
- **Seen before:** the matched work orders (score ≥ 0.75), and who fixed them.
- **Failure window:** `eta_low–eta_high h`, always labeled **ESTIMATE** and never given as one number.
- **What fixed it:** the best RESOLVED FIX card, as an exact quote plus `[card_id]`.
- **Do NOT:** each GOTCHA / RECURRED card, with its quote or recurrence basis plus `[card_id]`.
- **Next step:** "Run `$work-order-drafter` for <anomaly_id>."
Then one line per other active anomaly, saying whether it matches any past failure.

## Rules
- Cite every claim with a card id, work-order id or anomaly id. If the data doesn't show it, say "I can't establish that from the available data."
- Never invent part numbers, people or numbers.
- Decoys (anomalies with no matching history) are reported, but not escalated.

# Examples
User: `$anomaly-triage What needs attention in the plant right now?`
Assistant: runs steps 1–4 and reports that P3 is CRITICAL. Its vibration is ramping, with temperature following ~11 h later. It matches 4 past bearing-wear failures, with a failure window of 21–54 h (ESTIMATE). The fix is to "replace bearing AND switch grease from LG-2 to HT-3" [CARD-HN-0163-…]. Do NOT do a bearing-only replacement: WO-2026-0067 recurred after 9 days [CARD-WO-2026-0067-1]. CNC2 and CV2 have no matching history.
