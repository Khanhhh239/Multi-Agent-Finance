from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from agent1.models.t9_source_policy import retention_components,ObservedAllocationPolicy,hazard_subset
from agent1.models.t9_fast import reconcile_arrays
from agent1.models.t9_recon import Reconciler


def invoices():
    return pd.DataFrame(dict(invoice_id=['a','b'],firm_id=['f','f'],customer_id=['c','c'],invoice_no=[101,102],
        issue_date=pd.to_datetime(['2024-01-01','2024-01-02']),due_date=pd.to_datetime(['2024-02-01','2024-01-02']),
        amount_gross=[1000000.,1000000.],remaining_amount=[1000000.,1000000.]))


def test_retention_needs_known_contract_and_preserves_parent_amount():
    contract=dict(invoice_id='a',known_at='2024-01-02',source='HĐ đã nhận',amount=50000,due_date='2026-01-01')
    assert retention_components(invoices(),[contract],'2024-01-01').empty
    result=retention_components(invoices(),[contract],'2024-01-03')
    assert result.amount.sum()==1000000 and set(result.component)=={'base','retention'}
    with pytest.raises(KeyError):retention_components(invoices(),[{k:v for k,v in contract.items() if k!='known_at'}],'2024-01-03')
    with pytest.raises(ValueError,match='ngày biết'):retention_components(invoices(),[dict(contract,known_at=None)],'2024-01-03')


def test_partial_payment_leaves_retained_cash_open_and_later_settles_once():
    inv=invoices().iloc[:1].copy()
    bank=pd.DataFrame(dict(txn_id=['p1','p2'],firm_id=['f','f'],value_date=pd.to_datetime(['2024-02-01','2024-03-01']),
        amount=[950000.,50000.],memo=['HD 101','HD 101'],direction=['in','in']))
    assigned=pd.DataFrame(dict(txn_id=['p1','p2'],customer_id=['c','c'],confidence=[.99,.99]))
    links,_=reconcile_arrays(Reconciler(),bank,inv,pd.DataFrame(),assignments=assigned,allocation_policy=ObservedAllocationPolicy())
    assert links.amount.sum()==1000000
    assert links.kind.tolist()==['partial','full']


def test_cod_uses_observed_issue_date_and_rejects_duplicate_candidates():
    pool=invoices();pool['due_date']=pool.issue_date
    txn=SimpleNamespace(value_date=pd.Timestamp('2024-01-05'),amount=1000000.,memo='')
    assert ObservedAllocationPolicy()(pool,txn)==(['b'],'COD_recent_unique')
    duplicate=pd.concat([pool.iloc[1:],pool.iloc[1:].assign(invoice_id='d')])
    assert ObservedAllocationPolicy()(duplicate,txn)==([], '')


def test_hazard_tie_stays_in_review_but_strong_frozen_prior_selects_subset():
    pool=invoices()
    assert hazard_subset(pool,1000000.,[.5,.5])==[]
    assert hazard_subset(pool,1000000.,[.9,.1])==['a']
    assert hazard_subset(pool,1000000.,np.array([.1,.9]))==['b']
