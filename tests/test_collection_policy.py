import numpy as np
import pandas as pd
from agent1.eval.collection_policy import rank_delta,move_receipts,remaining_ar,response_uniform,count_shortfalls
from agent1.models.t10 import rank_collections


def test_single_simulation_delta_matches_full_crn_resimulation():
    frame=pd.DataFrame(dict(invoice_id=['a','b','c'],customer_id=['x','y','z'],amount_open=[7.,11.,4.]))
    P=np.zeros((3,13));P[:,[0,2,6]]=[.1,.4,.3]
    args=dict(B0=5.,known_out=np.full(13,2.),rev_q=None,kernel=np.zeros(17),capex_rate=0.,capex_sizes=[],n=300,rho=.2,seed=9)
    expected=rank_collections(frame,P,args,top_n=3).set_index('invoice_id').sort_index()
    actual=rank_delta(frame,P,args,top_n=3).set_index('invoice_id').sort_index()
    np.testing.assert_allclose(actual.delta_shortfall,expected.delta_shortfall,atol=1e-15)


def test_receipt_shift_conserves_total_cash_and_does_not_move_already_known_or_week1_cash():
    payments=pd.DataFrame(dict(invoice_id=['a','a','a','b'],amount=[2.,3.,5.,7.],
        pay_date_true=pd.to_datetime(['2024-01-01','2024-01-05','2024-02-01','2024-02-01'])))
    shifted,moves=move_receipts(payments,'a','2024-01-01')
    assert shifted.amount.sum()==payments.amount.sum()
    assert shifted.pay_date_true.tolist()==list(pd.to_datetime(['2024-01-01','2024-01-05','2024-01-08','2024-02-01']))
    assert moves.amount.sum()==5
    assert payments.pay_date_true.iloc[2]==pd.Timestamp('2024-02-01')


def test_ar_uses_only_observed_credit_and_receipts_and_excludes_known_writeoff():
    inv=pd.DataFrame(dict(invoice_id=['a','b'],amount_gross=[100.,200.],
        issue_date=pd.to_datetime(['2024-01-01']*2),writeoff_date=pd.to_datetime([None,'2024-01-05']),
        credit_note=[20.,0.],credit_note_date=pd.to_datetime(['2024-02-01',None])))
    pay=pd.DataFrame(dict(invoice_id=['a','a'],amount=[30.,50.],pay_date_true=pd.to_datetime(['2024-01-05','2024-02-05'])))
    ar=remaining_ar(inv,pay,'2024-01-10')
    assert ar.to_dict()=={'a':70.,'b':0.}
    changed=pay.copy();changed.loc[1,'amount']=5000.
    pd.testing.assert_series_equal(ar,remaining_ar(inv,changed,'2024-01-10'))
    u=response_uniform('a','2024-01-10')
    assert 0<=u<1 and u==response_uniform('a','2024-01-10')
    assert count_shortfalls([-1.,-2.,2.,-1.])==2


def test_terminal_settlement_closes_credit_residual_but_future_settlement_is_not_used():
    inv=pd.DataFrame(dict(invoice_id=['a','b'],amount_gross=[100.,100.],
        issue_date=pd.to_datetime(['2024-01-01']*2),writeoff_date=pd.to_datetime([None,None]),
        paid_date_true=pd.to_datetime(['2024-01-05','2024-02-05'])))
    pay=pd.DataFrame(dict(invoice_id=['a','b'],amount=[98.,30.],pay_date_true=pd.to_datetime(['2024-01-05']*2)))
    result=remaining_ar(inv,pay,'2024-01-10')
    assert result.to_dict()=={'a':0.,'b':70.}
    changed=inv.copy();changed.loc[1,'paid_date_true']=pd.Timestamp('2025-01-01')
    pd.testing.assert_series_equal(result,remaining_ar(changed,pay,'2024-01-10'))
