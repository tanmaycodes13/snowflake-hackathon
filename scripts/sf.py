"""Tiny Snowflake runner for Plant Brain (run from repo root).

    python scripts/sf.py run snowflake/01_raw_tables.sql snowflake/02_load.sql ...
    python scripts/sf.py query "SELECT * FROM PLANT_BRAIN.CORE.ASSET_HEALTH"

Connection (first match wins):
  1. SNOWFLAKE_CONNECTION_NAME -> named connection in ~/.snowflake/connections.toml
  2. SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER + SNOWFLAKE_PRIVATE_KEY_PATH (key-pair auth)
  3. SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER + SNOWFLAKE_AUTHENTICATOR=externalbrowser
Values can live in a local .env (gitignored).
"""
import os
import sys
from io import StringIO
from pathlib import Path

import snowflake.connector


def load_dotenv(path=".env"):
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def connect():
    load_dotenv()
    common = dict(role=os.getenv("SNOWFLAKE_ROLE", "PB_ROLE"),
                  warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "PB_WH"),
                  database=os.getenv("SNOWFLAKE_DATABASE", "PLANT_BRAIN"))
    if os.getenv("SNOWFLAKE_CONNECTION_NAME") and not os.getenv("SNOWFLAKE_ACCOUNT"):
        return snowflake.connector.connect(connection_name=os.environ["SNOWFLAKE_CONNECTION_NAME"], **common)
    kw = dict(account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"], **common)
    if os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"):
        kw.update(authenticator="SNOWFLAKE_JWT", private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])
    else:
        kw.update(authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR", "externalbrowser"))
    return snowflake.connector.connect(**kw)


def show(cur, max_rows=60):
    if cur.description is None:
        return
    cols = [d[0] for d in cur.description]
    rows = cur.fetchmany(max_rows)
    if not rows:
        return
    fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)  # noqa: E731
    table = [cols] + [[fmt(v) for v in r] for r in rows]
    widths = [min(60, max(len(r[i]) for r in table)) for i in range(len(cols))]
    for i, r in enumerate(table):
        print("  " + " | ".join(c[:60].ljust(w) for c, w in zip(r, widths)))
        if i == 0:
            print("  " + "-+-".join("-" * w for w in widths))


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("run", "query"):
        sys.exit(__doc__)
    conn = connect()
    try:
        if sys.argv[1] == "query":
            cur = conn.cursor()
            cur.execute(" ".join(sys.argv[2:]))
            show(cur)
            return
        for f in sys.argv[2:]:
            print(f"\n=== {f}")
            for cur in conn.execute_stream(StringIO(Path(f).read_text()), remove_comments=True):
                first = (cur.query or "").strip().splitlines()[0][:100]
                print(f"-- ok: {first}")
                show(cur)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
