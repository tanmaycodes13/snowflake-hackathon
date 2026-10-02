# Demo video script: Plant Brain (target 4:00, max 5:00)

Team ReLearn · Presenter: Tanmay · Track 3: Predictive Maintenance & OEE Command Center
All data is **synthetic** (fictional plant, people and assets). Say so once on camera, at 0:20.

Narration is about 560 words at a calm ~140 words per minute. **Bold lines are what you say.** Plain lines are what you click.

---

## Before you hit record (10 minutes)

1. In the app sidebar, click **Reset demo** (or run `CALL PLANT_BRAIN.APP.RESET_DEMO();`). This clears old drafts and jobs.
2. Open these tabs, in this order:
   1. the deck, on the cover slide;
   2. the Streamlit app (Snowsight → Projects → Streamlit → **PLANT_BRAIN_APP**), on **Command Center**;
   3. a Snowsight worksheet with the two queries from step 7 already pasted in.
3. Click through every app page once, so the warehouse is warm and nothing spins on camera.
4. Set the browser zoom to 110–125%, hide the bookmarks bar, and turn off notifications. Record at 1920×1080.
5. Keep this script open on a second screen or your phone.
6. Fallback: if the Snowflake app is slow, record the same flow on the local mock (`make app`). Every click and number is identical.

---

## The script

### 0:00–0:20 · Hook (deck: cover slide)
**"Every factory has a Ravi: the senior technician everyone calls when a machine acts up. Ravi retires next year. When he leaves, his fixes leave with him. We're team ReLearn, and this is Plant Brain: when your best technician retires, their knowledge doesn't."**

### 0:20–0:45 · The problem (deck: problem slide → persona slide)
**"Sensors can tell you that a machine is drifting. They can't tell you what fixed it last time. That lives in people's heads, in scribbled work orders, and in shift handovers nobody searches. Meet Anjali, a maintenance planner at a fictional plant in Pune. Everything you'll see runs on synthetic data, all inside Snowflake."**

### 0:45–1:05 · Command Center (app: Command Center)
- Point at the KPI row, then at the **Active anomalies** table.

**"This is Anjali's morning: OEE by line, and three active anomalies. Two machines are flagged HIGH. But Press P3 is CRITICAL, because its pattern matches four past failures on this same machine."**
- Keep **A-P3-2026083104** selected and click **Open →**.

### 1:05–1:50 · Brain recall (app: Anomaly → Brain)
- Point at the four metrics at the top.

**"Vibration is up about nine percent and temperature is starting to follow. The Brain estimates twenty-one to fifty-four hours to failure. That's a range, because one number would be false precision."**
- Point at the chart: the orange line against the gray ones.

**"Orange is today. Gray is every past P3 failure, lined up on the hour each one started. It's the same shape every time: vibration climbs, then temperature."**
- Point at the top recalled card (CARD-HN-0163-2).

**"Here's what fixed it: replace the bearing *and* switch the grease from LG-2 to HT-3. Ravi wrote that down clearly exactly once, in a shift handover note, between chatter about the canteen AC. The Brain found it and cites it."**
- Point at the yellow **Gotcha** banner.

**"And here's what *not* to do. In July a junior replaced only the bearing. His note says 'trial run ok', but the same failure came back nine days later. No one wrote 'this didn't work'. The Brain worked it out by linking the two work orders."**
- Click **Draft work order →**.

### 1:50–2:25 · Draft and human approval (app: Work Order Approval)
- Scroll slowly through the draft.

**"One click drafts the work order. It gives the cited fix, a 'Do NOT' list, and the parts. Bearing 6312 is down to one in stock with a twenty-one-day lead time, so it's flagged. It suggests Ravi, who fixed this three times. Since he's retiring, it also suggests pairing him with a junior."**
- Approver = **Anjali** → click **✅ Approve**.

**"The agent can draft, but it can never approve. Only a named human can. Anjali approves, and a real work order opens."**

### 2:25–2:55 · The learning loop (app: Close Job)
- In the sidebar, click **Close Job**. The closing note is prefilled. Click **Submit and close**.

**"The job's done, and the technician closes it in his own words, abbreviations and all. Watch: that note just became a new knowledge card, linked to P3 and to bearing wear. It also supersedes the bearing-only fix that failed. Every closed job teaches the Brain something, and nobody had to write documentation."**

### 2:55–3:25 · Ask the Plant (app: Ask the Plant)
- Click the example **"What was the OEE for line L3 last week?"**, or type it.

**"Anjali can also just ask. Analytics questions run verified SQL queries from our semantic view, so the numbers are exact and cited."**
- Click **"Which technician is most likely to quit this year?"**

**"And when a question isn't something the data can answer, like guessing who'll quit, it says so instead of making something up."**

### 3:25–3:45 · Under the hood (Snowsight worksheet)
- Run the queries you pasted in earlier:
  ```sql
  SELECT card_id, card_type, outcome, source_excerpt
  FROM PLANT_BRAIN.BRAIN.CARDS WHERE asset_id = 'P3' ORDER BY created_at DESC LIMIT 6;

  SHOW CORTEX SEARCH SERVICES IN SCHEMA PLANT_BRAIN.BRAIN;
  ```

**"Everything is Snowflake-native. Cortex AI_COMPLETE extracts the cards, and only once per note. Then there's Cortex Search, a semantic view for Cortex Analyst, a Cortex Agent, Snowpark procedures, and this Streamlit app. No data leaves the account."**

### 3:45–4:10 · Proof and close (deck: architecture slide → proof slide → thank-you slide)
**"We tested it honestly. On twenty-five golden questions, live on Cortex, Plant Brain got eighteen right. A keyword-search baseline got nine. It answered every analytics question and refused every out-of-scope one. Where it missed, it was too cautious, and that's our next fix. We built it with CoCo CLI, with every prompt and skill logged in the repo."**

**"When your best technician retires, their knowledge doesn't. Thank you."**

---

## If you have time to stretch toward 5:00 (optional add-ons)
| Insert after | Add (about 20–30 s each) |
|---|---|
| 1:50 | Flip the chart's **Sensor** toggle to Temperature: "Temperature follows about eleven hours later, the same lag as every past failure." |
| 2:55 | Ask **"What should I NOT do when fixing the P3 bearing?"**: it lists the warnings with card citations. |
| 3:45 | Snowsight → AI & ML → Agents → **PLANT_BRAIN_AGENT**: ask "How was P3's bearing issue fixed before?" |

## Recording tips
- Record the screen and voice in one take per section. Cut between sections in editing. A mistake only costs you that section.
- Move the mouse slowly and pause for one second on each thing you point at. Viewers follow the cursor.
- Zoom in during editing (to 150%) on the gotcha banner, the 21–54 h metric and the new card.
- Add captions. Judges often watch muted.
- Don't read the numbers off the slides at speed. Say "eighteen out of twenty-five" and let it land.
- Keep the final cut **under 5:00**. If you're over, trim the Snowsight section first.

## Checklist before uploading
- [ ] The **Reset demo** was done before recording (the approval should create WO-2026-0145 on a fresh reset)
- [ ] "Synthetic data" was said once
- [ ] No credentials, account URLs or `.env` contents are visible on screen
- [ ] The video is ≤ 5:00 at 1080p, with captions on
