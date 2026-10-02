-- Plant Brain :: 05_anomaly.sql
-- Deterministic anomaly detection, failure-window estimate and historical pattern match.
-- Plain SQL only (no ML), written in a portable subset so mocks/warehouse.py runs this exact
-- file on DuckDB. Re-run (or CALL BRAIN.REFRESH_ANOMALIES() from 08_procs.sql) when new
-- sensor data lands.
--
-- Method
--   1. Hourly means of RUNNING readings (idle readings during work-order downtime excluded).
--   2. Residual vs the asset's hour-of-day profile (cancels the daily temperature/load cycle).
--   3. Rolling z-score of the 3 h smoothed residual against the trailing week
--      (rows 192..24 back, so a slow ramp can't hide in its own baseline).
--   4. An hour is flagged when any sensor channel has |z| >= 3 in its failure direction.
--   5. Consecutive flagged hours form an anomaly; its signature = channels involved,
--      rise, slope, shape (RAMP/STEP) and temperature lag.
--   6. Pattern match: compare the signature with pre-failure anomalies on the SAME asset
--      (those ending <= 12 h before a corrective work order), aligned to the same age.
--   7. Failure window: low/high of (a) linear extrapolation to the failure-mode threshold and
--      (b) time-to-failure of the matched historical episodes. Labeled as an estimate.

USE ROLE PB_ROLE;
USE WAREHOUSE PB_WH;
USE SCHEMA PLANT_BRAIN.BRAIN;

-- 1. Hourly running means --------------------------------------------------------------
CREATE OR REPLACE TABLE BRAIN.SENSOR_HOURLY AS
WITH r AS (
  SELECT s.*, AVG(s.current_a) OVER (PARTITION BY s.asset_id) AS avg_curr
  FROM RAW.SENSOR_READINGS s
)
SELECT
  asset_id,
  DATE_TRUNC('hour', ts)                                    AS hr,
  AVG(vibration_rms)                                        AS vib,
  AVG(temperature_c)                                        AS temp,
  AVG(pressure_bar)                                         AS pres,
  AVG(current_a)                                            AS curr,
  STDDEV_SAMP(current_a) / NULLIF(AVG(current_a), 0)       AS curr_cv,
  STDDEV_SAMP(pressure_bar) / NULLIF(AVG(pressure_bar), 0) AS pres_cv,
  COUNT(*)                                                  AS n_readings
FROM r
WHERE current_a >= 0.5 * avg_curr
GROUP BY asset_id, DATE_TRUNC('hour', ts)
HAVING COUNT(*) >= 6;

-- 2-4. Residuals, rolling z-scores, flags -----------------------------------------------
CREATE OR REPLACE TABLE BRAIN.SENSOR_SCORES AS
WITH prof AS (
  SELECT asset_id, EXTRACT(hour FROM hr) AS hod,
         AVG(vib) AS p_vib, AVG(temp) AS p_temp, AVG(pres) AS p_pres, AVG(curr) AS p_curr,
         AVG(curr_cv) AS p_curr_cv, AVG(pres_cv) AS p_pres_cv
  FROM BRAIN.SENSOR_HOURLY
  GROUP BY asset_id, EXTRACT(hour FROM hr)
),
resid AS (
  SELECT h.asset_id, h.hr, h.vib, h.temp, h.pres, h.curr,
         100 * (h.vib  / NULLIF(p.p_vib, 0)  - 1)  AS r_vib,     -- % vs profile
         h.temp - p.p_temp                          AS r_temp,    -- degC vs profile
         100 * (h.pres / NULLIF(p.p_pres, 0) - 1)  AS r_pres,
         100 * (h.curr / NULLIF(p.p_curr, 0) - 1)  AS r_curr,
         h.curr_cv / NULLIF(p.p_curr_cv, 0)         AS r_curr_noise,  -- x normal noise
         h.pres_cv / NULLIF(p.p_pres_cv, 0)         AS r_pres_noise
  FROM BRAIN.SENSOR_HOURLY h
  JOIN prof p ON p.asset_id = h.asset_id AND p.hod = EXTRACT(hour FROM h.hr)
),
smooth AS (
  SELECT *,
    AVG(r_vib)  OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS s_vib,
    AVG(r_temp) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS s_temp,
    AVG(r_pres) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS s_pres,
    AVG(r_curr) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS s_curr,
    AVG(r_curr_noise) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS s_curr_noise,
    AVG(r_pres_noise) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS s_pres_noise
  FROM resid
),
base AS (
  SELECT *,
    AVG(s_vib)  OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS m_vib,  STDDEV_SAMP(s_vib)  OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS sd_vib,
    AVG(s_temp) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS m_temp, STDDEV_SAMP(s_temp) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS sd_temp,
    AVG(s_pres) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS m_pres, STDDEV_SAMP(s_pres) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS sd_pres,
    AVG(s_curr) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS m_curr, STDDEV_SAMP(s_curr) OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS sd_curr,
    COUNT(*)    OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN 192 PRECEDING AND 24 PRECEDING) AS n_base
  FROM smooth
),
z AS (
  SELECT *,
    (s_vib  - m_vib)  / GREATEST(COALESCE(sd_vib, 0), 0.6)  AS z_vib,
    (s_temp - m_temp) / GREATEST(COALESCE(sd_temp, 0), 0.25) AS z_temp,
    (s_pres - m_pres) / GREATEST(COALESCE(sd_pres, 0), 0.4)  AS z_pres,
    (s_curr - m_curr) / GREATEST(COALESCE(sd_curr, 0), 0.6)  AS z_curr
  FROM base
)
SELECT
  asset_id, hr, vib, temp, pres, curr,
  s_vib AS vib_resid_pct, s_temp AS temp_resid_c, s_pres AS pres_resid_pct, s_curr AS curr_resid_pct,
  s_curr_noise AS curr_noise_x, s_pres_noise AS pres_noise_x,
  z_vib, z_temp, z_pres, z_curr,
  (n_base >= 72 AND z_vib  >= 3)                   AS f_vib_up,
  (n_base >= 72 AND z_temp >= 3)                   AS f_temp_up,
  (n_base >= 72 AND z_pres <= -3)                  AS f_pres_down,
  (n_base >= 72 AND z_curr >= 3)                   AS f_curr_up,
  (n_base >= 72 AND COALESCE(s_curr_noise, 0) >= 2.5) AS f_curr_noisy,
  (n_base >= 72 AND COALESCE(s_pres_noise, 0) >= 2.5) AS f_pres_noisy
