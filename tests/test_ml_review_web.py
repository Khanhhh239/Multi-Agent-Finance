"""Blinded scoped reviews, timer accounting, concurrent tabs and durable results."""
import base64
import csv
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sme_fraud.company_ml import CompanyML
from sme_fraud.company_ml_comparison import compare,collect
from sme_fraud.data_import import DataImport
from sme_fraud.ml_review_packets import load_packet
from sme_fraud.ml_review_web import MLReview
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.feature_contract import sha
from company_ml_fixture import CHIEF,ACCOUNTANT
from test_data_import import import_fixture,upload_rows,csv_bytes
from test_company_ml_comparison import WINDOWS

FORM=dict(useful='yes',business_action='SIM: đối chiếu chứng từ và yêu cầu điều chỉnh có căn cứ',rationale='SIM: dữ kiện kiểm thử',evidence_refs='SIM_DOCUMENT')


def packet_fixture(root,review_count=2,algorithms=None):
    store,_=import_fixture(root/'source');ml=CompanyML(store);importer=DataImport(ml)
    for company in ('C001','C002'):
        preview=importer.preview('003',company,CHIEF,filename='SIM.csv',content_base64=base64.b64encode(csv_bytes(upload_rows(company,count=30))).decode(),expected_revision=None)
        importer.commit('003',company,CHIEF,token=preview['token'],acknowledge=True)
    packet=root/'packet'
    compare(store.database,packet,companies=['C001','C002'],scenario='003',windows=WINDOWS,review_count=review_count,
            source_kind='synthetic_demo',algorithms=algorithms or ['ecod','isolation_forest'])
    return packet


class MLReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.shared.cleanup)
        cls.packet=packet_fixture(Path(cls.shared.name));cls.packet_data=load_packet(cls.packet)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store,_=import_fixture(self.root/'work')
        self.store.prepare()
        self.now=[datetime.now(timezone.utc)+timedelta(seconds=5)]
        self.service=MLReview(self.store,[self.packet],clock=lambda:self.now[0],qa=True)
        self.pid=self.packet_data['packet_id'];self.rid=self.service.units(self.pid,CHIEF,'C001')['items'][0]['review_id']
    def advance(self,seconds):self.now[0]+=timedelta(seconds=seconds)
    def detail(self,rid=None,person=CHIEF):return self.service.detail(self.pid,rid or self.rid,person)
    def timer(self,action,revision,token='',rid=None,person=CHIEF):
        return self.service.timer(self.pid,rid or self.rid,person,action=action,expected_revision=revision,timer_token=token)
    def complete(self,rid=None,form=None,person=CHIEF):
        rid=rid or self.rid;work=self.detail(rid,person)['work']
        result=self.timer('start',work['revision'],rid=rid,person=person);self.advance(3)
        paused=self.timer('pause',result['work']['revision'],result['timer_token'],rid,person)
        return self.service.save(self.pid,rid,person,expected_revision=paused['work']['revision'],form=form or FORM,submit=True,acknowledge=True)

    def test_packet_is_copied_without_touching_frozen_files_and_public_views_are_blinded(self):
        before=sha(self.packet/'manifest.json');self.assertEqual(self.service.import_packet(self.packet),self.pid)
        self.assertEqual(sha(self.packet/'manifest.json'),before)
        info=self.service.overview(ACCOUNTANT);self.assertEqual(info['packets'][0]['companies'],['C001'])
        data=self.detail(person=ACCOUNTANT);text=json.dumps(data)
        for key in ('algorithm','anomaly_score','rank','threshold','selected_review_ids','token_hash'):
            self.assertNotIn('"'+key+'"',text)
        self.assertNotIn('ecod',text);self.assertEqual(data['work']['status'],'unstarted')

    def test_timer_pause_resume_counts_active_segments_and_not_paused_time(self):
        started=self.timer('start',0);token=started['timer_token'];self.advance(10)
        tick=self.timer('heartbeat',started['work']['revision'],token);self.assertEqual(tick['work']['timer']['confirmed_ms'],10000)
        self.advance(5);paused=self.timer('pause',tick['work']['revision'],token)
        self.assertEqual(paused['work']['timer']['confirmed_ms'],15000)
        self.advance(200);self.assertEqual(self.detail()['work']['timer']['elapsed_ms'],15000)
        resumed=self.timer('start',paused['work']['revision']);self.advance(3)
        last=self.timer('pause',resumed['work']['revision'],resumed['timer_token'])
        self.assertEqual(last['work']['timer']['confirmed_ms'],18000)

    def test_connection_loss_expires_and_drops_unconfirmed_gap(self):
        started=self.timer('start',0);self.advance(10)
        tick=self.timer('heartbeat',started['work']['revision'],started['timer_token']);self.advance(50)
        view=self.detail()['work'];self.assertTrue(view['timer']['expired']);self.assertFalse(view['timer']['running'])
        self.assertEqual(view['timer']['confirmed_ms'],10000)
        paused=self.timer('pause',tick['work']['revision'],started['timer_token'])
        self.assertEqual(paused['work']['timer']['confirmed_ms'],10000)

    def test_recover_after_reload_does_not_credit_unconfirmed_tail(self):
        started=self.timer('start',0);self.advance(8)
        tick=self.timer('heartbeat',started['work']['revision'],started['timer_token']);self.advance(4)
        recovered=self.timer('recover',tick['work']['revision'])
        self.assertEqual(recovered['work']['timer']['confirmed_ms'],8000);self.assertFalse(recovered['work']['timer']['running'])
        with self.assertRaises(PermissionError):self.timer('heartbeat',recovered['work']['revision'],started['timer_token'])

    def test_concurrent_tabs_and_foreign_nonce_cannot_double_count(self):
        started=self.timer('start',0);self.advance(2)
        with self.assertRaises(RuntimeError):self.timer('start',0)
        with self.assertRaises(RuntimeError):self.timer('start',started['work']['revision'])
        with self.assertRaises(PermissionError):self.timer('heartbeat',started['work']['revision'],'other-token')
        first=self.timer('heartbeat',started['work']['revision'],started['timer_token'])
        with self.assertRaises(RuntimeError):self.timer('heartbeat',started['work']['revision'],started['timer_token'])
        self.assertEqual(first['work']['timer']['confirmed_ms'],2000)

    def test_scope_identity_and_ownership_are_enforced(self):
        with self.assertRaises(PermissionError):self.service.overview(None)
        c2=self.service.units(self.pid,CHIEF,'C002')['items'][0]['review_id']
        with self.assertRaises(PermissionError):self.detail(c2,ACCOUNTANT)
        self.timer('start',0,person=ACCOUNTANT)
        with self.assertRaises(PermissionError):self.timer('recover',1,person=CHIEF)
        changed=ReviewPrincipal(ACCOUNTANT.user_id,'DIFFERENT_PERSON','other','accountant',('C001',))
        with self.assertRaises(PermissionError):self.timer('recover',1,person=changed)

    def test_submission_requires_measured_time_acknowledgement_and_specific_action(self):
        with self.assertRaises(ValueError):self.service.save(self.pid,self.rid,CHIEF,expected_revision=0,form=FORM,submit=True,acknowledge=True)
        started=self.timer('start',0)
        with self.assertRaises(ValueError):self.service.save(self.pid,self.rid,CHIEF,expected_revision=1,form=FORM,submit=True,acknowledge=True)
        self.advance(2);paused=self.timer('pause',1,started['timer_token']);revision=paused['work']['revision']
        for values in (FORM|dict(business_action=''),FORM|dict(rationale=''),FORM|dict(evidence_refs='')):
            with self.assertRaises(ValueError):self.service.save(self.pid,self.rid,CHIEF,expected_revision=revision,form=values,submit=True,acknowledge=True)
        with self.assertRaises(ValueError):self.service.save(self.pid,self.rid,CHIEF,expected_revision=revision,form=FORM,submit=True)
        with self.assertRaises(ValueError):self.service.save(self.pid,self.rid,CHIEF,expected_revision=revision,form=FORM|dict(active_review_minutes=999),submit=True,acknowledge=True)

    def test_draft_and_completed_result_survive_service_restart(self):
        started=self.timer('start',0);self.advance(5);paused=self.timer('pause',1,started['timer_token'])
        draft=self.service.save(self.pid,self.rid,CHIEF,expected_revision=paused['work']['revision'],form={'rationale':'SIM draft'})
        self.service=MLReview(self.store,clock=lambda:self.now[0],qa=True)
        view=self.detail();self.assertEqual(view['work']['form']['rationale'],'SIM draft');self.assertEqual(view['work']['timer']['confirmed_ms'],5000)
        saved=self.service.save(self.pid,self.rid,CHIEF,expected_revision=draft['work']['revision'],form=FORM,submit=True,acknowledge=True)
        self.assertEqual(saved['work']['status'],'reviewed')
        self.assertEqual(self.detail()['work']['owner']['user_id'],CHIEF.user_id)

    def test_summary_hides_model_names_until_scoped_reviews_are_complete(self):
        manager=ReviewPrincipal('C1_MANAGER','C1_PERSON','manager','director',('C001',))
        result=self.service.summary(self.pid,manager);self.assertEqual(result['metrics'],[]);self.assertFalse(result['complete'])
        with self.assertRaises(PermissionError):self.service.summary(self.pid,ACCOUNTANT)
        items=self.service.units(self.pid,manager)['items']
        for i,unit in enumerate(items):self.complete(unit['review_id'],FORM|dict(useful='unknown' if i==0 else 'yes'))
        result=self.service.summary(self.pid,manager);self.assertTrue(result['complete'])
        self.assertAlmostEqual(result['total_unique_review_minutes'],len(items)*3/60)
        self.assertTrue(all(m['company_id']=='C001' for m in result['metrics']));self.assertIsNone(result['business_winner'])
        self.assertTrue(any(m['unknown'] for m in result['metrics']))

    def test_csv_export_matches_frozen_collector_and_does_not_create_fraud_labels(self):
        self.complete();text=self.service.export(self.pid,CHIEF)
        rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))));done=[r for r in rows if r['human_verified']]
        self.assertEqual(len(done),1);self.assertEqual(done[0]['reviewer_id'],CHIEF.user_id)
        self.assertEqual(float(done[0]['active_review_minutes']),3/60);self.assertNotIn('label',done[0])
        path=self.root/'reviews.csv';path.write_text(text,encoding='utf-8')
        result=collect(self.packet,path,self.root/'collected',now=self.now[0]+timedelta(seconds=1))
        self.assertEqual(result['completed_human_reviews'],1)

    def test_unlisted_evidence_and_tampered_state_are_rejected(self):
        clone=self.root/'tampered';shutil.copytree(self.packet,clone)
        (clone/'public/evidence/unlisted.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):self.service.import_packet(clone)
        with self.assertRaises(ValueError):collect(clone,clone/'human_reviews.csv',self.root/'bad_results')
        self.timer('start',0)
        with self.store.connection() as db:
            row=db.execute('SELECT data FROM ml_review_work').fetchone();state=json.loads(row[0]);state['confirmed_ms']=100000
            db.execute('UPDATE ml_review_work SET data=?',(json.dumps(state),))
        with self.assertRaises(ValueError):self.detail()

    def test_backup_restore_retains_packet_draft_timer_and_review_result(self):
        from sme_fraud.review_backup import create_backup,restore_backup,restored_store
        self.complete();before=self.detail()
        create_backup(self.store.database,self.store.data_root,self.store.reports_root,self.root/'backup')
        restore_backup(self.root/'backup',self.root/'restored');restored=restored_store(self.root/'restored')
        service=MLReview(restored,clock=lambda:self.now[0],qa=True)
        self.assertEqual(service.detail(self.pid,self.rid,CHIEF),before)


if __name__=='__main__':unittest.main()
