# Demo video script: Plant Brain, run end to end in CoCo CLI (3:30–4:30, hard max 5:00)

Team ReLearn · Presenter: Tanmay · Track 3: Predictive Maintenance & OEE Command Center

**What the judges asked for, and where it is in this video**

| Requirement | Where |
|---|---|
| End-to-end workflow executed **via CoCo CLI**, as a screen recording | The whole video runs in the `cortex` terminal (0:15–3:50) |
| **Input → Processing → Output** shown | Every skill segment has three on-screen captions: INPUT / PROCESSING / OUTPUT |
| At least one fully working workflow | Triage → Draft → **Human approval** → Close job → New knowledge (one continuous run) |
| 2–3 modular skills | `$anomaly-triage` → `$work-order-drafter` → `$card-extractor`, project skills in `.cortex/skills/` |
| 3–5 minutes | The script runs ~4:00; the cut list below gets you under 4:00 if needed |

All data is **synthetic** (a fictional plant). Say so once, at 0:10.

---

## Setup (do it once, ~15 minutes before recording)

1. **Install CoCo CLI and connect** (see the CoCo CLI docs):
   ```bash
   curl -qLsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh
   ```
   Use the Snowflake connection you deployed with (it lives in `~/.snowflake/connections.toml`).
   To see its name: `snow connection list`, or just run `cortex` with no `-c` and pick it in the setup wizard.
2. **Deploy is done** (`python scripts/deploy_snowflake.py`). Check that steps 04, 05, 06 and 08 exist: the card procedure, anomalies, `CARD_SEARCH`, and the `APP.*` procedures.
3. **Reset the demo state** (and again before every retake): run `snowflake/demo_reset.sql` in Snowsight, or
   `python scripts/sf.py run snowflake/demo_reset.sql`.
4. **Start CoCo from the repo root**, so it loads the project skills:
   ```bash
   cd snowflake-hackathon            # the repo root (your clone folder)
   cortex -c <your-connection-name>  # or plain `cortex` and pick the connection
   ```
   Type `$$`. All three skills must be listed: `anomaly-triage`, `work-order-drafter`, `card-extractor`.
5. **Do a dry run of the whole script once.** It warms the warehouse and teaches you where CoCo pauses for
   tool-permission prompts. Then run `demo_reset.sql` again.
6. **Set up the screen.** Terminal font at 18–20 pt with a dark theme, and the window maximised at 1920×1080.
   Hide notifications. Have the Streamlit app open in a browser tab for the two short cutaways (optional).
7. **Never show** `.env`, `connections.toml`, keys or your account URL on screen.

If CoCo asks permission to run SQL, approve it. Those pauses can be trimmed in editing.

---

## The script

Bold = say it. `>` = type it into CoCo. CAPTION = on-screen text added in editing (a lower third).

### 0:00–0:15 · Hook (title card or deck cover)
**"Every factory has a Ravi: the senior technician everyone calls when a machine acts up. Ravi retires next year. We're team ReLearn, and this is Plant Brain. When your best technician retires, their knowledge doesn't."**

