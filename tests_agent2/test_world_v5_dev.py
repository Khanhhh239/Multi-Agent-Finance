import copy
import random
from collections import defaultdict
from datetime import timedelta

from sme_fraud.generate import WINDOWS, parse

from agent2.world_v5_dev import WorldV5Development, development_config, scale_money
from agent2.world_v4 import WorldV4
from agent2.runtime_v5 import memory_ready


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


def test_advance_checks_staff_against_its_actual_issue_date():
    class Earliest:
        def randint(self,a,b): return a
        def choice(self,values): return values[0]
    world=WorldV5Development.__new__(WorldV5Development)
    world.rng=Earliest()
    world.tables=defaultdict(list)
    world.company_staff={'C1':[f'E{i}' for i in range(9)]}
    world.employees={eid:dict(employee_id=eid,hired_at='2023-01-01T00:00:00+07:00',terminated_at='')
                     for eid in world.company_staff['C1']}
    world.employees['E6']['hired_at']='2025-01-06T09:00:00+07:00'
    world.employees['E7']['terminated_at']='2025-01-04T17:00:00+07:00'
    serial=iter(range(100)); world.identifier=lambda prefix:prefix+str(next(serial))
    records=[]
    def transaction(cid,split,at,kind,**kwargs):
        row=dict(posted_at=at,kind=kind,employee_id=kwargs['employee']['employee_id'])
        records.append(row)
        return row
    world.transaction=transaction
    world.put=lambda *args,**kwargs:'T'+str(next(serial))
    review=WINDOWS['validation'][0]+timedelta(days=110,hours=10)
    world.advance('C1','validation',review,'E3',valid=True,mode='writeoff')
    assert [row['employee_id'] for row in records]==['E8','E8']
    assert records[0]['posted_at']==WINDOWS['validation'][0]+timedelta(days=4,hours=10)
    assert parse(world.tables['advances'][0]['issued_at'])==records[0]['posted_at']
    assert {event['event_type'] for event in world.tables['advance_events']}=={'extension','writeoff'}


def test_scheduler_needs_commit_margin_and_limits_paging_fallback():
    assert memory_ready(3,6,3)
    assert not memory_ready(4,5,3)
    assert memory_ready(2,20,3)
    assert not memory_ready(2,11,3)
    assert memory_ready(1,20,3)
    assert not memory_ready(.5,20,3)
