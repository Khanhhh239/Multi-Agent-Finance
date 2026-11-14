"""Tests for Slice 1: `agent2-rule-snapshot/1.0.0` P1 connected to Concrete `p1` circuit."""
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
from sme_fraud.import_files import ImportFailure, canonical, digest
from sme_fraud.native_rule_demo import authorities, finish, scenario
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshots import commit_fields

from experiments.he4 import circuits
from experiments.he4.rule_snapshot_adapter import (
    decode_p1_plan_results,
    plan_p1_from_rule_snapshot,
    prepare_p1_rule_snapshot,
)


def _scope(company='C001', actor='rules-he-tester'):
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


def _commit(store, scope, data, key='slice1-p1'):
    draft = store.upload(scope, canonical(data), 'rule-snapshot.json', key + '-upload')
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise AssertionError(preview['errors'])
    saved = store.commit(scope, draft['import_id'], commit_fields(preview), key + '-commit')
    return saved['snapshot']['snapshot_id']


def _run_plain_p1(plan):
    outputs = []
    for row in plan['rows']:
        for req in row.get('requests', []):
            out = circuits.p1(*[np.asarray(v, dtype=np.int64) for v in req['values']])
            outputs.append(out.tolist())
    return decode_p1_plan_results(plan, outputs)


