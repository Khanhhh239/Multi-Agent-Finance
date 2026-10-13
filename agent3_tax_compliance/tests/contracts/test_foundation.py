import concurrent.futures
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from src.app import create_app
from src.config import Settings
from src.domain.cfr import CanonicalFinancialRecord, ISODate, Item
from src.domain.evidence import Evidence, PageTransform, stable_candidate_id
from src.domain.field import FieldObject
from src.domain.interfaces import Assessment, Correction, StageResponse
from src.domain.money import ExactDecimal
from src.domain.storage import Artifact, Job
from src.domain.taxpayer import BranchRelation, identity_match
from src.persistence.repository import Repository, RevisionConflict
from factories import RAW, STAMP, context, envelope, field, master, record

PROJECT = Path(__file__).resolve().parents[2]


class DomainTests(unittest.TestCase):
    def test_decimal_roundtrip_and_reject_lossy_inputs(self):
        adapter = TypeAdapter(ExactDecimal)
        for raw in ('9007199254740993', '0.1', '9007199254740993.12345678901234567890123456789'):
            value = adapter.validate_python(raw)
            self.assertEqual(adapter.validate_json(adapter.dump_json(value)), Decimal(raw))
        for bad in (0.1, 1, True, 'NaN', 'Infinity', '1e3', '1,000', '01'):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                adapter.validate_python(bad)

    def test_status_value_invariants_and_no_default_probability(self):
        self.assertIsNone(FieldObject[str](**field('abc')).confidence)
        for status in ('MISSING', 'AMBIGUOUS', 'NOT_PROVIDED_BY_SOURCE', 'NOT_APPLICABLE'):
            self.assertIsNone(FieldObject[str](**field(status=status)).value)
            with self.assertRaises(ValidationError):
                FieldObject[str](**field('invented', status))
        with self.assertRaises(ValidationError):
            FieldObject[str](**field(status='PRESENT'))

    def test_confidence_basis_requires_proof(self):
        for basis in ('CALIBRATED', 'DETERMINISTIC', 'HUMAN_CONFIRMED'):
            data = field('x'); data['confidence_basis'] = basis
            with self.assertRaises(ValidationError):
                FieldObject[str](**data)
        data = field('x'); data.update(confidence_basis='CALIBRATED', confidence=0.8)
        data['provenance']['calibration_version'] = 'cal-v1'
        self.assertEqual(FieldObject[str](**data).confidence, 0.8)
        for basis, key in [('DETERMINISTIC','deterministic_policy_version'), ('HUMAN_CONFIRMED','review_event_id')]:
            data = field('x'); data['confidence_basis'] = basis; data['provenance'][key] = 'proof-1'
            self.assertIsNone(FieldObject[str](**data).confidence)
        data = field('x'); data['confidence'] = 1.0
        with self.assertRaises(ValidationError):
            FieldObject[str](**data)

    def test_geometry_and_candidate_stability(self):
        e = Evidence(source_id='s', document_id='d', page_index=0, bbox=(0.1,0.2,0.3,0.4))
        self.assertEqual(stable_candidate_id('gross','12',(e,)), stable_candidate_id('gross','12',(e,)))
        self.assertNotEqual(stable_candidate_id('gross','12',(e,)), stable_candidate_id('net','12',(e,)))
        for bbox in ((0,0,0,1),(-1,0,1,1),(0,0,1,2)):
            with self.assertRaises(ValidationError):
                Evidence(source_id='s',document_id='d',page_index=0,bbox=bbox)
        with self.assertRaises(ValidationError):
            PageTransform(transform_id='t',source_id='s',page_index=0,from_space='PDF_POINTS',
                          source_width=100,source_height=100,matrix=(0,0,0,0,0,0))

    def test_dates_reject_implicit_epoch_and_locales(self):
        adapter = TypeAdapter(ISODate)
        self.assertEqual(adapter.validate_python('2026-10-11'), date(2026,10,11))
        for value in (0, 123.4, '11/10/2026', '2026-10-11T00:00:00Z'):
            with self.assertRaises(ValidationError):
                adapter.validate_python(value)

    def test_exported_producer_examples_validate_as_consumer(self):
        from src.domain.envelope import SourceEnvelope
        from src.domain.interfaces import DetectedSource, Extraction
        models = {'cfr':CanonicalFinancialRecord,'source_envelope':SourceEnvelope,
                  'detect_response':StageResponse[DetectedSource],
                  'extract_response':StageResponse[Extraction],
                  'canonicalize_response':StageResponse[tuple[CanonicalFinancialRecord,...]],
                  'assess_response':StageResponse[Assessment], 'review_response':StageResponse[CanonicalFinancialRecord]}
        bundle=json.loads((PROJECT/'contracts/v1/examples.json').read_text(encoding='utf-8'))
        for example in bundle['valid']:
            model=models[example['contract']]
            parsed=model.model_validate_json(json.dumps(example['payload']))
            self.assertEqual(model.model_validate_json(parsed.model_dump_json()),parsed)
        for example in bundle['invalid']:
            with self.subTest(example=example['name']), self.assertRaises(ValidationError):
                models[example['contract']].model_validate_json(json.dumps(example['payload']))

    def test_unknown_direction_and_vat_semantics(self):
        data = record().model_dump(mode='json')
        data['derived']['invoice_direction'] = field('UNKNOWN')
        with self.assertRaises(ValidationError):
            CanonicalFinancialRecord.model_validate(data)
        for treatment in ('KCT','KKKNT'):
            Item(item_id='id-a',line_number=1,vat_treatment=field(treatment))
            with self.assertRaises(ValidationError):
                Item(item_id='id-a',line_number=1,vat_treatment=field(treatment),vat_rate=field('0'))
        Item(item_id='id-a',line_number=1,vat_treatment=field('TAXABLE_RATE'),vat_rate=field('0'))

    def test_bank_has_no_seller_buyer(self):
        data = record().model_dump(mode='json')
        data.update(record_type='BANK_TRANSACTION',invoice=None,parties={},
                    bank_transaction=dict(account_owner={}, amount=field('0.1')))
        self.assertIsNone(CanonicalFinancialRecord.model_validate(data).parties.seller)
        data['parties']={'seller':{}}
        with self.assertRaises(ValidationError):
            CanonicalFinancialRecord.model_validate(data)

    def test_branch_mapping_is_explicit_and_time_bound(self):
        m = master()
        self.assertEqual(identity_match('1234567890001',m,date(2026,2,1)), 'UNKNOWN')
        rel = BranchRelation(tenant_id='tenant-a',parent_tax_code=m.tax_code,branch_tax_code='1234567890001',
                             effective_from=date(2026,3,1),effective_to=date(2026,4,1),evidence_reference='approved-relation')
        self.assertEqual(identity_match(rel.branch_tax_code,m,date(2026,3,1),(rel,)), 'MATCH')
        self.assertEqual(identity_match(rel.branch_tax_code,m,date(2026,4,1),(rel,)), 'UNKNOWN')
        self.assertEqual(identity_match(m.tax_code,m,None), 'UNKNOWN')

    def test_typed_response_and_correction(self):
        response = StageResponse[Assessment](**STAMP,request_id='r',input_sha256='a'*64,status='ERROR',
                           error=dict(code='PROCESSING_ERROR',retryable=True,message='safe error'))
        self.assertIsNone(response.data)
        with self.assertRaises(ValidationError):
            StageResponse[Assessment](**STAMP,request_id='r',input_sha256='a'*64,status='SUCCEEDED')
        with self.assertRaises(ValidationError):
            Correction(**STAMP,tenant_id='t',taxpayer_id='p',record_id='r',expected_revision=1,
                       task_id='task',field_path='seller.name',reason='check',new_value='x',selected_candidate_id='c')


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(database_path=Path(self.temp.name)/'new.sqlite3')
        self.repo = Repository(self.settings); self.repo.initialize(); self.ctx = context()
        self.repo.add_taxpayer(self.ctx, master()); self.repo.add_taxpayer(self.ctx, master('payer-b'))
        self.repo.store_source(self.ctx, envelope(), RAW)
        self.repo.create_record(self.ctx, record())

    def tearDown(self):
        self.temp.cleanup()

    def test_money_and_raw_integrity_reopen(self):
        reopened = Repository(self.settings); reopened.initialize()
        self.assertEqual(reopened.record(self.ctx,'payer-a','record-1').totals.gross.value, Decimal('9007199254740993.1'))
        env, raw = reopened.source(self.ctx,'payer-a','source-1')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), env.sha256)
        with self.assertRaises(sqlite3.IntegrityError), self.repo.connection() as db:
            db.execute("UPDATE sources SET raw=x'01'")
        with self.assertRaises(sqlite3.IntegrityError), self.repo.connection() as db:
            db.execute('DELETE FROM revisions')

    def test_source_master_pin_and_hash_are_enforced(self):
        bad=record().model_copy(update={'record_id':'bad','taxpayer_master_revision':2})
        with self.assertRaises(ValueError):
            self.repo.create_record(self.ctx,bad)
        with self.assertRaises(ValueError):
            self.repo.store_source(self.ctx,envelope().model_copy(update={'source_id':'bad'}),b'changed')

    def test_source_audit_failure_rolls_back_raw(self):
        with self.repo.connection() as db:
            db.execute("CREATE TRIGGER fail_source_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.store_source(self.ctx,envelope().model_copy(update={'source_id':'source-2'}),RAW)
        with self.assertRaises(KeyError):
            self.repo.source(self.ctx,'payer-a','source-2')

    def test_cross_tenant_and_taxpayer_isolation(self):
        alien = context('tenant-b', ('payer-a',))
        with self.assertRaises(KeyError):
            self.repo.record(alien,'payer-a','record-1')
        with self.assertRaises(PermissionError):
            self.repo.create_record(alien, record())
        with self.assertRaises(PermissionError):
            self.repo.taxpayer(context(taxpayers=('payer-b',)), 'payer-a', 1)
        with self.assertRaises(KeyError):
            self.repo.record(self.ctx,'payer-b','record-1')
        self.assertEqual(self.repo.taxpayer(self.ctx,'payer-b',1).taxpayer_id,'payer-b')

    def test_read_only_context_cannot_write_or_register_master(self):
        viewer=self.ctx.model_copy(update={'permissions':frozenset({'READ'})})
        self.assertEqual(self.repo.record(viewer,'payer-a','record-1').revision,1)
        with self.assertRaises(PermissionError):
            self.repo.create_record(viewer,record().model_copy(update={'record_id':'blocked'}))
        with self.assertRaises(PermissionError):
            self.repo.add_taxpayer(viewer,master('payer-b'))

    def test_two_concurrent_reviewers_only_one_wins(self):
        import threading
        barrier = threading.Barrier(2)
        data = record().model_dump(mode='json'); data['revision']=2
        revised = CanonicalFinancialRecord.model_validate(data)
        def submit():
            barrier.wait()
            try:
                Repository(self.settings).append_revision(self.ctx,revised,1,'reviewed')
                return 'won'
            except RevisionConflict:
                return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:submit(), range(2)))
        self.assertCountEqual(results,['won','conflict'])
        self.assertEqual(self.repo.record(self.ctx,'payer-a','record-1').revision,2)
        self.assertEqual(len([e for e in self.repo.events(self.ctx,'payer-a') if e.event_type=='RECORD_REVISED']),1)

    def test_audit_failure_rolls_back_revision_and_head(self):
        data = record().model_dump(mode='json'); data['revision']=2
        revised = CanonicalFinancialRecord.model_validate(data)
        with self.repo.connection() as db:
            db.execute("CREATE TRIGGER injected_audit_failure BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.append_revision(self.ctx,revised,1,'reviewed')
        self.assertEqual(self.repo.record(self.ctx,'payer-a','record-1').revision,1)
        with self.assertRaises(KeyError):
            self.repo.record(self.ctx,'payer-a','record-1',2)

    def test_item_reorder_preserves_ids_and_identity_changes_rejected(self):
        data = record().model_dump(mode='json'); data['record_id']='with-items'
        data['items']=[dict(item_id='uuid-a',line_number=1),dict(item_id='uuid-b',line_number=2)]
        r = CanonicalFinancialRecord.model_validate(data); self.repo.create_record(self.ctx,r)
        data['revision']=2; data['items'].reverse()
        self.repo.append_revision(self.ctx,CanonicalFinancialRecord.model_validate(data),1,'reorder')
        data['revision']=3; data['items'][0]['item_id']='renamed'
        with self.assertRaises(ValueError):
            self.repo.append_revision(self.ctx,CanonicalFinancialRecord.model_validate(data),2,'rename')

    def test_artifact_job_and_input_hashes(self):
        r = self.repo.record(self.ctx,'payer-a','record-1')
        artifact = Artifact(**STAMP,artifact_id='a',tenant_id='tenant-a',taxpayer_id='payer-a',record_id='record-1',
                            record_revision=1,input_sha256=hashlib.sha256(r.model_dump_json().encode()).hexdigest(),
                            artifact_kind='quality',content='{}')
        self.repo.add_artifact(self.ctx,artifact)
        self.assertEqual(self.repo.artifact(self.ctx,'payer-a','a'),artifact)
        job = Job(**STAMP,job_id='j',tenant_id='tenant-a',taxpayer_id='payer-a',source_id='source-1',input_sha256=envelope().sha256)
        self.repo.add_job(self.ctx,job)
        self.assertEqual(self.repo.job(self.ctx,'payer-a','j'),job)
        with self.assertRaises(ValueError):
            self.repo.add_job(self.ctx,job.model_copy(update={'job_id':'bad','input_sha256':'b'*64}))

    def test_refuse_legacy_database_even_if_named_sqlite(self):
        path=Path(self.temp.name)/'legacy.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE legacy(amount REAL)')
        before=path.read_bytes()
        with self.assertRaises(ValueError):
            Repository(Settings(database_path=path)).initialize()
        self.assertEqual(before,path.read_bytes())


class AppTests(unittest.TestCase):
    def test_offline_health_no_database_side_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'not-created.sqlite3'
            app=create_app(Settings(database_path=path))
            with TestClient(app) as client:
                self.assertEqual(client.get('/v1/health').json()['status'],'ok')
                self.assertEqual(client.post('/process_transaction',json={}).status_code,404)
                self.assertEqual(client.get('/v1/records',params={'taxpayer_id':'payer-a'}).status_code,401)
            self.assertFalse(path.exists())

    def test_import_does_not_load_legacy_models_or_database(self):
        code="import sys; from src.app import create_app; assert 'src.main' not in sys.modules; assert 'src.database' not in sys.modules; assert 'torch' not in sys.modules; assert 'zen' not in sys.modules; assert 'openai' not in sys.modules"
        subprocess.run([sys.executable,'-c',code],cwd=PROJECT,check=True,capture_output=True)


if __name__ == '__main__':
    unittest.main()
