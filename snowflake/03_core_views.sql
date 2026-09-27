-- Plant Brain :: 03_core_views.sql
-- CORE.OEE_DAILY, CORE.OEE_LINE_DAILY, CORE.ASSET_HEALTH.
-- OEE formula must match docs/DATA_MODEL.md and data_gen/answer_key.json exactly:
--   A = Σrun / Σplanned ;  P = Σ(ideal_cycle_s × total) / (Σrun × 60) ;  Q = Σgood / Σtotal ;  OEE = A×P×Q

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.CORE;

-- ---------------------------------------------------------------------------
-- OEE per asset per production day (production assets only; compressors are utilities)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW OEE_DAILY
  COMMENT = 'OEE = Availability x Performance x Quality per asset per shift_date'
AS
WITH agg AS (
  SELECT
    p.asset_id,
    a.asset_name,
    a.asset_type,
    p.line_id,
    p.shift_date                                   AS oee_date,
    COUNT(*)                                       AS shifts,
    SUM(p.planned_time_min)                        AS planned_min,
    SUM(p.run_time_min)                            AS run_min,
    SUM(p.downtime_min)                            AS downtime_min,
    SUM(p.total_count)                             AS total_count,
    SUM(p.good_count)                              AS good_count,
    SUM(p.ideal_cycle_time_s * p.total_count)      AS ideal_output_s
  FROM PLANT_BRAIN.RAW.PRODUCTION_LOG p
  JOIN PLANT_BRAIN.RAW.ASSETS a ON a.asset_id = p.asset_id
  GROUP BY 1, 2, 3, 4, 5
)
SELECT
  asset_id, asset_name, asset_type, line_id, oee_date, shifts,
  planned_min, run_min, downtime_min, total_count, good_count,
  total_count - good_count                                   AS scrap_count,
  DIV0(run_min, planned_min)                                 AS availability,
  DIV0(ideal_output_s, run_min * 60)                         AS performance,
  DIV0(good_count, total_count)                              AS quality,
  DIV0(run_min, planned_min) * DIV0(ideal_output_s, run_min * 60) * DIV0(good_count, total_count) AS oee
FROM agg;

-- ---------------------------------------------------------------------------
-- OEE per line per day (same formula over all production assets on the line)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW OEE_LINE_DAILY
  COMMENT = 'Line-level OEE per day, same formula aggregated over the line''s production assets'
AS
WITH agg AS (
  SELECT
    p.line_id,
    p.shift_date                               AS oee_date,
    SUM(p.planned_time_min)                    AS planned_min,
    SUM(p.run_time_min)                        AS run_min,
    SUM(p.downtime_min)                        AS downtime_min,
    SUM(p.total_count)                         AS total_count,
    SUM(p.good_count)                          AS good_count,
    SUM(p.ideal_cycle_time_s * p.total_count)  AS ideal_output_s
  FROM PLANT_BRAIN.RAW.PRODUCTION_LOG p
  GROUP BY 1, 2
)
SELECT
  line_id, oee_date, planned_min, run_min, downtime_min, total_count, good_count,
  DIV0(run_min, planned_min)          AS availability,
  DIV0(ideal_output_s, run_min * 60)  AS performance,
  DIV0(good_count, total_count)       AS quality,
  DIV0(run_min, planned_min) * DIV0(ideal_output_s, run_min * 60) * DIV0(good_count, total_count) AS oee
FROM agg;

-- ---------------------------------------------------------------------------
-- Asset health: latest reading + recent trend per sensor.
-- Trend compares the last 6 h (and 24 h) with the SAME clock hours over the previous
-- 7 days, which cancels the daily temperature/load cycle. Idle readings (machine
-- stopped for a work order) are excluded via a current threshold.
-- Status is a simple, explainable triage flag; real detection lives in BRAIN.ANOMALIES (Phase 5).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW ASSET_HEALTH
  COMMENT = 'Latest readings and 6h/24h trend vs same clock hours over the prior 7 days'
