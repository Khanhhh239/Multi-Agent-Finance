"""Sửa duy nhất phân phối mốc điểm của A; mô hình và phân vị đã đo không đổi."""
import sys
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_t1 as R
from agent1.models import t1


def main():
    path=R.RES/'A_rolling_origin_src.csv'
    old=pd.read_csv(path)
    archive=path.with_name('A_rolling_origin_src.v2_before_point_fix.csv')
    if not archive.exists():shutil.copy2(path,archive)
    S=R.snapshots('src',pd.date_range('2019-07-01','2025-09-29',freq='7D'),tag='weekly')
    rows=[];strata=[]
    for setting in old.setting.unique():
        O=pd.Timestamp(setting[-10:])
        te=R.censor(S[(S.cutoff>=O)&(S.cutoff<O+pd.Timedelta(days=182))],'2025-12-31')
        points={name:{'Q':np.column_stack([fn(te)]*3)} for name,fn in [('B0-due',t1.b0_predict),('B1-cust-median',t1.b1_predict)]}
        points['B1d-cust-quantiles']={'Q':t1.b1_dist(te)}
        rows.append(R.score(points,te,setting,strata_rows=strata))
    updated=pd.concat(rows,ignore_index=True)
    check=updated.merge(old[['setting','model','pinball_avg']],on=['setting','model'],suffixes=('','_old'))
    if not np.allclose(check.pinball_avg,check.pinball_avg_old,rtol=1e-6):
        raise ValueError('Đặc trưng/nhãn đã đổi; cần chạy lại A đầy đủ thay vì chỉ chấm lại mốc điểm')
    kept=old[~old.model.isin(updated.model.unique())]
    result=pd.concat([kept,updated],ignore_index=True)
    result['measurement_version']='asof-pchip-v3-point-mass'
    result.to_csv(path,index=False)
    strata_path=R.RES/'A_strata.csv'
    previous=pd.read_csv(strata_path)
    pd.concat([previous[~previous.model.isin(updated.model.unique())],pd.DataFrame(strata)],ignore_index=True).to_csv(strata_path,index=False)


if __name__=='__main__':main()
