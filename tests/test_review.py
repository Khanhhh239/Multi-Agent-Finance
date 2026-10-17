"""Local UI API tests for real state transitions, quotas and evidence boundaries."""
import csv
import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from sme_fraud.feedback import read_audit, record_feedback
from sme_fraud.generate import write_csv
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore


def make_fixture(root):
    data, report = root / 'data/sme_fraud_003', root / 'reports/sme_fraud_003'
    data.mkdir(parents=True)
    report.mkdir(parents=True)
    write_csv(data / 'companies.csv', [dict(company_id=c, name=f'SME {c}', accounting_framework='TT133') for c in ['C001', 'C002']])
    write_csv(data / 'employees.csv', [dict(employee_id='E01', company_id='C001', full_name='Người rà soát mẫu',
        recorded_at='2023-01-01T00:00:00+07:00', bank_account='EMPBANK', phone='PHONE', role='chief_accountant')])
    write_csv(data / 'vendors.csv', [dict(vendor_id='V01', company_id='C001', name='<script>Đối tác</script>',
        recorded_at='2023-01-01T00:00:00+07:00', bank_account='BANK01', phone='PHONE2')])
    write_csv(data / 'customers.csv', [dict(customer_id='CU01', company_id='C001', name='Khách hàng mẫu',
        recorded_at='2023-01-01T00:00:00+07:00')])
    transactions, cases, hits, docs, lines, events = [], [], [], [], [], []
    for i in range(8):
        cid = 'C002' if i == 7 else 'C001'
        tid = f'T{i}'
        posted = f'2025-08-{i + 1:02}T12:00:00+07:00'
        row = dict(transaction_id=tid, company_id=cid, posted_at=posted, txn_type='vendor_payment',
            amount_vnd=1_000_000, approval_limit_vnd=20_000_000, vendor_id='V01', employee_id='',
            creator_id='E01', approver_id='E01', journal_document_id=f'J{i}', linked_document_id='',
            recipient_account='BANK01', invoice_number='HD001', invoice_gross_vnd=1_000_000,
            debit_account='331', credit_account='112', is_financial_entry=1, payment_channel='bank',
            support_doc_count=2, business_purpose='Thanh toán')
        transactions.append(row)
        docs.append(dict(document_id=f'J{i}', company_id=cid, posted_at=posted, purpose='vendor_payment'))
        lines += [dict(document_id=f'J{i}', account_code='331', debit_vnd=1_000_000, credit_vnd=0),
                  dict(document_id=f'J{i}', account_code='112', debit_vnd=0, credit_vnd=1_000_000)]
        if i:
            cases.append(dict(case_id=f'RC_{i}', company_id=cid, entity='entity:V01', opened_at=posted,
                last_seen_at=posted, priority='cao_nhat', max_score=20 + i, owner_id='E01', status='new',
                conclusion='', reviewer_note='', transaction_ids=json.dumps([tid]), rule_ids='P1',
                explanation_vi='Thanh toán vượt hóa đơn', sla_due_at=f'2025-08-{i + 2:02}T12:00:00+07:00',
                sla_basis='calendar_hours', observation_count=1, case_type='transaction', source_scope='',
                source_status='', estimated_minutes=20, requires_rereview=0, rereview_due_at=''))
            hits.append(dict(transaction_id=tid, company_id=cid, detected_at=posted, rule_id='P1',
                rule_name='Thanh toán vượt hóa đơn', points=20, hard_trigger=1, suppressed_reason='',
                evidence=dict(cumulative_paid_vnd=2_000_000, invoice_gross_vnd=1_000_000),
                related_transaction_ids=['T0'], graph_path=[]))
            events.append(dict(case_id=f'RC_{i}', event_at=posted, event='opened', transaction_id=tid, rule_score=20 + i, priority='cao_nhat'))
    source_cutoff = '2025-08-20T23:59:59+07:00'
    cases += [dict(case_id='SC_F3', company_id='C001', entity='source:series:PC-2025', opened_at=source_cutoff,
        last_seen_at=source_cutoff, priority='trung_binh', max_score=0, owner_id='E01', status='new', conclusion='',
        reviewer_note='', transaction_ids='[]', rule_ids='F3', explanation_vi='Dải số chứng từ có khoảng trống chưa giải trình',
        sla_due_at='2025-08-27T23:59:59+07:00', sla_basis='calendar_hours_from_source_finding_policy', observation_count=1,
        case_type='source', source_scope='series:PC-2025', source_status='evaluated', estimated_minutes=45,
        requires_rereview=0, rereview_due_at=''),
        dict(case_id='SC_F4', company_id='C001', entity='source:invoice:INV-01', opened_at=source_cutoff,
        last_seen_at=source_cutoff, priority='thap', max_score=0, owner_id='E01', status='new', conclusion='',
        reviewer_note='', transaction_ids='[]', rule_ids='F4', explanation_vi='Thiếu coverage hoặc bằng chứng nguồn để đánh giá công nợ hóa đơn',
        sla_due_at='2025-09-03T23:59:59+07:00', sla_basis='calendar_hours_from_source_finding_policy', observation_count=1,
        case_type='source', source_scope='invoice:INV-01', source_status='information_gap', estimated_minutes=35,
        requires_rereview=1, rereview_due_at='2025-08-27T23:59:59+07:00')]
    events += [dict(case_id='SC_F3', event_at=source_cutoff, event='opened', transaction_id='', rule_score=0, priority='trung_binh'),
               dict(case_id='SC_F4', event_at=source_cutoff, event='opened', transaction_id='', rule_score=0, priority='thap')]
    for filename, rows in [('transactions.csv', transactions), ('journal_documents.csv', docs), ('journal_lines.csv', lines)]:
        write_csv(data / filename, rows)
    write_csv(report / 'case_queue.csv', cases)
    write_csv(report / 'case_events.csv', events)
    coverage = [dict(rule_id='P1', name='Thanh toán trùng', status='implemented', scope='transaction', note=''),
                dict(rule_id='F3', name='Khoảng trống/trùng số chứng từ', status='implemented', scope='source_diagnostic', note=''),
                dict(rule_id='F4', name='Công nợ kéo dài', status='implemented', scope='source_diagnostic', note='')]
    (report / 'rule_coverage.json').write_text(json.dumps(coverage, ensure_ascii=False), encoding='utf-8')
    (report / 'rule_hits.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in hits) + '\n', encoding='utf-8')
    findings = [dict(rule_id='F3', company_id='C001', cutoff_at=source_cutoff, scope='series:PC-2025', status='evaluated',
        signal=True, points=0, action='source_review_only', evidence=dict(series=dict(series_id='PC-2025', document_type='payment',
        start_number=1, closed_through_number=10, closed_at=source_cutoff, cancellation_log_complete=1),
        missing_numbers=[7], cancellations=[])),
        dict(rule_id='F4', company_id='C001', cutoff_at=source_cutoff, scope='invoice:INV-01', status='information_gap',
        signal=None, points=0, action='collection_review_only', evidence=dict(invoice=dict(invoice_id='INV-01', customer_id='CU01',
        gross_vnd=12_000_000, issued_at='2025-05-01T00:00:00+07:00', due_at='2025-05-31T00:00:00+07:00'),
        known_paid_vnd=2_000_000, outstanding_vnd=10_000_000, overdue_days=81, receipt_allocations=[],
        invalid_allocation_ids=['ALLOC-01'], receipt_coverage=[], approved_explanations=[]))]
    (report / 'evidence_findings.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in findings)+'\n', encoding='utf-8')
    # The UI does not require or read truth/split/features files.
    return data, report


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data, self.report = make_fixture(self.root)
        self.when = [datetime.fromisoformat('2026-10-13T09:00:00+07:00')]
        self.store = ReviewStore(self.root / 'data', self.root / 'reports', self.root / 'cache.sqlite3', clock=lambda: self.when[0])
        self.store.prepare()

    def tearDown(self):
        self.temporary.cleanup()

    def test_queue_filters_and_evidence_are_not_ground_truth(self):
        result = self.store.list_cases('003', company='C001', rule='P1', limit=2)
        self.assertEqual(result['total'], 6)
        self.assertEqual(len(result['items']), 2)
        detail = self.store.detail('003', 'RC_1')
        self.assertEqual(detail['hits'][0]['related_transaction_ids'], ['T0'])
        self.assertEqual(self.store.transaction('003', 'T0')['amount_vnd'], 1_000_000)
        self.assertEqual(sum(r['debit_vnd'] for r in detail['documents'][0]['lines']), 1_000_000)
        self.assertNotIn('is_fraud', json.dumps(detail))
        self.assertNotIn('fraud_type', json.dumps(detail))
        with self.assertRaises(KeyError):
            self.store.detail('003', 'missing')

    def batch_fixture(self):
        with (self.report/'case_queue.csv').open(encoding='utf-8-sig', newline='') as stream:
            cases = list(csv.DictReader(stream))
        case = next(row for row in cases if row['case_id'] == 'RC_1')
        for row in cases:
            row['batch_event_ids'] = json.dumps(['BE_TEST']) if row is case else '[]'
        case['case_type'] = 'batch'
        event = dict(event_id='BE_TEST', company_id='C001', detected_at=case['opened_at'],
            phase='batch_closed', rule_id='P1', rule_name='Thanh toán vượt hóa đơn', points=20,
            hard_trigger=1, transaction_ids=['T1'], related_transaction_ids=['T0'], graph_path=[],
            evidence=dict(invoice_number='HD001', invoice_gross_vnd=1_000_000,
                          cumulative_paid_vnd=2_000_000, excess_vnd=1_000_000))
        write_csv(self.report/'case_queue.csv', cases)
        (self.report/'batch_events.jsonl').write_text(json.dumps(event)+'\n', encoding='utf-8')
        return event

    def test_batch_evidence_survives_artifact_loading_and_cache_refresh(self):
        event = self.batch_fixture()
        self.store.prepare()
        detail = self.store.detail('003', 'RC_1')
        self.assertEqual(detail['case']['case_type'], 'batch')
        self.assertEqual(detail['batch_events'], [event])
        self.assertEqual(self.store.transaction('003', 'T0')['transaction_id'], 'T0')
        event['evidence']['excess_vnd'] = 500_000
        (self.report/'batch_events.jsonl').write_text(json.dumps(event)+'\n', encoding='utf-8')
        self.store.prepare()
        self.assertEqual(self.store.detail('003', 'RC_1')['batch_events'][0]['evidence']['excess_vnd'], 500_000)

    def test_missing_batch_artifact_is_rejected(self):
        self.batch_fixture()
        (self.report/'batch_events.jsonl').unlink()
        with self.assertRaisesRegex(ValueError, 'Batch cases require'):
            self.store.prepare()

    def test_budget_is_per_company_idempotent_and_resets_on_local_day(self):
        for i in range(1, 6):
            self.store.admit('003', f'RC_{i}')
        self.assertEqual(self.store.admit('003', 'RC_1')['used'], 5)
        with self.assertRaises(OverflowError):
            self.store.admit('003', 'RC_6')
        self.assertEqual(self.store.admit('003', 'RC_7')['used'], 1)
        self.when[0] += timedelta(days=1)
        self.assertEqual(self.store.admit('003', 'RC_6')['used'], 1)
        self.store.set_budget(10)
        self.assertEqual(self.store.budget(), 10)
        with self.assertRaises(ValueError):
            self.store.set_budget(100)

    def test_concurrent_admission_cannot_exceed_budget(self):
        for i in range(1, 5):
            self.store.admit('003', f'RC_{i}')
        def attempt(identifier):
            try:
                self.store.admit('003', identifier)
                return True
            except OverflowError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt, ['RC_5', 'RC_6'])), 1)

    def test_feedback_survives_restart_and_stale_review_is_rejected(self):
        original = (self.report / 'case_queue.csv').read_bytes()
        event = self.store.save_feedback('003', 'RC_1', 'information_gap', 'Người thử', 'Thiếu biên bản', '')
        self.assertEqual(self.store.detail('003', 'RC_1')['case']['status'], 'awaiting_information')
        with self.assertRaises(RuntimeError):
            self.store.save_feedback('003', 'RC_1', 'false_positive', 'Người thử', 'Đã đối chiếu', '')
        self.when[0] += timedelta(minutes=1)
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'Người thử', 'Đã đối chiếu', event['event_hash'])
        restarted = ReviewStore(self.root / 'data', self.root / 'reports', self.root / 'cache.sqlite3', clock=lambda: self.when[0])
        restarted.prepare()
        self.assertEqual(restarted.detail('003', 'RC_1')['case']['status'], 'closed')
        self.assertEqual(len(restarted.detail('003', 'RC_1')['feedback_history']), 2)
        self.assertEqual((self.report / 'case_queue.csv').read_bytes(), original)

    def test_cli_and_web_share_serialised_audit_and_tamper_is_visible(self):
        def save(i):
            return record_feedback(self.report, f'RC_{i}', 'information_gap', 'QA', 'Cần hồ sơ', self.when[0].isoformat())
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(1, 5)))
        self.assertEqual(len(read_audit(self.report / 'feedback_audit.jsonl')), 4)
        self.assertEqual(self.store.list_cases('003')['counts']['awaiting_information'], 4)
        path = self.report / 'feedback_audit.jsonl'
        path.write_text(path.read_text(encoding='utf-8').replace('Cần hồ sơ', 'changed'), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.list_cases('003')

    def test_http_csrf_origin_host_and_file_routes(self):
        server = make_server(self.store, 0, qa=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=4)
            payload = json.dumps(body) if body is not None else None
            connection.request(method, path, body=payload, headers=headers or {})
            response = connection.getresponse()
            status, content = response.status, response.read()
            connection.close()
            return status, content
        try:
            status, body = request('GET', '/api/meta')
            self.assertEqual(status, 200)
            token = json.loads(body)['csrf_token']
            self.assertEqual(request('GET', '/api/meta', headers={'Host':'evil.example'})[0], 403)
            self.assertEqual(request('GET', '/data/labels.csv')[0], 404)
            self.assertEqual(request('POST', '/api/admit', {'scenario':'003','case_id':'RC_1'}, {'Content-Type':'application/json'})[0], 403)
            valid = {'Content-Type':'application/json','X-CSRF-Token':token}
            self.assertEqual(request('POST', '/api/admit', {'scenario':'003','case_id':'RC_1'}, valid | {'Origin':'https://evil.example'})[0], 403)
            self.assertEqual(request('POST', '/api/admit', {'scenario':'003','case_id':'RC_1'}, valid)[0], 200)
            self.assertEqual(request('POST', '/api/feedback', {'case_id':'RC_1','decision':'false_positive','reviewer':'QA','reason':'','expected_hash':''}, valid)[0], 400)
            status, exported = request('GET', '/api/export?scenario=003&company=C001')
            self.assertEqual(status, 200)
            self.assertTrue(exported.startswith(b'\xef\xbb\xbf'))
            self.assertIn(b'RC_1', exported)
            with self.store.connection() as db:
                saved = db.execute('SELECT data FROM entities WHERE entity_id=?', ('E01',)).fetchone()
                entity = json.loads(saved[0])
                entity['full_name'] = '\t=HYPERLINK("https://example.invalid")'
                db.execute('UPDATE entities SET data=? WHERE entity_id=?', (json.dumps(entity), 'E01'))
            _, guarded = request('GET', '/api/export?scenario=003&company=C001')
            row = next(csv.DictReader(io.StringIO(guarded.decode('utf-8-sig'))))
            self.assertTrue(row['owner_name'].startswith("'\t="))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
