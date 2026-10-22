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
from .select_v5 import HN_WEIGHTS, PU_WEIGHTS, candidate_summary, world_summary
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

    def take(self, rows):
        """Gather arbitrary sorted rows (fancy indexing on the memory map reads only those rows)."""
        return np.asarray(self.array[np.asarray(rows)][:, self.columns], dtype=np.float64, order='C')


class ConcatSequence(lgb.Sequence):
    """Column-wise concatenation of several row-aligned sequences (base L4 + change features)."""
    batch_size = 4096

    def __init__(self, parts):
        self.parts = parts
        assert len({len(p) for p in parts}) == 1, 'row counts differ between matrices'

    def __len__(self):
        return len(self.parts[0])

    def __getitem__(self, index):
        blocks = [p[index] for p in self.parts]
        return np.concatenate(blocks, axis=blocks[0].ndim - 1)

    def take(self, rows):
        return np.concatenate([p.take(rows) for p in self.parts], axis=1)


class SubsetSequence(lgb.Sequence):
    """Rows `index` (sorted) of a MatrixSequence or ConcatSequence, gathered batch by batch."""
    batch_size = 4096

    def __init__(self, sequence, index):
        self.sequence, self.index = sequence, np.asarray(index, dtype=np.int64)

    def __len__(self):
        return len(self.index)

    def __getitem__(self, item):
        rows = self.index[item]
        if np.ndim(rows) == 0:
            return self.sequence.take(np.array([rows]))[0]
        return self.sequence.take(rows)


def negative_subsample(metadata, y, fraction, world_seed):
    """Keep every observed positive and every hard negative; keep `fraction` of the remaining rows.

    Returns (kept row index, inverse-probability factor per kept row). Deterministic per source world.
    """
    if fraction >= 1:
        return np.arange(len(y)), np.ones(len(y), dtype=np.float32)
    rng = np.random.default_rng(1000 + world_seed)
    always = (y == 1) | (metadata.hard_negative_type.to_numpy() != '')
    keep = always | (rng.random(len(y)) < fraction)
    index = np.flatnonzero(keep)
    factor = np.where(always[index], 1.0, 1.0 / fraction).astype(np.float32)
    return index, factor


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_storage_revision(generation):
    migration=Path(generation)/'io_revision1'/'migration_proof.json'
    if not migration.exists():
        return
    recorded=_load(migration)['partial_1013_csv_sha256']
    actual=_load(Path(generation)/'world_1013.json')['file_hashes']
    mismatches=[name for name,value in recorded.items() if actual.get(name)!=value]
    proof={'data_origin':'dữ liệu tổng hợp','status':'failed' if mismatches else 'passed',
           'world':1013,'csv_files_compared':len(recorded),'mismatches':mismatches,
           'migration_sha256':sha256(migration),'checkpoint_sha256':sha256(Path(generation)/'world_1013.json')}
    write_json(Path(generation)/'storage_full_world_parity.json',proof)
    if mismatches:
        raise ValueError('Full-world storage equivalence failed; refuse any feature preparation or model evaluation')


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


def observed_labels(metadata, hidden=None, balanced=False, weight=.1, hn_weight=None):
    """v6: `hn_weight` re-weights source rows that are legitimate AND a confirmed hard negative; None = v5 behaviour."""
    if weight not in PU_WEIGHTS:
        raise ValueError('Unregistered PU weight')
    if hn_weight is not None and hn_weight not in HN_WEIGHTS:
        raise ValueError('Unregistered hard-negative weight')
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
    if hn_weight is not None:
        sample[(metadata.is_fraud.to_numpy()==0) & (metadata.hard_negative_type.to_numpy()!='')]=hn_weight
    return y,sample


def change_feature_names():
    from .change_detect import CD_FEATURES, ED2_SPECS
    return list(CD_FEATURES) + [f"{f}{'+' if s > 0 else '-'}" for f, s, _ in ED2_SPECS] + ['ed2_score']


