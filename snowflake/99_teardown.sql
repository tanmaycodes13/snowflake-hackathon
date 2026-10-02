-- Plant Brain :: 99_teardown.sql
-- Removes EVERYTHING this project created. Irreversible. Run as ACCOUNTADMIN.
USE ROLE ACCOUNTADMIN;
ALTER TASK IF EXISTS PLANT_BRAIN.BRAIN.CARD_EXTRACT_TASK SUSPEND;
DROP DATABASE IF EXISTS PLANT_BRAIN;          -- tables, views, stages, procs, task, search service, semantic view, agent, streamlit
DROP WAREHOUSE IF EXISTS PB_WH;
DROP RESOURCE MONITOR IF EXISTS PB_MONITOR;
DROP USER IF EXISTS PB_SVC;                   -- agent login from 00b_agent_user.sql (if created)
DROP ROLE IF EXISTS PB_ROLE;
-- Optional: revert the account parameter set in 00_setup.sql
-- ALTER ACCOUNT UNSET CORTEX_ENABLED_CROSS_REGION;
