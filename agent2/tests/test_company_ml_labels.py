"""Regression cases for incremental labels, explicit corrections and snapshot safety."""
import base64
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.company_ml import CompanyML
from sme_fraud.data_import import DataImport
from sme_fraud.feature_contract import digest, sha
from sme_fraud.review_roles import ReviewPrincipal
from company_ml_fixture import CHIEF, ACCOUNTANT, label_text
from test_data_import import import_fixture, upload_rows, csv_bytes


def csv_text(rows):
    return csv_bytes(rows).decode('utf-8-sig')


class CompanyMLLabelsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store,_=import_fixture(Path(self.temp.name));self.ml=CompanyML(self.store)
        importer=DataImport(self.ml)
        preview=importer.preview('003','C001',CHIEF,filename='SIM.csv',expected_revision=None,
            content_base64=base64.b64encode(csv_bytes(upload_rows(count=30))).decode())
        importer.commit('003','C001',CHIEF,token=preview['token'],acknowledge=True)
        with self.store.connection() as db:records=self.ml._data(db,'C001')[2]
        self.rows=list(csv.DictReader(io.StringIO(label_text(records))))
        self.update(self.rows[:15])
    def state(self):return self.ml.status('003','C001',CHIEF)
    def revision(self):return self.state()['data']['revision']
    def update(self,rows,**kw):
        return self.ml.update_labels('003','C001',kw.pop('principal',CHIEF),
            expected_revision=kw.pop('expected_revision',self.revision()),labels_text=csv_text(rows),**kw)
    def preview(self,rows,**kw):
        return self.ml.preview_labels('003','C001',kw.pop('principal',CHIEF),
            expected_revision=kw.pop('expected_revision',self.revision()),labels_text=csv_text(rows),**kw)
    def snapshot(self):
        with self.store.connection() as db:
            data=dict(db.execute('SELECT * FROM company_ml_data WHERE company_id=?',('C001',)).fetchone())
            imports=[tuple(r) for r in db.execute('SELECT * FROM company_ml_imports')]
            versions=[tuple(r) for r in db.execute('SELECT * FROM company_ml_versions')]
            bindings=[tuple(r) for r in db.execute('SELECT * FROM company_ml_bindings')]
            labels=json.loads(data['labels'])
        return data,labels,imports,versions,bindings
    def conflict(self,**changes):return dict(self.rows[0],label='1' if self.rows[0]['label']=='0' else '0',**changes)

    def test_fifteen_then_one_identical_keeps_all_labels_and_revision(self):
        before=self.snapshot();state=self.state()
        result=self.update(self.rows[:1])
        self.assertEqual(result['data']['labels_count'],15)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.state(),state)
        self.assertEqual(result['label_update']['unchanged'],1)

    def test_new_label_adds_to_fifteen_and_keeps_model_features_and_raw_history(self):
        revision=self.revision()
        state=self.ml.evaluate('003','C001',CHIEF,expected_revision=revision,algorithm='ecod',alert_budget=.1,
                              **self.state()['data']['suggested_windows'])
        self.ml.activate('003','C001',CHIEF,expected_revision=revision,expected_active=None,version_id=state['versions'][0]['version_id'])
        before,old,imports,versions,bindings=self.snapshot()
        result=self.update(self.rows[15:16]);after,labels,*unchanged=self.snapshot()
        self.assertEqual(result['data']['labels_count'],16);self.assertNotEqual(result['data']['revision'],revision)
        self.assertTrue(all(labels[tid]==value for tid,value in old.items()))
        for key in ('records','matrix'):self.assertEqual(after[key],before[key])
        self.assertEqual(unchanged,[imports,versions,bindings]);self.assertEqual(result['label_update']['added'],1)

    def test_preview_is_readonly_and_shows_class_and_provenance_conflicts(self):
        before=sha(self.store.database)
        row=dict(self.rows[1],evidence_ref='SIM_NEW_EVIDENCE')
        preview=self.preview([self.conflict(),row,self.rows[15],self.rows[2]])
        self.assertEqual(sha(self.store.database),before)
        self.assertEqual(preview['counts'],dict(existing=15,incoming=4,added=1,unchanged=1,conflicts=2,total=16))
        self.assertEqual(preview['conflicts'][0]['existing']['label'],int(self.rows[0]['label']))
        self.assertEqual(preview['conflicts'][1]['incoming']['evidence_ref'],'SIM_NEW_EVIDENCE')

    def test_conflicting_batch_is_atomic_by_default(self):
        before=sha(self.store.database)
        with self.assertRaisesRegex(ValueError,'xung đột.*000000'):
            self.update([self.rows[15],self.conflict()])
        self.assertEqual(sha(self.store.database),before);self.assertEqual(self.state()['data']['labels_count'],15)

    def test_keep_existing_skips_conflicts_and_adds_unrelated_new_labels(self):
        rows=[self.conflict(),self.rows[15],self.rows[1]];preview=self.preview(rows)
        result=self.update(rows,conflict_policy='keep_existing',preview_hash=preview['preview_hash'])
        labels=self.snapshot()[1]
        self.assertEqual(labels[self.rows[0]['transaction_id']]['label'],int(self.rows[0]['label']))
        self.assertEqual(len(labels),16);self.assertEqual(result['label_update']['skipped'],1)
        self.assertEqual(result['label_update']['updated'],0)

    def test_correction_requires_preview_confirmation_and_reason(self):
        rows=[self.conflict()];preview=self.preview(rows);before=sha(self.store.database)
        for extra in ({},{'preview_hash':preview['preview_hash']},
                      {'preview_hash':preview['preview_hash'],'acknowledge':True},
                      {'preview_hash':preview['preview_hash'],'reason':'SIM correction','acknowledge':'true'}):
            with self.subTest(extra=extra),self.assertRaises((ValueError,RuntimeError)):
                self.update(rows,conflict_policy='replace_conflicts',**extra)
            self.assertEqual(sha(self.store.database),before)

    def test_explicit_correction_keeps_fourteen_unrelated_and_records_old_and_new(self):
        rows=[self.conflict(evidence_ref='SIM_CORRECTED')];preview=self.preview(rows)
        before=self.snapshot()[1]
        result=self.update(rows,conflict_policy='replace_conflicts',preview_hash=preview['preview_hash'],
                           acknowledge=True,reason='SIM: đối chiếu chứng từ mới')
        after=self.snapshot()[1];tid=rows[0]['transaction_id']
        self.assertEqual(len(after),15);self.assertEqual(after[tid]['label'],int(rows[0]['label']))
        for key in before.keys()-{tid}:self.assertEqual(after[key],before[key])
        with self.store.connection() as db:
            event=self.ml._events(db,'C001')[-1]
            audit=json.loads(db.execute('SELECT data FROM company_ml_label_changes WHERE operation_id=?',
                                       (event['details']['operation_id'],)).fetchone()[0])
        self.assertEqual(digest(audit),event['details']['changes_sha256'])
        self.assertEqual(audit['changes'],[dict(transaction_id=tid,previous=before[tid],current=after[tid])])
        self.assertEqual(audit['actor'],CHIEF.user_id);self.assertEqual(audit['reason'],'SIM: đối chiếu chứng từ mới')
        self.assertEqual(result['label_update']['updated'],1)
        self.assertNotIn('changes',result['history'][-1]['details'])

    def test_stale_preview_or_changed_csv_never_overwrites_labels(self):
        rows=[self.conflict()];preview=self.preview(rows)
        with self.assertRaises(RuntimeError):
            self.update([dict(rows[0],evidence_ref='SIM_OTHER')],conflict_policy='keep_existing',preview_hash=preview['preview_hash'])
        self.update(self.rows[15:16]);before=sha(self.store.database)
        with self.assertRaises(RuntimeError):
            self.update(rows,expected_revision=preview['expected_revision'],conflict_policy='replace_conflicts',
                        preview_hash=preview['preview_hash'],acknowledge=True,reason='SIM correction')
        self.assertEqual(sha(self.store.database),before)

    def test_duplicate_empty_malformed_unverified_or_wrong_company_are_atomic(self):
        before=sha(self.store.database);header=csv_text(self.rows[:1]).splitlines()[0]
        bad=[header+'\n','',csv_text([self.rows[0],self.rows[0]]),
             csv_text([dict(self.rows[15],company_id='C002')]),csv_text([dict(self.rows[15],verified='0')]),
             csv_text([dict(self.rows[15],reviewed_at='2099-01-01T00:00:00+07:00')]),
             csv_text([dict(self.rows[15],evidence_ref='')]),csv_text([self.rows[15]]).rstrip()+',EXTRA\n',
             header+',label\n',header+'\nC001,000015,1\n']
        for text in bad:
            with self.subTest(text=text[:80]),self.assertRaises(ValueError):
                self.ml.update_labels('003','C001',CHIEF,expected_revision=self.revision(),labels_text=text)
            self.assertEqual(sha(self.store.database),before)

    def test_equivalent_timezone_is_an_idempotent_resubmission(self):
        row=dict(self.rows[0],reviewed_at=datetime.fromisoformat(self.rows[0]['reviewed_at']).astimezone(timezone.utc).isoformat())
        before=self.snapshot();self.update([row]);self.assertEqual(self.snapshot(),before)

    def test_changed_provenance_requires_conflict_decision_even_when_class_same(self):
        for values in (dict(reviewer_id='SIM_SECOND_REVIEWER'),dict(evidence_ref='SIM_UPDATED_DOCUMENT'),
                       dict(reviewed_at='2024-01-20T12:00:00+07:00')):
            row=dict(self.rows[0],**values)
            self.assertEqual(self.preview([row])['counts']['conflicts'],1)
            with self.assertRaises(ValueError):self.update([row])

    def test_scope_role_and_holdout_remain_enforced(self):
        foreign=ReviewPrincipal('FOREIGN','P','SIM','director',('C002',))
        before=sha(self.store.database)
        for principal in (None,ACCOUNTANT,foreign):
            with self.assertRaises(PermissionError):self.preview(self.rows[:1],principal=principal)
            with self.assertRaises(PermissionError):self.update(self.rows[:1],principal=principal)
        with self.assertRaises(ValueError):
            self.ml.preview_labels('005','C001',CHIEF,expected_revision=self.revision(),labels_text=csv_text(self.rows[:1]))
        self.assertEqual(sha(self.store.database),before)

    def test_audit_tampering_is_detected_without_exposing_label_history(self):
        with self.store.connection() as db:
            db.execute("UPDATE company_ml_label_changes SET data=replace(data,'SIM_DOCUMENT','TAMPERED')")
        with self.assertRaisesRegex(ValueError,'Lịch sử thay đổi nhãn'):self.state()

    def test_backup_restore_retains_labels_correction_history_and_can_merge_again(self):
        from sme_fraud.review_backup import create_backup, restore_backup, restored_store
        rows=[self.conflict()];preview=self.preview(rows)
        self.update(rows,conflict_policy='replace_conflicts',preview_hash=preview['preview_hash'],
                    acknowledge=True,reason='SIM: verified correction for backup test')
        self.store.prepare()  # Bind the master fixtures changed by import_fixture.
        before=self.state();snapshot=self.snapshot()
        with self.store.connection() as db:audits=[tuple(row) for row in db.execute('SELECT * FROM company_ml_label_changes ORDER BY operation_id')]
        root=Path(self.temp.name)
        create_backup(self.store.database,self.store.data_root,self.store.reports_root,root/'backup')
        restore_backup(root/'backup',root/'restored')
        restored=restored_store(root/'restored');restored.clock=self.store.clock
        self.store=restored;self.ml=CompanyML(restored)
        self.assertEqual(self.state(),before);self.assertEqual(self.snapshot(),snapshot)
        with restored.connection() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM company_ml_label_changes ORDER BY operation_id')],audits)
        self.assertEqual(self.update(self.rows[15:16])['data']['labels_count'],16)

    def test_connected_refresh_with_partial_labels_also_merges_and_rejects_conflicts(self):
        state=self.ml.update_data('003','C002',CHIEF,expected_revision=None)
        with self.store.connection() as db:records=self.ml._data(db,'C002')[2]
        rows=list(csv.DictReader(io.StringIO(label_text(records,'C002'))))
        state=self.ml.update_data('003','C002',CHIEF,expected_revision=state['data']['revision'],labels_text=csv_text(rows[:15]))
        state=self.ml.update_data('003','C002',CHIEF,expected_revision=state['data']['revision'],labels_text=csv_text(rows[15:16]))
        self.assertEqual(state['data']['labels_count'],16)
        state=self.ml.update_data('003','C002',CHIEF,expected_revision=state['data']['revision'])
        self.assertEqual(state['data']['labels_count'],16)
        before=sha(self.store.database)
        with self.assertRaisesRegex(ValueError,'xung đột'):
            self.ml.update_data('003','C002',CHIEF,expected_revision=state['data']['revision'],
                labels_text=csv_text([dict(rows[0],evidence_ref='SIM_CONFLICT'),rows[16]]))
        self.assertEqual(sha(self.store.database),before)


if __name__=='__main__':unittest.main()