### 0:15–0:35 · The setup: CoCo CLI and three modular skills
CAPTION: *CoCo CLI · project skills in .cortex/skills/*
- Show the terminal with `cortex` running in the repo.
```
> $$
```
**"Everything you'll see runs in CoCo CLI against our Snowflake account. All the data is synthetic. Plant Brain is three modular skills. Each one takes an input, does its processing inside Snowflake, and hands its output to the next: triage, then draft, then learn."**

### 0:35–1:35 · Skill 1: `$anomaly-triage`
CAPTION: **INPUT:** *311k sensor readings · 144 work orders · 295 shift notes (in Snowflake)*
```
> $anomaly-triage What needs attention in the plant right now?
```
CAPTION while queries run: **PROCESSING:** *SQL z-score + slope · pattern match vs past failures · Cortex Search over knowledge cards*

**"CoCo loads the triage skill and runs it step by step. First, plain SQL finds the active anomalies. It's deterministic and explainable. Then it compares each one with that same machine's past failures, and uses Cortex Search to recall what the technicians wrote."**

- When the report prints, scroll to it.

CAPTION: **OUTPUT:** *P3 CRITICAL · 4 matching failures · 21–54 h (estimate) · cited fix + warning*

**"Three anomalies, but only Press P3 is critical. Its pattern matches four past bearing failures, and the failure window is twenty-one to fifty-four hours. That's an estimate, so it's shown as a range. Here's the fix, quoted from a shift note Ravi wrote once: replace the bearing *and* switch the grease to HT-3. And the warning: a bearing-only fix in July came back nine days later. Nobody wrote that down. The knowledge graph worked it out by linking the two work orders."**

### 1:35–2:35 · Skill 2: `$work-order-drafter` (with human approval)
CAPTION: **INPUT:** *anomaly A-P3-… from skill 1*
```
> $work-order-drafter Draft a work order for the P3 anomaly
```
CAPTION: **PROCESSING:** *Snowpark procedure APP.DRAFT_WORK_ORDER: cards + failure window + parts stock + technician history*

**"The second skill calls a Snowpark procedure. It's the same code our Streamlit app runs. It pulls the cited fix, the warnings, the spare-parts stock and who fixed this before."**

CAPTION: **OUTPUT:** *draft · status PENDING_APPROVAL · citations · BRG-6312 at risk · suggests Ravi*

**"The draft cites every line. Bearing 6312 is down to one in stock, so it's flagged. And it suggests Ravi, who's retiring, so it recommends pairing him with a junior. Notice the status: pending approval. CoCo stops here and asks who approves."**
```
> Approve it as Anjali
```
**"The agent can draft, but it can never approve. Only a named human can. Anjali approves, and work order 145 is open."**

- *(Optional 5 s cutaway: the Streamlit **Work Order Approval** page showing the same draft as APPROVED. It's the same tables.)*

### 2:35–3:35 · Skill 3: `$card-extractor`, the learning loop
CAPTION: **INPUT:** *the technician's closing note, written the way people really write*
```
> $work-order-drafter Close WO-2026-0145 with this note: P3 DE brg 6312 replaced + HT-3 grease, old grease flushed. vib normal after trial run. keep 2 brg in store pls
```
**"The job's done, and the technician closes it in his own words."**

CAPTION: **PROCESSING:** *Cortex AI_COMPLETE with a JSON schema, only on new text (cached by hash)*

CAPTION: **OUTPUT:** *new knowledge card + graph link SUPERSEDES the failed fix*

**"That note just became a knowledge card. It's linked to P3 and bearing wear, and it supersedes the fix that failed. And it works on any note, Hinglish included:"**
```
> $card-extractor Learn from this handover note: CV3 belt jerking again near tail pulley. Priya ne bola tension mat badhao, motor trip hota hai - pehle tail pulley alignment check karo. 2 mm off tha, aligned the tail pulley, belt running smooth now.
```
**"'Tension mat badhao' means 'don't increase the tension'. Cortex turns it into a warning card, and the alignment into a fix card. Each one cites the exact words. No forms, no documentation sprint. Every closed job teaches the Brain."**

### 3:35–4:05 · Wrap-up (deck: architecture slide → proof slide)
CAPTION: *Live on Snowflake Cortex: 18/25 vs 9/25 (keyword baseline) · analytics 7/7 · refusals 5/5*

**"Three modular skills, one workflow: triage, draft with human approval, and learn, all inside Snowflake with Cortex. We tested it on twenty-five golden questions, live on Cortex. Plant Brain got eighteen right. A keyword-search baseline got nine. Every prompt and skill is in the repo. When your best technician retires, their knowledge doesn't. Thank you."**

---

## Cut list (if you're over time)
1. Drop the Streamlit cutaway (−5 s).
2. Drop the Hinglish note in skill 3 (−25 s). The closing-note card alone still shows the learning loop.
3. Shorten the hook to its last sentence (−8 s).

## If CoCo's wording differs from the script
CoCo writes its own summaries, and Cortex writes the card text. Don't read numbers you can't see on screen. The
fixed facts are the anomaly id, 21–54 h, the matched work orders, WO-2026-0145 (after a fresh reset), and the
quoted note text. If a step errors (a missing object or a permission), stop the take, fix it, run
`demo_reset.sql`, and retake that segment. Record each segment separately and join them in editing.

## Before uploading
- [ ] Every segment shows INPUT / PROCESSING / OUTPUT captions
- [ ] `$$` shows the 3 skills; each skill is invoked by name (`$anomaly-triage`, `$work-order-drafter`, `$card-extractor`)
- [ ] The approval was typed by you, as a named human
- [ ] "Synthetic data" was said once
- [ ] No credentials, account URL or `.env` on screen
- [ ] The video is 3–5 minutes at 1080p, with captions burned in