def prepare_change_world(seed, root, matrices):
    """Change features + EntityDeviation2 tails for one prepared world, row-aligned with its base matrices.

    EntityDeviation2 is fitted on the world's own TRAIN period without labels. Files: {split}_cd.npy and
    manifest_cd.json. Base matrices are never modified.
    """
    from .change_detect import CD_FEATURES, EntityDeviation2, change_features
    directory = matrices/f's{seed}'
    manifest_path = directory/'manifest_cd.json'
    if manifest_path.exists():
        manifest = _load(manifest_path)
        assert all(sha256(directory/name)==digest for name,digest in manifest['files'].items())
        return manifest
    began = time.monotonic()
    world = root/f'v5dev_s{seed}'
    features = change_features(world)
    kinds = pd.read_csv(world/'transactions.csv', dtype=str, keep_default_na=False,
                        usecols=['transaction_id','txn_type'])
    split = pd.read_csv(world/'splits.csv', dtype=str)
    features = features.merge(kinds, on='transaction_id').merge(split, on='transaction_id')
    train = features[features.split=='train']
    ed2 = EntityDeviation2().fit(train, train.txn_type.to_numpy())
    names = change_feature_names()
    parts = ed2.parts(features, features.txn_type.to_numpy())
    block = pd.DataFrame({name: parts.get(name, np.zeros(len(features))) for name in names[len(CD_FEATURES):-1]})
    block['ed2_score'] = ed2.score(features, features.txn_type.to_numpy())
    full = pd.concat([features[['transaction_id'] + list(CD_FEATURES)].reset_index(drop=True), block], axis=1)
    full['transaction_id'] = f'v5dev_s{seed}:' + full['transaction_id']
    full = full.set_index('transaction_id')
    files = {}
    for part in ('train','validation','test'):
        ids = pd.read_parquet(directory/f'{part}.parquet', columns=['transaction_id']).transaction_id
        matrix = full.loc[ids.to_numpy(), names].to_numpy(dtype=np.float32)   # same row order as the base matrix
        np.save(directory/f'{part}_cd.npy', matrix)
        files[f'{part}_cd.npy'] = sha256(directory/f'{part}_cd.npy')
    manifest = {'data_origin':'dữ liệu tổng hợp','seed':seed,'columns':names,'files':files,
                'code_sha256':{'agent2/change_detect.py':sha256(Path('agent2/change_detect.py'))},
                'base_manifest_sha256':sha256(directory/'manifest.json'),'seconds':time.monotonic()-began}
    write_json(manifest_path, manifest)
    return manifest


def world_sequence(directory, split, columns, with_change=False):
    base = MatrixSequence(directory/f'{split}.npy', columns)
    return ConcatSequence([base, MatrixSequence(directory/f'{split}_cd.npy')]) if with_change else base


def source_data(target, split, matrices, hidden, weight, columns, balanced, with_change=False, negative_fraction=1.0):
    sequences=[]; metas=[]; seeds=[]
    for seed in range(1001,1021):
        if seed==target:
            continue
        directory=matrices/f's{seed}'
        sequences.append(world_sequence(directory,split,columns,with_change))
        meta=pd.read_parquet(directory/f'{split}.parquet')
        if 'hard_negative_type' not in meta:
            meta['hard_negative_type']=''
        metas.append(meta[['is_fraud','fraud_type','branch','hard_negative_type']].copy())
        del meta
        seeds.append(seed)
    metadata=pd.concat(metas,ignore_index=True)
    # labels and family balancing over the pooled sources, exactly as before subsampling existed
    y,sample=observed_labels(metadata,hidden,balanced,weight)
    if negative_fraction<1 and split=='train':
        kept_y,kept_w,start=[],[],0
        for k,(meta,seed) in enumerate(zip(metas,seeds)):
            stop=start+len(meta)
            index,factor=negative_subsample(meta,y[start:stop],negative_fraction,seed)
            sequences[k]=SubsetSequence(sequences[k],index)
            kept_y.append(y[start:stop][index]); kept_w.append(sample[start:stop][index]*factor)
            start=stop
        y,sample=np.concatenate(kept_y),np.concatenate(kept_w)
    del metadata,metas
    return sequences,y,sample