AS
WITH last_ts AS (
  SELECT asset_id, MAX(ts) AS max_ts
  FROM PLANT_BRAIN.RAW.SENSOR_READINGS
  GROUP BY asset_id
),
win AS (
  SELECT r.*, l.max_ts,
         DATEDIFF('minute', r.ts, l.max_ts) AS age_min
  FROM PLANT_BRAIN.RAW.SENSOR_READINGS r
  JOIN last_ts l
    ON l.asset_id = r.asset_id
   AND r.ts > DATEADD('day', -8, l.max_ts)
),
running AS (
  SELECT w.*
  FROM win w
  QUALIFY w.current_a >= 0.5 * AVG(w.current_a) OVER (PARTITION BY w.asset_id)
),
trend AS (
  SELECT
    asset_id,
    -- last 6 h vs same 6 clock hours on each of the previous 7 days
    AVG(IFF(age_min < 360, vibration_rms, NULL))                                             AS vib_6h,
    AVG(IFF(age_min BETWEEN 1440 AND 11519 AND MOD(age_min, 1440) < 360, vibration_rms, NULL)) AS vib_base_6h,
    AVG(IFF(age_min < 360, temperature_c, NULL))                                             AS temp_6h,
    AVG(IFF(age_min BETWEEN 1440 AND 11519 AND MOD(age_min, 1440) < 360, temperature_c, NULL)) AS temp_base_6h,
    AVG(IFF(age_min < 360, pressure_bar, NULL))                                              AS pres_6h,
    AVG(IFF(age_min BETWEEN 1440 AND 11519 AND MOD(age_min, 1440) < 360, pressure_bar, NULL))  AS pres_base_6h,
    AVG(IFF(age_min < 360, current_a, NULL))                                                 AS curr_6h,
    AVG(IFF(age_min BETWEEN 1440 AND 11519 AND MOD(age_min, 1440) < 360, current_a, NULL))     AS curr_base_6h,
    -- last 24 h vs previous 7 days (full days, so the cycle averages out)
    AVG(IFF(age_min < 1440, vibration_rms, NULL))                                            AS vib_24h,
    AVG(IFF(age_min BETWEEN 1440 AND 11519, vibration_rms, NULL))                            AS vib_base_7d,
    AVG(IFF(age_min < 1440, temperature_c, NULL))                                            AS temp_24h,
    AVG(IFF(age_min BETWEEN 1440 AND 11519, temperature_c, NULL))                            AS temp_base_7d
  FROM running
  GROUP BY asset_id
),
latest AS (
  SELECT asset_id, ts AS latest_ts, vibration_rms, temperature_c, pressure_bar, current_a
  FROM PLANT_BRAIN.RAW.SENSOR_READINGS
  QUALIFY ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY ts DESC) = 1
),
scored AS (
  SELECT
    a.asset_id, a.asset_name, a.asset_type, a.line_id, a.criticality,
    l.latest_ts, l.vibration_rms, l.temperature_c, l.pressure_bar, l.current_a,
    100 * (t.vib_6h  / NULLIF(t.vib_base_6h, 0)  - 1)  AS vib_6h_pct,
    t.temp_6h - t.temp_base_6h                          AS temp_6h_delta_c,
    100 * (t.pres_6h / NULLIF(t.pres_base_6h, 0) - 1)  AS pres_6h_pct,
    100 * (t.curr_6h / NULLIF(t.curr_base_6h, 0) - 1)  AS curr_6h_pct,
    100 * (t.vib_24h / NULLIF(t.vib_base_7d, 0) - 1)   AS vib_24h_pct,
    t.temp_24h - t.temp_base_7d                         AS temp_24h_delta_c
  FROM PLANT_BRAIN.RAW.ASSETS a
  JOIN latest l ON l.asset_id = a.asset_id
  JOIN trend  t ON t.asset_id = a.asset_id
)
SELECT
  *,
  CASE
    WHEN vib_6h_pct >= 8 OR temp_6h_delta_c >= 3 OR pres_6h_pct <= -5 OR ABS(curr_6h_pct) >= 8 THEN 'ALERT'
    WHEN vib_6h_pct >= 4 OR temp_6h_delta_c >= 1.5 OR pres_6h_pct <= -2.5 OR ABS(curr_6h_pct) >= 4 THEN 'WATCH'
    ELSE 'OK'
  END AS health_status
FROM scored;
