"""A deliberately short second payment must not strand a small AR balance forever."""
import numpy as np
import pandas as pd
import pytest

from agent1.data.accounting import derive_invoice_accounting
from agent1.synth.world import World, WorldConfig


def _settlement_inputs(world, n=1200):
    issue = int(world.cal.idx(np.datetime64('2023-01-02')))
    invoices = pd.DataFrame({'ci': np.zeros(n, dtype=int),
                             'issue_i': np.full(n, issue),
                             'net': np.full(n, 10_000_000.)})
    customer = pd.DataFrame({'term_days': [14], 'ontime_logit': [100.], 'early_p': [0.],
                             'late_med': [35.], 'late_sig': [.5], 'ultra_p': [0.],
                             'break_day': [-1], 'break_shift': [0.], 'dispute_p': [0.],
                             'payrun': ['adhoc'], 'tet_settle_p': [0.], 'partial_p': [1.]})
    liquidity = np.zeros((1, world.W))
    stress = np.zeros(world.W)
    firm = {'firm_id': 'F000', 'industry': 'services'}
    return firm, customer, invoices, liquidity, stress


def _dates(world, indices):
    indices = np.asarray(indices)
    return pd.Series(pd.to_datetime(world.cal.date(np.maximum(indices, 0)))).where(indices >= 0)


def _accounting(world, settled, payments):
    ids = pd.Series([f'I{i:05d}' for i in range(len(settled))])
    invoice_truth = pd.DataFrame({
        'invoice_id': ids, 'amount_gross': settled.amount_gross,
        'credit_note': settled.credit_note,
        'credit_note_date': _dates(world, settled.credit_note_i),
        'writeoff_date': _dates(world, settled.writeoff_i),
        'due_date': _dates(world, settled.due_i),
    })
    payment_truth = pd.DataFrame({
        'payment_id': [f'P{i:05d}' for i in range(len(payments))],
        'invoice_id': ids.iloc[payments.k.to_numpy()].to_numpy(),
        'amount': payments.amount.to_numpy(),
        'pay_date_true': _dates(world, payments.day_i),
        'ledger_post_date': _dates(world, payments.day_i),
    })
    return derive_invoice_accounting(invoice_truth, payment_truth)


def test_short_second_payment_is_followed_by_full_settlement():
    world = World(WorldConfig(seed=95318, start='2023-01-01', end='2024-12-31',
                              n_firms=1, write_xml=0, rng_version=3))
    firm, customer, invoices, liquidity, stress = _settlement_inputs(world)
    settled, payments = world.settle(firm, customer, invoices, liquidity,
                                     np.array([-1]), stress)
    short_ids = payments.loc[payments.kind.eq('partial')].groupby('k').size()
    short_ids = short_ids.index[short_ids.ge(2)]
    assert len(short_ids) > 20
    final = payments.loc[payments.kind.eq('final')].set_index('k')
    assert final.index.is_unique
    assert set(short_ids).issubset(final.index)
    second_day = payments.loc[payments.kind.eq('partial')].groupby('k').day_i.max()
    assert (final.loc[short_ids, 'day_i'].to_numpy() >=
            second_day.loc[short_ids].to_numpy() + 7).all()

    accounting = _accounting(world, settled, payments)
    assert accounting.loc[short_ids, 'closure_type'].eq('paid').all()
    assert accounting.loc[short_ids, 'remaining_amount'].eq(0).all()
    assert accounting.loc[short_ids, 'paid_date_true'].notna().all()


@pytest.mark.parametrize('end,default_day,closure', [
    pytest.param('2024-12-31', 10, 'writeoff', id='default-writeoff'),
    pytest.param('2023-03-31', -1, 'open', id='observation-end-censored'),
])
def test_unsettled_short_residual_has_expected_lifecycle(monkeypatch, end, default_day, closure):
    world = World(WorldConfig(seed=95318, start='2023-01-01', end=end,
                              n_firms=1, write_xml=0, rng_version=3))
    firm, customer, invoices, liquidity, stress = _settlement_inputs(world, n=400)
    calls = []

    def scheduled_then_unsettled(cal, week0_i, customer_i, start_i, *args, **kwargs):
        if not len(start_i):
            return np.empty(0, dtype=int)
        calls.append(len(start_i))
        return np.asarray(start_i).copy() if len(calls) == 1 else np.full(len(start_i), -1)

    monkeypatch.setattr('agent1.synth.world.weekly_payment_dates', scheduled_then_unsettled)
    settled, payments = world.settle(firm, customer, invoices, liquidity,
                                     np.array([default_day]), stress)
    short_ids = payments.loc[payments.kind.eq('partial')].groupby('k').size()
    short_ids = short_ids.index[short_ids.ge(2)]
    assert len(short_ids) > 5 and len(calls) == 2
    assert not payments.loc[payments.k.isin(short_ids), 'kind'].eq('final').any()
    accounting = _accounting(world, settled, payments)
    assert accounting.loc[short_ids, 'closure_type'].eq(closure).all()
    if closure == 'writeoff':
        assert settled.loc[short_ids, 'writeoff_i'].ge(0).all()
        assert settled.loc[short_ids, 'is_bad_debt'].all()
        assert accounting.loc[short_ids, 'writeoff_amount'].gt(0).all()
        assert accounting.loc[short_ids, 'remaining_amount'].eq(0).all()
    else:
        assert settled.loc[short_ids, 'writeoff_i'].eq(-1).all()
        assert accounting.loc[short_ids, 'remaining_amount'].gt(0).all()
