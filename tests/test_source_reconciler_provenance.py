import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_e2e_protocol as protocol
import run_t9


def test_holdout_refits_unidentified_cache_and_returns_training_provenance(monkeypatch,tmp_path):
    calls=[]
    saved=[]

    class Reconciler:
        @classmethod
        def load(cls,path):
            return SimpleNamespace(provenance={'target_used':False})

        def candidates(self,*args):return 'source candidates'
        def fit(self,candidates):return self
        def calibrate(self,candidates):pass
        def save(self,path,provenance):saved.append((path,provenance))

    def load(world,firms,start,end):
        calls.append((world,firms,start,end))
        return None,None,None,None

    monkeypatch.setattr(protocol,'Reconciler',Reconciler)
    monkeypatch.setattr(run_t9,'load',load)
    result=protocol.source_reconciler(tmp_path,require_training_firms=True)
    assert [call[2:] for call in calls]==[('2023-01-01','2023-12-31'),('2024-01-01','2024-06-30')]
    assert all(world=='src' and firms==[f'F{i:03d}' for i in range(12)] for world,firms,*_ in calls)
    assert result.provenance['training_firms']==calls[0][1]
    assert result.provenance['target_used'] is False
    assert saved==[(tmp_path,result.provenance)]


def test_existing_e2e_cache_keeps_default_loading_behavior(monkeypatch,tmp_path):
    cached=SimpleNamespace(provenance={'target_used':False})
    monkeypatch.setattr(protocol.Reconciler,'load',lambda path:cached)
    assert protocol.source_reconciler(tmp_path) is cached
