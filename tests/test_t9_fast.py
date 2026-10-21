import numpy as np
import pandas as pd
from agent1.models.t9_recon import Reconciler,TOL
from agent1.models.t9_fast import FastAmountReconciler,concatenate_parts,reconcile_arrays
from agent1.models.reconciliation_pipeline import reconcile


def test_vectorized_amount_features_match_reference_including_credit_dates_and_tolerance():
    rng=np.random.default_rng(18);date=pd.Timestamp('2024-03-01')
    for size in range(1,15):
        amounts=rng.integers(100,100000,size)*1000.
        frame=pd.DataFrame(dict(amount_gross=amounts,due_date=pd.date_range('2023-12-01',periods=size),
            ledger_clear_date=pd.to_datetime([None if i%3 else '2024-02-01' for i in range(size)]),
            credit_note=np.where(np.arange(size)%2,10000.,0.),
            credit_note_date=pd.to_datetime(['2024-02-01' if i%2 else '2025-01-01' for i in range(size)])))
        for amount in [amounts[0],amounts[:2].sum(),amounts[:3].sum()+TOL,amounts[:3].sum()+TOL+1,1.]:
            expected=Reconciler._amount_feats(frame,amount,date)
            actual=FastAmountReconciler._amount_feats(frame,amount,date)
            for key in expected:np.testing.assert_allclose(actual[key],expected[key],equal_nan=True)


def test_partitioned_reconciliation_matches_all_firms_with_interleaved_dates():
    inv=pd.DataFrame(dict(invoice_id=['a','b','c','d'],firm_id=['f','f','g','g'],customer_id=['x','x','y','y'],
        invoice_no=['00000101','00000102']*2,amount_gross=[1e6,2e6,1e6,2e6],
        issue_date=pd.to_datetime(['2024-01-01']*4),due_date=pd.to_datetime(['2024-02-01']*4),
        ledger_clear_date=pd.to_datetime([None,'2024-02-04',None,None])))
    bank=pd.DataFrame(dict(txn_id=['t1','t2','t3','t4'],firm_id=['f','g','f','g'],
        value_date=pd.to_datetime(['2024-02-01','2024-02-02','2024-02-05','2024-02-06']),
        amount=[1e6,2e6,2e6,1e6],memo=['']*4))
    whole=reconcile(Reconciler(),bank,inv,pd.DataFrame())
    split=[reconcile(Reconciler(),b,inv[inv.firm_id==fid],pd.DataFrame()) for fid,b in bank.groupby('firm_id')]
    for i in range(2):
        left=whole[i].sort_values('txn_id').reset_index(drop=True)
        right=concatenate_parts([part[i] for part in split]).sort_values('txn_id').reset_index(drop=True)
        pd.testing.assert_frame_equal(left,right)


def test_array_reconciliation_matches_reference_state_transitions_randomized():
    rng=np.random.default_rng(42);origin=pd.Timestamp('2024-01-01')
    for trial in range(4):
        n=18;m=30
        issued=origin+pd.to_timedelta(rng.integers(0,40,n),unit='D')
        inv=pd.DataFrame(dict(invoice_id=[f'i{x}' for x in range(n)],firm_id=np.repeat(['f','g'],n//2),
            customer_id=np.repeat(['x','y','z','w','v','u'],3),invoice_no=[str(101+x%9) for x in range(n)],
            amount_gross=rng.integers(1,12,n)*1e5,issue_date=issued,due_date=issued+pd.Timedelta(days=30),
            ledger_clear_date=origin+pd.to_timedelta(rng.integers(30,100,n),unit='D'),
            credit_note=np.where(rng.random(n)<.3,1e4,0.),
            credit_note_date=origin+pd.to_timedelta(rng.integers(30,100,n),unit='D')))
        inv.loc[rng.random(n)<.5,'ledger_clear_date']=pd.NaT
        bank=pd.DataFrame(dict(txn_id=[f't{x}' for x in range(m)],firm_id=rng.choice(['f','g'],m),
            value_date=origin+pd.to_timedelta(rng.integers(0,100,m),unit='D'),
            amount=rng.integers(-1,25,m)*1e5,memo=rng.choice(['','HD 00000101','TT 00000102 00000103'],m),
            direction=rng.choice(['in','out'],m,p=[.9,.1])))
        assigned=pd.DataFrame(dict(txn_id=bank.txn_id,customer_id=rng.choice(inv.customer_id,m),confidence=rng.choice([.5,.95,1.],m)))
        for policy in ['asof','opening_only']:
            for rule_mode in ['both','amount','memo']:
                args=dict(assignments=assigned,ledger_policy=policy,rule_mode=rule_mode,rules_first=trial%2==0)
                expected=reconcile(Reconciler(),bank,inv,pd.DataFrame(),**args)
                actual=reconcile_arrays(Reconciler(),bank,inv,pd.DataFrame(),**args)
                for left,right in zip(expected,actual):pd.testing.assert_frame_equal(left,right)


def test_array_candidates_match_reference_with_future_customers_and_credit_notes():
    rng=np.random.default_rng(17);origin=pd.Timestamp('2024-01-01');n=48;m=40
    inv=pd.DataFrame(dict(invoice_id=[f'i{x}' for x in range(n)],firm_id=np.repeat(['f','g'],n//2),
        customer_id=np.repeat([f'c{x}' for x in range(8)],6),invoice_no=[str(101+x%7) for x in range(n)],
        issue_date=origin+pd.to_timedelta(rng.integers(0,90,n),unit='D'),
        due_date=origin+pd.to_timedelta(rng.integers(30,120,n),unit='D'),amount_gross=rng.integers(1,20,n)*1e5,
        ledger_clear_date=origin+pd.to_timedelta(rng.integers(30,150,n),unit='D'),
        credit_note=np.where(rng.random(n)<.3,1e4,0.),
        credit_note_date=origin+pd.to_timedelta(rng.integers(20,120,n),unit='D')))
    inv.loc[inv.index%3==0,'ledger_clear_date']=pd.NaT
    bank=pd.DataFrame(dict(txn_id=[f't{x}' for x in range(m)],firm_id=np.repeat(['f','g'],m//2),
        value_date=origin+pd.to_timedelta(rng.integers(0,130,m),unit='D'),amount=rng.integers(1,30,m)*1e5,
        memo=rng.choice(['Buyer A','HD 00000101 00000102',''],m),counterparty=rng.choice(['Buyer A','Buyer B',''],m)))
    customers=inv[['firm_id','customer_id']].drop_duplicates().assign(short=['Buyer A','Buyer B']*4)
    expected=Reconciler().candidates(bank,inv,customers)
    actual=FastAmountReconciler().candidates(bank,inv,customers)
    pd.testing.assert_frame_equal(expected,actual)
