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


def test_newly_observed_ledger_clear_prevents_rematching_old_invoice():
    inv, bank = data()
    inv['ledger_clear_date'] = pd.to_datetime(['2024-02-01',None,None])
    bank = bank.iloc[[2]].copy()
    bank.loc[:,'amount'] = 1e6
    # Sao kê có một giao dịch đầu kỳ không khớp, trước ngày sổ tất toán i1.
    first = bank.copy(); first['txn_id']='start'; first['value_date']=pd.Timestamp('2024-01-31'); first['amount']=8e6
    links, review = Reconciler().reconcile(pd.concat([first,bank]),inv,pd.DataFrame())
    assert links.empty and len(review)==2


def test_credit_adjustment_is_only_used_after_its_observed_date():
    inv, bank = data()
    inv['credit_note']=[1e5,0,0]
    inv['credit_note_date']=pd.to_datetime(['2024-02-02',None,None])
    bank = bank.iloc[:2].copy();bank['amount']=9e5;bank['memo']=''
    links, review = Reconciler().reconcile(bank,inv,pd.DataFrame())
    assert links.txn_id.tolist()==['t2']
    assert review.txn_id.tolist()==['t1']
    assert links.amount.iloc[0]==9e5
    labelled = build_bank_labels(inv,links)
    assert labelled.set_index('invoice_id').loc['i1','paid_date_est']==pd.Timestamp('2024-02-02')


def test_future_customer_name_does_not_change_candidate_ranking():
    inv,bank=data()
    inv.loc[inv.invoice_id=='future','customer_id']='future_customer'
    bank['counterparty']='Buyer';bank['memo']='Buyer'
    customers=pd.DataFrame(dict(customer_id=['c'],firm_id=['f'],short=['Buyer']))
    future=pd.DataFrame(dict(customer_id=['future_customer'],firm_id=['f'],short=['Buyer']))
    one=Reconciler().candidates(bank,inv,customers)
    two=Reconciler().candidates(bank,inv,pd.concat([customers,future],ignore_index=True))
    pd.testing.assert_frame_equal(one,two)


def test_reconciler_text_model_roundtrip_and_hash_validation(tmp_path):
    from agent1.models.t9_recon import FEATS
    import pytest
    rng=np.random.default_rng(9)
    candidates=pd.DataFrame(rng.normal(size=(400,len(FEATS))),columns=FEATS)
    candidates['txn_id']=[f't{i}' for i in range(len(candidates))]
    candidates['customer_id']='c';candidates['y']=(candidates.name_score>0).astype(int)
    rec=Reconciler().fit(candidates).calibrate(candidates)
    rec.save(tmp_path,dict(target_used=False))
    restored=Reconciler.load(tmp_path)
    pd.testing.assert_frame_equal(rec.assign_customers(candidates),restored.assign_customers(candidates))
    with (tmp_path/'model.txt').open('a') as f:f.write('corrupted')
    with pytest.raises(ValueError,match='hash'):Reconciler.load(tmp_path)
