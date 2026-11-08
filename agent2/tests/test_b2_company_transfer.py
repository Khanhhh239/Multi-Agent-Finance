"""Company transfers must update current identity matches without rewriting history."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case


class B2CompanyTransferTest(unittest.TestCase):
    def case(self, fields=('phone',), *, legacy=False, graph=False):
        case = Case()
        case.config = dict(noise_policy='legacy' if legacy else 'phase2',
                           spec_policy='legacy' if legacy else 'phase3', enable_graph=graph)
        case.tables['companies'].append(dict(case.tables['companies'][0], company_id='C002'))
        for source, key in ((case.maker, 'B2_C2_MAKER'), (case.director, 'B2_C2_DIRECTOR')):
            case.tables['employees'].append(dict(source, employee_id=key, company_id='C002'))
        for field in fields:
            token = 'B2_TRANSFER_' + field.upper()
            case.worker[field] = case.vendor[field] = token
        for edge in case.tables['entity_links']:
            if edge['source_id'] in {case.worker['employee_id'], case.vendor['vendor_id']} and edge['link_type'] in fields:
                edge['target_id'] = case.worker[edge['link_type']]
        return case

    def version(self, case, record=None, *, company='C002', days=1, **values):
        revision = dict(record or case.worker, company_id=company,
                        recorded_at=stamp(case.at + timedelta(days=days)), **values)
        case.tables['employees'].append(revision)
        return revision

    def pay_c2(self, case, *, days=2, **values):
        vendor = next((v for v in case.tables['vendors'] if v['vendor_id'] == 'B2_C2_VENDOR'), None)
        if vendor is None:
            vendor = dict(case.vendor, vendor_id='B2_C2_VENDOR', company_id='C002')
            case.tables['vendors'].append(vendor)
        return case.pay(case.at + timedelta(days=days), vendor=vendor, company_id='C002',
                        creator_id='B2_C2_MAKER', approver_id='B2_C2_DIRECTOR', **values)

    def hits(self, result, row, rule='B2'):
        return [h for h in result['hits'] if h['transaction_id'] == row['transaction_id']
                and h['rule_id'] == rule]

    def test_transfer_removes_old_company_phone_and_address_in_both_modes(self):
        for legacy in (False, True):
            for fields in (('phone',), ('address',), ('phone', 'address')):
                with self.subTest(legacy=legacy, fields=fields):
                    case = self.case(fields, legacy=legacy)
                    earlier = case.pay()
                    self.version(case)
                    later = case.pay(case.at + timedelta(days=2))
                    result = case.score()
                    before, = self.hits(result, earlier)
                    self.assertEqual(before['points'], 8 if len(fields) == 2 else 3)
                    self.assertEqual(before['evidence']['direct_matches'],
                                     {field: [case.worker['employee_id']] for field in fields})
                    self.assertEqual(self.hits(result, later), [])

    def test_new_company_gets_current_employee_while_old_company_loses_them(self):
        case = self.case(('phone', 'address'))
        self.version(case)
        old = case.pay(case.at + timedelta(days=2))
        new = self.pay_c2(case)
        result = case.score()
        self.assertEqual(self.hits(result, old), [])
        hit, = self.hits(result, new)
        self.assertEqual(hit['evidence']['direct_matches'],
                         {field: [case.worker['employee_id']] for field in ('phone', 'address')})

    def test_transfer_applies_at_cutoff_to_every_payment_in_the_batch(self):
        case = self.case()
        cutoff = case.at + timedelta(days=1)
        earlier = case.pay(cutoff - timedelta(seconds=1))
        self.version(case)
        at_cutoff = [case.pay(cutoff), case.pay(cutoff)]
        result = case.score()
        self.assertEqual(self.hits(result, earlier)[0]['points'], 3)
        for row in at_cutoff:
            self.assertEqual(self.hits(result, row), [])

    def test_future_transfer_does_not_rewrite_historical_scores_or_hits(self):
        case = self.case(graph=True)
        earlier = case.pay()
        before = copy.deepcopy(case.score())
        self.version(case)
        later = case.pay(case.at + timedelta(days=2))
        after = case.score()
        self.assertEqual(before['scores'], [r for r in after['scores']
                                           if r['posted_at'] <= earlier['posted_at']])
        self.assertEqual(before['hits'], [h for h in after['hits']
                                         if h['detected_at'] <= earlier['posted_at']])
        self.assertTrue(self.hits(after, earlier)[0]['graph_path'])
        self.assertEqual(self.hits(after, later), [])

    def test_departing_employee_does_not_remove_another_current_employee(self):
        case = self.case()
        remaining = case.tables['employees'][11]
        remaining['phone'] = case.worker['phone']
        earlier = case.pay()
        self.version(case)
        later = case.pay(case.at + timedelta(days=2))
        result = case.score()
        self.assertEqual(self.hits(result, earlier)[0]['evidence']['direct_matches']['phone'],
                         sorted([case.worker['employee_id'], remaining['employee_id']]))
        hit, = self.hits(result, later)
        self.assertEqual(hit['points'], 3)
        self.assertEqual(hit['evidence']['direct_matches'], {'phone': [remaining['employee_id']]})

    def test_transfer_back_restores_only_the_current_company_match(self):
        case = self.case()
        first = case.pay()
        moved = self.version(case)
        old_during_move = case.pay(case.at + timedelta(days=2))
        new_during_move = self.pay_c2(case)
        self.version(case, moved, company='C001', days=3)
        returned = case.pay(case.at + timedelta(days=4))
        previous_company = self.pay_c2(case, days=4)
        result = case.score()
        for row in (first, new_during_move, returned):
            self.assertEqual(self.hits(result, row)[0]['points'], 3)
        for row in (old_during_move, previous_company):
            self.assertEqual(self.hits(result, row), [])

    def test_transfer_with_changed_contacts_leaves_no_old_company_match(self):
        case = self.case(('phone', 'address'))
        self.version(case, phone='B2_NEW_PHONE', address='B2_NEW_ADDRESS')
        old = case.pay(case.at + timedelta(days=2))
        new_company = self.pay_c2(case)
        new_vendor = next(v for v in case.tables['vendors'] if v['vendor_id'] == 'B2_C2_VENDOR')
        new_vendor.update(phone='B2_NEW_PHONE', address='B2_NEW_ADDRESS')
        result = case.score()
        self.assertEqual(self.hits(result, old), [])
        hit, = self.hits(result, new_company)
        self.assertEqual(set(hit['evidence']['direct_matches']), {'phone', 'address'})

    def test_same_company_replacement_or_clear_still_removes_old_contacts(self):
        for replacement in ('B2_REPLACEMENT', ''):
            with self.subTest(replacement=replacement):
                case = self.case(('phone', 'address'))
                earlier = case.pay()
                self.version(case, company='C001', phone=replacement, address=replacement)
                later = case.pay(case.at + timedelta(days=2))
                result = case.score()
                self.assertTrue(self.hits(result, earlier))
                self.assertEqual(self.hits(result, later), [])

    def test_shared_index_also_retires_legacy_bank_and_national_id_on_transfer(self):
        for field in ('bank_account', 'national_id'):
            with self.subTest(field=field):
                case = self.case((field,), legacy=True)
                first = case.pay(recipient_account=case.worker['bank_account'])
                self.version(case)
                old = case.pay(case.at + timedelta(days=2), recipient_account=case.worker['bank_account'])
                new = self.pay_c2(case, recipient_account=case.worker['bank_account'])
                result = case.score()
                self.assertEqual(self.hits(result, first, 'B1')[0]['evidence']['employee_ids'],
                                 [case.worker['employee_id']])
                self.assertEqual(self.hits(result, old, 'B1'), [])
                self.assertEqual(self.hits(result, new, 'B1')[0]['evidence']['employee_ids'],
                                 [case.worker['employee_id']])

    def bridge_case(self):
        case = self.case(graph=True)
        remaining = case.tables['employees'][11]
        remaining.update(bank_account=case.worker['bank_account'],
                         bank_code=case.worker.get('bank_code', ''))
        for edge in case.tables['entity_links']:
            if edge['source_id'] == remaining['employee_id'] and edge['link_type'] == 'bank_account':
                edge['target_id'] = remaining['bank_account']
        return case

    def test_transferred_employee_cannot_bridge_old_company_graph_to_current_staff(self):
        case = self.bridge_case()
        earlier = case.pay()
        before = copy.deepcopy(case.score())
        self.version(case)
        later = case.pay(case.at + timedelta(days=2))
        after = case.score()
        self.assertEqual(self.hits(before, earlier)[0]['points'], 8)
        self.assertEqual(self.hits(before, earlier), self.hits(after, earlier))
        self.assertEqual(self.hits(after, later), [])

    def test_old_company_mirror_at_transfer_time_cannot_restore_departed_staff_edges(self):
        case = self.bridge_case()
        self.version(case)
        for field in ('phone', 'bank_account'):
            case.tables['entity_links'].append(dict(company_id='C001', source_id=case.worker['employee_id'],
                target_id=case.worker[field], link_type=field,
                observed_at=stamp(case.at + timedelta(days=1))))
        later = case.pay(case.at + timedelta(days=2))
        self.assertEqual(self.hits(case.score(), later), [])

    def test_transfer_keeps_independent_graph_match_to_remaining_employee(self):
        case = self.case(graph=True)
        remaining = case.tables['employees'][11]
        remaining['phone'] = case.worker['phone']
        self.version(case)
        later = case.pay(case.at + timedelta(days=2))
        hit, = self.hits(case.score(), later)
        self.assertEqual(hit['points'], 8)
        self.assertEqual(hit['evidence']['direct_matches'], {'phone': [remaining['employee_id']]})
        self.assertTrue(hit['graph_path'])
        self.assertFalse(any(edge['source'] == 'entity:' + case.worker['employee_id']
                             or edge['target'] == 'entity:' + case.worker['employee_id']
                             for edge in hit['graph_path']))
