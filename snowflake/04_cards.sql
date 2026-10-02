-- Plant Brain :: 04_cards.sql
-- The Brain: knowledge cards + graph edges, extracted from work orders and handover notes.
--
--   BRAIN.CARD_SOURCES      view   every text the Brain learns from (work orders, handover notes)
--   BRAIN.CARDS_RAW         table  extraction output, one row per card (cache: never re-extracted)
--   BRAIN.CARD_EXTRACT_LOG  table  which (source, text hash) have been processed
--   BRAIN.EXTRACT_NEW_CARDS proc   Cortex AI_COMPLETE with a JSON schema over NEW sources only
--   BRAIN.CARD_EXTRACT_TASK task   optional scheduled backfill (created SUSPENDED for cost)
--   BRAIN.CARDS             view   cards + recurrence rule (outcome RECURRED) + staleness flag
--   BRAIN.EDGES             view   card->asset / failure mode / technician, card->card CONTRADICTS|SUPERSEDES
--
-- Extraction rules live in coco/skills/card-extractor/SKILL.md. The local mock
-- (mocks/cortex.py) applies the same rules without an LLM. Everything except the procedure
-- and the task is portable SQL that mocks/warehouse.py also runs on DuckDB.

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.BRAIN;

-- ---------------------------------------------------------------------------
-- Sources
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW BRAIN.CARD_SOURCES AS
SELECT 'WORK_ORDER'                AS source_type,
       w.wo_id                     AS source_id,
       w.asset_id,
       w.failure_mode_code,
       w.wo_type                   AS source_subtype,
       w.technician_id             AS author_technician_id,
       w.closed_at                 AS source_ts,
       w.resolution_note           AS source_text,
       MD5(w.resolution_note)      AS text_hash
FROM RAW.WORK_ORDERS w
WHERE w.status = 'CLOSED' AND w.resolution_note IS NOT NULL
UNION ALL
SELECT 'HANDOVER_NOTE', h.note_id, NULL, NULL, h.note_type, h.author_technician_id,
       h.created_at, h.note_text, MD5(h.note_text)
FROM RAW.HANDOVER_NOTES h
WHERE h.note_text IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Extraction cache
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS BRAIN.CARDS_RAW (
  source_type      VARCHAR,
  source_id        VARCHAR,
  text_hash        VARCHAR,
  card_seq         INTEGER,
  card_type        VARCHAR,   -- FIX | GOTCHA | SYMPTOM_PATTERN | CONVENTION
  asset_id         VARCHAR,
  failure_mode     VARCHAR,
  symptom_summary  VARCHAR,
  action_taken     VARCHAR,
  parts            VARCHAR,
  outcome          VARCHAR,   -- RESOLVED | RECURRED | UNKNOWN (as stated in the text)
  source_excerpt   VARCHAR,
  confidence       FLOAT,
  extracted_by     VARCHAR,   -- model name, or 'mock-rules'
  extracted_at     TIMESTAMP_NTZ
);

CREATE TABLE IF NOT EXISTS BRAIN.CARD_EXTRACT_LOG (
  source_type   VARCHAR,
  source_id     VARCHAR,
  text_hash     VARCHAR,
  n_cards       INTEGER,
  extracted_by  VARCHAR,
  extracted_at  TIMESTAMP_NTZ
);

