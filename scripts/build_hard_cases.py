import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.synth.world import WorldConfig
from agent1.synth.hard_cases import HardCaseWorld,CASES
from agent1.data.contracts import validate_world
from agent1.paths import SYNTH,OUT


def main():
    p=argparse.ArgumentParser();p.add_argument('--firms',type=int,default=12)
    p.add_argument('--cases',default=','.join(CASES));p.add_argument('--smoke',action='store_true');args=p.parse_args()
    rows=[]
    for case in args.cases.split(','):
        name=f'hc_{case}_v2'+('_smoke' if args.smoke else '')
        kwargs=dict(name=name,seed=901,n_firms=1 if args.smoke else args.firms,write_xml=0,rng_version=2)
        if args.smoke:kwargs.update(start='2023-01-01',end='2024-12-31')
        if case=='new_company':kwargs.update(start='2025-01-01',end='2025-12-31')
        if case=='seasonal_extreme':kwargs['season_override']=[1.8 if m in (1,8,11,12) else .6 for m in range(1,13)]
        cfg=WorldConfig(**kwargs);cfg.hard_case=case
        if (SYNTH/name/'config.json').exists():
            expected=json.loads(json.dumps(asdict(cfg)))
            if json.loads((SYNTH/name/'config.json').read_text(encoding='utf-8'))!=expected:raise ValueError('Cấu hình khác dữ liệu đã sinh; không ghi đè')
        if not (SYNTH/name/'hard_case_complete.txt').exists():HardCaseWorld(cfg,case).run()
        result=validate_world(SYNTH/name,raise_on_error=False)
        inv=pd.read_parquet(SYNTH/name/'invoices.parquet')
        rows.append(dict(world=name,case=case,n_firms=args.firms if not args.smoke else 1,n_invoices=len(inv),
                         checks=len(result),passed=int(result.passed.sum()),smoke=args.smoke,seed=cfg.seed))
    directory=OUT/'data';directory.mkdir(exist_ok=True)
    output=directory/('hard_case_smoke_v2.csv' if args.smoke else 'hard_cases_v2.csv')
    previous=pd.read_csv(output) if output.exists() else pd.DataFrame()
    combined=pd.concat([previous,pd.DataFrame(rows)],ignore_index=True).drop_duplicates('world',keep='last')
    combined.to_csv(output,index=False)
    return 0 if all(r['checks']==r['passed'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
