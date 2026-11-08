"""CI cặp E2E ACI so từng đối chứng đã lưu; không fit/chọn lại mô hình."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT
from agent1.eval.cluster import mean_ci


def losses(frame):
    residual=frame.y.to_numpy()[:,None]-frame[['lo','med','hi']].to_numpy()
    return dict(IS80=(frame.hi-frame.lo+10*(frame.lo-frame.y).clip(lower=0)+10*(frame.y-frame.hi).clip(lower=0)).to_numpy(),
        pinball=np.maximum(residual*np.asarray([.1,.5,.9]),residual*np.asarray([-.9,-.5,-.1])).mean(1),
        MAE=np.abs(residual[:,1]))


def main():
    provenance=pd.read_csv(OUT/'e2e/e2e_metrics.csv')
    current=provenance.measurement_version.fillna('').str.contains('fullweek').all() and provenance.oracle_ablation_completed.all()
    reference=pd.read_parquet(OUT/'e2e/protocol/t6_predictions.parquet')
    reference=reference[reference.model=='MC-copula-t + ACI'].copy()
    parts=[]
    for path in [OUT/'t6/traditional/predictions.parquet',OUT/'t6/chronos/predictions.parquet']:
        if path.exists():parts.append(pd.read_parquet(path))
    challengers=pd.concat(parts,ignore_index=True);rows=[]
    keys=['firm_id','cutoff','k']
    for (model,horizon),part in challengers.assign(horizon=lambda d:np.where(d.k<=4,'w1-4','w5-13')).groupby(['model','horizon']):
        joined=part.merge(reference,on=keys,suffixes=('','_main'),validate='one_to_one')
        if len(joined)!=len(part) or not np.allclose(joined.y,joined.y_main):raise ValueError('Cohort/nhãn không khớp')
        main_frame=joined.rename(columns={c:c+'_challenger' for c in ['lo','med','hi','y']})
        main_frame=main_frame.rename(columns={c+'_main':c for c in ['lo','med','hi','y']})
        main_loss,challenger_loss=losses(main_frame),losses(joined)
        for metric in main_loss:
            ci=mean_ci(main_loss[metric],joined.firm_id,baseline=challenger_loss[metric])
            rows.append(dict(main='MC-copula-t + ACI',challenger=model,horizon=horizon,metric=metric,
                main_loss=main_loss[metric].mean(),challenger_loss=challenger_loss[metric].mean(),
                main_improvement_pct=ci['improvement_pct'],main_improvement_ci_low=ci['improvement_ci_low'],
                main_improvement_ci_high=ci['improvement_ci_high'],n_firms=ci['n_firms'],bootstrap_n=300,
                main_beats_challenger_with_CI=ci['improvement_ci_low']>0,test_used_for_selection=False,
                measurement_version='cash-paired-additional-baselines-v1'+('-fullweek' if current else '-legacy-expand')))
    pd.DataFrame(rows).to_csv(OUT/'t6/additional_baseline_comparisons.csv',index=False)


if __name__=='__main__':main()