-- ---------------------------------------------------------------------------
-- Cortex extraction (Snowflake only). Processes sources whose (id, text hash) is not in the
-- log yet, so re-running is free when nothing changed. CLOSE_JOB calls it for the learning loop.
-- Model: any AI_COMPLETE model available in your region (cross-region enabled in 00_setup.sql).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE BRAIN.EXTRACT_NEW_CARDS(MODEL VARCHAR DEFAULT 'claude-haiku-4-5', MAX_ROWS INTEGER DEFAULT 1000)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  n INTEGER DEFAULT 0;
BEGIN
  CREATE OR REPLACE TEMPORARY TABLE BRAIN.TMP_TODO AS
    SELECT s.*
    FROM BRAIN.CARD_SOURCES s
    LEFT JOIN BRAIN.CARD_EXTRACT_LOG l
      ON l.source_type = s.source_type AND l.source_id = s.source_id AND l.text_hash = s.text_hash
    WHERE l.source_id IS NULL
    ORDER BY s.source_ts
    LIMIT :MAX_ROWS;

  CREATE OR REPLACE TEMPORARY TABLE BRAIN.TMP_EXTRACTED AS
    SELECT t.*,
      AI_COMPLETE(
        model => :MODEL,
        prompt =>
          'You extract maintenance knowledge cards from factory notes (fictional plant). Notes are messy: '
          || 'abbreviations (brg=bearing, vib=vibration, chngd=changed, repl=replaced), typos and Hinglish '
          || '(warna = otherwise, phir se = again, wapas aaya = came back, sirf = only, badla = changed). '
          || 'Rules: (1) Only extract what the text states; never invent. (2) card_type FIX = an action that '
          || 'fixed a problem; GOTCHA = a warning or something that did NOT work; SYMPTOM_PATTERN = how a '
          || 'failure shows up in advance; CONVENTION = a standing practice or rule. (3) asset_id must be one of '
          || 'CNC1-CNC4, P1-P3, AC1, AC2, CV1-CV3, or null. (4) failure_mode must be one of BEARING_WEAR, '
          || 'SEAL_LEAK, SPINDLE_MISALIGNMENT, BELT_SLIP, VALVE_STICKING, COOLANT_BLOCKAGE, MOTOR_OVERHEAT, '
          || 'AIR_FILTER_CLOG, TOOL_WEAR, OIL_CONTAMINATION, or null. (5) outcome RESOLVED / RECURRED / UNKNOWN '
          || 'only as stated in the text; a fix the author presents as the working fix ("Fix = ...", "use X") is '
          || 'RESOLVED; "came back", "does not hold", "wapas", "phir se" is RECURRED. (6) source_excerpt = an exact '
          || 'substring of the text that supports the card: the whole sentence it comes from (max 220 characters). '
          || '(7) Routine chatter (targets, canteen, housekeeping, safety talk, "PM done", "running ok") gives no card. '
          || 'But a workaround or warning ("do X otherwise Y", "use X, Y fails", "dont", "only", "warna") is a GOTCHA, '
          || 'not chatter. (8) One sentence can yield several cards (e.g. a FIX and a GOTCHA). '
          || 'Example: "Fix = replace bearing AND switch grease from LG-2 to HT-3. Only bearing change does NOT hold - '
          || 'it came back in 9 days. Keep min 2 bearings in store." gives FIX RESOLVED, GOTCHA RECURRED, CONVENTION. '
          || '(9) Never output null: use outcome UNKNOWN and an empty string for any text you cannot fill '
          || '(the action_taken of a warning is the advised action). '
          || '\nSOURCE TYPE: ' || t.source_type
          || '\nASSET (if known): ' || COALESCE(t.asset_id, 'unknown')
          || '\nFAILURE MODE CODE (if known): ' || COALESCE(t.failure_mode_code, 'unknown')
          || '\nPARTS USED (work orders): ' || COALESCE(w.parts_used, 'n/a')
          || '\nTEXT: ' || t.source_text,
        model_parameters => {'temperature': 0},
        response_format => {
          'type': 'json',
          'schema': {
            'type': 'object',
            'properties': {
              'cards': {
                'type': 'array',
                'items': {
                  'type': 'object',
                  'properties': {
                    'card_type': {'type': 'string', 'enum': ['FIX', 'GOTCHA', 'SYMPTOM_PATTERN', 'CONVENTION']},
                    'asset_id': {'type': 'string'},
                    'failure_mode': {'type': 'string'},
                    'symptom_summary': {'type': 'string'},
                    'action_taken': {'type': 'string'},
                    'parts': {'type': 'string'},
                    'outcome': {'type': 'string', 'enum': ['RESOLVED', 'RECURRED', 'UNKNOWN']},
                    'source_excerpt': {'type': 'string'},
                    'confidence': {'type': 'number'}
                  },
                  'required': ['card_type', 'symptom_summary', 'action_taken', 'outcome', 'source_excerpt', 'confidence']
                }
              }
            },
            'required': ['cards']
          }
        }
      ) AS resp
    FROM BRAIN.TMP_TODO t
    LEFT JOIN RAW.WORK_ORDERS w ON t.source_type = 'WORK_ORDER' AND w.wo_id = t.source_id;

  INSERT INTO BRAIN.CARDS_RAW
    SELECT e.source_type, e.source_id, e.text_hash, f.index + 1,
           f.value:card_type::VARCHAR,
           COALESCE(NULLIF(f.value:asset_id::VARCHAR, ''), e.asset_id),
           COALESCE(NULLIF(f.value:failure_mode::VARCHAR, ''), e.failure_mode_code),
           f.value:symptom_summary::VARCHAR,
           f.value:action_taken::VARCHAR,
           f.value:parts::VARCHAR,
           f.value:outcome::VARCHAR,
           f.value:source_excerpt::VARCHAR,
           f.value:confidence::FLOAT,
           :MODEL, CURRENT_TIMESTAMP()
    FROM BRAIN.TMP_EXTRACTED e,
         LATERAL FLATTEN(input => e.resp:cards) f;

  -- A NULL response is a failed call (e.g. output rejected by the schema): leave it unlogged so the next run retries.
  INSERT INTO BRAIN.CARD_EXTRACT_LOG
    SELECT source_type, source_id, text_hash, COALESCE(ARRAY_SIZE(resp:cards), 0), :MODEL, CURRENT_TIMESTAMP()
    FROM BRAIN.TMP_EXTRACTED
    WHERE resp IS NOT NULL;

  SELECT COUNT(*) INTO :n FROM BRAIN.TMP_EXTRACTED;
  CALL BRAIN.REFRESH_CARD_SEARCH_DOCS();
  RETURN n || ' new source(s) extracted with ' || MODEL;
