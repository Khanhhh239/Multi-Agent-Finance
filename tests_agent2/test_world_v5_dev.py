import copy
import random

from agent2.world_v5_dev import WorldV5Development, development_config, scale_money
from agent2.world_v4 import WorldV4


def test_development_draws_are_fixed_and_in_domain():
    configs = [development_config(s) for s in range(1001, 1021)]
    assert configs == [development_config(s) for s in range(1001, 1021)]
    assert all(30 <= c['companies'] <= 60 and 1 <= c['money_scale'] <= 20 for c in configs)
    assert all(abs(sum(c['difficulty_weights']) - 1) < 1e-12 for c in configs)
    assert len({c['companies'] for c in configs}) > 5
    assert len({tuple(c['difficulty_weights']) for c in configs}) == 20


def test_currency_transform_handles_shared_records_without_scaling_keys():
    employee = dict(employee_id='E1', monthly_salary_vnd=12_000_000)
    tables = {'a': [employee], 'b': [employee, dict(amount_vnd=100_000, unit_price_vnd=1234,
             quantity=81.037, label=1, amount_scale=2.0, empty_vnd='')]}
    original = copy.deepcopy(tables)
    scale_money(tables, 3.14159)
    assert employee['monthly_salary_vnd'] == 37_699_000
    row = tables['b'][1]
    assert row['amount_vnd'] == 314_000 and row['unit_price_vnd'] == 3877
    assert row['quantity'] == original['b'][1]['quantity'] and row['label'] == 1
    assert row['amount_scale'] == 6.28318 and row['empty_vnd'] == ''


def test_world_share_controls_actual_case_concealment(monkeypatch):
    monkeypatch.setattr(WorldV4,'open_case',lambda self,*args:dict(concealment='L0'))
    world=WorldV5Development.__new__(WorldV5Development)
    world.rng=random.Random(7)
    for i in range(3):
        world.development={'difficulty_weights':[int(j==i) for j in range(3)]}
        assert {world.open_case('scheme','company')['concealment'] for _ in range(30)}=={f'L{i}'}
