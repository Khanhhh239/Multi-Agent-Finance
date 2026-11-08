"""Integrated shock propagation and causal weekly exposure."""
from dataclasses import replace

import numpy as np
import pandas as pd

from agent1.data.contracts import validate_feature_columns, validate_world
from agent1.synth.shocks import ShockEpisode, episode_path
from agent1.synth.world import World, WorldConfig
from scripts.build_big import merge_shards


def test_episode_has_calm_rise_peak_recovery_and_no_future_effect():
    weeks = pd.date_range('2024-01-01', periods=22, freq='W-MON')
    episode = ShockEpisode('supply', '2024-02-05', rise_weeks=2,
                           peak_weeks=3, recovery_weeks=4, severity=1.5)
    path = episode_path(episode, weeks)
    assert np.all(path[:5] == 0)
    np.testing.assert_allclose(path[5:14], [.75, 1.5, 1.5, 1.5, 1.5,
                                             1.125, .75, .375, 0.])
    assert np.all(path[14:] == 0)


def test_sector_and_buyer_seller_exposures_are_private_and_distinct():
    cfg = WorldConfig(seed=73, start='2024-01-01', end='2024-09-30', n_firms=1,
                      shock_schedule=[ShockEpisode('price', '2024-04-01',
                                                   industries=('steel_metals',), regions=(1,))])
    world = World(cfg)
    firm = dict(industry='steel_metals', region=1, price_exposure=.8)
    buyer = dict(industry='steel_metals', region=1, price_exposure=1.7)
    other = dict(industry='services', region=1, price_exposure=2.)
    week = world.weeks.get_loc(pd.Timestamp('2024-04-15'))
    assert world.shock_effects(buyer)['price'][week] > world.shock_effects(firm)['price'][week]
    assert world.shock_effects(other)['price'][week] == 0
    assert world.shock_effects(firm)['price'][:world.weeks.get_loc(pd.Timestamp('2024-04-01'))].sum() == 0
    for name in ('price_exposure', 'supply_capacity'):
        try:
            validate_feature_columns([name])
        except ValueError:
            pass
        else:
            raise AssertionError(f'{name} leaked into model features')


def test_weekly_buyer_liquidity_changes_only_after_episode_starts():
    episode = ShockEpisode('credit', '2024-04-01', rise_weeks=1,
                           peak_weeks=4, recovery_weeks=4, severity=1.4)
    cfg = WorldConfig(seed=36, start='2024-01-01', end='2024-09-30', n_firms=1,
                      shock_schedule=[episode])
    base = World(replace(cfg, shock_schedule=[]))
    stressed = World(cfg)
    base.macro()
    stressed.macro()
    firm_a, firm_b = base.make_firm(0), stressed.make_firm(0)
    cust_a, cust_b = base.make_customers(firm_a), stressed.make_customers(firm_b)
    assert firm_a == firm_b
    pd.testing.assert_frame_equal(cust_a, cust_b)
    normal, _, _ = base.customer_paths(firm_a, cust_a)
    shock, _, _ = stressed.customer_paths(firm_b, cust_b)
    first = stressed.weeks.get_loc(pd.Timestamp('2024-04-01'))
    np.testing.assert_array_equal(normal[:, :first], shock[:, :first])
    assert np.all(shock[:, first:first + 4] < normal[:, first:first + 4])


def test_all_four_families_propagate_through_one_world(tmp_path):
    episodes = [ShockEpisode(family, '2024-04-01', rise_weeks=2,
                             peak_weeks=5, recovery_weeks=7, severity=1.2)
                for family in ('demand', 'supply', 'price', 'credit')]
    cfg = WorldConfig(name='integrated', seed=61, start='2024-01-01', end='2024-10-31',
                      n_firms=1, n_cust_median=20., revenue_median=25e9,
                      write_xml=0, rng_version=2, shock_schedule=episodes)
    stressed = World(cfg)
    control = World(replace(cfg, name='control', shock_schedule=[]))
    control.run(tmp_path / 'control', verbose=False)
    stressed.run(tmp_path / 'integrated', verbose=False)
    directory = tmp_path / 'integrated'
    assert validate_world(directory).passed.all()
    truth = pd.read_parquet(directory / 'shock_truth.parquet')
    assert set(truth.family) == {'demand', 'supply', 'price', 'credit'}
    assert set(truth.phase) == {'calm', 'rise', 'shock', 'recovery'}
    assert len(truth) == 4 * stressed.W
    stock = pd.read_parquet(directory / 'inventory_weekly.parquet').set_index('week')
    base_stock = pd.read_parquet(tmp_path / 'control' / 'inventory_weekly.parquet').set_index('week')
    pd.testing.assert_frame_equal(stock.loc[:'2024-03-25',
        ['booked_orders', 'purchase_net', 'sale_price_index', 'input_cost_index']],
        base_stock.loc[:'2024-03-25',
        ['booked_orders', 'purchase_net', 'sale_price_index', 'input_cost_index']])
    active = stock.loc['2024-04-15':'2024-05-20']
    assert (active.supply_capacity < 1).all()
    assert (active.sale_price_index > 1).all()
    assert (active.input_cost_index > 1).all()
    assert (active.booked_orders <= active.demand_orders).all()
    assert (active.booked_orders < active.demand_orders).any()
    assert not np.allclose(active.booked_orders, base_stock.loc[active.index, 'booked_orders'])
    assert not np.allclose(active.purchase_net, base_stock.loc[active.index, 'purchase_net'])
    out = pd.read_parquet(directory / 'outflows.parquet')
    base_out = pd.read_parquet(tmp_path / 'control' / 'outflows.parquet')
    loan = out[out.category.eq('loan_service')].set_index('date').amount
    base_loan = base_out[base_out.category.eq('loan_service')].set_index('date').amount
    active_loan = loan.loc['2024-04-01':'2024-05-31']
    assert len(active_loan) and (active_loan > base_loan.loc[active_loan.index]).all()
    cash = pd.read_parquet(directory / 'daily_cash.parquet').set_index('date')
    base_cash = pd.read_parquet(tmp_path / 'control' / 'daily_cash.parquet').set_index('date')
    assert not np.allclose(cash.loc['2024-06-01':'2024-06-30', 'balance'],
                           base_cash.loc['2024-06-01':'2024-06-30', 'balance'])
    assert set(pd.read_parquet(directory / 'invoices.parquet').columns) >= {
        'outcome_status_at_end', 'remaining_amount'}


def test_shards_keep_one_shared_episode_path(tmp_path):
    cfg = WorldConfig(name='shocked_shards', seed=81, start='2024-01-01', end='2024-07-31',
                      n_firms=2, n_cust_median=10., revenue_median=12e9, write_xml=0,
                      rng_version=2, shock_schedule=[ShockEpisode('supply', '2024-04-01')])
    parts = []
    for i in range(2):
        path = tmp_path / f'part{i}'
        World(cfg).run(path, verbose=False, firm_indices=[i])
        parts.append(path)
    merged = tmp_path / 'merged'
    merge_shards(parts, merged)
    assert validate_world(merged).passed.all()
    pd.testing.assert_frame_equal(pd.read_parquet(parts[0] / 'shock_truth.parquet'),
                                  pd.read_parquet(merged / 'shock_truth.parquet'))
    assert pd.read_parquet(merged / 'firms.parquet').firm_id.nunique() == 2
