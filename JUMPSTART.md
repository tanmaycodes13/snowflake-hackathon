# JUMPSTART: Plant Brain from zero to demo

Every step, in order: local mock demo, then the full Snowflake deployment, then demo day.
All data is **synthetic** (fictional plant, people and assets, generated with `seed=42`).

```
plant-brain/
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
├── coco/                ← CoCo skills (card-extractor, work-order-drafter) + PROMPTS.md log
└── docs/                ← pitch, demo script, data model, evaluation, Snowflake setup notes
```

---

## Path A: local demo in ~5 minutes (no Snowflake account needed)

Needs Python 3.10+ and git.

```bash
git clone https://github.com/tanmaycodes13/snowflake-hackathon.git plant-brain && cd plant-brain
python3 -m venv .venv && source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python data_gen/generate.py && python data_gen/generate.py --verify   # 9 CSVs + answer key; ALL CHECKS PASSED
python -m mocks.warehouse                                   # DuckDB runs the real snowflake/*.sql + mock extraction
python scripts/run_checks.py                                # 25 checks: OEE, cards, edges, anomalies, failure window
python scripts/smoke_test.py                                # whole demo flow end to end
PB_BACKEND=mock streamlit run app/streamlit_app.py          # open http://localhost:8501
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
python scripts/deploy_snowflake.py           # resume with --from 05 etc. if a step fails
```

| Step | File | Creates | Check |
|---|---|---|---|
| 01 | `01_raw_tables.sql` | 9 RAW tables | |
| 02 | `02_load.sql` | `PUT` the CSVs to `@RAW.LANDING`, `COPY INTO` | row counts 12 / 10 / 8 / 40 / 15 / 144 / 295 / 2690 / 311040 |
| 03 | `03_core_views.sql` | `CORE.OEE_DAILY`, `CORE.OEE_LINE_DAILY`, `CORE.ASSET_HEALTH` | OEE = answer key |
| 04 | `04_cards.sql` | `BRAIN.CARD_SOURCES`, `CARDS_RAW`, `CARD_EXTRACT_LOG`, proc `EXTRACT_NEW_CARDS` (Cortex `AI_COMPLETE` + JSON schema), task (suspended), views `BRAIN.CARDS`, `BRAIN.EDGES` | |
| 04x | `CALL BRAIN.EXTRACT_NEW_CARDS()` | ~439 sources → cards, **once** (cached by text hash) | C1–C12 present |
| 05 | `05_anomaly.sql` | `SENSOR_HOURLY`, `SENSOR_SCORES`, `ANOMALY_HOURS`, `ANOMALIES`, `PREFAILURE_EPISODES`, `ANOMALY_MATCHES`, `FAILURE_WINDOWS` | 3 active; P3 matches E1/E2/E3 |
| 06 | `06_search.sql` | Cortex Search `BRAIN.CARD_SEARCH` | smoke query returns HN-0163 cards |
| 07 | `07_semantic_view.sql` | semantic view `CORE.PLANT_SEMANTIC_VIEW` with 10 verified queries | |
| 08 | `08_procs.sql` | `APP.WORK_ORDER_DRAFTS`, stage `APP.CODE` (+ `plant_brain.zip`), Python procs `DRAFT_WORK_ORDER`, `APPROVE_WORK_ORDER`, `REJECT_WORK_ORDER`, `CLOSE_JOB`, `RESET_DEMO` | |
| 09 | `09_agent.sql` | Cortex Agent `APP.PLANT_BRAIN_AGENT` (CardSearch + PlantAnalytics + DraftWorkOrder) | |
| checks | `checks/*.sql` | | every row PASS |

Re-run only the checks: `python scripts/run_checks.py --snowflake`.

### B5. Deploy the app to Streamlit in Snowflake
```bash
pip install snowflake-cli
snow connection add                                   # name it plant_brain; same account/user/auth as .env
snow streamlit deploy --project app --replace --connection plant_brain
```
Open Snowsight → Projects → Streamlit → **PLANT_BRAIN_APP**. The app detects it is inside Snowflake and uses the
live backend automatically. To run the UI locally against Snowflake instead: `PB_BACKEND=snowflake streamlit run app/streamlit_app.py`.

