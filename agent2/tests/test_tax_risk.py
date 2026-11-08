"""Real-source ingestion contracts exercised with explicitly synthetic documents."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.feature_contract import cache_contract, sha
from sme_fraud.features import FEATURE_DESCRIPTIONS
from sme_fraud.generate import write_csv
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import INPUT_TABLES, load_inputs, score_rules
from sme_fraud.tax_risk import FIELDS, TaxRiskHistory, import_list, tax_code


class TaxRiskTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = dict(noise_policy='phase2', spec_policy='phase3', evidence_policy='phase4')
        case.vendor['tax_code'] = '0100000001'
        case.tables['tax_risk_history'] = [self.record()]
        return case

    def record(self, **values):
        return dict(record_id='SIM_TAX_001', company_id='C001', tax_code='0100000001',
                    status='high_risk', risk_reason='Synthetic high-risk listing for contract tests',
                    effective_from='2025-01-01', effective_to='',
                    published_at='2025-01-02T09:00:00+07:00', observed_at='2025-01-02T10:00:00+07:00',
                    source_url='https://www.gdt.gov.vn/synthetic-contract-test', source_document_id='SIM_DOC',
                    source_sha256=hashlib.sha256(b'synthetic source document').hexdigest(), **values)

    def hit(self, result):
        return next((r for r in result['hits'] if r['rule_id'] == 'B4'), None)

    def test_exact_tax_code_list_match_opens_review_with_source_evidence(self):
        case = self.case()
        case.pay()
        hit = self.hit(case.score())
        self.assertEqual((hit['points'], hit['hard_trigger']), (10, 0))
        evidence = hit['evidence']
        self.assertEqual(evidence['evidence_status'], 'tax_authority_list_match')
        self.assertEqual(evidence['issuer_tax_code'], '0100000001')
        self.assertEqual(evidence['source_records'][0]['source_document_id'], 'SIM_DOC')
        self.assertEqual(case.score()['scores'][0]['operational_alert'], 1)

    def test_tax_code_formatting_preserves_zeros_and_exact_branch_identity(self):
        self.assertEqual(tax_code('010.000.0001-001'), '0100000001001')
        self.assertEqual(tax_code(100000001), '')
        case = self.case()
        case.vendor['tax_code'] = '0100000001-001'
        case.pay()
        self.assertIsNone(self.hit(case.score()))

    def test_explicit_invoice_issuer_takes_precedence_over_vendor_master(self):
        case = self.case()
        case.vendor['tax_code'] = '0200000002'
        case.pay(invoice_issuer_tax_code='0100000001')
        self.assertIsNotNone(self.hit(case.score()))
        case.rows[0]['invoice_issuer_tax_code'] = '0200000002'
        case.vendor['tax_code'] = '0100000001'
        self.assertIsNone(self.hit(case.score()))

    def test_publication_and_observation_after_cutoff_never_change_past_hits(self):
        case = self.case()
        row = case.pay()
        case.tables['tax_risk_history'] = []
        before = case.score()
        future = self.record()
        future.update(published_at='2025-08-13T09:00:00+07:00', observed_at='2025-08-13T10:00:00+07:00')
        case.tables['tax_risk_history'] = [future]
        after = case.score()
        self.assertEqual(before['scores'], after['scores'])
        self.assertEqual(before['hits'], after['hits'])
        future['published_at'] = '2025-01-02T09:00:00+07:00'
        self.assertIsNone(self.hit(case.score()))
        self.assertEqual(row['posted_at'], '2025-08-12T11:00:00+07:00')

    def test_effective_interval_applies_to_invoice_date_not_payment_date(self):
        for start, end, invoice, expected in (
                ('2025-08-10', '', '2025-08-09T11:00:00+07:00', False),
                ('2025-08-10', '', '2025-08-10T11:00:00+07:00', True),
                ('2025-01-01', '2025-08-10', '2025-08-10T11:00:00+07:00', False)):
            case = self.case()
            case.tables['tax_risk_history'][0].update(effective_from=start, effective_to=end)
            case.pay(invoice_issued_at=invoice)
            self.assertEqual(self.hit(case.score()) is not None, expected)

    def test_removal_is_revisioned_and_order_independent(self):
        case = self.case()
        case.pay()
        original = case.tables['tax_risk_history'][0]
        removed = dict(original, status='removed', observed_at='2025-08-11T10:00:00+07:00')
        for records in ([original, removed], [removed, original]):
            case.tables['tax_risk_history'] = records
            self.assertIsNone(self.hit(case.score()))
        removed['observed_at'] = '2025-08-13T10:00:00+07:00'
        self.assertIsNotNone(self.hit(case.score()))

    def test_other_company_missing_invoice_and_unknown_mst_do_not_match(self):
        for changes in ({'company_id': 'OTHER'}, {'tax_code': '0200000002'}):
            case = self.case()
            case.tables['tax_risk_history'][0].update(changes)
            case.pay()
            self.assertIsNone(self.hit(case.score()))
        case = self.case()
        case.pay()
        case.score()
        case.rows[0].update(invoice_id='', invoice_number='', invoice_issued_at='')
        self.assertIsNone(self.hit(score_rules(case.tables, config=case.config)))

    def test_legacy_registry_and_tax_listing_do_not_duplicate_b4_hits(self):
        case = self.case()
        case.g.status(case.vendor, 'inactive', case.at.replace(month=1), case.at.replace(month=1))
        case.pay()
        result = case.score()
        self.assertEqual(len([h for h in result['hits'] if h['rule_id'] == 'B4']), 1)
        self.assertEqual(self.hit(result)['points'], 10)

    def test_extra_labels_in_source_cannot_enter_detections_or_evidence(self):
        case = self.case()
        case.pay()
        expected = case.score()
        case.tables['tax_risk_history'][0].update(is_fraud='1', prediction='1', case_id='SECRET_LABEL')
        self.assertEqual(case.score(), expected)

    def test_invalid_and_ambiguous_source_rows_fail_closed(self):
        for changes in ({'tax_code': 'not-an-MST'}, {'tax_code': 1000000001},
                        {'source_url': 'https://gdt.gov.vn.attacker.example/list'},
                        {'source_url': 'http://www.gdt.gov.vn/list'},
                        {'source_sha256': 'unverified'}, {'source_document_id': ''},
                        {'effective_to': '2024-01-01'}, {'status': 'anything'},
                        {'published_at': '2025-02-01T00:00:00+07:00'}):
            record = self.record()
            record.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                TaxRiskHistory([record])
        original = self.record()
        for revision in (dict(original, tax_code='0200000002', observed_at='2025-02-01T00:00:00+07:00'),
                         dict(original, status='removed')):
            with self.assertRaises(ValueError):
                TaxRiskHistory([original, revision])

    def test_importer_binds_to_archived_document_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            document = root/'official-document-fixture.txt'
            document.write_text('Synthetic fixture, not an official tax list.', encoding='utf-8')
            source, output = root/'mapped.csv', root/'tax_risk_history.csv'
            fields = [f for f in FIELDS if not f.startswith('source_') and f != 'observed_at']
            with source.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({k: self.record()[k] for k in fields})
            args = dict(url='https://www.gdt.gov.vn/synthetic-contract-test', document_id='SIM_DOC',
                        observed_at='2025-01-02T10:00:00+07:00')
            summary = import_list(source, document, output, **args)
            self.assertEqual(summary['source_sha256'], sha(document))
            with output.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]['tax_code'], '0100000001')
            self.assertEqual(rows[0]['source_sha256'], sha(document))
            with self.assertRaises(FileExistsError):
                import_list(source, document, output, **args)

    def test_normal_loader_binds_tax_source_to_manifest_and_cache(self):
        case = self.case()
        case.pay()
        expected = case.score()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (*INPUT_TABLES, 'tax_risk_history'):
                rows = case.tables.get(name, [])
                write_csv(root/f'{name}.csv', rows, list(rows[0]) if rows else ['company_id'])
            write_csv(root/'features.csv', case.features)
            files = {p.name: dict(sha256=sha(p)) for p in root.glob('*.csv')}
            metadata = dict(files=files, feature_columns=list(FEATURE_DESCRIPTIONS), feature_contract=cache_contract(files))
            (root/'manifest.json').write_text(json.dumps(metadata), encoding='utf-8')
            tables, features, _ = load_inputs(root)
            result = score_rules(tables, features=features, config=case.config)
            self.assertEqual(self.hit(result), self.hit(expected))
            with (root/'tax_risk_history.csv').open('a', encoding='utf-8') as stream:
                stream.write('tamper')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_inputs(root)
