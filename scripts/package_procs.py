"""Zip app/plant_brain into build/plant_brain.zip for the Python stored procedures (08_procs.sql)."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "build" / "plant_brain.zip"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted((ROOT / "app" / "plant_brain").glob("*.py")):
        z.write(f, f"plant_brain/{f.name}")
print(f"wrote {out}")
