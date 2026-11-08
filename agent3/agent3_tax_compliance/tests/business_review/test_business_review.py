"""Synthetic operator dossiers; no claims of real-product legal accuracy."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import os
import subprocess
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/planning'));sys.path.insert(0,str(APP/'tests/e2e_v1'))
import test_planning as pf
import test_compliance as cf
from src.business_review.contracts import ReviewDossier,ProductReview
from src.business_review.service import prepare,bind_scope
from src.business_review.evidence import verify_files
from src.business_review.repository import BusinessReviewRepository
from src.canonicalization.derive import sha
from src.planning.catalog import load_catalog
from src.planning.contracts import PlanningContext,PurchaseEvidence,DailyPurchases
from src.rules.contracts import PaymentProof
from src.rules.contracts import ExecutionPolicy
from src.rules.models import load_package
from src.rules.context import build
from src.planning.contracts import RuleSet
from src.planning.service import plan
from src.domain.taxpayer import AccessContext
from src.review.contracts import ReviewError


def dossier_for(rec,reviewer='operator'):
    return dict(review_id='review-1',tenant_id=rec.tenant_id,taxpayer_id=rec.taxpayer_id,record_id=rec.record_id,
        record_revision=rec.revision,record_sha256=sha(rec.model_dump(mode='json')),reviewer_id=reviewer,
        reviewed_at='2026-10-16T10:00:00+07:00',review_reference='synthetic-review-not-legal-approval',
        documents=[dict(evidence_id='invoice',relative_path='invoice.pdf',sha256='a'*64,kind='INVOICE'),
            dict(evidence_id='catalogue',relative_path='catalogue.pdf',sha256='b'*64,kind='PRODUCT_CATALOGUE'),
            dict(evidence_id='bank',relative_path='bank.pdf',sha256='c'*64,kind='BANK_STATEMENT')],
        invoice=dict(invoice_kind='VAT',form='ORDINARY',vat_method='DEDUCTION',claim_input_vat=True,
            seller_tax_id_observed='PRESENT_VALUE',document_complete=True,evidence_ids=['invoice']),
        products=[dict(item_id=i.item_id,product_code='SYNTHETIC-SKU-'+str(n),effective_from='2026-01-01',effective_to='2026-10-17',
            base_vat_rate='0.10',annex_i='NOT_EXCLUDED',annex_ii='NOT_EXCLUDED',legal_context_checked=True,
            classification_rationale='Synthetic classification for tests only, not an approved real product.',evidence_ids=['catalogue'])
            for n,i in enumerate(rec.items)],
        payment=dict(case='STANDARD',settlement='VERIFIED_NON_CASH',method='BANK_TRANSFER',seller_tax_id=rec.parties.seller.tax_id.value,
            buyer_tax_id=rec.parties.buyer.tax_id.value,currency='VND',amount=str(rec.totals.gross.value),
            execution_confirmed=True,full_settlement=True,evidence_ids=['bank']))


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.rec,self.q,_,_,_,_,profile,_=pf.fixture()
        self.rules,self.legal,_=load_catalog()
        self.profile=profile.model_copy(update={'absence_fidelity_policies':('complete-content-v1',)})
        self.data=dossier_for(self.rec)

    def run_case(self,data=None,rec=None,profile='default',q=None):
        rec=rec or self.rec
        return prepare(rec,ReviewDossier.model_validate(data or self.data),self.rules,self.legal,
            self.profile if profile=='default' else profile,q or pf.quality_for(rec))

    def check(self,result,family):return next(c for c in result['checks'] if c['rule_id']==family)

    def test_ready_bundle_typed_no_tax_verdict_or_publication(self):
        result=self.run_case()
        self.assertTrue(all(c['readiness']=='READY_FOR_TECHNICAL_CHECK' for c in result['checks']))
        self.assertTrue(all(c['release_blocked'] for c in result['checks']))
        self.assertIsNone(result['tax_verdict']);self.assertTrue(result['technical_only'])
        context=PlanningContext.model_validate(result['planning_context']);self.assertEqual(len(context.classifications),len(self.rec.items))
        proof=PaymentProof.model_validate(result['payment_proof']);self.assertTrue(proof.field.value)
        self.assertTrue(all(v.publication=='DRAFT' for f in self.rules.families for v in f.versions))

    def test_missing_dossier_abstains(self):
        result=prepare(self.rec,None,self.rules,self.legal,self.profile,self.q)
        self.assertTrue(all(c['readiness']=='NEEDS_REVIEW' for c in result['checks']))
        self.assertFalse(result['planning_context']['values']);self.assertIsNone(result['payment_proof'])

    def test_scope_revision_hash_and_unknown_item_rejected(self):
        for update in ({'tenant_id':'other'},{'taxpayer_id':'other'},{'record_id':'other'},
            {'record_revision':999},{'record_sha256':'0'*64}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.run_case({**self.data,**update})
        data=json.loads(json.dumps(self.data));data['products'][0]['item_id']='unknown'
        with self.assertRaises(ValueError):self.run_case(data)

    def test_missing_date_and_outside_horizon_do_not_select_rule(self):
        for day in (None,date(2026,10,17)):
            rec=self.rec.model_copy(update={'invoice':self.rec.invoice.model_copy(update={'issue_date':pf.human(day) if day else None})})
            data=dossier_for(rec)
            result=self.run_case(data,rec)
            self.assertTrue(all(c['rule_version'] is None for c in result['checks']))
            self.assertTrue(all(c['readiness']=='NEEDS_REVIEW' for c in result['checks']))

    def test_special_or_unknown_invoice_no_presence_binding(self):
        for form in ('SPECIAL','UNKNOWN'):
            self.data['invoice']['form']=form;result=self.run_case()
            self.assertEqual(self.check(result,'INV_CONTENT_001')['reason'],'SPECIAL_OR_UNKNOWN_INVOICE_FORM')
            self.assertFalse(result['planning_context']['observations'])
            self.assertNotIn('context.invoice_kind',[v['path'] for v in result['planning_context']['values']])

    def test_complete_review_and_source_capability_required(self):
        self.data['invoice']['document_complete']=False
        self.assertEqual(self.check(self.run_case(),'INV_CONTENT_001')['readiness'],'NEEDS_REVIEW')
        self.data['invoice']['document_complete']=True
        self.assertEqual(self.check(self.run_case(profile=None),'INV_CONTENT_001')['readiness'],'NEEDS_REVIEW')

    def test_confirmed_absent_requires_missing_not_ambiguous_or_present(self):
        self.data['invoice']['seller_tax_id_observed']='CONFIRMED_ABSENT'
        self.assertEqual(self.check(self.run_case(),'INV_CONTENT_001')['reason'],'REVIEW_CONFLICTS_WITH_CFR')
        for field in (None,pf.human('1234567890').model_copy(update={'value':None,'status':'AMBIGUOUS'})):
            rec=self.rec.model_copy(update={'parties':self.rec.parties.model_copy(update={'seller':self.rec.parties.seller.model_copy(update={'tax_id':field})})})
            data=dossier_for(self.rec);data['record_sha256']=sha(rec.model_dump(mode='json'));data['invoice']['seller_tax_id_observed']='CONFIRMED_ABSENT'
            result=self.run_case(data,rec)
            expected='READY_FOR_TECHNICAL_CHECK' if field is None else 'NEEDS_REVIEW'
            self.assertEqual(self.check(result,'INV_CONTENT_001')['readiness'],expected)

    def test_invoice_label_cannot_supply_product_or_payment_proof(self):
        self.data['products'][0]['evidence_ids']=['invoice'];self.data['payment']['evidence_ids']=['invoice']
        result=self.run_case();self.assertEqual(self.check(result,'VAT_RATE_001')['reason'],'INDEPENDENT_PRODUCT_EVIDENCE_REQUIRED')
        self.assertIsNone(result['payment_proof'])

    def test_same_product_classification_independent_of_printed_rate(self):
        for rate in ('0.08','0.10'):
            item=self.rec.items[0].model_copy(update={'vat_rate':pf.human(Decimal(rate))})
            rec=self.rec.model_copy(update={'items':(item,)})
            result=self.run_case(dossier_for(rec),rec)
            self.assertEqual(result['planning_context']['classifications'][0]['category']['value'],'REDUCTION_CANDIDATE')
            reason=self.check(result,'VAT_RATE_001')['reason']
            self.assertEqual(reason,'PRODUCT_REVIEWED' if rate=='0.08' else 'RATE_DIFFERS_FROM_SCOPED_EIGHT_PERCENT')

    def test_exclusions_not_forced_to_ten_percent(self):
        for annex in ('annex_i','annex_ii'):
            self.data['products'][0][annex]='EXCLUDED'
            result=self.run_case();c=self.check(result,'VAT_RATE_001')
            self.assertEqual(c['readiness'],'NOT_IN_SCOPE');self.assertIn('NOT_GENERAL_RATE_VERDICT',c['reason'])
            self.data['products'][0][annex]='NOT_EXCLUDED'

    def test_unknown_annex_unreviewed_context_or_interval_needs_review(self):
        for update in ({'annex_i':'UNKNOWN'},{'annex_ii':'UNKNOWN'},{'legal_context_checked':False},
            {'effective_to':'2026-02-01'}):
            data=json.loads(json.dumps(self.data));data['products'][0].update(update)
            self.assertEqual(self.check(self.run_case(data),'VAT_RATE_001')['readiness'],'NEEDS_REVIEW')

    def test_base_rate_five_percent_not_reduced_again(self):
        self.data['products'][0]['base_vat_rate']='0.05'
        self.assertEqual(self.check(self.run_case(),'VAT_RATE_001')['reason'],'BASE_RATE_NOT_TEN_PERCENT')

    def test_kct_kkknt_and_direct_outside_this_check(self):
        for treatment in ('KCT','KKKNT'):
            item=self.rec.items[0].model_copy(update={'vat_treatment':pf.human(treatment),'vat_rate':None})
            rec=self.rec.model_copy(update={'items':(item,)})
            self.assertEqual(self.check(self.run_case(dossier_for(rec),rec),'VAT_RATE_001')['readiness'],'NOT_IN_SCOPE')
        self.data['invoice']['vat_method']='DIRECT'
        self.assertEqual(self.check(self.run_case(),'VAT_RATE_001')['readiness'],'NOT_IN_SCOPE')

    def test_payment_special_unknown_unsettled_partial_and_unexecuted_abstain(self):
        for update in ({'case':'SPECIAL'},{'case':'UNKNOWN'},{'settlement':'UNSETTLED'},
            {'full_settlement':False},{'execution_confirmed':False},{'amount':'1'}):
            data=json.loads(json.dumps(self.data));data['payment'].update(update)
            result=self.run_case(data);self.assertIsNone(result['payment_proof'])
            self.assertEqual(self.check(result,'VAT_NON_CASH_PAYMENT_001')['readiness'],'NEEDS_REVIEW')

    def test_payment_mismatch_seller_and_buyer_abstains(self):
        for key in ('seller_tax_id','buyer_tax_id'):
            data=json.loads(json.dumps(self.data));data['payment'][key]='1111111111'
            self.assertEqual(self.check(self.run_case(data),'VAT_NON_CASH_PAYMENT_001')['reason'],'PAYMENT_PARTIES_MISMATCH')

    def test_cash_requires_separate_receipt_then_binds_false(self):
        self.data['payment'].update(settlement='VERIFIED_CASH',method='CASH')
        self.assertIsNone(self.run_case()['payment_proof'])
        self.data['documents'][2]['kind']='CASH_RECEIPT'
        self.assertFalse(self.run_case()['payment_proof']['field']['value'])

    def test_cash_deposit_to_seller_is_never_non_cash(self):
        self.data['payment']['method']='CASH_DEPOSIT_TO_SELLER'
        self.assertIsNone(self.run_case()['payment_proof'])
        self.data['payment']['settlement']='VERIFIED_CASH'
        self.assertFalse(self.run_case()['payment_proof']['field']['value'])

    def test_low_confidence_and_stale_quality_not_bypassed(self):
        q=self.q.model_copy(update={'fields':tuple(v.model_copy(update={'reliability':'UNAVAILABLE'}) for v in self.q.fields)})
        result=self.run_case(q=q)
        self.assertTrue(all(c['readiness']=='NEEDS_REVIEW' for c in result['checks']))
        with self.assertRaises(ValueError):self.run_case(q=self.q.model_copy(update={'input_sha256':'0'*64}))

    def test_daily_ledger_context_is_scoped_and_completeness_not_invented(self):
        rec=self.rec
        row=PurchaseEvidence(tenant_id=rec.tenant_id,taxpayer_id=rec.taxpayer_id,record_id=rec.record_id,
            revision=rec.revision,input_sha256=sha(rec.model_dump(mode='json')),issue_date=rec.invoice.issue_date.value,
            seller_tax_id=rec.parties.seller.tax_id.value.replace('-',''),gross=rec.totals.gross.value)
        ledger=DailyPurchases(version='synthetic-ledger',complete=False,verification_reference='synthetic',purchases=(row,))
        self.data['daily']=dict(ledger=ledger.model_dump(mode='json'),evidence_ids=['bank'])
        context=PlanningContext.model_validate(self.run_case()['planning_context'])
        self.assertFalse(context.daily.complete)
        self.data['daily']['ledger']['purchases'][0]['taxpayer_id']='other'
        with self.assertRaises(ValueError):self.run_case()

    def test_currency_and_negative_or_unusable_total_cannot_produce_payment_proof(self):
        for update in ({'currency':pf.human('USD')},{'totals':self.rec.totals.model_copy(update={'gross':pf.human(Decimal('-1'))})}):
            rec=self.rec.model_copy(update=update);data=dossier_for(self.rec)
            data['record_sha256']=sha(rec.model_dump(mode='json'))
            self.assertIsNone(self.run_case(data,rec)['payment_proof'])

    def test_prepared_inputs_reach_real_zen_only_in_test_approved_scope(self):
        # Exercise prepared context through planner -> binding -> native ZEN, not a mock verdict.
        self.rec=self.rec.model_copy(update={'totals':self.rec.totals.model_copy(update={'gross':pf.human(Decimal('5000000'))})})
        self.q=pf.quality_for(self.rec);self.data=dossier_for(self.rec)
        result=self.run_case();context=PlanningContext.model_validate(result['planning_context'])
        rules=RuleSet(version='SYNTHETIC_ONLY',families=tuple(f.model_copy(update={'versions':tuple(v.model_copy(update={
            'publication':'APPROVED_TECHNICAL','review_reference':'SYNTHETIC_ONLY'}) for v in f.versions)}) for f in self.rules.families))
        taxonomy=load_catalog()[2]
        vat_rule=next(f for f in rules.families if f.rule_id=='VAT_RATE_001').versions[-1]
        taxonomy=taxonomy.model_copy(update={'categories':tuple(c.model_copy(update={'legal_basis':vat_rule.legal_basis}) for c in taxonomy.categories)})
        master=pf.fixture()[2]
        planned=plan(self.rec,self.q,master,rules,self.legal,self.profile,taxonomy,context)
        inputs={k:v.model_dump(mode='json') for k,v in [('record',self.rec),('quality',self.q),('master',master),
            ('ruleset',rules),('legal',self.legal),('profile',self.profile),('taxonomy',taxonomy),('context',context)]}
        package=load_package();count=0
        for entry in planned.entries:
            self.assertEqual(entry.eligibility,'ELIGIBLE')
            model=next(m for m in package.models if (m.rule_id,m.rule_version)==(entry.rule_id,entry.rule_version)).model_copy(update={
                'publication':'APPROVED_TECHNICAL','review_reference':'SYNTHETIC_ONLY'})
            bound=build(planned,entry,model,inputs,payment=PaymentProof.model_validate(result['payment_proof']))
            self.assertEqual(cf.rf.native(model,bound,ExecutionPolicy())[0],'PASS');count+=1
        self.assertEqual(count,2+len(self.rec.items))


class DossierContractTests(unittest.TestCase):
    def setUp(self):self.rec=pf.fixture()[0];self.data=dossier_for(self.rec)

    def test_unknown_refs_duplicate_items_timezone_and_strict_bools(self):
        for key,value in [('reviewed_at','2026-10-16T10:00:00'),('record_revision',True)]:
            with self.assertRaises(ValidationError):ReviewDossier.model_validate({**self.data,key:value})
        self.data['products'].append(self.data['products'][0])
        with self.assertRaises(ValidationError):ReviewDossier.model_validate(self.data)
        self.data=dossier_for(self.rec);self.data['invoice']['evidence_ids']=['unknown']
        with self.assertRaises(ValidationError):ReviewDossier.model_validate(self.data)
        self.data=dossier_for(self.rec);self.data['invoice']['document_complete']='true'
        with self.assertRaises(ValidationError):ReviewDossier.model_validate(self.data)

    def test_review_cannot_span_annex_year_boundary(self):
        self.data['products'][0]['effective_from']='2025-07-01'
        with self.assertRaises(ValidationError):ReviewDossier.model_validate(self.data)

    def test_file_hash_and_traversal_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for doc in self.data['documents']:
                (root/doc['relative_path']).write_bytes(b'synthetic');doc['sha256']=hashlib.sha256(b'synthetic').hexdigest()
            self.assertEqual(len(verify_files(ReviewDossier.model_validate(self.data),root)),3)
            (root/'bank.pdf').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_files(ReviewDossier.model_validate(self.data),root)
            for path in ('../other.pdf','C:\\outside.pdf','/outside.pdf'):
                self.data['documents'][0]['relative_path']=path
                with self.assertRaises(ValueError):verify_files(ReviewDossier.model_validate(self.data),root)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=cf.ComplianceTests('test_default_catalog_no_false_tax_pass_and_capture_export_works')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.repo=BusinessReviewRepository(self.fixture.settings)
        self.ctx=self.fixture.ctx;self.payer=self.fixture.payer;self.record_id=self.fixture.record_id

    def test_http_readiness_auth_and_no_assertion_intake(self):
        self.fixture.run_evaluation()
        url='/v1/records/'+self.record_id+'/business-readiness?taxpayer_id='+self.payer
        response=self.fixture.client.get(url,headers=self.fixture.headers)
        self.assertEqual(response.status_code,200);self.assertIsNone(response.json()['tax_verdict'])
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.assertEqual(self.fixture.client.get(url).status_code,401)
        self.assertEqual(self.fixture.client.post(url,json=dossier_for(pf.fixture()[0]),headers=self.fixture.headers).status_code,405)
        self.assertEqual(self.fixture.client.get(url.replace(self.payer,'other'),headers=self.fixture.headers).status_code,403)

    def test_import_immutable_hash_bound_and_reviewer_authenticated(self):
        rec=self.repo.base.record(self.ctx,self.payer,self.record_id)
        data=dossier_for(pf.fixture()[0],self.ctx.actor_id)
        data.update(tenant_id=rec.tenant_id,taxpayer_id=rec.taxpayer_id,record_id=rec.record_id,
            record_revision=rec.revision,record_sha256=sha(rec.model_dump(mode='json')),invoice=None,products=[],payment=None)
        # Local supplemental catalogue, not an invented captured-invoice source.
        data['documents']=[dict(evidence_id='doc',relative_path='doc.txt',sha256=hashlib.sha256(b'synthetic').hexdigest(),kind='OTHER')]
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'doc.txt').write_bytes(b'synthetic')
            d=ReviewDossier.model_validate(data)
            self.assertTrue(self.repo.import_local(self.ctx,self.payer,self.record_id,d,directory)['imported'])
            self.repo.import_local(self.ctx,self.payer,self.record_id,d,directory)
            self.assertEqual(self.repo.latest(self.ctx,self.payer,rec),d)
            with self.assertRaises(ReviewError):self.repo.import_local(self.ctx,self.payer,self.record_id,d.model_copy(update={'review_reference':'changed'}),directory)
            with self.assertRaises(ValueError):self.repo.import_local(self.ctx,self.payer,self.record_id,d.model_copy(update={'reviewer_id':'forged'}),directory)
            with self.repo.db() as db:db.execute("UPDATE business_reviews SET payload='{}'")
            with self.assertRaises(ValueError):self.repo.latest(self.ctx,self.payer,rec)

    def test_legacy_evaluation_replay_unchanged(self):
        evaluation=self.fixture.run_evaluation();artifact=self.fixture.workflow.artifact(self.ctx,self.payer,evaluation.evaluation_id)
        self.repo.assess(self.ctx,self.payer,self.record_id)
        self.assertEqual(self.fixture.workflow.artifact(self.ctx,self.payer,evaluation.evaluation_id),artifact)
        self.assertTrue(self.fixture.workflow.replay(self.ctx,self.payer,evaluation.evaluation_id)['verified'])

    def local_data(self):
        rec=self.repo.base.record(self.ctx,self.payer,self.record_id)
        data=dossier_for(pf.fixture()[0],self.ctx.actor_id)
        data.update(tenant_id=rec.tenant_id,taxpayer_id=rec.taxpayer_id,record_id=rec.record_id,
            record_revision=rec.revision,record_sha256=sha(rec.model_dump(mode='json')),invoice=None,products=[],payment=None)
        return rec,data

    def test_captured_invoice_bytes_required_and_revision_change_hides_dossier(self):
        rec,data=self.local_data();source,raw=self.repo.base.source(self.ctx,self.payer,rec.source_id)
        data['documents']=[dict(evidence_id='invoice',relative_path='invoice.pdf',sha256=source.sha256,kind='INVOICE')]
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'invoice.pdf';file.write_bytes(raw)
            dossier=ReviewDossier.model_validate(data)
            self.repo.import_local(self.ctx,self.payer,self.record_id,dossier,directory)
            self.assertIsNone(self.repo.latest(self.ctx,self.payer,rec.model_copy(update={'revision':rec.revision+1})))
            file.write_bytes(b'other invoice');data['review_id']='review-other';data['documents'][0]['sha256']=hashlib.sha256(b'other invoice').hexdigest()
            with self.assertRaises(ValueError):self.repo.import_local(self.ctx,self.payer,self.record_id,ReviewDossier.model_validate(data),directory)

    def test_local_cli_import_then_assess_against_real_database(self):
        self.fixture.run_evaluation();rec,data=self.local_data()
        data['documents']=[dict(evidence_id='doc',relative_path='doc.txt',sha256=hashlib.sha256(b'synthetic').hexdigest(),kind='OTHER')]
        env={**os.environ,'CAPTURE_DATABASE_PATH':str(self.fixture.settings.database_path),
            'CAPTURE_AUTH_GRANTS_JSON':json.dumps([g.model_dump(mode='json') for g in self.fixture.settings.auth_grants]),
            'AGENT3_ACCESS_TOKEN':self.fixture.fixture.fixture.fixture.token}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'doc.txt').write_bytes(b'synthetic');(root/'review.json').write_text(json.dumps(data),encoding='utf-8')
            base=[sys.executable,'-m','src.business_review.cli']
            common=['--taxpayer-id',self.payer,'--record-id',self.record_id,'--output',str(root/'out.json')]
            imported=subprocess.run(base+['import',*common,'--dossier',str(root/'review.json'),'--evidence-root',directory],cwd=APP,env=env,capture_output=True,text=True)
            self.assertEqual(imported.returncode,0,imported.stderr)
            assessed=subprocess.run(base+['assess',*common],cwd=APP,env=env,capture_output=True,text=True)
            self.assertEqual(assessed.returncode,0,assessed.stderr)
            result=json.loads((root/'out.json').read_text(encoding='utf-8'))
            self.assertIsNotNone(result['dossier_sha256']);self.assertIsNone(result['tax_verdict'])
            self.assertTrue(all(e['eligibility']!='ELIGIBLE' for e in result['draft_plan']['entries']))

    def test_stale_other_invoice_in_daily_ledger_rejected_after_import(self):
        rec,data=self.local_data();row=pf.fixture()[0]
        # All row fields are coherent with the saved record at import, then revision changes.
        purchase=PurchaseEvidence(tenant_id=rec.tenant_id,taxpayer_id=rec.taxpayer_id,record_id=rec.record_id,
            revision=rec.revision,input_sha256=sha(rec.model_dump(mode='json')),issue_date=rec.invoice.issue_date.value,
            seller_tax_id=rec.parties.seller.tax_id.value.replace('-',''),gross=rec.totals.gross.value)
        data['daily']=dict(ledger=DailyPurchases(version='ledger',complete=True,verification_reference='synthetic',purchases=(purchase,)).model_dump(mode='json'),evidence_ids=['bank'])
        dossier=ReviewDossier.model_validate(data)
        self.repo.verify_daily(self.ctx,self.payer,dossier)
        with patch.object(self.repo.base,'record',return_value=rec.model_copy(update={'revision':999})):
            with self.assertRaises(ValueError):self.repo.verify_daily(self.ctx,self.payer,dossier)

    def test_read_only_identity_cannot_import_and_unknown_sidecar_refused(self):
        rec,data=self.local_data()
        readonly=self.ctx.model_copy(update={'permissions':frozenset({'READ'})})
        with self.assertRaises(PermissionError):self.repo.import_local(readonly,self.payer,self.record_id,ReviewDossier.model_validate(data),APP)
        with sqlite3.connect(self.repo.path) as db:db.execute('CREATE TABLE unrelated(id INTEGER)')
        with self.assertRaises(ValueError):
            with self.repo.db():pass

    def test_supplemental_bytes_retained_and_tampering_detected(self):
        rec,data=self.local_data();pin=hashlib.sha256(b'synthetic').hexdigest()
        data['documents']=[dict(evidence_id='doc',relative_path='doc.txt',sha256=pin,kind='OTHER')]
        dossier=ReviewDossier.model_validate(data)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'doc.txt';path.write_bytes(b'synthetic')
            self.repo.import_local(self.ctx,self.payer,self.record_id,dossier,directory)
            path.write_bytes(b'changed external file')
            self.assertEqual(self.repo.latest(self.ctx,self.payer,rec),dossier)
        retained=self.repo.evidence_directory(self.ctx,self.payer)/pin
        self.assertEqual(retained.read_bytes(),b'synthetic')
        retained.write_bytes(b'changed archive')
        with self.assertRaises(ValueError):self.repo.latest(self.ctx,self.payer,rec)


if __name__=='__main__':unittest.main()
