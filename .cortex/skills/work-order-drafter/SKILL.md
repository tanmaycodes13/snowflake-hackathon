---
name: work-order-drafter
description: Draft a cited Plant Brain work order for an active anomaly, then (only on a named human's explicit instruction) approve it, and close the job so the technician's closing note becomes new knowledge. Use after $anomaly-triage, or when asked to draft, approve or close a maintenance work order.
tools:
- sql_execute
- snowflake_sql_execute
---

# When to Use
- "Draft a work order for the P3 anomaly", "Approve DRAFT-… as Anjali", "Close WO-… with this note: …"

# What This Skill Provides
Step 2 of the Plant Brain workflow. **Input** = an active anomaly id (from `$anomaly-triage`).
**Processing** = the Snowpark procedure `APP.DRAFT_WORK_ORDER`, which combines recalled cards, the failure window,
spare-parts stock and technician history. It runs the same code as the Streamlit app (`app/plant_brain`).
**Output** = a draft in `APP.WORK_ORDER_DRAFTS` with status `PENDING_APPROVAL` and card citations. A human approves it.

# Instructions
1. **Draft.** If the user didn't give an anomaly id, find it:
   `SELECT anomaly_id FROM PLANT_BRAIN.BRAIN.ANOMALIES WHERE is_active AND asset_id = '<ASSET>';`
   Then:
   ```sql
   CALL PLANT_BRAIN.APP.DRAFT_WORK_ORDER('<ANOMALY_ID>');
   ```
   Show the returned `draft_id`, `title` and `status`, the `body` (render the markdown), `parts_at_risk` and
   `recommended_technician_id`.
2. **Stop and ask for approval.** Say: "This draft is PENDING_APPROVAL. Who is approving it?" Do **not** continue
   until the user names a person and explicitly says to approve.
3. **Approve** (only after step 2):
   ```sql
   CALL PLANT_BRAIN.APP.APPROVE_WORK_ORDER('<DRAFT_ID>', '<HUMAN NAME>');
   ```
   Report the new `wo_id` (status OPEN). The procedure refuses approvers named agent, bot, system, Cortex or Plant Brain.
   Never pass your own name or a placeholder.
4. **Close the job** when the user gives a closing note (the learning loop):
   ```sql
   CALL PLANT_BRAIN.APP.CLOSE_JOB('<WO_ID>', '<closing note exactly as written>', '<TECHNICIAN_ID or empty>');
   ```
   Escape single quotes in the note by doubling them. The procedure runs `BRAIN.EXTRACT_NEW_CARDS()` on the note.
   Then show the new knowledge:
   ```sql
   SELECT card_id, card_type, outcome, source_excerpt FROM PLANT_BRAIN.BRAIN.CARDS WHERE source_id = '<WO_ID>';
   SELECT relation, to_type, to_id FROM PLANT_BRAIN.BRAIN.EDGES
   WHERE from_id IN (SELECT card_id FROM PLANT_BRAIN.BRAIN.CARDS WHERE source_id = '<WO_ID>');
   ```

## Drafting rules (enforced in app/plant_brain/drafting.py)
1. Lead with the best RESOLVED FIX for this asset + failure mode. An explicit handover-note fix ranks above work-order fixes. Cite `[CARD-…]`.
2. List the other resolved fixes as "same fix applied before", with their work-order ids.
3. Always include a **Do NOT** section: every GOTCHA, and every RECURRED fix with its recurrence basis.
4. Never recommend an action that only appears in a RECURRED card.
5. Parts = the parts used by the cited fixes; show stock vs reorder point and lead time; flag `AT RISK`.
6. Technician = whoever authored the most RESOLVED fixes; if they are retiring in 2027, suggest pairing with a junior.
7. The failure window is an **ESTIMATE** range, never one number.
8. Status is always `PENDING_APPROVAL`. **Only a named human approves.** The agent never does.

# Examples
User: `$work-order-drafter Draft a work order for the P3 anomaly`
Assistant: calls DRAFT_WORK_ORDER('A-P3-…') and shows the draft. It cites CARD-HN-0163-…, flags BRG-6312 and LUB-HT3 at risk and suggests T01 Ravi Kulkarni. Then it asks who approves.
User: `Approve it as Anjali`
Assistant: calls APPROVE_WORK_ORDER('DRAFT-…', 'Anjali') and reports that WO-2026-0145 is OPEN.
