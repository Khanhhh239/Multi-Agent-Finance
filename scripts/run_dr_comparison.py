"""So sánh DR 1×400/20×20 với số HĐ khớp mỗi cặp DN, cùng ngân sách T1."""
import gc
import hashlib
import json
import shutil
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT,PROCESSED,ROOT
from agent1.data.dr_comparison import paired_quotas,sample_company_invoices
from agent1.models.features import SnapshotBuilder,FEATURES,add_labels
from agent1.models import t1
from agent1.data import real_loaders
from agent1.eval.cluster import mean_ci
from run_t1 import snapshots,censor,score


def row_sample(frame,budget=40000):
    frame=frame.drop_duplicates(['invoice_id','cutoff']).copy()
    if '_priority' not in frame:
        frame['_priority']=pd.util.hash_pandas_object(frame[['invoice_id','cutoff']],index=False,hash_key='0000000000000007').to_numpy()
    anchors=frame.sort_values('_priority').groupby('firm_id',sort=False).head(1)
    if len(anchors)>budget:raise ValueError('Ngân sách không đủ giữ mọi công ty')
    remaining=frame.drop(index=anchors.index).nsmallest(budget-len(anchors),'_priority')
    return pd.concat([anchors,remaining]).sort_values('_priority').reset_index(drop=True)


def counts(worlds,origin):
    rows=[]
    for world in worlds:
        for part in world['parts']:
            invoices=pd.read_parquet(SYNTH/part['path']/'invoices.parquet',columns=['firm_id','issue_date'])
            observed=invoices[invoices.issue_date<=origin].groupby('firm_id').size()
            firms=pd.read_parquet(SYNTH/part['path']/'firms.parquet').firm_id
            for firm in firms:
                rows.append(dict(company_key=world['name']+'/'+firm,n_invoices=int(observed.get(firm,0))))
    return pd.DataFrame(rows)


def prepare_arm(worlds,quotas,origin,cache):
    if cache.exists():return pd.read_parquet(cache)
    collected=pd.DataFrame();anchors=pd.DataFrame();actual_invoices=0
    cuts=pd.date_range('2019-01-07',origin-pd.Timedelta(days=7),freq='28D')
    if not len(cuts):raise ValueError('Origin dữ liệu thật nằm trước lịch nguồn; không dùng nguồn tương lai')
    for world in worlds:
        for part in world['parts']:
            part_cache=cache.parent/(cache.stem+'_parts')
            part_cache.mkdir(exist_ok=True)
            key=hashlib.sha256((world['name']+'/'+part['path']).encode()).hexdigest()[:20]
            saved=part_cache/(key+'.parquet');marker=part_cache/(key+'.json')
            if marker.exists() and saved.exists():
                state=json.loads(marker.read_text(encoding='utf-8'))
                if hashlib.sha256(saved.read_bytes()).hexdigest()!=state['sha256']:
                    raise ValueError('DR checkpoint hash không khớp')
                local=pd.read_parquet(saved);actual_invoices+=state['n_invoices']
                if not local.empty:
                    anchors=pd.concat([anchors,local.sort_values('_priority').groupby('firm_id',sort=False).head(1)],ignore_index=True)
                    collected=pd.concat([collected,local],ignore_index=True).nsmallest(40000,'_priority')
                print('resumed',world['name'],part['path'],flush=True)
                continue
            directory=SYNTH/part['path']
            inv=pd.read_parquet(directory/'invoices.parquet')
            inv=sample_company_invoices(inv,quotas,world['name'],origin)
            actual_invoices+=len(inv)
            pay=pd.read_parquet(directory/'payments.parquet');pay=pay[pay.invoice_id.isin(inv.invoice_id)]
            prom=pd.read_parquet(directory/'promises.parquet');prom=prom[prom.invoice_id.isin(inv.invoice_id)]
            builder=SnapshotBuilder(inv,pay,prom);parts=[]
            for cutoff in cuts:
                frame=builder.snapshot(cutoff)
                if frame.empty:continue
                keep=list(dict.fromkeys(['invoice_id','firm_id','cutoff','label_date','writeoff_date','top1','top2',*FEATURES]))
                frame=frame[[c for c in keep if c in frame]].copy()
                numeric=frame.select_dtypes('number').columns;frame[numeric]=frame[numeric].astype('float32')
                parts.append(frame)
            if not parts:
                pd.DataFrame().to_parquet(saved,index=False)
                marker.write_text(json.dumps(dict(n_invoices=len(inv),sha256=hashlib.sha256(saved.read_bytes()).hexdigest())),encoding='utf-8')
                continue
            frame=add_labels(pd.concat(parts,ignore_index=True),origin)
            frame['firm_id']=world['name']+'/'+frame.firm_id
            frame['invoice_id']=world['name']+'/'+frame.invoice_id
            frame['_priority']=pd.util.hash_pandas_object(frame[['invoice_id','cutoff']],index=False,hash_key='0000000000000007').to_numpy()
            local=row_sample(frame)
            local.to_parquet(saved,index=False)
            marker.write_text(json.dumps(dict(n_invoices=len(inv),sha256=hashlib.sha256(saved.read_bytes()).hexdigest())),encoding='utf-8')
            local_anchors=local.sort_values('_priority').groupby('firm_id',sort=False).head(1)
            anchors=pd.concat([anchors,local_anchors],ignore_index=True)
            collected=pd.concat([collected,local.nsmallest(40000,'_priority')],ignore_index=True).nsmallest(40000,'_priority')
            print('prepared',world['name'],part['path'],len(collected),'rows',flush=True)
            del builder,inv,pay,prom,parts,frame,local;gc.collect()
    if actual_invoices!=sum(quotas.values()):raise ValueError('Số HĐ sau chọn không khớp quota')
    collected=row_sample(pd.concat([collected,anchors],ignore_index=True))
    if collected.firm_id.nunique()!=400:raise ValueError('Snapshot cần đủ 400 công ty nguồn')
    collected.to_parquet(cache,index=False)
    return collected