FROM z;

-- 5. Anomaly episodes (islands of flagged hours, gaps <= 2 h bridged) --------------------
CREATE OR REPLACE TABLE BRAIN.ANOMALY_HOURS AS
WITH flagged AS (
  SELECT *, (f_vib_up OR f_temp_up OR f_pres_down OR f_curr_up OR f_curr_noisy OR f_pres_noisy) AS f_any
  FROM BRAIN.SENSOR_SCORES
),
f AS (
  SELECT *, LAG(hr) OVER (PARTITION BY asset_id ORDER BY hr) AS prev_hr
  FROM flagged WHERE f_any
),
isl AS (
  SELECT *, SUM(CASE WHEN prev_hr IS NULL OR DATEDIFF('hour', prev_hr, hr) > 3 THEN 1 ELSE 0 END)
              OVER (PARTITION BY asset_id ORDER BY hr ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS island
  FROM f
)
SELECT
  asset_id, island, hr,
  MIN(hr) OVER (PARTITION BY asset_id, island) AS start_hr,
  DATEDIFF('hour', MIN(hr) OVER (PARTITION BY asset_id, island), hr) AS age_h,
  vib_resid_pct, temp_resid_c, pres_resid_pct, curr_resid_pct, curr_noise_x, pres_noise_x,
  f_vib_up, f_temp_up, f_pres_down, f_curr_up, f_curr_noisy, f_pres_noisy
FROM isl;

CREATE OR REPLACE TABLE BRAIN.ANOMALIES AS
WITH last_data AS (
  SELECT asset_id, MAX(hr) AS last_hr FROM BRAIN.SENSOR_HOURLY GROUP BY asset_id
),
ep AS (
  SELECT
    asset_id, island, MIN(hr) AS start_hr, MAX(hr) AS end_hr,
    DATEDIFF('hour', MIN(hr), MAX(hr)) + 1 AS duration_h,
    MAX(CASE WHEN f_vib_up THEN 1 ELSE 0 END)     AS s_vib_up,
    MAX(CASE WHEN f_temp_up THEN 1 ELSE 0 END)    AS s_temp_up,
    MAX(CASE WHEN f_pres_down THEN 1 ELSE 0 END)  AS s_pres_down,
    MAX(CASE WHEN f_curr_up THEN 1 ELSE 0 END)    AS s_curr_up,
    MAX(CASE WHEN f_curr_noisy THEN 1 ELSE 0 END) AS s_curr_noisy,
    MAX(CASE WHEN f_pres_noisy THEN 1 ELSE 0 END) AS s_pres_noisy,
    MIN(CASE WHEN f_vib_up THEN age_h END)        AS first_vib_h,
    MIN(CASE WHEN f_temp_up THEN age_h END)       AS first_temp_h,
    MAX(ABS(vib_resid_pct))                       AS peak_vib_pct,
    MAX(ABS(temp_resid_c))                        AS peak_temp_c,
    MAX(ABS(pres_resid_pct))                      AS peak_pres_pct
  FROM BRAIN.ANOMALY_HOURS
  GROUP BY asset_id, island
),
edges AS (   -- first and last 3 hours, for rise / slope / shape
  SELECT asset_id, island,
    AVG(CASE WHEN age_h <= 2 THEN vib_resid_pct END)  AS vib_first,
    AVG(CASE WHEN age_h <= 2 THEN temp_resid_c END)   AS temp_first
  FROM BRAIN.ANOMALY_HOURS GROUP BY asset_id, island
),
lasts AS (
  SELECT h.asset_id, h.island,
    AVG(h.vib_resid_pct) AS vib_last, AVG(h.temp_resid_c) AS temp_last, AVG(h.pres_resid_pct) AS pres_last
  FROM BRAIN.ANOMALY_HOURS h
  JOIN ep e ON e.asset_id = h.asset_id AND e.island = h.island
  WHERE h.hr > DATEADD('hour', -3, e.end_hr)
  GROUP BY h.asset_id, h.island
)
SELECT
  'A-' || e.asset_id || '-' || CAST(EXTRACT(year FROM e.start_hr) AS VARCHAR)
       || LPAD(CAST(EXTRACT(month FROM e.start_hr) AS VARCHAR), 2, '0')
       || LPAD(CAST(EXTRACT(day FROM e.start_hr) AS VARCHAR), 2, '0')
       || LPAD(CAST(EXTRACT(hour FROM e.start_hr) AS VARCHAR), 2, '0')        AS anomaly_id,
  e.asset_id, a.asset_type, a.line_id,
  e.start_hr, e.end_hr, e.duration_h,
  (e.end_hr >= DATEADD('hour', -1, d.last_hr))                                AS is_active,
  e.s_vib_up, e.s_temp_up, e.s_pres_down, e.s_curr_up, e.s_curr_noisy, e.s_pres_noisy,
  TRIM(CASE WHEN e.s_vib_up = 1 THEN 'vibration ' ELSE '' END
    || CASE WHEN e.s_temp_up = 1 THEN 'temperature ' ELSE '' END
    || CASE WHEN e.s_pres_down = 1 THEN 'pressure-drop ' ELSE '' END
    || CASE WHEN e.s_curr_up = 1 THEN 'current ' ELSE '' END
    || CASE WHEN e.s_curr_noisy = 1 THEN 'current-noise ' ELSE '' END
    || CASE WHEN e.s_pres_noisy = 1 THEN 'pressure-noise ' ELSE '' END)      AS sensors,
  l.vib_last  AS vib_rise_pct,
  l.temp_last AS temp_rise_c,
  l.pres_last AS pres_change_pct,
  (l.vib_last - g.vib_first) / GREATEST(e.duration_h - 2, 1)                AS vib_slope_pct_h,
  CASE WHEN e.s_vib_up = 1 AND g.vib_first >= 0.6 * l.vib_last THEN 'STEP'
       WHEN e.s_vib_up = 1 THEN 'RAMP' ELSE 'N/A' END                       AS vib_shape,
  e.first_temp_h - e.first_vib_h                                             AS temp_lag_h,
  CASE WHEN e.peak_vib_pct >= 15 OR e.peak_temp_c >= 6 OR e.peak_pres_pct >= 6 THEN 'HIGH'
       WHEN e.peak_vib_pct >= 8  OR e.peak_temp_c >= 3 OR e.peak_pres_pct >= 3 THEN 'MEDIUM'
       ELSE 'LOW' END                                                        AS severity
FROM ep e
JOIN edges g ON g.asset_id = e.asset_id AND g.island = e.island
JOIN lasts l ON l.asset_id = e.asset_id AND l.island = e.island
JOIN RAW.ASSETS a ON a.asset_id = e.asset_id
JOIN last_data d ON d.asset_id = e.asset_id
WHERE e.duration_h >= 3;

-- 6. Historical pre-failure signatures + pattern match -------------------------------------
-- An anomaly is "pre-failure" if it ends <= 12 h before (or during) a corrective work order on
-- the same asset; it inherits that work order's failure mode.
CREATE OR REPLACE VIEW BRAIN.PREFAILURE_EPISODES AS
SELECT an.anomaly_id, an.asset_id, an.start_hr, an.end_hr,
       w.wo_id, w.failure_mode_code AS failure_mode, w.reported_at, w.technician_id,
       DATEDIFF('hour', an.start_hr, w.reported_at) AS hours_start_to_failure
FROM BRAIN.ANOMALIES an
JOIN RAW.WORK_ORDERS w
  ON w.asset_id = an.asset_id
 AND w.wo_type = 'CORRECTIVE'
 AND w.reported_at >= an.end_hr
 AND w.reported_at <= DATEADD('hour', 12, an.end_hr)
WHERE NOT an.is_active
QUALIFY ROW_NUMBER() OVER (PARTITION BY an.anomaly_id ORDER BY w.reported_at) = 1;

-- Signature of every anomaly re-computed at a given age, so a 24 h-old live anomaly is compared
-- with the first 24 h of each historical episode.
CREATE OR REPLACE TABLE BRAIN.ANOMALY_MATCHES AS
WITH live AS (
  SELECT * FROM BRAIN.ANOMALIES WHERE is_active
),
hist_at_age AS (
  SELECT l.anomaly_id AS live_id, p.anomaly_id AS hist_id, p.wo_id, p.failure_mode,
         p.hours_start_to_failure, p.technician_id,
         MAX(CASE WHEN h.f_vib_up THEN 1 ELSE 0 END)     AS s_vib_up,
         MAX(CASE WHEN h.f_temp_up THEN 1 ELSE 0 END)    AS s_temp_up,
         MAX(CASE WHEN h.f_pres_down THEN 1 ELSE 0 END)  AS s_pres_down,
         MAX(CASE WHEN h.f_curr_up THEN 1 ELSE 0 END)    AS s_curr_up,
         MAX(CASE WHEN h.f_curr_noisy THEN 1 ELSE 0 END) AS s_curr_noisy,
         MAX(CASE WHEN h.f_pres_noisy THEN 1 ELSE 0 END) AS s_pres_noisy,
         MIN(CASE WHEN h.f_temp_up THEN h.age_h END) - MIN(CASE WHEN h.f_vib_up THEN h.age_h END) AS temp_lag_h,
         (AVG(CASE WHEN h.age_h > l.duration_h - 4 THEN h.vib_resid_pct END)
          - AVG(CASE WHEN h.age_h <= 2 THEN h.vib_resid_pct END)) / GREATEST(l.duration_h - 2, 1) AS vib_slope_pct_h
  FROM live l
  JOIN BRAIN.PREFAILURE_EPISODES p ON p.asset_id = l.asset_id
  JOIN BRAIN.ANOMALY_HOURS h ON h.asset_id = p.asset_id AND h.start_hr = p.start_hr AND h.age_h < l.duration_h
  GROUP BY l.anomaly_id, l.duration_h, p.anomaly_id, p.wo_id, p.failure_mode, p.hours_start_to_failure, p.technician_id
),
scored AS (
  SELECT h.*, l.duration_h AS live_age_h,
    -- Jaccard similarity of the channels involved
    (  LEAST(h.s_vib_up, l.s_vib_up) + LEAST(h.s_temp_up, l.s_temp_up) + LEAST(h.s_pres_down, l.s_pres_down)
     + LEAST(h.s_curr_up, l.s_curr_up) + LEAST(h.s_curr_noisy, l.s_curr_noisy) + LEAST(h.s_pres_noisy, l.s_pres_noisy))
    / NULLIF(GREATEST(h.s_vib_up, l.s_vib_up) + GREATEST(h.s_temp_up, l.s_temp_up) + GREATEST(h.s_pres_down, l.s_pres_down)
     + GREATEST(h.s_curr_up, l.s_curr_up) + GREATEST(h.s_curr_noisy, l.s_curr_noisy) + GREATEST(h.s_pres_noisy, l.s_pres_noisy), 0) AS channel_sim,
    CASE WHEN l.s_vib_up = 0 AND h.s_vib_up = 0 THEN 1
         ELSE 1 - LEAST(1, ABS(COALESCE(h.vib_slope_pct_h, 0) - COALESCE(l.vib_slope_pct_h, 0))
                          / GREATEST(ABS(COALESCE(h.vib_slope_pct_h, 0)), ABS(COALESCE(l.vib_slope_pct_h, 0)), 0.1)) END AS slope_sim,
    CASE WHEN h.temp_lag_h IS NULL AND l.temp_lag_h IS NULL THEN 1
         WHEN h.temp_lag_h IS NULL OR l.temp_lag_h IS NULL THEN 0
         ELSE 1 - LEAST(1, ABS(h.temp_lag_h - l.temp_lag_h) / 12.0) END    AS lag_sim
  FROM hist_at_age h
  JOIN live l ON l.anomaly_id = h.live_id
)
SELECT live_id AS anomaly_id, hist_id, wo_id, failure_mode, technician_id, hours_start_to_failure, live_age_h,
       channel_sim, slope_sim, lag_sim,
       0.5 * COALESCE(channel_sim, 0) + 0.3 * slope_sim + 0.2 * lag_sim AS score,
       (0.5 * COALESCE(channel_sim, 0) + 0.3 * slope_sim + 0.2 * lag_sim) >= 0.75 AS is_match
FROM scored;

-- 7. Failure window (estimate) -------------------------------------------------------------
-- low/high of: linear trend of the anomaly's vibration slope to the failure-mode threshold, and the
-- median time-to-failure of the matched past episodes minus the time already elapsed.
CREATE OR REPLACE VIEW BRAIN.FAILURE_WINDOWS AS
WITH best_fm AS (
  SELECT anomaly_id, failure_mode, COUNT(*) AS n_matches, AVG(score) AS avg_score,
         MEDIAN(hours_start_to_failure) AS median_start_to_failure_h
  FROM BRAIN.ANOMALY_MATCHES
  WHERE is_match
  GROUP BY anomaly_id, failure_mode
  QUALIFY ROW_NUMBER() OVER (PARTITION BY anomaly_id ORDER BY COUNT(*) DESC, AVG(score) DESC) = 1
),
est AS (
  SELECT a.anomaly_id, a.asset_id, a.duration_h, a.vib_rise_pct, a.vib_slope_pct_h,
         b.failure_mode, b.n_matches, b.avg_score,
         CASE WHEN b.failure_mode = 'BEARING_WEAR' AND a.vib_slope_pct_h > 0.05
              THEN (35 - a.vib_rise_pct) / a.vib_slope_pct_h END   AS linear_eta_h,
         b.median_start_to_failure_h - a.duration_h                AS analog_eta_h
  FROM BRAIN.ANOMALIES a
  JOIN best_fm b ON b.anomaly_id = a.anomaly_id
  WHERE a.is_active
)
SELECT
  anomaly_id, asset_id, failure_mode, n_matches, avg_score,
  CASE failure_mode WHEN 'BEARING_WEAR' THEN 'vibration_rms >= 1.35 x baseline' END AS threshold_rule,
  vib_rise_pct, vib_slope_pct_h, linear_eta_h, analog_eta_h,
  LEAST(COALESCE(linear_eta_h, analog_eta_h), analog_eta_h)       AS eta_low_h,
  GREATEST(COALESCE(linear_eta_h, analog_eta_h), analog_eta_h)    AS eta_high_h,
  'ESTIMATE: one bound = median time-to-failure of matched past episodes, the other = linear trend to threshold' AS note
FROM est;
