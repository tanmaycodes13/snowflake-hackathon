"""Verified analytics queries (keywords prefixed "!" are strong: weight 2, others weight 1): the single source for
  * the semantic view's AI_VERIFIED_QUERIES (scripts/render_semantic_view.py -> 07_semantic_view.sql)
  * the deterministic analytics router used by Ask the Plant (Snowflake mode and mock mode).

SQL uses {placeholders}: logical table names inside the semantic view, physical names when run directly.
Dates are anchored to the latest date in the data (the dataset ends 2026-08-31), not CURRENT_DATE.
"""
PHYSICAL = {
    "oee_daily": "PLANT_BRAIN.CORE.OEE_DAILY",
    "line_oee": "PLANT_BRAIN.CORE.OEE_LINE_DAILY",
    "work_orders": "PLANT_BRAIN.RAW.WORK_ORDERS",
    "technicians": "PLANT_BRAIN.RAW.TECHNICIANS",
    "spare_parts": "PLANT_BRAIN.RAW.SPARE_PARTS",
    "assets": "PLANT_BRAIN.RAW.ASSETS",
}
LOGICAL = {k: k for k in PHYSICAL}

VERIFIED_QUERIES = [
    dict(name="oee_by_line_last_week",
         question="What was the OEE for each line last week?",
         keywords=["!line", "oee", "week", "each line"],
         sql="""SELECT line_id, ROUND(AVG(oee), 4) AS avg_oee, ROUND(AVG(availability), 4) AS avg_availability,
       ROUND(AVG(performance), 4) AS avg_performance, ROUND(AVG(quality), 4) AS avg_quality
FROM {line_oee}
WHERE oee_date > DATEADD('day', -7, (SELECT MAX(oee_date) FROM {line_oee}))
GROUP BY line_id ORDER BY line_id"""),
    dict(name="top_downtime_causes_this_month",
         question="What are the top downtime causes this month?",
         keywords=["!cause", "!reason", "downtime", "month", "top"],
         sql="""SELECT COALESCE(failure_mode_code, 'UNCLASSIFIED') AS failure_mode, COUNT(*) AS breakdowns,
       SUM(downtime_min) AS downtime_min
FROM {work_orders}
WHERE wo_type = 'CORRECTIVE'
  AND reported_at >= DATE_TRUNC('month', (SELECT MAX(reported_at) FROM {work_orders} WHERE wo_type = 'CORRECTIVE'))
GROUP BY COALESCE(failure_mode_code, 'UNCLASSIFIED') ORDER BY downtime_min DESC"""),
    dict(name="mttr_by_technician",
         question="What is the MTTR by technician?",
         keywords=["!mttr", "!mean time to repair", "repair time", "technician"],
         sql="""SELECT t.full_name AS technician, COUNT(*) AS corrective_jobs,
       ROUND(AVG(DATEDIFF('minute', w.reported_at, w.closed_at)) / 60.0, 2) AS mttr_hours
FROM {work_orders} w JOIN {technicians} t ON t.technician_id = w.technician_id
WHERE w.wo_type = 'CORRECTIVE' AND w.closed_at IS NOT NULL
GROUP BY t.full_name ORDER BY mttr_hours"""),
    dict(name="parts_at_risk_of_stockout",
         question="Which spare parts are at risk of stockout?",
         keywords=["!stockout", "!stock", "!reorder", "parts", "spare", "inventory"],
         sql="""SELECT part_id, description, stock_qty, reorder_point, lead_time_days
FROM {spare_parts}
WHERE stock_qty <= reorder_point
ORDER BY stock_qty - reorder_point, lead_time_days DESC"""),
    dict(name="lowest_oee_assets_last_week",
         question="Which assets had the lowest OEE last week?",
         keywords=["!lowest", "!worst", "oee", "asset", "machine"],
         sql="""SELECT asset_id, line_id, ROUND(AVG(oee), 4) AS avg_oee, SUM(downtime_min) AS downtime_min
FROM {oee_daily}
WHERE oee_date > DATEADD('day', -7, (SELECT MAX(oee_date) FROM {oee_daily}))
GROUP BY asset_id, line_id ORDER BY avg_oee LIMIT 5"""),
    dict(name="downtime_by_asset",
         question="How much breakdown downtime did each asset have?",
         keywords=["!breakdown downtime", "!downtime by asset", "downtime", "each asset"],
         sql="""SELECT asset_id, COUNT(*) AS breakdowns, SUM(downtime_min) AS downtime_min
FROM {work_orders}
WHERE wo_type = 'CORRECTIVE'
GROUP BY asset_id ORDER BY downtime_min DESC"""),
    dict(name="breakdowns_by_asset_and_failure_mode",
         question="How many times has each asset failed, and why?",
         keywords=["!how many times", "!failed", "failures", "breakdowns", "why"],
         sql="""SELECT asset_id, COALESCE(failure_mode_code, 'UNCLASSIFIED') AS failure_mode, COUNT(*) AS breakdowns,
       SUM(downtime_min) AS downtime_min
FROM {work_orders}
WHERE wo_type = 'CORRECTIVE'
GROUP BY asset_id, COALESCE(failure_mode_code, 'UNCLASSIFIED') ORDER BY asset_id, breakdowns DESC"""),
    dict(name="weekly_plant_oee_trend",
         question="What is the weekly OEE trend for the plant?",
         keywords=["!trend", "weekly", "plant", "oee"],
         sql="""SELECT DATE_TRUNC('week', oee_date) AS week_start, ROUND(AVG(oee), 4) AS avg_oee
FROM {line_oee}
GROUP BY DATE_TRUNC('week', oee_date) ORDER BY week_start"""),
    dict(name="jobs_done_by_retiring_technicians",
         question="Which breakdown repairs were done by technicians retiring in 2027?",
         keywords=["!retiring", "!retire", "2027", "repairs"],
         sql="""SELECT t.full_name AS technician, w.asset_id, COUNT(*) AS corrective_jobs
FROM {work_orders} w JOIN {technicians} t ON t.technician_id = w.technician_id
WHERE w.wo_type = 'CORRECTIVE' AND t.retiring_2027
GROUP BY t.full_name, w.asset_id ORDER BY corrective_jobs DESC"""),
    dict(name="scrap_by_asset_last_week",
         question="Which assets produced the most scrap last week?",
         keywords=["!scrap", "!reject", "!defect", "quality"],
         sql="""SELECT asset_id, SUM(scrap_count) AS scrap_count, ROUND(AVG(quality), 4) AS avg_quality
FROM {oee_daily}
WHERE oee_date > DATEADD('day', -7, (SELECT MAX(oee_date) FROM {oee_daily}))
GROUP BY asset_id ORDER BY scrap_count DESC"""),
]


def render(vq: dict, logical: bool = False) -> str:
    return vq["sql"].format(**(LOGICAL if logical else PHYSICAL))
