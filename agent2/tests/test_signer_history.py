"""Evidence follows the employee revision known when it was signed, not posted."""
import copy
import unittest
from datetime import timedelta

import test_noise_policy as noise_fixtures
import test_spec_policy as spec_fixtures
from sme_fraud.generate import parse, stamp
from sme_fraud.rule_audit_cases import Case
from sme_fraud.temporal_evidence import EmployeeHistory


class SignerHistoryTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3', 'evidence_policy': 'phase4'}
        return case

    @staticmethod
    def hit(result, row, rule):
        return next((h for h in result['hits']
                     if h['transaction_id'] == row['transaction_id'] and h['rule_id'] == rule), None)

    @staticmethod
    def revise(case, employee, at, **changes):
        case.tables['employees'].append(dict(employee, recorded_at=stamp(at), **changes))

    def prepare(self, rule):
        case = self.case()
        if rule == 'E1':
            row = case.attendance(leave=22)
            source = case.tables['payroll_entitlements'][-1]
            signed_at = parse(source['approved_at'])
        else:
            row = case.change(verified=True)
            source = case.tables['bank_account_changes'][-1]
            signed_at = parse(source['verified_at'])
        return case, row, source, signed_at

    def assert_points(self, case, row, rule, points):
        hit = self.hit(case.score(), row, rule)
        self.assertIsNotNone(hit)
        self.assertEqual((hit['points'], hit['hard_trigger']), (points, int(points == 20)))
        if rule == 'B7':
            self.assertEqual(case.features[-1]['bank_change_verified'], int(points == 0))
        return hit

    def test_e1_name_revision_does_not_invalidate_signed_entitlement(self):
        case, row, _, _ = self.prepare('E1')
        before = self.assert_points(case, row, 'E1', 0)
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        after = self.assert_points(case, row, 'E1', 0)
        self.assertEqual(before, after)

    def test_b7_name_revision_preserves_callback_and_bank_features(self):
        case, row, _, _ = self.prepare('B7')
        before = self.assert_points(case, row, 'B7', 0)
        features = copy.deepcopy(case.features)
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        after = self.assert_points(case, row, 'B7', 0)
        self.assertEqual(before, after)
        self.assertEqual(features, case.features)

    def check_signer_transfer(self, rule):
        for before_signing in (True, False):
            with self.subTest(before_signing=before_signing):
                case, row, _, signed_at = self.prepare(rule)
                case.tables['companies'].append(dict(case.tables['companies'][0], company_id='OTHER'))
                moved_at = signed_at - timedelta(seconds=1) if before_signing else signed_at + timedelta(seconds=1)
                self.revise(case, case.director, moved_at, company_id='OTHER')
                self.assert_points(case, row, rule, 20 if before_signing else 0)

    def test_e1_signer_company_is_selected_at_approval(self):
        self.check_signer_transfer('E1')

    def test_b7_verifier_company_is_selected_at_callback(self):
        self.check_signer_transfer('B7')

    def test_company_filter_cannot_resurrect_a_stale_employee_version(self):
        for rule in ('E1', 'B7'):
            with self.subTest(rule=rule):
                case, row, _, signed_at = self.prepare(rule)
                case.tables['companies'].append(dict(case.tables['companies'][0], company_id='OTHER'))
                self.revise(case, case.director, signed_at - timedelta(seconds=1), company_id='OTHER')
                self.revise(case, case.director, signed_at + timedelta(seconds=1), full_name='Returned')
                self.assert_points(case, row, rule, 20)

    def test_signer_must_already_be_known_at_signature_time(self):
        for rule in ('E1', 'B7'):
            for offset in (0, 1):
                with self.subTest(rule=rule, seconds_after=offset):
                    case, row, _, signed_at = self.prepare(rule)
                    case.tables['employees'] = [e for e in case.tables['employees']
                                                if e['employee_id'] != case.director['employee_id']]
                    self.revise(case, case.director, signed_at + timedelta(seconds=offset))
                    self.assert_points(case, row, rule, 20 if offset else 0)

    def test_employee_added_after_signing_cannot_backfill_missing_signer(self):
        for rule in ('E1', 'B7'):
            with self.subTest(rule=rule):
                case, row, source, signed_at = self.prepare(rule)
                source['approver_id'] = 'NEW_SIGNER'
                self.revise(case, case.director, signed_at + timedelta(days=1), employee_id='NEW_SIGNER')
                self.assert_points(case, row, rule, 20)

    def test_self_approval_is_not_made_independent_by_a_later_profile(self):
        for rule in ('E1', 'B7'):
            with self.subTest(rule=rule):
                case, row, source, _ = self.prepare(rule)
                subject = case.worker if rule == 'E1' else case.maker
                source['approver_id'] = subject['employee_id']
                self.revise(case, subject, case.at - timedelta(days=1), full_name='Updated subject')
                self.assert_points(case, row, rule, 20)

    def test_future_employee_revision_cannot_change_past_results(self):
        for rule in ('E1', 'B7'):
            with self.subTest(rule=rule):
                case, _, _, _ = self.prepare(rule)
                before = copy.deepcopy(case)
                self.revise(case, case.director, case.at + timedelta(days=1), role='new_role')
                self.assertEqual(case.score(), before.score())
                self.assertEqual(case.features, before.features)

    def test_future_proof_cannot_become_valid_through_employee_history(self):
        for rule in ('E1', 'B7'):
            with self.subTest(rule=rule):
                case, row, source, _ = self.prepare(rule)
                source['observed_at'] = stamp(case.at + timedelta(days=1))
                self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
                if rule == 'E1':
                    self.assert_points(case, row, rule, 20)
                else:
                    self.assertIsNone(self.hit(case.score(), row, rule))
                    self.assertEqual(case.features[-1]['bank_change_verified'], 0)

    def test_e1_revocation_still_wins_after_signer_profile_update(self):
        case, first, source, _ = self.prepare('E1')
        second = case.pay(case.at + timedelta(days=1), kind='payroll', amount=first['amount_vnd'])
        second['amount_vnd'] = first['amount_vnd']
        case.tables['payroll_entitlements'].append(dict(source, status='revoked',
            observed_at=stamp(case.at + timedelta(hours=1))))
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        result = case.score()
        self.assertEqual([self.hit(result, row, 'E1')['points'] for row in (first, second)], [0, 20])

    def test_callback_revocation_does_not_retroactively_change_verified_payment(self):
        case, first, source, _ = self.prepare('B7')
        second = case.pay(case.at + timedelta(days=1), 50_000_000,
                          recipient_account=first['recipient_account'],
                          recipient_bank_code=first['recipient_bank_code'])
        case.tables['bank_account_changes'].append(dict(source, callback_verified=0,
            observed_at=stamp(case.at + timedelta(hours=1))))
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        result = case.score()
        self.assertEqual([self.hit(result, row, 'B7')['points'] for row in (first, second)], [0, 20])
        self.assertEqual([f['bank_change_verified'] for f in case.features], [1, 0])

    def test_shift_approval_survives_signer_name_revision(self):
        case = self.case()
        noise_fixtures.NoisePolicyTest().schedule(case)
        row = case.pay(case.at.replace(hour=23))
        self.assertIsNone(self.hit(case.score(), row, 'C1'))
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        self.assertIsNone(self.hit(case.score(), row, 'C1'))

    def test_shift_actor_role_is_selected_at_action_time(self):
        for before_action in (True, False):
            with self.subTest(before_action=before_action):
                case = self.case()
                record = noise_fixtures.NoisePolicyTest().schedule(case, 'maker')
                record.update(employee_id=case.maker['employee_id'], role=case.maker['role'])
                row = case.pay(case.at.replace(hour=23))
                row.update(created_at=stamp(case.at.replace(hour=22)), approved_at=stamp(case.at.replace(hour=23)))
                self.revise(case, case.maker, case.at.replace(hour=21 if before_action else 22, minute=30), role='new_role')
                hit = self.hit(case.score(), row, 'C1')
                self.assertIsNotNone(hit)
                self.assertEqual(hit['evidence']['created_outside'], int(before_action))

    def test_independent_purchase_proofs_survive_verifier_revision(self):
        case = self.case()
        rows = [case.pay(case.at + timedelta(days=i), 9_000_000) for i in range(2)]
        for index, row in enumerate(rows):
            case.tables['procurement_links'].append(noise_fixtures.NoisePolicyTest().proof(case,
                link_id=f'LINK_{index}', vendor_id=row['vendor_id'], transaction_id=row['transaction_id'],
                request_id=f'REQ_{index}', purchase_order_id=f'PO_{index}'))
        self.assertEqual(self.hit(case.score(), rows[-1], 'A1')['points'], 0)
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        self.assertEqual(self.hit(case.score(), rows[-1], 'A1')['points'], 0)

    def test_typed_fulfilment_survives_verifier_revision(self):
        case = self.case()
        case.new_vendor()
        row = case.pay(amount=50_000_000)
        for index, kind in enumerate(('invoice', 'purchase_order', 'goods_receipt')):
            case.tables['transaction_documents'].append(noise_fixtures.NoisePolicyTest().proof(case,
                record_id=f'DOC_{index}', vendor_id=row['vendor_id'], transaction_id=row['transaction_id'], document_type=kind))
        self.assertTrue(self.hit(case.score(), row, 'B3')['suppressed_reason'])
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        self.assertTrue(self.hit(case.score(), row, 'B3')['suppressed_reason'])

    def test_payroll_period_cap_survives_approver_revision(self):
        case = self.case()
        case.worker['contract_on_file'] = 1
        case.tables['payroll_entitlements'] = [spec_fixtures.SpecPolicyTest().approved(case,
            entitlement_id='PAYROLL', employee_id=case.worker['employee_id'], payroll_period='2025-08',
            leave_type='regular_payroll', entitled_amount_vnd=17_000_000)]
        rows = [case.pay(case.at + timedelta(days=i), kind='payroll') for i in range(3)]
        for row in rows:
            row['amount_vnd'] = 17_000_000
        self.assertIsNone(self.hit(case.score(), rows[-1], 'A4'))
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        self.assertIsNone(self.hit(case.score(), rows[-1], 'A4'))

    def test_recurring_round_amount_proof_survives_approver_revision(self):
        for blank_employee_column in (False, True):
            with self.subTest(blank_employee_column=blank_employee_column):
                case = self.case()
                case.sequence([1_000_000] * 25, kind='cash_expense', start=case.at - timedelta(days=30))
                row = case.pay(amount=3_000_000, kind='cash_expense')
                pattern = spec_fixtures.SpecPolicyTest().approved(case,
                    pattern_id='ROUND', vendor_id='', txn_type='cash_expense', frequency='monthly',
                    expected_amount_vnd=3_000_000, tolerance_vnd=0, effective_from='2025-01-01T00:00:00+07:00',
                    effective_to='2026-01-01T00:00:00+07:00')
                if blank_employee_column:
                    pattern['employee_id'] = ''
                case.tables['recurring_payments'] = [pattern]
                self.assertTrue(self.hit(case.score(), row, 'A5')['suppressed_reason'])
                self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
                self.assertTrue(self.hit(case.score(), row, 'A5')['suppressed_reason'])

    def test_close_and_materiality_approvals_survive_signer_revision(self):
        case = self.case()
        row = case.pay(kind='adjustment', amount=5_000_000)
        spec_fixtures.SpecPolicyTest().manual(case, row)
        self.assertEqual(self.hit(case.score(), row, 'F1')['points'], 8)
        self.revise(case, case.director, case.at - timedelta(days=1), full_name='Updated name')
        hit = self.hit(case.score(), row, 'F1')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['points'], 8)

    def test_unknown_checker_cannot_borrow_maker_shift(self):
        case = self.case()
        schedule = noise_fixtures.NoisePolicyTest().schedule(case)
        schedule['employee_id'] = case.maker['employee_id']
        row = case.pay(case.at.replace(hour=23), approver_id='UNKNOWN')
        hit = self.hit(case.score(), row, 'C1')
        self.assertIsNotNone(hit)
        self.assertEqual((hit['evidence']['created_outside'], hit['evidence']['approved_outside']), (0, 1))

    def test_employee_history_selects_by_time_independently_of_input_order(self):
        case = self.case()
        old = dict(case.director)
        new = dict(old, full_name='Updated name', recorded_at=stamp(case.at))
        rows = [new, old]
        before = copy.deepcopy(rows)
        history = EmployeeHistory(rows)
        self.assertEqual(history.employee_at(old['employee_id'], stamp(case.at - timedelta(seconds=1))), old)
        self.assertEqual(history.employee_at(old['employee_id'], stamp(case.at)), new)
        self.assertEqual(rows, before)

    def test_duplicate_equivalent_employee_revisions_are_idempotent(self):
        case = self.case()
        original = case.director
        history = EmployeeHistory([original, dict(original)])
        self.assertEqual(history.at(stamp(case.at)), {original['employee_id']: original})

    def test_conflicting_same_time_employee_revisions_are_rejected(self):
        case = self.case()
        for changes in ({'full_name': 'Other name'}, {'company_id': 'OTHER'}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, 'Conflicting employee revision'):
                    EmployeeHistory([case.director, dict(case.director, **changes)])

    def test_journal_actor_is_selected_at_entry_not_posting(self):
        case = self.case()
        row = case.pay(kind='adjustment', amount=5_000_000)
        spec_fixtures.SpecPolicyTest().manual(case, row)
        self.assertEqual(self.hit(case.score(), row, 'F1')['points'], 8)
        self.revise(case, case.maker, parse(row['created_at']) + timedelta(seconds=1), full_name='Updated maker')
        hit = self.hit(case.score(), row, 'F1')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['points'], 8)
