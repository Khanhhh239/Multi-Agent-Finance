"""Edge-case parity tests for rule-snapshot B1/B5/E4 adapters."""
from copy import deepcopy
import sys
import unittest

import test_he4_rule_snapshot_identity as ti
from experiments.he4.rule_snapshot_identity_adapter import (
    decode_b1_plan_results,
    decode_b5_e4_plan_results,
    plan_b1_from_rule_snapshot,
    plan_b5_e4_from_rule_snapshot,
)
from sme_fraud import rule_snapshot as rs
from sme_fraud.import_files import ImportFailure


def _native_rules(data: dict, scope) -> dict[str, dict]:
    native = rs.source_guards(deepcopy(data), rs.evaluate_bundle(deepcopy(data['source']), scope))
    return {entry['rule_id']: entry for entry in native['rules']}


class RuleSnapshotIdentityEdgeTests(unittest.TestCase):
    def test_b5_e4_unknown_contacts_with_no_known_fields_stays_unavailable(self):
        scope = ti._scope()
        src, meta = ti.scenario('B5', False)
        for vendor in src['tables']['vendors']:
            vendor['phone'] = '???'
            vendor['bank_account'] = ''
            vendor['address'] = '   '
        ti._rehash(src)
        data = ti._wrap(src, [meta['target_transaction_id']])

        native = _native_rules(data, scope)
        self.assertEqual(native['B5']['status'], 'unavailable')
        self.assertEqual(native['E4']['status'], 'unavailable')

        plan = plan_b5_e4_from_rule_snapshot(deepcopy(data), scope)
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['status'], 'unavailable')
        self.assertEqual(plan['rows'][0]['reason'], 'identity_field_unknown')
        self.assertEqual(plan['rows'][0]['requests'], [])

        decoded = decode_b5_e4_plan_results(plan, [])
        self.assertFalse(decoded['rows'][0]['available'])
        self.assertEqual(decoded['rows'][0]['status'], 'unavailable')
        self.assertEqual(decoded['rows'][0]['reason'], 'identity_field_unknown')

    def test_b5_e4_rejects_unvalidated_late_vendor_reference_and_missing_coverage(self):
        scope = ti._scope()
        src, meta = ti.scenario('B5', False)
        src['coverage'].pop('vendors')
        data = ti._wrap(src, [meta['target_transaction_id']])
        plan = plan_b5_e4_from_rule_snapshot(deepcopy(data), scope)
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['status'], 'unavailable')
        self.assertEqual(plan['rows'][0]['reason'], 'source_coverage_missing')

        bad_src, bad_meta = ti.scenario('B5', False)
        bad_src['tables']['transactions'][0]['observed_at'] = '2020-01-01T00:00:00+07:00'
        ti._rehash(bad_src)
        with self.assertRaises(ImportFailure):
            plan_b5_e4_from_rule_snapshot(ti._wrap(bad_src, [bad_meta['target_transaction_id']]), scope)

    def test_b1_missing_recipient_bank_code_and_late_transaction_cutoff(self):
        scope = ti._scope()
        src, meta = ti.scenario('B1', True)
        cid = meta['target_transaction_id']
        for tx in src['tables']['transactions']:
            if tx['transaction_id'] == cid:
                tx['recipient_bank_code'] = ''
        ti._rehash(src)
        data = ti._wrap(src, [cid])
        native = _native_rules(data, scope)
        self.assertEqual(native['B1']['status'], 'unavailable')

        plan = plan_b1_from_rule_snapshot(deepcopy(data), scope)
        self.assertFalse(plan['rows'][0]['available'])
        self.assertEqual(plan['rows'][0]['status'], 'unavailable')
        self.assertEqual(plan['rows'][0]['reason'], 'recipient_bank_identity_incomplete')

        decoded = decode_b1_plan_results(plan, [])
        self.assertFalse(decoded['rows'][0]['available'])
        self.assertEqual(decoded['rows'][0]['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()

