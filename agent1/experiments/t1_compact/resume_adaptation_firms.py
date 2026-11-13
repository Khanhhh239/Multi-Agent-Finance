"""Six independent groups; no two workers own the same company."""
import concurrent.futures
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
GROUPS=[("refit_04_fresh_test","F013,F015,F017"),("refit_04_fresh_test","F019,F026,F032"),
        ("refit_05_fresh_test","F007,F008,F018"),("refit_05_fresh_test","F021,F023,F030"),
        ("refit_06_fresh_test","F005,F008,F010"),("refit_06_fresh_test","F027,F032,F036")]


if __name__=="__main__":
    def run(group):
        world,firms=group
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"experiments/t1_compact/run_adaptation_firms.py"),
                        "--world",world,"--firms",firms],check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run,GROUPS))
