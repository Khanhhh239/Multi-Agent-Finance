"""Temporal regressions for changing identities, through the real A3/B2 engine."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import KnownGraph


class GraphHistoryTest(unittest.TestCase):
    def case(self):
        case = Case()
        case.config = {'noise_policy': 'phase2', 'spec_policy': 'phase3'}
        return case

    def hit(self, result, row, rule):
        return next((h for h in result['hits'] if h['transaction_id'] == row['transaction_id']
                     and h['rule_id'] == rule), None)

    def version(self, case, record, at, **values):
        updated = dict(record, recorded_at=stamp(at), **values)
        table = 'vendors' if 'vendor_id' in record else 'employees'
        case.tables[table].append(updated)
        return updated

    def mirror(self, case, record, field):
        key = record.get('vendor_id') or record['employee_id']
        for edge in case.tables['entity_links']:
            if edge['source_id'] == key and edge['link_type'] == field:
                edge['target_id'] = record[field]

    def test_vendor_phone_replacement_and_clear_retire_mirrored_links(self):
        for replacement in ('PHONE_SYN_NEW', ''):
            with self.subTest(replacement=replacement):
                c = self.case()
                c.vendor['phone'] = c.worker['phone']
                self.mirror(c, c.vendor, 'phone')
                first = c.pay()
                self.version(c, c.vendor, c.at + timedelta(days=1), phone=replacement)
                second = c.pay(c.at + timedelta(days=2))
                result = c.score()
                self.assertIsNotNone(self.hit(result, first, 'B2'))
                self.assertIsNone(self.hit(result, second, 'B2'))

    def test_employee_changes_retire_old_bank_and_phone(self):
        c = self.case()
        c.vendor.update(phone=c.worker['phone'], bank_account=c.worker['bank_account'])
        for field in ('phone', 'bank_account'):
            self.mirror(c, c.vendor, field)
        first = c.pay()
        self.version(c, c.worker, c.at + timedelta(days=1), phone='PHONE_SYN_NEW', bank_account='BANK_SYN_NEW')
        second = c.pay(c.at + timedelta(days=2))
        result = c.score()
        self.assertIsNotNone(self.hit(result, first, 'B2'))
        self.assertIsNone(self.hit(result, second, 'B2'))

    def test_a3_short_component_splits_after_master_change(self):
        c = self.case()
        vendors = c.shared_vendors()[:2]
        for vendor in vendors:
            self.mirror(c, vendor, 'phone')
        c.pay(vendor=vendors[0])
        linked = c.pay(c.at + timedelta(days=1), vendor=vendors[1])
        self.version(c, vendors[1], c.at + timedelta(days=2), phone='PHONE_SYN_SEPARATE')
        separate = c.pay(c.at + timedelta(days=3), vendor=vendors[1])
        result = c.score()
        self.assertIsNotNone(self.hit(result, linked, 'A3'))
        self.assertIsNone(self.hit(result, separate, 'A3'))

    def test_a3_long_window_excludes_payments_of_disconnected_vendor(self):
        c = self.case()
        vendors = c.shared_vendors()
        c.pay(vendor=vendors[0])
        c.pay(c.at + timedelta(days=10), vendor=vendors[1])
        self.version(c, vendors[0], c.at + timedelta(days=11), phone='PHONE_SYN_SEPARATE')
        last = c.pay(c.at + timedelta(days=20), vendor=vendors[2])
        self.assertIsNone(self.hit(c.score(), last, 'A3'))

    def test_bank_code_change_splits_identical_account_numbers(self):
        c = self.case()
        vendors = c.tables['vendors'][12:14]
        for vendor in vendors:
            vendor.update(bank_account='001234567', bank_code='BANK_A')
            self.mirror(c, vendor, 'bank_account')
        c.pay(vendor=vendors[0])
        linked = c.pay(c.at + timedelta(days=1), vendor=vendors[1])
        self.version(c, vendors[1], c.at + timedelta(days=2), bank_code='BANK_B')
        separate = c.pay(c.at + timedelta(days=3), vendor=vendors[1])
        result = c.score()
        self.assertIsNotNone(self.hit(result, linked, 'A3'))
        self.assertIsNone(self.hit(result, separate, 'A3'))

    def test_representative_replacement_and_clear_remove_old_two_hop_path(self):
        for replacement in ('REP_NEW', ''):
            with self.subTest(replacement=replacement):
                c = self.case()
                representative = c.vendor['representative_id']
                for edge in c.tables['entity_links']:
                    if edge['source_id'] == representative and edge['link_type'] == 'phone':
                        edge['target_id'] = c.worker['phone']
                first = c.pay()
                self.version(c, c.vendor, c.at + timedelta(days=1), representative_id=replacement)
                second = c.pay(c.at + timedelta(days=2))
                result = c.score()
                self.assertTrue(self.hit(result, first, 'B2')['graph_path'])
                self.assertIsNone(self.hit(result, second, 'B2'))

    def test_removing_phone_does_not_remove_independent_bank_evidence(self):
        c = self.case()
        c.vendor.update(phone=c.worker['phone'], bank_account=c.worker['bank_account'])
        first = c.pay()
        self.version(c, c.vendor, c.at + timedelta(days=1), phone='')
        second = c.pay(c.at + timedelta(days=2))
        result = c.score()
        self.assertIsNotNone(self.hit(result, first, 'B2'))
        hit = self.hit(result, second, 'B2')
        self.assertIsNotNone(hit)
        self.assertTrue(hit['graph_path'])
        self.assertTrue(all(e['link_type'] == 'bank_account' for e in hit['graph_path']))

    def test_non_master_contact_replacement_and_revocation_are_as_of(self):
        for status, target in [('active', 'PHONE_SYN_OTHER'), ('revoked', '')]:
            with self.subTest(status=status):
                c = self.case()
                representative = c.vendor['representative_id']
                for edge in c.tables['entity_links']:
                    if edge['source_id'] == representative and edge['link_type'] == 'phone':
                        edge['target_id'] = c.worker['phone']
                first = c.pay()
                c.tables['entity_links'].append(dict(company_id='C001', source_id=representative,
                    target_id=target, link_type='phone', status=status,
                    observed_at=stamp(c.at + timedelta(days=1))))
                second = c.pay(c.at + timedelta(days=2))
                result = c.score()
                self.assertIsNotNone(self.hit(result, first, 'B2'))
                self.assertIsNone(self.hit(result, second, 'B2'))

    def test_future_master_and_link_versions_preserve_past_scores_hits_and_paths(self):
        c = self.case()
        c.vendor['phone'] = c.worker['phone']
        first = c.pay()
        before = copy.deepcopy(c.score())
        self.version(c, c.vendor, c.at + timedelta(days=1), phone='')
        c.tables['entity_links'].append(dict(company_id='C001', source_id=c.vendor['representative_id'],
            target_id=c.worker['phone'], link_type='phone', status='revoked',
            observed_at=stamp(c.at + timedelta(days=2))))
        c.pay(c.at + timedelta(days=3))
        after = c.score()
        self.assertEqual(before['scores'], [r for r in after['scores'] if r['posted_at'] <= first['posted_at']])
        self.assertEqual(before['hits'], [r for r in after['hits'] if r['detected_at'] <= first['posted_at']])
        self.assertTrue(all(edge['observed_at'] <= hit['detected_at']
                            for hit in after['hits'] for edge in hit['graph_path']))

    def test_clear_at_transaction_timestamp_applies_to_entire_batch(self):
        c = self.case()
        c.vendor['phone'] = c.worker['phone']
        first = c.pay()
        cutoff = c.at + timedelta(days=1)
        self.version(c, c.vendor, cutoff, phone='')
        second, third = c.pay(cutoff), c.pay(cutoff)
        result = c.score()
        self.assertIsNotNone(self.hit(result, first, 'B2'))
        self.assertIsNone(self.hit(result, second, 'B2'))
        self.assertIsNone(self.hit(result, third, 'B2'))

    def test_later_reactivation_is_valid_without_rewriting_revoked_period(self):
        c = self.case()
        c.vendor['phone'] = c.worker['phone']
        first = c.pay()
        cleared = self.version(c, c.vendor, c.at + timedelta(days=1), phone='')
        second = c.pay(c.at + timedelta(days=2))
        self.version(c, cleared, c.at + timedelta(days=3), phone=c.worker['phone'])
        third = c.pay(c.at + timedelta(days=4))
        result = c.score()
        self.assertIsNotNone(self.hit(result, first, 'B2'))
        self.assertIsNone(self.hit(result, second, 'B2'))
        self.assertIsNotNone(self.hit(result, third, 'B2'))

    def test_master_tombstone_wins_equal_time_mirror_in_either_order(self):
        for master_first in (True, False):
            graph = KnownGraph()
            records = [('', True), ('phone:OLD', False)]
            if not master_first:
                records.reverse()
            for target, master in records:
                graph.replace('C001', 'entity:V', target, '2025-01-02', 'phone', master=master)
            graph.replace('C001', 'entity:E', 'phone:OLD', '2025-01-01', 'phone', master=True)
            # Delayed processing of an older stream item cannot undo the clear.
            graph.replace('C001', 'entity:V', 'phone:OLD', '2025-01-01', 'phone')
            self.assertEqual(graph.path('C001', 'entity:V', {'entity:E'}), [])
            self.assertNotEqual(graph.group('C001').root('entity:V'), graph.group('C001').root('entity:E'))

    def test_company_scope_prevents_shared_tokens_and_revocations_crossing_companies(self):
        graph = KnownGraph()
        for cid in ('C001', 'C002'):
            for entity in ('entity:V', 'entity:E'):
                graph.replace(cid, entity, 'phone:SHARED', '2025-01-01', 'phone')
        graph.replace('C001', 'entity:V', '', '2025-01-02', 'phone')
        self.assertFalse(graph.path('C001', 'entity:V', {'entity:E'}))
        self.assertTrue(graph.path('C002', 'entity:V', {'entity:E'}))

    def test_conflicting_equal_time_sources_do_not_depend_on_input_order(self):
        for targets in [('phone:A', 'phone:B'), ('phone:B', 'phone:A')]:
            graph = KnownGraph()
            graph.replace('C001', 'entity:V', targets[0], '2025-01-01', 'phone')
            with self.assertRaisesRegex(ValueError, 'Conflicting graph identity'):
                graph.replace('C001', 'entity:V', targets[1], '2025-01-01', 'phone')

    def test_revocation_of_old_target_does_not_cancel_replacement(self):
        c = self.case()
        representative = c.vendor['representative_id']
        original = next(e for e in c.tables['entity_links']
                        if e['source_id'] == representative and e['link_type'] == 'phone')
        c.tables['entity_links'].append(dict(original, target_id=c.worker['phone'],
            observed_at=stamp(c.at - timedelta(days=1))))
        first = c.pay()
        c.tables['entity_links'].append(dict(original, status='revoked', observed_at=stamp(c.at + timedelta(days=1))))
        second = c.pay(c.at + timedelta(days=2))
        c.tables['entity_links'].append(dict(original, target_id=c.worker['phone'], status='revoked',
            observed_at=stamp(c.at + timedelta(days=3))))
        third = c.pay(c.at + timedelta(days=4))
        result = c.score()
        self.assertIsNotNone(self.hit(result, first, 'B2'))
        self.assertIsNotNone(self.hit(result, second, 'B2'))
        self.assertIsNone(self.hit(result, third, 'B2'))

    def test_ambiguous_bank_revocation_cannot_cancel_verified_institution(self):
        c = self.case()
        representative = c.vendor['representative_id']
        c.worker.update(bank_account='001234567', bank_code='BANK_A')
        original = dict(company_id='C001', source_id=representative, target_id='001234567',
                        bank_code='BANK_A', link_type='bank_account', observed_at=stamp(c.at - timedelta(days=1)))
        c.tables['entity_links'].append(original)
        first = c.pay()
        c.tables['entity_links'].append(dict(original, bank_code='', status='revoked', observed_at=stamp(c.at + timedelta(days=1))))
        second = c.pay(c.at + timedelta(days=2))
        result = c.score()
        self.assertIsNotNone(self.hit(result, first, 'B2'))
        self.assertIsNotNone(self.hit(result, second, 'B2'))


if __name__ == '__main__':
    unittest.main()
