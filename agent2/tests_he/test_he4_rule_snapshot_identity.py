"""Tests for Slice 3: `B1`, `B5`, `E4` on bounded Concrete `graph` circuit."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from finance_input import AccessScope
from sme_fraud.import_files import canonical, digest
from sme_fraud.native_rule_demo import scenario
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields

from experiments.he4 import circuits
from experiments.he4.rule_snapshot_identity_adapter import (
    decode_b1_plan_results,
    decode_b5_e4_plan_results,
    plan_b1_from_rule_snapshot,
    plan_b5_e4_from_rule_snapshot,
)


def _scope(company='C001', actor='id-he-tester'):
    return AccessScope('native-demo', frozenset({company}), actor, frozenset({'data.import'}))


def _rehash(source):
    for name, rows in source['tables'].items():
        source['coverage'][name] = dict(
            source['coverage'][name],
            record_count=len(rows),
            records_sha256=digest(canonical(rows)),
        )
    return source


def _wrap(source, candidate_ids=None):
    return dict(
        contract_version=CONTRACT,
        tenant_id=source['tenant_id'],
        company_id=source['company_id'],
        source=source,
        candidate_transaction_ids=candidate_ids or [source['tables']['transactions'][-1]['transaction_id']],
    )


def _commit(store, scope, data, key='slice3-id'):
    draft = store.upload(scope, canonical(data), 'rule-snapshot.json', key + '-upload')
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise AssertionError(preview['errors'])
    return store.commit(scope, draft['import_id'], commit_fields(preview), key + '-commit')['snapshot']['snapshot_id']


def _run_plain_graph(plan, decoder):
    outputs = []
    for row in plan['rows']:
        for req in row.get('requests', []):
            out = circuits.graph(*[np.asarray(v, dtype=np.int64) for v in req['values']])
            outputs.append(out.tolist())
    return decoder(plan, outputs)


class RuleSnapshotIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SnapshotStore(Path(self.tmp.name) / 'snapshots.sqlite3')

    def test_b1_strong_disclosed_ambiguous_and_node_overflow(self):
        # 1. Undisclosed positive (weight=20, hard_trigger=1) & negative
        for company, positive in (('C001', True), ('C002', False)):
            src, info = scenario('B1', positive, company)
            data = _wrap(src, [info['target_transaction_id']])
            sid = _commit(self.store, _scope(company), data, f'b1-{company}-{positive}')
            native = analyze_rule_snapshot(self.store, _scope(company), sid, src['as_of'], technical=True)
            native_b1 = next(r for r in native['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'B1')
            res = _run_plain_graph(plan_b1_from_rule_snapshot(data, _scope(company)), decode_b1_plan_results)
            self.assertEqual(res['rows'][0]['matched'], native_b1['matched'])
            self.assertEqual(res['rows'][0]['score'], native_b1['score'])
            self.assertEqual(res['rows'][0]['hard_trigger'], 1 if positive else 0)

        # 2. Disclosed related party before posted_at -> weight=4, hard_trigger=0
        src, info = scenario('B1', True, 'C001')
        src['tables']['vendors'][0]['related_party_disclosed_at'] = '2025-01-01T00:00:00+07:00'
        _rehash(src)
        sid = _commit(self.store, _scope('C001'), _wrap(src, [info['target_transaction_id']]), 'b1-disclosed')
        native = analyze_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'], technical=True)
        native_b1 = next(r for r in native['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'B1')
        res = _run_plain_graph(plan_b1_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001')), decode_b1_plan_results)
        self.assertTrue(res['rows'][0]['matched'])
        self.assertEqual(res['rows'][0]['score'], native_b1['score'])
        self.assertEqual(res['rows'][0]['hard_trigger'], 0)

        # 3. Employee missing bank_code while bare account matches -> context ambiguous (weight=0)
        src_a, info_a = scenario('B1', True, 'C001')
        src_a['tables']['employees'][2]['bank_code'] = ''
        _rehash(src_a)
        res_a = _run_plain_graph(plan_b1_from_rule_snapshot(_wrap(src_a, [info_a['target_transaction_id']]), _scope('C001')), decode_b1_plan_results)
        self.assertTrue(res_a['rows'][0]['matched'])
        self.assertEqual(res_a['rows'][0]['scoring_role'], 'context')
        self.assertEqual(res_a['rows'][0]['score'], 0)
        self.assertEqual(res_a['rows'][0]['ambiguous_employee_ids'], [src_a['tables']['employees'][2]['employee_id']])

        # 4. 4+ employees -> total nodes > 4 -> unavailable (never sliced)
        src_o, info_o = scenario('B1', True, 'C001')
        e4 = deepcopy(src_o['tables']['employees'][2])
        e4['employee_id'] = 'SIM_EXTRA_EMP_4'
        e4['bank_account'] = 'SIM_EXTRA_BANK_4'
        src_o['tables']['employees'].append(e4)
        _rehash(src_o)
        plan_o = plan_b1_from_rule_snapshot(_wrap(src_o, [info_o['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan_o['rows'][0]['available'])
        self.assertEqual(plan_o['rows'][0]['reason'], 'he_graph_node_limit')

    def test_b5_e4_weak_address_strong_bank_phone_and_node_overflow(self):
        # 1. Strong phone/bank overlap vs no overlap
        for positive in (True, False):
            src, info = scenario('B5', positive, 'C001')
            data = _wrap(src, [info['target_transaction_id']])
            sid = _commit(self.store, _scope('C001'), data, f'b5-{positive}')
            native = analyze_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'], technical=True)
            native_b5 = next(r for r in native['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'B5')
            res = _run_plain_graph(plan_b5_e4_from_rule_snapshot(data, _scope('C001')), decode_b5_e4_plan_results)
            self.assertEqual(res['rows'][0]['matched'], native_b5['matched'])
            self.assertEqual(res['rows'][0]['score'], native_b5['score'])  # master_quality = 0 effective row score
            if positive:
                self.assertEqual(res['rows'][0]['intrinsic_points'], 3)
                self.assertEqual(res['rows'][0]['aliases'], ['E4'])
                self.assertEqual(res['rows'][0]['overlap_kind'], 'shared_bank_or_phone')

        # 2. Address-only shared -> weak (`intrinsic_points = 1`)
        src_w, info_w = scenario('B5', False, 'C001')
        src_w['tables']['vendors'][1]['address'] = src_w['tables']['vendors'][0]['address']
        _rehash(src_w)
        res_w = _run_plain_graph(plan_b5_e4_from_rule_snapshot(_wrap(src_w, [info_w['target_transaction_id']]), _scope('C001')), decode_b5_e4_plan_results)
        self.assertTrue(res_w['rows'][0]['matched'])
        self.assertEqual(res_w['rows'][0]['overlap_kind'], 'shared_address_only')
        self.assertEqual(res_w['rows'][0]['intrinsic_points'], 1)
        self.assertEqual(res_w['rows'][0]['score'], 0)

        # 3. 5 vendors -> > 4 graph node limit -> unavailable (never sliced)
        src_o, info_o = scenario('B5', False, 'C001')
        for k in range(3):
            extra = deepcopy(src_o['tables']['vendors'][1])
            extra['vendor_id'] = f'SIM_V_EXTRA_{k}'
            extra['bank_account'] = f'SIM_B_{k}'
            extra['phone'] = f'090800000{k}'
            extra['address'] = f'ADDR_{k}'
            src_o['tables']['vendors'].append(extra)
        _rehash(src_o)
        plan_o = plan_b5_e4_from_rule_snapshot(_wrap(src_o, [info_o['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan_o['rows'][0]['available'])
        self.assertEqual(plan_o['rows'][0]['reason'], 'he_graph_node_limit')


if __name__ == '__main__':
    unittest.main()

