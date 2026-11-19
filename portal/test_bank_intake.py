"""Regression tests for the common inbox, isolated from live agent stores."""
import csv
import io
import tempfile
import concurrent.futures
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from portal import bank_intake, server


SAMPLE = (Path(__file__).parent / 'static/samples/sao-ke-chung.csv').read_bytes()
CONTEXT = dict(code='MOCK', agent2_company='MOCK', tax_code='0999999905', date_format='iso', number_format='plain')


class SharedBankTest(unittest.TestCase):
    def test_exact_reupload_of_committed_agent2_file_is_already_recorded(self):
        raw = b'transaction_id,posted_at,amount_vnd\nTX-1,2026-11-18,250000\n'
        digest = server.hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            inbox = work / 'pending'
            inbox.mkdir()
            batch_file = work / 'batches.json'
            server.write_json(batch_file, [dict(company=CONTEXT['code'], version=1, files=[dict(
                name='07_so_giao_dich_ngan_hang_A2.csv', kind='transactions', sha256=digest,
                results={'agent2': dict(state='done', snapshot_id='snp_existing')})])])
            with patch.multiple(server, WORK=work, PENDING=inbox, BATCH_FILE=batch_file), \
                 patch.object(server, 'company', return_value=CONTEXT), \
                 patch.object(server, 'classify', return_value=dict(kind='transactions', targets=['agent2'])), \
                 patch.object(server, 'check') as check:
                with self.assertRaisesRegex(server.AlreadyRecorded, 'đã được ghi đầy đủ'):
                    server.add_file('07_so_giao_dich_ngan_hang_A2.csv', raw)
                self.assertEqual(check.call_count, 0)
                self.assertEqual(server.pending(), [])

    def test_duplicate_agent2_source_in_one_upload_reuses_one_pending_item(self):
        raw = b'transaction_id,posted_at,amount_vnd\nTX-1,2026-11-18,250000\n'
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            inbox = work / 'pending'
            inbox.mkdir()
            with patch.multiple(server, WORK=work, PENDING=inbox, BATCH_FILE=work / 'batches.json'), \
                 patch.object(server, 'company', return_value=CONTEXT), \
                 patch.object(server, 'classify', return_value=dict(kind='transactions', targets=['agent2'])), \
                 patch.object(server, 'check', return_value=dict(state='ready', message='Tệp hợp lệ')) as check:
                first = server.add_file('07_so_giao_dich_ngan_hang_A2.csv', raw)
                second = server.add_file('07_so_giao_dich_ngan_hang_A2.csv', raw)
                self.assertEqual(first['id'], second['id'])
                self.assertEqual(check.call_count, 1)
                self.assertEqual(len(server.pending()), 1)

    def test_partial_prior_write_resumes_only_missing_agent(self):
        raw = b'transaction-source'
        digest = server.hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            inbox = work / 'pending'
            inbox.mkdir()
            batch_file = work / 'batches.json'
            server.write_json(batch_file, [dict(company=CONTEXT['code'], version=1, files=[dict(
                name='transactions.csv', kind='transactions', sha256=digest,
                intake_context=CONTEXT, results={'agent1': dict(state='done', message='Đã ghi')})])])
            with patch.multiple(server, WORK=work, PENDING=inbox, BATCH_FILE=batch_file), \
                 patch.object(server, 'company', return_value=CONTEXT), \
                 patch.object(server, 'classify', return_value=dict(kind='transactions', targets=['agent1', 'agent3'])), \
                 patch.object(server, 'check', side_effect=lambda aid, *_args, **_kwargs: dict(state='ready', message='Cần xử lý')) as check:
                record = server.add_file('02_sao_ke_chung_A1_A3.csv', raw)
                self.assertEqual(record['checks']['agent1']['state'], 'done')
                self.assertEqual(record['checks']['agent3']['state'], 'ready')
                self.assertEqual([call.args[0] for call in check.call_args_list], ['agent3'])

    def test_long_payment_check_is_visible_and_same_upload_does_not_start_again(self):
        raw = (b'payment_id,invoice_id,payment_date,known_at,amount,bank_id\n'
               b'P1,I1,2026-11-18,2026-11-18,10000000,B1\n')
        started, release = threading.Event(), threading.Event()

        def slow_preview(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(3))
            return 200, {'can_commit': True, 'id': 'checked', 'valid_rows': 1}

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.multiple(server, WORK=work, PENDING=work), \
                 patch.object(server, 'company', return_value=CONTEXT), patch.object(server, 'health', return_value=True), \
                 patch.object(server, 'agent1_key', return_value='mock-key'), patch.object(server, 'call', side_effect=slow_preview) as call, \
                 concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = []
                handler = SimpleNamespace(path='/api/inbox',
                    route=lambda method: results.append(server.add_file('03_payments.csv', raw)),
                    send=lambda status, body: self.fail(f'Unexpected HTTP error {status}: {body}'))
                future = pool.submit(server.Handler.handle_one, handler, 'POST')
                try:
                    self.assertTrue(started.wait(2))
                    pending = server.pending()[0]
                    self.assertEqual(pending['checks']['agent1']['state'], 'checking')
                    self.assertGreater(pending['check_started_at'], 0)
                    duplicate = server.add_file('renamed-payments.csv', raw)
                    self.assertEqual(duplicate['id'], pending['id'])
                    self.assertEqual(server.recheck(pending['id'])['checks']['agent1']['state'], 'checking')
                    with self.assertRaisesRegex(ValueError, 'đang được kiểm tra'):
                        server.remove_file(pending['id'])
                    self.assertEqual(call.call_count, 1)
                finally:
                    release.set()
                future.result(timeout=3)
                self.assertEqual(results[0]['checks']['agent1']['state'], 'ready')
                self.assertEqual(len(server.pending()), 1)

    def test_poll_cannot_overwrite_check_that_completed_while_waiting_for_lock(self):
        started, read = threading.Event(), threading.Event()
        original_read = server.read_json

        def observe_read(*args):
            result = original_read(*args)
            read.set()
            return result

        def poll():
            started.set()
            return server.pending()

        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'company', return_value=CONTEXT), \
             patch.object(server, 'PENDING', Path(tmp)), patch.object(server, 'read_json', side_effect=observe_read), \
             concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            record = dict(id='finishing', name='04_statements.csv', added_at='2026-11-18 10:44:59',
                          targets=['agent1'], intake_context=CONTEXT,
                          checks={'agent1': dict(state='checking')})
            meta = Path(tmp) / 'finishing.json'
            server.write_json(meta, record)
            with server.LOCK:
                server.CHECKING.add(record['id'])
                future = pool.submit(poll)
                self.assertTrue(started.wait(2))
                read.wait(.1)
                record['checks'] = {'agent1': dict(state='ready', rows=142, preview='valid-preview')}
                server.write_json(meta, record)
                server.CHECKING.discard(record['id'])
            self.assertEqual(future.result(timeout=2)[0]['checks']['agent1']['state'], 'ready')
            self.assertEqual(original_read(meta, {})['checks']['agent1']['preview'], 'valid-preview')

    def test_company_change_and_commit_wait_for_active_check(self):
        for path in ('/api/company', '/api/inbox/commit'):
            responses = []
            handler = SimpleNamespace(path=path,
                route=lambda method: self.fail('Must not mutate profile/data during a check'),
                send=lambda status, body: responses.append((status, body)))
            with patch.object(server, 'CHECKING', {'active-check'}):
                server.Handler.handle_one(handler, 'PUT' if path == '/api/company' else 'POST')
            self.assertEqual(responses[0][0], 400)
            self.assertIn('Đang kiểm tra', responses[0][1]['error'])

    def test_commit_allows_agent_session_callback_without_second_writer(self):
        forbidden = []

        def write(method):
            self.assertTrue(server.COMMITTING)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                # Agent 2 calls back from a different request thread.
                self.assertEqual(pool.submit(server.session_left, 'unknown-session', False).result(timeout=2), 0)
            second_writer = SimpleNamespace(path='/api/inbox/commit',
                route=lambda method: self.fail('Must not start a second writer'),
                send=lambda status, body: forbidden.append(status))
            server.Handler.handle_one(second_writer, 'POST')

        handler = SimpleNamespace(path='/api/inbox/commit', route=write,
            send=lambda status, body: self.fail(f'Unexpected status: {status}'))
        server.Handler.handle_one(handler, 'POST')
        self.assertEqual(forbidden, [400])
        self.assertFalse(server.COMMITTING)

    def test_interrupted_check_becomes_retryable_instead_of_spinning_forever(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'company', return_value=CONTEXT), patch.object(server, 'PENDING', Path(tmp)):
            record = dict(id='interrupted', name='03_payments.csv', added_at='2026-11-18 10:00:00',
                          targets=['agent1'], intake_context=CONTEXT,
                          checks={'agent1': dict(state='checking', message='waiting')})
            server.write_json(Path(tmp) / 'interrupted.json', record)
            result = server.pending()[0]
            self.assertEqual(result['checks']['agent1']['state'], 'error')
            self.assertIn('gián đoạn', result['checks']['agent1']['message'])

    def test_expense_payment_is_agent1_input(self):
        raw = (b'settlement_id,expense_id,bank_id,payment_date,amount,known_at\n'
               b'S1,E1,B1,2026-11-18,40000000,2026-11-18\n')
        record = server.classify('02_expense_payments.csv', raw)
        self.assertEqual(record['kind'], 'a1:expense_payments')
        self.assertEqual(record['targets'], ['agent1'])

    def test_agent1_bank_remains_shared_and_preserves_memo_and_counterparty(self):
        raw = (b'bank_id,account,date,direction,amount,known_at,component,memo,counterparty,customer_id,cash_flow_class\n'
               b'B1,00123,2026-10-02,in,9000000,2026-10-02,other,Invoice-HD1,Buyer,C1,other_external\n')
        record = dict(server.classify('02_bank.csv', raw), name='02_bank.csv', intake_context=CONTEXT)
        self.assertEqual(record['kind'], 'shared_bank')
        self.assertEqual(record['targets'], ['agent1', 'agent3'])
        rows = server.shared_bank_rows(record, raw)
        tax = list(csv.DictReader(io.StringIO(bank_intake.project(rows, 'agent3').decode())))
        self.assertEqual(tax[0]['Nội dung'], 'Invoice-HD1')
        self.assertEqual(tax[0]['Tên đơn vị đối ứng'], 'Buyer')
        self.assertEqual(tax[0]['Ghi Có'], '9000000')

        def fake_call(method, url, body=None, headers=None, timeout=120):
            self.assertEqual(timeout, 600)
            self.assertTrue(url.endswith('/v1/imports/preview'))
            self.assertIn(raw, body)
            return 200, {'can_commit': True, 'id': 'preview-native', 'valid_rows': 1}

        with patch.object(server, 'company', return_value=CONTEXT), \
             patch.object(server, 'health', return_value=True), \
             patch.object(server, 'agent1_key', return_value='mock-key'), \
             patch.object(server, 'ensure_agent3_workspace', return_value={'state': 'ok', 'id': CONTEXT['tax_code'], 'profile_revision': 'mock'}), \
             patch.object(server, 'call', side_effect=fake_call):
            checks = server.preview_file(record, raw)
        self.assertEqual(list(checks), ['agent1', 'agent3'])
        self.assertEqual(checks['agent1']['state'], 'ready')
        self.assertEqual(checks['agent3']['state'], 'ready')

    def test_recheck_restores_both_bank_targets_without_reupload(self):
        raw = (b'bank_id,account,date,direction,amount,known_at,component,memo\n'
               b'B1,00123,2026-10-02,in,9000000,2026-10-02,other,HD1\n')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fid = '123456abcdef'
            record = dict(id=fid, name='02_bank.csv', kind='a1:bank', label='old routing',
                          targets=['agent1'], intake_context=CONTEXT,
                          checks={'agent1': {'state': 'ready'}})
            (work / f'{fid}.bin').write_bytes(raw)
            with patch.object(server, 'PENDING', work), patch.object(server, 'company', return_value=CONTEXT), \
                 patch.object(server, 'health', return_value=True), patch.object(server, 'agent1_key', return_value='mock-key'), \
                 patch.object(server, 'ensure_agent3_workspace', return_value={'state': 'ok', 'id': CONTEXT['tax_code'], 'profile_revision': 'mock'}), \
                 patch.object(server, 'call', return_value=(200, {'can_commit': True, 'id': 'rechecked', 'valid_rows': 1})) as call:
                server.write_json(work / f'{fid}.json', record)
                result = server.recheck(fid)
                self.assertEqual(result['targets'], ['agent1', 'agent3'])
                self.assertEqual(result['checks']['agent1']['state'], 'ready')
                self.assertEqual(result['checks']['agent3']['state'], 'ready')
                self.assertEqual((work / f'{fid}.bin').read_bytes(), raw)
                self.assertEqual(call.call_count, 1)
                self.assertTrue(call.call_args.args[1].endswith('/v1/imports/preview'))

    def test_timeout_does_not_claim_agent_is_offline(self):
        with patch.object(server, 'urlopen', side_effect=TimeoutError):
            status, result = server.call('POST', 'http://127.0.0.1/preview', timeout=600)
        self.assertEqual(status, 0)
        self.assertIn('600', result['error'])
        self.assertIn('vẫn đang xử lý', result['error'])
        self.assertNotIn('Bật agent', result['error'])

    def test_shared_bank_cannot_commit_while_agent3_is_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.multiple(server, WORK=work, PENDING=work, BATCH_FILE=work / 'batches.json'), \
                 patch.object(server, 'company', return_value=CONTEXT), \
                 patch.object(server, 'health', side_effect=lambda aid: aid == 'agent1'), \
                 patch.object(server, 'agent1_key', return_value='mock-key'), \
                 patch.object(server, 'call', return_value=(200, {'can_commit': True, 'id': 'preview', 'valid_rows': 2})) as call:
                record = server.add_file('bank.csv', SAMPLE)
                self.assertEqual(record['checks']['agent3']['state'], 'offline')
                with self.assertRaisesRegex(ValueError, 'Không tệp nào được ghi'):
                    server.commit([record['id']])
                self.assertEqual(call.call_count, 1)
                self.assertTrue(call.call_args.args[1].endswith('/preview'))
                self.assertTrue((work / (record['id'] + '.bin')).is_file())

    def test_sample_has_two_targets_and_one_value_per_transaction(self):
        record = dict(server.classify('bank.csv', SAMPLE), name='bank.csv', intake_context=CONTEXT)
        self.assertEqual(record['targets'], ['agent1', 'agent3'])
        rows = server.shared_bank_rows(record, SAMPLE)
        cash = list(csv.DictReader(io.StringIO(bank_intake.project(rows, 'agent1').decode())))
        tax = list(csv.DictReader(io.StringIO(bank_intake.project(rows, 'agent3').decode())))
        self.assertEqual([r['amount'] for r in cash], ['12000000', '8500000'])
        self.assertEqual([r['Ghi Có'] for r in tax], ['12000000', ''])
        self.assertEqual([r['Ghi Nợ'] for r in tax], ['', '8500000'])
        self.assertEqual(cash[0]['account'], '000012345678')
        self.assertEqual(cash[0]['memo'], 'Thu hóa đơn MOCK-001')
        self.assertEqual(cash[0]['counterparty'], 'Khách hàng mô phỏng')
        self.assertEqual(tax[0]['portal_bank_id'], cash[0]['bank_id'])
        self.assertEqual(tax[1]['Số tài khoản đối ứng'], '000033334444')

    def test_explicit_customer_and_non_ar_class_survive_projection(self):
        raw = (b'bank_id,account,date,direction,amount,description,counterparty_name,customer_id,cash_flow_class\n'
               b'LOAN-1,00123,2026-10-02,in,9000000,Loan drawdown,Lender,C_LOAN,financing\n')
        record = dict(server.classify('bank.csv', raw), name='bank.csv', intake_context=CONTEXT)
        rows = server.shared_bank_rows(record, raw)
        cash = list(csv.DictReader(io.StringIO(bank_intake.project(rows, 'agent1').decode())))
        self.assertEqual(cash[0]['memo'], 'Loan drawdown')
        self.assertEqual(cash[0]['counterparty'], 'Lender')
        self.assertEqual(cash[0]['customer_id'], 'C_LOAN')
        self.assertEqual(cash[0]['cash_flow_class'], 'financing')

    def test_vietnamese_split_amount_and_validation(self):
        raw = ('Mã giao dịch;Tài khoản;Ngày giao dịch;Ghi Nợ;Ghi Có\n'
               'T01;00123;02/10/2026;1.250.000;\n').encode()
        record = dict(server.classify('bank.csv', raw), name='bank.csv',
                      intake_context=dict(CONTEXT, number_format='vi-VN'))
        self.assertEqual(server.shared_bank_rows(record, raw)[0][:5], ('T01', '00123', '2026-10-02', 'out', '1250000'))
        with self.assertRaisesRegex(ValueError, 'Ghi Nợ/Ghi Có'):
            server.shared_bank_rows(record, raw.rstrip() + b'1000\n')
        with self.assertRaisesRegex(ValueError, 'trùng'):
            server.shared_bank_rows(record, raw + b'T01;00123;02/10/2026;2.250.000;\n')

    def test_excel_preserves_text_account_and_sparse_columns(self):
        def inline(ref, value):
            return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
        columns = ('bank_id', 'account', 'date', 'debit', 'credit')
        header = ''.join(inline(f'{letter}1', name) for letter, name in zip('ABCDE', columns))
        row = inline('A2', 'T02') + inline('B2', '00123') + inline('C2', '2026-10-02') + '<c r="E2"><v>8500</v></c>'
        sheet = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row>{header}</row><row>{row}</row></sheetData></worksheet>'
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            archive.writestr('xl/worksheets/sheet1.xml', sheet)
        raw = out.getvalue()
        record = dict(server.classify('bank.xlsx', raw), name='bank.xlsx', intake_context=CONTEXT)
        self.assertEqual(record['kind'], 'shared_bank')
        self.assertEqual(server.shared_bank_rows(record, raw)[0][:5], ('T02', '00123', '2026-10-02', 'in', '8500'))

    def test_retry_does_not_write_to_a1_twice(self):
        calls = []

        def fake_call(method, url, body=None, headers=None, timeout=120):
            calls.append((method, url))
            if method == 'POST' and url.endswith('/preview'):
                self.assertIn(b'MOCK-20261001-001,000012345678', body)
                return 200, {'can_commit': True, 'id': 'mock-preview', 'valid_rows': 2}
            if method == 'POST' and url.endswith('/commit'):
                return 200, {'accepted': 2}
            if method == 'PUT' and '/inbox?' in url:
                self.assertIn(b'portal_bank_id,portal_bank_account', body)
                self.assertEqual(headers['X-Agent3-Profile-Revision'], 'mock-profile-revision')
                if sum(m == 'PUT' for m, _ in calls) == 1:
                    return 503, {'error': 'Mock offline during write'}
                return 200, {'files': [{'label': 'Sao kê ngân hàng'}]}
            self.fail(f'Unexpected call {method} {url}')

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            pending_dir = work / 'pending'
            pending_dir.mkdir()
            with patch.multiple(server, WORK=work, PENDING=pending_dir, BATCH_FILE=work / 'batches.json',
                                AUDIT_FILE=work / 'audit.jsonl'), patch.object(server, 'company', return_value=CONTEXT), \
                 patch.object(server, 'health', return_value=True), patch.object(server, 'agent1_key', return_value='mock-key'), \
                 patch.object(server, 'ensure_agent3_workspace', return_value={'state': 'ok', 'id': CONTEXT['tax_code'], 'profile_revision': 'mock-profile-revision'}), \
                 patch.object(server, 'call', side_effect=fake_call):
                record = server.add_file('bank.csv', SAMPLE)
                self.assertEqual(server.add_file('renamed.csv', SAMPLE)['id'], record['id'])
                first = server.commit([record['id']])
                self.assertEqual(first['files'][0]['results']['agent3']['state'], 'error')
                self.assertEqual(server.pending()[0]['applied']['agent1']['state'], 'done')
                retry = server.commit([record['id']], 'Thử lại Agent 3')
                self.assertEqual(retry['files'][0]['results']['agent3']['state'], 'done')
                self.assertEqual(sum(url.endswith('/commit') for _, url in calls), 1)
                self.assertEqual(sum(url.endswith('/preview') for _, url in calls), 1)
                self.assertEqual(server.pending(), [])
                self.assertEqual(sum(p.is_file() for p in (work / 'bank_sources').rglob('*')), 1)
                with self.assertRaisesRegex(ValueError, 'đã được ghi'):
                    server.add_file('bank.csv', SAMPLE)

    def test_cached_bank_preview_refreshes_when_stale_or_inputs_no_longer_match(self):
        for mode in ('stale', 'projection_changed', 'legacy_preview'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                inbox = work / 'pending'
                inbox.mkdir()
                calls = []

                def fake_call(method, url, body=None, headers=None, timeout=120):
                    calls.append((method, url))
                    if url.endswith('/preview'):
                        n = sum(u.endswith('/preview') for _, u in calls)
                        return 200, {'can_commit': True, 'id': 'cached' if n == 1 else 'fresh', 'valid_rows': 2}
                    if url.endswith('/cached/commit'):
                        self.assertEqual(mode, 'stale')
                        return 409, {'error': 'Dataset changed'}
                    if url.endswith('/fresh/commit'):
                        return 200, {'accepted': 2}
                    if method == 'PUT' and '/inbox?' in url:
                        return 200, {'files': [{'label': 'Sao kê ngân hàng'}]}
                    self.fail(f'Unexpected request: {method} {url}')

                with patch.multiple(server, WORK=work, PENDING=inbox, BATCH_FILE=work / 'batches.json'), \
                     patch.object(server, 'company', return_value=CONTEXT), patch.object(server, 'health', return_value=True), \
                     patch.object(server, 'agent1_key', return_value='mock-key'), \
                     patch.object(server, 'ensure_agent3_workspace', return_value={'state': 'ok', 'id': CONTEXT['tax_code'], 'profile_revision': 'mock'}), \
                     patch.object(server, 'call', side_effect=fake_call):
                    record = server.add_file('bank.csv', SAMPLE)
                    if mode == 'projection_changed':
                        record['checks']['agent1']['source_sha256'] = 'old-projection'
                    elif mode == 'legacy_preview':
                        record['checks']['agent1'].pop('import_kind')
                    server.write_json(inbox / (record['id'] + '.json'), record)
                    result = server.commit([record['id']])
                    states = result['files'][0]['results']
                    self.assertEqual([states[a]['state'] for a in ('agent1', 'agent3')], ['done', 'done'])
                    self.assertEqual(sum(u.endswith('/preview') for _, u in calls), 2)
                    self.assertEqual(sum(u.endswith('/fresh/commit') for _, u in calls), 1)

    def test_changed_source_bytes_are_rejected_before_any_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.multiple(server, WORK=work, PENDING=work, BATCH_FILE=work / 'batches.json'), \
                 patch.object(server, 'company', return_value=CONTEXT), patch.object(server, 'health', return_value=True), \
                 patch.object(server, 'agent1_key', return_value='mock-key'), \
                 patch.object(server, 'ensure_agent3_workspace', return_value={'state': 'ok', 'id': CONTEXT['tax_code'], 'profile_revision': 'mock'}), \
                 patch.object(server, 'call', return_value=(200, {'can_commit': True, 'id': 'cached', 'valid_rows': 2})) as call:
                record = server.add_file('bank.csv', SAMPLE)
                (work / (record['id'] + '.bin')).write_bytes(SAMPLE + b'\n')
                with self.assertRaisesRegex(ValueError, 'Nội dung tệp nguồn đã thay đổi'):
                    server.commit([record['id']])
                self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
