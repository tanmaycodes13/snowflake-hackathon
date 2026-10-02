"""Plant Brain: Streamlit app (runs in Streamlit in Snowflake, or locally against the mock).

Local:      PB_BACKEND=mock streamlit run app/streamlit_app.py
Snowflake:  snow streamlit deploy --project app   (see JUMPSTART.md)
ALL DATA IS SYNTHETIC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plant_brain import agent  # noqa: E402
from plant_brain.runtime import make_brain  # noqa: E402

st.set_page_config(page_title="Plant Brain", page_icon="🧠", layout="wide")

# Chart colors: categorical slots 1-3 for lines L1-L3; LIVE trace = accent, past episodes = one muted gray.
LINE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]
LIVE_COLOR, PAST_COLOR = "#eb6834", "#8a8984"
PRIORITY_ICON = {"CRITICAL": "🔴 CRITICAL", "HIGH": "🟠 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "⚪ LOW"}
DEMO_NOTE = ("P3 DE brg 6312 replaced + HT-3 grease, old grease flushed. vib back to normal after trial run. "
             "Ravi guided on call. keep 2 brg in store pls")


@st.cache_resource
def brain_and_mode():
    return make_brain()


brain, MODE = brain_and_mode()


def df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def cite_card(c: dict, expanded: bool = False):
    stale = "  ⚠ possibly stale" if c.get("is_stale") else ""
    label = f"{c['card_type']} · {c['outcome']} · {c['card_id']}{stale}"
    with st.expander(label, expanded=expanded):
        st.markdown(f"> {c['source_excerpt']}")
        st.caption(f"Source **{c['source_type']} {c['source_id']}** · author {c.get('author_name') or c.get('author_technician_id')} "
                   f"· {c.get('created_at')} · confidence {c.get('confidence') or 0:.2f} · extracted by {c.get('extracted_by')}")
        if c.get("outcome_basis") and c["outcome_basis"] != "stated in source":
            st.caption(f"Outcome derived by the graph: {c['outcome_basis']}")
        if c.get("is_stale"):
            st.caption(f"Asset changed after this card: {c.get('stale_reason')}")


# ---------------------------------------------------------------------------------------------- sidebar
st.sidebar.title("🧠 Plant Brain")
st.sidebar.caption("Deccan Precision Components, Pune: **synthetic data**")
PAGES = ["Command Center", "Anomaly → Brain", "Work Order Approval", "Close Job", "Ask the Plant"]
if "nav_to" in st.session_state:            # set by buttons that jump to another page
    st.session_state.page = st.session_state.pop("nav_to")
if "page" not in st.session_state:
    st.session_state.page = PAGES[0]
page = st.sidebar.radio("Page", PAGES, key="page")
st.sidebar.divider()
st.sidebar.caption(f"Backend: **{MODE}**")
if st.sidebar.button("Reset demo", help="Removes drafts and demo work orders. Historical data is untouched."):
    st.sidebar.success(brain.reset_demo())
    st.session_state.pop("chat", None)


def go(p: str):
    st.session_state.nav_to = p


# ---------------------------------------------------------------------------------------------- 1. Command Center
if page == "Command Center":
    st.title("Command Center")
    anomalies = brain.active_anomalies()
    lines = df(brain.oee_line_daily(30))
    assets = df(brain.oee_asset_summary(7))
    last_day = lines["oee_date"].max()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Plant OEE, last day", f"{lines[lines.oee_date == last_day].oee.mean():.1%}")
    c2.metric("Plant OEE, 7 days", f"{assets.oee.mean():.1%}")
    c3.metric("Active anomalies", len(anomalies))
    c4.metric("Critical", sum(a["priority"] == "CRITICAL" for a in anomalies))

    st.subheader("Active anomalies")
    if anomalies:
        tbl = df([{"Priority": PRIORITY_ICON.get(a["priority"], a["priority"]), "Asset": a["asset_id"], "Line": a["line_id"],
                   "Signal": a["sensors"], "Shape": a["vib_shape"], "Since": f"{a['start_hr']:%d %b %H:%M}",
                   "Hours": a["duration_h"], "Matches past failure": a["matched_failure_mode"] or "no match",
                   "Est. window (h)": (f"{a['eta_low_h']:.0f}–{a['eta_high_h']:.0f}" if a["eta_low_h"] is not None else "–"),
                   "Anomaly": a["anomaly_id"]} for a in anomalies])
        st.dataframe(tbl, hide_index=True, use_container_width=True)
        pick = st.selectbox("Open in the Brain", [a["anomaly_id"] for a in anomalies], key="cc_pick")
        if st.button("Open →", type="primary"):
            st.session_state.anomaly_id = pick
            go("Anomaly → Brain")
            st.rerun()
    else:
        st.success("No active anomalies.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("OEE by line, last 30 days")
        chart = alt.Chart(lines).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=30)).encode(
            x=alt.X("oee_date:T", title=None),
            y=alt.Y("oee:Q", title="OEE", axis=alt.Axis(format="%"), scale=alt.Scale(zero=False)),
            color=alt.Color("line_id:N", title="Line", scale=alt.Scale(domain=["L1", "L2", "L3"], range=LINE_COLORS)),
            tooltip=[alt.Tooltip("line_id:N", title="Line"), alt.Tooltip("oee_date:T", title="Date"),
                     alt.Tooltip("oee:Q", title="OEE", format=".1%"), alt.Tooltip("availability:Q", format=".1%"),
                     alt.Tooltip("performance:Q", format=".1%"), alt.Tooltip("quality:Q", format=".1%")],
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)
    with right:
        st.subheader("Asset OEE, last 7 days")
        st.dataframe(assets.assign(oee=lambda d: d.oee.map("{:.1%}".format),
                                   availability=lambda d: d.availability.map("{:.1%}".format))
                     [["asset_id", "line_id", "oee", "availability", "downtime_min"]],
                     hide_index=True, use_container_width=True, height=300)
    with st.expander("Asset health (latest 6 h vs same hours, prior 7 days)"):
        st.dataframe(df(brain.asset_health()), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------------------------- 2. Anomaly -> Brain
elif page == "Anomaly → Brain":
    st.title("Anomaly → Brain")
    anomalies = brain.active_anomalies()
    if not anomalies:
        st.info("No active anomalies.")
        st.stop()
    ids = [a["anomaly_id"] for a in anomalies]
    default = ids.index(st.session_state.get("anomaly_id", ids[0])) if st.session_state.get("anomaly_id") in ids else 0
    aid = st.selectbox("Anomaly", ids, index=default,
                       format_func=lambda i: next(f"{PRIORITY_ICON.get(a['priority'])} · {a['asset_id']} · {a['sensors']}"
                                                  for a in anomalies if a["anomaly_id"] == i))
    st.session_state.anomaly_id = aid
    a = brain.anomaly(aid)
    r = brain.recall(aid)
    w = r["window"]
    matches = brain.matches(aid)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Vibration vs profile", f"{a['vib_rise_pct'] or 0:+.1f}%")
    c2.metric("Temperature vs profile", f"{a['temp_rise_c'] or 0:+.1f} °C")
    c3.metric("Past failures matched", sum(1 for m in matches if m["is_match"]))
    if w and w["eta_low_h"] is not None:
        c4.metric("Failure window (estimate)", f"{w['eta_low_h']:.0f}–{w['eta_high_h']:.0f} h")
    else:
        c4.metric("Failure window (estimate)", "no matching history")

    trace = df(brain.sensor_trace(aid))
    if not trace.empty:
        trace["kind"] = trace["live"].map({True: "Live (today)", False: "Past failure episodes"})
        sensor = st.radio("Sensor", ["Vibration (% vs profile)", "Temperature (°C vs profile)"], horizontal=True)
        ycol = "vib_resid_pct" if sensor.startswith("Vib") else "temp_resid_c"
        base = alt.Chart(trace).encode(
            x=alt.X("hours_since_start:Q", title="Hours since anomaly start"),
            y=alt.Y(f"{ycol}:Q", title=sensor),
            detail="series:N",
            color=alt.Color("kind:N", title=None, scale=alt.Scale(domain=["Live (today)", "Past failure episodes"],
                                                                   range=[LIVE_COLOR, PAST_COLOR])),
            tooltip=[alt.Tooltip("series:N", title="Episode"), alt.Tooltip("hours_since_start:Q", title="Hour", format=".0f"),
                     alt.Tooltip(f"{ycol}:Q", title=sensor, format=".2f")])
        past = base.transform_filter("datum.live == false").mark_line(strokeWidth=1.5, opacity=0.7)
        live = base.transform_filter("datum.live == true").mark_line(strokeWidth=3)
        st.altair_chart((past + live).properties(height=320), use_container_width=True)
        st.caption("Today's trace overlaid on the matched past episodes, aligned on the hour each anomaly started. "
                   "Each past line ends where the machine was stopped for repair.")

    derived = [c for c in r["gotchas"] if (c.get("outcome_basis") or "").startswith("recurrence")]
    written = [c for c in r["gotchas"] if c["card_type"] == "GOTCHA"]
    if derived:
        g = derived[0]
        st.warning(f"**Gotcha:** {g['source_id']} ({g.get('author_name')}) didn't hold: {g['outcome_basis']}.  [{g['card_id']}]"
                   + (f"  \nIn the plant's words: \"{written[0]['source_excerpt']}\"  [{written[0]['card_id']}]" if written else ""))
    elif written:
        st.warning(f"**Gotcha:** {written[0]['source_excerpt']}  [{written[0]['card_id']}]")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("What the Brain recalls")
        for i, c in enumerate(r["top"]):
            cite_card(c, expanded=(i == 0))
        with st.expander(f"All warnings ({len(r['gotchas'])})"):
            for c in r["gotchas"]:
                st.markdown(f"- {c['source_excerpt']}  `{c['card_id']}`")
    with right:
        st.subheader("Matched history")
        if matches:
            st.dataframe(df([{"Work order": m["wo_id"], "Failure mode": m["failure_mode"], "Score": round(m["score"], 2),
                              "Match": "yes" if m["is_match"] else "no", "Fixed by": m["technician"]} for m in matches]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("No pre-failure history on this asset.")
        if w:
            st.caption(f"**Estimate only.** {w['note']}. Linear trend: "
                       f"{w['linear_eta_h']:.0f} h; past episodes: {w['analog_eta_h']:.0f} h."
                       if w.get("linear_eta_h") is not None else f"**Estimate only.** {w['note']}")
    if st.button("Draft work order →", type="primary"):
        d = brain.draft_work_order(aid, created_by="streamlit")
        st.session_state.draft_id = d["draft_id"]
        go("Work Order Approval")
        st.rerun()

# ---------------------------------------------------------------------------------------------- 3. Approval
elif page == "Work Order Approval":
    st.title("Work Order Approval")
    pending = brain.drafts("PENDING_APPROVAL")
    if not pending:
        st.info("No drafts waiting. Draft one from **Anomaly → Brain**.")
    else:
        ids = [d["draft_id"] for d in pending]
        sel = st.session_state.get("draft_id") if st.session_state.get("draft_id") in ids else ids[0]
        did = st.selectbox("Draft", ids, index=ids.index(sel))
        d = brain.draft(did)
        st.subheader(d["title"])
        st.caption(f"{d['draft_id']} · status **{d['status']}** · drafted by {d['created_by']} at {d['created_at']}")
        st.markdown(d["body"])
        with st.expander(f"Citations ({len((d['cited_card_ids'] or '').split(','))} cards)"):
            for cid in [c for c in (d["cited_card_ids"] or "").split(",") if c]:
                c = brain.card(cid)
                if c:
                    cite_card(c)
        st.divider()
        approver = st.text_input("Approver (your name)", value="Anjali")
        b1, b2, b3 = st.columns(3)
        if b1.button("✅ Approve", type="primary", use_container_width=True):
            try:
                res = brain.approve_work_order(did, approver)
                st.success(f"Approved by {res['approved_by']}. Work order **{res['wo_id']}** is open.")
                st.session_state.wo_id = res["wo_id"]
            except Exception as e:
                st.error(str(e))
        with b2.popover("✏️ Edit", use_container_width=True):
            body = st.text_area("Draft body", d["body"], height=300)
            if st.button("Save edit"):
                brain.edit_draft(did, body, approver)
                st.rerun()
        with b3.popover("❌ Reject", use_container_width=True):
            reason = st.text_input("Reason")
            if st.button("Confirm reject"):
                brain.reject_draft(did, approver, reason or "no reason given")
                st.rerun()
    with st.expander("All drafts"):
        st.dataframe(df(brain.drafts()), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------------------------- 4. Close Job
elif page == "Close Job":
    st.title("Close Job")
    open_wos = brain.open_work_orders()
    if not open_wos:
        st.info("No open work orders. Approve a draft first.")
    else:
        ids = [w["wo_id"] for w in open_wos]
        sel = st.session_state.get("wo_id") if st.session_state.get("wo_id") in ids else ids[0]
        wo_id = st.selectbox("Work order", ids, index=ids.index(sel),
                             format_func=lambda i: next(f"{i} · {w['asset_id']} · {w.get('title') or ''}" for w in open_wos if w["wo_id"] == i))
        wo = next(w for w in open_wos if w["wo_id"] == wo_id)
        st.caption(f"Assigned technician: {wo['technician_id']} · planned parts: {wo['parts_used']}")
        tech = st.text_input("Technician closing the job", value=wo["technician_id"] or "")
        note = st.text_area("Closing note (write it the way you normally would)", DEMO_NOTE, height=120)
        if st.button("Submit and close", type="primary"):
            with st.spinner("Closing the job and extracting knowledge…"):
                res = brain.close_job(wo_id, note, tech or None)
            st.session_state.last_close = res
    res = st.session_state.get("last_close")
    if res:
        st.success(f"{res['wo_id']} closed. The note became {len(res['new_cards'])} new knowledge card(s): the learning loop.")
        for c in res["new_cards"]:
            cite_card(c, expanded=True)
        if res["edges"]:
            st.markdown("**New links in the knowledge graph**")
            st.dataframe(df(res["edges"]), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------------------------- 5. Ask the Plant
elif page == "Ask the Plant":
    st.title("Ask the Plant")
    st.caption("Answers come only from the plant's data, with citations. Analytics use verified queries from the "
               "semantic view; maintenance answers cite knowledge cards. It refuses what the data can't establish, "
               "and it never approves work orders.")
    examples = ["How was P3's bearing issue fixed before?", "What should I NOT do when fixing the P3 bearing?",
                "What was the OEE for line L3 last week?", "Which spare parts are at risk of stockout?",
                "Which technician is most likely to quit this year?"]
    cols = st.columns(len(examples))
    clicked = None
    for c, ex in zip(cols, examples):
        if c.button(ex, use_container_width=True):
            clicked = ex
    st.session_state.setdefault("chat", [])
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("citations"):
                st.caption("Citations: " + ", ".join(m["citations"]))
    q = st.chat_input("Ask about the plant…") or clicked
    if q:
        st.session_state.chat.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        out = agent.ask(brain, q)
        with st.chat_message("assistant"):
            st.markdown(out["answer"])
            if out["citations"]:
                st.caption("Citations: " + ", ".join(out["citations"]))
            st.caption(f"tool: {out['tool']}" + (" · refused" if out["refused"] else ""))
        st.session_state.chat.append({"role": "assistant", "content": out["answer"], "citations": out["citations"]})

st.sidebar.divider()
st.sidebar.caption("SYNTHETIC DATA. All people, plants and assets are fictional.")
