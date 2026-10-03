# JUMPSTART: Plant Brain from zero to running

Every step, in order: local mock run, then the full Snowflake deployment.
All data is **synthetic** (fictional plant, people and assets, generated with `seed=42`).

```
snowflake-hackathon/
├── app/                 ← CORE APPLICATION
│   ├── streamlit_app.py     5-page UI (runs in Streamlit in Snowflake or locally)
│   ├── plant_brain/         core logic: recall, drafting, approval, close-job loop, agent, DB adapters
│   ├── snowflake.yml        `snow streamlit deploy` project
│   └── environment.yml      Streamlit-in-Snowflake packages
├── snowflake/           ← every Snowflake object, run in numeric order (00 → 09), 99 = teardown, checks/
├── mocks/               ← local stand-ins for Snowflake services (DuckDB warehouse, Cortex extraction/search)
├── data_gen/            ← seeded synthetic data + golden scenario + answer key
├── eval/                ← 25 golden questions + Plant Brain vs naive baseline
├── scripts/             ← sf.py runner, deploy, checks, smoke test, packaging, semantic-view renderer
├── .cortex/skills/      ← CoCo CLI project skills: anomaly-triage, work-order-drafter, card-extractor
├── coco/                ← PROMPTS.md: how CoCo was used, phase by phase
└── docs/                ← pitch, data model, evaluation
```

---

## Path A: local run in ~5 minutes (no Snowflake account needed)

Needs Python 3.10+ and git.

```bash
# Clone and install (Windows: .venv\Scripts\activate)
git clone https://github.com/tanmaycodes13/snowflake-hackathon.git && cd snowflake-hackathon
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 9 CSVs + answer key; prints ALL CHECKS PASSED
python data_gen/generate.py && python data_gen/generate.py --verify

# DuckDB runs the real snowflake/*.sql + mock extraction
python -m mocks.warehouse

# 25 checks (OEE, cards, edges, anomalies, failure window), then the whole flow end to end
python scripts/run_checks.py
python scripts/smoke_test.py

# Open http://localhost:8501
PB_BACKEND=mock streamlit run app/streamlit_app.py
```

The same with make: `make setup test app`.

What runs locally, and what it stands in for: see `mocks/README.md`. In short, the **same SQL files** and the
**same application code** run on DuckDB, with rule-based card extraction and BM25 search in place of Cortex.

---

## Path B: full Snowflake deployment

### B1. Create the account (once)
1. Sign up at <https://signup.snowflake.com>: **Enterprise**, **AWS**, **US West 2 (Oregon)**. Oregon has the broadest
   native set of Cortex models.
2. **Add a credit card** (Admin → Billing → Payment method). AI features are disabled on self-service trials until
   a card is added. This does not end the trial or charge you while free credits remain.

### B2. Bootstrap (once, as ACCOUNTADMIN, in Snowsight)
Snowsight → Projects → Workspaces → new SQL file → paste `snowflake/00_setup.sql` → **Run All**.
It creates:
- role `PB_ROLE`
- warehouse `PB_WH` (XS, auto-suspend 60 s), guarded by a 20-credit/month monitor `PB_MONITOR`
- database `PLANT_BRAIN` with schemas `RAW` / `CORE` / `BRAIN` / `APP`
- stage `RAW.LANDING`
- Cortex grants, plus cross-region inference enabled

The last result row is your **account identifier** (`ORGNAME-ACCOUNTNAME`).

### B3. Connect your terminal
Choose one, then `cp .env.example .env` and fill it in (`.env` is gitignored):

| Option | `.env` | Notes |
|---|---|---|
| Your own user, browser SSO | `SNOWFLAKE_ACCOUNT=…`, `SNOWFLAKE_USER=…`, `SNOWFLAKE_AUTHENTICATOR=externalbrowser` | Simplest on a laptop |
| Key-pair service user (for an agent/CI) | `SNOWFLAKE_ACCOUNT=…`, `SNOWFLAKE_USER=PB_SVC`, `SNOWFLAKE_PRIVATE_KEY_PATH=/path/key.p8` | Run `snowflake/00b_agent_user.sql` with your public key (**Run All**, not Run) |

Test it:
```bash
python scripts/sf.py query "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_REGION()"
python scripts/sf.py query "SELECT AI_COMPLETE('claude-haiku-4-5', 'Reply with OK')"
```
If the model call fails, pick a model available to you (for example `llama3.3-70b`) and `export PB_MODEL=llama3.3-70b`.

### B4. Deploy everything (one command, ~5–10 min)
```bash
python scripts/deploy_snowflake.py
```
If a step fails, fix it and resume from that step: `python scripts/deploy_snowflake.py --from 05`.

