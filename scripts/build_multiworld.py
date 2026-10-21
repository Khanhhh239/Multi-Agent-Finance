"""Thiết kế LHS có seed; chỉ sinh thế giới dr mới, không ghi đè miền niêm phong."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy.stats import qmc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.synth.world import WorldConfig, generate, INDUSTRY
from agent1.paths import SYNTH, OUT


def design(count=20, firms=12, seed=73):
    points=qmc.LatinHypercube(8,seed=seed).random(count)
    rng=np.random.default_rng(seed)
    configs=[]
    for i,u in enumerate(points):
        configs.append(WorldConfig(name=f'dr_{i:03d}',seed=seed*1000+i,n_firms=firms,write_xml=0,
            tail=['atradius','uk','coface'][min(int(3*u[0]),2)], late_scale=.7+.8*u[1],dispute_scale=.5+1.5*u[2],
            posting_mode_p=tuple(rng.dirichlet(np.ones(3))),payrun_p=tuple(rng.dirichlet(np.ones(10))),
            memo_invoice_no_p=(.5+4*u[3],.5+4*u[4]),cod_mult=1+1.4*u[5],
            ontime_shift={k:float(-.3+.6*u[6]) for k in INDUSTRY},revenue_median=10e9+50e9*u[7],
            n_cust_median=float(rng.uniform(20,100))))
    return configs


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--count',type=int,default=20)
    parser.add_argument('--firms',type=int,default=12); parser.add_argument('--seed',type=int,default=73)
    parser.add_argument('--generate',action='store_true'); args=parser.parse_args()
    configs=design(args.count,args.firms,args.seed)
    directory=OUT/'data'; directory.mkdir(exist_ok=True)
    pd.DataFrame([dict(name=c.name,seed=c.seed,n_firms=c.n_firms,config=json.dumps(asdict(c))) for c in configs]).to_csv(directory/'design.csv',index=False)
    if args.generate:
        for cfg in configs:
            if (SYNTH/cfg.name/'config.json').exists():
                from agent1.data.contracts import validate_world
                validate_world(SYNTH/cfg.name)
                continue
            generate(cfg)


if __name__=='__main__':
    main()
