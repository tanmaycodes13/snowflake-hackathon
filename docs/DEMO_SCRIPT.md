# Demo Script: 3 minutes, click by click

> Everything shown is **synthetic** and reproduces exactly from `seed=42`. The IDs and numbers below come from `data_gen/answer_key.json`.
> The app screens are described as **designed for Phase 7**. Re-check each step against the built app before recording.

**Cast:** one presenter plays Anjali (planner) and, in step 5, the technician. An optional second person drives the clicks.
**Setup:** two windows. Window 1 is the deck, open on slide 1. Window 2 is the Streamlit app (Snowsight → Projects → Streamlit → `PLANT_BRAIN_APP`), already signed in, on **Command Center**.

## Run of show

| Time | Screen | Click | Say (verbatim-ish) |
|---|---|---|---|
| **0:00** | Deck, slide 1 (cover) | none | "Every plant has a Ravi: the senior technician everyone calls when a machine acts up. Ravi retires next year. Plant Brain makes sure his knowledge doesn't." |
| **0:15** | Switch to app → **Command Center** | none | "This is Anjali's morning. OEE by line, and three active anomalies." |
| **0:20** | Command Center | Point at the anomaly table: **P3 = ALERT**, CNC2, CV2 | "Press P3: vibration up about 10% since midnight, and temperature is starting to follow. Two other machines are also flagged. Watch how the Brain treats them differently." |
| **0:40** | Click the **P3** row → **Anomaly → Brain** | none | "We've seen this signature before, three times." |
| **0:45** | Anomaly → Brain: sensor chart | Toggle **overlay historical matches** | "Today's trace, in amber, overlaid on the three past episodes: 17 June, 22 July and 14 August. Same shape: vibration climbs, then temperature." |
| **0:60** | Recalled cards panel | Hover the top card | "Top card: Ravi's fix. Replace the DE bearing *and* switch the grease from LG-2 to HT-3. Cited from handover note **HN-0163**. He wrote that down clearly exactly once, between a line about material delays and the canteen AC." |
| **1:10** | Gotcha banner | Point at the amber banner | "And what *not* to do: in July a bearing-only fix recurred in 9 days, **WO-2026-0067**. Nobody wrote 'this failed' on that work order. The Brain worked it out by linking it to the recurrence." |
| **1:20** | Failure window | Point at the range bar | "Estimated 24 to 46 hours to threshold. It's labeled as an estimate: the low end is how past episodes accelerated, the high end is a straight-line trend." |
| **1:30** | Click **Draft work order** → **Work Order Approval** | none | "One click drafts the work order." |
| **1:35** | Draft | Scroll through it | "Parts: bearing 6312 and HT-3 grease. Only one bearing in stock, so it flags reorder risk. Suggested technician: Ravi, who fixed this three times. Every line cites a card." |
| **1:45** | Draft | Click **Approve** (approver: Anjali) | "The agent drafts. A human approves. It never approves anything itself." |
| **1:50** | Click **Close Job** | Paste the closing note below, click **Submit** | "Now the technician closes the job, in his own words." |
| **2:00** | Close Job: new-card panel | Wait for the refresh, point at the new card | "And there's the learning loop: his note is now a knowledge card, linked to P3 and bearing wear. Next time, the Brain knows a little more." |
| **2:15** | Click **Ask the Plant** | Type Q1 below | "Anjali can also just ask." (Answer shows OEE with a source.) |
| **2:25** | Ask the Plant | Type Q2 below | "And when the data can't answer, it says so instead of guessing." |
| **2:35** | Back to deck → slide 11 (proof) | none | "We didn't just demo the happy path. 25 golden questions, Plant Brain against a keyword-search baseline: [hit@3], [correctness], [citations], [refusals]." |
| **2:50** | Deck, slide 12 (close) | none | "All of it is Snowflake-native, built with CoCo. When your best technician retires, their knowledge doesn't. Thank you." |

## Scripted inputs (copy-paste)

**Closing note (step 5):**
```
P3 DE brg 6312 replaced + HT-3 grease, old grease flushed. vib back to normal after trial run. Ravi guided on call. keep 2 brg in store pls
```

**Q1, analytics:**
```
What was the OEE for line L3 last week, and what was the top downtime cause?
```

**Q2, boundary (must refuse, or answer "I can't establish that"):**
```
Which technician is most likely to quit this year?
```

**Backup Q2 (if Q1 runs long):** `What will P3's OEE be next quarter?`

## Before recording
- [ ] `python data_gen/generate.py --verify` passes, and the data loaded is fresh (`snowflake/02_load.sql` resets RAW, which also wipes earlier demo closing notes).
- [ ] Reset the demo state: no leftover drafts or closed jobs from rehearsal. Phase 6 will add an `APP.RESET_DEMO()` proc for this.
- [ ] Warm up: open every page once, so the warehouse is resumed and caches are hot.
- [ ] `PB_WH` is running: cold resume is ~1–2 s, fine, but do the warm-up anyway.
- [ ] Browser zoom at 110–125%, notifications off, bookmarks bar hidden.
- [ ] Record at 1920×1080. Keep it **≤ 3:00**; the timings above leave ~10 s slack.

## If something breaks live
| Failure | Fallback |
|---|---|
| Agent is slow or times out on Ask the Plant | Skip to the proof slide: "The agent's answers are in the eval table." |
| New card doesn't appear within ~10 s | Click **Refresh**. If still nothing, show the pre-recorded clip of step 5. |
| Streamlit won't load | Play the recorded demo video from 0:15. |
| Wi-Fi dies | The video is saved locally, and the deck exports to PDF. |

## Why this flow scores
- **Real-world relevance (30%):** it opens on a retiring expert and a ₹-denominated (illustrative) downtime cost, a problem every plant recognizes.
- **Technical execution (40%):** it shows detection, retrieval with citations, a graph-derived gotcha, a cited draft, human approval, and the learning loop, all inside Snowflake.
- **Completeness (30%):** the loop closes on screen, and the proof slide backs it with measured numbers against a baseline.