END;
$$;

-- Cortex Search can't track changes on BRAIN.CARDS (the view has a subquery, GROUP BY and outer
-- joins), so the search service reads this plain copy. Refreshed after every extraction.
-- DELETE + INSERT (not CREATE OR REPLACE) keeps the table, and its change tracking, in place.
CREATE OR REPLACE PROCEDURE BRAIN.REFRESH_CARD_SEARCH_DOCS()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
  CREATE TABLE IF NOT EXISTS BRAIN.CARD_SEARCH_DOCS CHANGE_TRACKING = TRUE AS
    SELECT card_id, search_text, card_type, asset_id, failure_mode, outcome,
           symptom_summary, action_taken, source_type, source_id, source_excerpt,
           author_name, confidence, is_stale
    FROM BRAIN.CARDS WHERE FALSE;
  DELETE FROM BRAIN.CARD_SEARCH_DOCS;
  INSERT INTO BRAIN.CARD_SEARCH_DOCS
    SELECT card_id, search_text, card_type, asset_id, failure_mode, outcome,
           symptom_summary, action_taken, source_type, source_id, source_excerpt,
           author_name, confidence, is_stale
    FROM BRAIN.CARDS;
  RETURN 'card search docs refreshed';
END;
$$;

-- Optional hourly backfill. Created SUSPENDED: the demo calls the proc directly (CLOSE_JOB does).
-- Enable with: ALTER TASK BRAIN.CARD_EXTRACT_TASK RESUME;
CREATE OR REPLACE TASK BRAIN.CARD_EXTRACT_TASK
  WAREHOUSE = PB_WH
  SCHEDULE = '60 MINUTE'
  COMMENT = 'Incremental card extraction for new/changed sources'
AS
  CALL BRAIN.EXTRACT_NEW_CARDS();

