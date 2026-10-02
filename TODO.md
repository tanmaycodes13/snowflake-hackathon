# Plant Brain — Live TODO

Deadline: **4 Oct 2026**. Legend: **[must]** / **[should]** / **[stretch]**. ✔ = done and verified locally (mock),
◐ = written against Snowflake docs, **not yet run on a live account**.

## Blocker
- [ ] [must] Live Snowflake access: fix `PB_SVC` key (DESC USER fingerprint) **or** use your own user with browser SSO (JUMPSTART B3)
- [ ] [must] Credit card added so AI features are enabled (JUMPSTART B1)

## Phase 0–2 — Scaffold, pitch, data
- [x] [must] Repo layout, `.gitignore`, `.env.example`, `AGENTS.md`, `coco/PROMPTS.md` ✔
- [x] [must] `docs/PITCH.md` + 12-slide deck (artifact) ✔
- [x] [must] `data_gen/` generator, golden scenario, answer key, `--verify` ✔

## Phase 3 — Foundation
- [x] [must] `00_setup.sql` ◐ · `01_raw_tables.sql` ✔ · `02_load.sql` ◐ · `03_core_views.sql` ✔ (OEE = answer key on DuckDB)

## Phase 4 — Brain
- [x] [must] `04_cards.sql`: sources, cache, log, `EXTRACT_NEW_CARDS` (AI_COMPLETE + JSON schema) ◐, task (suspended) ◐, `CARDS` + `EDGES` views ✔
- [x] [must] Recurrence rule (RECURRED via graph) + CONTRADICTS/SUPERSEDES edges ✔ · staleness flag ✔
- [x] [must] `coco/skills/card-extractor/SKILL.md` ✔ · mock extractor `mocks/cortex.py` ✔
- [ ] [must] Run `CALL BRAIN.EXTRACT_NEW_CARDS()` on Cortex and confirm C1–C12 (`run_checks.py --snowflake`)

## Phase 5 — Anomalies
- [x] [must] `05_anomaly.sql`: z-score + slope, signatures, pattern match, failure window ✔ (P3 matches E1/E2/E3; decoys don't)
- [ ] [stretch] `SNOWFLAKE.ML.ANOMALY_DETECTION` side-by-side

## Phase 6 — Search, semantic view, procs, agent
- [x] [must] `06_search.sql` ◐ · `07_semantic_view.sql` (generated, 10 verified queries) ◐ · `08_procs.sql` Python procs ◐ · `09_agent.sql` ◐
- [x] [must] `coco/skills/work-order-drafter/SKILL.md` ✔ · `APP.RESET_DEMO()` ✔ (logic) ◐ (proc)
- [x] [should] Python orchestration of the 3 tools in the app (`plant_brain/agent.py`) ✔

## Phase 7 — App
- [x] [must] 5 pages, local mock run, headless-browser click-through ✔
- [ ] [must] `snow streamlit deploy --project app --replace` and click through in Snowsight ◐

## Phase 8 — Evaluation
- [x] [must] 25 golden questions, baseline vs Plant Brain, `docs/EVALUATION.md` (mock) ✔
- [ ] [should] Cortex run: `python eval/run_eval.py --snowflake --write`; update slide 6

## Phase 9 — Docs, demo, submission
- [x] [must] `JUMPSTART.md`, `README.md`, `ARCHITECTURE.md`, `docs/DEMO_SCRIPT.md`, `mocks/README.md` ✔
- [ ] [must] Full quickstart from a clean clone (local path ✔; Snowflake path pending access)
- [ ] [stretch] Voice notes (`AI_TRANSCRIBE`) · MCP server · multi-plant

## Submission checklist
- [ ] Repo public · [x] README complete · [ ] Demo video ≤3 min · [ ] Deck PDF (export from artifact) · [ ] Teardown tested · [x] No secrets committed
