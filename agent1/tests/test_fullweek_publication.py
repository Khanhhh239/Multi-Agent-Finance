import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_e2e_protocol import publish_metrics


def test_fullweek_watcher_cannot_see_incomplete_oracle_as_final(tmp_path):
    target=tmp_path/'e2e_metrics.csv';target.write_text('legacy evidence',encoding='utf-8')
    frame=pd.DataFrame(dict(full_protocol=[True],oracle_ablation_completed=[False],measurement_version=['new-fullweek']))
    with pytest.raises(ValueError,match='oracle'):publish_metrics(frame,tmp_path)
    assert target.read_text(encoding='utf-8')=='legacy evidence'
    frame['oracle_ablation_completed']=True
    publish_metrics(frame,tmp_path)
    assert pd.read_csv(target).measurement_version.str.endswith('fullweek').all()
    assert not (tmp_path/'e2e_metrics.ready.csv').exists()
    frame['full_protocol']=False
    publish_metrics(frame,tmp_path,require_full=False)
    assert not pd.read_csv(target).full_protocol.any()
