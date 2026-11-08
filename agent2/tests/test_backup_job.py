"""Whole-store recovery, P2 WAL snapshots, owned retention and job failures."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from sme_fraud import backup_suite, backup_job
from sme_fraud.backup_suite import create_suite, verify_suite, restore_suite, restored_suite
from sme_fraud.case_identity import digest
from sme_fraud.feedback import feedback_lock
from p2_test_fixture import SOURCE, REPORT
from sme_fraud.p2_controls_web import P2Controls
from sme_fraud.review_backup import sha, read_database
from sme_fraud.review_store import ReviewStore
from test_review import make_fixture


class BackupJobTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.data,self.report=make_fixture(self.root)
        self.store=ReviewStore(self.root/'data',self.root/'reports',self.root/'review.sqlite3')
        self.store.prepare()
        self.now=datetime.now(timezone.utc)
        detail=self.store.detail('003','RC_1')
        self.store.update_information_request('003','RC_1',dict(action='create',expected_hash='',
            case_scope_hash=detail['case']['review_scope_hash'],owner='SIM_OWNER',actor='SIM_ACTOR',
            requested_documents='SIM: invoice',reason='SIM: requested',due_at=(self.now+timedelta(days=2)).isoformat()))
        self.store.save_feedback('003','RC_2','false_positive','SIM_REVIEWER','SIM: checked','')
        self.p2=P2Controls(SOURCE,REPORT,self.root/'p2.sqlite3')
        event=self.note()
        self.p2.save_review(dict(snapshot_id=self.p2.snapshot_id,control_id='FULL_BELOW',
            verdict='needs_information',reviewer='SIM_REVIEWER',reason='SIM: recheck',expected_hash=event['event_hash']))
        P2Controls(SOURCE,REPORT,self.root/'empty_p2.sqlite3')
        self.specs=[dict(id='primary',source=str(SOURCE),report=str(REPORT),database=str(self.p2.database)),
                    dict(id='empty',source=str(SOURCE),report=str(REPORT),database=str(self.root/'empty_p2.sqlite3'))]
        self.raw=dict(version=backup_job.VERSION,job_id='test_review',backup_root=str(self.root/'backups'),
            database=str(self.store.database),data_root=str(self.root/'data'),reports_root=str(self.root/'reports'),
            p2_stores=self.specs,schedule=dict(timezone='Asia/Saigon',daily_at='02:00'),
            retention=dict(days=30,minimum_successful=3),calendar=dict(working_weekdays=list(range(7)),non_working_dates=[]),
            timeout_seconds=120)
        self.config_path=self.root/'config.json'; self.write_config()
        self.owner=dict(version=backup_job.VERSION,job_id='test_review',repository_id='a'*32,source_binding='test')

    def tearDown(self): self.temp.cleanup()

    def note(self):
        return self.p2.save_review(dict(snapshot_id=self.p2.snapshot_id,control_id='FULL_BELOW',verdict='passed',
            reviewer='SIM_REVIEWER',reason='SIM: technical fixture, not independent acceptance',expected_hash=''))

    def write_config(self): self.config_path.write_text(json.dumps(self.raw),encoding='utf-8')

    def suite(self,name='suite'):
        return create_suite(self.store.database,self.root/'data',self.root/'reports',self.specs,
                            self.root/name,owner=self.owner)

    def test_complete_suite_restores_main_history_and_both_p2_journals(self):
        before=self.p2.history(); manifest=self.suite()
        self.assertEqual([row['state']['history_events'] for row in manifest['p2_stores']],[2,0])
        self.assertEqual(len({row['source'] for row in manifest['p2_stores']}),1)
        restore_suite(self.root/'suite',self.root/'restored')
        review,p2=restored_suite(self.root/'restored','primary')
        self.assertEqual(p2.history(),before)
        self.assertEqual(review.detail('003','RC_1')['information_requests']['active_count'],1)
        self.assertEqual(review.detail('003','RC_2')['feedback_history'],self.store.detail('003','RC_2')['feedback_history'])
        self.assertEqual(restored_suite(self.root/'restored','empty')[1].history(),[])
        self.assertEqual(verify_suite(self.root/'suite')['manifest_sha256'],manifest['manifest_sha256'])

    def test_restored_suite_survives_unusable_original_sources_and_p2_database(self):
        self.suite()
        (self.report/'case_identity.json').write_text('BROKEN',encoding='utf-8')
        with self.p2.connect() as db: db.execute("UPDATE reviews SET reason='BROKEN'")
        restore_suite(self.root/'suite',self.root/'restored')
        review,p2=restored_suite(self.root/'restored')
        self.assertEqual(len(p2.history()),2)
        self.assertEqual(review.detail('003','RC_1')['case']['case_id'],'RC_1')
        self.assertNotEqual(p2.source,SOURCE)

    def test_readonly_p2_never_creates_a_missing_database_or_accepts_writes(self):
        missing=self.root/'missing.sqlite3'
        with self.assertRaises(FileNotFoundError): P2Controls(SOURCE,REPORT,missing,readonly=True)
        self.assertFalse(missing.exists())
        ro=P2Controls(SOURCE,REPORT,self.p2.database,readonly=True)
        with self.assertRaises(PermissionError): ro.save_review({})
        self.assertEqual(len(ro.history()),2)

    def test_live_p2_wal_commit_is_preserved_without_copying_wal_sidecars(self):
        with self.p2.connect() as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0],'wal')
            self.assertTrue(Path(str(self.p2.database)+'-wal').is_file())
            manifest=self.suite()
        item=manifest['p2_stores'][0]
        self.assertEqual(item['state']['history_events'],2)
        self.assertFalse(any(name.endswith(('-wal','-shm')) for name in manifest['files']))

    def test_concurrent_p2_commit_does_not_mix_snapshots(self):
        original=backup_suite.p2_state; changed=False
        def state(db,control):
            nonlocal changed
            result=original(db,control)
            if not changed and control.database==self.p2.database:
                changed=True
                self.p2.save_review(dict(snapshot_id=self.p2.snapshot_id,control_id='FULL_EQUAL',verdict='passed',
                    reviewer='SIM',reason='SIM: concurrent',expected_hash=''))
            return result
        with patch.object(backup_suite,'p2_state',state): manifest=self.suite()
        self.assertEqual(manifest['p2_stores'][0]['state']['history_events'],2)
        self.assertEqual(len(self.p2.history()),3)

    def test_broken_p2_history_and_missing_journal_never_publish_a_suite(self):
        with self.p2.connect() as db: db.execute("UPDATE reviews SET reason='TAMPERED'")
        with self.assertRaises(ValueError): self.suite()
        self.assertFalse((self.root/'suite').exists())
        self.assertEqual(list(self.root.glob('.review-backup-*')),[])

    def test_p2_payload_corruption_is_rejected_before_restore(self):
        manifest=self.suite(); item=manifest['p2_stores'][0]
        path=self.root/'suite'/item['database']
        with closing(sqlite3.connect(path)) as db:
            db.execute("UPDATE reviews SET reason='TAMPERED'"); db.commit()
        with self.assertRaisesRegex(ValueError,'inventory/checksum'): restore_suite(self.root/'suite',self.root/'restored')
        self.assertFalse((self.root/'restored').exists())

    def test_runtime_mismatch_is_not_bypassed_for_restore(self):
        self.suite()
        with patch.object(backup_suite,'runtime',return_value={}):
            with self.assertRaisesRegex(ValueError,'matching backup-suite'): verify_suite(self.root/'suite')
            self.assertEqual(verify_suite(self.root/'suite',require_runtime=False)['status'],'complete')

    def test_restore_refuses_overwrite_and_removes_its_own_failed_output(self):
        self.suite(); (self.root/'existing').mkdir()
        with self.assertRaises(FileExistsError): restore_suite(self.root/'suite',self.root/'existing')
        with patch.object(backup_suite,'restore_backup',side_effect=OSError('SIM_DISK')):
            with self.assertRaisesRegex(OSError,'SIM_DISK'): restore_suite(self.root/'suite',self.root/'failed')
        self.assertFalse((self.root/'failed').exists())

    def test_job_success_records_status_and_durable_event(self):
        result=backup_job.run_job(self.config_path)
        self.assertEqual((result['status'],result['exit_code']),('success',0))
        self.assertTrue(backup_job.status(self.config_path)['healthy'])
        root=Path(self.raw['backup_root'])
        self.assertEqual(len((root/'events.jsonl').read_text(encoding='utf-8').splitlines()),1)
        self.assertEqual(json.loads((root/'latest.json').read_text(encoding='utf-8'))['last_success_bundle'],result['bundle'])

    def test_backup_failure_preserves_last_success_and_never_prunes(self):
        first=backup_job.run_job(self.config_path)
        with patch.object(backup_job,'create_suite',side_effect=OSError('SIM_DISK_FULL')),patch.object(backup_job,'prune') as prune:
            failed=backup_job.run_job(self.config_path)
        self.assertEqual(failed['status'],'failed'); prune.assert_not_called()
        self.assertEqual(failed['last_success_bundle'],first['bundle'])
        self.assertTrue(Path(first['bundle']).exists())
        self.assertEqual(failed['consecutive_failures'],1)
        self.assertFalse(backup_job.status(self.config_path)['healthy'])

    def test_overlapping_run_is_skipped_without_overwriting_status(self):
        root=Path(self.raw['backup_root']); root.mkdir()
        with feedback_lock(root): result=backup_job.run_job(self.config_path)
        self.assertEqual(result['status'],'skipped_busy')
        self.assertFalse((root/'latest.json').exists())

    def aged_copies(self):
        result=backup_job.run_job(self.config_path)
        config=backup_job.load_config(self.config_path); owner=backup_job.repository_owner(config)
        for index in range(5):
            folder=config['backup_root']/('run-20240101T000000Z-'+format(index,'08x'))
            shutil.copytree(result['bundle'],folder)
            path=folder/backup_suite.MANIFEST
            manifest=json.loads(path.read_text(encoding='utf-8')); manifest.pop('manifest_sha256')
            manifest['created_at']=(self.now-timedelta(days=40+index)).isoformat()
            manifest['manifest_sha256']=digest(manifest); path.write_text(json.dumps(manifest),encoding='utf-8')
        return config,owner,result

    def test_retention_keeps_thirty_days_and_at_least_three_successes(self):
        config,owner,result=self.aged_copies()
        planned=backup_job.retention_plan(config,owner,self.now+timedelta(hours=1))
        self.assertEqual(len(planned['delete']),3)
        pruned=backup_job.prune(config,owner,self.now+timedelta(hours=1))
        self.assertEqual(len(pruned['deleted']),3)
        self.assertEqual(len(list(config['backup_root'].glob('run-*'))),3)
        self.assertTrue(Path(result['bundle']).exists())

    def test_retention_ignores_manual_foreign_and_tampered_bundles(self):
        config,owner,_=self.aged_copies()
        (config['backup_root']/'manual_keep').mkdir()
        candidates=sorted(config['backup_root'].glob('run-2024*'))
        foreign=candidates[0]; path=foreign/backup_suite.MANIFEST
        manifest=json.loads(path.read_text(encoding='utf-8')); manifest.pop('manifest_sha256')
        manifest['owner']['repository_id']='b'*32; manifest['manifest_sha256']=digest(manifest)
        path.write_text(json.dumps(manifest),encoding='utf-8')
        broken=candidates[1]; (broken/backup_suite.MANIFEST).write_text('{}',encoding='utf-8')
        result=backup_job.prune(config,owner,self.now+timedelta(hours=1))
        self.assertTrue(foreign.exists()); self.assertTrue(broken.exists())
        self.assertTrue((config['backup_root']/'manual_keep').exists()); self.assertTrue(result['warnings'])

    def test_retention_delete_failure_is_reported(self):
        config,owner,_=self.aged_copies()
        with patch.object(backup_job.shutil,'rmtree',side_effect=OSError('SIM_DELETE_DENIED')):
            result=backup_job.prune(config,owner,self.now+timedelta(hours=1))
        self.assertFalse(result['deleted']); self.assertEqual(len(result['warnings']),3)

    def test_missing_schedule_is_reported_after_grace_period(self):
        result=backup_job.run_job(self.config_path)
        last=backup_job.timestamp(result['last_success_at']).astimezone(backup_job.VN)
        late=last.replace(hour=5,minute=0,second=0,microsecond=0)+timedelta(days=2)
        self.assertTrue(backup_job.status(self.config_path,now=late)['overdue'])

    def test_config_rejects_unsafe_roots_holdout_and_invalid_retention(self):
        variations=[dict(backup_root=str(self.root/'data')),dict(backup_root=str(self.root)),
                    dict(backup_root=str(self.root/'data/sme_fraud_005/backups')),
                    dict(retention=dict(days=0,minimum_successful=3)),dict(retention=dict(days=30,minimum_successful=True)),
                    dict(schedule=dict(timezone='UTC',daily_at='02:00')),
                    dict(p2_stores=[self.specs[0],self.specs[0]])]
        for change in variations:
            with self.subTest(change=change):
                raw=deepcopy(self.raw); raw.update(change)
                self.config_path.write_text(json.dumps(raw),encoding='utf-8')
                with self.assertRaises(ValueError): backup_job.load_config(self.config_path)

    def test_repository_cannot_be_silently_rebound_to_other_sources(self):
        backup_job.run_job(self.config_path)
        self.raw['p2_stores']=[self.specs[0]]; self.write_config()
        config=backup_job.load_config(self.config_path)
        with self.assertRaisesRegex(ValueError,'ownership/source'): backup_job.repository_owner(config)

    def test_tampered_restore_receipt_cannot_redirect_a_p2_database(self):
        self.suite(); restore_suite(self.root/'suite',self.root/'restored')
        path=self.root/'restored'/backup_suite.RECEIPT
        receipt=json.loads(path.read_text(encoding='utf-8')); receipt['p2_stores'][0]['database']='../outside.sqlite3'
        path.write_text(json.dumps(receipt),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'receipt checksum'): restored_suite(self.root/'restored')

    def test_failed_health_before_any_run(self):
        self.assertEqual(backup_job.status(self.config_path)['status'],'never_run')

    def test_task_definition_has_vietnam_daily_time_and_limited_interactive_identity(self):
        executable=self.root/'Python With Spaces/pythonw.exe'; executable.parent.mkdir(); executable.touch()
        xml=backup_job.task_xml(self.config_path,executable,'S-1-5-21-123-456-789-1002',
            now=datetime.fromisoformat('2026-10-19T20:00:00+07:00'))
        task=ET.fromstring(xml); ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        text=lambda path:task.find(path,ns).text
        self.assertEqual(text('.//t:StartBoundary'),'2026-10-20T02:00:00+07:00')
        self.assertEqual(text('.//t:DaysInterval'),'1')
        self.assertEqual(text('.//t:LogonType'),'InteractiveToken')
        self.assertEqual(text('.//t:RunLevel'),'LeastPrivilege')
        self.assertEqual(text('.//t:MultipleInstancesPolicy'),'IgnoreNew')
        self.assertEqual(text('.//t:StartWhenAvailable'),'true')
        self.assertEqual(text('.//t:WorkingDirectory'),str(backup_job.ROOT))
        self.assertNotIn('Password',xml)

    def test_task_definition_rejects_unexpected_executable_and_identity(self):
        executable=self.root/'pythonw.exe'; executable.touch()
        with self.assertRaises(ValueError): backup_job.task_xml(self.config_path,executable,'malformed')
        with self.assertRaises(ValueError): backup_job.task_xml(self.config_path,self.root/'missing.exe','S-1-5-21-1002')
