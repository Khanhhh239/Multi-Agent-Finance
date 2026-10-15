"""Rebuild derived features after schema changes without altering raw data or labels."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from .features import build_features,FEATURE_DESCRIPTIONS
from .generate import write_csv


def rebuild(directory):
    tables={}
    for name in ('transactions','companies','employees','vendors','calendar','entity_links','attendance',
                 'vendor_status_history','bank_account_changes','advances','advance_events','journal_lines'):
        with (directory/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f:
            tables[name]=list(csv.DictReader(f))
    rows=build_features(tables)
    assert list(rows[0])==['transaction_id',*FEATURE_DESCRIPTIONS], 'Feature order mismatch'
    write_csv(directory/'features.csv',rows)
    meta=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    meta['feature_columns']=list(FEATURE_DESCRIPTIONS)
    meta['files']['features.csv']['sha256']=hashlib.sha256((directory/'features.csv').read_bytes()).hexdigest()
    (directory/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    dictionary=json.loads((directory/'data_dictionary.json').read_text(encoding='utf-8'))
    dictionary['features']=FEATURE_DESCRIPTIONS
    (directory/'data_dictionary.json').write_text(json.dumps(dictionary,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(rows=len(rows),features=len(FEATURE_DESCRIPTIONS),vat_pair_rows=sum(r['pair_133_331'] for r in rows))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(rebuild(args.data),indent=2))


if __name__=='__main__':
    main()
