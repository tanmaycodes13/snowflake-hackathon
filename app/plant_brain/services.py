"""Real Snowflake services: Cortex Search, Cortex AI_COMPLETE, and the Cortex card-extraction proc.
The mock equivalents live in mocks/services.py with the same three methods."""
from __future__ import annotations

import json
import os

SEARCH_SERVICE = "PLANT_BRAIN.BRAIN.CARD_SEARCH"
SEARCH_COLUMNS = ["card_id"]


def _sql_literal(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


class SnowflakeServices:
    name = "snowflake"

    def __init__(self, db, model: str | None = None):
        self.db = db
        self.model = model or os.getenv("PB_MODEL", "claude-haiku-4-5")

    def search(self, query: str, filters: dict | None = None, limit: int = 5) -> list[dict]:
        """Cortex Search via SEARCH_PREVIEW (constant arguments only, so the JSON is inlined),
        then the full card rows from BRAIN.CARDS, in search order."""
        req = {"query": query, "columns": SEARCH_COLUMNS, "limit": limit}
        if filters:
            req["filter"] = filters
        raw = self.db.scalar(f"SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW({_sql_literal(SEARCH_SERVICE)}, "
                             f"{_sql_literal(json.dumps(req))}) AS r")
        ids = [r["card_id"] for r in json.loads(raw).get("results", [])]
        if not ids:
            return []
        rows = self.db.query("SELECT * FROM PLANT_BRAIN.BRAIN.CARDS WHERE card_id IN ("
                             + ",".join("?" * len(ids)) + ")", ids)
        by_id = {r["card_id"]: r for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def complete(self, prompt: str) -> str | None:
        return self.db.scalar("SELECT AI_COMPLETE(?, ?) AS r", [self.model, prompt])

    def extract_new_cards(self) -> int:
        msg = self.db.scalar("CALL PLANT_BRAIN.BRAIN.EXTRACT_NEW_CARDS(?)", [self.model]) or "0"
        return int(str(msg).split()[0]) if str(msg).split()[0].isdigit() else 0
