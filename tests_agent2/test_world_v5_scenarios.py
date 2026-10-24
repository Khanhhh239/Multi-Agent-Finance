"""Encoded v5 scenarios on a small world (dữ liệu tổng hợp): coverage, labelling and no registered shortcut fields."""
import collections

import pytest

import agent2.world_v5_sealed as S

CONFIG = {'seed': 4242, 'rows': 60000, 'fraud_rate': .004, 'companies': 16, 'money_scale': 1.0,
          'difficulty_weights': [1 / 3, 1 / 3, 1 / 3], 'calendar_seed': 4243}


@pytest.fixture(scope='module')
def tables():
    return S.WorldV5Sealed(CONFIG).finalize()


def test_catalogue_matches_the_locked_prose():
    assert len(S.NOVEL_V5) == 10 and len(S.NEW_DECOYS_V5) == 20
    assert all(hasattr(S.WorldV5Sealed, f'scheme_{name}') for name in S.NOVEL_V5)
    assert all(hasattr(S.WorldV5Sealed, f'decoy_{name}') for name in S.NEW_DECOYS_V5)
    assert len({branch for branch, *_ in S.NOVEL_V5.values()}) >= 6          # spread over the ACFE branches


def test_every_novel_scheme_has_test_cases_and_every_look_alike_has_test_rows(tables):
    test_cases = collections.Counter(c['scheme'] for c in tables['truth_cases'] if c['split'] == 'test')
    assert all(test_cases[name] >= S.MIN_TEST_CASES_PER_NOVEL for name in S.NOVEL_V5)
    split = {r['transaction_id']: r['split'] for r in tables['splits']}
    rows = collections.Counter(r['hard_negative_type'] for r in tables['labels'] if split[r['transaction_id']] == 'test')
    assert all(rows[name] >= S.MIN_TEST_ROWS_PER_DECOY for name in S.NEW_DECOYS_V5)


def test_fraud_and_look_alike_labels_never_mix_and_shortcut_fields_stay_empty(tables):
    labels = {r['transaction_id']: r for r in tables['labels']}
    rows = {r['transaction_id']: r for r in tables['transactions']}
    novel_rows = [t for t, r in labels.items() if r['fraud_type'] in S.NOVEL_V5]
    assert novel_rows and all(labels[t]['is_fraud'] == 1 and not labels[t]['hard_negative_type'] for t in novel_rows)
    decoys = [t for t, r in labels.items() if r['hard_negative_type'] in S.NEW_DECOYS_V5]
    assert decoys and all(labels[t]['is_fraud'] == 0 for t in decoys)
    for t in novel_rows:                       # the R1 v1.3 shortcut fields are not written on new fraud rows
        assert not rows[t]['collector_id']
        assert rows[t]['txn_type'] not in ('customer_receipt',) or not rows[t]['applied_invoice_id']
    assert not any(rows[t]['applied_invoice_id'] for t in novel_rows if rows[t]['txn_type'] in ('sales_return', 'bad_debt_writeoff'))
