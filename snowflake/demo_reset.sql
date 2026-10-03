-- Plant Brain :: demo_reset.sql
-- Run before every recording or rehearsal (Snowsight, `snow sql -f`, or in CoCo: /sql CALL ...).
-- Removes drafts, work orders created by the demo, and demo handover notes (ids HN-9xxx) with their cards.
-- Historical (seeded) data is untouched.
USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
CALL PLANT_BRAIN.APP.RESET_DEMO();                 -- drafts + app work orders + HN-9xxx notes and their cards
CALL PLANT_BRAIN.BRAIN.REFRESH_CARD_SEARCH_DOCS(); -- keep Cortex Search docs in sync
SELECT
  (SELECT COUNT(*) FROM PLANT_BRAIN.APP.WORK_ORDER_DRAFTS)                               AS drafts_left,
  (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.WORK_ORDERS WHERE wo_id > 'WO-2026-0144')        AS demo_wos_left,
  (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.HANDOVER_NOTES WHERE note_id LIKE 'HN-9%')       AS demo_notes_left;