def predict_sequences(booster,sequences):
    pieces=[]
    for sequence in sequences:
        pieces.extend(booster.predict(sequence[start:start+8192],num_threads=4)
                      for start in range(0,len(sequence),8192))
    return np.concatenate(pieces)


KINDS = ('L3-PU', 'L4-FB-PU', 'L4-PU', 'L4-PU-E2-AR')


def fit_source(target,matrices,hidden,weight,seed=0,kind='L4-FB-PU',max_rounds=600,early_stop=60,
               negative_fraction=1.0):
    """early_stop=None trains exactly `max_rounds` trees for each leaf setting and picks the leaf setting by
    validation AP. Diagnostics (scripts/diag_cd_transfer.py) showed early stopping on validation AP can stop
    after ONE tree under PU weights; the fixed-round policy must be registered before it is used."""
    contract=_load(matrices/f's{target}'/'manifest.json')
    columns=list(range(len(contract['columns'])))
    if kind not in KINDS:
        raise ValueError('Base runner accepts only registered base models')
    if kind=='L3-PU':
        columns=[contract['columns'].index(name) for name in contract['L3_columns']]
    with_change = kind=='L4-PU-E2-AR'
    for world in range(1001,1021):
        assert _load(matrices/f's{world}'/'manifest.json')['columns']==contract['columns']
        if with_change:
            assert _load(matrices/f's{world}'/'manifest_cd.json')['columns']==change_feature_names()
    balanced = kind=='L4-FB-PU'
    train,y,weights=source_data(target,'train',matrices,hidden,weight,columns,balanced,with_change,negative_fraction)
    valid,yv,_=source_data(target,'validation',matrices,hidden,weight,columns,False,with_change)
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
        callbacks=[] if early_stop is None else [lgb.early_stopping(early_stop,first_metric_only=False,verbose=False)]
        model=lgb.train(dict(common,num_leaves=leaves),ds,num_boost_round=max_rounds,
                        valid_sets=[dv],valid_names=['validation'],callbacks=callbacks)
        ap=float(average_precision_score(yv,predict_sequences(model,valid)))
        if ap>best[0]:
            best=(ap,model,leaves)
    target_x=world_sequence(matrices/f's{target}','test',columns,with_change)
    scores=predict_sequences(best[1],[target_x])
    trees=best[1].current_iteration()
    details={'source_worlds':19,'source_train_rows':len(y),'source_validation_rows':len(yv),
             'source_observed_train_positives':int(y.sum()),'validation_ap':best[0],
             'num_leaves':best[2],'best_iteration':best[1].best_iteration,'trees':trees,'kind':kind,
             'round_policy':'fixed' if early_stop is None else f'early_stop_{early_stop}',
             'negative_fraction':negative_fraction,'PU_weight':weight,'model_seed':seed}
    if trees < 20:
        details['warning']='fewer than 20 trees: early stopping collapsed; do not use this fit for selection'
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
    verify_storage_revision(args.generation)
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
    parser.add_argument('--prepare-change-world',type=int,
                        help='Add change features and EntityDeviation2 tails to one prepared world; no model evaluation')
    args=parser.parse_args()
    limit_memory(6)
    try:
        if args.prepare_change_world is not None:
            if args.prepare_change_world not in range(1001,1021):
                raise ValueError('Preparation seed outside registered development set')
            assert (args.matrices/f's{args.prepare_change_world}'/'manifest.json').exists(), 'prepare the base world first'
            prepare_change_world(args.prepare_change_world,args.root,args.matrices)
            print(f'prepared change features {args.prepare_change_world}',flush=True)
        elif args.prepare_world is not None:
            if args.prepare_world not in range(1001,1021):
                raise ValueError('Preparation seed outside registered development set')
            for seed in range(1001,1021):
                checked=_load(args.generation/f'world_{seed}.json')
                if checked['status']!='validated' or any(value!='passed' for value in checked['checks'].values()):
                    raise ValueError('All twenty worlds must be validated before feature preparation')
            verify_storage_revision(args.generation)
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