| Step | File | Creates | Check |
|---|---|---|---|
| 01 | `01_raw_tables.sql` | 9 RAW tables | |
| 02 | `02_load.sql` | `PUT` the CSVs to `@RAW.LANDING`, `COPY INTO` | row counts 12 / 10 / 8 / 40 / 15 / 144 / 295 / 2690 / 311040 |
| 03 | `03_core_views.sql` | `CORE.OEE_DAILY`, `CORE.OEE_LINE_DAILY`, `CORE.ASSET_HEALTH` | OEE = answer key |
| 04 | `04_cards.sql` | `BRAIN.CARD_SOURCES`, `CARDS_RAW`, `CARD_EXTRACT_LOG`, proc `EXTRACT_NEW_CARDS` (Cortex `AI_COMPLETE` + JSON schema), task (suspended), views `BRAIN.CARDS`, `BRAIN.EDGES` | |
| 04x | `CALL BRAIN.EXTRACT_NEW_CARDS()` | ~439 sources → cards, **once** (cached by text hash) | C1–C12 present |
| 05 | `05_anomaly.sql` | `SENSOR_HOURLY`, `SENSOR_SCORES`, `ANOMALY_HOURS`, `ANOMALIES`, `PREFAILURE_EPISODES`, `ANOMALY_MATCHES`, `FAILURE_WINDOWS` | 3 active; P3 matches E1/E2/E3 |
| 06 | `06_search.sql` | Cortex Search `BRAIN.CARD_SEARCH` over `BRAIN.CARD_SEARCH_DOCS` (a change-tracked copy of `BRAIN.CARDS`, refreshed after every extraction) | smoke query returns HN-0163 cards |
| 07 | `07_semantic_view.sql` | semantic view `CORE.PLANT_SEMANTIC_VIEW` with 10 verified queries | |
| 08 | `08_procs.sql` | `APP.WORK_ORDER_DRAFTS`, stage `APP.CODE` (+ `plant_brain.zip`), Python procs `DRAFT_WORK_ORDER`, `APPROVE_WORK_ORDER`, `REJECT_WORK_ORDER`, `CLOSE_JOB`, `RESET_DEMO` | |
| 09 | `09_agent.sql` | Cortex Agent `APP.PLANT_BRAIN_AGENT` (CardSearch + PlantAnalytics + DraftWorkOrder) | |
| checks | `checks/*.sql` | | every row PASS |

Re-run only the checks: `python scripts/run_checks.py --snowflake`.

### B5. Deploy the app to Streamlit in Snowflake
```bash
pip install snowflake-cli
# Name it plant_brain; same account/user/auth as .env
snow connection add
snow streamlit deploy --project app --replace --connection plant_brain
```
Open Snowsight → Projects → Streamlit → **PLANT_BRAIN_APP**. The app detects it is inside Snowflake and uses the
live backend automatically. To run the UI locally against Snowflake instead: `PB_BACKEND=snowflake streamlit run app/streamlit_app.py`.

### B6. Try the agent and the procedures
- Snowsight → AI & ML → Agents → **PLANT_BRAIN_AGENT** (Snowflake Intelligence): "How was P3's bearing issue fixed before?"
- SQL: `CALL PLANT_BRAIN.APP.DRAFT_WORK_ORDER('A-P3-2026083104');` then approve in the app (only a human can approve).

### B7. Evaluate on Cortex
```bash
# Rewrites docs/EVALUATION.md with live Cortex numbers
python eval/run_eval.py --snowflake --write
```
Then update the evaluation summary in `README.md` with the new numbers.

### B8. Teardown
Snowsight (ACCOUNTADMIN): run `snowflake/99_teardown.sql`. This drops the database, warehouse, monitor, `PB_SVC` and `PB_ROLE`.

---

## Verification status
| Piece | Verified how |
|---|---|
| Data generator + golden scenario | `generate.py --verify`, byte-identical regeneration |
| Full Snowflake deployment (`00`–`09`) | Run on a live trial account (AWS US West 2); `python scripts/run_checks.py --snowflake`: all 25 checks PASS, including cards C1–C12 extracted by Cortex `AI_COMPLETE` |
| Portable SQL (`01`, `03`, `04` views, `05`, `08` table) | Also executed verbatim on DuckDB by `mocks/warehouse.py`; all 25 checks pass locally |
| App, workflow, agent routing, eval | `scripts/smoke_test.py`, headless browser run of all 5 pages, `eval/run_eval.py` (mock) |

## Troubleshooting
| Symptom | Fix |
|---|---|
| `JWT token is invalid` | `DESC USER PB_SVC;` and compare `RSA_PUBLIC_KEY_FP` with `openssl rsa -pubin -in key.pub -outform DER \| openssl dgst -sha256 -binary \| openssl enc -base64`. Re-run `00b_agent_user.sql` with **Run All**. |
| AI functions disabled / not authorized | Add a credit card (B1.2); check `GRANT USE AI FUNCTIONS` + `CORTEX_USER` ran (00_setup). |
| Model unavailable | `CORTEX_ENABLED_CROSS_REGION` (set in 00_setup) or `export PB_MODEL=<available model>`; `CALL BRAIN.EXTRACT_NEW_CARDS('<model>');` |
| `PUT` fails in Snowsight | PUT needs a client: use `scripts/sf.py`/the deploy script, or upload the CSVs via Snowsight → stage → **+ Files** and run `02_load.sql` from `TRUNCATE`. |
| Semantic view or agent DDL errors | The app does not depend on them (Ask the Plant uses the same verified queries + search directly). Fix the DDL and re-run step 07/09. |
| New card not in search right after Close Job | Cortex Search refreshes on `TARGET_LAG = '1 hour'`. The Close Job page reads `BRAIN.CARDS` directly, so the app is unaffected. |
| Mock DB locked | Stop other Streamlit/Python processes using `mocks/plant_brain.duckdb`, or `make clean mock`. |

## Cost (trial credits)
- XS warehouse ≈ 1 credit per running hour, suspending after 60 s; the whole deploy is well under 1 credit of compute.
- Card extraction is ~439 short `AI_COMPLETE` calls, **once** (cached); each Close Job extracts 1 new source.
- Cortex Search: small index, `TARGET_LAG = 1 hour`. The card-extraction task is created **suspended**.
