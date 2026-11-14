"""Prepare ten blank synthetic review forms, or validate/aggregate exports."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.he_inference.business_review import build,merge_feedback,summarize
from experiments.he_inference.protocol import canonical,read_json


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare');p.add_argument('--packet',type=Path,default=ROOT/'.runtime/he-company-demo')
    p.add_argument('--comparison',type=Path,default=ROOT.parent/'Agent2_Spec_v2_1/evidence/HE/plaintext_comparison_20261112/run/comparison.json')
    p.add_argument('--output-dir',type=Path,required=True)
    p=sub.add_parser('summarize');p.add_argument('--packet-file',type=Path,required=True)
    p.add_argument('--feedback',type=Path,nargs='+',required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='prepare':
        packet=build(args.packet,args.comparison,args.output_dir)
        print(json.dumps(dict(status='awaiting_human_review',cases=len(packet['cases']),packet_id=packet['packet_id'])))
    else:
        packet=read_json(args.packet_file);merged=merge_feedback(packet,[read_json(p) for p in args.feedback])
        result=summarize(packet,merged);args.output_dir.mkdir(parents=True,exist_ok=False)
        (args.output_dir/'merged.feedback.json').write_bytes(canonical(merged))
        (args.output_dir/'summary.json').write_bytes(canonical(result))
        print(json.dumps(dict(status=result['status'],reviewed=sum(c['reviewed'] for c in result['companies']),business_effectiveness_verified=False)))
