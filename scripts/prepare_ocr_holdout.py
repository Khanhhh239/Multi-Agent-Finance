"""Explicitly pending until new source/layout groups are supplied; no fake split."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from src.quality.evaluation_split import seal,verify
from benchmark_public_invoices import CASES


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path);args=parser.parse_args()
    output=APP/'data/ocr_coverage_v1/holdout_manifest.json';output.parent.mkdir(parents=True,exist_ok=True)
    used=set(CASES)|{'charity_2023','software_kct','cyber_construction','misa_public_filing','viettel_adjustment','accounting_training'}
    if output.exists():
        manifest=json.loads(output.read_bytes());verify(manifest,ROOT)
        if args.input:raise ValueError('Manifest already sealed; create a separately versioned dataset, do not overwrite')
    else:
        manifest=seal(json.loads(args.input.read_bytes()) if args.input else [],used,ROOT)
        output.write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'status':manifest['status'],'input_count':len(manifest['entries']),'manifest_sha256':manifest['manifest_sha256']}))


if __name__=='__main__':main()
