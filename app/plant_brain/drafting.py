"""Work-order drafter. Pure Python, no I/O: inputs in, draft dict out.

Rules (mirrored in coco/skills/work-order-drafter/SKILL.md):
  1. Lead with the best RESOLVED FIX card for this asset + failure mode; cite its card id.
  2. Always include GOTCHA cards as "Do NOT" lines; cite them.
  3. Never recommend an action that only appears in a RECURRED card.
  4. Parts come from the cited fix; flag any part at/below its reorder point.
  5. Technician: whoever authored the most RESOLVED fixes for this asset + failure mode.
  6. The failure window is an ESTIMATE with a low-high range, never a single number.
  7. Status is always PENDING_APPROVAL. Only a human approver changes it.
"""
from __future__ import annotations


def _parts(parts_str: str | None) -> list[tuple[str, int]]:
    out = []
    for p in (parts_str or "").split(";"):
        p = p.strip()
        if not p:
            continue
        pid, _, qty = p.partition(":")
        out.append((pid.strip(), int(qty) if qty.strip().isdigit() else 1))
    return out


def draft(anomaly: dict, window: dict | None, cards: list[dict], stock: dict[str, dict],
          technicians: dict[str, dict]) -> dict:
    asset, fm = anomaly["asset_id"], (window or {}).get("failure_mode")
    fixes = [c for c in cards if c["card_type"] == "FIX" and c["outcome"] == "RESOLVED"
             and c.get("asset_id") == asset and (fm is None or c.get("failure_mode") == fm)]
    # explicit written fix from a handover note first, then most recent work-order fixes
    fixes.sort(key=lambda c: (c["source_type"] != "HANDOVER_NOTE", -(c.get("confidence") or 0),
                              str(c.get("created_at"))), reverse=False)
    gotchas = [c for c in cards if c["card_type"] == "GOTCHA" and c.get("asset_id") == asset
               and (fm is None or c.get("failure_mode") in (fm, None))]
    recurred = [c for c in cards if c["outcome"] == "RECURRED" and c["card_type"] == "FIX" and c.get("asset_id") == asset
                and (fm is None or c.get("failure_mode") == fm)]
    symptoms = [c for c in cards if c["card_type"] == "SYMPTOM_PATTERN" and c.get("asset_id") == asset]

    # parts: union of parts on resolved work-order fixes (most common first)
    counts: dict[str, int] = {}
    for c in fixes:
        for pid, _ in _parts(c.get("parts")):
            counts[pid] = counts.get(pid, 0) + 1
    parts = sorted(counts, key=lambda p: (-counts[p], p))
    parts_lines, risky = [], []
    for pid in parts:
        s = stock.get(pid)
        if not s:
            parts_lines.append(f"- {pid}: not in the spare-parts master")
            continue
        flag = s["stock_qty"] <= s["reorder_point"]
        if flag:
            risky.append(pid)
        parts_lines.append(f"- {pid} ({s['description']}): {s['stock_qty']} in stock, reorder point {s['reorder_point']}, "
                           f"lead time {s['lead_time_days']} d" + ("  ⚠ AT RISK: reorder now" if flag else ""))

    # technician: most resolved fixes authored for this asset + failure mode
    authors: dict[str, int] = {}
    for c in fixes:
        if c.get("author_technician_id"):
            authors[c["author_technician_id"]] = authors.get(c["author_technician_id"], 0) + 1
    tech_id = max(authors, key=lambda t: (authors[t], t)) if authors else None
    tech = technicians.get(tech_id, {}) if tech_id else {}

    cited = []
    lines = [f"**Asset:** {asset} ({anomaly.get('asset_type', '')}, line {anomaly.get('line_id', '')})",
             f"**Trigger:** anomaly {anomaly['anomaly_id']}: {anomaly.get('sensors', '')}; "
             f"vibration {anomaly.get('vib_rise_pct') or 0:+.1f}% vs profile, temperature {anomaly.get('temp_rise_c') or 0:+.1f} °C, "
             f"{anomaly.get('duration_h')} h so far ({anomaly.get('vib_shape')})"]
    if fm:
        lines.append(f"**Suspected failure mode:** {fm}, matching {window.get('n_matches')} past episode(s) on this asset")
    if window and window.get("eta_low_h") is not None:
        lines.append(f"**Failure window (ESTIMATE):** {window['eta_low_h']:.0f}–{window['eta_high_h']:.0f} h to threshold "
                     f"({window.get('threshold_rule') or 'failure-mode threshold'})")
    lines = ["\n\n".join(lines)]       # header facts as separate paragraphs
    lines.append("")
    lines.append("**Recommended action**")
    if fixes:
        best = fixes[0]
        cited.append(best["card_id"])
        lines.append(f"1. {best['action_taken']}  [{best['card_id']}]")
        for c in fixes[1:4]:
            cited.append(c["card_id"])
            lines.append(f"   - Same fix applied before: {c['source_id']} by {c.get('author_name') or c.get('author_technician_id')}  [{c['card_id']}]")
    else:
        lines.append("1. No resolved fix on record for this pattern. Inspect and diagnose; capture findings in the closing note.")
    if gotchas or recurred:
        lines.append("")
        lines.append("**Do NOT**")
        for c in gotchas[:3]:
            cited.append(c["card_id"])
            lines.append(f"- {c['source_excerpt']}  [{c['card_id']}]")
        for c in recurred[:2]:
            cited.append(c["card_id"])
            lines.append(f"- Repeat {c['source_id']}: {c.get('outcome_basis')}  [{c['card_id']}]")
    if symptoms:
        lines.append("")
        lines.append(f"**Known symptom pattern:** {symptoms[0]['source_excerpt']}  [{symptoms[0]['card_id']}]")
        cited.append(symptoms[0]["card_id"])
    lines.append("")
    lines.append("**Parts**")
    lines.extend(parts_lines or ["- none identified from past fixes"])
    lines.append("")
    if tech_id:
        lines.append(f"**Suggested technician:** {tech.get('full_name', tech_id)} ({tech_id}), authored {authors[tech_id]} "
                     f"resolved fix(es) for this pattern" + ("; retiring 2027, pair with a junior to transfer knowledge"
                                                              if tech.get("retiring_2027") else ""))
    lines.append("")
    lines.append("_Drafted by Plant Brain. Status PENDING_APPROVAL: a human must approve before work starts._")

    title = f"{asset}: {fm.replace('_', ' ').lower() if fm else 'anomaly'}, {'planned repair' if fixes else 'inspect'}"
    seen, cited_unique = set(), []
    for c in cited:
        if c not in seen:
            seen.add(c)
            cited_unique.append(c)
    return dict(title=title, body="\n".join(lines), asset_id=asset, failure_mode=fm,
                recommended_technician_id=tech_id, parts=";".join(parts), parts_at_risk=";".join(risky),
                eta_low_h=(window or {}).get("eta_low_h"), eta_high_h=(window or {}).get("eta_high_h"),
                cited_card_ids=",".join(cited_unique), status="PENDING_APPROVAL")
