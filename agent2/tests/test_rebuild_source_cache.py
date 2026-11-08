"""Raw-source migration keeps unknown evidence unknown and refuses replacement."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.feature_contract import sha, validate_cache
from sme_fraud.generate import write_csv
from sme_fraud.rebuild_source_cache import rebuild_cache
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import INPUT_TABLES, OPTIONAL_INPUT_TABLES


class RebuildCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'raw';self.source.mkdir();self.output=self.root/'cache'
        c=Case();c.pay(amount=1_000_000);c.score()
        for name in dict.fromkeys(INPUT_TABLES+OPTIONAL_INPUT_TABLES):
            rows=c.tables.get(name,[])
            if rows or name in INPUT_TABLES:
                write_csv(self.source/(name+'.csv'),rows,list(dict.fromkeys(k for r in rows for k in r)) or ['company_id'])
        # These deliberately invalid files must never be parsed or copied.
        for name in ('features.csv','labels.csv','splits.csv'):(self.source/name).write_bytes(b'not valid CSV or old feature cache\xff')
        self.meta=dict(version='raw-fixture-v1',role='reporting',is_synthetic=True,
            files={p.name:dict(sha256=sha(p)) for p in self.source.glob('*.csv')})
        self.save_manifest()

    def save_manifest(self):
        (self.source/'manifest.json').write_text(json.dumps(self.meta),encoding='utf-8')

    def tearDown(self):self.temp.cleanup()

    def test_rebuild_is_attested_194_columns_and_preserves_missing_times(self):
        before={p.name:sha(p) for p in self.source.iterdir()}
        r=rebuild_cache(self.source,self.output)
        self.assertEqual(r['feature_count'],194)
        meta=json.loads((self.output/'manifest.json').read_text(encoding='utf-8'));validate_cache(meta)
        with (self.output/'features.csv').open(encoding='utf-8-sig',newline='') as stream:row=next(csv.DictReader(stream))
        self.assertEqual((float(row['support_docs_known']),float(row['support_doc_count'])),(0,0))
        self.assertFalse(meta['feature_derivation']['raw_values_and_timestamps_modified'])
        for name in meta['files']:
            if name!='features.csv':self.assertEqual(sha(self.output/name),before[name])
        self.assertEqual({p.name:sha(p) for p in self.source.iterdir()},before)
        self.assertFalse((self.output/'splits.csv').exists());self.assertFalse((self.output/'labels.csv').exists())

    def test_checksum_error_refuses_final_output(self):
        (self.source/'transactions.csv').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'checksum'):rebuild_cache(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir();(self.output/'keep').write_text('keep',encoding='utf-8')
        with self.assertRaises(FileExistsError):rebuild_cache(self.source,self.output)
        self.assertEqual((self.output/'keep').read_text(encoding='utf-8'),'keep')

    def test_failed_feature_rebuild_removes_only_its_new_staging_directory(self):
        with patch('sme_fraud.rebuild_source_cache.build_features',side_effect=ValueError('bad raw evidence')):
            with self.assertRaisesRegex(ValueError,'bad raw evidence'):rebuild_cache(self.source,self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual([p.name for p in self.root.iterdir()],['raw'])

    def test_source_mutation_during_rebuild_is_rejected_before_publication(self):
        from sme_fraud.features import build_features
        def changed(tables):
            result=build_features(tables)
            with (self.source/'transactions.csv').open('a',encoding='utf-8') as s:s.write('\n')
            return result
        with patch('sme_fraud.rebuild_source_cache.build_features',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Source changed'):rebuild_cache(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_holdout_and_nonreporting_or_unattested_source_rejected(self):
        with self.assertRaisesRegex(ValueError,'Holdout'):rebuild_cache(self.root/'sme_fraud_005',self.output)
        for update in ({'role':'holdout'},{'is_synthetic':False}):
            self.meta.update(update);self.save_manifest()
            with self.assertRaises(ValueError):rebuild_cache(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_manifest_cannot_escape_source_directory(self):
        self.meta['files']['../escape.csv']=dict(sha256='invalid');self.save_manifest()
        with self.assertRaisesRegex(ValueError,'plain CSV'):rebuild_cache(self.source,self.output)
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
