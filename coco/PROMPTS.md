# How CoCo was used

A running log of key prompts given to the coding agent, what it produced, and what we changed. Judges score how CoCo was used, so keep this honest and current.

| # | Phase | Prompt (summary) | What was produced | What we changed / why |
|---|---|---|---|---|
| 1 | 0–1 | Master prompt, sections 0–3: scaffold the repo, write the 7-slide pitch, pre-fill TODO.md | Full repo scaffold with phase-tagged stubs, `docs/PITCH.md`, `TODO.md`, `AGENTS.md`, `.env.example`, `.gitignore` | Approved at Checkpoint 1, no changes |
| 2 | 2 | Master prompt, section 4: data model + seeded generator + golden scenario + answer key + `--verify` | `scenario.py` (all golden constants and hand-written notes), `generate.py` (stdlib only, 311k readings, 144 WOs, 295 notes), `answer_key.json`, `DATA_MODEL.md` | Chose stdlib over numpy for cross-machine determinism. The first `--verify` failed 5 checks: the check compared against a 24 h mean baseline, which the daily cycle distorts. Fixed it to compare against the same clock time before onset, and reserved 2 clean days before each golden onset. Removed duplicate chatter lines and replaced exact failure-mode names in handovers with casual labels for realism. |
| 3 | 3 | "Guide me through the Snowflake account, or connect directly" | Checked the current docs: trial accounts have AI features disabled until a card is added; USE AI FUNCTIONS + CORTEX_USER grants; Oregon has the broadest native model coverage. Wrote `00_setup.sql` (with a resource monitor), `00b_agent_user.sql` (key-pair service user), `01`–`03` SQL, `checks/phase3_checks.sql`, `scripts/sf.py`, `docs/SNOWFLAKE_SETUP.md` | ASSET_HEALTH first compared the last 6 h against a 7-day mean, which the daily cycle distorts. Changed it to compare against the same clock hours over the prior 7 days, and simulated it in Python first: exactly P3, CNC2 and CV2 come out as ALERT. |

## Skills
- `coco/skills/card-extractor/SKILL.md`: extraction rules for knowledge cards (Phase 4)
- `coco/skills/work-order-drafter/SKILL.md`: drafting rules for work orders (Phase 6)
