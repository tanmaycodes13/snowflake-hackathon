"""Plant Brain vs a naive baseline on the 25 golden questions + golden-anomaly retrieval.

    python eval/run_eval.py                 # mock backend (offline, no LLM)
    python eval/run_eval.py --snowflake     # live account: Cortex Search + AI_COMPLETE for both systems
    python eval/run_eval.py --write         # also write docs/EVALUATION.md

Baseline ("naive RAG"): keyword retrieval (BM25) over the RAW work-order notes and handover notes:
no knowledge cards, no graph, no verified queries, no guard. Its answer is the top-3 raw snippets with
their source ids (Snowflake mode: AI_COMPLETE writes the answer from those snippets).
Plant Brain: app/plant_brain/agent.py (guard -> verified queries -> card search -> grounded answer).
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
from mocks.search import tokens  # noqa: E402
from plant_brain import agent  # noqa: E402
from plant_brain.core import PlantBrain  # noqa: E402
from plant_brain.verified_queries import VERIFIED_QUERIES  # noqa: E402

CANT = agent.CANT
VQ = {v["name"]: v for v in VERIFIED_QUERIES}


def make(snowflake: bool) -> PlantBrain:
    if snowflake:
        import os
        os.environ["PB_BACKEND"] = "snowflake"
        from plant_brain.runtime import make_brain
        return make_brain()[0]
    from mocks import warehouse
    from mocks.services import MockServices
    from plant_brain.db import DuckDB
    warehouse.build(verbose=False)          # fresh, deterministic state
    db = DuckDB(warehouse.connect())
    return PlantBrain(db, MockServices(db))


class Baseline:
    """BM25 over raw text chunks (one chunk per note / work order)."""

    def __init__(self, brain):
        self.brain = brain
        self.docs = brain.db.query("""SELECT source_id, source_text FROM PLANT_BRAIN.BRAIN.CARD_SOURCES""")
        self.toks = [tokens(d["source_text"]) for d in self.docs]
        self.avgdl = sum(map(len, self.toks)) / len(self.toks)
        self.df = {}
        for t in self.toks:
            for w in set(t):
                self.df[w] = self.df.get(w, 0) + 1

    def retrieve(self, q: str, k: int = 3) -> list[dict]:
        qt, n, out = tokens(q), len(self.docs), []
        for d, t in zip(self.docs, self.toks):
            s = 0.0
            for w in qt:
                f = t.count(w)
                if f:
                    idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * f * 2.4 / (f + 1.4 * (0.25 + 0.75 * len(t) / self.avgdl))
            if s > 0:
                out.append((s, d))
        out.sort(key=lambda x: (-x[0], x[1]["source_id"]))
        return [d for _, d in out[:k]]

    def ask(self, q: str) -> dict:
        hits = self.retrieve(q)
        if not hits:
            return dict(answer=CANT, citations=[], refused=True)
        ans = None
        if getattr(self.brain.services, "name", "") == "snowflake":
            ctx = "\n".join(f"[{h['source_id']}] {h['source_text']}" for h in hits)
            ans = self.brain.services.complete(f"Answer the question using these notes. Cite note ids.\n{ctx}\nQuestion: {q}")
        if not ans:
            ans = "\n".join(f"[{h['source_id']}] {h['source_text']}" for h in hits)
        return dict(answer=ans, citations=[h["source_id"] for h in hits], refused=CANT in ans)


def fmt(v):
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def score(brain, q: dict, out: dict) -> dict:
    ans = out["answer"] or ""
    refused = out.get("refused", False) or CANT in ans
    if q.get("refuse"):
        correct = refused
    else:
        checks = []
        if q.get("expect_any"):
            checks.append(any(e.lower() in ans.lower() for e in q["expect_any"]))
        if q.get("verified_query"):
            rows = brain.run_verified(VQ[q["verified_query"]])
            first_num = next((fmt(v) for v in rows[0].values() if isinstance(v, (int, float)) and not isinstance(v, bool)), None)
            checks.append(first_num is not None and first_num in ans)
        correct = (not refused) and all(checks)
    return dict(correct=correct, cited=bool(out.get("citations")) and not refused, refused=refused)


def golden_hit_at_3(brain, base) -> tuple[bool, bool, list, list]:
    a = next(x for x in brain.active_anomalies() if x["asset_id"] == "P3")
    top = [c["source_id"] for c in brain.recall(a["anomaly_id"], k=3)["top"]]
    btop = [d["source_id"] for d in base.retrieve(
        f"P3 {a['sensors']} rising bearing fix", 3)]
    return "HN-0163" in top, "HN-0163" in btop, top, btop


def main():
    snow = "--snowflake" in sys.argv
    brain = make(snow)
    base = Baseline(brain)
    qs = yaml.safe_load((ROOT / "eval/golden_questions.yaml").read_text())["questions"]
    rows = []
    for q in qs:
        b_out, p_out = base.ask(q["question"]), agent.ask(brain, q["question"])
        rows.append(dict(q=q, base=score(brain, q, b_out), brain=score(brain, q, p_out), p_out=p_out, b_out=b_out))
    if not snow:
        brain.reset_demo()   # Ask the Plant may have drafted a work order
    hit_p, hit_b, top_p, top_b = golden_hit_at_3(brain, base)

    def pct(sys_, key, cats=None, only=None):
        sel = [r for r in rows if (cats is None or r["q"]["category"] in cats)]
        if only:
            sel = [r for r in sel if only(r)]
        return sum(r[sys_][key] for r in sel), len(sel)

    non_boundary = lambda r: not r["q"].get("refuse")  # noqa: E731
    metrics = [
        ("Retrieval hit@3 on the golden anomaly (HN-0163 in top 3)", (int(hit_b), 1), (int(hit_p), 1)),
        ("Answer correctness, all 25 questions", pct("base", "correct"), pct("brain", "correct")),
        ("  recall (8)", pct("base", "correct", ["recall"]), pct("brain", "correct", ["recall"])),
        ("  gotcha (5)", pct("base", "correct", ["gotcha"]), pct("brain", "correct", ["gotcha"])),
        ("  analytics (7)", pct("base", "correct", ["analytics"]), pct("brain", "correct", ["analytics"])),
        ("  boundary: correct refusals (5)", pct("base", "correct", ["boundary"]), pct("brain", "correct", ["boundary"])),
        ("Answers with citations (20 answerable)", pct("base", "cited", only=non_boundary), pct("brain", "cited", only=non_boundary)),
    ]
    mode = "Snowflake (Cortex Search + AI_COMPLETE)" if snow else "local mock (DuckDB, BM25 search, rule-based extraction, no LLM)"
    lines = [f"| Metric | Naive baseline | Plant Brain |", "|---|---|---|"]
    for name, (bn, bd), (pn, pd_) in metrics:
        lines.append(f"| {name} | {bn}/{bd} ({bn / bd:.0%}) | {pn}/{pd_} ({pn / pd_:.0%}) |")
    table = "\n".join(lines)
    print(f"Backend: {mode}\n\n{table}\n")
    print(f"golden anomaly top-3  Plant Brain: {top_p}\n                      baseline:    {top_b}\n")
    fails = [r for r in rows if not r["brain"]["correct"]]
    for r in rows:
        print(f"{r['q']['id']:3} brain={'OK ' if r['brain']['correct'] else 'MISS'} base={'OK ' if r['base']['correct'] else 'MISS'} "
              f"tool={r['p_out'].get('tool'):8} {r['q']['question']}")

    if "--write" in sys.argv:
        detail = "\n".join(f"| {r['q']['id']} | {r['q']['category']} | {r['q']['question']} | {r['p_out'].get('tool')} | "
                           f"{'✔' if r['brain']['correct'] else '✘'} | {'✔' if r['base']['correct'] else '✘'} |" for r in rows)
        fail_txt = "\n".join(f"- **{r['q']['id']}** {r['q']['question']}: Plant Brain answered with tool `{r['p_out'].get('tool')}`; "
                             f"answer started \"{r['p_out']['answer'][:140].replace(chr(10), ' ')}…\"" for r in fails) or "- none"
        (ROOT / "docs/EVALUATION.md").write_text(f"""# Evaluation

