"""G3: global CQR hai phía so Mondrian; cùng dự báo nguồn của A fullweek."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from agent1.models import t1
from agent1.models.mondrian_cqr import MondrianCQR
from agent1.eval.cluster import mean_ci


def interval_scores(y,q):
    low,high=q[:,0],q[:,-1]
    return high-low+10*(low-y)*(y<low)+10*(y-high)*(y>high)


def main():
    directory=ROOT/'outputs/t1/G3';directory.mkdir(exist_ok=True)
    rows=[];sources={}
    for origin in ['2023-07-03','2024-07-01']:
        source=ROOT/'outputs/t1/fullweek_A'/origin
        protocol=json.loads((source/'protocol.json').read_text(encoding='utf-8'))
        if not protocol['expand_full_week_only'] or protocol['test_used_for_selection']:raise ValueError('Cần A fullweek nguồn')
        cal=pd.read_parquet(source/'calibration.parquet');test=pd.read_parquet(source/'test.parquet')
        for name in ['calibration.parquet','test.parquet','protocol.json']:
            sources[f'{origin}/{name}']=hashlib.sha256((source/name).read_bytes()).hexdigest()
        qc=cal[['Q10','Q50','Q90']].to_numpy();qt=test[['Q10','Q50','Q90']].to_numpy()
        global_q=t1.cqr_fit_asym(cal.remaining.to_numpy(),qc,allow_shrink=True)
        mondrian=MondrianCQR(min_group=100).fit(cal.remaining.to_numpy(),qc,cal.days_to_due)
        estimates={'raw':qt,'global_two_sided':t1.cqr_apply_asym(qt,global_q),
            'mondrian_two_sided':mondrian.apply(qt,test.days_to_due)}
        y=np.minimum(test.remaining.to_numpy(),t1.CAP);baseline=interval_scores(y,estimates['global_two_sided'])
        for name,q in estimates.items():
            covered=((y>=q[:,0])&(y<=q[:,-1])).astype(float);scores=interval_scores(y,q)
            cov_ci=mean_ci(covered,test.firm_id);score_ci=mean_ci(scores,test.firm_id,baseline=baseline)
            rows.append(dict(origin=origin,model=name,cov80=covered.mean(),cov80_ci_low=cov_ci['ci_low'],cov80_ci_high=cov_ci['ci_high'],
                IS80=scores.mean(),vs_global_IS_improvement_pct=score_ci['improvement_pct'],
                improvement_ci_low=score_ci['improvement_ci_low'],improvement_ci_high=score_ci['improvement_ci_high'],
                n=len(test),n_firms=cov_ci['n_firms'],bootstrap_n=300,test_used_for_selection=False,
                measurement_version='G3-source-mondrian-two-sided-v1-fullweek'))
        (directory/f'offsets_{origin}.json').write_text(json.dumps(dict(global_offsets=global_q,
            group_offsets=mondrian.offsets,group_counts=mondrian.counts,min_group=100),indent=2),encoding='utf-8')
    frame=pd.DataFrame(rows);frame.to_csv(directory/'metrics.csv',index=False)
    candidate=frame[frame.model=='mondrian_two_sided'];reference=frame[frame.model=='global_two_sided']
    eligible=bool(len(candidate)==2 and candidate.cov80.between(.75,.85).all() and (candidate.IS80.to_numpy()<=reference.IS80.to_numpy()).all())
    (directory/'protocol.json').write_text(json.dumps(dict(complete=True,eligible=eligible,candidate='mondrian_two_sided',
        criterion='both origins cov80 [.75,.85]; IS80 <= global two-sided at each origin',
        calibration='source only, same pre-origin model; minimum group 100 fixed before test',
        test_used_for_selection=False,input_sha256=sources),indent=2),encoding='utf-8')
    print(frame.to_string(index=False));print('G3 eligible',eligible)


if __name__=='__main__':main()
