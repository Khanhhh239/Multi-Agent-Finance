"""Hire-date invariant for v5 development worlds (dữ liệu tổng hợp)."""
import os

import pytest

from agent2.world_v5_dev import WorldV5Development
from sme_fraud.generate import parse


def bare_world(employees):
    world = WorldV5Development.__new__(WorldV5Development)
    world.employees = employees
    return world


def row(posted, created=None, approved=None, **staff):
    return {'txn_type': 'payroll', 'posted_at': posted, 'approved_at': approved or posted,
            'created_at': created or posted, **staff}


HIRE = {'E1': {'employee_id': 'E1', 'recorded_at': '2024-12-30T09:00:00+07:00'},
        'E0': {'employee_id': 'E0', 'recorded_at': '2023-01-01T00:00:00+07:00'}}


def test_same_day_conflict_moves_row_after_hire_and_keeps_order():
    r = row('2024-12-30T08:06:00+07:00', created='2024-12-30T06:42:59+07:00', employee_id='E1', creator_id='E0')
    bare_world(HIRE).hire_guard(r)
    assert parse(r['posted_at']) == parse('2024-12-30T09:01:00+07:00')
    assert parse(r['created_at']) <= parse(r['approved_at']) <= parse(r['posted_at'])
    assert parse(r['created_at']) == parse('2024-12-30T07:37:59+07:00')


def test_clean_row_is_untouched():
    r = row('2024-12-30T10:00:00+07:00', employee_id='E1', creator_id='E0')
    before = dict(r)
    bare_world(HIRE).hire_guard(r)
    assert r == before


def test_conflict_across_days_raises_with_context():
    r = row('2024-12-29T15:00:00+07:00', employee_id='E1')
    with pytest.raises(ValueError, match='employee_id E1 recorded'):
        bare_world(HIRE).hire_guard(r)


def test_unknown_or_empty_staff_ids_are_ignored():
    r = row('2024-01-02T10:00:00+07:00', employee_id='', creator_id='GHOST', approver_id=None)
    bare_world(HIRE).hire_guard(r)
    assert r['posted_at'] == '2024-01-02T10:00:00+07:00'


@pytest.mark.skipif(not os.environ.get('AGENT2_SLOW'), reason='set AGENT2_SLOW=1: small worlds across many seeds')
@pytest.mark.parametrize('seed', range(7001, 7013))
def test_small_worlds_have_no_future_staff(seed, tmp_path):
    """Property test: every master-data reference is recorded before the row."""
    from agent2.validate_v4 import validate_v4
    from agent2.world_v5_dev import generate
    config = {'seed': seed, 'rows': 60_000, 'fraud_rate': .004, 'companies': 12 + seed % 7,
              'money_scale': 1.0 + seed % 5, 'difficulty_weights': [1 / 3, 1 / 3, 1 / 3],
              'calendar_seed': seed + 520_000, 'data_origin': 'dữ liệu tổng hợp'}
    generate(config, tmp_path / 'w')
    report = validate_v4(tmp_path / 'w', run_shortcut=False)
    assert report['status'] == 'passed'
