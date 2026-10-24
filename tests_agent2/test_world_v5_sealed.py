"""Sealed v5 world machinery on a small world with STAND-IN scenarios (dữ liệu tổng hợp).

The stand-ins reuse an existing development scheme and a plain background row only to exercise coverage and
labelling; they are not the independent author's scenarios and are never used for evaluation.
"""
import pytest

import agent2.world_v5_sealed as S
from agent2.world_v4_schemes import SCHEMES, NotApplicable

SMALL = {'seed': 4242, 'rows': 15000, 'fraud_rate': .004, 'companies': 6, 'money_scale': 1.0,
         'difficulty_weights': [1 / 3, 1 / 3, 1 / 3], 'calendar_seed': 4243}


class StandIn(S.WorldV5Sealed):
    catalog = {**SCHEMES, 'standin_split': SCHEMES['split_payments']}
    scheme_standin_split = S.WorldV5Sealed.scheme_split_payments

    def decoy_standin_docs(self, cid, split):
        self.put(split, self.transaction(cid, split), hard='standin_docs')


@pytest.fixture
def stand_ins(monkeypatch):
    monkeypatch.setattr(S, 'NOVEL_V5', {'standin_split': SCHEMES['split_payments']})
    monkeypatch.setattr(S, 'NEW_DECOYS_V5', ('standin_docs',))
    monkeypatch.setattr(S, 'MIN_TEST_CASES_PER_WORLD', 5)


def test_novel_and_new_look_alike_coverage_and_labels(stand_ins):
    tables = StandIn(SMALL).finalize()
    novel_test = [c for c in tables['truth_cases'] if c['scheme'] == 'standin_split' and c['split'] == 'test']
    assert len(novel_test) >= S.MIN_TEST_CASES_PER_NOVEL
    split = {r['transaction_id']: r['split'] for r in tables['splits']}
    decoys = [r for r in tables['labels'] if r['hard_negative_type'] == 'standin_docs']
    assert all(r['is_fraud'] == 0 and r['case_role'] == 'hard_negative' for r in decoys)
    assert sum(split[r['transaction_id']] == 'test' for r in decoys) >= S.MIN_TEST_ROWS_PER_DECOY
    fraud = [r for r in tables['labels'] if r['fraud_type'] == 'standin_split']
    assert fraud and all(r['is_fraud'] == 1 for r in fraud)


def test_look_alike_coverage_failure_raises(stand_ins):
    class NeverApplicable(StandIn):
        def decoy_standin_docs(self, cid, split):
            raise NotApplicable

    with pytest.raises(ValueError, match='look-alike coverage'):
        NeverApplicable(SMALL).finalize()


def test_dry_run_v13_flags_only_separations_new_to_development():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_sealed_v5.py"
    spec = importlib.util.spec_from_file_location("run_sealed_v5", path)
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    base = [{"findings": [{"txn_type": "sales_return", "column": "applied_invoice_id"}]}]
    found = [{"txn_type": "sales_return", "column": "applied_invoice_id"}, {"txn_type": "rent", "column": "vendor_id"}]
    assert run.new_separations(found, base) == [{"txn_type": "rent", "column": "vendor_id"}]


def test_empty_catalogue_and_unregistered_seeds_are_refused(monkeypatch):
    monkeypatch.setattr(S, 'NOVEL_V5', {})
    with pytest.raises(RuntimeError, match='NOVEL_V5 is empty'):
        S.WorldV5Sealed(SMALL).finalize()
    with pytest.raises(ValueError, match='fixed in advance'):
        S.sealed_config(1001)
    assert S.sealed_config(5101)['sealed'] and not S.sealed_config(S.DRY_RUN_SEED)['sealed']
