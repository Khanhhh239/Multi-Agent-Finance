"""Đối chiếu P2 với P1 theo cùng công ty/q; không chọn q từ kết quả test."""
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT
from agent1.eval.cluster import mean_ci


def main():
    directory=OUT/'t6/collection_policy'
    protocol=json.loads((directory/'protocol.json').read_text(encoding='utf-8'))
    if not protocol.get('complete'):raise ValueError('Chính sách chưa chạy đủ')
    if hashlib.sha256((directory/'metrics.csv').read_bytes()).hexdigest()!=protocol['metrics_sha256']:raise ValueError('Metrics hash lệch')
    frame=pd.read_csv(directory/'company_metrics.csv');rows=[]
    current=frame.measurement_version.fillna('').str.contains('fullweek').all()
    for q in [.3,.5,.7]:
        baseline=frame[(frame.policy=='P1-largest')&(frame.q==q)].set_index('firm_id').sort_index()
        candidate=frame[(frame.policy=='P2-delta')&(frame.q==q)].set_index('firm_id').sort_index()
        if not baseline.index.equals(candidate.index) or len(baseline)!=14:raise ValueError('Cohort P1/P2 không khớp')
        for metric in ['shortfall_events','shortfall_weeks','DSO']:
            reduction=baseline[metric]-candidate[metric];ci=mean_ci(reduction,reduction.index)
            rows.append(dict(q=q,metric=metric,mean_P1=baseline[metric].mean(),mean_P2=candidate[metric].mean(),
                reduction_P2_vs_P1=reduction.mean(),reduction_ci_low=ci['ci_low'],reduction_ci_high=ci['ci_high'],
                n_firms=14,bootstrap_n=300,decision='supported' if ci['ci_low']>0 else 'rejected' if ci['ci_high']<0 else 'not_demonstrated',
                evidence_type='policy_simulation_not_causal',test_used_for_selection=False,
                measurement_version='collection-policy-paired-v1'+('-fullweek' if current else '-legacy-expand')))
    pd.DataFrame(rows).to_csv(directory/'P2_vs_P1.csv',index=False)


if __name__=='__main__':main()
