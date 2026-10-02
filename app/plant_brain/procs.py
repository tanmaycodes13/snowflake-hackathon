"""Handlers for the Python stored procedures in snowflake/08_procs.sql.
They run PlantBrain inside Snowflake with the procedure's Snowpark session, so the stored procedures,
the Streamlit app and the local mock all execute the same workflow code."""
from __future__ import annotations

import json

from .core import PlantBrain
from .db import Snowpark
from .services import SnowflakeServices


def _brain(session):
    db = Snowpark(session)
    return PlantBrain(db, SnowflakeServices(db))


def _jsonable(d):
    return json.loads(json.dumps(d, default=str))


def draft_work_order(session, anomaly_id: str):
    return _jsonable(_brain(session).draft_work_order(anomaly_id, created_by="APP.DRAFT_WORK_ORDER"))


def approve_work_order(session, draft_id: str, approver: str):
    return _jsonable(_brain(session).approve_work_order(draft_id, approver))


def reject_work_order(session, draft_id: str, approver: str, reason: str):
    return _jsonable(_brain(session).reject_draft(draft_id, approver, reason))


def close_job(session, wo_id: str, closing_note: str, technician_id: str):
    r = _brain(session).close_job(wo_id, closing_note, technician_id or None)
    return _jsonable({"wo_id": r["wo_id"], "new_card_ids": [c["card_id"] for c in r["new_cards"]],
                      "sources_extracted": r["sources_extracted"]})


def reset_demo(session):
    return _brain(session).reset_demo()
