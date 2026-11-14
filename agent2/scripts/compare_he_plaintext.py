"""Generate a same-model/same-snapshot HE/plaintext comparison, locally."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.he_inference.benchmark import run


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,default=ROOT/'.runtime/he-company-demo')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=5)
    parser.add_argument('--recovery-repetitions',type=int,default=1)
    parser.add_argument('--budget',type=int,default=5)
    args=parser.parse_args()
    report=run(args.packet,args.output_dir,args.repetitions,args.recovery_repetitions,args.budget)
    print(json.dumps(dict(status=report['status'],score_parity=report['score_parity_passed'],
        full_recovery=report['full_recovery_passed'],output=str(args.output_dir.resolve())),ensure_ascii=False))
