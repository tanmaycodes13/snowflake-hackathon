"""One-command Snowflake deploy (after 00_setup.sql has been run once as ACCOUNTADMIN).

    python scripts/deploy_snowflake.py            # load data + all objects + checks
    python scripts/deploy_snowflake.py --from 04  # resume from a step

Steps: 01 tables, 02 load, 03 core views, 04 cards (+ CALL EXTRACT_NEW_CARDS), 05 anomalies,
06 search, 07 semantic view, 08 procs, 09 agent, checks. Streamlit is deployed separately with
`snow streamlit deploy --project app --replace` (see JUMPSTART.md).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STEPS = [
    ("01", ["run", "snowflake/01_raw_tables.sql"]),
    ("02", ["run", "snowflake/02_load.sql"]),
    ("03", ["run", "snowflake/03_core_views.sql"]),
    ("04", ["run", "snowflake/04_cards.sql"]),
    ("04x", ["query", "CALL PLANT_BRAIN.BRAIN.EXTRACT_NEW_CARDS()"]),
    ("05", ["run", "snowflake/05_anomaly.sql"]),
    ("06", ["run", "snowflake/06_search.sql"]),
    ("07", ["run", "snowflake/07_semantic_view.sql"]),
    ("08", ["run", "snowflake/08_procs.sql"]),
    ("09", ["run", "snowflake/09_agent.sql"]),
    ("checks", ["run", "snowflake/checks/phase3_checks.sql", "snowflake/checks/brain_checks.sql"]),
]


def main():
    start = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "01"
    names = [s for s, _ in STEPS]
    if not (ROOT / "data_gen/out/sensor_readings.csv").exists():
        subprocess.check_call([PY, "data_gen/generate.py"], cwd=ROOT)
    subprocess.check_call([PY, "scripts/package_procs.py"], cwd=ROOT)
    subprocess.check_call([PY, "scripts/render_semantic_view.py", "--check"], cwd=ROOT)
    for name, args in STEPS[names.index(start):]:
        print(f"\n######## step {name}")
        subprocess.check_call([PY, "scripts/sf.py", *args], cwd=ROOT)
    print("\nDone. Next: snow streamlit deploy --project app --replace")


if __name__ == "__main__":
    main()
