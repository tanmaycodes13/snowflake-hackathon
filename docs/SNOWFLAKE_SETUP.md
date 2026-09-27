# Snowflake setup runbook

Getting from zero to a loaded `PLANT_BRAIN` database. Takes about 15 minutes, and Phase 3 costs well under 1 credit.

## 1. Create the account
1. Sign up for a trial at <https://signup.snowflake.com>.
   - **Edition:** Enterprise.
   - **Cloud:** AWS.
   - **Region:** **US West 2 (Oregon)**. Per the Cortex [regional availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability) page, it hosts the widest set of Cortex models natively. `00_setup.sql` also enables cross-region inference as a safety net.
2. **Add a credit card** (Snowsight → Admin → Billing → Payment method → + Credit Card).
   - Per the [trial account docs](https://docs.snowflake.com/en/user-guide/admin-trial-account), *AI features are disabled on self-service trials until a card is added*.
   - Adding a card does **not** upgrade the account or end the trial. You keep spending free credits first.
   - Without a card, Phase 4 onwards (Cortex AI SQL, Search, Agents) will not work.

## 2. Bootstrap (as ACCOUNTADMIN, in Snowsight)
1. Open Snowsight → **Projects → Workspaces** (or Worksheets) → new SQL file.
2. Paste the contents of [`snowflake/00_setup.sql`](../snowflake/00_setup.sql), then **Run All**.
3. The last result row shows your **account identifier** (`ORGNAME-ACCOUNTNAME`) and region.

`00_setup.sql` creates:
- role `PB_ROLE`
- warehouse `PB_WH` (XS, auto-suspend 60 s), guarded by resource monitor `PB_MONITOR` (20 credits/month, then suspend)
- database `PLANT_BRAIN` with schemas `RAW` / `CORE` / `BRAIN` / `APP`
- stage `RAW.LANDING` and file format `RAW.CSV_FF`
- Cortex privileges for the role

It also grants `PB_ROLE` to you.

## 3a. Option A: let the coding agent connect (recommended, fastest)
1. The agent generates an RSA key pair in its own session and gives you **only the public key**.
2. Run [`snowflake/00b_agent_user.sql`](../snowflake/00b_agent_user.sql) with that public key pasted in. This creates service user `PB_SVC`, which can only log in with key-pair auth and only holds `PB_ROLE`.
3. Tell the agent your account identifier. It's not a secret. Never paste passwords or private keys into chat.
4. The agent then runs everything from `01_raw_tables.sql` onwards and verifies each phase itself.
5. **To revoke access at any time:** `DROP USER PB_SVC;`

## 3b. Option B: run it yourself

**From a terminal (needs Python 3.10+):**
```bash
python data_gen/generate.py                 # writes data_gen/out/*.csv
pip install -r requirements.txt
cp .env.example .env                        # set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER (browser SSO)
python scripts/sf.py run snowflake/01_raw_tables.sql snowflake/02_load.sql \
                         snowflake/03_core_views.sql snowflake/checks/phase3_checks.sql
```

**Snowsight only (no terminal for SQL):**
1. Generate the CSVs locally with `python data_gen/generate.py`.
2. Snowsight → Data → Databases → PLANT_BRAIN → RAW → Stages → **LANDING** → **+ Files**. Upload all 9 files from `data_gen/out/`.
3. Run `01_raw_tables.sql` in a worksheet.
4. Run `02_load.sql` **from the `TRUNCATE` section onwards**. Snowsight can't run `PUT`.
5. Run `03_core_views.sql`.
6. Run `snowflake/checks/phase3_checks.sql`. Every row must say **PASS**.

## Cost notes
- XS warehouse ≈ 1 credit per running hour, and it suspends after 60 s idle. Loading 311k rows takes seconds.
- Cortex AI functions are billed per token. Phase 4 extracts cards from about 440 short texts **once**, then caches them in `BRAIN.CARDS`.
- Track spend in Snowsight → Admin → Cost management.

## Teardown
`snowflake/99_teardown.sql` (written in Phase 9) drops everything this project created.
