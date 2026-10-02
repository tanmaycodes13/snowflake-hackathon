-- Plant Brain :: 06_search.sql
-- Cortex Search over the knowledge cards. Used by: Anomaly -> Brain recall, Ask the Plant,
-- APP.DRAFT_WORK_ORDER and the Cortex Agent (09_agent.sql).
-- Mock equivalent: mocks/search.py (BM25, same request/response shape as SEARCH_PREVIEW).

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.BRAIN;

-- Source is the table BRAIN.CARD_SEARCH_DOCS (copy of BRAIN.CARDS, see 04_cards.sql): Cortex Search
-- needs change tracking, which the BRAIN.CARDS view can't support.
CALL BRAIN.REFRESH_CARD_SEARCH_DOCS();

CREATE OR REPLACE CORTEX SEARCH SERVICE BRAIN.CARD_SEARCH
  ON search_text
  ATTRIBUTES asset_id, failure_mode, card_type, outcome
  WAREHOUSE = PB_WH
  TARGET_LAG = '1 hour'
  COMMENT = 'Knowledge cards: symptom + action + source excerpt'
AS
  SELECT card_id, search_text, card_type, asset_id, failure_mode, outcome,
         symptom_summary, action_taken, source_type, source_id, source_excerpt,
         author_name, confidence, is_stale
  FROM PLANT_BRAIN.BRAIN.CARD_SEARCH_DOCS;

-- Smoke test (expect Ravi's fix, CARD-HN-0163-*, near the top):
SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
  'PLANT_BRAIN.BRAIN.CARD_SEARCH',
  '{"query": "P3 vibration rising then temperature, how was the bearing fixed",
    "columns": ["card_id", "card_type", "outcome", "source_excerpt"],
    "filter": {"@eq": {"asset_id": "P3"}},
    "limit": 5}'
) AS results;
