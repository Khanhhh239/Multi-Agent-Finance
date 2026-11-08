"""Thay đổi lời hứa không được đổi các bảng tiền; RNG v2 giữ nền các hard-case."""
from pathlib import Path
import pandas as pd
from agent1.synth.world import World,WorldConfig


def test_noisy_promises_preserve_all_financial_tables(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    common=dict(seed=31,n_firms=1,start='2023-01-01',end='2024-12-31',write_xml=0)
    World(WorldConfig(**common)).run(a,verbose=False)
    World(WorldConfig(**common,promises_mode='noisy')).run(b,verbose=False)
    for name in ['invoices','payments','bank_txns','outflows','daily_cash','customers','firms','macro']:
        pd.testing.assert_frame_equal(pd.read_parquet(a/f'{name}.parquet'),pd.read_parquet(b/f'{name}.parquet'))
    assert not pd.read_parquet(a/'promises.parquet').equals(pd.read_parquet(b/'promises.parquet'))
