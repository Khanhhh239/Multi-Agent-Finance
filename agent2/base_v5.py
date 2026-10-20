"""Memory-bounded S2/P2 base evaluation for the v5 PU-weight screen.

Every source row is retained. LightGBM Sequence streams memory-mapped matrices
instead of materializing nineteen full worlds in one pandas frame.
All evaluation results are dữ liệu tổng hợp.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import inspect
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from .runtime_v5 import limit_memory, sha256, wait_memory, write_json
from .select_v5 import PU_WEIGHTS, candidate_summary, world_summary
from .world_v4_schemes import SCHEMES

BRANCHES = tuple(sorted({item[0] for item in SCHEMES.values()}))
FAMILIES = tuple(sorted(SCHEMES))


class MatrixSequence(lgb.Sequence):
    batch_size = 4096

    def __init__(self, path, columns=None):
        self.array = np.load(path, mmap_mode='r') if isinstance(path,(str,Path)) else path
        self.columns = np.arange(self.array.shape[1]) if columns is None else np.asarray(columns)

    def __len__(self):
        return len(self.array)

    def __getitem__(self, index):
        # LightGBM's sampled-column constructor requires float64 values;
        # on-disk storage stays float32 and only requested rows are copied.
        return np.asarray(self.array[index][..., self.columns], dtype=np.float64, order='C')


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def preparation_hashes():
    paths=[Path(name) for name in ('agent2/data.py','agent2/feats.py','agent2/feats_v4.py',
                                  'agent2/hybrid.py','agent2/methods.py')]
    paths.extend(sorted(Path('sme_fraud').glob('*.py')))
    return {'prepare_world_function':hashlib.sha256(inspect.getsource(prepare_world).encode()).hexdigest(),
            **{str(path):sha256(path) for path in paths}}


def prepare_world(seed, root, matrices, generation):
    from .data import load
    from .hybrid import FEATURE_SETS, attach_unsupervised
    source = root/f'v5dev_s{seed}'
    verified = _load(generation/f'world_{seed}.json')
    if verified['status'] != 'validated' or any(value!='passed' for value in verified['checks'].values()):
        raise ValueError('No validated development world')
    directory = matrices/f's{seed}'
    manifest_path = directory/'manifest.json'
    if manifest_path.exists():
        manifest=_load(manifest_path)
        assert manifest['input_hash']==sha256(generation/f'world_{seed}.json')
        assert manifest['preparation_hashes']==preparation_hashes()
        assert all(sha256(directory/name)==digest for name,digest in manifest['files'].items())
        return manifest
    wait_memory(3,matrices/'runtime.json')
    began=time.monotonic()
    frame=attach_unsupervised(load(source),source/'_cache'/'ustack.pkl',seed=0)
    cols=FEATURE_SETS['L4'](frame)
    assert len(cols)==len(set(cols))
    l3=FEATURE_SETS['L3'](frame)
    directory.mkdir(parents=True,exist_ok=True)
    for split in ('train','validation','test'):
        part=frame[frame.split==split].copy()
        np.save(directory/f'{split}.npy',part[cols].to_numpy(dtype=np.float32))
        keep=['transaction_id','company_id','is_fraud','fraud_type','case_id','hard_negative_type','week','t',
              'rule_graph','u_entity']
        meta=part[keep].copy()
        for key in ('transaction_id','company_id','case_id'):
            meta[key]=f'v5dev_s{seed}:'+meta[key].astype(str)
        meta['branch']=meta.fraud_type.map(lambda family:SCHEMES[family][0] if family in SCHEMES else '')
        meta.to_parquet(directory/f'{split}.parquet',index=False)
        del part,meta
    del frame
    from sme_fraud import rules
    rules.parse.cache_clear()
    rules.normalize.cache_clear()
    gc.collect()
    manifest={'data_origin':'dữ liệu tổng hợp','seed':seed,'columns':cols,'L3_columns':l3,
              'input_hash':sha256(generation/f'world_{seed}.json'),'preparation_hashes':preparation_hashes(),
              'seconds':time.monotonic()-began,
              'files':{p.name:sha256(p) for p in directory.iterdir() if p.suffix in ('.npy','.parquet')}}
    write_json(manifest_path,manifest)
    return manifest


def observed_labels(metadata, hidden=None, balanced=False, weight=.1):
    if weight not in PU_WEIGHTS:
        raise ValueError('Unregistered PU weight')
    y=metadata.is_fraud.to_numpy(dtype=np.int8).copy()
    if hidden is not None:
        y[metadata.branch.to_numpy()==hidden]=0
    sample=np.full(len(y),weight,dtype=np.float32)
    pos=y==1
    sample[pos]=1.
    if balanced and pos.any():
        names,counts=np.unique(metadata.fraud_type.to_numpy()[pos],return_counts=True)
        families=metadata.fraud_type.to_numpy()
        for name,count in zip(names,counts):
            sample[pos & (families==name)]=pos.sum()/len(names)/count
    return y,sample


def source_data(target, split, matrices, hidden, weight, columns, balanced):
    sequences=[]; metas=[]
    for seed in range(1001,1021):
        if seed==target:
            continue
        directory=matrices/f's{seed}'
        sequences.append(MatrixSequence(directory/f'{split}.npy',columns))
        metas.append(pd.read_parquet(directory/f'{split}.parquet',columns=['is_fraud','fraud_type','branch']))
    metadata=pd.concat(metas,ignore_index=True)
    y,sample=observed_labels(metadata,hidden,balanced,weight)
    del metadata,metas
    return sequences,y,sample


def predict_sequences(booster,sequences):
    pieces=[]
    for sequence in sequences:
        pieces.extend(booster.predict(sequence[start:start+8192],num_threads=4)
                      for start in range(0,len(sequence),8192))
    return np.concatenate(pieces)


def fit_source(target,matrices,hidden,weight,seed=0,kind='L4-FB-PU',max_rounds=600,early_stop=60):
    contract=_load(matrices/f's{target}'/'manifest.json')
    columns=list(range(len(contract['columns'])))
    if kind=='L3-PU':
        columns=[contract['columns'].index(name) for name in contract['L3_columns']]
    elif kind!='L4-FB-PU':
        raise ValueError('Base runner accepts only registered base models')
    for world in range(1001,1021):
        assert _load(matrices/f's{world}'/'manifest.json')['columns']==contract['columns']
    train,y,weights=source_data(target,'train',matrices,hidden,weight,columns,kind=='L4-FB-PU')
    valid,yv,_=source_data(target,'validation',matrices,hidden,weight,columns,False)
    if not y.sum() or not yv.sum():
        raise ValueError('Source positive support absent; refuse undocumented fallback')
    common=dict(objective='binary',metric=['binary_logloss','average_precision'],min_child_samples=10,
                subsample=.8,subsample_freq=1,colsample_bytree=.6,reg_lambda=2.,
                scale_pos_weight=max(1.,(len(y)-y.sum())/y.sum())**.5,seed=seed,
                num_threads=4,verbosity=-1,learning_rate=.05,feature_pre_filter=False)
    ds=lgb.Dataset(train,label=y,weight=weights,free_raw_data=True,params=common)
    dv=lgb.Dataset(valid,label=yv,reference=ds,free_raw_data=True,params=common)
    best=(-1.,None,None)
    for leaves in (7,15):
        model=lgb.train(dict(common,num_leaves=leaves),ds,num_boost_round=max_rounds,
                        valid_sets=[dv],valid_names=['validation'],callbacks=[lgb.early_stopping(early_stop,verbose=False)])
        ap=float(average_precision_score(yv,predict_sequences(model,valid)))
        if ap>best[0]:
            best=(ap,model,leaves)
    target_x=MatrixSequence(matrices/f's{target}'/'test.npy',columns)
    scores=predict_sequences(best[1],[target_x])
    details={'source_worlds':19,'source_train_rows':len(y),'source_validation_rows':len(yv),
             'source_observed_train_positives':int(y.sum()),'validation_ap':best[0],
             'num_leaves':best[2],'best_iteration':best[1].best_iteration,'PU_weight':weight,'model_seed':seed}
    del ds,dv,train,valid,model,best
    gc.collect()
    return scores,details


def run_world(target,weight,matrices,output):
    from .metrics import tie_break,weekly_alerts
    directory=output/f'w{weight:.1f}'/f's{target}'
    directory.mkdir(parents=True,exist_ok=True)
    te=pd.read_parquet(matrices/f's{target}'/'test.parquet')
    protocols={}
    for protocol in ('S2',*BRANCHES):
        saved=directory/f'{protocol}.json'
        flags=directory/f'{protocol}.npz'
        if saved.exists():
            result=_load(saved)
            if result['flags_sha256']!=sha256(flags):
                raise ValueError('Checkpoint flags do not match')
            protocols[protocol]=result
            continue
        wait_memory(3,output/'runtime.json')
        began=time.monotonic()
        write_json(output/'runtime.json',{'status':'fitting','world':target,'w':weight,'protocol':protocol,
                                         'data_origin':'dữ liệu tổng hợp'})
        scores,fit=fit_source(target,matrices,None if protocol=='S2' else protocol,weight)
        alerts=weekly_alerts(te,scores+tie_break(len(te),5),3)
        positive=te.is_fraud.to_numpy()==1
        hard=(te.hard_negative_type.to_numpy()!='') & ~positive
        branch=(te.branch.to_numpy()==protocol) & positive
        temporary=flags.with_suffix('.tmp.npz')
        np.savez_compressed(temporary,transaction_id=te.transaction_id.to_numpy(dtype=str),
                            company_id=te.company_id.to_numpy(dtype=str),case_id=te.case_id.to_numpy(dtype=str),
                            alerts=alerts,scores=scores,is_fraud=te.is_fraud.to_numpy(dtype=np.int8))
        temporary.replace(flags)
        result={'data_origin':'dữ liệu tổng hợp','world':target,'protocol':protocol,'fit':fit,
                'tp':int((positive & alerts).sum()),'positives':int(positive.sum()),
                'branch_tp':int((branch & alerts).sum()),'branch_positives':int(branch.sum()),
                'hard_negative_alerts':int((hard & alerts).sum()),'hard_negatives':int(hard.sum()),
                'alerts':int(alerts.sum()),'seconds':time.monotonic()-began,'flags_sha256':sha256(flags)}
        write_json(saved,result)
        protocols[protocol]=result
        print(f'PU w={weight} world={target} protocol={protocol} persisted',flush=True)
    summary=world_summary(protocols,BRANCHES)
    write_json(directory/'summary.json',summary)
    return summary


def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    # No model fit until all twenty world validations are present.
    for seed in range(1001,1021):
        checked=_load(args.generation/f'world_{seed}.json')
        if checked['status']!='validated' or any(value!='passed' for value in checked['checks'].values()):
            raise ValueError('All twenty worlds must be validated before PU selection')
    for seed in range(1001,1021):
        prepare_world(seed,args.root,args.matrices,args.generation)
        print(f'prepared base matrix {seed}',flush=True)
    code_paths=('agent2/base_v5.py','agent2/select_v5.py','agent2/hybrid.py','agent2/methods.py',
                'agent2/data.py','agent2/feats.py','agent2/feats_v4.py','agent2/metrics.py')
    plan={'data_origin':'dữ liệu tổng hợp','weights':list(PU_WEIGHTS),'targets':list(range(1001,1009)),
          'source_worlds_per_target':19,'model_seed':0,'protocols':['S2',*BRANCHES],
          'code_hashes':{name:sha256(name) for name in code_paths},
          'matrix_manifests':{str(seed):sha256(args.matrices/f's{seed}'/'manifest.json') for seed in range(1001,1021)}}
    plan_path=args.output/'plan.json'
    if plan_path.exists() and _load(plan_path)!=plan:
        raise ValueError('PU plan changed; refuse mixed checkpoints')
    write_json(plan_path,plan)
    pilot_file=args.output/'runtime_estimate.json'
    if not pilot_file.exists():
        began=time.monotonic()
        run_world(1001,.1,args.matrices,args.output)
        wall_seconds=time.monotonic()-began
        # On resume, count all measured protocols rather than timing only the
        # unfinished suffix and underestimating the complete world workload.
        pilot_directory=args.output/'w0.1'/'s1001'
        seconds=sum(_load(pilot_directory/f'{protocol}.json')['seconds'] for protocol in ('S2',*BRANCHES))
        estimate={'data_origin':'dữ liệu tổng hợp','pilot_candidate':'L4-FB-PU','pilot_weight':.1,
                  'pilot_target':1001,'protocols':11,'model_seed':0,'seconds':seconds,
                  'wall_seconds_this_invocation':wall_seconds,
                  'timing_definition':'sum of all eleven saved protocol runtimes; excludes waiting for memory; safe on resume',
                  'preparation_seconds':sum(_load(args.matrices/f's{s}'/'manifest.json')['seconds'] for s in range(1001,1021)),
                  'PU_screen_world_runs':24,'PU_screen_estimated_hours':seconds*24/3600,
                  'supervised_screen_world_runs':32,'supervised_screen_estimated_hours':seconds*32/3600,
                  'selection_three_candidates_five_seed_fit_equivalents':300,
                  'selection_estimated_hours':seconds*300/3600,
                  'caveat':'One-world estimate; cold runs and feature work not included; no world or seed reduction authorized'}
        write_json(pilot_file,estimate)
        print(json.dumps(estimate,ensure_ascii=False),flush=True)
    if args.pilot_only:
        return
    summaries={}
    for weight in PU_WEIGHTS:
        worlds={seed:run_world(seed,weight,args.matrices,args.output) for seed in range(1001,1009)}
        summaries[str(weight)]=candidate_summary(worlds,'screening')
        write_json(args.output/f'summary_w{weight}.json',summaries[str(weight)])
    valid=[weight for weight in PU_WEIGHTS if summaries[str(weight)]['eligible']]
    if not valid:
        write_json(args.output/'weight_selection_failure.json',{'status':'no_eligible_PU_weight',
                   'data_origin':'dữ liệu tổng hợp','summaries':summaries,'sealed_generation_permitted':False})
        return
    weight=max(valid,key=lambda value:summaries[str(value)]['J'])
    write_json(args.output/'PU_locked.json',{'status':'locked','w':weight,'data_origin':'dữ liệu tổng hợp',
               'summaries':summaries,'plan_sha256':sha256(plan_path),'tie_order':list(PU_WEIGHTS)})
    write_json(args.output/'runtime.json',{'status':'PU_locked','w':weight,'data_origin':'dữ liệu tổng hợp'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('work/data'))
    parser.add_argument('--generation',type=Path,default=Path('results/v5/development'))
    parser.add_argument('--matrices',type=Path,default=Path('work/v5_matrices'))
    parser.add_argument('--output',type=Path,default=Path('results/v5/PU_screen'))
    parser.add_argument('--pilot-only',action='store_true')
    parser.add_argument('--prepare-world',type=int,help='Prepare one world in a fresh bounded worker; no model evaluation')
    args=parser.parse_args()
    limit_memory(6)
    try:
        if args.prepare_world is not None:
            if args.prepare_world not in range(1001,1021):
                raise ValueError('Preparation seed outside registered development set')
            for seed in range(1001,1021):
                checked=_load(args.generation/f'world_{seed}.json')
                if checked['status']!='validated' or any(value!='passed' for value in checked['checks'].values()):
                    raise ValueError('All twenty worlds must be validated before feature preparation')
            write_json(args.output/'runtime.json',{'status':'preparing_base_features','world':args.prepare_world,
                                                  'data_origin':'dữ liệu tổng hợp'})
            prepare_world(args.prepare_world,args.root,args.matrices,args.generation)
            print(f'prepared base matrix {args.prepare_world}',flush=True)
        else:
            run(args)
    except Exception as error:
        write_json(args.output/'failure.json',{'status':'failed','error':repr(error),'data_origin':'dữ liệu tổng hợp'})
        raise


if __name__=='__main__':
    main()
