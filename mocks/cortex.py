"""Mock Cortex AI_COMPLETE for card extraction: deterministic rules, no LLM.

Follows the same rules as .cortex/skills/card-extractor/SKILL.md and the prompt in
snowflake/04_cards.sql, and writes the same rows to BRAIN.CARDS_RAW / BRAIN.CARD_EXTRACT_LOG.
It is intentionally simple: it shows the pipeline end to end offline. Real extraction quality
comes from Cortex in Snowflake mode.
"""
from __future__ import annotations

import re
from datetime import datetime

MODEL_NAME = "mock-rules"

ASSET_RE = re.compile(r"\b(CNC[1-4]|P[1-3]|AC[12]|CV[1-3])\b", re.I)

FM_KEYWORDS = [  # order matters: first hit wins
    ("MOTOR_OVERHEAT", ["motor trip", "overload", "motor hot", "motor tripping"]),
    ("BEARING_WEAR", ["bearing", "brg", "grease", "lube"]),
    ("SEAL_LEAK", ["seal", "leak"]),
    ("BELT_SLIP", ["belt", "slipping", "jerking"]),
    ("VALVE_STICKING", ["valve"]),
    ("COOLANT_BLOCKAGE", ["coolant"]),
    ("SPINDLE_MISALIGNMENT", ["spindle vib", "misalign", "realign", "chatter"]),
    ("AIR_FILTER_CLOG", ["air filter", "intake filter", "filter choked", "low discharge", "discharge pressure low"]),
    ("TOOL_WEAR", ["tool", "insert", "holder", "finish"]),
    ("OIL_CONTAMINATION", ["milky", "contaminat", "oil temp"]),
]
CONVENTION_CUES = ["mandatory", "ref return", "keep min", "always "]
GOTCHA_CUES = ["not hold", "dont ", "don't", "do not", "otherwise", "warna", "fails in", "never ",
               "sirf", "only bearing", "wapas aaya", " mat "]
SYMPTOM_CUES = ["when ", "creeping", "starts rising", "root cause looks like", "then temp"]
FIX_CUES = ["fix =", "fix=", "replace", "repl", "changed", "chngd", "change kiya", "badla", "done", "fitted", "aligned", "align kiya"]
RECUR_CUES = ["came back", "wapas", "phir se", "recur", "again"]


def failure_mode_of(text: str) -> str | None:
    t = text.lower()
    for fm, kws in FM_KEYWORDS:
        if any(k in t for k in kws):
            return fm
    return None


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _card(card_type, asset, fm, sentence, outcome, confidence, parts=None, symptom=None):
    return dict(card_type=card_type, asset_id=asset, failure_mode=fm,
                symptom_summary=(symptom or sentence)[:300], action_taken=sentence[:300],
                parts=parts, outcome=outcome, source_excerpt=sentence[:220], confidence=confidence)


def extract_cards(source: dict) -> list[dict]:
    """source: one BRAIN.CARD_SOURCES row as a dict. Returns card dicts (no ids)."""
    text = source["source_text"] or ""
    cards: list[dict] = []
    if source["source_type"] == "WORK_ORDER":
        if source.get("source_subtype") == "CORRECTIVE":
            fm = source.get("failure_mode_code") or failure_mode_of(text)
            first = re.split(r"[.,;]", text, maxsplit=1)[0]
            cards.append(_card("FIX", source.get("asset_id"), fm, text, "RESOLVED", 0.9,
                               parts=source.get("parts_used"), symptom=first))
        for s in sentences(text):
            low = s.lower()
            if any(c in low for c in GOTCHA_CUES):
                cards.append(_card("GOTCHA", source.get("asset_id"), source.get("failure_mode_code") or failure_mode_of(s),
                                   s, "RECURRED" if any(c in low for c in RECUR_CUES) else "UNKNOWN", 0.85))
        return cards

    asset_ctx = None
    for s in sentences(text):
        low = s.lower()
        m = ASSET_RE.search(s)
        if m:
            asset_ctx = m.group(1).upper()
        fm = failure_mode_of(s)
        if asset_ctx is None:
            continue
        if any(c in low for c in CONVENTION_CUES):
            cards.append(_card("CONVENTION", asset_ctx, fm, s, "UNKNOWN", 0.8))
        elif any(c in low for c in GOTCHA_CUES):
            cards.append(_card("GOTCHA", asset_ctx, fm, s, "RECURRED" if any(c in low for c in RECUR_CUES) else "UNKNOWN", 0.85))
        elif any(c in low for c in SYMPTOM_CUES) and fm:
            cards.append(_card("SYMPTOM_PATTERN", asset_ctx, fm, s, "UNKNOWN", 0.8))
        elif any(c in low for c in FIX_CUES) and fm:
            explicit = "fix =" in low or "fix=" in low
            cards.append(_card("FIX", asset_ctx, fm, s, "RESOLVED" if explicit else "UNKNOWN", 0.95 if explicit else 0.5))
    return cards


def run_extraction(con, source_ids: list[str] | None = None) -> int:
    """Mock of CALL BRAIN.EXTRACT_NEW_CARDS(): extract only sources not yet in the log."""
    sql = """
        SELECT s.*, w.parts_used
        FROM brain.card_sources s
        LEFT JOIN brain.card_extract_log l
          ON l.source_type = s.source_type AND l.source_id = s.source_id AND l.text_hash = s.text_hash
        LEFT JOIN raw.work_orders w ON s.source_type = 'WORK_ORDER' AND w.wo_id = s.source_id
        WHERE l.source_id IS NULL
        ORDER BY s.source_ts, s.source_id"""
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    todo = [dict(zip(cols, r)) for r in cur.fetchall()]
    if source_ids is not None:
        todo = [t for t in todo if t["source_id"] in source_ids]
    now = datetime(2026, 9, 1, 0, 0, 0)  # fixed "extraction time" keeps the mock deterministic
    for src in todo:
        cards = extract_cards(src)
        for i, c in enumerate(cards, start=1):
            con.execute("""INSERT INTO brain.cards_raw VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [src["source_type"], src["source_id"], src["text_hash"], i, c["card_type"], c["asset_id"],
                         c["failure_mode"], c["symptom_summary"], c["action_taken"], c["parts"], c["outcome"],
                         c["source_excerpt"], c["confidence"], MODEL_NAME, now])
        con.execute("INSERT INTO brain.card_extract_log VALUES (?,?,?,?,?,?)",
                    [src["source_type"], src["source_id"], src["text_hash"], len(cards), MODEL_NAME, now])
    return len(todo)


def complete(prompt: str) -> str:
    """Mock AI_COMPLETE for free text: the app's agent uses its own templated answer in mock mode."""
    return "[mock-complete] " + prompt[:200]
