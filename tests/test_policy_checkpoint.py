import importlib
from pathlib import Path


def test_windows_checkpoint_resumes_known_metadata_only_change(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    compatible=importlib.import_module('run_collection_policy').compatible_checkpoint
    old=dict(code={'scripts\\run_collection_policy.py':'8493b8d3b655fd164af00072d22c11f8458c988ef601a3f6b1e6c44b449c6340',
        'agent1\\eval\\collection_policy.py':'AR-v2'},inputs={'src':'unchanged'},seed=7)
    current=dict(code={'scripts/run_collection_policy.py':'metadata-fixed','agent1/eval/collection_policy.py':'AR-v2'},
        inputs={'src':'unchanged'},seed=7)
    assert compatible(old,current)
    current['code']['agent1/eval/collection_policy.py']='different-financial-logic'
    assert not compatible(old,current)
    current['code']['agent1/eval/collection_policy.py']='AR-v2';current['inputs']['src']='different-data'
    assert not compatible(old,current)
