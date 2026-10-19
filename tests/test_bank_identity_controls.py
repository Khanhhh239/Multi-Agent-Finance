"""Recipient identity must agree across rules, history, callbacks and features."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case
from sme_fraud.temporal_evidence import BankChangeHistory, bank_change_state


class BankIdentityControlsTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3', 'evidence_policy': 'phase4'}
        return case

    @staticmethod
    def hits(result, rule, row=None):
        return [hit for hit in result['hits'] if hit['rule_id'] == rule
                and (row is None or hit['transaction_id'] == row['transaction_id'])]

    def payments(self, banks, *, days=1, amount=9_000_000, accounts=None):
        case = self.case()
        rows = []
        for index, bank in enumerate(banks):
            rows.append(case.pay(case.at + timedelta(days=index * days), amount,
                                 recipient_account=accounts[index] if accounts else '0123456789',
                                 recipient_bank_code=bank, invoice_number=f'INV_{index}',
                                 invoice_gross_vnd=amount))
        return case, rows

    def bank_change(self, *, verified=False):
        case = self.case()
        row = case.change(verified=verified)
        source = case.tables['bank_account_changes'][-1]
        source.update(new_account='0123456789', new_bank_code='BANK_A')
        row.update(recipient_account='0123456789', recipient_bank_code='BANK_A')
        return case, row, source

    def test_different_banks_do_not_share_a_recipient(self):
        case, _ = self.payments(['BANK_A', 'BANK_B'])
        vendors = case.tables['vendors'][12:14]
        for index, row in enumerate(case.rows):
            row['vendor_id'] = vendors[index]['vendor_id']
        result = case.score()
        self.assertFalse(any(h['points'] for h in self.hits(result, 'A1')))
        self.assertEqual(case.features[-1]['recipient_count_3d'], 0)
        self.assertEqual(case.features[-1]['recipient_sum_limit_3d'], 0)

    def test_same_bank_identity_matches_formatting_and_keeps_alert_without_payment_proof(self):
        case, rows = self.payments([' bank-a ', 'BANK_A'],
                                   accounts=['0123 456-789', '0123456789'])
        result = case.score()
        hit, = self.hits(result, 'A1', rows[-1])
        self.assertEqual(hit['points'], 8)
        self.assertFalse(hit['suppressed_reason'])
        self.assertTrue(hit['evidence']['recipient_identity'])
        self.assertEqual(case.features[-1]['recipient_count_3d'], 1)

    def test_leading_zero_is_part_of_the_account(self):
        case, _ = self.payments(['BANK_A', 'BANK_A'], accounts=['0123456789', '123456789'])
        self.assertFalse(any(h['points'] for h in self.hits(case.score(), 'A1')))
        self.assertEqual(case.features[-1]['recipient_count_3d'], 0)

    def test_a2_uses_bank_and_account_in_long_history(self):
        for banks, expected in ((['BANK_A'] * 3, True), (['BANK_A', 'BANK_B', 'BANK_A'], False)):
            with self.subTest(banks=banks):
                case, rows = self.payments(banks, days=5, amount=7_000_000)
                hit = self.hits(case.score(), 'A2', rows[-1])
                self.assertEqual(any(h['points'] > 0 for h in hit), expected)

    def test_unknown_bank_is_a_gap_without_recipient_matching_or_master_inference(self):
        case, rows = self.payments(['', '', ''])
        case.vendor.update(bank_account='0123456789', bank_code='BANK_A')
        result = case.score()
        for rule in ('A1', 'A2'):
            hit, = self.hits(result, rule, rows[-1])
            self.assertEqual((hit['points'], hit['hard_trigger'], hit['scoring_role']), (0, 0, 'context'))
            self.assertEqual(hit['evidence']['evidence_status'], 'information_gap')
            self.assertIn('recipient_bank_code', hit['evidence']['missing_fields'])
        self.assertEqual([f['recipient_count_3d'] for f in case.features], [0, 0, 0])
        self.assertEqual(case.features[-1]['creator_recipients_7d'], 0)

    def test_unconfirmed_history_does_not_contaminate_confirmed_recipient(self):
        case, rows = self.payments(['', 'BANK_A', 'BANK_A'])
        result = case.score()
        self.assertFalse(any(h['points'] for h in self.hits(result, 'A1', rows[1])))
        hit, = self.hits(result, 'A1', rows[2])
        self.assertEqual(hit['evidence']['count'], 2)
        self.assertEqual(hit['related_transaction_ids'], [rows[1]['transaction_id']])

    def test_creator_recipient_counts_distinguish_banks(self):
        for banks, expected in ((['BANK_A', 'BANK_B', 'BANK_A'], 2), (['BANK_A'] * 3, 1)):
            with self.subTest(banks=banks):
                case, _ = self.payments(banks)
                case.score()
                self.assertEqual(case.features[-1]['creator_recipients_7d'], expected)

    def test_unknown_recipient_does_not_disable_strong_graph_a3(self):
        case, _ = self.payments(['', ''])
        vendors = case.shared_vendors()
        for index, row in enumerate(case.rows):
            row['vendor_id'] = vendors[index]['vendor_id']
        result = case.score()
        self.assertTrue(any(h['points'] for h in self.hits(result, 'A3')))
        self.assertFalse(any(h['points'] for h in self.hits(result, 'A1')))

    def test_bank_change_for_other_bank_is_not_a_payment_match(self):
        case, row, _ = self.bank_change()
        row['recipient_bank_code'] = 'BANK_B'
        result = case.score()
        self.assertFalse(self.hits(result, 'B7'))
        self.assertEqual((case.features[-1]['bank_changed_recently'],
                          case.features[-1]['bank_change_verified']), (0, 0))

    def test_same_bank_change_requires_valid_independent_callback(self):
        for verified in (False, True):
            with self.subTest(verified=verified):
                case, row, _ = self.bank_change(verified=verified)
                hit, = self.hits(case.score(), 'B7')
                self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0) if verified else (20, 1))
                self.assertEqual(hit['evidence']['change_bank_identity'], hit['evidence']['recipient_identity'])
                self.assertEqual(case.features[-1]['bank_change_verified'], int(verified))

    def test_callback_for_another_bank_cannot_verify_payment(self):
        case, row, _ = self.bank_change(verified=True)
        row['recipient_bank_code'] = 'BANK_B'
        self.assertFalse(self.hits(case.score(), 'B7'))
        self.assertEqual(case.features[-1]['bank_change_verified'], 0)

    def test_missing_change_or_payment_bank_is_an_explicit_gap(self):
        for missing_source, missing_recipient in ((True, False), (False, True), (True, True)):
            with self.subTest(source=missing_source, recipient=missing_recipient):
                case, row, source = self.bank_change(verified=True)
                if missing_source:
                    source.pop('new_bank_code')
                if missing_recipient:
                    row['recipient_bank_code'] = ''
                hit, = self.hits(case.score(), 'B7')
                self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0))
                self.assertEqual(hit['evidence']['evidence_status'], 'information_gap')
                self.assertEqual(case.features[-1]['bank_change_verified'], 0)

    def test_different_account_has_no_bank_change_signal(self):
        case, row, _ = self.bank_change()
        row['recipient_account'] = '1123456789'
        self.assertFalse(self.hits(case.score(), 'B7'))
        self.assertEqual(case.features[-1]['bank_changed_recently'], 0)

    def test_callback_revision_cannot_rebind_account_bank_vendor_or_effective_date(self):
        for updates in ({'new_bank_code': 'BANK_B'}, {'new_account': '9999999999'},
                        {'vendor_id': 'OTHER_VENDOR'}, {'old_bank_code': 'BANK_B'},
                        {'effective_at': '2025-08-08T11:00:00+07:00'}):
            with self.subTest(updates=updates):
                case, _, source = self.bank_change()
                case.tables['bank_account_changes'].append(dict(source, **updates,
                    observed_at=stamp(case.at - timedelta(days=1)), callback_verified=1))
                with self.assertRaisesRegex(ValueError, 'Bank change binding changed'):
                    case.score()

    def test_equivalent_bank_formatting_is_not_a_binding_change(self):
        case, row, source = self.bank_change()
        case.tables['bank_account_changes'].append(dict(source,
            new_bank_code=' bank-a ', new_account='0123 456-789', callback_verified=1,
            verified_at=stamp(case.at - timedelta(days=2)),
            observed_at=stamp(case.at - timedelta(days=1)), approver_id=case.director['employee_id']))
        hit, = self.hits(case.score(), 'B7')
        self.assertEqual((hit['points'], hit['hard_trigger']), (0, 0))
        self.assertEqual(case.features[-1]['bank_change_verified'], 1)

    def test_cross_company_or_vendor_source_cannot_match(self):
        case, row, source = self.bank_change(verified=True)
        for field in ('company_id', 'vendor_id'):
            with self.subTest(field=field):
                changed = dict(source, **{field: 'OTHER'})
                self.assertEqual(bank_change_state(changed, row,
                    {e['employee_id']: e for e in case.tables['employees']}, stamp(case.at)), (False, False))
        history = BankChangeHistory([source])
        history.advance(stamp(case.at))
        self.assertIsNone(history.current('OTHER', row['vendor_id'], stamp(case.at)))

    def test_employee_bank_features_require_same_institution(self):
        for bank, expected in (('BANK_A', 1), ('BANK_B', 0), ('', 0)):
            with self.subTest(bank=bank):
                case = self.case()
                case.worker.update(bank_account='0123456789', bank_code='BANK_A')
                case.pay(recipient_account='0123456789', recipient_bank_code=bank)
                case.score()
                feature = case.features[-1]
                self.assertEqual(feature['employee_bank_overlap'], expected)
                self.assertEqual(feature['payable_to_employee_bank'], expected)
                payroll = case.pay(case.at + timedelta(days=1), kind='payroll',
                                   recipient_account='0123456789', recipient_bank_code=bank)
                case.score()
                feature = next(f for f in case.features if f['transaction_id'] == payroll['transaction_id'])
                self.assertEqual(feature['recipient_employee_bank_count'], expected)

    def test_employee_revision_removes_old_bank_identity_from_features(self):
        case = self.case()
        case.worker.update(bank_account='0123456789', bank_code='BANK_A')
        case.pay(recipient_account='0123456789', recipient_bank_code='BANK_A')
        case.tables['employees'].append(dict(case.worker, bank_code='BANK_B',
            recorded_at=stamp(case.at + timedelta(hours=1))))
        case.pay(case.at + timedelta(days=1), recipient_account='0123456789', recipient_bank_code='BANK_A')
        case.pay(case.at + timedelta(days=2), recipient_account='0123456789', recipient_bank_code='BANK_B')
        case.score()
        self.assertEqual([f['employee_bank_overlap'] for f in case.features], [1, 0, 1])

    def test_graph_bank_features_do_not_merge_different_or_unknown_banks(self):
        for banks, expected in ((['BANK_A', 'BANK_B'], 1), (['BANK_A'] * 2, 2), ([''] * 2, 1)):
            with self.subTest(banks=banks):
                case = self.case()
                vendors = case.tables['vendors'][12:14]
                for vendor, bank in zip(vendors, banks):
                    case.tables['entity_links'].append(dict(company_id='C001',
                        source_id=vendor['vendor_id'], target_id='0123456789', bank_code=bank,
                        link_type='bank_account', observed_at=stamp(case.at - timedelta(days=1))))
                case.pay(vendor=vendors[-1])
                case.score()
                self.assertEqual(case.features[-1]['linked_vendor_count'], expected)

    def test_unique_synthetic_accounts_remain_usable_without_bank_codes(self):
        case, rows = self.payments(['', ''], accounts=['BANK_SYN_ACCOUNT_1'] * 2)
        hit, = self.hits(case.score(), 'A1', rows[-1])
        self.assertEqual(hit['points'], 8)
        self.assertEqual(case.features[-1]['recipient_count_3d'], 1)

    def test_future_bank_source_does_not_change_past_rules_or_features(self):
        case, _, source = self.bank_change()
        before = copy.deepcopy(case)
        case.tables['bank_account_changes'].append(dict(source, change_id='FUTURE',
            new_bank_code='BANK_B', observed_at=stamp(case.at + timedelta(days=1))))
        self.assertEqual(case.score(), before.score())
        self.assertEqual(case.features, before.features)
