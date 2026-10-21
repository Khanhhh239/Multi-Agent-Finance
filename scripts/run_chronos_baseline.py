"""WP-6.6: Chronos-Bolt Tiny zero-shot trên số dư, revision khoá trước, CPU."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,SYNTH,PROCESSED,ROOT
from agent1.models.chronos_context import balance_context
from agent1.eval.cluster import mean_ci

MODEL='amazon/chronos-bolt-tiny'
REVISION='a0e552de83495b5c28c14c71c374f3e33280b340'


def main():
    import torch
    from chronos import BaseChronosPipeline
    from huggingface_hub import snapshot_download
    import run_t6 as R6
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    directory=OUT/'t6/chronos';directory.mkdir(exist_ok=True)
    model_dir=PROCESSED/'models'/('chronos_bolt_tiny_'+REVISION[:12])
    snapshot_download(MODEL,revision=REVISION,allow_patterns=['config.json','model.safetensors','README.md','LICENSE'],local_dir=model_dir)
    model=BaseChronosPipeline.from_pretrained(str(model_dir),device_map='cpu',torch_dtype=torch.float32,local_files_only=True)
    reference=pd.read_parquet(OUT/'e2e/protocol/t6_predictions.parquet')
    reference=reference[reference.model=='MC-copula-t + ACI'].copy()
    daily=pd.read_parquet(SYNTH/'tgt/daily_cash.parquet')
    out=pd.read_parquet(SYNTH/'e2e_observed_tgt/outflows.parquet')
    invoices=pd.read_parquet(SYNTH/'e2e_observed_tgt/invoices.parquet',columns=['firm_id'])
    contexts=[];keys=[]
    for firm,g in reference.groupby('firm_id'):
        series=daily[daily.firm_id==firm].set_index('date').balance
        ctx=R6.firm_context('tgt',firm,invoices,out,daily)
        for cutoff,part in g.groupby('cutoff'):
            cutoff=pd.Timestamp(cutoff);scale=max(R6.known_outflows(ctx,cutoff).mean(),1.)
            _,truth=R6.truth_path(ctx,cutoff)
            if not np.allclose(part.sort_values('k').y.to_numpy(),truth/scale):raise ValueError('Không khớp chuẩn hoá E2E')
            contexts.append(balance_context(series,cutoff));keys.append((firm,cutoff,scale))
    if len(keys)!=14*52:raise ValueError('Cần đủ cohort 14×52')
    rows=[];began=time.monotonic()
    for start in range(0,len(contexts),32):
        inputs=torch.tensor(np.stack(contexts[start:start+32]),dtype=torch.float32)
        with torch.inference_mode():quantiles,_=model.predict_quantiles(inputs,prediction_length=13,quantile_levels=[.1,.5,.9])
        quantiles=quantiles.numpy()
        if not np.isfinite(quantiles).all() or (np.diff(quantiles,axis=2)<-1e-5).any():raise ValueError('Phân vị Chronos không hợp lệ')
        for ix,(firm,cutoff,scale) in enumerate(keys[start:start+32]):
            truth=reference[(reference.firm_id==firm)&(reference.cutoff==cutoff)].sort_values('k').y.to_numpy()
            for k in range(13):rows.append(dict(model='Chronos-Bolt Tiny zero-shot',firm_id=firm,cutoff=cutoff,k=k+1,
                y=truth[k],lo=quantiles[ix,k,0]/scale,med=quantiles[ix,k,1]/scale,hi=quantiles[ix,k,2]/scale))
        print('predicted',min(start+32,len(contexts)),'/',len(contexts),flush=True)
    frame=pd.DataFrame(rows);frame.to_parquet(directory/'predictions.parquet',index=False)
    combined=pd.concat([frame,reference],ignore_index=True);summary=[]
    for (name,horizon),part in combined.assign(horizon=lambda d:np.where(d.k<=4,'w1-4','w5-13')).groupby(['model','horizon']):
        coverage=part.y.between(part.lo,part.hi).astype(float)
        score=part.hi-part.lo+10*(part.lo-part.y).clip(lower=0)+10*(part.y-part.hi).clip(lower=0)
        ci=mean_ci(coverage,part.firm_id);score_ci=mean_ci(score,part.firm_id)
        errors=part.y.to_numpy()[:,None]-part[['lo','med','hi']].to_numpy()
        pinball=np.maximum(errors*np.asarray([.1,.5,.9]),errors*np.asarray([-.9,-.5,-.1])).mean()
        summary.append(dict(model=name,horizon=horizon,n=len(part),n_firms=part.firm_id.nunique(),cov80=coverage.mean(),
            cov80_ci_low=ci['ci_low'],cov80_ci_high=ci['ci_high'],IS80=score.mean(),IS80_ci_low=score_ci['ci_low'],
            IS80_ci_high=score_ci['ci_high'],pinball=pinball,MAE_p50=(part.y-part.med).abs().mean(),bootstrap_n=300,
            test_used_for_selection=False,measurement_version='chronos-bolt-tiny-zero-shot-E2E-v1'))
    pd.DataFrame(summary).to_csv(directory/'metrics.csv',index=False)
    protocol=dict(complete=True,model=MODEL,revision=REVISION,license='Apache-2.0',n_firms=14,n_weeks=52,
        context='52 weekly observed balance levels at or before cutoff',fine_tuned=False,device='cpu',batch_size=32,
        inference_seconds=time.monotonic()-began,parameters_selected_on_test=False,
        limitation='synthetic;Tiny model only;univariate balance without future obligation covariates;not evidence about all Chronos sizes',
        reference='https://huggingface.co/amazon/chronos-bolt-tiny',
        dependencies={name:importlib.metadata.version(name) for name in ['torch','chronos-forecasting','transformers']},
        code_sha256=hashlib.sha256((ROOT/'scripts/run_chronos_baseline.py').read_bytes()+(ROOT/'agent1/models/chronos_context.py').read_bytes()).hexdigest(),
        model_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in model_dir.glob('*') if p.is_file()},
        reference_sha256=hashlib.sha256((OUT/'e2e/protocol/t6_predictions.parquet').read_bytes()).hexdigest())
    (directory/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
