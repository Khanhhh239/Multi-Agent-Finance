import sys
sys.path.insert(0, ".")
from pathlib import Path
from agent2 import external
Path("work/results").mkdir(parents=True, exist_ok=True)
print("== DFKI", flush=True)
external.run_dfki(Path("work/results/external_dfki.json"))
print("== ERP", flush=True)
external.run_erp(Path("work/results/external_erp.json"))
