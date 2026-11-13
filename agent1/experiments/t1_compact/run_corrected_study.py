"""Repeat the locked study with repaired targets, reusing unchanged Workspace fits."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.t1_compact.build_corrected_study import initialize,copy_role,copy_local,PARENT,CORRECTED
from experiments.t1_compact.refit_landmark import sample_risk,load_role,OLD
from experiments.t1_compact.compare_adaptation import execution_protocol,COMPARISON
from experiments.t1_compact.resume_adaptation_firms import GROUPS


if __name__=="__main__":
    output=initialize()
    def command(script,*args):
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"experiments/t1_compact"/script),"--output",str(output),*args],check=True)
    for role in ("train","validation","weight_validation"):copy_role(output,role)
    command("refit_landmark.py","--phase","train")
    command("refit_landmark.py","--phase","audit")
    copy_role(output,"fresh_test")
    # Workspace uses its own actual-cash chronological targets; its dated input
    # and training code did not change. Verify and reuse those fitted bundles.
    frame=load_role(output,"fresh_test")
    receipts=[PARENT/COMPARISON/w/f/str(o.date())/"receipt.json" for w,f,o in frame.groupby(["world","firm","origin"]).groups]
    while not all(p.exists() for p in receipts):time.sleep(5)
    copy_local(output)
    x,y,w=sample_risk(load_role(output,"train"),4096)
    np.savez_compressed(output/"current_global_replay.npz",x=x,y=y,weights=w)
    if not (output/"serving_artifact").exists():shutil.copytree(OLD,output/"serving_artifact")
    execution_protocol(output)
    groups=[*GROUPS,("refit_07_fresh_test_onboarding","F000,F005,F031,F035,F037,F038")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        jobs=[pool.submit(command,"run_adaptation_firms.py","--world",world,"--firms",firms) for world,firms in groups]
        for job in concurrent.futures.as_completed(jobs):job.result()
    for script,args in [("compare_adaptation.py",["--summarize"]),("verify_refit_comparison.py",[]),
                        ("verify_refit_runtime.py",[]),("write_refit_report.py",[])]:command(script,*args)
