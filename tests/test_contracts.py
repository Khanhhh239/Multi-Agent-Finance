"""Chèn lỗi vào một thế giới nhỏ để xác nhận cổng dữ liệu bắt được."""
import pandas as pd
import pytest
from agent1.synth.world import World, WorldConfig
from agent1.data.contracts import validate_world


@pytest.fixture(scope='module')
def world_dir(tmp_path_factory):
    directory = tmp_path_factory.mktemp('world')
    World(WorldConfig(name='contract_test', seed=31, n_firms=1, start='2023-01-01', end='2024-12-31', write_xml=0)).run(directory, verbose=False)
    return directory


def test_generated_world_satisfies_contract(world_dir):
    assert validate_world(world_dir).passed.all()


@pytest.mark.parametrize('table,column,value,expected', [
    ('invoices', 'amount_gross', -1., 'invoices.amount_gross'),
    ('payments', 'invoice_id', 'missing', 'payments.invoice_id.foreign_key'),
    ('daily_cash', 'balance', 1e30, 'daily_cash.balance'),
    ('customers', 'mst', '0000000000', 'customers.mst'),
])
def test_corrupted_world_is_rejected(world_dir, table, column, value, expected):
    path = world_dir / f'{table}.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    df.loc[0, column] = value
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc[expected, 'passed']
        with pytest.raises(ValueError, match='Hợp đồng'):
            validate_world(world_dir)
    finally:
        path.write_bytes(original)
