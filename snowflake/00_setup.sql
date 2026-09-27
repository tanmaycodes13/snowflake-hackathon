-- Plant Brain :: 00_setup.sql
-- One-time account bootstrap. Run as ACCOUNTADMIN (Snowsight worksheet or `snow sql -f`).
-- Creates: role PB_ROLE, warehouse PB_WH (XS, AUTO_SUSPEND=60), database PLANT_BRAIN with
-- schemas RAW / CORE / BRAIN / APP, stage RAW.LANDING, CSV file format RAW.CSV_FF.
-- Idempotent: safe to re-run.

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------------
-- Role + account-level privileges
-- ---------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS PB_ROLE COMMENT = 'Plant Brain hackathon project role';
GRANT ROLE PB_ROLE TO ROLE SYSADMIN;

-- Cortex AI functions: USE AI FUNCTIONS (account) + CORTEX_USER database role.
-- (Both are granted to PUBLIC by default; granted explicitly so the project never depends on that.)
GRANT USE AI FUNCTIONS ON ACCOUNT TO ROLE PB_ROLE;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE PB_ROLE;

-- Tasks for the incremental card pipeline (Phase 4).
GRANT EXECUTE TASK ON ACCOUNT TO ROLE PB_ROLE;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE PB_ROLE;

-- Let Cortex route to another region if a model isn't hosted locally.
-- Synthetic data only, so no residency concern. Tighten to 'AWS_US' etc. if preferred.
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- ---------------------------------------------------------------------------
-- Warehouse (cost discipline: XS, suspend after 60 s)
-- ---------------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS PB_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Plant Brain XS warehouse';
GRANT USAGE, OPERATE, MONITOR ON WAREHOUSE PB_WH TO ROLE PB_ROLE;

-- Guard rail for the trial balance: suspend PB_WH after 20 credits/month.
CREATE RESOURCE MONITOR IF NOT EXISTS PB_MONITOR
  WITH CREDIT_QUOTA = 20 FREQUENCY = MONTHLY START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 80 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND;
ALTER WAREHOUSE PB_WH SET RESOURCE_MONITOR = PB_MONITOR;

-- ---------------------------------------------------------------------------
-- Database + schemas, owned by PB_ROLE
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS PLANT_BRAIN COMMENT = 'Plant Brain (SYNTHETIC DATA)';
GRANT OWNERSHIP ON DATABASE PLANT_BRAIN TO ROLE PB_ROLE COPY CURRENT GRANTS;

USE ROLE PB_ROLE;
USE DATABASE PLANT_BRAIN;
CREATE SCHEMA IF NOT EXISTS RAW   COMMENT = 'Landed synthetic source data';
CREATE SCHEMA IF NOT EXISTS CORE  COMMENT = 'OEE and asset health';
CREATE SCHEMA IF NOT EXISTS BRAIN COMMENT = 'Knowledge cards, edges, anomalies, search';
CREATE SCHEMA IF NOT EXISTS APP   COMMENT = 'Procs, work-order drafts, UI-facing objects';

CREATE FILE FORMAT IF NOT EXISTS RAW.CSV_FF
  TYPE = CSV
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE
  NULL_IF = ('')
  ENCODING = 'UTF8';

CREATE STAGE IF NOT EXISTS RAW.LANDING
  FILE_FORMAT = RAW.CSV_FF
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Upload data_gen/out/*.csv here';

-- ---------------------------------------------------------------------------
-- Give yourself the role so the objects are visible in Snowsight.
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
EXECUTE IMMEDIATE $$
BEGIN
  LET stmt VARCHAR := 'GRANT ROLE PB_ROLE TO USER "' || CURRENT_USER() || '"';
  EXECUTE IMMEDIATE :stmt;
END;
$$;

-- Account identifier to share with the agent (not a secret):
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS account_identifier,
       CURRENT_REGION() AS region;
