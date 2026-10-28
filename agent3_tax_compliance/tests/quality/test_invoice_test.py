import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import invoice_test as runner
from invoice_test_review import write_review, embedded_preview, slim_record


class InvoiceTestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'agent3_tax_compliance/data')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.patch = patch.object(runner, 'WORK', self.work)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def source(self):
        import pymupdf as fitz
        source = self.work / 'source.pdf'
        with fitz.open() as document:
            for number in range(3):
                page = document.new_page(width=200, height=300)
                page.insert_text((20, 60), f'SYNTHETIC ONLY - PAGE {number + 1}')
                page.set_rotation(90 if number == 1 else 0)
            document.save(source)
        return source

    def test_split_keeps_all_pages_and_groups_continuation_without_altering_source(self):
        source = self.source(); before = source.read_bytes()
        target = self.work / 'prepared'
        result = runner.prepare(source, target, '1-2', '1-2')
        self.assertEqual(result['pages'], 3); self.assertEqual(result['invoice_cases'], 1)
        self.assertEqual(source.read_bytes(), before)
        manifest = runner.read(target / 'manifest.json')
        self.assertEqual(manifest['entries'][0]['source_pages'], [1, 2])
        self.assertEqual(manifest['entries'][0]['split'], 'dev')
        self.assertEqual(len(list((target / 'pages').glob('*.pdf'))), 3)
        self.assertTrue(all(p['render_within_tolerance'] and p['native_text_matches'] for p in runner.read(target / 'inventory.json')['pixel_checks']))
        with self.assertRaises(FileExistsError): runner.prepare(source, target, '1-2')

    def test_invalid_groups_fail_before_creating_outputs(self):
        source = self.source(); target = self.work / 'prepared'
        for groups in ('1-3', '1-2;2'):
            with self.assertRaises(ValueError): runner.prepare(source, target, '1-2', groups)
        self.assertFalse(target.exists())

    def test_page_selection_retains_whole_invoice_and_rejects_excluded_pages(self):
        manifest = {'entries': [{'case_id': 'a', 'source_pages': [2]}, {'case_id': 'b', 'source_pages': [12, 13]}]}
        self.assertEqual(runner.selected_entries(manifest, '12'), [manifest['entries'][1]])
        with self.assertRaises(ValueError): runner.selected_entries(manifest, '1')
        for bad in ('0', '../a', '3-1', '1-99'):
            with self.assertRaises(ValueError): runner.page_numbers(bad, 32)

    def test_html_roundtrips_invoice_text_without_script_injection(self):
        folder = self.work / 'run'; case = folder / 'invoice-p001'; case.mkdir(parents=True)
        text = '</script><img src=x onerror=alert(1)>&'
        runner.write(case / 'extraction.json', {'record': {'parties': {'seller': {'name': {'value': text, 'status': 'PRESENT'}}}}, 'issues': []})
        report = {'run_state': 'COMPLETED', 'cases': [{'case_id': 'invoice-p001', 'state': 'REVIEW'}]}
        manifest = {'entries': [{'case_id': 'invoice-p001', 'sha256': 'a' * 64, 'path': 'invoice_test/source.pdf', 'source_pages': [1]}]}
        output = self.work / 'review.html'
        write_review(output, folder, report, manifest, ROOT / 'invoice_test/prepared')
        html = output.read_text(encoding='utf-8')
        embedded = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)[1]
        self.assertNotIn('</script>', embedded)
        self.assertEqual(json.loads(embedded)['cases'][0]['record']['parties']['seller']['name']['value'], text)
        self.assertNotIn('innerHTML', html)

    def test_embedded_preview_recovers_missing_png_from_pdf(self):
        source = self.source()
        uri = embedded_preview(self.work / 'missing.png', source, 1)
        self.assertTrue(uri.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,')))
        self.assertIsNone(embedded_preview(self.work / 'missing.png', self.work / 'missing.pdf', 0))

    def test_review_payload_keeps_exact_values_without_full_provenance(self):
        field = {'value': '9007199254740993.01', 'status': 'PRESENT',
                 'provenance': {'large': 'x' * 10000}, 'candidates': ['not needed for editing']}
        record = {'totals': {'gross': field}, 'items': [{'line_number': 1, 'net': field}]}
        result = slim_record(record)
        self.assertEqual(result['totals']['gross'], {'value': field['value'], 'status': 'PRESENT'})
        self.assertEqual(result['items'][0]['net']['value'], field['value'])
        self.assertNotIn('provenance', json.dumps(result))


if __name__ == '__main__': unittest.main()
