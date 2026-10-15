import numpy as np
import pandas as pd
from agent1.models.t9_recon import Reconciler
from agent1.models.reconciliation_pipeline import build_bank_labels, choose_subset


def data():
    inv = pd.DataFrame({'invoice_id': ['i1', 'i2', 'future'], 'firm_id': ['f'] * 3,
                        'customer_id': ['c'] * 3, 'invoice_no': ['00000101', '00000102', '00000103'],
                        'issue_date': pd.to_datetime(['2024-01-01', '2024-01-01', '2025-01-01']),
                        'due_date': pd.to_datetime(['2024-02-01'] * 3), 'amount_gross': [1e6, 2e6, 4e6]})
    bank = pd.DataFrame({'txn_id': ['t1', 't2', 't3'], 'firm_id': ['f'] * 3,
                         'value_date': pd.to_datetime(['2024-02-01', '2024-02-02', '2024-02-03']),
                         'amount': [1e6, 2e6, 4e6], 'memo': ['TT HD 00000101', '', ''], 'direction': ['in'] * 3})
    return inv, bank


def test_rules_are_sequential_conserve_cash_and_reject_future_invoice():
    inv, bank = data()
    links, review = Reconciler().reconcile(bank, inv, pd.DataFrame())
    assert links.method.tolist() == ['R2_memo', 'R1_unique_amount']
    assert review.txn_id.tolist() == ['t3']
    allocated = links.groupby('txn_id').amount.sum()
    assert (allocated <= bank.set_index('txn_id').amount.reindex(allocated.index)).all()
    labels = build_bank_labels(inv, links)
    assert labels.paid_date_est.notna().tolist() == [True, True, False]


def test_latent_labels_do_not_affect_reconciliation():
    inv, bank = data()
    one = Reconciler().reconcile(bank, inv.assign(paid_date_true=pd.Timestamp('2020-01-01')), pd.DataFrame())[0]
    two = Reconciler().reconcile(bank, inv.assign(paid_date_true=pd.Timestamp('2030-01-01')), pd.DataFrame())[0]
    pd.testing.assert_frame_equal(one, two)


def test_ambiguous_subset_is_reported():
    op = pd.DataFrame({'remaining_amount': [1e6, 1e6, 2e6]})
    chosen, count = choose_subset(op, 2e6)
    assert count == 2
    assert chosen


def test_partial_link_does_not_create_settlement_date():
    inv, _ = data()
    links = pd.DataFrame({'invoice_id': ['i1'], 'txn_id': ['t'], 'est_pay_date': pd.to_datetime(['2024-02-01']), 'amount': [1e5]})
    assert build_bank_labels(inv, links).paid_date_est.isna().all()