### B6. Try the agent and the procedures
- Snowsight → AI & ML → Agents → **PLANT_BRAIN_AGENT** (Snowflake Intelligence): "How was P3's bearing issue fixed before?"
- SQL: `CALL PLANT_BRAIN.APP.DRAFT_WORK_ORDER('A-P3-2026083104');` then approve in the app (only a human can approve).

### B7. Evaluate on Cortex
```bash
python eval/run_eval.py --snowflake --write        # rewrites docs/EVALUATION.md with live Cortex numbers
```
Copy the table into `docs/PITCH.md` slide 6 and the deck.

### B8. Teardown
Snowsight (ACCOUNTADMIN): run `snowflake/99_teardown.sql`. This drops the database, warehouse, monitor, `PB_SVC` and `PB_ROLE`.

---

## Path C: demo day
1. Click **Reset demo** in the app sidebar (or `CALL PLANT_BRAIN.APP.RESET_DEMO();`).
2. Follow `docs/DEMO_SCRIPT.md`: 3 minutes, click by click, with copy-paste inputs.
3. Open every page once beforehand, so the warehouse is warm.
4. Keep the local mock running as a backup: `make app` shows the identical flow offline.

---

## Verification status (be honest with judges)
| Piece | Verified how |
|---|---|
| Data generator + golden scenario | `generate.py --verify`, byte-identical regeneration |
| `01`, `03`, `04` (views), `05`, `08` (table) SQL | executed verbatim on DuckDB by `mocks/warehouse.py`; all 25 checks pass |
| App, workflow, agent routing, eval | `scripts/smoke_test.py`, headless browser run of all 5 pages, `eval/run_eval.py` (mock) |
| `00_setup`, `02_load` (PUT/COPY), `04` Cortex proc, `06` search, `07` semantic view, `08` Python procs, `09` agent, Streamlit deploy | Written against current Snowflake docs. **Not yet executed on a live account.** Run B4 and fix anything that errors. |

## Troubleshooting
| Symptom | Fix |
|---|---|
| `JWT token is invalid` | `DESC USER PB_SVC;` and compare `RSA_PUBLIC_KEY_FP` with `openssl rsa -pubin -in key.pub -outform DER \| openssl dgst -sha256 -binary \| openssl enc -base64`. Re-run `00b_agent_user.sql` with **Run All**. |
| AI functions disabled / not authorized | Add a credit card (B1.2); check `GRANT USE AI FUNCTIONS` + `CORTEX_USER` ran (00_setup). |
| Model unavailable | `CORTEX_ENABLED_CROSS_REGION` (set in 00_setup) or `export PB_MODEL=<available model>`; `CALL BRAIN.EXTRACT_NEW_CARDS('<model>');` |
| `PUT` fails in Snowsight | PUT needs a client: use `scripts/sf.py`/the deploy script, or upload the CSVs via Snowsight → stage → **+ Files** and run `02_load.sql` from `TRUNCATE`. |
| Semantic view or agent DDL errors | The app does not depend on them (Ask the Plant uses the same verified queries + search directly). Fix the DDL and re-run step 07/09. |
| New card not in search right after Close Job | Cortex Search refreshes on `TARGET_LAG = '1 hour'`. The Close Job page reads `BRAIN.CARDS` directly, so the demo is unaffected. |
| Mock DB locked | Stop other Streamlit/Python processes using `mocks/plant_brain.duckdb`, or `make clean mock`. |

## Cost (trial credits)
- XS warehouse ≈ 1 credit per running hour, suspending after 60 s; the whole deploy is well under 1 credit of compute.
- Card extraction is ~439 short `AI_COMPLETE` calls, **once** (cached); each Close Job extracts 1 new source.
- Cortex Search: small index, `TARGET_LAG = 1 hour`. The card-extraction task is created **suspended**.
