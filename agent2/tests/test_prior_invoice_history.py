"""Unknown prior allocation sources must stay missing, not become known zero."""
import copy
import math
from pathlib import Path
import tempfile
import unittest

from sme_fraud.feature_pipeline import export_artifact, read_artifact
from sme_fraud.snapshot_features import build_feature_rows, build_from_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshot_features import bundle, scope, feature, committed, AS_OF

PRIOR = ('prior_invoice_payment_count', 'prior_invoice_allocation_log_abs', 'prior_invoice_allocation_negative')
LATE = '2026-10-13T00:00:00+07:00'


class PriorInvoiceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.data = bundle('C001')

    def unknown_invoice(self, observed='2026-10-12T08:00:00+07:00'):
        invoice = copy.deepcopy(self.data['invoices'][0])
        invoice.update(revision=2, observed_at=observed)
        self.data['invoices'].append(invoice)
        allocation = next(a for a in self.data['payment_allocations'] if a['record_id'] == 'A_H0')
        allocation['invoice_ref']['revision'] = 2

    def build(self, at=AS_OF):
        return build_feature_rows(self.data, scope(), at)

    def evidence(self, result, identity):
        index = next(r['row_index'] for r in result['rows'] if r['record_id'] == identity)
        return result['evidence'][index]

    def assert_missing(self, result, identity):
        f = feature(result, 'C001', identity)
        evidence = self.evidence(result, identity)
        for column in PRIOR:
            self.assertIsNone(f[column], column)
            self.assertEqual(evidence['missing_reasons'][column], 'prior_invoice_history_incomplete')
            index = next(r['row_index'] for r in result['rows'] if r['record_id'] == identity)
            self.assertIs(result['missing'][index][result['contract']['columns'].index(column)], True)
        self.assertIsNone(evidence['prior_signed_allocation_vnd'])
        self.assertEqual(evidence['prior_invoice_history']['status'], 'unavailable')
        return evidence

    def test_unknown_invoice_revision_marks_features_and_exact_total_missing(self):
        self.unknown_invoice()
        result = self.build()
        e = self.assert_missing(result, 'T001')
        issue = e['prior_invoice_history']['unavailable_references'][0]
        self.assertEqual(issue['source']['record_id'], 'A_H0')
        self.assertEqual(issue['field'], 'invoice_ref')
        self.assertEqual(issue['reference'], dict(table='invoices', record_id='I001', revision=2))
        self.assertIn('Chưa đủ dữ liệu', issue['message'])
        self.assertTrue(issue['action'])
        self.assertIn(('payment_allocations', 'A_H0', 1), {(r['table'], r['record_id'], r['revision']) for r in e['records']})
        self.assertNotIn(('invoices', 'I001', 2), {(r['table'], r['record_id'], r['revision']) for r in e['records']})
        self.assertEqual(feature(result, 'C001', 'T001')['allocation_to_invoice_face_ratio'], .3)

    def test_later_global_run_does_not_backfill_old_rows(self):
        self.unknown_invoice()
        before = self.build(); after = self.build(LATE)
        self.assert_missing(before, 'T001')
        self.assertEqual(feature(before, 'C001', 'T001'), feature(after, 'C001', 'T001'))
        self.assertEqual(self.evidence(before, 'T001'), self.evidence(after, 'T001'))

    def test_new_later_row_can_use_source_that_has_become_known(self):
        self.unknown_invoice()
        result = self.build(LATE)
        f = feature(result, 'C001', 'NEXT01'); e = self.evidence(result, 'NEXT01')
        self.assertEqual(f['prior_invoice_payment_count'], 3)
        self.assertAlmostEqual(f['prior_invoice_allocation_log_abs'], math.log1p(17000000))
        self.assertEqual(e['prior_signed_allocation_vnd'], 17000000)
        self.assertEqual(e['prior_invoice_history']['status'], 'available')
        self.assertEqual(e['prior_invoice_history']['unavailable_references'], [])

    def test_partial_known_history_is_not_presented_as_complete_total(self):
        self.unknown_invoice(observed='2026-10-14T08:00:00+07:00')
        result = self.build(LATE)
        e = self.assert_missing(result, 'NEXT01')
        self.assertEqual({r['record_id'] for r in e['records'] if r['table'] == 'payment_allocations'}, {'A_H0', 'A_T001', 'A_T002', 'A_NEXT01'})

    def test_known_empty_history_stays_zero_not_missing(self):
        result = build_feature_rows(bundle('C002'), scope('C002'), AS_OF)
        f = feature(result, 'C002', 'T001'); e = self.evidence(result, 'T001')
        self.assertEqual([f[k] for k in PRIOR], [0, 0.0, 0])
        self.assertEqual(e['prior_signed_allocation_vnd'], 0)
        self.assertEqual(e['prior_invoice_history']['status'], 'available')

    def test_unknown_unrelated_invoice_does_not_poison_current_invoice(self):
        invoice = copy.deepcopy(self.data['invoices'][0])
        invoice.update(record_id='I_OTHER', number='other-invoice')
        later = copy.deepcopy(invoice); later.update(revision=2, observed_at='2026-10-12T08:00:00+07:00')
        self.data['invoices'].extend([invoice, later])
        allocation = next(a for a in self.data['payment_allocations'] if a['record_id'] == 'A_H0')
        allocation['invoice_ref'] = dict(record_id='I_OTHER', revision=2)
        result = self.build(); f = feature(result, 'C001', 'T001')
        self.assertEqual([f[k] for k in PRIOR], [0, 0.0, 0])
        self.assertEqual(self.evidence(result, 'T001')['prior_invoice_history']['status'], 'available')

    def test_allocation_not_yet_known_cannot_change_old_features_or_limits(self):
        self.data['payment_allocations'] = [a for a in self.data['payment_allocations'] if a['record_id'] != 'A_H0']
        absent = self.build()
        allocation = next(a for a in bundle('C001')['payment_allocations'] if a['record_id'] == 'A_H0')
        allocation['observed_at'] = '2026-10-12T08:00:00+07:00'
        self.data['payment_allocations'].append(allocation)
        later_source = self.build()
        self.assertEqual(absent, later_source)

    def test_multiple_missing_references_are_deterministic_under_reordering(self):
        self.unknown_invoice(observed='2026-10-14T08:00:00+07:00')
        for a in self.data['payment_allocations']:
            if a['record_id'] in {'A_T001', 'A_T002'}:
                a['invoice_ref']['revision'] = 2
        first = self.build(LATE); self.assert_missing(first, 'NEXT01')
        for rows in self.data.values():
            if isinstance(rows, list): rows.reverse()
        self.assertEqual(first, self.build(LATE))

    def test_signed_allocations_cancelling_to_zero_remain_available(self):
        correction = copy.deepcopy(next(a for a in self.data['payment_allocations'] if a['record_id'] == 'A_H0'))
        correction.update(record_id='A_CANCEL', kind='adjustment', amount_vnd=-4000000,
                          observed_at='2026-10-09T10:00:00+07:00', effective_at='2026-10-09T10:00:00+07:00',
                          adjustment_reason='Synthetic cancellation', adjusts_ref=dict(record_id='A_H0', revision=1))
        self.data['payment_allocations'].append(correction)
        result = self.build(); f = feature(result, 'C001', 'T001'); e = self.evidence(result, 'T001')
        self.assertEqual([f[k] for k in PRIOR], [1, 0.0, 0])
        self.assertEqual(e['prior_signed_allocation_vnd'], 0)
        self.assertEqual(e['prior_invoice_history']['status'], 'available')

    def test_unknown_revision_of_a_known_prior_transaction_is_also_missing(self):
        tx = copy.deepcopy(next(t for t in self.data['transactions'] if t['record_id'] == 'H0'))
        tx.update(revision=2, observed_at='2026-10-12T08:00:00+07:00')
        self.data['transactions'].append(tx)
        next(a for a in self.data['payment_allocations'] if a['record_id'] == 'A_H0')['transaction_ref']['revision'] = 2
        e = self.assert_missing(self.build(), 'T001')
        self.assertEqual(e['prior_invoice_history']['unavailable_references'][0]['field'], 'transaction_ref')

    def test_known_but_not_yet_effective_invoice_revision_is_missing(self):
        self.unknown_invoice(observed='2026-10-09T07:00:00+07:00')
        self.data['invoices'][-1]['effective_at'] = '2026-10-12T08:00:00+07:00'
        self.assert_missing(self.build(), 'T001')

    def test_missing_history_in_one_company_does_not_affect_the_other(self):
        self.data = bundle()
        self.unknown_invoice()
        result = build_feature_rows(self.data, scope(('C001', 'C002')), AS_OF)
        # Both companies deliberately reuse I001/T001. The unresolved C001
        # invoice must not make C002's observed-empty history unavailable.
        f = feature(result, 'C002', 'T001')
        self.assertEqual([f[k] for k in PRIOR], [0, 0.0, 0])
        c1 = next(e for r, e in zip(result['rows'], result['evidence']) if r['company_id'] == 'C001' and r['record_id'] == 'T001')
        c2 = next(e for r, e in zip(result['rows'], result['evidence']) if r['company_id'] == 'C002' and r['record_id'] == 'T001')
        self.assertEqual(c1['prior_invoice_history']['status'], 'unavailable')
        self.assertEqual(c2['prior_invoice_history']['status'], 'available')

    def test_snapshot_export_keeps_null_missing_and_provenance_separate(self):
        self.unknown_invoice()
        with tempfile.TemporaryDirectory() as temporary:
            store = SnapshotStore(Path(temporary)/'snapshot.sqlite3')
            identity = committed(store, data=self.data)
            result = build_from_snapshot(store, scope(), identity, AS_OF)
            saved = export_artifact(result, Path(temporary)/'artifacts')
            artifact = read_artifact(saved['directory'])
            self.assert_missing(artifact, 'T001')
            self.assertEqual(len(artifact['contract']['columns']), 33)


if __name__ == '__main__':
    unittest.main()