def predict(model,frame):
    hazard=model.hazards(frame);pmf,survival=t1.pmf_from_hazard(hazard)
    return dict(Q=t1.quantiles_from_hazard(hazard),P=pmf,cdf=1-survival)


def loss(frame,quantiles):
    error=np.minimum(frame.remaining.to_numpy(),t1.CAP)[:,None]-quantiles
    return np.maximum(np.asarray(t1.QS)*error,(np.asarray(t1.QS)-1)*error).mean(1)


def main():
    path=SYNTH/'dr_comparison_v1/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if not manifest.get('complete'):raise ValueError('DR source build chưa hoàn tất')
    output=OUT/'t1/DR';output.mkdir(exist_ok=True)
    real=real_loaders.customer_invoices().copy()
    real['writeoff_date']=pd.NaT;real['is_bad_debt']=False
    real_end=real.paid_date_true.max()
    real_origin=min(pd.Timestamp('2019-10-01'),real_end-pd.Timedelta(days=183))
    experiments=[(pd.Timestamp('2024-07-01'),['tgt','sens_uk','sens_coface']),
                 (real_origin,['real_customer_invoices'])]
    source_files=['scripts/run_dr_comparison.py','agent1/data/dr_comparison.py','agent1/models/features.py','agent1/models/t1.py','agent1/calendar_vn.py','scripts/run_t1.py']
    code_sha=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in source_files)).hexdigest()
    signature=hashlib.sha256(path.read_bytes()+code_sha.encode()).hexdigest()
    cache_dir=PROCESSED/('dr_comparison_'+signature[:12]);cache_dir.mkdir(exist_ok=True)
    # Chỉ chuyển cache số học từ đúng phiên bản bị ngắt, đối chiếu mọi phụ thuộc.
    archive=output/'interrupted_v1'
    legacy=archive/'run_dr_comparison.py'
    migrated={}
    if legacy.exists():
        previous=json.loads((archive/'protocol.json').read_text(encoding='utf-8'))
        previous_sha=hashlib.sha256(legacy.read_bytes()+b''.join((ROOT/p).read_bytes() for p in source_files[1:])).hexdigest()
        if previous_sha==previous['code_sha256'] and previous['source_manifest_sha256']==hashlib.sha256(path.read_bytes()).hexdigest():
            previous_key=hashlib.sha256(path.read_bytes()+previous_sha.encode()).hexdigest()[:12]
            for old in (PROCESSED/('dr_comparison_'+previous_key)).glob('*.parquet'):
                destination=cache_dir/old.name
                if not destination.exists():shutil.copyfile(old,destination)
                migrated[old.name]=hashlib.sha256(old.read_bytes()).hexdigest()
    protocol=dict(complete=False,code_sha256=code_sha,source_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        design='one world x400 vs twenty worlds x20; same per-pair invoice counts before features',
        fit='source-only; max 40k snapshots per arm, 300 trees, same N; no target tuning',
        history='observed target histories available; zero-shot model, no target-label fitting; not M0 onboarding',
        criterion='DR pinball reduction >=5%; report paired CI by target firm; no automatic adoption',
        limitation='one generator seed design; CI does not include source-generation uncertainty; synthetic vs real calendar origins trained separately',
        target_used_for_selection=False,origins=[],
        cache_resume=dict(previous_code_sha256=previous_sha if migrated else None,validated_prepared_cache_sha256=migrated,
            scope='checkpoint/storage only; original snapshot sampling and model fitting unchanged'))
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    results=[];decisions=[]
    for origin,targets in experiments:
        arms={arm:[w for w in manifest['worlds'] if w['arm']==arm] for arm in ['one_world','twenty_worlds']}
        quota=paired_quotas(counts(arms['one_world'],origin),counts(arms['twenty_worlds'],origin))
        quota.to_csv(output/f'invoice_quotas_{origin.date()}.csv',index=False)
        maps={'one_world':dict(zip(quota.left_company,quota.n_invoices)),
              'twenty_worlds':dict(zip(quota.right_company,quota.n_invoices))}
        source={arm:prepare_arm(worlds,maps[arm],origin,cache_dir/f'{arm}_{origin.date()}.parquet') for arm,worlds in arms.items()}
        budget=min(40000,*[len(frame) for frame in source.values()]);models={}
        for arm,frame in source.items():
            frame=row_sample(frame,budget)
            models[arm]=t1.HazardGBM(rounds=300).fit(frame)
            models[arm].booster.save_model(str(cache_dir/f'{arm}_{origin.date()}.txt'))
            print('fit',arm,str(origin.date()),len(frame),'rows',flush=True)
        del source;gc.collect()
        protocol['origins'].append(dict(origin=str(origin.date()),n_source_invoices_per_arm=int(quota.n_invoices.sum()),
            n_source_firms_per_arm=400,n_train_per_arm=budget))
        for target in targets:
            if target=='real_customer_invoices':
                builder=SnapshotBuilder(real)
                test=add_labels(builder.build(pd.date_range(origin,origin+pd.Timedelta(days=63),freq='7D')),real_end)
                test['amount_open']=test.amount_gross*(1-test.paid_frac_so_far.fillna(0))
            else:
                test=censor(snapshots(target,pd.date_range(origin,periods=52,freq='7D'),tag='DR_comparison_test'),'2025-12-31')
            predictions={arm:predict(model,test) for arm,model in models.items()}
            predictions['B1d-cust-quantiles']=dict(Q=t1.b1_dist(test))
            metrics=score(predictions,test,target)
            baseline=loss(test,predictions['one_world']['Q'])
            candidate=loss(test,predictions['twenty_worlds']['Q'])
            ci=mean_ci(candidate,test.firm_id,baseline=baseline)
            for key in ['improvement_pct','improvement_ci_low','improvement_ci_high']:
                metrics.loc[metrics.model=='twenty_worlds','vs_one_world_'+key]=ci[key]
            metrics['n_source_invoices_per_arm']=int(quota.n_invoices.sum());metrics['n_source_firms_per_arm']=400
            metrics['n_train_per_arm']=budget;metrics['origin']=str(origin.date());metrics['test_used_for_selection']=False
            metrics['measurement_version']='DR-400-matched-invoices-source-only-v1-fullweek'
            results.append(metrics)
            decisions.append(dict(target=target,origin=str(origin.date()),**ci,threshold_pct=5.,
                status='supported' if ci['improvement_ci_low']>=5 else 'rejected' if ci['improvement_ci_high']<5 else 'not_demonstrated',
                candidate_adopted=False,test_used_for_selection=False,measurement_version='DR-400-matched-invoices-source-only-v1-fullweek'))
            pd.concat(results).to_csv(output/'metrics.csv',index=False)
            pd.DataFrame(decisions).to_csv(output/'decisions.csv',index=False)
            print(target,'scored',flush=True);del test,predictions;gc.collect()
    protocol['complete']=True
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
