"""Coordinated SQLite/audit/identity backup, corruption checks and safe relocation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import contextlib
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from sme_fraud.case_identity import digest
from sme_fraud.feedback import feedback_lock
from sme_fraud.notifications import Notifications
from sme_fraud.review_backup import create_backup,verify_backup,restore_backup,restored_store,sha,main,read_database
from sme_fraud.review_capacity import ReviewCalendar
from sme_fraud.review_store import ReviewStore
from test_review import make_fixture


class ReviewBackupTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data,self.report=make_fixture(self.root)
        self.now=datetime.fromisoformat('2026-10-19T09:00:00+07:00')
        self.store=ReviewStore(self.root/'data',self.root/'reports',self.root/'review.sqlite3',clock=lambda:self.now)
        self.store.prepare()
        detail=self.store.detail('003','RC_1')
        self.request=self.store.update_information_request('003','RC_1',dict(action='create',expected_hash='',
            case_scope_hash=detail['case']['review_scope_hash'],owner='SIM_OWNER',actor='SIM_REVIEWER',
            requested_documents='SIM: hóa đơn gốc',reason='SIM: cần bổ sung',due_at=(self.now+timedelta(days=2)).isoformat()))
        self.feedback=self.store.save_feedback('003','RC_2','false_positive','SIM_REVIEWER','SIM: đã đối chiếu chứng từ','')
        self.notifier=Notifications(self.store,dict(dry_run=True))
        self.notifier.plan('003');self.notifier.dispatch()
        self.calendar=ReviewCalendar((0,1,2,3,4),('2026-10-20',))

    def tearDown(self):self.temp.cleanup()

    def backup(self,name='backup',**values):
        return create_backup(self.store.database,self.root/'data',self.root/'reports',self.root/name,calendar=self.calendar,**values)

    def test_complete_restore_preserves_cases_requests_feedback_and_outbox(self):
        before={p:sha(p) for p in [*self.data.glob('*.csv'),*self.report.glob('*.json*'),self.report/'case_queue.csv']}
        manifest=self.backup()
        self.assertEqual(verify_backup(self.root/'backup')['manifest_sha256'],manifest['manifest_sha256'])
        receipt=restore_backup(self.root/'backup',self.root/'restored')
        restored=restored_store(self.root/'restored');restored.clock=lambda:self.now
        self.assertEqual(receipt['database_state'],manifest['database_state'])
        self.assertNotEqual(receipt['relocation']['003']['original'],receipt['relocation']['003']['restored'])
        for key in ('RC_1','RC_2','SC_F4'):
            original,after=self.store.detail('003',key),restored.detail('003',key)
            for field in ('case','transactions','hits','documents','feedback_history','information_requests','case_lineage'):
                self.assertEqual(after[field],original[field],(key,field))
        self.assertEqual(restored.review_calendar.as_dict(),self.calendar.as_dict())
        self.assertEqual(restored.admissions('003'),self.store.admissions('003'))
        self.assertEqual(Notifications(restored).status('003')['counts'],self.notifier.status('003')['counts'])
        with self.assertRaises(RuntimeError):
            restored.save_feedback('003','RC_1','false_positive','SIM_REVIEWER','SIM: tài liệu chưa rà','')
        self.assertEqual(before,{p:sha(p) for p in before})

    def test_restored_copy_does_not_depend_on_original_sources(self):
        self.backup()
        restore_backup(self.root/'backup',self.root/'restored')
        # Make the original report unusable without deleting or moving any tree.
        (self.report/'case_identity.json').write_text('BROKEN ORIGINAL',encoding='utf-8')
        (self.data/'transactions.csv').write_text('BROKEN ORIGINAL',encoding='utf-8')
        restored=restored_store(self.root/'restored')
        self.assertEqual(restored.detail('003','RC_2')['case']['feedback']['event_hash'],self.feedback['event_hash'])

    def test_live_wal_commit_is_backed_up_without_copying_sidecars(self):
        with self.store.connection() as live:
            live.execute("INSERT INTO settings VALUES('wal_canary','committed')");live.commit()
            self.assertTrue(Path(str(self.store.database)+'-wal').is_file())
            self.backup()
        with read_database(self.root/'backup/review.sqlite3') as db:
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='wal_canary'").fetchone()[0],'committed')
        self.assertFalse((self.root/'backup/review.sqlite3-wal').exists())
        self.assertFalse((self.root/'backup/review.sqlite3-shm').exists())

    def test_backup_waits_for_feedback_writer_before_freezing_snapshot(self):
        entered=threading.Event()
        def backup():entered.set();return self.backup()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with feedback_lock(self.report):
                future=pool.submit(backup);self.assertTrue(entered.wait(2));time.sleep(.1)
                self.assertFalse(future.done())
                with self.store.connection() as db:
                    db.execute("INSERT INTO settings VALUES('lock_canary','after_wait')")
            result=future.result(timeout=15)
        self.assertGreater(result['database_state']['settings']['rows'],0)
        with read_database(self.root/'backup/review.sqlite3') as db:
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='lock_canary'").fetchone()[0],'after_wait')

    def test_existing_destinations_and_input_overlap_are_rejected(self):
        self.backup()
        with self.assertRaises(FileExistsError):self.backup()
        with self.assertRaises(ValueError):
            create_backup(self.store.database,self.root/'data',self.root/'reports',self.data/'new')
        with self.assertRaises(ValueError):restore_backup(self.root/'backup',self.root/'backup/nested')
        restore_backup(self.root/'backup',self.root/'restored')
        with self.assertRaises(FileExistsError):restore_backup(self.root/'backup',self.root/'restored')

    def test_wal_writer_during_copy_does_not_split_the_database_snapshot(self):
        from sme_fraud import review_backup
        original=review_backup.copy_checked
        wrote=[]
        def copying(source,target):
            if not wrote:
                with self.store.connection() as db:db.execute("INSERT INTO settings VALUES('late_writer','after_snapshot')")
                wrote.append(True)
            return original(source,target)
        with patch.object(review_backup,'copy_checked',copying):self.backup()
        with read_database(self.root/'backup/review.sqlite3') as db:
            self.assertIsNone(db.execute("SELECT value FROM settings WHERE key='late_writer'").fetchone())
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='late_writer'").fetchone()[0],'after_snapshot')

    def test_all_prepared_scenarios_are_included(self):
        import shutil
        shutil.copytree(self.data,self.root/'data/sme_fraud_001')
        report=self.root/'reports/sme_fraud_001';report.mkdir()
        for name in ('case_queue.csv','case_events.csv','rule_coverage.json','rule_hits.jsonl','evidence_findings.jsonl'):
            shutil.copyfile(self.report/name,report/name)
        store=ReviewStore(self.root/'data',self.root/'reports',self.store.database,scenarios=['001','003'],clock=lambda:self.now)
        store.prepare()
        manifest=self.backup()
        self.assertEqual(manifest['scenarios'],['001','003'])
        restore_backup(self.root/'backup',self.root/'restored')
        restored=restored_store(self.root/'restored')
        self.assertEqual(restored.detail('001','RC_1')['case']['company_id'],'C001')
        self.assertEqual(restored.detail('003','RC_1')['information_requests']['active_count'],1)

    def test_unknown_database_scenario_is_not_silently_copied(self):
        with self.store.connection() as db:
            db.execute("INSERT INTO metadata VALUES('005','UNSUPPORTED','2026-10-19')")
        with self.assertRaisesRegex(ValueError,'005'):self.backup()

    def test_corrupted_or_missing_payload_is_rejected_before_restore(self):
        self.backup()
        path=self.root/'backup/reports/sme_fraud_003/feedback_audit.jsonl'
        original=path.read_bytes();path.write_bytes(original+b'CORRUPT')
        with self.assertRaisesRegex(ValueError,'checksum/inventory'):restore_backup(self.root/'backup',self.root/'restored')
        self.assertFalse((self.root/'restored').exists())
        path.write_bytes(original);path.unlink()
        with self.assertRaises(ValueError):verify_backup(self.root/'backup')

    def test_manifest_and_runtime_contract_are_verified(self):
        self.backup();path=self.root/'backup/backup_manifest.json'
        manifest=json.loads(path.read_text(encoding='utf-8'));manifest['scenarios']=['001']
        path.write_text(json.dumps(manifest),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'manifest checksum'):verify_backup(self.root/'backup')
        manifest.pop('manifest_sha256');manifest['runtime_contract']={};manifest['manifest_sha256']=digest(manifest)
        path.write_text(json.dumps(manifest),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'matching Case Management runtime'):verify_backup(self.root/'backup')

    def test_manifest_path_traversal_is_rejected(self):
        self.backup();path=self.root/'backup/backup_manifest.json'
        manifest=json.loads(path.read_text(encoding='utf-8'))
        manifest.pop('manifest_sha256');manifest['files']['../outside']={'sha256':'x','bytes':0}
        manifest['manifest_sha256']=digest(manifest);path.write_text(json.dumps(manifest),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Invalid backup file path'):verify_backup(self.root/'backup')

    def test_failed_manifest_write_cleans_staging_and_never_publishes(self):
        with patch.object(Path,'write_text',side_effect=OSError('SIM_WRITE_FAILURE')):
            with self.assertRaisesRegex(OSError,'SIM_WRITE_FAILURE'):self.backup()
        self.assertFalse((self.root/'backup').exists())
        self.assertEqual(list(self.root.glob('.review-backup-*')),[])

    def test_stale_sources_or_missing_identity_fail_without_output(self):
        path=self.data/'transactions.csv';original=path.read_bytes();path.write_bytes(original+b'\n')
        with self.assertRaisesRegex(ValueError,'stale'):self.backup()
        path.write_bytes(original)
        (self.report/'case_identity.json').unlink()
        with self.assertRaisesRegex(ValueError,'identity'):self.backup()
        self.assertFalse((self.root/'backup').exists())

    def test_tampered_request_or_feedback_hash_chain_is_rejected(self):
        with self.store.connection() as db:
            db.execute("UPDATE information_request_events SET data=replace(data,'SIM_OWNER','TAMPERED')")
        with self.assertRaises(ValueError):self.backup()
        self.assertFalse((self.root/'backup').exists())

    def test_feedback_chain_corruption_is_rejected(self):
        path=self.report/'feedback_audit.jsonl'
        path.write_text(path.read_text(encoding='utf-8').replace('SIM_REVIEWER','TAMPERED'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'hash chain'):self.backup()

    def test_request_history_survives_changed_scope_and_archives(self):
        from sme_fraud.generate import write_csv
        with (self.report/'case_queue.csv').open(encoding='utf-8-sig',newline='') as stream:cases=list(csv.DictReader(stream))
        cases[0]['max_score']='99';write_csv(self.report/'case_queue.csv',cases);self.store.prepare()
        self.backup();restore_backup(self.root/'backup',self.root/'restored')
        restored=restored_store(self.root/'restored')
        info=restored.detail('003','RC_1')['information_requests']
        self.assertEqual(info['active_count'],0);self.assertEqual(len(info['history']),1)
        self.assertFalse(info['requests'][0]['applies_to_current_scope'])

    def test_source_change_during_copy_and_write_failure_publish_nothing(self):
        from sme_fraud import review_backup
        original=review_backup.copy_checked
        def changing(source,target):
            value=original(source,target)
            if source.name=='transactions.csv':source.write_bytes(source.read_bytes()+b'\n')
            return value
        with patch.object(review_backup,'copy_checked',changing):
            with self.assertRaisesRegex(ValueError,'changed'):self.backup()
        self.assertFalse((self.root/'backup').exists())
        self.assertEqual(list(self.root.glob('.review-backup-*')),[])

    def test_holdout_is_rejected_before_reading(self):
        with patch.object(Path,'open',side_effect=AssertionError('No holdout reads')):
            with self.assertRaisesRegex(ValueError,'005'):
                create_backup(self.root/'sme_fraud_005/x.sqlite3',self.root/'data',self.root/'reports',self.root/'backup')

    def test_restored_source_tampering_does_not_trigger_silent_rebuild(self):
        self.backup();restore_backup(self.root/'backup',self.root/'restored')
        path=self.root/'restored/data/sme_fraud_003/transactions.csv';path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'automatic cache rebuild'):restored_store(self.root/'restored')

    def test_cli_verify_and_restore(self):
        self.backup()
        for args in ([ 'verify','--backup',str(self.root/'backup')],
                     ['restore','--backup',str(self.root/'backup'),'--output',str(self.root/'cli_restored')]):
            with patch('sys.argv',['review_backup',*args]),contextlib.redirect_stdout(io.StringIO()) as captured:main()
            self.assertEqual(json.loads(captured.getvalue())['status'],'verified')
