import numpy as np
import pandas as pd
from agent1.synth.world import WorldConfig,World
from agent1.synth.hard_cases import HardCaseWorld


def test_lumpy_case_controls_realized_revenue_despite_customer_churn():
    world=HardCaseWorld(WorldConfig(seed=901,start='2023-01-01',end='2024-12-31',n_firms=1,rng_version=2),'lumpy_customer')
    world.macro()
    firm=world.make_firm(0);customers=world.make_customers(firm);invoices=world.make_invoices(firm,customers)
    share=invoices.loc[invoices.ci==0,'net'].sum()/invoices.net.sum()
    assert .4<=share<=.6
    assert abs(share-customers.loc[0,'weight'])<1e-5


def test_discount_eligible_customers_have_net30_terms():
    world=HardCaseWorld(WorldConfig(seed=901,rng_version=2),'discount_early')
    customers=world.make_customers(world.make_firm(0))
    assert customers.discount_eligible.any()
    assert customers.loc[customers.discount_eligible,'term_days'].eq(30).all()


def test_discount_settlement_is_single_payment_and_balances_credit_note():
    world=HardCaseWorld(WorldConfig(seed=901,start='2023-01-01',end='2024-12-31',rng_version=2),'discount_early')
    world.macro();firm=world.make_firm(0);customers=world.make_customers(firm)
    invoices=world.make_invoices(firm,customers)
    invoices['symbol']='TEST';invoices['invoice_no']=[str(i) for i in range(len(invoices))]
    liquidity,default,stress=world.customer_paths(firm,customers)
    invoices,payments=world.settle(firm,customers,invoices,liquidity,default,stress)
    selected=invoices.index[invoices.discount_taken]
    assert len(selected)>0
    paid=payments[payments.k.isin(selected)].set_index('k')
    assert paid.index.is_unique and paid.kind.eq('full').all()
    np.testing.assert_allclose(paid.amount.sort_index()+invoices.loc[selected,'credit_note'],invoices.loc[selected,'amount_gross'])
    assert invoices.loc[selected,'term_days'].eq(30).all()
    expected=world.cal.snap_bd(invoices.loc[selected,'issue_i'].to_numpy()+10)
    np.testing.assert_array_equal(paid.day_i.sort_index(),expected)


def test_supply_shock_is_exactly_eight_weeks_and_local_to_sector(monkeypatch):
    def base(self,firm,cust):return np.zeros((2,self.W)),np.full(2,-1),np.zeros(self.W)
    monkeypatch.setattr(World,'customer_paths',base)
    world=HardCaseWorld(WorldConfig(seed=901,rng_version=2),'supply_shock')
    affected,_,stress=world.customer_paths(dict(industry='steel_metals'),pd.DataFrame())
    other,_,_=world.customer_paths(dict(industry='services'),pd.DataFrame())
    assert (affected[0]!=0).sum()==8 and stress.sum()==8
    assert np.all(other==0)
