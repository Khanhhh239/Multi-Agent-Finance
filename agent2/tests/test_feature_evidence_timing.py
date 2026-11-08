"""M01: evidence unavailable at posting cannot enter monetary/document features."""
import copy
import math
from datetime import timedelta
from types import SimpleNamespace
import unittest

from sme_fraud.features import FEATURE_DESCRIPTIONS, build_features
from sme_fraud.feature_contract import cache_contract, model_compatibility, require_model
from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


FLAGS = ('support_docs_known', 'invoice_known', 'invoice_components_known', 'linked_input_vat_known')
INVOICE_VALUES = ('invoice_log_gross', 'invoice_payment_ratio', 'cumulative_invoice_payment_ratio',
                  'invoice_vat_fraction', 'linked_input_vat_fraction', 'vat_invoice_arithmetic_gap')


class FeatureEvidenceTimingTest(unittest.TestCase):
    def case(self, **values):
        case = Case()
        # Keep ledger fixtures valid; zero invoice knowledge is projected after
        # the ordinary positive payment/accrual documents have been created.
        initial = dict(values)
        if initial.get('invoice_gross_vnd') == 0:
            initial['invoice_gross_vnd'] = 12_000_000
        row = case.pay(**initial)
        case.score()  # Ordinary accounting enrichment once; never read fixture truth.
        if values.get('invoice_gross_vnd') == 0:
            row.update(invoice_gross_vnd=0, invoice_net_vnd=0, invoice_vat_vnd=0, linked_input_vat_vnd=0)
        return case, row

    def feature(self, case):
        return build_features(case.tables)[0]

    def document(self, case, row, *, identity='DOC', kind='goods_receipt', days=-1, **values):
        at = stamp(case.at + timedelta(days=days))
        record = dict(record_id=identity, company_id=row['company_id'], vendor_id=row['vendor_id'],
                      transaction_id=row['transaction_id'], document_type=kind, status='verified',
                      evidence_id='SIM_' + identity, verifier_id=case.director['employee_id'],
                      verified_at=at, observed_at=at)
        record.update(values)
        return record

    def invoice(self, case, row, **values):
        return self.document(case, row, kind='invoice', invoice_number=row['invoice_number'],
            invoice_issued_at=stamp(case.at - timedelta(days=2)), invoice_gross_vnd=12_000_000,
            invoice_net_vnd=10_000_000, invoice_vat_vnd=2_000_000, linked_input_vat_vnd=2_000_000, **values)

    def test_future_document_values_cannot_change_historical_feature_vector(self):
        case, row = self.case(support_doc_count=0, goods_receipt_verified=0)
        row['support_docs_observed_at'] = stamp(case.at + timedelta(days=2))
        before = self.feature(case)
        row.update(support_doc_count=2, goods_receipt_verified=1)
        self.assertEqual(self.feature(case), before)
        self.assertEqual((before['support_doc_count'], before['goods_receipt_verified']), (0, 0))

    def test_document_cutoff_is_inclusive_and_one_second_late_is_excluded(self):
        for seconds, known in ((-1, 1), (0, 1), (1, 0)):
            with self.subTest(seconds=seconds):
                case, row = self.case(support_doc_count=2, goods_receipt_verified=1)
                row['support_docs_observed_at'] = stamp(case.at + timedelta(seconds=seconds))
                f = self.feature(case)
                self.assertEqual((f['support_doc_count'], f['goods_receipt_verified'], f['support_docs_known']),
                                 (2 * known, known, known))

    def test_untimed_document_values_are_missing_and_distinct_from_observed_zero(self):
        case, row = self.case(support_doc_count=2, goods_receipt_verified=1)
        missing = self.feature(case)
        self.assertEqual((missing['support_doc_count'], missing['goods_receipt_verified'], missing['support_docs_known']), (0, 0, 0))
        row.update(support_doc_count=0, goods_receipt_verified=0, support_docs_observed_at=row['posted_at'])
        known = self.feature(case)
        self.assertEqual((known['support_doc_count'], known['goods_receipt_verified'], known['support_docs_known']), (0, 0, 1))

    def test_future_invoice_masks_all_dependent_monetary_features(self):
        case, row = self.case(invoice_issued_at='2025-08-14T11:00:00+07:00', invoice_gross_vnd=0)
        row['invoice_observed_at'] = '2025-08-14T11:00:00+07:00'
        before = self.feature(case)
        row.update(invoice_gross_vnd=12_000_000, invoice_net_vnd=10_000_000,
                   invoice_vat_vnd=2_000_000, linked_input_vat_vnd=2_000_000)
        after = self.feature(case)
        self.assertEqual(after, before)
        self.assertEqual({name: after[name] for name in INVOICE_VALUES}, {name: 0 for name in INVOICE_VALUES})
        self.assertEqual(after['invoice_known'], 0)

    def test_future_issue_date_is_excluded_even_if_observation_claims_known(self):
        case, row = self.case(invoice_gross_vnd=12_000_000)
        row.update(invoice_observed_at=row['posted_at'], invoice_issued_at=stamp(case.at + timedelta(seconds=1)))
        f = self.feature(case)
        self.assertEqual((f['invoice_log_gross'], f['invoice_known'], f['registry_risky_at_invoice']), (0, 0, 0))

    def test_old_issue_date_does_not_make_late_observation_available(self):
        case, row = self.case(invoice_gross_vnd=12_000_000)
        row.update(invoice_issued_at=stamp(case.at - timedelta(days=30)),
                   invoice_observed_at=stamp(case.at + timedelta(days=2)))
        f = self.feature(case)
        self.assertEqual((f['invoice_log_gross'], f['invoice_known']), (0, 0))

    def test_invoice_at_cutoff_is_available_and_observed_zero_is_not_missing(self):
        for gross in (0, 12_000_000):
            with self.subTest(gross=gross):
                case, row = self.case(invoice_gross_vnd=gross)
                row.update(invoice_issued_at=row['posted_at'], invoice_observed_at=row['posted_at'])
                f = self.feature(case)
                self.assertEqual(f['invoice_log_gross'], round(math.log1p(gross), 8))
                self.assertEqual(f['invoice_known'], 1)

    def test_untimed_invoice_amount_is_missing(self):
        case, row = self.case(invoice_gross_vnd=12_000_000)
        f = self.feature(case)
        self.assertEqual((f['invoice_log_gross'], f['invoice_known']), (0, 0))

    def test_known_invoice_revision_wins_over_later_raw_and_document_values(self):
        case, row = self.case(invoice_gross_vnd=24_000_000)
        prior = self.invoice(case, row)
        case.tables['transaction_documents'] = [prior]
        before = self.feature(case)
        future = dict(prior, observed_at=stamp(case.at + timedelta(days=2)),
                      verified_at=stamp(case.at + timedelta(days=2)),
                      invoice_gross_vnd=30_000_000, invoice_net_vnd=25_000_000, invoice_vat_vnd=5_000_000)
        case.tables['transaction_documents'].append(future)
        row.update(invoice_gross_vnd=30_000_000, invoice_net_vnd=25_000_000, invoice_vat_vnd=5_000_000)
        self.assertEqual(self.feature(case), before)
        self.assertEqual(before['invoice_log_gross'], round(math.log1p(12_000_000), 8))
        self.assertEqual((before['invoice_known'], before['invoice_components_known']), (1, 1))

    def test_document_revisions_are_selected_before_status_and_order_does_not_matter(self):
        case, row = self.case(support_doc_count=9, goods_receipt_verified=1)
        original = self.document(case, row)
        future = dict(original, status='revoked', observed_at=stamp(case.at + timedelta(days=2)))
        case.tables['transaction_documents'] = [future, original]
        before = self.feature(case)
        case.tables['transaction_documents'].reverse()
        self.assertEqual(self.feature(case), before)
        self.assertEqual((before['support_doc_count'], before['goods_receipt_verified'], before['support_docs_known']), (1, 1, 1))

    def test_known_revocation_cannot_fall_back_to_positive_final_scalar(self):
        case, row = self.case(support_doc_count=9, goods_receipt_verified=1, invoice_gross_vnd=24_000_000)
        row.update(support_docs_observed_at=row['posted_at'], invoice_observed_at=row['posted_at'])
        receipt = self.document(case, row)
        invoice = self.invoice(case, row, identity='INV')
        revisions = [dict(record, status='revoked', observed_at=row['posted_at']) for record in (receipt, invoice)]
        case.tables['transaction_documents'] = [receipt, invoice, *revisions]
        f = self.feature(case)
        self.assertEqual((f['support_doc_count'], f['goods_receipt_verified'], f['invoice_known']), (0, 0, 0))

    def test_wrong_company_or_vendor_document_cannot_supply_feature_values(self):
        for changes in ({'company_id': 'C002'}, {'vendor_id': 'WRONG_VENDOR'}):
            with self.subTest(changes=changes):
                case, row = self.case(support_doc_count=9, goods_receipt_verified=1)
                record = self.document(case, row, **changes)
                case.tables['transaction_documents'] = [record]
                f = self.feature(case)
                self.assertEqual((f['support_doc_count'], f['goods_receipt_verified'], f['support_docs_known']), (0, 0, 0))

    def test_late_verification_does_not_set_receipt_flag(self):
        case, row = self.case(goods_receipt_verified=1)
        pending = self.document(case, row, status='pending', verified_at='')
        verified = dict(pending, status='verified', verified_at=stamp(case.at + timedelta(days=2)),
                        observed_at=stamp(case.at + timedelta(days=2)))
        case.tables['transaction_documents'] = [pending, verified]
        f = self.feature(case)
        self.assertEqual((f['support_doc_count'], f['goods_receipt_verified']), (1, 0))

    def test_missing_invoice_components_do_not_create_arithmetic_anomaly(self):
        case, row = self.case(invoice_gross_vnd=99_000_000)
        record = self.invoice(case, row)
        for key in ('invoice_net_vnd', 'invoice_vat_vnd', 'linked_input_vat_vnd'):
            record.pop(key)
        case.tables['transaction_documents'] = [record]
        f = self.feature(case)
        self.assertEqual((f['invoice_known'], f['invoice_components_known'], f['linked_input_vat_known']), (1, 0, 0))
        self.assertEqual((f['invoice_vat_fraction'], f['vat_invoice_arithmetic_gap'], f['linked_input_vat_fraction']), (0, 0, 0))

    def test_invoice_id_can_bind_amounts_without_a_document_number(self):
        case, row = self.case(invoice_gross_vnd=99_000_000)
        record = self.invoice(case, row)
        record.pop('invoice_number')
        record['invoice_id'] = row['invoice_id']
        case.tables['transaction_documents'] = [record]
        f = self.feature(case)
        self.assertEqual((f['invoice_known'], f['invoice_log_gross']), (1, round(math.log1p(12_000_000), 8)))

    def test_conflicting_invoice_identifier_cannot_supply_values(self):
        case, row = self.case(invoice_gross_vnd=99_000_000)
        record = self.invoice(case, row, invoice_id='OTHER_INVOICE')
        case.tables['transaction_documents'] = [record]
        f = self.feature(case)
        self.assertEqual((f['invoice_known'], f['invoice_log_gross']), (0, 0))

    def test_invoice_id_binding_is_exact_even_when_punctuation_differs(self):
        case, row = self.case(invoice_id='INV-1')
        record = self.invoice(case, row, invoice_id='INV1')
        record.pop('invoice_number')
        case.tables['transaction_documents'] = [record]
        self.assertEqual(self.feature(case)['invoice_known'], 0)

    def test_blank_new_observation_fields_remain_unknown(self):
        case, row = self.case(goods_receipt_verified=1, support_doc_count=2)
        row.update(support_docs_observed_at=row['posted_at'], goods_receipt_verified_at='', invoice_observed_at='')
        f = self.feature(case)
        self.assertEqual((f['support_docs_known'], f['goods_receipt_verified'], f['invoice_known']), (1, 0, 0))

    def test_conflicting_or_rebound_revisions_are_rejected_including_future(self):
        for changes in ({'status': 'revoked'}, {'vendor_id': 'OTHER', 'observed_at': '2025-08-14T11:00:00+07:00'}):
            with self.subTest(changes=changes):
                case, row = self.case()
                original = self.document(case, row)
                case.tables['transaction_documents'] = [original, dict(original, **changes)]
                with self.assertRaisesRegex(ValueError, 'Conflicting|binding'):
                    self.feature(case)

    def test_invalid_new_timestamps_are_rejected(self):
        for name in ('invoice_observed_at', 'goods_receipt_verified_at'):
            case, row = self.case()
            row[name] = '2025-08-12'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                self.feature(case)

    def test_future_receipt_verification_is_not_available_with_known_documents(self):
        case, row = self.case(goods_receipt_verified=1, support_doc_count=2)
        row.update(support_docs_observed_at=row['posted_at'],
                   goods_receipt_verified_at=stamp(case.at + timedelta(seconds=1)))
        f = self.feature(case)
        self.assertEqual((f['support_doc_count'], f['support_docs_known'], f['goods_receipt_verified']), (2, 1, 0))

    def test_new_columns_are_finite_and_source_is_not_mutated(self):
        case, _ = self.case()
        before = copy.deepcopy(case.tables)
        f = self.feature(case)
        self.assertTrue(set(FLAGS) <= set(FEATURE_DESCRIPTIONS))
        self.assertEqual(set(f), {'transaction_id', *FEATURE_DESCRIPTIONS})
        self.assertEqual(list(f), ['transaction_id', *FEATURE_DESCRIPTIONS])
        self.assertTrue(all(math.isfinite(float(v)) for k, v in f.items() if k != 'transaction_id'))
        self.assertEqual(case.tables, before)

    def test_old_feature_artifact_is_rejected_by_fresh_cache_contract(self):
        files = {'transactions.csv': {'sha256': 'tx'}, 'features.csv': {'sha256': 'features'}}
        meta = dict(version='fixture', files=files, feature_columns=list(FEATURE_DESCRIPTIONS), feature_contract=cache_contract(files))
        old_columns = [c for c in FEATURE_DESCRIPTIONS if c not in FLAGS]
        old = dict(model=SimpleNamespace(n_features_in_=len(old_columns)), feature_columns=old_columns,
                   feature_contract_fingerprint='b7426e60ce2fee4f1fc7afac1d2ab2cb13072a6f02a0bf7595a1d69134e4bee1',
                   sklearn_version='runtime', dataset_version='fixture', training_feature_fingerprint='previous-train',
                   score_direction='higher_is_more_anomalous')
        self.assertFalse(model_compatibility(old, meta, 'runtime')['compatible'])
        with self.assertRaisesRegex(ValueError, 'IF model incompatible'):
            require_model(old, meta, 'runtime')
