import copy
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.synthetic_world import World, AS_OF, raw_export, map_export
from sme_fraud.synthetic_dataset import export_world, diagnostics, quarantine_probes
from sme_fraud.exception_validation import validated_tables
from sme_fraud.real_source_acceptance import _looks_synthetic, inventory_ready, RULES
from sme_fraud.rules import load_inputs
from sme_fraud.run_synthetic_readiness import select_packet, metrics


class SyntheticSourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(2026101701, companies=2, background_rows=50)
        cls.tables, cls.oracle = cls.world.build(repetitions=1)

    def test_all_exception_sources_obey_strict_contract(self):
        validated_tables(self.tables)

    def test_seed_replays_sources_and_source_defined_oracle(self):
        other = World(2026101701, companies=2, background_rows=50)
        tables, oracle = other.build(repetitions=1)
        self.assertEqual(tables, self.tables)
        self.assertEqual(oracle, self.oracle)

    def test_different_seeds_change_business_profiles_and_values(self):
        other = World(2026101702, companies=2, background_rows=50)
        self.assertNotEqual(other.profiles, self.world.profiles)
        self.assertNotEqual(other.tables['employees'], self.tables['employees'])

    def test_mapping_preserves_utc_vnd_bank_identity_and_leading_zeros(self):
        for row in self.tables['transactions']:
            mapped = map_export(raw_export(row))
            self.assertEqual(mapped, {key: row[key] for key in mapped})
        self.assertTrue(any(r['recipient_account'].startswith('0') for r in self.tables['transactions']))

    def test_journal_balances_and_unknown_background_has_no_fraud_labels(self):
        result = diagnostics(self.tables, self.oracle, self.world.profiles)
        self.assertEqual(result['unbalanced_journal_documents'], 0)
        self.assertFalse(result['financial_fraud_labels_available'])
        self.assertEqual(self.tables['labels'], [])

    def test_bad_flags_enums_amounts_times_and_unsupported_semantics_are_quarantined(self):
        probes = quarantine_probes(self.tables)
        self.assertEqual(len(probes), 16)
        self.assertTrue(all(p['status'] == 'rejected' for p in probes))

    def test_future_sources_retained_but_future_transactions_not_scored(self):
        self.assertTrue(all(r['posted_at'] <= AS_OF for r in self.tables['transactions']))
        self.assertTrue(self.world.quarantine)
        self.assertTrue(any(r['recorded_at'] > AS_OF for r in self.tables['employees']))
        self.assertTrue(any(r['observed_at'] > AS_OF for r in self.tables['receipt_allocations']))

    def test_reserved_staff_contact_edges_follow_master_bank_identity(self):
        employees = {r['employee_id']: r for r in self.tables['employees']}
        for ids in self.world.reserved.values():
            for identity in ids:
                links = [r for r in self.tables['entity_links'] if r['source_id'] == identity and r['link_type'] == 'bank_account']
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0]['target_id'], employees[identity]['bank_account'])
                self.assertEqual(links[0]['bank_code'], employees[identity]['bank_code'])

    def test_expanded_headcount_has_no_obsolete_or_duplicate_contact_mirrors(self):
        masters = {row.get('employee_id') or row.get('vendor_id'): row
                   for row in [*self.tables['employees'], *self.tables['vendors']]}
        seen = set()
        for link in self.tables['entity_links']:
            identity, kind = link['source_id'], link['link_type']
            self.assertNotIn((identity, kind), seen)
            seen.add((identity, kind))
            self.assertEqual(link['target_id'], masters[identity][kind])
            if kind == 'bank_account':
                self.assertEqual(link['bank_code'], masters[identity]['bank_code'])
        self.assertEqual(len(seen), 2*len(masters))

    def test_synthetic_origin_never_becomes_real_even_without_legacy_fraud_keys(self):
        self.assertTrue(_looks_synthetic(dict(is_synthetic=True)))
        self.assertTrue(_looks_synthetic(dict(data_origin='synthetic_process_simulation')))
        self.assertFalse(_looks_synthetic(dict(data_origin='real_sme_export')))

    def test_packet_selection_uses_sources_not_predicted_hits_and_keeps_truth_separate(self):
        base = dict(company_id='C1', rule_id='F1', unit_type='transaction')
        population = [dict(base, unit_id=str(i), review_id=f'R{i:03}') for i in range(30)]
        controls = [dict(population[-1], expected=True, scenario='manual_material_close')]
        before = select_packet(population, controls, per_stratum=3)
        after = select_packet(list(reversed(population)), controls, per_stratum=3)
        self.assertEqual(before, after)
        self.assertEqual(len(before), 4)
        self.assertTrue(all(not {'expected', 'prediction', 'scenario'} & set(row) for row in before))

    def test_oracle_abstention_mismatches_cannot_disappear_from_metrics(self):
        result = metrics([dict(expected=True, actual=None), dict(expected=None, actual=False),
                          dict(expected=False, actual=False), dict(expected=None, actual=None)])
        self.assertEqual(result['mismatches_including_unknown'], 2)
        self.assertEqual(result['known_expected_abstentions'], 1)
        self.assertEqual(result['unknown_expected_nonabstentions'], 1)

    def test_export_and_native_loader_cache_contract(self):
        runtime = Path('.runtime').resolve()
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temp:
            data, report = Path(temp)/'data', Path(temp)/'report'
            export_world(data, report, 193, role='blind_holdout', companies=2, background_rows=20, repetitions=1)
            tables, features, manifest = load_inputs(data)
            self.assertEqual(len(features), len(tables['transactions']))
            self.assertNotIn('labels', tables)
            self.assertTrue(manifest['is_synthetic'])
            inventory = json.loads((report/'source_inventory.json').read_text(encoding='utf-8'))
            self.assertTrue(all(inventory_ready(inventory, rule) for rule in RULES))
            self.assertFalse((report/'predictions.json').exists())
            self.assertFalse((data/'labels.csv').exists())


if __name__ == '__main__':
    unittest.main()
