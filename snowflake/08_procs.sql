-- Plant Brain :: 08_procs.sql
-- Actions: draft -> human approval -> close job (learning loop).
--
--   APP.WORK_ORDER_DRAFTS          table  drafts with citations, status PENDING_APPROVAL | APPROVED | REJECTED
--   APP.CODE                       stage  holds plant_brain.zip (the same package the Streamlit app uses)
--   APP.DRAFT_WORK_ORDER(id)       proc   top cards + failure window + parts + best technician -> draft
--   APP.APPROVE_WORK_ORDER(id, by) proc   HUMAN approval only; creates an OPEN work order
--   APP.REJECT_WORK_ORDER(id,by,r) proc
--   APP.CLOSE_JOB(wo, note, tech)  proc   closes the job and runs BRAIN.EXTRACT_NEW_CARDS -> new card
--   APP.RESET_DEMO()               proc   removes drafts + demo work orders (historical data untouched)
--
-- Before running: python scripts/package_procs.py  (builds build/plant_brain.zip)
-- Then run this file with scripts/sf.py from the repo root (PUT needs a client, not Snowsight).
-- The procedure logic is app/plant_brain/core.py; drafting rules: coco/skills/work-order-drafter/SKILL.md.

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.APP;

CREATE TABLE IF NOT EXISTS APP.WORK_ORDER_DRAFTS (
  draft_id                   VARCHAR,
  anomaly_id                 VARCHAR,
  asset_id                   VARCHAR,
  failure_mode               VARCHAR,
  status                     VARCHAR,   -- PENDING_APPROVAL | APPROVED | REJECTED
  title                      VARCHAR,
  body                       VARCHAR,   -- markdown with [CARD-...] citations
  recommended_technician_id  VARCHAR,
  parts                      VARCHAR,
  parts_at_risk              VARCHAR,
  eta_low_h                  FLOAT,
  eta_high_h                 FLOAT,
  cited_card_ids             VARCHAR,   -- comma-separated card ids
  created_at                 TIMESTAMP_NTZ,
  created_by                 VARCHAR,
  edited_by                  VARCHAR,
  approved_by                VARCHAR,
  approved_at                TIMESTAMP_NTZ,
  rejected_reason            VARCHAR,
  wo_id                      VARCHAR    -- work order created on approval
);

CREATE STAGE IF NOT EXISTS APP.CODE COMMENT = 'plant_brain package for Python stored procedures';
PUT 'file://build/plant_brain.zip' @APP.CODE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;

CREATE OR REPLACE PROCEDURE APP.DRAFT_WORK_ORDER(ANOMALY_ID VARCHAR)
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  IMPORTS = ('@PLANT_BRAIN.APP.CODE/plant_brain.zip')
  HANDLER = 'plant_brain.procs.draft_work_order'
  COMMENT = 'Drafts a cited work order for an anomaly. Status PENDING_APPROVAL; never approves.'
  EXECUTE AS OWNER;

CREATE OR REPLACE PROCEDURE APP.APPROVE_WORK_ORDER(DRAFT_ID VARCHAR, APPROVER VARCHAR)
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  IMPORTS = ('@PLANT_BRAIN.APP.CODE/plant_brain.zip')
  HANDLER = 'plant_brain.procs.approve_work_order'
  COMMENT = 'Human approval of a draft. Refuses agent/system approvers. Not exposed to the agent.'
  EXECUTE AS OWNER;

CREATE OR REPLACE PROCEDURE APP.REJECT_WORK_ORDER(DRAFT_ID VARCHAR, APPROVER VARCHAR, REASON VARCHAR)
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  IMPORTS = ('@PLANT_BRAIN.APP.CODE/plant_brain.zip')
  HANDLER = 'plant_brain.procs.reject_work_order'
  EXECUTE AS OWNER;

CREATE OR REPLACE PROCEDURE APP.CLOSE_JOB(WO_ID VARCHAR, CLOSING_NOTE VARCHAR, TECHNICIAN_ID VARCHAR)
  RETURNS VARIANT
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  IMPORTS = ('@PLANT_BRAIN.APP.CODE/plant_brain.zip')
  HANDLER = 'plant_brain.procs.close_job'
  COMMENT = 'Closes a job; the closing note becomes new knowledge cards (learning loop).'
  EXECUTE AS OWNER;

CREATE OR REPLACE PROCEDURE APP.RESET_DEMO()
  RETURNS VARCHAR
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  IMPORTS = ('@PLANT_BRAIN.APP.CODE/plant_brain.zip')
  HANDLER = 'plant_brain.procs.reset_demo'
  EXECUTE AS OWNER;
