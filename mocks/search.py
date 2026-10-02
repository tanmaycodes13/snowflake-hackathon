"""Mock Cortex Search: BM25 over BRAIN.CARDS.search_text, with the same request/response shape as
SNOWFLAKE.CORTEX.SEARCH_PREVIEW ({"query", "columns", "filter", "limit"} -> {"results": [...]}).
Cortex Search is hybrid (vector + keyword); this mock is keyword-only plus a small synonym map
for shop-floor abbreviations, which is enough to exercise the app and the eval offline."""
from __future__ import annotations

import math
import re

SYNONYMS = {"brg": "bearing", "bearings": "bearing", "vib": "vibration", "temp": "temperature",
            "chngd": "changed", "repl": "replaced", "lube": "grease", "greased": "grease", "ht3": "ht-3",
            "prodn": "production", "pls": "please", "wapas": "again", "phir": "again"}
STOP = set("the a an and or of to in on for is it was with by at as be this that what how why which who "
           "did do does from p3 cnc1 cnc2 cnc3 cnc4 p1 p2 ac1 ac2 cv1 cv2 cv3".split())


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9][a-z0-9\-]*", (text or "").lower()):
        t = SYNONYMS.get(t, t)
        for suf in ("ing", "ed", "es", "s"):          # crude stemmer: fixed -> fix, bearings -> bearing
            if len(t) > len(suf) + 3 and t.endswith(suf):
                t = t[: -len(suf)]
                break
        if t not in STOP and len(t) > 1:
            out.append(t)
    return out


def _match(filt: dict | None, row: dict) -> bool:
    if not filt:
        return True
    (op, arg), = filt.items()
    if op == "@eq":
        return all(str(row.get(k)) == str(v) for k, v in arg.items())
    if op == "@and":
        return all(_match(f, row) for f in arg)
    if op == "@or":
        return any(_match(f, row) for f in arg)
    if op == "@not":
        return not _match(arg, row)
    raise ValueError(f"unsupported filter {op}")


class MockCortexSearch:
    """Index is rebuilt on each query from the live BRAIN.CARDS view (TARGET_LAG = 0 in the mock)."""

    def __init__(self, db, k1: float = 1.4, b: float = 0.75):
        self.db, self.k1, self.b = db, k1, b

    def search_preview(self, request: dict) -> dict:
        rows = self.db.query("SELECT * FROM PLANT_BRAIN.BRAIN.CARDS")
        rows = [r for r in rows if _match(request.get("filter"), r)]
        docs = [tokens(r["search_text"] + " " + (r.get("failure_mode") or "").replace("_", " ")) for r in rows]
        n = len(docs) or 1
        avgdl = sum(map(len, docs)) / n
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        q = tokens(request.get("query", ""))
        scored = []
        for r, d in zip(rows, docs):
            s = 0.0
            for t in q:
                f = d.count(t)
                if f:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / avgdl))
            if s > 0:
                scored.append((s, r))
        scored.sort(key=lambda x: (-x[0], x[1]["card_id"]))
        cols = request.get("columns")
        res = [({c: r.get(c) for c in cols} if cols else dict(r)) | {"@score": round(s, 4)}
               for s, r in scored[: request.get("limit", 10)]]
        return {"results": res}
