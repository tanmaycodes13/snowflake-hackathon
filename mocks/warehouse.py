"""Mock Snowflake warehouse: DuckDB running the SAME SQL files as Snowflake.

The portable files (01 raw tables, 03 core views, 04 card views, 05 anomalies) are executed
verbatim after a small dialect shim, so local results check the Snowflake SQL itself rather
than a re-implementation.

    python -m mocks.warehouse            # build data_gen/out -> mocks/plant_brain.duckdb
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "mocks" / "plant_brain.duckdb"   # file name => catalog "plant_brain" (matches PLANT_BRAIN.*)
CSV_DIR = ROOT / "data_gen" / "out"
SQL_DIR = ROOT / "snowflake"

RAW_TABLES = ["assets", "failure_modes", "technicians", "spare_parts", "asset_changes",
              "work_orders", "handover_notes", "production_log", "sensor_readings"]

# Snowflake functions the portable SQL uses that DuckDB lacks, defined as macros.
MACROS = [
    "CREATE OR REPLACE MACRO div0(a, b) AS CASE WHEN b = 0 OR b IS NULL THEN 0 ELSE a / b END",
    "CREATE OR REPLACE MACRO iff(c, a, b) AS CASE WHEN c THEN a ELSE b END",
    """CREATE OR REPLACE MACRO dateadd(part, n, ts) AS CASE lower(part)
         WHEN 'day' THEN ts + to_days(CAST(n AS INTEGER))
         WHEN 'hour' THEN ts + to_hours(CAST(n AS INTEGER))
         WHEN 'minute' THEN ts + to_minutes(CAST(n AS INTEGER)) END""",
]


def translate(sql: str) -> list[str]:
    """Snowflake -> DuckDB for the portable subset. Returns executable statements."""
    out = []
    for stmt in split_statements(sql):
        s = stmt.strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith(("USE ROLE", "USE WAREHOUSE", "USE DATABASE", "PUT ", "COPY INTO",
                          "TRUNCATE", "GRANT ", "ALTER ", "CREATE TASK", "CREATE OR REPLACE TASK",
                          "CREATE OR REPLACE PROCEDURE", "CREATE PROCEDURE", "CALL ", "EXECUTE ",
                          "CREATE STAGE", "CREATE OR REPLACE CORTEX", "CREATE OR REPLACE SEMANTIC",
                          "CREATE OR REPLACE AGENT", "CREATE OR REPLACE STREAMLIT", "CREATE RESOURCE")):
            continue
        if up.startswith("USE SCHEMA"):
            s = "USE " + s.split(None, 2)[2].lower()
        s = re.sub(r"\s+COMMENT\s*=\s*'(?:[^']|'')*'", "", s)          # object comments
        s = re.sub(r"\bCLUSTER BY\s*\([^)]*\)", "", s, flags=re.I)
        s = re.sub(r"\bNUMBER\(", "DECIMAL(", s)
        s = re.sub(r"\bNUMBER\b", "BIGINT", s)
        s = re.sub(r"\bTIMESTAMP_NTZ\b", "TIMESTAMP", s)
        s = re.sub(r"\bVARIANT\b", "JSON", s)
        s = re.sub(r"\bCURRENT_TIMESTAMP\(\)", "CURRENT_TIMESTAMP", s)
        out.append(s)
    return out


def split_statements(sql: str) -> list[str]:
    """Split on ';' outside quotes, $$ blocks and -- comments."""
    stmts, buf, i, n = [], [], 0, len(sql)
    in_str = in_dollar = False
    while i < n:
        c = sql[i]
        if not in_str and not in_dollar and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue
        if not in_str and sql.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$"); i += 2
            continue
        if not in_dollar and c == "'":
            in_str = not in_str
        if c == ";" and not in_str and not in_dollar:
            stmts.append("".join(buf)); buf = []
        else:
            buf.append(c)
        i += 1
    stmts.append("".join(buf))
    return [s for s in stmts if s.strip()]


def run_file(con, path: Path):
    for s in translate(path.read_text()):
        try:
            con.execute(s)
        except Exception as e:  # surface the failing statement
            raise RuntimeError(f"{path.name}: {e}\n--- statement ---\n{s[:800]}") from e


def connect(path: Path = DB_PATH, read_only: bool = False):
    con = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        for m in MACROS:
            con.execute(m)
    con.execute("USE plant_brain")
    return con


PORTABLE_FILES = ["03_core_views.sql", "05_anomaly.sql", "04_cards.sql", "08_procs.sql"]


def build(path: Path = DB_PATH, verbose: bool = True) -> Path:
    """Fresh database: raw tables + CSVs + portable views/tables (cards are filled by mocks.cortex)."""
    if not (CSV_DIR / "sensor_readings.csv").exists():
        sys.exit("data_gen/out is empty. Run: python data_gen/generate.py")
    if path.exists():
        path.unlink()
    con = connect(path)
    for schema in ("raw", "core", "brain", "app"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    run_file(con, SQL_DIR / "01_raw_tables.sql")
    for t in RAW_TABLES:
        con.execute(f"INSERT INTO raw.{t} SELECT * FROM read_csv(?, header=true, nullstr='', "
                    f"auto_detect=true)", [str(CSV_DIR / f"{t}.csv")])
        if verbose:
            print(f"  raw.{t:16} {con.execute(f'SELECT COUNT(*) FROM raw.{t}').fetchone()[0]:>7}")
    for f in PORTABLE_FILES:
        if (SQL_DIR / f).exists():
            run_file(con, SQL_DIR / f)
            if verbose:
                print(f"  ran {f}")
    from . import cortex                      # mock of CALL BRAIN.EXTRACT_NEW_CARDS()
    n = cortex.run_extraction(con)
    if verbose:
        print(f"  mock card extraction: {n} sources -> "
              f"{con.execute('SELECT COUNT(*) FROM brain.cards').fetchone()[0]} cards")
    con.close()
    return path


if __name__ == "__main__":
    build()
    print(f"built {DB_PATH}")
