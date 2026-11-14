"""Tests for Slice 2: `agent2-rule-snapshot/1.0.0` C3 connected to Concrete `c3` circuit."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
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
from sme_fraud.native_rule_demo import approved, authorities, base, finish, scenario
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields

from experiments.he4 import c3_circuit as c3m
from experiments.he4.rule_snapshot_c3_adapter import (
    decode_c3_plan_results,
    plan_c3_from_rule_snapshot,
    prepare_c3_rule_snapshot,
)


def _scope(company='C001', actor='c3-he-tester'):
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


def _commit(store, scope, data, key='slice2-c3'):
    draft = store.upload(scope, canonical(data), 'rule-snapshot.json', key + '-upload')
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise AssertionError(preview['errors'])
    return store.commit(scope, draft['import_id'], commit_fields(preview), key + '-commit')['snapshot']['snapshot_id']


def _run_plain_c3(plan):
    c3m.ARRAY = np.array
    outputs = []
    for row in plan['rows']:
        for req in row.get('requests', []):
            out = c3m.c3(*[np.asarray(v, dtype=np.int64) for v in req['values']])
            outputs.append(out.tolist())
    return decode_c3_plan_results(plan, outputs)


class RuleSnapshotC3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SnapshotStore(Path(self.tmp.name) / 'snapshots.sqlite3')

    def test_c3_time_and_explicit_authority_boundaries_match_engine(self):
        # 1. Exact boundaries: 0s (hit), 59s (hit), 59.999s (hit), 60s (no hit), created > approved (-1s -> no hit),
        #    and low/standard authority -> no hit even at 20s!
        TZ = timezone(timedelta(hours=7))
        cases = [
            ('hit_0s', 0, 60_000_000, 'high', True),
            ('hit_59s', 59, 60_000_000, 'high', True),
            ('no_hit_60s', 60, 60_000_000, 'high', False),
            ('no_hit_negative_dt', -1, 60_000_000, 'high', False),
            ('no_hit_standard_level', 20, 60_000_000, 'standard', False),
            ('hit_executive_level', 20, 10_000_000, 'executive', True),
        ]
        for label, dt_sec, amount, auth_level, expected_hit in cases:
            with self.subTest(label=label):
                c = base()
                approved_at = c.at
                created_at = approved_at - timedelta(seconds=dt_sec)
                target = c.pay(amount=amount, created_at=created_at.isoformat(timespec='seconds'))
                authorities(c)
                c.tables['approval_authorities'][1]['authority_level'] = auth_level
                src = finish(c, 'C001')
                data = _wrap(src, [target['transaction_id']])
                sid = _commit(self.store, _scope('C001'), data, 'c3-' + label)
                native = analyze_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'], technical=True)
                native_c3 = next(r for r in native['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'C3')

                plan = prepare_c3_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'])
                res = _run_plain_c3(plan)
                row = res['rows'][0]
                self.assertTrue(row['available'])
                self.assertEqual(row['matched'], expected_hit)
                self.assertEqual(row['matched'], native_c3['matched'])
                self.assertEqual(row['score'], native_c3['score'])

    def test_c3_encrypted_authority_specificity_and_band_ambiguity(self):
        # Multiple rules overlapping amount band: higher specificity wins; tied ambiguous levels become unavailable
        src, info = scenario('C3', True, 'C001')
        tables = src['tables']
        base_auth = deepcopy(tables['approval_authorities'][1])
        # Base auth (specific employee_id, subject_role='') is high for 0..1B.
        # Add a role-only rule (lower specificity -> rank lower) with level='standard' -> specific employee rule must win!
        role_auth = deepcopy(base_auth)
        role_auth['authority_id'] = 'SIM_ROLE_LOW'
        role_auth['subject_employee_id'] = ''
        role_auth['subject_role'] = tables['employees'][0]['role']
        role_auth['authority_level'] = 'standard'
        tables['approval_authorities'].append(role_auth)
        _rehash(src)

        res = _run_plain_c3(plan_c3_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001')))
        self.assertTrue(res['rows'][0]['available'])
        self.assertTrue(res['rows'][0]['matched'])
        self.assertTrue(res['rows'][0]['details']['explicit_high'])
        self.assertFalse(res['rows'][0]['details']['ambiguous_authority'])

        # Now add a second equally-specific rule with conflicting authority_level covering the same amount -> FHE detects ambiguous_authority -> unavailable!
        tie_auth = deepcopy(base_auth)
        tie_auth['authority_id'] = 'SIM_TIE_CONFLICT'
        tie_auth['authority_level'] = 'standard'
        tables['approval_authorities'].append(tie_auth)
        _rehash(src)
        sid = _commit(self.store, _scope('C001'), _wrap(src, [info['target_transaction_id']]), 'c3-ambig')
        native = analyze_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'], technical=True)
        native_c3 = next(r for r in native['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'C3')
        self.assertEqual(native_c3['status'], 'unavailable')

        res_ambig = _run_plain_c3(prepare_c3_rule_snapshot(self.store, _scope('C001'), sid, src['as_of']))
        self.assertFalse(res_ambig['rows'][0]['available'])
        self.assertEqual(res_ambig['rows'][0]['status'], 'unavailable')
        self.assertEqual(res_ambig['rows'][0]['reason'], 'authority_not_covered_or_ambiguous_at_action')
        self.assertTrue(res_ambig['rows'][0]['details']['ambiguous_authority'])

    def test_c3_legacy_fallback_threshold_inside_circuit_and_missing_coverage_guard(self):
        # 1. With enforce_source_guards=True (rule-snapshot default): empty coverage -> unavailable
        src, info = scenario('C3', True, 'C001')
        src['tables']['approval_authority_coverage'] = []
        _rehash(src)
        plan_guarded = plan_c3_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan_guarded['rows'][0]['available'])
        self.assertEqual(plan_guarded['rows'][0]['status'], 'unavailable')

        # 2. Legacy fallback circuit mode (`enforce_source_guards=False`): exercises encrypted legacy_high (`>= 50M`)
        for amt, expect_hit in ((49_999_999, False), (50_000_000, True)):
            with self.subTest(amt=amt):
                src_l = deepcopy(src)
                src_l['tables']['transactions'][-1]['amount_vnd'] = amt
                _rehash(src_l)
                plan_leg = plan_c3_from_rule_snapshot(
                    _wrap(src_l, [info['target_transaction_id']]),
                    _scope('C001'),
                    enforce_source_guards=False,
                )
                res_leg = _run_plain_c3(plan_leg)
                self.assertEqual(res_leg['rows'][0]['matched'], expect_hit)

    def test_c3_exceeding_four_authorities_is_unavailable_not_sliced(self):
        src, info = scenario('C3', True, 'C001')
        base_auth = deepcopy(src['tables']['approval_authorities'][1])
        for i in range(4):
            extra = deepcopy(base_auth)
            extra['authority_id'] = f'EXTRA_AUTH_{i}'
            src['tables']['approval_authorities'].append(extra)
        _rehash(src)
        plan = plan_c3_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['reason'], 'he_c3_authority_limit')
        self.assertEqual(plan['rows'][0]['requests'], [])


if __name__ == '__main__':
    unittest.main()

