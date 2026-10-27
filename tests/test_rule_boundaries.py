"""Previously uncovered business edges, using raw sources and current defaults."""
import copy
import json
import unittest
from datetime import timedelta

from sme_fraud.case_queue import review_queue
from sme_fraud.generate import stamp
from sme_fraud.features import build_features
from sme_fraud.evidence_cases import prepare, decision
from sme_fraud.rules import score_rules
from rule_matrix_cases import advance_case, advance_event, current_case, target_hits


class RuleBoundaryTest(unittest.TestCase):
    def hit(self, case, row, code):
        return target_hits(case.score(), row, code)

    def test_a1_total_equality_and_one_dong_below(self):
        for total, active in ((16_999_999, False), (17_000_000, True)):
            with self.subTest(total=total):
                c = current_case()
                row = c.sequence([8_000_000, total - 8_000_000])
                self.assertEqual(bool(self.hit(c, row, 'A1')), active)

    def test_a2_total_equality_and_one_dong_below(self):
        for total, active in ((19_999_999, False), (20_000_000, True)):
            with self.subTest(total=total):
                c = current_case()
                row = c.sequence([6_000_000, 6_000_000, total - 12_000_000], days=7)
                self.assertEqual(bool(self.hit(c, row, 'A2')), active)

    def test_a2_thirty_day_window_includes_exact_second_and_excludes_next(self):
        for extra, active in ((0, True), (1, False)):
            c = current_case()
            c.pay(c.at - timedelta(days=30), 7_000_000)
            c.pay(c.at - timedelta(days=15), 7_000_000)
            row = c.pay(c.at + timedelta(seconds=extra), 7_000_000)
            self.assertEqual(bool(self.hit(c, row, 'A2')), active)

    def test_a3_long_window_and_total_boundaries(self):
        for extra, total, active in ((0, 20_000_000, True), (1, 20_000_000, False), (0, 19_999_999, False)):
            c = current_case()
            vendors = c.shared_vendors()
            c.pay(c.at - timedelta(days=30), 6_000_000, vendor=vendors[0])
            c.pay(c.at - timedelta(days=15), 6_000_000, vendor=vendors[1])
            row = c.pay(c.at + timedelta(seconds=extra), total - 12_000_000, vendor=vendors[2])
            self.assertEqual(bool(self.hit(c, row, 'A3')), active)

    def test_a4_near_limit_interval_is_inclusive(self):
        for amount, active in ((15_999_999, False), (16_000_000, True), (19_800_000, True), (19_800_001, False)):
            with self.subTest(amount=amount):
                c = current_case()
                row = c.sequence([amount] * 3, kind='cash_expense')
                self.assertEqual(bool(self.hit(c, row, 'A4')), active)

    def test_a6_one_dong_tolerance_and_rounding_eligibility(self):
        for amount, gross, active in ((2_001_000, 2_000_999, False), (2_001_000, 2_000_998, True),
                                      (2_001_001, 1_990_007, False), (2_001_000, 1_990_000, False)):
            c = current_case()
            row = c.pay(amount=amount, invoice_gross_vnd=gross)
            self.assertEqual(bool(self.hit(c, row, 'A6')), active)

    def test_a6_missing_invoice_total_is_unknown_not_overpayment(self):
        c = current_case()
        row = c.pay(amount=2_001_000, invoice_gross_vnd=1_990_007)
        c.score()  # Build ordinary ledger once, then present a missing source header.
        row['invoice_gross_vnd'] = 0
        result = score_rules(c.tables, features=build_features(c.tables), config=c.config)
        self.assertEqual(target_hits(result, row, 'A6'), [])

    def test_a6_invoice_date_and_observation_must_not_be_after_cutoff(self):
        for field in ('invoice_issued_at', 'invoice_observed_at'):
            for offset, active in ((-1, True), (0, True), (1, False)):
                with self.subTest(field=field, offset=offset):
                    c = current_case()
                    row = c.pay(amount=2_001_000, invoice_gross_vnd=1_990_007,
                                **{field: stamp(c.at + timedelta(seconds=offset))})
                    result = c.score()
                    self.assertEqual(bool(target_hits(result, row, 'A6')), active)
                    if not active:
                        queue, _ = review_queue(result, c.tables)
                        self.assertFalse(any('A6' in q['rule_ids'].split('|') for q in queue))

    def test_b3_age_and_large_payment_boundaries(self):
        for age, amount, active in ((89, 20_000_000, True), (90, 20_000_000, False),
                                     (89, 19_999_999, False), (-1, 20_000_000, False)):
            c = current_case()
            c.new_vendor()
            c.vendor['registered_at'] = stamp(c.at - timedelta(days=age))
            row = c.pay(amount=amount)
            self.assertEqual(bool(self.hit(c, row, 'B3')), active)

    def test_b3_future_fulfilment_document_cannot_clear_current_finding(self):
        from test_noise_policy import NoisePolicyTest
        for late, suppressed in ((False, True), (True, False)):
            c = current_case()
            c.new_vendor()
            row = c.pay(amount=50_000_000)
            for i, kind in enumerate(('invoice', 'purchase_order', 'goods_receipt')):
                record = NoisePolicyTest().proof(c, record_id=f'MATRIX_DOC{i}',
                    transaction_id=row['transaction_id'], vendor_id=row['vendor_id'], document_type=kind)
                if late and kind == 'goods_receipt':
                    record['observed_at'] = stamp(c.at + timedelta(days=1))
                c.tables['transaction_documents'].append(record)
            hit, = self.hit(c, row, 'B3')
            self.assertEqual(bool(hit['suppressed_reason']), suppressed)

    def test_b2_blank_contacts_are_not_employee_relationships(self):
        c = current_case()
        for table in ('employees', 'vendors'):
            for record in c.tables[table]:
                record.update(phone='', address='')
        row = c.pay()
        self.assertEqual(self.hit(c, row, 'B2'), [])

    def test_b2_disclosure_cutoff_is_inclusive(self):
        for offset, suppressed in ((-1, True), (0, True), (1, False)):
            c = current_case()
            c.vendor.update(phone=c.worker['phone'], related_party_disclosed_at=stamp(c.at + timedelta(seconds=offset)))
            row = c.pay()
            hit, = self.hit(c, row, 'B2')
            self.assertEqual(bool(hit['suppressed_reason']), suppressed)
            self.assertEqual(hit['points'] == 0, suppressed)

    def test_b6_idle_day_and_prior_p90_boundaries(self):
        for idle, amount, active in ((179, 1_000_001, False), (180, 1_000_001, True), (180, 1_000_000, False)):
            c = current_case()
            c.sequence([1_000_000] * 20, start=c.at - timedelta(days=idle + 19))
            row = c.pay(amount=amount)
            self.assertEqual(bool(self.hit(c, row, 'B6')), active)

    def test_b6_insufficient_history_does_not_invent_percentile(self):
        c = current_case()
        c.sequence([1_000_000] * 19, start=c.at - timedelta(days=200))
        row = c.pay(amount=5_000_000)
        self.assertEqual(self.hit(c, row, 'B6'), [])

    def test_c1_working_hour_boundaries_check_both_actions(self):
        for hour, minute, active in ((7, 59, True), (8, 0, False), (18, 59, False), (19, 0, True)):
            c = current_case()
            at = c.at.replace(hour=hour, minute=minute)
            row = c.pay(at=at, created_at=stamp(at), approved_at=stamp(at))
            self.assertEqual(bool(self.hit(c, row, 'C1')), active)

    def test_c3_fifty_nine_seconds_is_fast_sixty_is_not(self):
        for seconds, active in ((0, True), (59, True), (60, False), (61, False)):
            c = current_case()
            row = c.pay(amount=50_000_000, created_at=stamp(c.at - timedelta(seconds=seconds)), approved_at=stamp(c.at))
            self.assertEqual(bool(self.hit(c, row, 'C3')), active)

    def test_c3_amount_proxy_is_inclusive_at_fifty_million(self):
        for amount, active in ((49_999_999, False), (50_000_000, True)):
            c = current_case()
            row = c.pay(amount=amount, created_at=stamp(c.at - timedelta(seconds=1)), approved_at=stamp(c.at))
            self.assertEqual(bool(self.hit(c, row, 'C3')), active)

    def test_b5_e4_current_master_contact_replacement_removes_duplicate(self):
        c = current_case()
        other = c.tables['vendors'][13]
        other['phone'] = c.vendor['phone']
        first = c.pay()
        changed = {**c.vendor, 'recorded_at': stamp(c.at + timedelta(days=1)), 'phone': 'PHONE_SYN_MATRIX_REPLACED'}
        c.tables['vendors'].append(changed)
        second = c.pay(c.at + timedelta(days=2))
        result = c.score()
        for code in ('B5', 'E4'):
            self.assertTrue(target_hits(result, first, code))
            self.assertEqual(target_hits(result, second, code), [])

    def test_e3_current_master_name_change_removes_old_similarity(self):
        c = current_case()
        c.tables['vendors'] = c.tables['vendors'][12:14]
        c.tables['vendors'][0]['name'] = 'ABC Co., Ltd'
        other = c.tables['vendors'][1]
        other['name'] = 'A.B.C Co Ltd'
        first = c.pay()
        c.tables['vendors'].append({**other, 'name': 'ZETA MANUFACTURING', 'recorded_at': stamp(c.at + timedelta(days=1))})
        second = c.pay(c.at + timedelta(days=2))
        result = c.score()
        self.assertTrue(target_hits(result, first, 'E3'))
        self.assertEqual(target_hits(result, second, 'E3'), [])

    def test_b2_one_vs_two_direct_contacts_changes_strength_and_queue(self):
        for fields, points, admitted in ((1, 3, 0), (2, 8, 1)):
            c = current_case()
            c.config['enable_graph'] = False
            c.vendor['phone'] = c.worker['phone']
            if fields == 2:
                c.vendor['address'] = c.worker['address']
            row = c.pay()
            result = c.score()
            hit, = target_hits(result, row, 'B2')
            self.assertEqual(hit['points'], points)
            self.assertEqual(result['scores'][0]['operational_alert'], admitted)
            queue, _ = review_queue(result, c.tables)
            self.assertEqual(len(queue), admitted)

    def test_b5_e4_blank_identifiers_do_not_create_master_duplicates(self):
        c = current_case()
        for vendor in c.tables['vendors']:
            vendor.update(phone='', address='')
        row = c.pay()
        result = c.score()
        for code in ('B5', 'E4'):
            self.assertEqual(target_hits(result, row, code), [])

    def test_e3_similarity_must_strictly_exceed_threshold(self):
        for threshold, matched in ((0.87499999, True), (0.875, False), (0.87500001, False)):
            c = current_case()
            c.config['fuzzy_similarity'] = threshold
            c.tables['vendors'] = c.tables['vendors'][12:14]
            c.tables['vendors'][0]['name'] = 'ABCDEFGH'
            c.tables['vendors'][1]['name'] = 'ABCXEFGH'  # Seven of eight distinctive letters agree.
            row = c.pay()
            self.assertEqual(bool(self.hit(c, row, 'E3')), matched)

    def test_e2_termination_day_is_not_confirmed_post_termination_service(self):
        for start, confirmed in (('2025-08-31', False), ('2025-09-01', True)):
            c, row, _, scope = prepare('E2', 'positive', 20261027)
            c.tables['payroll_settlements'][0]['service_period_start'] = start
            result = c.score()
            self.assertEqual(decision(result, 'E2', row, scope) is True, confirmed)
            self.assertEqual(any(h['hard_trigger'] for h in target_hits(result, row, 'E2')), confirmed)

    def test_e1_zero_vs_one_observed_work_day(self):
        for days, active in ((0, True), (1, False)):
            c = current_case()
            row = c.attendance()
            for record in c.tables['attendance']:
                if record['employee_id'] == c.worker['employee_id'] and record['payroll_period'] == row['payroll_period']:
                    record['days_worked_observed'] = days
            self.assertEqual(bool(self.hit(c, row, 'E1')), active)

    def test_p1_cumulative_total_has_one_dong_tolerance(self):
        for last_amount, active in ((500_000, False), (500_001, False), (500_002, True)):
            c = current_case()
            c.pay(amount=500_000, invoice_number='MATRIX_TOLERANCE', invoice_gross_vnd=1_000_000)
            row = c.pay(c.at + timedelta(days=1), last_amount, invoice_number='MATRIX_TOLERANCE', invoice_gross_vnd=1_000_000)
            hits = self.hit(c, row, 'P1')
            self.assertEqual(bool(hits), active)
            if active:
                self.assertEqual(hits[0]['hard_trigger'], 1)

    def test_f2_approved_override_cap_is_inclusive(self):
        for amount, active in ((20_000_000, False), (20_000_001, True)):
            c, row, _, scope = prepare('F2', 'authorized', 20261027)
            row.update(amount_vnd=amount, invoice_gross_vnd=amount)
            self.assertEqual(decision(c.score(), 'F2', row, scope), active)

    def test_f3_series_closed_at_cutoff_is_available_but_next_second_is_not(self):
        for offset, active in ((0, True), (1, None)):
            c, row, _, scope = prepare('F3', 'positive', 20261027)
            c.tables['document_series'][0]['closed_at'] = stamp(c.at + timedelta(seconds=offset))
            self.assertIs(decision(c.score(), 'F3', row, scope), active)

    def test_f4_sixty_days_is_not_overdue_signal_sixty_one_is(self):
        for days, active in ((60, False), (61, True)):
            c, row, _, scope = prepare('F4', 'positive', 20261027)
            c.tables['receivable_invoices'][0]['due_at'] = stamp(c.at - timedelta(days=days))
            result = c.score()
            self.assertIs(decision(result, 'F4', row, scope), active)
            queue, _ = review_queue(result, c.tables)
            self.assertEqual(any(q.get('source_scope') == scope for q in queue), active)

    def test_t1_due_and_grace_are_strict_whole_days(self):
        for days, grace, active in ((0, 0, False), (1, 0, True), (3, 3, False), (4, 3, True)):
            c, row = advance_case(overdue_days=days, grace=grace)
            self.assertEqual(bool(self.hit(c, row, 'T1')), active)

    def test_t1_only_known_extension_can_defer_review(self):
        for seconds, active in ((-1, False), (1, True)):
            c, row = advance_case()
            advance_event(c, row, 'extension', observed=c.at + timedelta(seconds=seconds), due=c.at + timedelta(days=10))
            self.assertEqual(bool(self.hit(c, row, 'T1')), active)

    def test_t1_settlement_preserves_own_pre_event_balance(self):
        c, row = advance_case()
        advance_event(c, row, 'settlement', observed=c.at, amount=5_000_000)
        before = c.score()
        self.assertTrue(target_hits(before, row, 'T1'))
        later = c.pay(c.at + timedelta(seconds=1), 5_000_000, kind='advance_review', advance_id=row['advance_id'])
        result = c.score()
        self.assertTrue(target_hits(result, row, 'T1'))
        self.assertEqual(target_hits(result, later, 'T1'), [])

    def test_t1_partial_settlement_keeps_remaining_balance_actionable(self):
        c, row = advance_case()
        advance_event(c, row, 'settlement', amount=4_999_999)
        hits = self.hit(c, row, 'T1')
        self.assertEqual(len(hits), 1)
        self.assertGreater(hits[0]['evidence']['open_fraction'], 0)

    def test_t1_missing_advance_record_does_not_invent_debt(self):
        c, row = advance_case()
        c.tables['advances'] = []
        self.assertEqual(self.hit(c, row, 'T1'), [])

    def test_t2_writeoff_evidence_and_transaction_type(self):
        for writeoff, evidence, active in ((True, 0, True), (True, 1, False), (False, 0, False)):
            c, row = advance_case(writeoff=writeoff, evidence=evidence)
            hits = self.hit(c, row, 'T2')
            self.assertEqual(bool(hits), active)
            if hits:
                self.assertEqual((hits[0]['points'], hits[0]['hard_trigger']), (20, 1))

    def test_t2_writeoff_does_not_close_its_own_pre_event_balance(self):
        c, row = advance_case(writeoff=True)
        result = c.score()
        hit, = target_hits(result, row, 'T2')
        self.assertEqual(hit['evidence']['prior_balance_fraction'], 1)
        self.assertTrue(target_hits(result, row, 'T1'))

    def test_t1_t2_writeoff_documents_are_known_at_cutoff_or_remain_actionable(self):
        for offset, actionable in ((-1, False), (0, False), (1, True)):
            c, row = advance_case(writeoff=True, evidence=1)
            row['support_docs_observed_at'] = stamp(c.at + timedelta(seconds=offset))
            result = c.score()
            for code in ('T1', 'T2'):
                active = [h for h in target_hits(result, row, code) if h['points'] > 0]
                self.assertEqual(bool(active), actionable, (code, offset))
            if actionable:
                queue, _ = review_queue(result, c.tables)
                bound = [q for q in queue if row['transaction_id'] in json.loads(q['transaction_ids'])]
                self.assertEqual(len(bound), 1)
                self.assertEqual(bound[0]['priority'], 'cao_nhat')

    def test_t2_future_document_flag_change_cannot_reduce_past_warning(self):
        c, row = advance_case(writeoff=True, evidence=0)
        row['support_docs_observed_at'] = stamp(c.at + timedelta(days=2))
        before = c.score()
        row.update(evidence_on_file=1, support_doc_count=2)
        c.tables['advance_events'][0]['evidence_on_file'] = 1
        after = c.score()
        for code in ('T1', 'T2'):
            self.assertEqual(target_hits(before, row, code), target_hits(after, row, code))

    def test_t2_writeoff_source_event_must_be_observed_before_using_its_proof(self):
        for offset, active in ((-1, False), (0, False), (1, True)):
            c, row = advance_case(writeoff=True, evidence=1)
            c.tables['advance_events'][0]['observed_at'] = stamp(c.at + timedelta(seconds=offset))
            self.assertNotIn('support_docs_observed_at', row)
            result = c.score()
            self.assertEqual(bool(target_hits(result, row, 'T2')), active)
            if active:
                self.assertTrue(any(h['points'] > 0 for h in target_hits(result, row, 'T1')))

    def test_t2_writeoff_source_for_another_company_or_advance_cannot_exempt(self):
        for field, value in (('company_id', 'C_OTHER'), ('advance_id', 'OTHER_ADVANCE')):
            c, row = advance_case(writeoff=True, evidence=1)
            c.tables['advance_events'][0][field] = value
            hit, = self.hit(c, row, 'T2')
            self.assertEqual((hit['points'], hit['hard_trigger']), (20, 1))

    def test_t2_future_source_append_cannot_change_an_undated_header_decision(self):
        c, row = advance_case(writeoff=True, evidence=1)
        c.tables['advance_events'] = []
        before = c.score()
        event = advance_event(c, row, 'writeoff', observed=c.at + timedelta(days=1), amount=5_000_000)
        event['transaction_id'] = row['transaction_id']
        after = c.score()
        self.assertEqual(before['scores'], after['scores'])
        self.assertEqual(before['hits'], after['hits'])
        self.assertTrue(target_hits(after, row, 'T2'))

    def test_t2_dated_header_can_support_writeoff_without_a_separate_event(self):
        c, row = advance_case(writeoff=True, evidence=1)
        c.tables['advance_events'] = []
        row['support_docs_observed_at'] = stamp(c.at)
        self.assertEqual(self.hit(c, row, 'T2'), [])


if __name__ == '__main__':
    unittest.main()
