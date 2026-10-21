from agent1.synth.world import WorldConfig
from scripts import build_big


def test_streamed_generation_records_elapsed_time_not_final_shard_index(tmp_path,monkeypatch):
    monkeypatch.setattr(build_big,'SYNTH',tmp_path)
    readings=iter([1000.,1005.])
    monkeypatch.setattr(build_big.time,'monotonic',lambda:next(readings))
    config=WorldConfig(name='timing_test',seed=901,n_firms=2,start='2023-01-01',end='2023-12-31',write_xml=0,rng_version=2)
    result=build_big.build(config,shard_size=1)
    assert result['seconds']==5.
    assert result['timing_valid'] and result['contracts_passed']
