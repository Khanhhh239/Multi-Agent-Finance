"""Use Agent 1's real profile guard and CSV parser with isolated, synthetic inputs.

Run from the repo root with agent1/.venv/Scripts/python.exe -m unittest
portal.test_bank_profile_contract -v. No live agent or company store is used.
"""
import json
import sys
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

from portal import bank_intake, server

ROOT = Path(__file__).resolve().parent.parent
with patch.object(sys, 'path', [str(ROOT / 'agent1'), *sys.path]):
    from agent1.adaptive.data import parse_rows
    from agent1_service.ingest.strict_files import read_csv
    from agent1_service.workspace.company_profile import company_profile, import_formats
from fastapi import HTTPException

SAMPLE = (ROOT / 'portal/static/samples/sao-ke-chung.csv').read_bytes()


class BankProfileContractTest(unittest.TestCase):
    def test_shared_preview_matches_managed_profile_for_all_formats(self):
        for date_format in ('dmy', 'iso'):
            for number_format in ('vi-VN', 'plain'):
                with self.subTest(date_format=date_format, number_format=number_format), tempfile.TemporaryDirectory() as tmp:
                    context = dict(code='MOCK', tax_code='0999999905', date_format=date_format, number_format=number_format)
                    profile_file = Path(tmp) / 'profile.json'
                    profile_file.write_text(json.dumps(context), encoding='utf-8')
                    record = dict(name='bank.csv', intake_context=context)
                    rows = server.shared_bank_rows(record, SAMPLE)
                    rows[0] = (*rows[0][:5], '2026-10-03', *rows[0][6:])
                    captured = []

                    def preview(method, url, body=None, headers=None, timeout=120):
                        self.assertEqual(method, 'POST')
                        self.assertTrue(url.endswith('/v1/imports/preview'))
                        message = BytesParser(policy=policy.default).parsebytes(
                            b'Content-Type: ' + headers['Content-Type'].encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
                        fields = {part.get_param('name', header='content-disposition'): part for part in message.iter_parts()}
                        text = lambda key: fields[key].get_payload(decode=True).decode('utf-8')
                        # This is the same guard and parser used by Agent 1's preview endpoint.
                        actual_profile = company_profile('MOCK')
                        formats = import_formats(actual_profile, text('date_format'), text('number_format'))
                        csv_data = fields['file'].get_payload(decode=True)
                        accepted, errors, warnings = parse_rows(read_csv(csv_data, fields['file'].get_filename()),
                                                               text('kind'), json.loads(text('mapping')), *formats)
                        self.assertEqual(errors, [])
                        captured.extend(accepted)
                        return 200, dict(can_commit=not errors, id='isolated-preview', valid_rows=len(accepted), errors=errors, error_count=len(errors))

                    with patch.dict('os.environ', AGENT1_COMPANY_PROFILE_FILE=str(profile_file)), \
                         patch.object(server, 'company', return_value=context), \
                         patch.object(server, 'health', return_value=True), \
                         patch.object(server, 'agent1_key', return_value='mock-key'), \
                         patch.object(server, 'call', side_effect=preview):
                        result = server.check('agent1', record, SAMPLE, bank_rows=rows)
                    self.assertEqual(result['state'], 'ready')
                    self.assertEqual(result['rows'], 2)
                    self.assertEqual([row['amount'] for row in captured], [12000000, 8500000])
                    self.assertEqual([row['date'] for row in captured], ['2026-10-01', '2026-10-02'])
                    self.assertEqual(captured[0]['known_at'], '2026-10-03')
                    self.assertEqual(captured[0]['account'], '000012345678')
                    self.assertEqual(captured[0]['bank_id'], 'MOCK-20261001-001')

    def test_managed_guard_still_rejects_old_iso_plain_override(self):
        with self.assertRaises(HTTPException) as error:
            import_formats(dict(managed=True, date_format='dmy', number_format='vi-VN'), '%Y-%m-%d', 'plain')
        self.assertEqual(error.exception.status_code, 409)

    def test_projection_preserves_large_vnd_and_tax_bytes(self):
        context = dict(number_format='plain')
        rows = server.shared_bank_rows(dict(name='bank.csv', intake_context=context), SAMPLE)
        rows[0] = (*rows[0][:4], '9007199254740991', *rows[0][5:])
        tax_bytes = bank_intake.project(rows, 'agent3')
        for number_format in ('plain', 'vi-VN'):
            with self.subTest(number_format=number_format):
                projected = bank_intake.project(rows, 'agent1', date_format='dmy', number_format=number_format)
                mapping = {key: key for key in ('bank_id', 'account', 'date', 'direction', 'amount', 'known_at', 'component')}
                accepted, errors, _ = parse_rows(read_csv(projected, 'bank.csv'), 'bank', mapping, '%d/%m/%Y', number_format)
                self.assertEqual(errors, [])
                self.assertEqual(accepted[0]['amount'], 9007199254740991)
                self.assertEqual(bank_intake.project(rows, 'agent3', date_format='dmy', number_format=number_format), tax_bytes)


if __name__ == '__main__':
    unittest.main()
