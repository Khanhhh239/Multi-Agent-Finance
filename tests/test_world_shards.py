import pandas as pd
import pytest
from agent1.synth.world import World,WorldConfig
from scripts.build_big import merge_shards
from agent1.data.contracts import validate_world


def test_sharding_preserves_world_values_and_global_payment_keys(tmp_path):
    cfg=WorldConfig(seed=83,n_firms=2,rng_version=2,start='2023-01-01',end='2024-12-31',write_xml=0)
    whole=World(cfg).run(tmp_path/'whole',verbose=False)
    parts=[World(cfg).run(tmp_path/f'shard{i}',verbose=False,firm_indices=[i]) for i in range(2)]
    merged=tmp_path/'merged';merge_shards(parts,merged)
    assert validate_world(merged).passed.all()
    for table in whole.glob('*.parquet'):
        pd.testing.assert_frame_equal(pd.read_parquet(table),pd.read_parquet(merged/table.name),check_dtype=False)
    with pytest.raises(ValueError,match='RNG v2'):
        World(WorldConfig(n_firms=2,rng_version=1)).run(tmp_path/'invalid',verbose=False,firm_indices=[1])
