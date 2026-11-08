"""Frozen replay must retain source identity and never mutate its input DB."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_extraction import document, MASTER
from src.extraction.service import extract

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from replay_invoice_extraction import frozen_inputs,reference_report
import ocr_quality as quality


class FrozenExtractionReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.doc = document()
        self.artifact = extract(self.doc, 'PDF', MASTER)
        self.path = self.folder / 'capture.sqlite3'
        self.payload = self.doc.model_dump_json()
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE ocr_jobs(tenant_id,taxpayer_id,ingestion_id,payload,sha256)')
            db.execute('CREATE TABLE taxpayer_masters(tenant_id,taxpayer_id,revision,payload)')
            db.execute('INSERT INTO ocr_jobs VALUES(?,?,?,?,?)',
                       (self.doc.tenant_id, self.doc.taxpayer_id, self.doc.ingestion_id,
                        self.payload, hashlib.sha256(self.payload.encode()).hexdigest()))
            db.execute('INSERT INTO taxpayer_masters VALUES(?,?,?,?)',
                       (MASTER.tenant_id, MASTER.taxpayer_id, MASTER.revision, MASTER.model_dump_json()))

    def test_source_database_bytes_unchanged_and_observation_bound_to_artifact(self):
        before = self.path.read_bytes()
        doc, master = frozen_inputs(self.folder, self.artifact)
        self.assertEqual(doc, self.doc)
        self.assertEqual(master, MASTER)
        self.assertEqual(before, self.path.read_bytes())

    def test_tampered_payload_or_other_tenant_cannot_be_replayed(self):
        for changed in (self.artifact.model_copy(update={'tenant_id': 'other'}),
                        self.artifact.model_copy(update={'normalized_input_sha256': 'f' * 64}),
                        self.artifact.model_copy(update={'input_sha256': 'c' * 64})):
            with self.assertRaises(ValueError):
                frozen_inputs(self.folder, changed)
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE ocr_jobs SET sha256=?', ('0' * 64,))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            frozen_inputs(self.folder, self.artifact)

    def test_ambiguous_observations_cannot_be_silently_chosen(self):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO ocr_jobs SELECT * FROM ocr_jobs')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            frozen_inputs(self.folder, self.artifact)

    def reference(self):
        folder=self.folder/'previous';(folder/'a').mkdir(parents=True)
        manifest={'manifest_sha256':'a'*64}
        quality.write(folder/'report.json',{
            'manifest_sha256':manifest['manifest_sha256'],'run_state':'COMPLETED',
            'dataset_validated_at_end':True,'expected_cases':['a'],
            'cases':[{'case_id':'a','input_kind':'pdf_text','state':'REVIEW','score':{'correct':0}}]})
        path=folder/'a/extraction.json';quality.write(path,self.artifact.model_dump(mode='json'))
        inputs=[({'case_id':'a'},{'fields':{'invoice.number':'A001'}},self.artifact,self.doc,MASTER)]
        return folder,path,manifest,inputs

    def test_reference_is_rescored_with_same_labels_without_modifying_source(self):
        folder,path,manifest,inputs=self.reference();before=path.read_bytes();hashes={}
        with patch.object(quality,'OUTPUT',self.folder):
            report=reference_report('previous',inputs,manifest,hashes)
        self.assertEqual(report['cases'][0]['score']['correct'],1)
        self.assertEqual(path.read_bytes(),before)
        self.assertIn(str(path),hashes)

    def test_reference_with_different_observation_cannot_be_compared(self):
        folder,path,manifest,inputs=self.reference()
        quality.write(path,self.artifact.model_copy(update={'normalized_input_sha256':'f'*64}).model_dump(mode='json'))
        with patch.object(quality,'OUTPUT',self.folder):
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                reference_report('previous',inputs,manifest,{})

    def test_incomplete_or_other_dataset_reference_is_rejected(self):
        folder,path,manifest,inputs=self.reference();report=quality.read(folder/'report.json')
        with patch.object(quality,'OUTPUT',self.folder):
            with self.assertRaises(ValueError):
                reference_report('previous',inputs,{'manifest_sha256':'b'*64},{})
            quality.write(folder/'report.json',{**report,'run_state':'RUNNING'})
            with self.assertRaisesRegex(ValueError,'completed'):
                reference_report('previous',inputs,manifest,{})
