"""End-to-end smoke test of the demo flow on the local mock (no Snowflake needed).

    python scripts/smoke_test.py

Builds the mock warehouse, then: active anomalies -> recall -> draft -> agent approval blocked ->
human approval -> close job -> new card + edges -> Ask the Plant (recall / analytics / refusal) -> reset.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
from mocks import warehouse  # noqa: E402
from mocks.services import MockServices  # noqa: E402
from plant_brain import agent  # noqa: E402
from plant_brain.core import PlantBrain  # noqa: E402
from plant_brain.db import DuckDB  # noqa: E402


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        sys.exit(1)


warehouse.build(verbose=False)
db = DuckDB(warehouse.connect())
b = PlantBrain(db, MockServices(db))

act = b.active_anomalies()
check([a["asset_id"] for a in act][0] == "P3" and act[0]["priority"] == "CRITICAL", "P3 is the top, CRITICAL anomaly")
pid = act[0]["anomaly_id"]
r = b.recall(pid)
check(any(c["source_id"] == "HN-0163" for c in r["top"]), "Ravi's handover note is in the top-3 recall")
check(any(c["source_id"] == "WO-2026-0067" for c in r["gotchas"]), "bearing-only fix surfaces as a gotcha")
d = b.draft_work_order(pid)
check(d["status"] == "PENDING_APPROVAL" and "CARD-HN-0163-2" in d["cited_card_ids"], "draft cites Ravi's fix, pending approval")
check("BRG-6312" in d["parts_at_risk"] and d["recommended_technician_id"] == "T01", "draft flags bearing stock risk, suggests Ravi")
try:
    b.approve_work_order(d["draft_id"], "Plant Brain agent")
    check(False, "agent approval must be refused")
except PermissionError:
    check(True, "agent cannot approve")
a = b.approve_work_order(d["draft_id"], "Anjali")
check(a["status"] == "APPROVED" and a["wo_id"] == "WO-2026-0145", "human approval opens WO-2026-0145")
res = b.close_job(a["wo_id"], "P3 DE brg 6312 replaced + HT-3 grease, old grease flushed. vib normal after trial run.", "T07")
check(len(res["new_cards"]) >= 1 and res["new_cards"][0]["card_type"] == "FIX", "closing note became a FIX card (learning loop)")
check(any(e["relation"] == "SUPERSEDES" for e in res["edges"]), "new card supersedes the bearing-only fix")
check(any(c["card_id"].startswith("CARD-WO-2026-0145") for c in b.services.search("P3 bearing HT-3 grease", None, 10)),
      "new card is searchable")
check(agent.ask(b, "What should I NOT do when fixing the P3 bearing?")["citations"], "Ask the Plant cites cards")
check(agent.ask(b, "Which spare parts are at risk of stockout?")["tool"] == "analyst", "analytics routed to a verified query")
check(agent.ask(b, "Which technician is most likely to quit this year?")["refused"], "boundary question refused")
print(" ", b.reset_demo())
check(not b.drafts() and not b.open_work_orders(), "reset leaves no drafts or open work orders")
print("\nSMOKE TEST PASSED")
