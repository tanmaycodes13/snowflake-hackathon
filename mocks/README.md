# mocks/: local stand-ins for the Snowflake services

Lets the whole demo run on a laptop with no Snowflake account, using the same SQL and the same
application code. Used by `make app`, `scripts/run_checks.py`, `scripts/smoke_test.py` and `eval/run_eval.py`.

| Snowflake service (real) | Mock | How faithful |
|---|---|---|
| Virtual warehouse running `snowflake/01, 03, 04, 05, 08` | `warehouse.py`: DuckDB executes **those exact files** after a small dialect shim (`DIV0`, `IFF`, `DATEADD` macros; type names) | Same SQL; results checked against `answer_key.json` |
| `AI_COMPLETE` card extraction (`BRAIN.EXTRACT_NEW_CARDS`) | `cortex.py`: deterministic rules from `coco/skills/card-extractor/SKILL.md` | Same output table and incremental log; much less flexible than an LLM |
| Cortex Search `BRAIN.CARD_SEARCH` | `search.py`: BM25 + shop-floor synonym map, same request/response shape as `SEARCH_PREVIEW` | Keyword-only (Cortex is hybrid vector + keyword) |
| Cortex Analyst / semantic view | none needed: the verified queries (`app/plant_brain/verified_queries.py`) run directly | Same SQL as the semantic view's verified queries |
| `AI_COMPLETE` answer writing | template answer in `app/plant_brain/agent.py` | No LLM phrasing; citations identical |
| Python stored procedures (`APP.DRAFT_WORK_ORDER`, …) | the same `plant_brain.core` functions called directly | Identical code |

Build: `python -m mocks.warehouse` → `mocks/plant_brain.duckdb` (gitignored, ~3 s).
The file name makes DuckDB's catalog `plant_brain`, so fully qualified `PLANT_BRAIN.<schema>.<object>` names work unchanged.
