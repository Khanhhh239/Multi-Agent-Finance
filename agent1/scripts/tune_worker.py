"""Một trial trong tiến trình riêng, in pinball sau mỗi 100 cây cho pruner."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.models import t1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--train',required=True);parser.add_argument('--valid',required=True)
    parser.add_argument('--params',required=True);args=parser.parse_args()
    train=pd.read_parquet(args.train);valid=pd.read_parquet(args.valid)
    params=json.loads(Path(args.params).read_text(encoding='utf-8'))
    model=None
    for step in range(6):
        model=t1.HazardGBM(params,rounds=100).fit(train,init_model=model.booster if model else None)
        loss=t1.evaluate_quantiles(valid.remaining,t1.quantiles_from_hazard(model.hazards(valid)))['pinball_avg']
        print(json.dumps(dict(step=step,loss=loss)),flush=True)


if __name__=='__main__':main()
