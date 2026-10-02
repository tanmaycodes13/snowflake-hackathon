"""Pick the backend: Streamlit in Snowflake > PB_BACKEND=snowflake (local connector) > mock (default locally)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .core import PlantBrain

REPO = Path(__file__).resolve().parents[2]


def _load_dotenv():
    p = REPO / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def make_brain() -> tuple[PlantBrain, str]:
    _load_dotenv()
    mode = os.getenv("PB_BACKEND", "").lower()
    if mode != "mock":
        try:  # inside Streamlit in Snowflake
            from snowflake.snowpark.context import get_active_session
            from .db import Snowpark
            from .services import SnowflakeServices
            session = get_active_session()
            db = Snowpark(session)
            return PlantBrain(db, SnowflakeServices(db)), "Snowflake (Streamlit in Snowflake)"
        except Exception:
            if mode == "snowflake":
                import snowflake.connector
                from .db import SnowflakeConnector
                from .services import SnowflakeServices
                snowflake.connector.paramstyle = "qmark"
                kw = dict(account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
                          role=os.getenv("SNOWFLAKE_ROLE", "PB_ROLE"), warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "PB_WH"),
                          database="PLANT_BRAIN")
                if os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"):
                    kw.update(authenticator="SNOWFLAKE_JWT", private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])
                else:
                    kw.update(authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR", "externalbrowser"))
                db = SnowflakeConnector(snowflake.connector.connect(**kw))
                return PlantBrain(db, SnowflakeServices(db)), f"Snowflake ({os.environ['SNOWFLAKE_ACCOUNT']})"
    # local mock: DuckDB running the same SQL + mocked Cortex services
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from mocks import warehouse
    from mocks.services import MockServices
    from .db import DuckDB
    if not warehouse.DB_PATH.exists():
        warehouse.build(verbose=False)
    db = DuckDB(warehouse.connect())
    return PlantBrain(db, MockServices(db)), "Local mock (DuckDB + mocked Cortex)"
