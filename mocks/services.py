"""MockServices: the three Cortex-backed capabilities PlantBrain needs, offline.
Same interface as app/plant_brain/services.py:SnowflakeServices."""
from __future__ import annotations

from . import cortex
from .search import MockCortexSearch


class MockServices:
    name = "mock"

    def __init__(self, db):
        self.db = db
        self._search = MockCortexSearch(db)

    def search(self, query: str, filters: dict | None = None, limit: int = 5) -> list[dict]:
        res = self._search.search_preview({"query": query, "columns": ["card_id"], "filter": filters, "limit": limit})
        ids = [r["card_id"] for r in res["results"]]
        if not ids:
            return []
        rows = self.db.query("SELECT * FROM PLANT_BRAIN.BRAIN.CARDS WHERE card_id IN (" + ",".join("?" * len(ids)) + ")", ids)
        by_id = {r["card_id"]: r for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def complete(self, prompt: str) -> str | None:
        return None  # the agent falls back to its grounded template answer

    def extract_new_cards(self) -> int:
        return cortex.run_extraction(self.db.con.cursor())
