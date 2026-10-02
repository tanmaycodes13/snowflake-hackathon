"""Thin database adapters with one interface: query(sql, params) -> list[dict], execute(sql, params).

All SQL in plant_brain uses '?' placeholders and fully qualified PLANT_BRAIN.<schema>.<object>
names, which work unchanged on Snowflake (connector with qmark, or Snowpark) and on DuckDB.
"""
from __future__ import annotations

from decimal import Decimal


def _norm(v):
    return float(v) if isinstance(v, Decimal) else v


class DB:
    kind = "base"

    def query(self, sql: str, params=None) -> list[dict]:
        raise NotImplementedError

    def execute(self, sql: str, params=None) -> None:
        self.query(sql, params)

    def scalar(self, sql: str, params=None):
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None


class DuckDB(DB):
    kind = "duckdb"

    def __init__(self, con):
        self.con = con

    def query(self, sql, params=None):
        cur = self.con.cursor().execute(sql, params or [])   # cursor per call: safe across Streamlit threads
        if cur.description is None:
            return []
        cols = [d[0].lower() for d in cur.description]
        return [{c: _norm(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


class SnowflakeConnector(DB):
    """snowflake.connector connection created with paramstyle='qmark'."""
    kind = "snowflake"

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or None)
            if cur.description is None:
                return []
            cols = [d[0].lower() for d in cur.description]
            return [{c: _norm(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        finally:
            cur.close()


class Snowpark(DB):
    """Snowpark session: inside Streamlit in Snowflake and inside Python stored procedures."""
    kind = "snowflake"

    def __init__(self, session):
        self.session = session

    def query(self, sql, params=None):
        rows = self.session.sql(sql, params=list(params) if params else None).collect()
        return [{k.lower(): _norm(v) for k, v in r.as_dict().items()} for r in rows]
