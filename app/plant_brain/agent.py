"""Ask the Plant: a small, deterministic orchestrator over three tools.

  1. guard   : boundary questions are refused ("I can't establish that from the available data.")
  2. analyst : analytics questions -> a verified query from the semantic view (exact SQL, cited)
  3. search  : maintenance questions -> Cortex Search over knowledge cards (cited by card id)
  4. draft   : "draft a work order for P3" -> DRAFT_WORK_ORDER on the active anomaly (needs human approval)

In Snowflake mode the answer text is written by AI_COMPLETE, grounded only in the retrieved cards;
in mock mode a template writes it. The same tools back the Cortex Agent in 09_agent.sql.
"""
from __future__ import annotations

import re

CANT = "I can't establish that from the available data."
ASSET_RE = re.compile(r"\b(CNC[1-4]|P[1-3]|AC[12]|CV[1-3])\b", re.I)
LINE_RE = re.compile(r"\b(?:line\s*|L)([1-3])\b", re.I)

BOUNDARY_PATTERNS = [
    r"\b(quit|resign|fire|fired|salary|salaries|pay|personal|phone number|address|religion|caste|health of)\b",
    r"\b(next (quarter|year|month)|forecast|predict)\b.*\b(oee|revenue|profit|sales)\b",
    r"\b(oee|revenue|profit|sales)\b.*\b(next (quarter|year|month)|in 20[3-9]\d)\b",
    r"\b(revenue|profit|share price|stock price|competitor|customer name)\b",
    r"\b(approve|approval)\b.*\b(yourself|for me|automatically)\b",
    r"\bwho is (the )?(best|worst|laziest)\b",
]
GOTCHA_HINT = re.compile(r"\b(not do|avoid|don't|dont|mistake|gotcha|warning|didn't work|did not work|careful)\b", re.I)
DRAFT_HINT = re.compile(r"\b(draft|create|raise|open)\b.*\bwork order\b", re.I)
ANALYTIC_HINT = re.compile(r"\b(oee|mttr|downtime|stock|stockout|parts?|scrap|quality|availability|trend|"
                           r"how many|retiring|breakdowns?)\b", re.I)


def ask(brain, question: str) -> dict:
    q = question.strip()
    if not q:
        return dict(answer=CANT, citations=[], tool="none", refused=True)
    if any(re.search(p, q, re.I) for p in BOUNDARY_PATTERNS):
        return dict(answer=CANT + " Plant Brain only answers from maintenance, sensor and production data, "
                    "and never makes judgements about people or approves work orders.",
                    citations=[], tool="guard", refused=True)

    asset = (ASSET_RE.search(q).group(1).upper() if ASSET_RE.search(q) else None)

    if DRAFT_HINT.search(q):
        active = [a for a in brain.active_anomalies() if asset is None or a["asset_id"] == asset]
        if not active:
            return dict(answer=CANT + " There is no active anomaly to draft a work order for.", citations=[],
                        tool="draft", refused=True)
        d = brain.draft_work_order(active[0]["anomaly_id"], created_by="ask-the-plant")
        cites = [c for c in (d["cited_card_ids"] or "").split(",") if c]
        return dict(answer=f"Drafted **{d['draft_id']}** ({d['title']}). It is PENDING_APPROVAL: a human must "
                    f"approve it on the Work Order Approval page.\n\n{d['body']}", citations=cites, tool="draft",
                    refused=False, draft_id=d["draft_id"])

    vq, _ = brain.route_question(q)
    if vq and ANALYTIC_HINT.search(q):
        rows = brain.run_verified(vq)
        m = LINE_RE.search(q)
        if m and rows and "line_id" in rows[0]:
            rows = [r for r in rows if r["line_id"] == f"L{m.group(1)}"] or rows
        if asset and rows and "asset_id" in rows[0]:
            rows = [r for r in rows if r["asset_id"] == asset] or rows
        if not rows:
            return dict(answer=CANT, citations=[f"verified query: {vq['name']}"], tool="analyst", refused=True)
        return dict(answer=_table_answer(vq, rows), citations=[f"verified query: {vq['name']}"], tool="analyst",
                    refused=False, rows=rows, sql=vq["sql"])

    filters = {"@eq": {"asset_id": asset}} if asset else None
    hits = brain.services.search(q, filters, limit=10)
    hits = [h for h in hits if not asset or h.get("asset_id") == asset]
    hits = brain.rank_cards(hits, prefer_gotcha=bool(GOTCHA_HINT.search(q)))[:4]
    if not hits:
        return dict(answer=CANT, citations=[], tool="search", refused=True)
    text = None
    if getattr(brain.services, "name", "") == "snowflake":
        text = brain.services.complete(_grounded_prompt(q, hits))
    if not text:
        text = _template_answer(q, hits)
    return dict(answer=text, citations=[h["card_id"] for h in hits], tool="search", refused=False, cards=hits)


def _table_answer(vq, rows) -> str:
    cols = list(rows[0].keys())
    fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)  # noqa: E731
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = "\n".join("| " + " | ".join(fmt(r[c]) for c in cols) + " |" for r in rows[:12])
    return f"**{vq['question']}** (verified query `{vq['name']}`)\n\n{head}{body}"


def _template_answer(q, hits) -> str:
    lines = []
    for h in hits:
        tag = {"FIX": "What fixed it", "GOTCHA": "Warning", "SYMPTOM_PATTERN": "Early sign",
               "CONVENTION": "Standing rule"}.get(h["card_type"], h["card_type"])
        if h["card_type"] == "FIX" and h["outcome"] == "RECURRED":
            tag = "Did NOT hold"
        who = h.get("author_name") or h.get("author_technician_id") or "unknown"
        lines.append(f"- **{tag}** ({h.get('asset_id') or '-'}, {who}): \"{h['source_excerpt']}\"  [{h['card_id']}]")
    stale = [h["card_id"] for h in hits if h.get("is_stale")]
    note = f"\n\n⚠ Possibly stale (asset changed since): {', '.join(stale)}" if stale else ""
    return "From the plant's knowledge cards:\n\n" + "\n".join(lines) + note


def _grounded_prompt(q, hits) -> str:
    ctx = "\n".join(f"[{h['card_id']}] type={h['card_type']} outcome={h['outcome']} asset={h.get('asset_id')} "
                    f"author={h.get('author_name')} excerpt=\"{h['source_excerpt']}\"" for h in hits)
    return ("You are Plant Brain, a maintenance assistant for a fictional factory. Answer the question using ONLY "
            "the knowledge cards below. Cite card ids in square brackets after each claim. If the cards do not "
            f"answer the question, reply exactly: {CANT}\nCards:\n{ctx}\nQuestion: {q}\nAnswer in at most 5 short "
            "bullet points.")
