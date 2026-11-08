"""Validate every Parquet before recording synthetic world provenance."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,ROOT
from agent1.data.contracts import validate_world
from agent1.data.world_manifest import check_world_files, load_cohort, verify_world_manifest, canonical_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cohort',type=Path,help='Locked cohort manifest; otherwise scan all configured worlds')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/02_Data/worlds_registry.csv')
    parser.add_argument('--synthetic-root',type=Path,default=SYNTH)
    args=parser.parse_args()
    if args.cohort:
        cohort=load_cohort(args.cohort,synthetic_root=args.synthetic_root)
        names=[entry['name'] for entry in cohort['worlds']]
        roles={entry['name']:entry['role'] for entry in cohort['worlds']}
    else:
        names=[path.parent.name for path in sorted(args.synthetic_root.glob('*/config.json'))]
        roles={}
    if not names:
        raise ValueError('No configured worlds to register')
    rows=[]
    for name in names:
        directory=args.synthetic_root/name
        hashes=check_world_files(directory)  # fail closed, including legacy worlds
        checks=validate_world(directory)
        manifest=verify_world_manifest(directory) if (directory/'manifest.json').exists() else None
        cfg=json.loads((directory/'config.json').read_text(encoding='utf-8'))
        rows.append(dict(name=name,seed=cfg['seed'],config_sha256=canonical_hash(cfg),
            tables_sha256=canonical_hash(hashes),purpose=roles.get(name,'legacy_unassigned'),
            n_firms=cfg['n_firms'],all_contracts_pass=bool(checks.passed.all()),
            manifest_present=manifest is not None,smoke=('smoke' in name)))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output,index=False)


if __name__=='__main__':main()
