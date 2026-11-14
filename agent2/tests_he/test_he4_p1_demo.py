from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from experiments.he4.p1_demo import source,scope,save_snapshot,inspect,AS_OF
from experiments.he4.snapshot_adapter import prepare_snapshot
from sme_fraud.imports import validate_input
from sme_fraud.import_files import canonical,ImportFailure
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.p1_inputs import export_manifest


class P1SourceDemo(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=SnapshotStore(Path(self.tmp.name)/'snapshots.sqlite3')

    def test_both_companies_manual_totals_group_rules_and_all_rows(self):
        for company in ('C001','C002'):
            with self.subTest(company=company):
                data=source(company);self.assertFalse(validate_input(data,scope(company))['errors'])
                sid=save_snapshot(self.store,company,data);report,_=inspect(self.store,company,sid)
                self.assertEqual(report['row_count'],8)
                self.assertEqual(report['statuses'],dict(evaluated_hit=1,evaluated_no_hit=5,not_applicable=1,unavailable=1))
                rows={r['record_id']:r for r in report['rows']}
                self.assertEqual(rows['P1_T03']['row_score'],20);self.assertEqual(rows['P1_T06']['row_score'],0)
                self.assertEqual(rows['P1_T06']['simultaneous_checks'][0]['points'],20)
                self.assertEqual(rows['P1_T06']['simultaneous_checks'],rows['P1_T07']['simultaneous_checks'])

    def test_missing_history_has_invoice_and_allocation_but_no_score_or_request(self):
        data=source('C001');sid=save_snapshot(self.store,'C001',data);report,plan=inspect(self.store,'C001',sid)
        row=next(r for r in report['rows'] if r['record_id']=='P1_T08')
        self.assertIsNone(row['row_score']);self.assertIsNone(row['matched'])
        self.assertTrue(any(g['code']=='p1_history_scope_missing' for g in row['gaps']))
        self.assertTrue(any(i['record_id']=='P1_I_GAP' for i in data['invoices']))
        self.assertTrue(any(a['transaction_ref']['record_id']=='P1_T08' for a in data['payment_allocations']))
        branch=next(r for r in plan['rows'] if r['record_id']=='P1_T08')['branches']['rules']
        self.assertFalse(branch['available']);self.assertEqual(branch['requests'],[])

    def test_negative_adjustment_retained_and_reduces_later_history_once(self):
        data=source('C001');before=canonical(data);sid=save_snapshot(self.store,'C001',data);report,plan=inspect(self.store,'C001',sid)
        later=next(r for r in report['rows'] if r['record_id']=='P1_T05')['invoice_checks'][0]
        self.assertEqual(later['prior_paid_vnd'],8_000_000);self.assertEqual(later['cumulative_paid_vnd'],9_000_000)
        adjustment=next(t for t in data['transactions'] if t['record_id']=='P1_T04');self.assertEqual(adjustment['amount_vnd'],-4_000_000)
        self.assertEqual(canonical(data),before)
        request=next(r for r in plan['rows'] if r['record_id']=='P1_T05')['branches']['rules']['requests'][0]
        self.assertEqual(len(request['source_refs']['prior']),4)

    def test_mutated_source_cannot_reuse_manifest_and_expected_labels_absent(self):
        data=source('C001');data['transactions'][1]['amount_vnd']+=1
        codes={e['code'] for e in validate_input(data,scope('C001'))['errors']}
        self.assertIn('P1_MANIFEST_CHECKSUM',codes)
        raw=canonical(source('C001'))
        for key in (b'expected_status',b'fraud_label',b'evaluated_hit'):self.assertNotIn(key,raw)

    def test_company_scope_and_repeated_commit(self):
        data=source('C001');first=save_snapshot(self.store,'C001',data);self.assertEqual(first,save_snapshot(self.store,'C001',data))
        other=save_snapshot(self.store,'C002',source('C002'));self.assertNotEqual(first,other)
        with self.assertRaises(ImportFailure):prepare_snapshot(self.store,scope('C002'),first,AS_OF)

    def test_late_invoice_does_not_rewrite_past_and_no_fit_during_check(self):
        data=source('C001');first=save_snapshot(self.store,'C001',data);before,_=inspect(self.store,'C001',first)
        late=deepcopy(data['invoices'][0]);late.update(revision=2,amount_vnd=99_000_000,observed_at='2026-10-12T08:00:00+07:00');data['invoices'].append(late)
        second=save_snapshot(self.store,'C001',data)
        with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('implicit fit')):
            after,_=inspect(self.store,'C001',second)
        self.assertEqual(before['rows'],after['rows'])

    def test_fifth_historical_source_is_unavailable_not_trimmed_or_netted(self):
        data=source('C001');tx=deepcopy(data['transactions'][0]);tx.update(record_id='P1_EXTRA',effective_at='2026-10-02T09:00:00+07:00',observed_at='2026-10-02T09:00:00+07:00',amount_vnd=500_000,accounting_lines=[dict(account='331',debit_vnd=500_000,credit_vnd=0),dict(account='112',debit_vnd=0,credit_vnd=500_000)]);tx['source']['record_id']='P1_EXTRA'
        a=deepcopy(data['payment_allocations'][0]);a.update(record_id='P1_A_EXTRA',effective_at=tx['effective_at'],observed_at=tx['observed_at'],amount_vnd=500_000,transaction_ref=dict(record_id='P1_EXTRA',revision=1));a['source']['record_id']='P1_A_EXTRA'
        data['transactions'].append(tx);data['payment_allocations'].append(a)
        for claim in data['payment_history_coverage']:claim['manifest']=export_manifest(data,claim)
        sid=save_snapshot(self.store,'C001',data);plan=prepare_snapshot(self.store,scope('C001'),sid,AS_OF)
        branch=next(r for r in plan['rows'] if r['record_id']=='P1_T05')['branches']['rules']
        self.assertFalse(branch['available']);self.assertEqual(branch['reason'],'he_p1_source_limit');self.assertEqual(branch['requests'],[])


if __name__=='__main__':unittest.main()
