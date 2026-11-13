"""Resume the locked fresh comparison after the global audit completes."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")


def main():
    output = ROOT/"outputs/t1/aligned_refit_20261112"
    print("Waiting for frozen global artifact and independent audit",flush=True)
    while not (output/"audit_results.json").exists():
        time.sleep(5)
    def command(script,*args):
        return subprocess.run([sys.executable,"-X","utf8",str(ROOT/"experiments/t1_compact"/script),"--output",str(output),*args],check=True)
    command("compare_adaptation.py","--prepare")
    from experiments.t1_compact.compare_adaptation import execution_protocol
    execution_protocol(output)
    inventory=json.loads((output/"fresh_inventory.json").read_text(encoding="utf-8"))
    worlds=[e["name"] for e in inventory if e["role"]=="fresh_test"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(command,"compare_adaptation.py","--world",world) for world in worlds]
        for job in concurrent.futures.as_completed(jobs):
            job.result()
    command("compare_adaptation.py","--summarize")
    command("verify_refit_comparison.py")
    command("verify_refit_runtime.py")


if __name__=="__main__":
    main()
