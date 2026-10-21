import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_gates


@pytest.mark.parametrize('f1,status',[(.79,'failed'),(.8,'passed')])
def test_high_precision_alone_cannot_bypass_wp4_f1_floor(tmp_path,monkeypatch,f1,status):
    output=tmp_path/'outputs';(output/'t9').mkdir(parents=True);(output/'implementation').mkdir()
    (tmp_path/'docs/03_Evaluation').mkdir(parents=True)
    frame=pd.DataFrame([dict(method='Hybrid',link_f1=f1,link_precision=.96,auto_txn_coverage=.7,pay_date_MAE_est_days=2.),
                        dict(method='R1',link_f1=.6),dict(method='R2',link_f1=.5)])
    frame['measurement_version']='test-boundary'
    frame.to_csv(output/'t9/t9_reconciliation_tgt.csv',index=False)
    monkeypatch.setattr(evaluate_gates,'OUT',output);monkeypatch.setattr(evaluate_gates,'ROOT',tmp_path)
    evaluate_gates.main()
    gates=pd.read_csv(output/'implementation/gates.csv').set_index('gate')
    assert gates.loc['G15','status']==status
