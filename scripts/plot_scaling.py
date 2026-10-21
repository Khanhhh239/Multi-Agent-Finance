"""Bảng/đường scaling; M* khóa trước là pinball <=90% B1d tại cùng M."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT


def main():
    files=sorted(p for p in (OUT/'t1').glob('scaling_[0-9]*.csv') if '.legacy_expand' not in p.name)
    if not files:return
    df=pd.concat([pd.read_csv(path) for path in files],ignore_index=True)
    df.to_csv(OUT/'t1/scaling_results.csv',index=False)
    rows=[]
    for size,g in df.groupby('expanded_rows'):
        months=[]
        for m,part in g.groupby('months_history'):
            base=part[part.model=='B1d-cust-quantiles'].pinball_avg.iloc[0]
            strategy='pretrained zero-shot' if m==0 else 'fine-tuned'
            best=part[part.model==strategy].pinball_avg.iloc[0]
            if best<=.9*base:months.append(m)
        rows.append(dict(expanded_rows=size,M_star=min(months) if months else np.nan,
            criterion='zero-shot M0, fine-tune M>0; pinball <=0.9*B1d at same M (predeclared)',measurement_version='scaling-nested-expanded-v1-fullweek'))
    summary=pd.DataFrame(rows)
    loss_files=sorted(p for p in (OUT/'t1').glob('scaling_company_losses_*.csv') if '.legacy_expand' not in p.name)
    if loss_files:
        losses=pd.concat([pd.read_csv(path) for path in loss_files],ignore_index=True)
        firms=sorted(losses.firm_id.unique());rng=np.random.default_rng(7)
        index=rng.integers(0,len(firms),size=(300,len(firms)));boot={}
        for size,g in losses.groupby('expanded_rows'):
            hits=[];months=sorted(g.months_history.unique())
            for month in months:
                part=g[g.months_history==month].set_index(['model','firm_id'])
                strategy='pretrained zero-shot' if month==0 else 'fine-tuned'
                model=part.loc[strategy].loss_sum.reindex(firms).to_numpy()
                baseline=part.loc['B1d-cust-quantiles'].loss_sum.reindex(firms).to_numpy()
                hits.append(model[index].sum(1)<=.9*baseline[index].sum(1))
            hits=np.asarray(hits).T
            values=np.where(hits.any(1),np.asarray(months)[hits.argmax(1)],np.inf)
            boot[size]=values;ordered=np.sort(values)
            summary.loc[summary.expanded_rows==size,'M_star_ci_low']=ordered[7]
            summary.loc[summary.expanded_rows==size,'M_star_ci_high']=ordered[292]
            summary.loc[summary.expanded_rows==size,'prob_reaches_by_24m']=np.isfinite(values).mean()
        if len(boot)>1:
            smallest,largest=min(boot),max(boot)
            summary['paired_prob_largest_needs_less_history_than_smallest']=np.mean(boot[largest]<boot[smallest])
        summary['bootstrap_n']=300;summary['unreached_encoded_as']='inf'
    summary.to_csv(OUT/'t1/scaling_M_star.csv',index=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,5))
    g=df[(df.model=='pretrained zero-shot')&(df.months_history==0)].sort_values('expanded_rows')
    ax.errorbar(g.expanded_rows,g.pinball_avg,
        yerr=np.vstack([g.pinball_avg-g.pinball_ci_low,g.pinball_ci_high-g.pinball_avg]),
        marker='o',capsize=5,label='Zero-shot M=0; company bootstrap 95% CI')
    ax.set(xscale='log',xlabel='Expanded training rows',ylabel='Mean pinball (days)')
    ax.set_xticks(g.expanded_rows,[f'{int(value/1000000)}M' for value in g.expanded_rows])
    ax.legend();fig.tight_layout();fig.savefig(OUT/'t1/scaling_curve.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
