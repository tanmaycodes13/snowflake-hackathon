-- Plant Brain :: 10_streamlit.sql (alternative to `snow streamlit deploy`)
-- Preferred: from the repo root run   snow streamlit deploy --project app --replace
-- (uses app/snowflake.yml). This file documents the SQL equivalent for reference.
USE ROLE PB_ROLE;
USE SCHEMA PLANT_BRAIN.APP;
CREATE STAGE IF NOT EXISTS APP.STREAMLIT_STAGE;
-- Upload app/streamlit_app.py, app/environment.yml and app/plant_brain/*.py to
-- @APP.STREAMLIT_STAGE/plant_brain_app/ (keeping the plant_brain/ folder), then:
CREATE OR REPLACE STREAMLIT APP.PLANT_BRAIN_APP
  ROOT_LOCATION = '@PLANT_BRAIN.APP.STREAMLIT_STAGE/plant_brain_app'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = PB_WH
  TITLE = 'Plant Brain';
