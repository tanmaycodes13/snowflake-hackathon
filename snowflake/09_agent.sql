-- Plant Brain :: 09_agent.sql
-- Cortex Agent with three tools: card search (Cortex Search), plant analytics (Cortex Analyst over
-- the semantic view) and DRAFT_WORK_ORDER (custom procedure tool). Usable from Snowflake
-- Intelligence / the Agents REST API. The Streamlit "Ask the Plant" page orchestrates the same
-- three tools in Python (app/plant_brain/agent.py) so the demo stays deterministic and also
-- runs in mock mode.
-- APPROVE_WORK_ORDER is deliberately NOT a tool: only a human can approve.

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.APP;

CREATE OR REPLACE AGENT APP.PLANT_BRAIN_AGENT
  COMMENT = 'Plant Brain maintenance assistant (synthetic data)'
  PROFILE = '{"display_name": "Plant Brain", "color": "orange"}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto

  orchestration:
    budget:
      seconds: 60
      tokens: 16000

  instructions:
    response: >
      You are Plant Brain, the maintenance memory of a fictional factory (Deccan Precision Components, Pune).
      Always cite card IDs (e.g. CARD-HN-0163-2) and quote the source excerpt for maintenance claims.
      For numbers, say which verified query or table they came from.
      If the tools do not return evidence, say exactly: "I can't establish that from the available data."
      Never guess. Never make judgements about individual people.
      You can DRAFT work orders, but you can never approve them: approval is done by a human in the app.
    orchestration: >
      Use CardSearch for how something was fixed, what not to do, symptoms and conventions; filter by asset_id
      when an asset (CNC1-4, P1-3, AC1-2, CV1-3) is named. Use PlantAnalytics for OEE, downtime, MTTR,
      breakdown counts and spare-part stock. Use DraftWorkOrder only when the user asks for a work order
      for an active anomaly (anomaly ids look like A-P3-2026083104).
    sample_questions:
      - question: "How was P3's bearing issue fixed before?"
      - question: "What should I NOT do when fixing the P3 bearing?"
      - question: "What was the OEE for each line last week?"
      - question: "Which spare parts are at risk of stockout?"

  tools:
    - tool_spec:
        type: "cortex_search"
        name: "CardSearch"
        description: "Searches the plant's knowledge cards (fixes, gotchas, symptom patterns, conventions) extracted from work orders and shift handover notes."
    - tool_spec:
        type: "cortex_analyst_text_to_sql"
        name: "PlantAnalytics"
        description: "Answers OEE, downtime, MTTR, breakdown and spare-parts questions with SQL over the plant semantic view."
    - tool_spec:
        type: "generic"
        name: "DraftWorkOrder"
        description: "Drafts a work order for an active anomaly, citing knowledge cards, parts stock and the best technician. The draft is PENDING_APPROVAL until a human approves it."
        input_schema:
          type: "object"
          properties:
            anomaly_id:
              type: "string"
              description: "Active anomaly id, e.g. A-P3-2026083104"
          required: ["anomaly_id"]

  tool_resources:
    CardSearch:
      search_service: "PLANT_BRAIN.BRAIN.CARD_SEARCH"
      max_results: "5"
      id_column: "card_id"
      title_column: "card_id"
    PlantAnalytics:
      semantic_view: "PLANT_BRAIN.CORE.PLANT_SEMANTIC_VIEW"
    DraftWorkOrder:
      type: "procedure"
      identifier: "PLANT_BRAIN.APP.DRAFT_WORK_ORDER"
      execution_environment:
        type: "warehouse"
        warehouse: "PB_WH"
  $$;
