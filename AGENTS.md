# AGENTS.md — instructions for any coding agent in this repo

**Project:** Plant Brain, a maintenance memory for a (fictional) factory. Snowflake CoCo CLI Hackathon 2026 – GCC, Track 3. Deadline 4 Oct 2026.

## Ground rules
1. **Synthetic data only.** Never add real company, person, or asset data.
2. **Snowflake-native, GA features only.** Before writing any Cortex / AI SQL / Cortex Search / Semantic View / Cortex Agent syntax, check the current Snowflake docs. Never invent syntax. If a feature is unavailable, use the documented fallback (see `TODO.md` and the master prompt) and say so.
3. **Deterministic.** All randomness is seeded (`seed=42`). The golden scenario (P3 bearing wear) must reproduce identically on every run. `python data_gen/generate.py --verify` must pass.
4. **Cost discipline.** Use warehouse `PB_WH` (XS, `AUTO_SUSPEND=60`). Run LLM functions on the fewest rows possible, cache results in tables, and never re-extract unchanged rows.
5. **No secrets in git.** Use `.env` (gitignored) and `~/.snowflake/connections.toml`. Update `.env.example` when adding config.
6. **Human in the loop.** Nothing, whether the agent, a proc, or the UI, may approve a work order without a human approver.
7. **Log CoCo usage** in `coco/PROMPTS.md`: prompt, what CoCo produced, and what was changed.
8. **Keep `TODO.md` current** and commit after every phase.

## Layout
- `app/`: **core application**: `streamlit_app.py` + `plant_brain/` package (also imported by the Snowflake stored procedures)
- `snowflake/NN_*.sql`: run in numeric order; `99_teardown.sql` removes everything; `checks/` = portable PASS/FAIL checks
- `mocks/`: local stand-ins for Snowflake services. Keep SQL in `01/03/04/05/08` portable so DuckDB can run it verbatim
- `data_gen/`: synthetic data generator, golden scenario, answer key
- `eval/`: golden questions and evaluation harness
- `scripts/`: runner, deploy, checks, smoke test, packaging, semantic-view renderer
- `coco/skills/`: CoCo skills (card-extractor, work-order-drafter)

## Before you commit
`make test` (data verify, semantic-view freshness, 25 checks, smoke test, eval) must pass.

## Snowflake object naming
Database `PLANT_BRAIN`; schemas `RAW` (landed data), `CORE` (OEE/health views), `BRAIN` (cards, edges, anomalies, search), `APP` (procs, drafts, UI-facing objects). Role `PB_ROLE`. Stage `RAW.LANDING`.
