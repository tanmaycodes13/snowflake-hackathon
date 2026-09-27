-- Plant Brain :: Phase 3 checks. Every row must say PASS.
-- Expected OEE values come from data_gen/answer_key.json (tolerance 0.5% relative).
USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE DATABASE PLANT_BRAIN;

WITH expected (asset_id, oee_date, availability, performance, quality, oee) AS (
  SELECT * FROM VALUES
    ('P3',   '2026-06-17'::DATE, 0.6985, 0.9083, 0.9872, 0.6264),
    ('CNC1', '2026-07-03'::DATE, 0.9881, 0.9199, 0.9729, 0.8843),
    ('CV2',  '2026-08-31'::DATE, 0.9778, 0.9015, 0.9702, 0.8552)
),
oee_checks AS (
  SELECT 'OEE ' || e.asset_id || ' ' || e.oee_date AS check_name,
         IFF(ABS(o.oee - e.oee) / e.oee <= 0.005
             AND ABS(o.availability - e.availability) <= 0.0005
             AND ABS(o.performance - e.performance) <= 0.0005
             AND ABS(o.quality - e.quality) <= 0.0005, 'PASS', 'FAIL') AS result,
         'got ' || ROUND(o.oee, 4) || ' expected ' || e.oee AS detail
  FROM expected e
  LEFT JOIN CORE.OEE_DAILY o ON o.asset_id = e.asset_id AND o.oee_date = e.oee_date
),
counts AS (
  SELECT 'row counts' AS check_name,
         IFF((SELECT COUNT(*) FROM RAW.ASSETS) = 12
         AND (SELECT COUNT(*) FROM RAW.WORK_ORDERS) = 144
         AND (SELECT COUNT(*) FROM RAW.HANDOVER_NOTES) = 295
         AND (SELECT COUNT(*) FROM RAW.PRODUCTION_LOG) = 2690
         AND (SELECT COUNT(*) FROM RAW.SENSOR_READINGS) = 311040, 'PASS', 'FAIL') AS result,
         'assets/WOs/notes/prod/sensors = 12/144/295/2690/311040' AS detail
),
health AS (
  SELECT 'ASSET_HEALTH alerts = P3, CNC2, CV2' AS check_name,
         IFF(LISTAGG(asset_id, ',') WITHIN GROUP (ORDER BY asset_id) = 'CNC2,CV2,P3', 'PASS', 'FAIL') AS result,
         'got ' || COALESCE(LISTAGG(asset_id, ',') WITHIN GROUP (ORDER BY asset_id), '(none)') AS detail
  FROM CORE.ASSET_HEALTH WHERE health_status = 'ALERT'
),
golden_note AS (
  SELECT 'clear fix note HN-0163 loaded intact' AS check_name,
         IFF(COUNT(*) = 1, 'PASS', 'FAIL') AS result,
         COUNT(*) || ' note(s) contain the clear fix phrase' AS detail
  FROM RAW.HANDOVER_NOTES WHERE note_text ILIKE '%switch grease from LG-2 to HT-3%' AND note_id = 'HN-0163'
)
SELECT * FROM counts
UNION ALL SELECT * FROM oee_checks
UNION ALL SELECT * FROM health
UNION ALL SELECT * FROM golden_note
ORDER BY check_name;
