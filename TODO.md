# Plant Brain — Live TODO

Deadline: **4 Oct 2026**. Legend: **[must]** / **[should]** / **[stretch]**. Tick items as they land; keep this file current.

## Phase 0 — Scaffold
- [x] [must] Repository layout per master prompt
- [x] [must] `.gitignore`, `.env.example` (no secrets in git)
- [x] [must] `AGENTS.md`, `coco/PROMPTS.md` started
- [ ] [must] Create trial (Enterprise, AWS US West 2), **add credit card to enable AI features**; confirm region/edition and which Cortex features are enabled (AI_COMPLETE / AI_EXTRACT, Cortex Search, Semantic Views, Cortex Agents, ML Anomaly Detection)

## Phase 1 — Idea & pitch ✅ CHECKPOINT 1
- [x] [must] `docs/PITCH.md` 7-slide outline with speaker notes
- [ ] [should] Rough deck visuals (convert to PDF in Phase 9)

## Phase 2 — Synthetic data ✅ CHECKPOINT 2
- [x] [must] `docs/DATA_MODEL.md`
- [x] [must] `generate.py` (seed=42): assets(12), sensor_readings(~310k), failure_modes(~10), technicians(8, 2 retiring), work_orders(~150, messy/Hinglish), handover_notes(~300), production_log, spare_parts(~40), asset_changes(~15)
- [x] [must] `scenario.py`: P3 bearing wear ×3 (Ravi: bearing + lube grade), junior bearing-only fix recurred in 9 days, final-day precursor, 2 decoys
- [x] [must] `answer_key.json`: expected cards, top-3 retrieval for golden anomaly, OEE for 3 asset-days
- [x] [must] `--verify` asserts scenario invariants

## Phase 3 — Snowflake foundation ✅ CHECKPOINT 3
- [x] [must] `00_setup.sql` (PLANT_BRAIN db; RAW/CORE/BRAIN/APP; PB_WH XS AUTO_SUSPEND=60; PB_ROLE; RAW.LANDING)
- [x] [must] `01_raw_tables.sql`, `02_load.sql` (PUT + COPY INTO)
- [x] [must] `03_core_views.sql`: CORE.OEE_DAILY, CORE.ASSET_HEALTH (+ OEE_LINE_DAILY)
- [ ] [must] Verify OEE for 3 asset-days within 0.5% of answer key (`snowflake/checks/phase3_checks.sql`, needs a live account)
- [x] [should] `docs/SNOWFLAKE_SETUP.md` runbook + `scripts/sf.py` runner + optional key-pair agent user

## Phase 4 — The Brain: knowledge cards ✅ CHECKPOINT 4
- [ ] [must] Check current docs for AI_EXTRACT / AI_COMPLETE structured output
- [ ] [must] `04_cards.sql`: BRAIN.CARDS with full schema
- [ ] [must] BRAIN.EDGES (card→asset, failure_mode, technician; card→card CONTRADICTS/SUPERSEDES)
- [ ] [must] Incremental extraction (Dynamic Table, or fallback proc + task); cache results
- [ ] [must] `coco/skills/card-extractor/SKILL.md`, usage logged in PROMPTS.md
- [ ] [must] Verify expected cards exist; Ravi's fix RESOLVED with correct excerpt

## Phase 5 — Anomaly & failure window ✅ CHECKPOINT 5
- [ ] [must] Rolling z-score + 6h slope (deterministic SQL) → BRAIN.ANOMALIES with signature vector
- [ ] [must] Failure window: linear extrapolation, low/high range, labeled as estimate
- [ ] [must] Pattern match vs historical pre-failure signatures
- [ ] [must] Verify: golden P3 detected on final day, matches 3 episodes; decoys don't match
- [ ] [stretch] SNOWFLAKE.ML.ANOMALY_DETECTION side-by-side

## Phase 6 — Search, semantic view, agent, actions ✅ CHECKPOINT 6
- [ ] [must] `06_search.sql`: BRAIN.CARD_SEARCH (filters asset_id, failure_mode, card_type, outcome; TARGET_LAG)
- [ ] [must] `07_semantic_view.sql` with ≥8 verified queries (fallback: Analyst YAML)
- [ ] [must] `08_procs.sql`: DRAFT_WORK_ORDER, APPROVE_WORK_ORDER, CLOSE_JOB
- [ ] [must] `coco/skills/work-order-drafter/SKILL.md`
- [ ] [must] `09_agent.sql`: Cortex Agent (search + analyst + draft tool), cite / refuse / never approve
- [ ] [should] Python orchestration fallback if Agents unavailable

## Phase 7 — Streamlit in Snowflake ✅ CHECKPOINT 7
- [ ] [must] Command Center page
- [ ] [must] Anomaly → Brain page (chart + overlays, cards, gotcha, failure window)
- [ ] [must] Work Order Approval page (Approve / Edit / Reject)
- [ ] [must] Close Job page, with the new card appearing (learning loop visible)
- [ ] [must] Ask the Plant chat with inline citations
- [ ] [must] `snow streamlit deploy`; document local and in-Snowflake runs

## Phase 8 — Evaluation ✅ CHECKPOINT 8
- [ ] [must] `golden_questions.yaml` (25 Qs: recall, gotcha, analytics, boundary)
- [ ] [must] `run_eval.py`: naive baseline vs Plant Brain
- [ ] [must] Metrics: hit@3, correctness, citation presence, correct refusals
- [ ] [must] Results into `docs/EVALUATION.md` and pitch slide 6, failures included

## Phase 9 — Docs, demo, submission ✅ FINAL CHECKPOINT
- [ ] [must] README complete (pitch, screenshot, Mermaid, ≤10-command quickstart, objects, CoCo usage, eval, synthetic notice, limitations)
- [ ] [must] ARCHITECTURE.md (diagram + learning loop + design decisions)
- [ ] [must] DEMO_SCRIPT.md (3 min, click by click)
- [ ] [must] Full quickstart from clean clone reproduces golden scenario and eval
- [ ] [stretch] Voice-note ingestion (`AI_TRANSCRIBE` if available)
- [ ] [stretch] Staleness alerts from `asset_changes`
- [ ] [stretch] Snowflake managed MCP server exposing the agent
- [ ] [stretch] Multi-plant rollout

## Submission checklist
- [ ] Repo public
- [ ] README complete
- [ ] Demo video ≤3 min
- [ ] Deck PDF
- [ ] Teardown script tested
- [ ] No secrets committed
