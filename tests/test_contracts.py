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


def test_supplier_cash_and_credit_terms_are_dated_and_reconciled(world_dir, tmp_path):
    credit = pd.read_parquet(world_dir / 'inventory_weekly.parquet')
    bought_credit = credit[credit.purchase_gross.gt(0)]
    assert bought_credit.supplier_due_date.gt(bought_credit.purchase_date).all()
    assert bought_credit.supplier_pay_date.ge(bought_credit.supplier_due_date).all()
    cash_dir = tmp_path / 'cash_supplier'
    World(WorldConfig(name='cash_supplier', seed=31, n_firms=1,
                      start='2023-01-01', end='2024-12-31', write_xml=0,
                      supplier_cash_firm_p=1, rng_version=3)).run(cash_dir, verbose=False)
    cash = pd.read_parquet(cash_dir / 'inventory_weekly.parquet')
    bought_cash = cash[cash.purchase_gross.gt(0)]
    assert not bought_cash.empty
    assert bought_cash.supplier_payment_mode.eq('cash').all()
    assert bought_cash.purchase_date.eq(bought_cash.supplier_due_date).all()
    assert bought_cash.purchase_date.eq(bought_cash.supplier_pay_date).all()
    assert validate_world(cash_dir).passed.all()


@pytest.mark.parametrize('table,column,value,expected', [
    ('invoices', 'amount_gross', -1., 'invoices.amount_gross'),
    ('payments', 'invoice_id', 'missing', 'payments.invoice_id.foreign_key'),
    ('daily_cash', 'balance', 1e30, 'daily_cash.balance'),
    ('customers', 'mst', '0000000000', 'customers.mst'),
    ('macro', 'published_date', pd.Timestamp('2000-01-01'), 'macro.published_after_week'),
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


def test_false_final_payment_label_is_rejected(world_dir):
    path = world_dir / 'invoices.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    df.loc[0, 'paid_date_true'] = pd.Timestamp('2099-01-01')
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc['invoices.paid_date_true.reconciled', 'passed']
    finally:
        path.write_bytes(original)


def test_unrecorded_statement_inflow_is_rejected(world_dir):
    path = world_dir / 'bank_txns.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    row = df.index[(df.txn_type != 'customer_payment') &
                   (df.value_date <= pd.Timestamp('2024-12-31'))][0]
    df.loc[row, 'amount'] += 1_000_000.
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc['bank_txns.balance_effect', 'passed']
    finally:
        path.write_bytes(original)


def test_statement_inflow_missing_from_daily_balance_is_rejected(world_dir):
    path = world_dir / 'bank_txns.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    row = df.index[(df.txn_type != 'customer_payment') & df.in_balance_window][0]
    flow = df.loc[row, 'cash_flow_class']
    field = {
        'financing': 'inflow_financing', 'internal_transfer': 'inflow_internal',
        'cash_to_bank': 'inflow_cash_deposit', 'other_external': 'inflow_other_external',
        'unclassified': 'inflow_unclassified',
    }[flow]
    df.loc[row, ['amount', 'balance_effect']] += 1_000_000.
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc[f'daily_cash.{field}.bank_reconciled', 'passed']
    finally:
        path.write_bytes(original)


def test_inventory_purchase_without_supplier_cash_is_rejected(world_dir):
    path = world_dir / 'inventory_weekly.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    row = df.index[df.purchase_gross.gt(0)][0]
    df.loc[row, 'purchase_gross'] += 1_000_000.
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc['inventory_weekly.supplier_cash_reconciled', 'passed']
    finally:
        path.write_bytes(original)


def test_credit_hold_without_two_observed_weak_signals_is_rejected(world_dir):
    path = world_dir / 'events.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    rows = df.index[df.type.eq('seller_credit_hold')]
    if not len(rows):
        pytest.skip('This random world did not emit a credit hold')
    df.loc[rows[0], 'previous_signal'] = 0.
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc['events.credit_decision_observed_signal', 'passed']
    finally:
        path.write_bytes(original)


def test_censored_invoice_cannot_be_called_bad_debt(world_dir):
    path = world_dir / 'invoices.parquet'
    original = path.read_bytes()
    df = pd.read_parquet(path)
    rows = df.index[df.outcome_status_at_end.eq('censored')]
    assert len(rows)
    df.loc[rows[0], 'is_bad_debt'] = True
    df.to_parquet(path, index=False)
    try:
        result = validate_world(world_dir, raise_on_error=False).set_index('check')
        assert not result.loc['invoices.bad_debt_confirmed_only', 'passed']
    finally:
        path.write_bytes(original)
