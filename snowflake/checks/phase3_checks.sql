-- Plant Brain :: Phase 3 checks (portable: also run by scripts/run_checks.py on the mock).
-- Every row must say PASS. Expected OEE values come from data_gen/answer_key.json (tolerance 0.5% rel.).
USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE DATABASE PLANT_BRAIN;

WITH expected AS (
  SELECT 'P3' AS asset_id, CAST('2026-06-17' AS DATE) AS oee_date, 0.6985 AS availability, 0.9083 AS performance, 0.9872 AS quality, 0.6264 AS oee
  UNION ALL SELECT 'CNC1', CAST('2026-07-03' AS DATE), 0.9881, 0.9199, 0.9729, 0.8843
  UNION ALL SELECT 'CV2',  CAST('2026-08-31' AS DATE), 0.9778, 0.9015, 0.9702, 0.8552
),
oee_checks AS (
  SELECT 'OEE ' || e.asset_id || ' ' || CAST(e.oee_date AS VARCHAR) AS check_name,
         CASE WHEN ABS(o.oee - e.oee) / e.oee <= 0.005
               AND ABS(o.availability - e.availability) <= 0.0005
               AND ABS(o.performance - e.performance) <= 0.0005
               AND ABS(o.quality - e.quality) <= 0.0005 THEN 'PASS' ELSE 'FAIL' END AS result,
         'got ' || CAST(ROUND(o.oee, 4) AS VARCHAR) || ' expected ' || CAST(e.oee AS VARCHAR) AS detail
  FROM expected e
  LEFT JOIN PLANT_BRAIN.CORE.OEE_DAILY o ON o.asset_id = e.asset_id AND o.oee_date = e.oee_date
),
counts AS (
  SELECT 'row counts' AS check_name,
         CASE WHEN (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.ASSETS) = 12
          AND (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.WORK_ORDERS WHERE wo_id <= 'WO-2026-0144') = 144
          AND (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.HANDOVER_NOTES) = 295
          AND (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.PRODUCTION_LOG) = 2690
          AND (SELECT COUNT(*) FROM PLANT_BRAIN.RAW.SENSOR_READINGS) = 311040 THEN 'PASS' ELSE 'FAIL' END AS result,
         'assets/WOs/notes/prod/sensors = 12/144/295/2690/311040' AS detail
),
health AS (
  SELECT 'ASSET_HEALTH alerts = P3, CNC2, CV2' AS check_name,
         CASE WHEN COUNT(*) = 3 AND SUM(CASE WHEN asset_id IN ('P3', 'CNC2', 'CV2') THEN 1 ELSE 0 END) = 3
              THEN 'PASS' ELSE 'FAIL' END AS result,
         CAST(COUNT(*) AS VARCHAR) || ' alert(s)' AS detail
  FROM PLANT_BRAIN.CORE.ASSET_HEALTH WHERE health_status = 'ALERT'
),
golden_note AS (
  SELECT 'clear fix note HN-0163 loaded intact' AS check_name,
         CASE WHEN COUNT(*) = 1 THEN 'PASS' ELSE 'FAIL' END AS result,
         CAST(COUNT(*) AS VARCHAR) || ' note(s) contain the clear fix phrase' AS detail
  FROM PLANT_BRAIN.RAW.HANDOVER_NOTES WHERE note_text LIKE '%switch grease from LG-2 to HT-3%' AND note_id = 'HN-0163'
)
SELECT * FROM counts
UNION ALL SELECT * FROM oee_checks
UNION ALL SELECT * FROM health
UNION ALL SELECT * FROM golden_note
ORDER BY check_name;
