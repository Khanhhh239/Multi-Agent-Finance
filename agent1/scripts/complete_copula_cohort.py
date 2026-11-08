"""Giữ dự báo v1 đúng ở tuần có AR; bổ sung đúng 14 tuần rỗng đã bị bỏ, không fit lại.

Đây là sửa cohort bằng cùng mô hình/seed, không chọn lại tham số trên test.
Chỉ chấp nhận đúng phiên bản đã kiểm chứng; đổi dữ liệu/mô hình phải chạy đầy đủ.
"""
import json
from pathlib import Path
import sys
import lightgbm as lgb
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import ROOT,OUT,SYNTH
from agent1.models.features import SnapshotBuilder
from agent1.models.t1 import HazardGBM
from run_collection_policy import file_hash
from run_copula_hierarchy import tables,portfolio_rows,summarize


def main():
    legacy=OUT/'t6/copula_hierarchy_v1_missing_empty_AR';directory=OUT/'t6/copula_hierarchy'
    protocol=json.loads((legacy/'protocol.json').read_text(encoding='utf-8'));old=protocol['signature']
    if not protocol.get('complete') or old['code']['scripts/run_copula_hierarchy.py']!='7bc33b600ea099b7da2be46b48f75c6fecf804ba938f6b8957798f0c225a75ed':
        raise ValueError('Không phải phiên bản v1 đã kiểm')
    if file_hash(legacy/'metrics.csv')!=protocol['metrics_sha256']:raise ValueError('Metrics v1 hỏng')
    for name,digest in old['data'].items():
        if file_hash(SYNTH/name)!=digest:raise ValueError('Dữ liệu đã đổi')
    for name,digest in old['code'].items():
        if name not in {'scripts/run_copula_hierarchy.py','scripts/run_collection_policy.py','agent1/eval/collection_policy.py'} and file_hash(ROOT/name)!=digest:
            raise ValueError('Mã mô hình/đặc trưng đã đổi')
    model_path=OUT/'t6/collection_policy_v1_credit_residual_legacy/T1_oracle_policy.txt'
    if file_hash(model_path)!=old['target_model']:raise ValueError('Sai mô hình T1 cố định')
    grid=pd.read_csv(legacy/'source_grid.csv')
    if len(grid)!=9 or not grid.n.eq(4*13*13).all():raise ValueError('Nguồn chưa đủ cohort, cần chạy đầy đủ')
    choices={name:tuple(values) for name,values in protocol['choices'].items()}
    best=grid.sort_values(['IS80','rho_customer','rho']).iloc[0]
    one=grid[grid.rho_customer==0].sort_values(['IS80','rho']).iloc[0]
    if choices['source_selected_hierarchical']!=(best.rho,best.rho_customer) or choices['source_selected_one_factor']!=(one.rho,0.):raise ValueError('Lệch tham số nguồn')
    previous=pd.read_parquet(legacy/'predictions.parquet')
    for row in pd.read_csv(legacy/'metrics.csv').query("horizon == 'all'").itertuples():
        part=previous[previous.model==row.model]
        if len(part)!=row.n or not np.isclose(part.IS80.mean(),row.IS80,rtol=0,atol=1e-10):raise ValueError('Dự báo v1 không khớp điểm đã ghi')
    model=HazardGBM();model.booster=lgb.Booster(model_file=str(model_path));data=tables('tgt')
    cuts=pd.date_range('2024-07-01',periods=52,freq='7D');added=[];checked=False
    for firm in sorted(data['invoices'].firm_id.unique()):
        builder=SnapshotBuilder(data['invoices'][data['invoices'].firm_id==firm],data['payments'][data['payments'].firm_id==firm],None)
        for cutoff in cuts:
            existing=previous[(previous.firm_id==firm)&(previous.cutoff==cutoff)]
            if len(existing):
                if not checked:
                    replay=pd.DataFrame(portfolio_rows('tgt',firm,data,[cutoff],model,choices,week_offset=int(cuts.get_loc(cutoff))))
                    left=existing.sort_values(['model','k']);right=replay.sort_values(['model','k'])
                    np.testing.assert_allclose(left[['lo','med','hi','y']],right[['lo','med','hi','y']],rtol=0,atol=1e-10)
                    checked=True
                continue
            if not builder.snapshot(cutoff).empty:raise ValueError('Không chỉ thiếu tuần rỗng, phải chạy đầy đủ')
            # Giữ vị trí tuần gốc để seed CRN đúng; chỉ chạy cutoff thiếu qua cùng hàm.
            rows=portfolio_rows('tgt',firm,data,[cutoff],model,choices,week_offset=int(cuts.get_loc(cutoff)))
            added.extend(rows)
    if len(added)!=14*3*13:raise ValueError('Số tuần thiếu không khớp v1 đã kiểm')
    frame=pd.concat([previous,pd.DataFrame(added)],ignore_index=True)
    frame.to_parquet(directory/'predictions.parquet',index=False)
    summarize(frame).to_csv(directory/'metrics.csv',index=False)
    (directory/'source_grid.csv').write_bytes((legacy/'source_grid.csv').read_bytes())
    protocol.update(complete=True,empty_AR_weeks_added=14,n_target_contexts=14*52,
        correction='Reuse nonempty predictions with unchanged marginals/model; replay checked; add only verified empty-AR weeks; source calibration already complete',
        base_predictions_sha256=file_hash(legacy/'predictions.parquet'),target_model_artifact=str(model_path.relative_to(ROOT)),
        correction_code_sha256={p:file_hash(ROOT/p) for p in ['scripts/complete_copula_cohort.py','scripts/run_copula_hierarchy.py','agent1/eval/cash_cohort.py','agent1/eval/collection_policy.py']},
        metrics_sha256=file_hash(directory/'metrics.csv'))
    (directory/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    print('copula full cohort',len(frame),'rows')


if __name__=='__main__':main()
