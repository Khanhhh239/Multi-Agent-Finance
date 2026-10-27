import numpy as np
import pandas as pd
import pytest
from copy import deepcopy
from agent1.synth.world import WorldConfig,World
from agent1.synth.hard_cases import HardCaseWorld
from agent1.data.contracts import validate_world


def test_lumpy_case_sets_anchor_before_sales_without_future_rescaling():
    world=HardCaseWorld(WorldConfig(seed=901,start='2023-01-01',end='2024-12-31',n_firms=1,rng_version=2),'lumpy_customer')
    world.macro()
    firm=world.make_firm(0);customers=world.make_customers(firm)
    state=deepcopy(world.rng.bit_generator.state)
    unadjusted=World.make_invoices(world,firm,customers)
    world.rng.bit_generator.state=state
    invoices=world.make_invoices(firm,customers)
    pd.testing.assert_frame_equal(invoices,unadjusted)
    share=invoices.loc[invoices.ci==0,'net'].sum()/invoices.net.sum()
    assert .4<=share<=.6


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


@pytest.mark.parametrize('case', ['discount_early', 'retention', 'fx', 'credit_note'])
def test_money_changing_hard_case_reconciles_all_tables(case, tmp_path):
    cfg = WorldConfig(name=f'accounting_{case}', seed=901, n_firms=1, start='2023-01-01',
                      end='2024-12-31', write_xml=0, rng_version=2)
    directory = HardCaseWorld(cfg, case).run(tmp_path / case, verbose=False)
    assert validate_world(directory).passed.all()
    if case == 'credit_note':
        invoices = pd.read_parquet(directory / 'invoices.parquet')
        replacements = invoices[invoices.adjustment_type.eq('replacement')]
        originals = invoices.set_index('invoice_id').loc[replacements.adjusts_invoice_id]
        assert len(replacements) > 0
        assert originals.adjustment_type.eq('cancelled_original').all()
        assert originals.closure_type.eq('credit_note').all()
        assert originals.paid_date_true.isna().all()
        assert (originals.credit_note == originals.amount_gross).all()


def test_supply_shock_is_eight_weeks_and_changes_actual_supply(tmp_path):
    cfg=WorldConfig(seed=901,rng_version=2,n_firms=1,write_xml=0,
                    start='2022-01-01',end='2023-01-31',
                    industry_mix={'steel_metals':1.})
    world=HardCaseWorld(cfg,'supply_shock')
    exposed=world.shock_effects(dict(industry='steel_metals',region=1,supply_exposure=1.))['supply']
    other=world.shock_effects(dict(industry='services',region=1,supply_exposure=1.))['supply']
    assert np.count_nonzero(exposed)==8
    assert np.all(other==0)
    stressed=world.run(tmp_path/'supply',verbose=False)
    control=World(WorldConfig(seed=901,rng_version=2,n_firms=1,write_xml=0,
                    start='2022-01-01',end='2023-01-31',
                    industry_mix={'steel_metals':1.})).run(tmp_path/'control',verbose=False)
    stock=pd.read_parquet(stressed/'inventory_weekly.parquet').set_index('week')
    base=pd.read_parquet(control/'inventory_weekly.parquet').set_index('week')
    active=stock.loc['2022-10-03':'2022-11-21']
    assert active.supply_capacity.lt(1).all()
    assert active.booked_orders.sum()<base.loc[active.index,'booked_orders'].sum()
    assert active.input_cost_index.gt(1).all()
