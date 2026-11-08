"""Isolation and provenance boundaries for the integrated synthetic runner."""
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.feature_contract import cache_contract, sha
from sme_fraud.features import FEATURE_DESCRIPTIONS
from sme_fraud.integrated_rehearsal import (accounting_tables, copy_cache, dry_config, fake_people, fresh_output,
    no_truth_access, read_json, serve, write_json)


class IntegratedRehearsalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def cache(self):
        source = self.root/'source/sme_fraud_003'
        source.mkdir(parents=True)
        (source/'transactions.csv').write_text('transaction_id\nTX1\n', encoding='utf-8')
        (source/'features.csv').write_text('transaction_id,'+','.join(FEATURE_DESCRIPTIONS)+'\n', encoding='utf-8')
        files = {p.name:dict(sha256=sha(p)) for p in source.glob('*.csv')}
        # Forbidden names in old manifests must never become IO dependencies.
        files['labels.csv'] = dict(sha256='NOT_READ')
        files['splits.csv'] = dict(sha256='NOT_READ')
        write_json(source/'manifest.json', dict(role='reporting', is_synthetic=True, files=files,
            feature_columns=list(FEATURE_DESCRIPTIONS), feature_contract=cache_contract(files)))
        return source

    def test_copy_preserves_provenance_and_excludes_truth(self):
        source = self.cache()
        output = self.root/'workspace/source/sme_fraud_003'
        with no_truth_access() as attempted:
            copied = copy_cache(source, output)
        self.assertEqual(attempted, [])
        self.assertEqual(copied['files'], 2)
        self.assertEqual(sha(source/'manifest.json'), sha(output/'manifest.json'))
        self.assertEqual(sorted(p.name for p in output.iterdir()), ['features.csv','manifest.json','transactions.csv'])

    def test_modified_source_is_rejected_before_copy(self):
        source = self.cache()
        (source/'transactions.csv').write_text('transaction_id\nCHANGED\n', encoding='utf-8')
        output = self.root/'workspace/source/sme_fraud_003'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            copy_cache(source, output)
        self.assertFalse(output.exists())

    def test_accounting_audit_reads_attested_extra_tables_without_changing_rule_tables(self):
        source = self.cache()
        metadata = read_json(source/'manifest.json')
        for name in ('account_flow_edges','document_links','invoices'):
            path = source/(name+'.csv')
            path.write_text('id\nROW1\n', encoding='utf-8')
            metadata['files'][path.name] = dict(sha256=sha(path))
        original = {'transactions':[{'transaction_id':'TX1'}]}
        combined = accounting_tables(source, original, metadata)
        self.assertEqual(set(original), {'transactions'})
        self.assertEqual(combined['account_flow_edges'], [{'id':'ROW1'}])
        (source/'invoices.csv').write_text('id\nCHANGED\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Accounting source'):
            accounting_tables(source, original, metadata)

    def test_real_source_is_rejected(self):
        source = self.cache()
        metadata = read_json(source/'manifest.json')
        metadata['is_synthetic'] = False
        write_json(source/'manifest.json', metadata)
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            copy_cache(source, self.root/'output')

    def test_existing_workspace_is_never_overwritten(self):
        output = self.root/'existing'
        output.mkdir()
        with self.assertRaises(FileExistsError):
            fresh_output(output, [self.root/'prior'])

    def test_input_child_and_parent_are_rejected(self):
        for output, source in ((self.root/'prior/run',self.root/'prior'),
                               (self.root/'new',self.root/'new/prior')):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'separate'):
                fresh_output(output, [source])

    def test_holdout_and_truth_guard_fails_before_opening(self):
        for path in (self.root/'labels.csv', self.root/'splits.csv', self.root/'oracle.json',
                     self.root/'control_oracle.jsonl',self.root/'sme_fraud_005/transactions.csv'):
            with self.subTest(path=path), no_truth_access() as attempts:
                with self.assertRaises(AssertionError):
                    path.read_text()
                self.assertEqual(len(attempts), 1)

    def test_role_routing_has_distinct_people_and_company_scopes(self):
        config = dry_config(['C001','C002'])
        self.assertTrue(config['dry_run'])
        self.assertEqual(config['daily_budget'], 5)
        seen = set()
        for company in ('C001','C002'):
            actors = fake_people(company)
            self.assertEqual(len({a.person_id for a in actors}), 3)
            self.assertTrue(all(a.company_ids == (company,) for a in actors))
            for person in config['role_recipients'][company]:
                self.assertNotIn(person['person_id'], seen)
                seen.add(person['person_id'])
                self.assertTrue(all(e.endswith('@example.invalid') for e in person['channels']['email']))
                self.assertTrue(all(e.startswith('SIM_') for e in person['channels']['zalo']))

    def test_serving_rejects_an_unattested_workspace(self):
        app = self.root/'app'
        app.mkdir()
        write_json(app/'integration_qa.json', dict(kind='other',is_synthetic=False))
        with self.assertRaisesRegex(ValueError, 'successful synthetic'):
            serve(self.root)


if __name__ == '__main__':
    unittest.main()
