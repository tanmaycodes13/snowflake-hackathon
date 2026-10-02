-- Plant Brain :: Phase 4 + 5 checks (portable: also run by scripts/run_checks.py on the mock).
-- Expected values from data_gen/answer_key.json. Every row must say PASS.
USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE DATABASE PLANT_BRAIN;

WITH exp_cards AS (
  SELECT 'C1' AS ref, 'HN-0163' AS source_id, 'FIX' AS card_type, 'P3' AS asset_id, 'RESOLVED' AS outcome, '%switch grease from LG-2 to HT-3%' AS excerpt
  UNION ALL SELECT 'C2', 'HN-0163', 'GOTCHA', 'P3', 'RECURRED', '%Only bearing change does NOT hold%'
  UNION ALL SELECT 'C3', 'HN-0163', 'SYMPTOM_PATTERN', 'P3', NULL, '%temperature also starts rising%'
  UNION ALL SELECT 'C4', 'WO-2026-0021', 'FIX', 'P3', 'RESOLVED', '%'
  UNION ALL SELECT 'C5', 'WO-2026-0067', 'FIX', 'P3', 'RECURRED', '%'
  UNION ALL SELECT 'C6', 'WO-2026-0079', 'FIX', 'P3', 'RESOLVED', '%'
  UNION ALL SELECT 'C7', 'WO-2026-0116', 'FIX', 'P3', 'RESOLVED', '%'
  UNION ALL SELECT 'C8', 'HN-0075', 'GOTCHA', 'CV1', NULL, '%overtighten%'
  UNION ALL SELECT 'C9', 'HN-0103', 'GOTCHA', 'AC2', NULL, '%drain manually%'
  UNION ALL SELECT 'C10', 'HN-0150', 'CONVENTION', 'CNC3', NULL, '%ref return%'
  UNION ALL SELECT 'C11', 'HN-0191', 'GOTCHA', 'P1', NULL, '%viton%'
  UNION ALL SELECT 'C12', 'HN-0212', 'CONVENTION', 'CNC1', NULL, '%warmup%'
),
card_checks AS (
  SELECT 'card ' || e.ref || ' ' || e.card_type || ' ' || e.source_id AS check_name,
         CASE WHEN COUNT(c.card_id) > 0 THEN 'PASS' ELSE 'FAIL' END AS result,
         CAST(COUNT(c.card_id) AS VARCHAR) || ' matching card(s)' AS detail
  FROM exp_cards e
  LEFT JOIN PLANT_BRAIN.BRAIN.CARDS c
    ON c.source_id = e.source_id AND c.card_type = e.card_type AND c.asset_id = e.asset_id
   AND (e.outcome IS NULL OR c.outcome = e.outcome) AND c.source_excerpt LIKE e.excerpt
  GROUP BY e.ref, e.card_type, e.source_id
),
edge_checks AS (
  SELECT 'edge WO-0079 CONTRADICTS WO-0067 (bearing-only fix)' AS check_name,
         CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END AS result, CAST(COUNT(*) AS VARCHAR) AS detail
  FROM PLANT_BRAIN.BRAIN.EDGES
  WHERE relation = 'CONTRADICTS' AND from_id LIKE 'CARD-WO-2026-0079-%' AND to_id LIKE 'CARD-WO-2026-0067-%'
  UNION ALL
  SELECT 'edge HN-0163 SUPERSEDES WO-0067', CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END, CAST(COUNT(*) AS VARCHAR)
  FROM PLANT_BRAIN.BRAIN.EDGES
  WHERE relation = 'SUPERSEDES' AND from_id LIKE 'CARD-HN-0163-%' AND to_id LIKE 'CARD-WO-2026-0067-%'
),
anomaly_checks AS (
  SELECT 'active anomalies = P3, CNC2, CV2 (final day)' AS check_name,
         CASE WHEN COUNT(*) = 3 AND SUM(CASE WHEN asset_id IN ('P3', 'CNC2', 'CV2') AND CAST(start_hr AS DATE) = CAST('2026-08-31' AS DATE) THEN 1 ELSE 0 END) = 3
              THEN 'PASS' ELSE 'FAIL' END AS result, CAST(COUNT(*) AS VARCHAR) || ' active' AS detail
  FROM PLANT_BRAIN.BRAIN.ANOMALIES WHERE is_active
  UNION ALL
  SELECT 'P3 live anomaly matches E1, E2, E3 (WO-0021, WO-0079, WO-0116)',
         CASE WHEN SUM(CASE WHEN wo_id IN ('WO-2026-0021', 'WO-2026-0079', 'WO-2026-0116') AND is_match THEN 1 ELSE 0 END) = 3
              THEN 'PASS' ELSE 'FAIL' END,
         CAST(SUM(CASE WHEN is_match THEN 1 ELSE 0 END) AS VARCHAR) || ' match(es)'
  FROM PLANT_BRAIN.BRAIN.ANOMALY_MATCHES WHERE anomaly_id LIKE 'A-P3-%'
  UNION ALL
  SELECT 'P3 live anomaly does not match non-bearing history',
         CASE WHEN SUM(CASE WHEN is_match AND failure_mode <> 'BEARING_WEAR' THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END, ''
  FROM PLANT_BRAIN.BRAIN.ANOMALY_MATCHES WHERE anomaly_id LIKE 'A-P3-%'
  UNION ALL
  SELECT 'decoys (CNC2, CV2) do not match P3 bearing history',
         CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END, CAST(COUNT(*) AS VARCHAR)
  FROM PLANT_BRAIN.BRAIN.ANOMALY_MATCHES
  WHERE (anomaly_id LIKE 'A-CNC2-%' OR anomaly_id LIKE 'A-CV2-%') AND is_match AND failure_mode = 'BEARING_WEAR'
  UNION ALL
  SELECT 'failure window contains true remaining time (~24 h)',
         CASE WHEN MIN(eta_low_h) <= 24.1 AND MAX(eta_high_h) >= 24.1 THEN 'PASS' ELSE 'FAIL' END,
         CAST(ROUND(MIN(eta_low_h), 1) AS VARCHAR) || ' - ' || CAST(ROUND(MAX(eta_high_h), 1) AS VARCHAR) || ' h'
  FROM PLANT_BRAIN.BRAIN.FAILURE_WINDOWS WHERE asset_id = 'P3'
)
SELECT * FROM card_checks
UNION ALL SELECT * FROM edge_checks
UNION ALL SELECT * FROM anomaly_checks
ORDER BY check_name;
