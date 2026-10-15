"""Bound evidence and cumulative-cap controls for A1/A2/A4."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


class PaymentEvidenceTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3'}
        return case

    def hit(self, result, row, rule):
        return next((h for h in result['hits'] if h['transaction_id'] == row['transaction_id']
                     and h['rule_id'] == rule), None)

    def active(self, result, row, rule):
        hit = self.hit(result, row, rule)
        return bool(hit and hit['points'])

    def source_times(self, c, offset=0):
        return stamp(c.at + timedelta(days=offset-3)), stamp(c.at + timedelta(days=offset-2))

    def request(self, c, request_id, po_id, total, *, contract='', invoice='', offset=0,
                status='approved', recipient=''):
        approved, observed = self.source_times(c, offset)
        c.tables['payment_requests'].append(dict(request_id=request_id, company_id='C001',
            vendor_id=c.vendor['vendor_id'], purchase_order_id=po_id, contract_id=contract,
            invoice_number=invoice, txn_type='vendor_payment', total_vnd=total,
            status=status, evidence_on_file=1, evidence_id=f'EV_{request_id}',
            approver_id=c.director['employee_id'], approved_at=approved, observed_at=observed,
            recipient_account=recipient, recipient_bank_code=''))

    def bind(self, c, row, request_id, po_id, *, contract='', invoice=None, status='verified', offset=0):
        verified, observed = self.source_times(c, offset)
        c.tables['procurement_links'].append(dict(link_id=f'L_{row["transaction_id"]}',
            company_id='C001', vendor_id=row['vendor_id'], transaction_id=row['transaction_id'],
            request_id=request_id, purchase_order_id=po_id, contract_id=contract,
            invoice_number=row['invoice_number'] if invoice is None else invoice,
            status=status, evidence_id=f'LINK_{row["transaction_id"]}',
            verifier_id=c.director['employee_id'], verified_at=verified, observed_at=observed))

    def invoice(self, c, row, *, number=None, gross=None, status='verified', offset=0):
        verified, observed = self.source_times(c, offset)
        c.tables['transaction_documents'].append(dict(record_id=f'INV_{row["transaction_id"]}',
            company_id='C001', vendor_id=row['vendor_id'], transaction_id=row['transaction_id'],
            document_type='invoice', invoice_number=row['invoice_number'] if number is None else number,
            invoice_gross_vnd=row['invoice_gross_vnd'] if gross is None else gross,
            status=status, evidence_id=f'DOC_{row["transaction_id"]}',
            verifier_id=c.director['employee_id'], verified_at=verified, observed_at=observed))

    def bind_request_rows(self, c, rows, request_id='REQ', po_id='PO', total=None):
        total = total if total is not None else sum(int(r['amount_vnd']) for r in rows)
        self.request(c, request_id, po_id, total, invoice=rows[0]['invoice_number'])
        for row in rows:
            self.bind(c, row, request_id, po_id)
            self.invoice(c, row)

    def agreement(self, c, total, contract='CONTRACT', status='approved', offset=0):
        approved, observed = self.source_times(c, offset)
        c.tables['supplier_payment_agreements'].append(dict(agreement_id='AGR', company_id='C001',
            vendor_id=c.vendor['vendor_id'], contract_id=contract, invoice_number='', total_vnd=total,
            status=status, evidence_on_file=1, evidence_id='EV_AGR', approver_id=c.director['employee_id'],
            approved_at=approved, observed_at=observed))

    def recurring(self, c, *, pattern='RENT', total=17_000_000, contract='', frequency='monthly',
                  allow_partial=0, status='approved'):
        approved, observed = self.source_times(c)
        c.tables['recurring_payments'].append(dict(pattern_id=pattern, company_id='C001',
            vendor_id=c.vendor['vendor_id'], employee_id='', txn_type='rent', contract_id=contract,
            invoice_number='', frequency=frequency, expected_amount_vnd=total, tolerance_vnd=0,
            allow_partial=allow_partial, effective_from='2025-01-01', effective_to='2025-12-31',
            status=status, evidence_on_file=1, evidence_id=f'EV_{pattern}',
            approver_id=c.director['employee_id'], approved_at=approved, observed_at=observed))

    def test_same_approved_request_installments_under_caps_suppress_a1_and_a2(self):
        c = self.case()
        rows = [c.pay(c.at + timedelta(days=i), invoice_number='INV', invoice_gross_vnd=27_000_000)
                for i in range(3)]
        self.bind_request_rows(c, rows, total=27_000_000)
        result = c.score()
        for rule in ('A1', 'A2'):
            hit = self.hit(result, rows[-1], rule)
            self.assertIsNotNone(hit)
            self.assertEqual(hit['points'], 0)
            self.assertEqual(hit['evidence']['installment_check']['basis'], 'approved_request')
            self.assertEqual(hit['evidence']['installment_check']['cumulative_paid_vnd'], 27_000_000)

    def test_request_cap_and_invoice_cap_are_checked_across_full_history(self):
        for cap, gross in ((18_000_000, 27_000_000), (27_000_000, 18_000_000)):
            with self.subTest(cap=cap, gross=gross):
                c = self.case()
                rows = [c.pay(c.at + timedelta(days=i), invoice_number='INV', invoice_gross_vnd=gross)
                        for i in range(3)]
                self.bind_request_rows(c, rows, total=cap)
                result = c.score()
                self.assertTrue(self.active(result, rows[-1], 'A1'))
                self.assertTrue(self.active(result, rows[-1], 'A2'))
                if gross < 27_000_000:
                    self.assertTrue(self.active(result, rows[-1], 'P1'))

    def test_payment_outside_rule_window_still_consumes_request_cap(self):
        c = self.case()
        rows = [c.pay(c.at-timedelta(days=40), invoice_number='INV', invoice_gross_vnd=27_000_000),
                c.pay(c.at-timedelta(days=1), invoice_number='INV', invoice_gross_vnd=27_000_000),
                c.pay(c.at, invoice_number='INV', invoice_gross_vnd=27_000_000)]
        self.bind_request_rows(c, rows, total=18_000_000)
        self.assertTrue(self.active(c.score(), rows[-1], 'A1'))

    def test_distinct_verified_requests_are_removed_from_current_split_scope(self):
        c = self.case()
        rows = [c.pay(c.at + timedelta(days=i), invoice_number=f'INV{i}', invoice_gross_vnd=9_000_000)
                for i in range(3)]
        for i, row in enumerate(rows):
            self.bind_request_rows(c, [row], request_id=f'REQ{i}', po_id=f'PO{i}', total=9_000_000)
        result = c.score()
        for rule in ('A1', 'A2'):
            hit = self.hit(result, rows[-1], rule)
            self.assertIsNotNone(hit)
            self.assertEqual(hit['points'], 0)
            self.assertTrue(hit['evidence']['excluded_independent_obligations'])

    def test_same_po_with_changed_request_ids_cannot_hide_splitting(self):
        c = self.case()
        rows = [c.pay(c.at + timedelta(days=i), invoice_number=f'INV{i}', invoice_gross_vnd=9_000_000)
                for i in range(3)]
        for i, row in enumerate(rows):
            self.bind_request_rows(c, [row], request_id=f'REQ{i}', po_id='ONE_PO', total=9_000_000)
        result = c.score()
        self.assertTrue(self.active(result, rows[-1], 'A1'))
        self.assertTrue(self.active(result, rows[-1], 'A2'))

    def test_future_revoked_wrong_vendor_or_wrong_recipient_request_does_not_suppress(self):
        for change in ('future', 'revoked', 'vendor', 'recipient'):
            with self.subTest(change=change):
                c = self.case()
                rows = [c.pay(c.at + timedelta(days=i), invoice_number='INV', invoice_gross_vnd=27_000_000)
                        for i in range(3)]
                self.bind_request_rows(c, rows, total=27_000_000)
                request = c.tables['payment_requests'][0]
                if change == 'future':
                    request['observed_at'] = stamp(c.at+timedelta(days=20))
                elif change == 'revoked':
                    request['status'] = 'revoked'
                elif change == 'vendor':
                    request['vendor_id'] = c.tables['vendors'][13]['vendor_id']
                else:
                    request['recipient_account'] = 'BANK_SYN_WRONG'
                self.assertTrue(self.active(c.score(), rows[-1], 'A2'))

    def test_approved_contract_with_typed_invoices_suppresses_but_excess_does_not(self):
        for cap, expected in ((27_000_000, False), (26_000_000, True)):
            with self.subTest(cap=cap):
                c = self.case()
                rows = [c.pay(c.at + timedelta(days=7*i), contract_id='CONTRACT',
                              invoice_number=f'INV{i}', invoice_gross_vnd=9_000_000) for i in range(3)]
                self.agreement(c, cap)
                for row in rows:
                    self.invoice(c, row)
                self.assertEqual(self.active(c.score(), rows[-1], 'A2'), expected)

    def test_multiple_agreements_for_one_contract_do_not_grant_ambiguous_exception(self):
        c = self.case()
        rows = [c.pay(c.at + timedelta(days=7*i), contract_id='CONTRACT',
                      invoice_number=f'INV{i}', invoice_gross_vnd=9_000_000) for i in range(3)]
        self.agreement(c, 27_000_000)
        c.tables['supplier_payment_agreements'].append(dict(c.tables['supplier_payment_agreements'][0],
            agreement_id='AGR_2', evidence_id='EV_AGR_2'))
        for row in rows:
            self.invoice(c, row)
        self.assertTrue(self.active(c.score(), rows[-1], 'A2'))

    def test_a4_uses_exact_recurring_contract_and_period_total(self):
        c = self.case()
        self.recurring(c, pattern='R1', total=17_000_000, contract='C1')
        self.recurring(c, pattern='R2', total=17_000_000, contract='C2')
        rows = [c.pay(c.at+timedelta(days=i), 17_000_000, kind='rent', contract_id=f'C{i+1}')
                for i in range(2)]
        self.recurring(c, pattern='R3', total=17_000_000, contract='C3')
        rows.append(c.pay(c.at+timedelta(days=2), 17_000_000, kind='rent', contract_id='C3'))
        self.assertIsNone(self.hit(c.score(), rows[-1], 'A4'))

    def test_a4_excludes_distinct_approved_requests_but_not_relabelled_same_po(self):
        for same_po, expected in ((False, False), (True, True)):
            with self.subTest(same_po=same_po):
                c = self.case()
                rows = [c.pay(c.at+timedelta(days=i), 17_000_000,
                              invoice_number=f'INV{i}', invoice_gross_vnd=17_000_000) for i in range(3)]
                for i, row in enumerate(rows):
                    self.bind_request_rows(c, [row], request_id=f'REQ{i}',
                                           po_id='ONE_PO' if same_po else f'PO{i}', total=17_000_000)
                self.assertEqual(self.active(c.score(), rows[-1], 'A4'), expected)

    def test_a4_approved_contract_payments_do_not_count_as_near_limit_pattern(self):
        c = self.case()
        rows = [c.pay(c.at+timedelta(days=i), 17_000_000, contract_id='CONTRACT',
                      invoice_number=f'INV{i}', invoice_gross_vnd=17_000_000) for i in range(3)]
        self.agreement(c, 51_000_000)
        for row in rows:
            self.invoice(c, row)
        self.assertIsNone(self.hit(c.score(), rows[-1], 'A4'))

    def test_a4_recurring_cap_cannot_be_reused_by_extra_or_equal_time_payment(self):
        for simultaneous in (False, True):
            with self.subTest(simultaneous=simultaneous):
                c = self.case()
                self.recurring(c, total=17_000_000)
                rows = [c.pay(c.at if simultaneous else c.at+timedelta(days=i), 17_000_000, kind='rent')
                        for i in range(4)]
                target = c.pay(c.at+timedelta(days=1), 17_000_000, kind='rent') if simultaneous else rows[-1]
                hit = self.hit(c.score(), target, 'A4')
                self.assertIsNotNone(hit)
                self.assertGreater(hit['points'], 0)

    def test_quarterly_partial_schedule_excludes_only_authorized_period_total(self):
        c = self.case()
        self.recurring(c, total=51_000_000, frequency='quarterly', allow_partial=1)
        rows = [c.pay(c.at+timedelta(days=i), 17_000_000, kind='rent') for i in range(3)]
        self.assertIsNone(self.hit(c.score(), rows[-1], 'A4'))

    def test_recurring_period_total_resets_at_calendar_boundary(self):
        c = self.case()
        self.recurring(c, total=34_000_000, allow_partial=1)
        rows = [c.pay(c.at.replace(month=8, day=30+i), 17_000_000, kind='rent') for i in range(2)]
        rows.append(c.pay(c.at.replace(month=9, day=1), 17_000_000, kind='rent'))
        self.assertIsNone(self.hit(c.score(), rows[-1], 'A4'))

    def test_request_revocation_applies_only_after_observation(self):
        c = self.case()
        rows = [c.pay(c.at+timedelta(days=i*2), invoice_number='INV', invoice_gross_vnd=27_000_000)
                for i in range(3)]
        self.bind_request_rows(c, rows, total=27_000_000)
        request = c.tables['payment_requests'][0]
        c.tables['payment_requests'].append(dict(request, status='revoked',
            observed_at=stamp(c.at+timedelta(days=3))))
        result = c.score()
        self.assertEqual(self.hit(result, rows[1], 'A1')['points'], 0)
        self.assertTrue(self.active(result, rows[2], 'A2'))

    def test_missing_bound_sources_keeps_existing_alert_behavior(self):
        c = self.case()
        row = c.sequence([9_000_000]*3)
        result = c.score()
        self.assertTrue(self.active(result, row, 'A1'))
        self.assertTrue(self.active(result, row, 'A2'))
        near = c.sequence([17_000_000]*3, kind='cash_expense', start=c.at+timedelta(days=5))
        self.assertTrue(self.active(c.score(), near, 'A4'))

    def test_non_invoice_document_does_not_disable_legacy_installment_exception(self):
        c = self.case()
        row = c.sequence([9_000_000]*3, days=7, invoice_number='INV', invoice_gross_vnd=27_000_000)
        verified, observed = self.source_times(c)
        c.tables['transaction_documents'].append(dict(record_id='DELIVERY', company_id='C001',
            vendor_id=row['vendor_id'], transaction_id=row['transaction_id'],
            document_type='delivery_receipt', invoice_number='', invoice_gross_vnd='',
            status='verified', evidence_id='DELIVERY_DOC', verifier_id=c.director['employee_id'],
            verified_at=verified, observed_at=observed))
        hit = self.hit(c.score(), row, 'A2')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['points'], 0)
        self.assertEqual(hit['evidence']['installment_check']['basis'], 'invoice')

    def test_future_sources_do_not_rewrite_past_results(self):
        c = self.case()
        row = c.sequence([9_000_000]*3, invoice_number='INV', invoice_gross_vnd=27_000_000)
        before = copy.deepcopy(c.score())
        self.request(c, 'REQ', 'PO', 27_000_000, invoice='INV', offset=20)
        for tx in c.rows:
            self.bind(c, tx, 'REQ', 'PO', offset=20)
            self.invoice(c, tx, offset=20)
        self.assertEqual(c.score(), before)


if __name__ == '__main__':
    unittest.main()
