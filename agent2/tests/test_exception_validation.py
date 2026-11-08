"""Malformed exception sources must fail before features or rules can grant relief."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.evidence_cases import prepare
from sme_fraud.evidence_policy import EvidenceBook
from sme_fraud.exception_validation import validated_record, validated_tables
from sme_fraud.features import build_features, FEATURE_DESCRIPTIONS
from sme_fraud.payment_evidence import PaymentEvidence
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import INPUT_TABLES, OPTIONAL_INPUT_TABLES, load_inputs, score_rules
from sme_fraud.temporal_evidence import BankChangeHistory, approved_evidence, bank_change_state


SIGNED = dict(company_id='C001', status='approved', evidence_on_file=1, evidence_id='PROOF',
              approver_id='SIGNER', approved_at='2025-08-01T10:00:00+07:00', observed_at='2025-08-02T10:00:00+07:00')


def payment_sources():
    """Business examples specified independently of validator declarations."""
    return {
        'payment_requests': dict(SIGNED, request_id='REQUEST', vendor_id='VENDOR', purchase_order_id='PO',
            contract_id='', invoice_number='', txn_type='vendor_payment', total_vnd=20_000_000),
        'supplier_payment_agreements': dict(SIGNED, agreement_id='AGREEMENT', vendor_id='VENDOR', contract_id='CONTRACT', total_vnd=20_000_000),
        'recurring_payments': dict(SIGNED, pattern_id='RECURRING', vendor_id='', txn_type='rent', frequency='monthly',
            expected_amount_vnd=20_000_000, tolerance_vnd=0, allow_partial=0, effective_from='2025-01-01', effective_to='2025-12-31'),
        'vendor_payment_schedules': dict(SIGNED, schedule_id='ANNUAL', vendor_id='VENDOR', txn_type='vendor_payment',
            schedule_type='annual', window_start_mmdd='12-15', window_end_mmdd='01-15',
            expected_amount_vnd=20_000_000, tolerance_vnd=0, allow_partial=0, effective_from='2025-01-01', effective_to='2026-12-31'),
        'transaction_documents': dict(record_id='DOC', company_id='C001', vendor_id='VENDOR', transaction_id='TX',
            document_type='invoice', invoice_gross_vnd=20_000_000, status='verified', evidence_id='INVOICE',
            verifier_id='SIGNER', verified_at='2025-08-01T10:00:00+07:00', observed_at='2025-08-02T10:00:00+07:00'),
        'procurement_links': dict(link_id='LINK', company_id='C001', vendor_id='VENDOR', transaction_id='TX',
            request_id='REQUEST', purchase_order_id='PO', status='verified', evidence_id='LINK_PROOF',
            verifier_id='SIGNER', verified_at='2025-08-01T10:00:00+07:00', observed_at='2025-08-02T10:00:00+07:00'),
    }


class ExceptionValidationTest(unittest.TestCase):
    def leave(self):
        case = Case()
        row = case.attendance(leave=22)
        return case, row, case.tables['payroll_entitlements'][0]

    def bank(self):
        case = Case()
        row = case.change(verified=True)
        return case, row, case.tables['bank_account_changes'][0]

    def test_e1_rejects_flag_two(self):
        case = Case()
        case.attendance(leave=22)
        case.tables['payroll_entitlements'][0]['evidence_on_file'] = 2
        with self.assertRaisesRegex(ValueError, 'evidence_on_file'):
            case.score()

    def test_b7_and_bank_features_reject_flag_two(self):
        case = Case()
        case.change(verified=True)
        case.tables['bank_account_changes'][0]['callback_verified'] = 2
        with self.assertRaisesRegex(ValueError, 'callback_verified'):
            case.score()

    def test_boolean_domain_in_e1_and_b7(self):
        for factory, field in ((self.leave, 'evidence_on_file'), (self.bank, 'callback_verified')):
            for value in (2, -1, '2', 1.0, 0.0, 'true', 'False', 'yes', '', None, ' 1', [], {}):
                with self.subTest(factory=factory.__name__, value=value):
                    case, _, source = factory()
                    source[field] = value
                    with self.assertRaisesRegex(ValueError, field):
                        build_features(case.tables)

    def test_valid_native_and_csv_flags_keep_e1_b7_outcomes(self):
        for factory, field, rule in ((self.leave, 'evidence_on_file', 'E1'), (self.bank, 'callback_verified', 'B7')):
            for value in (False, True, 0, 1, '0', '1'):
                with self.subTest(rule=rule, value=value):
                    case, row, source = factory()
                    source[field] = value
                    hit = next(h for h in case.score()['hits'] if h['rule_id'] == rule and h['transaction_id'] == row['transaction_id'])
                    expected = 0 if value in (True, 1, '1') else 20
                    self.assertEqual((hit['points'], hit['hard_trigger']), (expected, int(expected == 20)))
                    if rule == 'B7':
                        self.assertEqual(case.features[-1]['bank_change_verified'], int(expected == 0))

    def test_cached_features_do_not_bypass_source_validation(self):
        for factory, field in ((self.leave, 'evidence_on_file'), (self.bank, 'callback_verified')):
            case, _, source = factory()
            case.score()
            source[field] = 2
            with self.assertRaisesRegex(ValueError, field):
                score_rules(case.tables, features=case.features, config={'evidence_policy': 'disabled'})

    def test_future_and_revoked_sources_are_validated_before_filtering(self):
        for factory, field in ((self.leave, 'evidence_on_file'), (self.bank, 'callback_verified')):
            for status in ('revoked', None):
                case, _, source = factory()
                source.update(observed_at='2026-10-17T00:00:00+07:00', **{field: 2})
                if status:
                    source['status'] = status
                with self.assertRaisesRegex(ValueError, field):
                    case.score()

    def test_direct_helpers_cannot_coerce_flag_two(self):
        case, row, source = self.bank()
        source['callback_verified'] = 2
        with self.assertRaisesRegex(ValueError, 'callback_verified'):
            bank_change_state(source, row, {}, row['posted_at'])
        with self.assertRaisesRegex(ValueError, 'evidence_on_file'):
            approved_evidence(dict(SIGNED, evidence_on_file=2), {}, 'C001', row['posted_at'])

    def test_payment_constructors_validate_flags_and_enums(self):
        case = Case()
        case.tables['transactions'] = []
        for table, source in payment_sources().items():
            for field, value in (('status', 'APPROVED'), ('evidence_on_file', 2)):
                if field not in source:
                    continue
                with self.subTest(table=table, field=field):
                    with self.assertRaisesRegex(ValueError, field):
                        PaymentEvidence(dict(case.tables, **{table: [dict(source, **{field: value})]}))
        for field, value in (('evidence_id', True), ('evidence_id', ' '), ('purchase_order_id', 123)):
            with self.assertRaisesRegex(ValueError, field):
                validated_record('payment_requests', dict(payment_sources()['payment_requests'], **{field: value}))

    def test_payment_numeric_fields_reject_truncation_and_nonfinite_values(self):
        amounts = {'payment_requests': 'total_vnd', 'supplier_payment_agreements': 'total_vnd',
                   'recurring_payments': 'expected_amount_vnd', 'vendor_payment_schedules': 'tolerance_vnd',
                   'transaction_documents': 'invoice_gross_vnd'}
        for table, field in amounts.items():
            for value in (True, 1.5, 1.0, -1, '1.5', '1e6', 'NaN', float('inf'), float('nan'), '1,000', ' 1', None):
                with self.subTest(table=table, field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        validated_record(table, dict(payment_sources()[table], **{field: value}))

    def test_payroll_days_and_amounts_have_strict_domains(self):
        _, _, source = self.leave()
        for field in ('required_work_days', 'approved_paid_leave_days', 'entitled_amount_vnd'):
            for value in (True, 1.5, -1, 'NaN', '1e3', None):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        validated_record('payroll_entitlements', dict(source, **{field: value}))
        for field in ('required_work_days', 'approved_paid_leave_days'):
            with self.assertRaisesRegex(ValueError, field):
                validated_record('payroll_entitlements', dict(source, **{field: 32}))

    def test_timestamps_reject_impossible_dates_offsets_and_noncanonical_precision(self):
        _, _, source = self.leave()
        for field in ('approved_at', 'observed_at'):
            for value in ('2025-02-29T10:00:00+07:00', '2025-08-01T24:00:00+07:00',
                          '2025-08-01T10:00:00', '2025-08-01T03:00:00Z', '2025-08-01T10:00+07:00',
                          '2025-08-01T10:00:00.100+07:00', '2025-8-1T10:00:00+07:00',
                          ' 2025-08-01T10:00:00+07:00', None, 20250801):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        validated_record('payroll_entitlements', dict(source, **{field: value}))

    def test_callback_dates_and_signature_chronology_are_checked(self):
        _, _, source = self.bank()
        for field, value in (('effective_at', '2025-02-30T10:00:00+07:00'),
                             ('verified_at', '2025-08-07T10:00:00+00:00'),
                             ('verified_at', '2026-10-17T10:00:00+07:00')):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field + '|observed_at'):
                    BankChangeHistory([dict(source, **{field: value})])
        with self.assertRaisesRegex(ValueError, 'observed_at'):
            validated_record('payment_requests', dict(payment_sources()['payment_requests'],
                approved_at='2025-08-03T10:00:00+07:00'))

    def test_source_enums_are_explicit(self):
        samples = payment_sources()
        samples['payroll_entitlements'] = self.leave()[2]
        for table, field in (('payroll_entitlements', 'leave_type'), ('recurring_payments', 'frequency'),
                             ('vendor_payment_schedules', 'schedule_type'), ('transaction_documents', 'document_type'),
                             ('payment_requests', 'txn_type')):
            for value in ('unknown', '', None, 2):
                with self.subTest(table=table, field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        validated_record(table, dict(samples[table], **{field: value}))

    def test_hr_workflow_receivable_and_document_flags_are_validated(self):
        for code, variant, table, field in (
            ('C4', 'authorized', 'leave_activity_authorizations', 'evidence_on_file'),
            ('E2', 'final_payment', 'payroll_settlements', 'evidence_on_file'),
            ('F2', 'authorized', 'workflow_policies', 'allow_override'),
            ('F2', 'authorized', 'workflow_policies', 'required'),
            ('F2', 'completed', 'override_events', 'normal_workflow_completed'),
            ('F3', 'cancelled_gap', 'document_series', 'cancellation_log_complete'),
            ('F3', 'cancelled_gap', 'document_cancellations', 'evidence_on_file'),
            ('F4', 'explanation', 'receivable_explanations', 'evidence_on_file'),
            ('F4', 'positive', 'receipt_coverage', 'evidence_on_file')):
            with self.subTest(table=table, field=field):
                case, _, _, _ = prepare(code, variant, 7007)
                case.tables[table][0][field] = 2
                with self.assertRaisesRegex(ValueError, field):
                    EvidenceBook(case.tables)

    def test_evidence_enums_and_amounts_are_validated(self):
        for code, variant, table, field, value in (
            ('C4', 'positive', 'system_actions', 'action', 'unknown'),
            ('E2', 'positive', 'employment_events', 'event_type', 'unknown'),
            ('E2', 'positive', 'payroll_settlements', 'payment_kind', 'unknown'),
            ('E2', 'positive', 'payroll_settlements', 'authorized_amount_vnd', True),
            ('F2', 'authorized', 'workflow_policies', 'override_max_vnd', 10.5),
            ('F2', 'authorized', 'override_events', 'status', 'unknown'),
            ('F3', 'positive', 'document_register', 'state', 'unknown'),
            ('F3', 'positive', 'document_register', 'document_number', '1.5'),
            ('F3', 'positive', 'document_series', 'fiscal_year', 10000),
            ('F4', 'fully_paid', 'receipt_allocations', 'amount_vnd', -1),
            ('F4', 'fully_paid', 'receipt_allocations', 'status', 'unknown'),
            ('F4', 'positive', 'receivable_invoices', 'gross_vnd', '1e6'),
            ('F4', 'explanation', 'receivable_explanations', 'reason', 'unknown')):
            with self.subTest(table=table, field=field):
                case, _, _, _ = prepare(code, variant, 7008)
                case.tables[table][0][field] = value
                with self.assertRaisesRegex(ValueError, field):
                    EvidenceBook(case.tables)

    def test_ranges_and_calendar_dates_are_checked(self):
        for code, variant, table, field, value in (
            ('C4', 'positive', 'leave_periods', 'ends_at', '2025-01-01T00:00:00+07:00'),
            ('E2', 'positive', 'employment_events', 'effective_date', '2025-02-29'),
            ('E2', 'positive', 'payroll_settlements', 'service_period_end', '2025-01-01'),
            ('F2', 'authorized', 'workflow_policies', 'effective_to', '2024-12-31T00:00:00+07:00'),
            ('F3', 'positive', 'document_series', 'closed_through_number', 0),
            ('F4', 'positive', 'receivable_invoices', 'due_at', '2025-01-01T00:00:00+07:00'),
            ('F4', 'positive', 'receipt_coverage', 'covered_through', '2025-01-01T00:00:00+07:00'),
            ('F4', 'explanation', 'receivable_explanations', 'expires_at', '2025-01-01T00:00:00+07:00')):
            with self.subTest(table=table, field=field):
                case, _, _, _ = prepare(code, variant, 7009)
                case.tables[table][0][field] = value
                with self.assertRaisesRegex(ValueError, field):
                    EvidenceBook(case.tables)

    def test_operating_shift_validation_keeps_valid_overnight_shifts(self):
        case, _, _, _ = prepare('C1', 'approved_shift', 7010)
        source = case.tables['operating_schedules'][0]
        for field, value in (('weekdays', '7'), ('weekdays', '1,1'), ('start_time', '24:00'),
                             ('end_time', '06:61'), ('holiday_work_allowed', 2), ('action', 'unknown')):
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, field):
                    validated_record('operating_schedules', dict(source, **{field: value}))
        self.assertEqual(validated_record('operating_schedules', source)['end_time'], '06:00')

    def test_annual_windows_and_leap_days(self):
        source = payment_sources()['vendor_payment_schedules']
        self.assertEqual(validated_record('vendor_payment_schedules', source)['window_end_mmdd'], '01-15')
        validated_record('vendor_payment_schedules', dict(source, window_start_mmdd='02-29'))
        for value in ('02-30', '13-01', '2-01'):
            with self.assertRaisesRegex(ValueError, 'window_start_mmdd'):
                validated_record('vendor_payment_schedules', dict(source, window_start_mmdd=value))

    def test_recurring_date_and_timestamp_intervals_cannot_be_mixed(self):
        source = payment_sources()['recurring_payments']
        validated_record('recurring_payments', source)
        validated_record('recurring_payments', dict(source, effective_from='2025-01-01T00:00:00+07:00', effective_to='2026-01-01T00:00:00+07:00'))
        with self.assertRaisesRegex(ValueError, 'effective_to'):
            validated_record('recurring_payments', dict(source, effective_to='2026-01-01T00:00:00+07:00'))

    def test_master_and_alternative_attendance_flags_cannot_grant_exceptions(self):
        for table, field in (('employees', 'contract_on_file'), ('companies', 'saturday_operations'),
                             ('attendance', 'alternative_work_evidence')):
            case, _, _ = self.leave()
            case.tables[table][0][field] = 2
            with self.assertRaisesRegex(ValueError, field):
                case.score()

    def test_missing_proof_stays_non_authorizing(self):
        case, row, source = self.leave()
        source.update(evidence_id='', approver_id='', approved_at='')
        hit = next(h for h in case.score()['hits'] if h['rule_id'] == 'E1' and h['transaction_id'] == row['transaction_id'])
        self.assertEqual((hit['points'], hit['hard_trigger']), (20, 1))
        case, row, source = self.bank()
        source.update(verified_at='', approver_id='')
        self.assertEqual(next(h for h in case.score()['hits'] if h['rule_id'] == 'B7')['points'], 20)

    def test_normalization_preserves_source_snapshot_and_csv_semantics(self):
        original = payment_sources()
        original = {name: [row] for name, row in original.items()}
        csv_rows = {name: [{field: str(value) if type(value) is int else value for field, value in row.items()}]
                    for name, (row,) in original.items()}
        before = copy.deepcopy(csv_rows)
        self.assertEqual(validated_tables(original), validated_tables(csv_rows))
        self.assertEqual(csv_rows, before)
        validated_tables(csv_rows)['payment_requests'][0]['total_vnd'] = 0
        self.assertEqual(csv_rows, before)

    def test_valid_non_authorizing_statuses_remain_valid(self):
        for status in ('draft', 'pending', 'rejected', 'revoked'):
            validated_record('payment_requests', dict(payment_sources()['payment_requests'], status=status))
        for status in ('unverified', 'pending', 'rejected', 'revoked'):
            validated_record('transaction_documents', dict(payment_sources()['transaction_documents'], status=status))

    def test_transaction_proof_flags_are_also_strict(self):
        case = Case()
        row = case.pay(kind='advance_writeoff')
        row['evidence_on_file'] = 2
        case.tables['transactions'] = case.rows
        with self.assertRaisesRegex(ValueError, 'evidence_on_file'):
            build_features(case.tables)

    def test_declared_relationship_dates_cannot_grant_exceptions_with_malformed_times(self):
        case = Case()
        case.pay()
        case.vendor['related_party_disclosed_at'] = '2025-02-30T00:00:00+07:00'
        with self.assertRaisesRegex(ValueError, 'related_party_disclosed_at'):
            case.score()

    def test_transaction_caps_and_document_times_cannot_be_silently_coerced(self):
        for field, value in (('invoice_gross_vnd', 9_000_000.5), ('amount_vnd', True),
                             ('approval_limit_vnd', 0), ('support_docs_observed_at', '2025-02-30T00:00:00+07:00')):
            with self.subTest(field=field):
                case = Case()
                row = case.pay()
                case.score()
                # Inject after the generator's accounting enrichment so the
                # real feature/rule entry points receive the malformed value.
                row[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    build_features(case.tables)
                with self.assertRaisesRegex(ValueError, field):
                    score_rules(case.tables, features=case.features)

    def test_csv_loader_rejects_malformed_source_even_with_matching_manifest(self):
        case, _, source = self.leave()
        case.score()
        source['evidence_on_file'] = 2
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = {'files': {}}
            for name in (*INPUT_TABLES, *OPTIONAL_INPUT_TABLES, 'features'):
                rows = case.features if name == 'features' else case.tables.get(name, [])
                if not rows and name in OPTIONAL_INPUT_TABLES:
                    continue
                path = directory / f'{name}.csv'
                fields = ['transaction_id', *FEATURE_DESCRIPTIONS] if name == 'features' else list(dict.fromkeys(field for row in rows for field in row))
                with path.open('w', encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                manifest['files'][path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'payroll_entitlements/.*evidence_on_file'):
                load_inputs(directory)


if __name__ == '__main__':
    unittest.main()