-- ---------------------------------------------------------------------------
-- Cards (portable view): recurrence rule + staleness
-- A FIX card from a corrective work order is RECURRED when the same asset + failure mode is
-- reported again within 14 days of that work order closing. The text alone can't tell you
-- this (the junior's note says "trial run ok"); the link between work orders can.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW BRAIN.CARDS AS
WITH recur AS (
  SELECT w1.wo_id,
         MIN(w2.wo_id)                                 AS recurred_by_wo,
         MIN(DATEDIFF('day', w1.closed_at, w2.reported_at)) AS recurred_after_days
  FROM RAW.WORK_ORDERS w1
  JOIN RAW.WORK_ORDERS w2
    ON w2.asset_id = w1.asset_id
   AND w2.failure_mode_code = w1.failure_mode_code
   AND w2.wo_type = 'CORRECTIVE'
   AND w2.reported_at > w1.closed_at
   AND w2.reported_at <= DATEADD('day', 14, w1.closed_at)
  WHERE w1.wo_type = 'CORRECTIVE'
  GROUP BY w1.wo_id
),
fixing_changes AS (   -- asset changes that are just the recorded fix of a corrective WO
  SELECT c.change_id
  FROM RAW.ASSET_CHANGES c
  JOIN RAW.WORK_ORDERS w
    ON w.asset_id = c.asset_id AND ABS(DATEDIFF('minute', w.closed_at, c.changed_at)) <= 60
),
stale AS (
  SELECT r.source_type, r.source_id, r.card_seq,
         MIN(c.changed_at) AS first_change_at,
         MIN(c.description) AS change_description
  FROM BRAIN.CARDS_RAW r
  JOIN BRAIN.CARD_SOURCES s ON s.source_type = r.source_type AND s.source_id = r.source_id
  JOIN RAW.ASSET_CHANGES c ON c.asset_id = r.asset_id AND c.changed_at > s.source_ts
  WHERE r.card_type IN ('GOTCHA', 'CONVENTION')
    AND c.change_type IN ('PART_REPLACEMENT', 'FIRMWARE_UPDATE')
    AND c.change_id NOT IN (SELECT change_id FROM fixing_changes)
  GROUP BY r.source_type, r.source_id, r.card_seq
)
SELECT
  'CARD-' || r.source_id || '-' || CAST(r.card_seq AS VARCHAR)            AS card_id,
  r.card_type,
  r.asset_id,
  COALESCE(r.failure_mode, w.failure_mode_code)                            AS failure_mode,
  r.symptom_summary,
  r.action_taken,
  COALESCE(r.parts, w.parts_used)                                          AS parts,
  CASE WHEN r.source_type = 'WORK_ORDER' AND r.card_type = 'FIX' AND rc.wo_id IS NOT NULL
       THEN 'RECURRED' ELSE r.outcome END                                  AS outcome,
  CASE WHEN r.source_type = 'WORK_ORDER' AND r.card_type = 'FIX' AND rc.wo_id IS NOT NULL
       THEN 'recurrence rule: ' || rc.recurred_by_wo || ' re-opened the same failure after '
            || CAST(rc.recurred_after_days AS VARCHAR) || ' days'
       ELSE 'stated in source' END                                         AS outcome_basis,
  rc.recurred_by_wo,
  s.author_technician_id,
  t.full_name                                                              AS author_name,
  r.source_type,
  r.source_id,
  r.source_excerpt,
  r.confidence,
  s.source_ts                                                              AS created_at,
  st.first_change_at IS NOT NULL                                           AS is_stale,
  st.change_description                                                    AS stale_reason,
  COALESCE(r.symptom_summary, '') || ' | ' || COALESCE(r.action_taken, '') || ' | '
    || COALESCE(r.source_excerpt, '')                                      AS search_text,
  r.extracted_by
FROM BRAIN.CARDS_RAW r
JOIN BRAIN.CARD_SOURCES s ON s.source_type = r.source_type AND s.source_id = r.source_id AND s.text_hash = r.text_hash
LEFT JOIN RAW.WORK_ORDERS w ON r.source_type = 'WORK_ORDER' AND w.wo_id = r.source_id
LEFT JOIN recur rc ON r.source_type = 'WORK_ORDER' AND rc.wo_id = r.source_id
LEFT JOIN RAW.TECHNICIANS t ON t.technician_id = s.author_technician_id
LEFT JOIN stale st ON st.source_type = r.source_type AND st.source_id = r.source_id AND st.card_seq = r.card_seq;

-- ---------------------------------------------------------------------------
-- Edges (portable view)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW BRAIN.EDGES AS
SELECT 'CARD' AS from_type, card_id AS from_id, 'ASSET' AS to_type, asset_id AS to_id, 'ABOUT_ASSET' AS relation
FROM BRAIN.CARDS WHERE asset_id IS NOT NULL
UNION ALL
SELECT 'CARD', card_id, 'FAILURE_MODE', failure_mode, 'ABOUT_FAILURE_MODE'
FROM BRAIN.CARDS WHERE failure_mode IS NOT NULL
UNION ALL
SELECT 'CARD', card_id, 'TECHNICIAN', author_technician_id, 'AUTHORED_BY'
FROM BRAIN.CARDS WHERE author_technician_id IS NOT NULL
UNION ALL
-- the recurrence work order's FIX card contradicts the fix that didn't hold
SELECT 'CARD', newer.card_id, 'CARD', older.card_id, 'CONTRADICTS'
FROM BRAIN.CARDS older
JOIN BRAIN.CARDS newer
  ON newer.source_type = 'WORK_ORDER' AND newer.source_id = older.recurred_by_wo AND newer.card_type = 'FIX'
WHERE older.outcome = 'RECURRED' AND older.recurred_by_wo IS NOT NULL
UNION ALL
-- later resolved fixes on the same asset + failure mode supersede it
SELECT 'CARD', newer.card_id, 'CARD', older.card_id, 'SUPERSEDES'
FROM BRAIN.CARDS older
JOIN BRAIN.CARDS newer
  ON newer.asset_id = older.asset_id
 AND newer.failure_mode = older.failure_mode
 AND newer.card_type = 'FIX'
 AND newer.outcome = 'RESOLVED'
 AND newer.created_at > older.created_at
 AND newer.source_id <> COALESCE(older.recurred_by_wo, '')
WHERE older.outcome = 'RECURRED' AND older.card_type = 'FIX' AND older.recurred_by_wo IS NOT NULL;
