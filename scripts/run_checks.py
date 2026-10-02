"""Run the check SQL files against the mock (default) or Snowflake and fail on any FAIL row.

    python scripts/run_checks.py                  # mock (DuckDB), builds it if needed
    python scripts/run_checks.py --snowflake      # live account via scripts/sf.py settings (.env)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
FILES = ["snowflake/checks/phase3_checks.sql", "snowflake/checks/brain_checks.sql"]


def main():
    if "--snowflake" in sys.argv:
        sys.path.insert(0, str(ROOT / "scripts"))
        import snowflake.connector
        from sf import connect
        conn = connect()
        def q(sql):
            cur = conn.cursor(); cur.execute(sql); return cur.fetchall()
        from mocks.warehouse import split_statements
        stmts = [s for f in FILES for s in split_statements((ROOT / f).read_text())]
    else:
        from mocks import warehouse
        if not warehouse.DB_PATH.exists():
            warehouse.build(verbose=False)
        con = warehouse.connect()
        q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
        stmts = [s for f in FILES for s in warehouse.translate((ROOT / f).read_text())]
    fails = 0
    for s in stmts:
        if not s.strip().upper().startswith(("WITH", "SELECT")):
            if "--snowflake" in sys.argv:
                q(s)
            continue
        for name, result, detail in q(s):
            print(f"  {result:4}  {name}  ({detail})")
            fails += result != "PASS"
    print(f"\n{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
