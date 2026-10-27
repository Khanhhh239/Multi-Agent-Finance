"""Accounting outcomes must follow dated money movements, not payment kind labels."""
import pandas as pd

from agent1.data.accounting import BANK_FLOW_CLASS, derive_invoice_accounting, mark_bank_balance_window
from agent1.synth.world import World, WorldConfig


def test_partial_payment_credit_note_and_writeoff_have_distinct_closure_labels():
    invoices = pd.DataFrame({
        'invoice_id': ['short', 'discount', 'cancelled', 'bad'],
        'amount_gross': [1000., 1000., 1000., 1000.],
        'credit_note': [0., 200., 1000., 0.],
        'credit_note_date': pd.to_datetime([None, '2024-01-10', '2024-01-10', None]),
        'writeoff_date': pd.to_datetime([None, None, None, '2024-01-20']),
        'due_date': pd.to_datetime(['2024-01-03'] * 4),
    })
    payments = pd.DataFrame({
        'payment_id': ['P1', 'P2', 'P3'],
        'invoice_id': ['short', 'discount', 'bad'],
        'amount': [900., 800., 200.],
        'pay_date_true': pd.to_datetime(['2024-01-05', '2024-01-05', '2024-01-12']),
        'ledger_post_date': pd.to_datetime(['2024-01-06', '2024-01-06', '2024-01-13']),
        'kind': ['final', 'full', 'recovery'],
    })
    result = derive_invoice_accounting(invoices, payments).set_axis(invoices.invoice_id)

    assert pd.isna(result.loc['short', 'paid_date_true'])
    assert result.loc['short', 'remaining_amount'] == 100.
    assert result.loc['short', 'closure_type'] == 'open'
    assert result.loc['discount', 'paid_date_true'] == pd.Timestamp('2024-01-10')
    assert result.loc['discount', 'closure_type'] == 'paid_after_credit_note'
    assert pd.isna(result.loc['cancelled', 'paid_date_true'])
    assert result.loc['cancelled', 'closed_date_true'] == pd.Timestamp('2024-01-10')
    assert result.loc['cancelled', 'closure_type'] == 'credit_note'
    assert pd.isna(result.loc['bad', 'paid_date_true'])
    assert result.loc['bad', 'writeoff_amount'] == 800.
    assert result.loc['bad', 'remaining_amount'] == 0.
    assert result.loc['bad', 'closure_type'] == 'writeoff'


def test_fx_adjustment_changes_bank_cash_but_not_invoice_face_payment():
    invoices = pd.DataFrame({
        'invoice_id': ['fx'], 'amount_gross': [1000.], 'credit_note': [0.],
        'credit_note_date': pd.to_datetime([None]), 'writeoff_date': pd.to_datetime([None]),
        'due_date': pd.to_datetime(['2024-01-03']),
    })
    payments = pd.DataFrame({
        'payment_id': ['P1'], 'invoice_id': ['fx'], 'amount': [1200.],
        'fx_adjustment': [200.], 'pay_date_true': pd.to_datetime(['2024-01-05']),
        'ledger_post_date': pd.to_datetime(['2024-01-06']),
    })
    result = derive_invoice_accounting(invoices, payments).iloc[0]
    assert result.paid_amount == 1000.
    assert result.cash_received_amount == 1200.
    assert result.remaining_amount == 0.
    assert result.paid_date_true == pd.Timestamp('2024-01-05')


def test_statement_flows_reconcile_to_observed_bank_account_only():
    world = World(WorldConfig(start='2024-01-01', end='2024-01-03', n_firms=1, write_xml=0))
    kinds = ['customer_payment', 'loan_disbursement', 'internal', 'cash_deposit', 'refund', 'unknown']
    bank = pd.DataFrame({
        'firm_id': ['F000'] * 7,
        'value_date': pd.to_datetime(['2024-01-02'] * 6 + ['2024-01-05']),
        'amount': [100., 200., 50., 30., 40., 20., 70.],
        'direction': ['in'] * 7,
        'txn_type': kinds + ['loan_disbursement'],
    })
    bank['cash_flow_class'] = bank.txn_type.map(BANK_FLOW_CLASS)
    bank = mark_bank_balance_window(bank, world.start, world.end)
    out = pd.DataFrame({'firm_id': ['F000'], 'date': pd.to_datetime(['2024-01-02']), 'amount': [10.]})
    firm = pd.DataFrame({'firm_id': ['F000'], 'buffer_days': [0.]})
    cash = world.cash_paths(firm, bank, out).set_index('date')
    day = cash.loc[pd.Timestamp('2024-01-02')]
    assert day.inflow_ar == 100.
    assert day.inflow_financing == 200.
    assert day.inflow_internal == 50.
    assert day.inflow_cash_deposit == 30.
    assert day.inflow_other == 340.
    assert day.balance == 430.
    assert bank.balance_effect.iloc[-1] == 0.
    assert day.balance_scope == 'operating_bank_account'
