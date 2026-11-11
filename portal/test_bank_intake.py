"""Regression tests for the common inbox, isolated from live agent stores."""
import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from portal import bank_intake, server


SAMPLE = (Path(__file__).parent / 'static/samples/sao-ke-chung.csv').read_bytes()
CONTEXT = dict(code='MOCK', agent2_company='MOCK', tax_code='0999999905', date_format='iso', number_format='plain')


class SharedBankTest(unittest.TestCase):
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
                self.assertEqual(server.pending(), [])
                self.assertEqual(sum(p.is_file() for p in (work / 'bank_sources').rglob('*')), 1)
                with self.assertRaisesRegex(ValueError, 'đã được ghi'):
                    server.add_file('bank.csv', SAMPLE)


if __name__ == '__main__':
    unittest.main()
