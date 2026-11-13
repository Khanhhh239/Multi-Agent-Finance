"""Wait for all independent context receipts, then verify and publish once."""
from pathlib import Path
import sys
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.t1_compact.refit_landmark import load_role
from experiments.t1_compact.compare_adaptation import COMPARISON


if __name__=="__main__":
    output=ROOT/"outputs/t1/aligned_refit_20261112"
    frame=load_role(output,"fresh_test")
    receipts=[output/COMPARISON/w/f/str(o.date())/"receipt.json" for w,f,o in frame.groupby(["world","firm","origin"]).groups]
    print(f"Waiting for {len(receipts)} context receipts",flush=True)
    while not all(p.exists() for p in receipts): time.sleep(5)
    for script,args in [("compare_adaptation.py",["--summarize"]),("verify_refit_comparison.py",[]),
                        ("verify_refit_runtime.py",[]),("write_refit_report.py",[])]:
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"experiments/t1_compact"/script),"--output",str(output),*args],check=True)
