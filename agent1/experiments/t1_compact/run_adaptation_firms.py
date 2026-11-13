"""Precompute disjoint tenant groups through the unchanged comparison code."""
import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from threadpoolctl import threadpool_limits
from agent1.adaptive.compact_t1 import sha256
from experiments.t1_compact import compare_adaptation as comparison
from experiments.t1_compact.aligned_data import write


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--world",required=True)
    parser.add_argument("--firms",required=True)
    parser.add_argument("--output",type=Path,default=ROOT/"outputs/t1/aligned_refit_20261112")
    args=parser.parse_args()
    firms=set(args.firms.split(","))
    output=args.output.resolve()
    original=comparison.world_ledgers
    comparison.world_ledgers=lambda directory: ((firm,ledger) for firm,ledger in original(directory) if firm in firms)
    write(output/"worker_protocols"/(args.world+"_"+"_".join(sorted(firms))+".json"),dict(
        world=args.world,firms=sorted(firms),helper_sha256=sha256(Path(__file__)),unchanged_comparison=True,
        prediction_or_parameter_changes=False,threads_per_worker=2))
    with threadpool_limits(limits=2),threadpool_limits(limits=1,user_api="blas"):
        comparison.run_world(output,args.world)
