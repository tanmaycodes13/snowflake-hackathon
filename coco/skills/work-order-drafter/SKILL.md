---
name: work-order-drafter
description: Rules for drafting a Plant Brain work order from an anomaly, its recalled knowledge cards, the failure window, spare-parts stock and technician history. Use when changing app/plant_brain/drafting.py, APP.DRAFT_WORK_ORDER (snowflake/08_procs.sql) or the agent's DraftWorkOrder tool.
---

# Work-order drafter

Inputs: the active anomaly, its failure window (estimate), ranked cards for the asset + failure mode,
`RAW.SPARE_PARTS`, `RAW.TECHNICIANS`. Output: one row in `APP.WORK_ORDER_DRAFTS`.

## Rules
1. **Lead with the best RESOLVED FIX** for this asset + failure mode. An explicit written fix from a handover note
   ranks above work-order fixes; cite its card id in `[CARD-…]` form.
2. List other resolved fixes as "same fix applied before" with their work-order ids, so the planner sees the pattern.
3. **Always include a "Do NOT" section** with every GOTCHA for this asset + failure mode and every RECURRED fix
   (with its recurrence basis, e.g. "WO-2026-0079 re-opened the same failure after 9 days").
4. **Never recommend an action that only appears in a RECURRED card.**
5. Parts = parts used by the cited resolved fixes; for each, show stock vs reorder point and lead time, and flag
   `AT RISK` when stock ≤ reorder point.
6. Technician = the author of the most RESOLVED fixes for this pattern. If they are `retiring_2027`, say so and
   suggest pairing with a junior (knowledge transfer).
7. Failure window is an **ESTIMATE** with a low–high range and its basis. Never a single number.
8. Every factual line carries a citation. No citation → don't write the line.
9. Status is always `PENDING_APPROVAL`. **Only a named human can approve**; approvals by "agent", "bot",
   "system", "Plant Brain" or "Cortex" are refused (`PlantBrain._require_human`). The Cortex Agent has no approve tool.

## Verify
`python scripts/smoke_test.py`: the P3 draft must cite CARD-HN-0163-2, flag BRG-6312 at risk and suggest T01.