Generated by `python eval/run_eval.py --write`. **Backend: {mode}.**
Questions: `eval/golden_questions.yaml` (8 recall, 5 gotcha, 7 analytics, 5 boundary). Expected facts come from
the synthetic scenario (`data_gen/answer_key.json`) and, for analytics, from the verified query's own result.

## Results

{table}

Golden anomaly (P3, 31 Aug) top-3 sources: Plant Brain `{top_p}`, baseline `{top_b}`.

## How to read this honestly
- **Mock mode has no LLM.** Both systems are retrieval plus a template answer, so these numbers measure retrieval,
  routing, the knowledge graph and the guard, not answer fluency. Run `python eval/run_eval.py --snowflake --write`
  on a live account to get the Cortex numbers (Cortex Search + AI_COMPLETE for both systems).
- **The baseline is deliberately naive** (the "chat with your notes" status quo): BM25 over raw notes, top-3 snippets,
  no structure. It can still contain the right words by luck; scoring is keyword-based, so it gets that credit.
- **Plant Brain is tuned on the same synthetic data it is evaluated on.** Treat this as a functional proof of the
  approach on the golden scenario, not as a generalisation claim.
- Citation counting: a baseline answer counts as cited when it lists raw source ids; a Plant Brain answer when it
  cites card ids or a verified query.

## History (kept on purpose)
- **First run: 22/25.** The eval caught three real bugs: MTTR and scrap questions were not routed to their verified
  queries (keyword scoring too strict), and the CV1 belt warning was buried because the staleness penalty was applied
  after the "warnings wanted" boost. Fixed with weighted router keywords and by demoting stale cards before boosting,
  then re-run. Both changes are logged in `coco/PROMPTS.md`. A high score on a scenario we designed is expected; the
  comparison with the baseline is the point.

## Where Plant Brain misses
{fail_txt}

## Per question

| Id | Category | Question | Plant Brain tool | Plant Brain | Baseline |
|---|---|---|---|---|---|
{detail}
""")
        print("\nwrote docs/EVALUATION.md")


if __name__ == "__main__":
    main()