class RuleSnapshotP1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SnapshotStore(Path(self.tmp.name) / 'snapshots.sqlite3')

    def _p1_native_entry(self, data, scope):
        sid = _commit(self.store, scope, data, 'native-' + digest(canonical(data))[:12])
        native = analyze_rule_snapshot(self.store, scope, sid, data['source']['as_of'], technical=True)
        return sid, native

    def test_p1_positive_negative_and_tolerance_boundaries_match_engine(self):
        TZ = timezone(timedelta(hours=7))
        for label, inv_gross, amounts, expected_hit, expected_excess in (
            ('exact_gross_no_hit', 10_000_000, [6_000_000, 4_000_000], False, 0),
            ('plus_1_tolerance_no_hit', 10_000_000, [6_000_000, 4_000_001], False, 1),
            ('plus_2_exceeds_hit', 10_000_000, [6_000_000, 4_000_002], True, 2),
            ('single_payment_no_prior_no_hit', 10_000_000, [12_000_000], False, 2_000_000),
            ('minimal_positive_no_hit', 10_000_000, [6_000_000, 1], False, 0),
        ):
            with self.subTest(label=label):
                c = Case()
                c.at = datetime(2025, 8, 12, 11, tzinfo=TZ)
                c.tables['employees'] = [c.director, c.maker, c.worker]
                c.tables['vendors'] = [c.vendor]
                c.vendor.update(
                    bank_account='SIM_VENDOR',
                    bank_code='SIMBANK',
                    phone='0902000000',
                    address='SIM_VENDOR_ADDRESS',
                    national_id='SIM_NATIONAL_VENDOR',
                )
                for idx, amt in enumerate(amounts):
                    target = c.pay(
                        c.at - timedelta(days=len(amounts) - 1 - idx),
                        amt,
                        invoice_number='INV_BOUNDARY_' + label,
                        invoice_gross_vnd=inv_gross,
                    )
                authorities(c)
                src = finish(c, 'C001')
                data = _wrap(src, [target['transaction_id']])
                sid, native = self._p1_native_entry(data, _scope('C001'))
                native_p1 = next(r for r in native['rows'][0]['rule_coverage']['rules'] if r['rule_id'] == 'P1')

                plan = prepare_p1_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'])
                decoded = _run_plain_p1(plan)
                he_row = decoded['rows'][0]
                self.assertTrue(he_row['available'])
                self.assertEqual(he_row['matched'], expected_hit)
                self.assertEqual(he_row['matched'], native_p1['matched'])
                self.assertEqual(he_row['score'], native_p1['score'])
                self.assertEqual(he_row['row_check']['excess_vnd'], expected_excess)

    def test_simultaneous_batch_p1_group_and_conflicting_gross_gap(self):
        c = Case()
        c.at = datetime(2025, 8, 12, 11, tzinfo=timezone(timedelta(hours=7)))
        c.tables['employees'] = [c.director, c.maker, c.worker]
        c.tables['vendors'] = [c.vendor]
        t1 = c.pay(c.at, 6_000_000, invoice_number='INV_SIM', invoice_gross_vnd=10_000_000)
        t2 = c.pay(c.at, 5_000_000, invoice_number='INV_SIM', invoice_gross_vnd=10_000_000)
        authorities(c)
        src = finish(c, 'C001')
        data = _wrap(src, [t1['transaction_id'], t2['transaction_id']])
        sid, native = self._p1_native_entry(data, _scope('C001'))

        plan = prepare_p1_rule_snapshot(self.store, _scope('C001'), sid, src['as_of'])
        decoded = _run_plain_p1(plan)
        for idx in range(2):
            self.assertFalse(decoded['rows'][idx]['matched'])
            self.assertEqual(len(decoded['rows'][idx]['simultaneous_checks']), 1)
            grp = decoded['rows'][idx]['simultaneous_checks'][0]
            self.assertTrue(grp['matched'])
            self.assertEqual(grp['cumulative_paid_vnd'], 11_000_000)
            self.assertEqual(grp['excess_vnd'], 1_000_000)

        native_groups = next(r['groups'] for r in native['catalogue_results'] if r['rule_id'] == 'P1')
        self.assertEqual(len(native_groups), 1)
        self.assertTrue(native_groups[0]['signal'])

        # Conflicting invoice_gross_vnd in simultaneous batch -> unavailable, never evaluates partial group
        src_bad = deepcopy(src)
        src_bad['tables']['transactions'][-1]['invoice_gross_vnd'] = 12_000_000
        _rehash(src_bad)
        plan_bad = plan_p1_from_rule_snapshot(_wrap(src_bad, [t1['transaction_id'], t2['transaction_id']]), _scope('C001'))
        self.assertFalse(plan_bad['rows'][0]['available'])
        self.assertEqual(plan_bad['rows'][0]['reason'], 'simultaneous_invoice_gross_gap')
        self.assertEqual(plan_bad['rows'][0]['requests'], [])

    def test_exceeding_four_prior_or_batch_rows_is_unavailable_not_sliced(self):
        src, info = scenario('P1', True, 'C001')
        tx0 = deepcopy(src['tables']['transactions'][0])
        # Add 4 more earlier payments -> total 5 prior payments before target (>4 cap)
        for i in range(4):
            extra = deepcopy(tx0)
            extra['transaction_id'] = f'EXTRA_PRIOR_{i}'
            extra['amount_vnd'] = 100_000
            extra['posted_at'] = f'2025-08-0{i + 2}T11:00:00+07:00'
            extra['observed_at'] = extra['posted_at']
            extra['created_at'] = extra['posted_at']
            extra['approved_at'] = extra['posted_at']
            src['tables']['transactions'].insert(-1, extra)
        _rehash(src)
        data = _wrap(src, [info['target_transaction_id']])
        plan = plan_p1_from_rule_snapshot(data, _scope('C001'))
        self.assertEqual(len(plan['rows']), 1)
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['status'], 'unavailable')
        self.assertEqual(plan['rows'][0]['reason'], 'he_p1_source_limit')
        self.assertEqual(plan['rows'][0]['requests'], [])
        decoded = _run_plain_p1(plan)
        self.assertFalse(decoded['rows'][0]['available'])
        self.assertIsNone(decoded['rows'][0]['matched'])

    def test_missing_sources_clock_and_not_applicable_conditions(self):
        # 1. Missing coverage on required table -> unavailable
        src, info = scenario('P1', True, 'C001')
        src['coverage'].pop('transaction_documents')
        plan = plan_p1_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['status'], 'unavailable')
        self.assertEqual(plan['rows'][0]['reason'], 'source_coverage_missing')

        # 2. Missing invoice_number on candidate -> unavailable
        src, info = scenario('P1', False, 'C001')
        src['tables']['transactions'][-1]['invoice_number'] = ''
        _rehash(src)
        plan = plan_p1_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['reason'], 'invoice_identity_not_provided')

        # 3. Late invoice_issued_at > posted_at -> unavailable
        src, info = scenario('P1', True, 'C001')
        src['tables']['transactions'][-1]['invoice_issued_at'] = '2025-08-20T00:00:00+07:00'
        _rehash(src)
        plan = plan_p1_from_rule_snapshot(_wrap(src, [info['target_transaction_id']]), _scope('C001'))
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['reason'], 'invoice_not_available_at_cutoff')

        # 4. Non-vendor_payment candidate -> not_applicable
        src_pay, info_pay = scenario('E1', True, 'C001')
        plan_na = plan_p1_from_rule_snapshot(_wrap(src_pay, [info_pay['target_transaction_id']]), _scope('C001'))
        self.assertEqual(plan_na['rows'][0]['status'], 'not_applicable')
        self.assertFalse(plan_na['rows'][0]['available'])

        # 5. All prior payments zero (parity guard against rules.py:557) -> unavailable
        src_zero, info_zero = scenario('P1', True, 'C001')
        src_zero['tables']['transactions'][0]['amount_vnd'] = 0
        _rehash(src_zero)
        plan_zero = plan_p1_from_rule_snapshot(_wrap(src_zero, [info_zero['target_transaction_id']]), _scope('C001'))
        self.assertEqual(plan_zero['rows'][0]['status'], 'unavailable')
        self.assertEqual(plan_zero['rows'][0]['reason'], 'he_p1_nonpositive_prior_unsupported')

    def test_c001_c002_company_isolation_and_shared_audit_0000_id(self):
        def make_audit_0000(company, positive):
            c = Case()
            c.at = datetime(2025, 8, 12, 11, tzinfo=timezone(timedelta(hours=7)))
            c.tables['employees'] = [c.director, c.maker, c.worker]
            c.tables['vendors'] = [c.vendor]
            prior = c.pay(c.at - timedelta(days=1), 6_000_000, invoice_number='SIM_SHARED_INVOICE', invoice_gross_vnd=10_000_000)
            target = c.pay(c.at, 6_000_000 if positive else 3_000_000, invoice_number='SIM_SHARED_INVOICE', invoice_gross_vnd=10_000_000)
            # Rename explicitly so prior is PRIOR_0000 and target is shared AUDIT_0000 across C001/C002
            prior['transaction_id'] = 'PRIOR_0000'
            target['transaction_id'] = 'AUDIT_0000'
            authorities(c)
            return finish(c, company)

        src1 = make_audit_0000('C001', True)
        src2 = make_audit_0000('C002', False)
        sid1 = _commit(self.store, _scope('C001'), _wrap(src1, ['AUDIT_0000']), 'iso-c1')
        sid2 = _commit(self.store, _scope('C002'), _wrap(src2, ['AUDIT_0000']), 'iso-c2')

        res1 = _run_plain_p1(prepare_p1_rule_snapshot(self.store, _scope('C001'), sid1, src1['as_of']))
        res2 = _run_plain_p1(prepare_p1_rule_snapshot(self.store, _scope('C002'), sid2, src2['as_of']))
        self.assertTrue(res1['rows'][0]['matched'])
        self.assertFalse(res2['rows'][0]['matched'])
        self.assertEqual(res1['company_id'], 'C001')
        self.assertEqual(res2['company_id'], 'C002')

        with self.assertRaises(ImportFailure):
            prepare_p1_rule_snapshot(self.store, _scope('C002'), sid1, src1['as_of'])
        with self.assertRaises(ImportFailure):
            prepare_p1_rule_snapshot(
                self.store, _scope('C001'), sid1, src1['as_of'], recheck=lambda: _scope('C002')
            )


if __name__ == '__main__':
    unittest.main()
