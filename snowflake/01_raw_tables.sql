-- Plant Brain :: 01_raw_tables.sql
-- Raw landing tables. Column order matches data_gen/out/*.csv exactly (positional COPY).
-- ALL DATA IS SYNTHETIC. Idempotent.

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.RAW;

CREATE TABLE IF NOT EXISTS ASSETS (
  asset_id            VARCHAR PRIMARY KEY,
  asset_name          VARCHAR,
  asset_type          VARCHAR,      -- CNC_MILL | HYDRAULIC_PRESS | AIR_COMPRESSOR | CONVEYOR
  line_id             VARCHAR,      -- L1 | L2 | L3
  install_date        DATE,
  firmware_version    VARCHAR,
  model               VARCHAR,
  ideal_cycle_time_s  NUMBER(6,1),  -- NULL for utilities (compressors)
  criticality         VARCHAR
);

CREATE TABLE IF NOT EXISTS FAILURE_MODES (
  failure_mode_id         VARCHAR PRIMARY KEY,
  code                    VARCHAR,
  name                    VARCHAR,
  applicable_asset_types  VARCHAR,  -- pipe-separated
  primary_sensors         VARCHAR,  -- pipe-separated
  signature_description   VARCHAR,
  threshold_rule          VARCHAR,
  typical_precursor_h     NUMBER
);

CREATE TABLE IF NOT EXISTS TECHNICIANS (
  technician_id     VARCHAR PRIMARY KEY,
  full_name         VARCHAR,
  seniority         VARCHAR,
  years_experience  NUMBER,
  skills            VARCHAR,        -- pipe-separated asset types
  shift_pattern     VARCHAR,
  retiring_2027     BOOLEAN
);

CREATE TABLE IF NOT EXISTS SPARE_PARTS (
  part_id         VARCHAR PRIMARY KEY,
  description     VARCHAR,
  asset_types     VARCHAR,
  stock_qty       NUMBER,
  reorder_point   NUMBER,
  lead_time_days  NUMBER,
  unit_cost_inr   NUMBER
);

CREATE TABLE IF NOT EXISTS ASSET_CHANGES (
  change_id    VARCHAR PRIMARY KEY,
  asset_id     VARCHAR,
  changed_at   TIMESTAMP_NTZ,
  change_type  VARCHAR,             -- PART_REPLACEMENT | FIRMWARE_UPDATE | LUBRICANT_CHANGE
  description  VARCHAR
);

CREATE TABLE IF NOT EXISTS WORK_ORDERS (
  wo_id              VARCHAR PRIMARY KEY,
  asset_id           VARCHAR,
  wo_type            VARCHAR,       -- CORRECTIVE | PREVENTIVE | INSPECTION
  priority           VARCHAR,
  failure_mode_code  VARCHAR,       -- may be NULL (planner left it blank)
  reported_at        TIMESTAMP_NTZ,
  started_at         TIMESTAMP_NTZ,
  closed_at          TIMESTAMP_NTZ,
  downtime_min       NUMBER,
  technician_id      VARCHAR,
  parts_used         VARCHAR,       -- 'PART:qty;PART:qty'
  resolution_note    VARCHAR,       -- messy free text -> knowledge cards (Phase 4)
  status             VARCHAR
);

CREATE TABLE IF NOT EXISTS HANDOVER_NOTES (
  note_id               VARCHAR PRIMARY KEY,
  created_at            TIMESTAMP_NTZ,
  shift_date            DATE,
  shift                 VARCHAR,    -- A | B | C
  note_type             VARCHAR,    -- SHIFT | ADHOC
  line_id               VARCHAR,
  author_technician_id  VARCHAR,
  note_text             VARCHAR     -- messy free text -> knowledge cards (Phase 4)
);

CREATE TABLE IF NOT EXISTS PRODUCTION_LOG (
  asset_id            VARCHAR,
  line_id             VARCHAR,
  shift_date          DATE,
  shift               VARCHAR,
  planned_time_min    NUMBER,
  run_time_min        NUMBER,
  downtime_min        NUMBER,
  ideal_cycle_time_s  NUMBER(6,1),
  total_count         NUMBER,
  good_count          NUMBER,
  PRIMARY KEY (asset_id, shift_date, shift)
);

CREATE TABLE IF NOT EXISTS SENSOR_READINGS (
  asset_id       VARCHAR,
  ts             TIMESTAMP_NTZ,
  vibration_rms  FLOAT,             -- mm/s
  temperature_c  FLOAT,
  pressure_bar   FLOAT,             -- presses + compressors only
  current_a      FLOAT
)
CLUSTER BY (asset_id, ts);
