"""Một kích cỡ huấn luyện trong tiến trình riêng; đánh giá cấu hình đã khóa."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
import lightgbm as lgb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT
from agent1.models import t1
from agent1.data.scaling import MemmapSequence
from run_t1 import snapshots,censor,score


def prediction(model,test):
    h=model.hazards(test);p,s=t1.pmf_from_hazard(h)
    return dict(Q=t1.quantiles_from_hazard(h),P=p,cdf=1-s)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cache',required=True);parser.add_argument('--rows',type=int,required=True)
    parser.add_argument('--rounds',type=int,default=300);args=parser.parse_args()
    directory=Path(args.cache);manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if not manifest['complete'] or args.rows not in manifest['sizes']:raise ValueError('Cache chưa đủ hoặc không có kích cỡ này')
    model=t1.HazardGBM(rounds=args.rounds);start=time.monotonic()
    checkpoint=OUT/'t1/scaling_models';checkpoint.mkdir(exist_ok=True)
    model_path=checkpoint/f"{args.rows}_{manifest['source_fingerprint'][:12]}_{args.rounds}.txt"
    metadata_path=model_path.with_suffix('.json');resumed=False
    if model_path.exists() and metadata_path.exists():
        metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata['model_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest() and metadata['source_fingerprint']==manifest['source_fingerprint']:
            model.booster=lgb.Booster(model_file=str(model_path));train_seconds=metadata['train_seconds'];resumed=True
    if not resumed:
        sequence=MemmapSequence(directory/f'X_{args.rows}.dat',args.rows,manifest['columns'])
        labels=np.memmap(directory/f'y_{args.rows}.dat',dtype='float32',mode='r',shape=(args.rows,))
        dataset=lgb.Dataset(sequence,label=labels,feature_name=manifest['features'],params=dict(data_random_seed=7))
        model.booster=lgb.train(model.p,dataset,num_boost_round=args.rounds)
        train_seconds=time.monotonic()-start
        model.booster.save_model(str(model_path))
        metadata_path.write_text(json.dumps(dict(model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
            source_fingerprint=manifest['source_fingerprint'],features=manifest['features'],expanded_rows=args.rows,
            parameters=model.p,rounds=args.rounds,train_seconds=train_seconds,test_used_for_selection=False),indent=2),encoding='utf-8')
        del dataset,sequence,labels;gc.collect()
    rows=[];company_losses=[];origin=pd.Timestamp('2024-07-01')
    for months in [0,3,6,12,24]:
        visible=origin-pd.DateOffset(months=months)
        test=censor(snapshots('tgt',pd.date_range(origin,periods=52,freq='7D'),visible_from=visible,tag=f'test_M{months}'),'2025-12-31')
        test=test[test.issue_date>=origin]
        preds={'B1d-cust-quantiles':dict(Q=t1.b1_dist(test)),'pretrained zero-shot':prediction(model,test)}
        n_target=0
        if months:
            history=censor(snapshots('tgt',pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='7D'),
                visible_from=visible,tag=f'adapt_M{months}'),origin)
            history=history.sample(min(len(history),40000),random_state=7);n_target=len(history)
            adapted=t1.HazardGBM(dict(learning_rate=.02),rounds=150).fit(history,init_model=model.booster)
            preds['fine-tuned']=prediction(adapted,test)
            del history,adapted
        result=score(preds,test,'pretraining_scaling_fixed_source')
        capped=np.minimum(test.remaining.to_numpy(),t1.CAP)
        for name,pred in preds.items():
            error=capped[:,None]-pred['Q']
            loss=np.maximum(np.asarray(t1.QS)*error,(np.asarray(t1.QS)-1)*error).mean(1)
            grouped=pd.DataFrame(dict(firm_id=test.firm_id.to_numpy(),loss=loss)).groupby('firm_id').agg(loss_sum=('loss','sum'),n=('loss','size')).reset_index()
            grouped['model']=name;grouped['months_history']=months;grouped['expanded_rows']=args.rows
            company_losses.append(grouped)
        pd.concat(company_losses).to_csv(OUT/f't1/scaling_company_losses_{args.rows}.csv',index=False)
        result['expanded_rows']=args.rows;result['source_world']=manifest['world'];result['source_fingerprint']=manifest['source_fingerprint']
        result['months_history']=months;result['n_target_rows']=n_target;result['pretraining_seconds']=train_seconds
        result['pretraining_rounds']=args.rounds;result['test_used_for_selection']=False
        result['n_source_firms_used']=manifest['n_firms_used'][str(args.rows)]
        result['experiment_version']='scaling-nested-expanded-v1'
        result['measurement_version']='scaling-nested-expanded-v1-fullweek'
        result['loaded_model_checkpoint']=resumed
        rows.append(result)
        pd.concat(rows).to_csv(OUT/f't1/scaling_{args.rows}.csv',index=False)
        print(args.rows,months,'done',flush=True)


if __name__=='__main__':main()
