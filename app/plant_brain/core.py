"""PlantBrain: every read and action the app, the procedures and the eval need.

Backend-agnostic: `db` is a plant_brain.db adapter (Snowflake or DuckDB) and `services`
provides the three Cortex-backed capabilities (search, complete, extract_new_cards), either
real (plant_brain.services.SnowflakeServices) or mocked (mocks.services.MockServices).
"""
from __future__ import annotations

import re
from datetime import timedelta

from . import drafting
from .verified_queries import VERIFIED_QUERIES, render

DB_ = "PLANT_BRAIN"
TYPE_WEIGHT = {"FIX": 3.0, "GOTCHA": 2.6, "SYMPTOM_PATTERN": 2.0, "CONVENTION": 1.0}
APP_WO_PREFIX = "WO-2026-"


class PlantBrain:
    def __init__(self, db, services):
        self.db, self.services = db, services

    # ------------------------------------------------------------------ reads: OEE + health
    def oee_line_daily(self, days: int = 30) -> list[dict]:
        return self.db.query(f"""SELECT line_id, oee_date, availability, performance, quality, oee
            FROM {DB_}.CORE.OEE_LINE_DAILY
            WHERE oee_date > DATEADD('day', ?, (SELECT MAX(oee_date) FROM {DB_}.CORE.OEE_LINE_DAILY))
            ORDER BY oee_date, line_id""", [-days])

    def oee_asset_summary(self, days: int = 7) -> list[dict]:
        return self.db.query(f"""SELECT asset_id, line_id, AVG(availability) AS availability, AVG(performance) AS performance,
                   AVG(quality) AS quality, AVG(oee) AS oee, SUM(downtime_min) AS downtime_min
            FROM {DB_}.CORE.OEE_DAILY
            WHERE oee_date > DATEADD('day', ?, (SELECT MAX(oee_date) FROM {DB_}.CORE.OEE_DAILY))
            GROUP BY asset_id, line_id ORDER BY line_id, asset_id""", [-days])

    def asset_health(self) -> list[dict]:
        return self.db.query(f"""SELECT asset_id, asset_name, asset_type, line_id, latest_ts, vib_6h_pct, temp_6h_delta_c,
                   pres_6h_pct, curr_6h_pct, health_status
            FROM {DB_}.CORE.ASSET_HEALTH ORDER BY line_id, asset_id""")

    # ------------------------------------------------------------------ anomalies
    def active_anomalies(self) -> list[dict]:
        """Active anomalies. Priority is CRITICAL when the pattern matches past failures on this asset and
        the estimated failure window opens within 48 h; otherwise the signal severity."""
        return self.db.query(f"""SELECT a.*, f.failure_mode AS matched_failure_mode, f.n_matches, f.eta_low_h, f.eta_high_h,
                   CASE WHEN f.eta_low_h IS NOT NULL AND f.eta_low_h <= 48 THEN 'CRITICAL' ELSE a.severity END AS priority
            FROM {DB_}.BRAIN.ANOMALIES a
            LEFT JOIN {DB_}.BRAIN.FAILURE_WINDOWS f ON f.anomaly_id = a.anomaly_id
            WHERE a.is_active
            ORDER BY CASE WHEN f.eta_low_h IS NOT NULL AND f.eta_low_h <= 48 THEN 0
                          WHEN a.severity = 'HIGH' THEN 1 WHEN a.severity = 'MEDIUM' THEN 2 ELSE 3 END,
                     a.asset_id""")

    def anomaly(self, anomaly_id: str) -> dict | None:
        rows = self.db.query(f"SELECT * FROM {DB_}.BRAIN.ANOMALIES WHERE anomaly_id = ?", [anomaly_id])
        return rows[0] if rows else None

    def matches(self, anomaly_id: str) -> list[dict]:
        return self.db.query(f"""SELECT m.*, w.reported_at, w.closed_at, w.resolution_note, t.full_name AS technician
            FROM {DB_}.BRAIN.ANOMALY_MATCHES m
            JOIN {DB_}.RAW.WORK_ORDERS w ON w.wo_id = m.wo_id
            LEFT JOIN {DB_}.RAW.TECHNICIANS t ON t.technician_id = m.technician_id
            WHERE m.anomaly_id = ? ORDER BY m.score DESC""", [anomaly_id])

    def failure_window(self, anomaly_id: str) -> dict | None:
        rows = self.db.query(f"SELECT * FROM {DB_}.BRAIN.FAILURE_WINDOWS WHERE anomaly_id = ?", [anomaly_id])
        return rows[0] if rows else None

    def sensor_trace(self, anomaly_id: str, before_h: int = 12, after_h: int = 48) -> list[dict]:
        """Live anomaly + matched past episodes, aligned on hours since anomaly start."""
        a = self.anomaly(anomaly_id)
        if not a:
            return []
        series = [(f"LIVE {a['start_hr']:%d %b}", a["start_hr"], a["end_hr"])]
        for m in self.matches(anomaly_id):
            if m["is_match"]:
                h = self.db.query(f"SELECT start_hr FROM {DB_}.BRAIN.ANOMALIES WHERE anomaly_id = ?", [m["hist_id"]])
                if h:
                    s = h[0]["start_hr"]
                    stop = min(after_h, int(m["hours_start_to_failure"] or after_h))   # stop when it failed
                    series.append((f"{m['wo_id']} ({s:%d %b})", s, s + timedelta(hours=stop)))
        out = []
        for label, start, end in series:
            for r in self.db.query(f"""SELECT hr, vib_resid_pct, temp_resid_c FROM {DB_}.BRAIN.SENSOR_SCORES
                    WHERE asset_id = ? AND hr >= ? AND hr <= ? ORDER BY hr""",
                                   [a["asset_id"], start - timedelta(hours=before_h), end]):
                out.append(dict(series=label, hours_since_start=(r["hr"] - start).total_seconds() / 3600,
                                vib_resid_pct=r["vib_resid_pct"], temp_resid_c=r["temp_resid_c"],
                                live=label.startswith("LIVE")))
        return out

    # ------------------------------------------------------------------ cards
    def cards(self, where: str = "1=1", params=None) -> list[dict]:
        return self.db.query(f"SELECT * FROM {DB_}.BRAIN.CARDS WHERE {where} ORDER BY created_at, card_id", params)

    def rank_cards(self, cards: list[dict], failure_mode: str | None = None, prefer_gotcha: bool = False) -> list[dict]:
        """Graph-aware ranking shared by recall and Ask the Plant: card type x confidence, failure-mode
        match, search rank; recurred fixes and stale cards are demoted unless warnings are wanted."""
        rank = {c["card_id"]: i for i, c in enumerate(cards)}

        def score(c):
            warn = c["card_type"] == "GOTCHA" or (c["card_type"] == "FIX" and c["outcome"] == "RECURRED")
            s = TYPE_WEIGHT.get(c["card_type"], 1.0) * (c.get("confidence") or 0.5)
            if c["card_type"] == "FIX" and c["outcome"] == "RECURRED":
                s *= 0.6
            if c.get("is_stale"):          # still shown (flagged), just demoted
                s *= 0.5
            if prefer_gotcha and warn:
                s += 3.0
            if failure_mode and c.get("failure_mode") == failure_mode:
                s += 1.0
            s += 1.0 / (1 + rank.get(c["card_id"], 50))
            return s

        return sorted({c["card_id"]: c for c in cards}.values(), key=lambda c: (-score(c), c["card_id"]))

    def card(self, card_id: str) -> dict | None:
        rows = self.cards("card_id = ?", [card_id])
        return rows[0] if rows else None

    def recall(self, anomaly_id: str, k: int = 3) -> dict:
        """Brain recall for an anomaly: Cortex Search (asset filter) + graph neighbours, ranked."""
        a = self.anomaly(anomaly_id)
        w = self.failure_window(anomaly_id)
        fm = (w or {}).get("failure_mode")
        query = f"{a['asset_id']} {a['sensors']} rising {(fm or '').replace('_', ' ').lower()} fix what worked"
        hits = self.services.search(query, {"@eq": {"asset_id": a["asset_id"]}}, limit=15)
        neighbours = self.cards("asset_id = ? AND failure_mode = ?", [a["asset_id"], fm]) if fm else []
        ranked = self.rank_cards(hits + neighbours, fm)
        return dict(anomaly=a, window=w, failure_mode=fm, top=ranked[:k], all=ranked,
                    fixes=[c for c in ranked if c["card_type"] == "FIX" and c["outcome"] == "RESOLVED"],
                    gotchas=[c for c in ranked if c["card_type"] == "GOTCHA"
                             or (c["card_type"] == "FIX" and c["outcome"] == "RECURRED")],
                    symptoms=[c for c in ranked if c["card_type"] == "SYMPTOM_PATTERN"])

    def edges_for(self, card_id: str) -> list[dict]:
        return self.db.query(f"SELECT * FROM {DB_}.BRAIN.EDGES WHERE from_id = ? OR to_id = ?", [card_id, card_id])

    # ------------------------------------------------------------------ work-order workflow
    def demo_now(self):
        """'Now' for the demo = one hour after the last sensor reading (data ends 2026-08-31 23:55)."""
        return self.db.scalar(f"SELECT MAX(hr) FROM {DB_}.BRAIN.SENSOR_HOURLY") + timedelta(hours=1)

    def draft_work_order(self, anomaly_id: str, created_by: str = "plant-brain") -> dict:
        r = self.recall(anomaly_id, k=10)
        a, w = r["anomaly"], r["window"]
        stock = {p["part_id"]: p for p in self.db.query(f"SELECT * FROM {DB_}.RAW.SPARE_PARTS")}
        techs = {t["technician_id"]: t for t in self.db.query(f"SELECT * FROM {DB_}.RAW.TECHNICIANS")}
        d = drafting.draft(a, w, r["all"], stock, techs)
        n = self.db.scalar(f"SELECT COUNT(*) FROM {DB_}.APP.WORK_ORDER_DRAFTS WHERE anomaly_id = ?", [anomaly_id]) or 0
        d["draft_id"] = f"DRAFT-{anomaly_id}-{int(n) + 1}"
        self.db.execute(f"""INSERT INTO {DB_}.APP.WORK_ORDER_DRAFTS
            (draft_id, anomaly_id, asset_id, failure_mode, status, title, body, recommended_technician_id, parts,
             parts_at_risk, eta_low_h, eta_high_h, cited_card_ids, created_at, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [d["draft_id"], anomaly_id, d["asset_id"], d["failure_mode"], d["status"], d["title"], d["body"],
                         d["recommended_technician_id"], d["parts"], d["parts_at_risk"], d["eta_low_h"], d["eta_high_h"],
                         d["cited_card_ids"], self.demo_now(), created_by])
        return self.draft(d["draft_id"])

    def drafts(self, status: str | None = None) -> list[dict]:
        if status:
            return self.db.query(f"SELECT * FROM {DB_}.APP.WORK_ORDER_DRAFTS WHERE status = ? ORDER BY created_at DESC, draft_id DESC", [status])
        return self.db.query(f"SELECT * FROM {DB_}.APP.WORK_ORDER_DRAFTS ORDER BY created_at DESC, draft_id DESC")

    def draft(self, draft_id: str) -> dict | None:
        rows = self.db.query(f"SELECT * FROM {DB_}.APP.WORK_ORDER_DRAFTS WHERE draft_id = ?", [draft_id])
        return rows[0] if rows else None

    def edit_draft(self, draft_id: str, body: str, editor: str) -> dict:
        self._require_human(editor)
        self.db.execute(f"""UPDATE {DB_}.APP.WORK_ORDER_DRAFTS SET body = ?, edited_by = ?
            WHERE draft_id = ? AND status = 'PENDING_APPROVAL'""", [body, editor, draft_id])
        return self.draft(draft_id)

    def reject_draft(self, draft_id: str, approver: str, reason: str) -> dict:
        self._require_human(approver)
        self.db.execute(f"""UPDATE {DB_}.APP.WORK_ORDER_DRAFTS SET status = 'REJECTED', approved_by = ?, approved_at = ?,
            rejected_reason = ? WHERE draft_id = ? AND status = 'PENDING_APPROVAL'""",
                        [approver, self.demo_now(), reason, draft_id])
        return self.draft(draft_id)

    @staticmethod
    def _require_human(who: str):
        if not who or not who.strip():
            raise ValueError("A named human approver is required.")
        if re.search(r"agent|plant[- ]?brain|cortex|bot|system", who, re.I):
            raise PermissionError("Work orders can only be approved by a human, not by the agent.")

    def approve_work_order(self, draft_id: str, approver: str) -> dict:
        """Human approval: creates an OPEN work order in RAW.WORK_ORDERS."""
        self._require_human(approver)
        d = self.draft(draft_id)
        if not d or d["status"] != "PENDING_APPROVAL":
            raise ValueError(f"{draft_id} is not pending approval")
        last = self.db.scalar(f"SELECT MAX(wo_id) FROM {DB_}.RAW.WORK_ORDERS")
        wo_id = f"{APP_WO_PREFIX}{int(last.rsplit('-', 1)[1]) + 1:04d}"
        now = self.demo_now()
        self.db.execute(f"""INSERT INTO {DB_}.RAW.WORK_ORDERS
            (wo_id, asset_id, wo_type, priority, failure_mode_code, reported_at, started_at, closed_at, downtime_min,
             technician_id, parts_used, resolution_note, status)
            VALUES (?, ?, 'CORRECTIVE', 'HIGH', ?, ?, ?, NULL, NULL, ?, ?, NULL, 'OPEN')""",
                        [wo_id, d["asset_id"], d["failure_mode"], now, now, d["recommended_technician_id"],
                         ";".join(f"{p}:1" for p in (d["parts"] or "").split(";") if p)])
        self.db.execute(f"""UPDATE {DB_}.APP.WORK_ORDER_DRAFTS SET status = 'APPROVED', approved_by = ?, approved_at = ?, wo_id = ?
            WHERE draft_id = ?""", [approver, now, wo_id, draft_id])
        return self.draft(draft_id)

    def open_work_orders(self) -> list[dict]:
        return self.db.query(f"""SELECT w.*, d.draft_id, d.title FROM {DB_}.RAW.WORK_ORDERS w
            LEFT JOIN {DB_}.APP.WORK_ORDER_DRAFTS d ON d.wo_id = w.wo_id
            WHERE w.status = 'OPEN' ORDER BY w.wo_id DESC""")

    def close_job(self, wo_id: str, closing_note: str, technician_id: str | None = None, repair_h: float = 5.0) -> dict:
        """Close the job and run the card pipeline on the new note: the learning loop."""
        wo = self.db.query(f"SELECT * FROM {DB_}.RAW.WORK_ORDERS WHERE wo_id = ?", [wo_id])
        if not wo or wo[0]["status"] != "OPEN":
            raise ValueError(f"{wo_id} is not an open work order")
        closed = wo[0]["reported_at"] + timedelta(hours=repair_h)
        self.db.execute(f"""UPDATE {DB_}.RAW.WORK_ORDERS SET status = 'CLOSED', closed_at = ?, downtime_min = ?,
            resolution_note = ?, technician_id = COALESCE(?, technician_id) WHERE wo_id = ?""",
                        [closed, int(repair_h * 60), closing_note, technician_id, wo_id])
        n = self.services.extract_new_cards()
        new_cards = self.cards("source_id = ?", [wo_id])
        return dict(wo_id=wo_id, sources_extracted=n, new_cards=new_cards,
                    edges=[e for c in new_cards for e in self.edges_for(c["card_id"])])

    def reset_demo(self) -> str:
        """Remove drafts, app-created work orders and their cards. Historical data is untouched."""
        app_wos = [r["wo_id"] for r in self.db.query(f"SELECT wo_id FROM {DB_}.APP.WORK_ORDER_DRAFTS WHERE wo_id IS NOT NULL")]
        for wo in app_wos:
            self.db.execute(f"DELETE FROM {DB_}.BRAIN.CARDS_RAW WHERE source_id = ?", [wo])
            self.db.execute(f"DELETE FROM {DB_}.BRAIN.CARD_EXTRACT_LOG WHERE source_id = ?", [wo])
            self.db.execute(f"DELETE FROM {DB_}.RAW.WORK_ORDERS WHERE wo_id = ?", [wo])
        self.db.execute(f"DELETE FROM {DB_}.APP.WORK_ORDER_DRAFTS")
        # demo handover notes added through the card-extractor skill (ids HN-9xxx)
        n_notes = self.db.scalar(f"SELECT COUNT(*) FROM {DB_}.RAW.HANDOVER_NOTES WHERE note_id LIKE 'HN-9%'") or 0
        for t in ("BRAIN.CARDS_RAW", "BRAIN.CARD_EXTRACT_LOG"):
            self.db.execute(f"DELETE FROM {DB_}.{t} WHERE source_id LIKE 'HN-9%'")
        self.db.execute(f"DELETE FROM {DB_}.RAW.HANDOVER_NOTES WHERE note_id LIKE 'HN-9%'")
        return (f"reset: removed {len(app_wos)} demo work order(s), {int(n_notes)} demo note(s) and all drafts")

    # ------------------------------------------------------------------ analytics
    def route_question(self, question: str) -> tuple[dict | None, float]:
        """Deterministic router: weighted keyword hits ("!kw" = 2, "kw" = 1); needs >= 2 to route."""
        q = question.lower()
        best, best_s = None, 0.0
        for vq in VERIFIED_QUERIES:
            s = sum(2.0 if k.startswith("!") else 1.0 for k in vq["keywords"] if k.lstrip("!") in q)
            if s > best_s:
                best, best_s = vq, s
        return (best, best_s) if best_s >= 2 else (None, best_s)

    def run_verified(self, vq: dict) -> list[dict]:
        return self.db.query(render(vq))
