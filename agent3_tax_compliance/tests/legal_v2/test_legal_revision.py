"""Source-linked business cases; synthetic records and test-only model approval."""
import hashlib
import json
import sys
import unittest
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError

APP=Path(__file__).resolve().parents[2];ROOT=APP.parent
sys.path.insert(0,str(APP))
sys.path.insert(0,str(APP/'tests/rules_v1'));sys.path.insert(0,str(APP/'tests/e2e_v1'))
import test_rules as rf
import test_planning as pf
import test_compliance as cf
from src.planning.catalog import load_catalog
from src.planning.selector import select
from src.planning.service import plan
from src.planning.contracts import RuleSet,RuleFamily,FieldObservation,PurchaseEvidence,DailyPurchases,ItemClassification
from src.quality.contracts import FieldQuality
from src.rules.models import load_package,validate_model
from src.rules.contracts import ModelPackage,ExecutionPolicy,PaymentProof
from src.rules.executor import execute
from src.rules.context import build
from src.explanation_v2.service import load_config
from src.explanation_v2.retrieval import retrieve
from src.orchestration.contracts import LegalCitation
from src.domain.cfr import CanonicalFinancialRecord
from src.legal_registry.registry import LegalRegistry
from src.taxonomy.service import Taxonomy
from src.canonicalization.derive import sha


def frozen_catalog():
    path=APP/'rules/registry/versions/20261014-v1'
    return (RuleSet.model_validate_json((path/'ruleset_v1.json').read_text(encoding='utf-8')),
            LegalRegistry.model_validate_json((path/'legal_registry_v1.json').read_text(encoding='utf-8')),
            Taxonomy.model_validate_json((path/'taxonomy_v1.json').read_text(encoding='utf-8')))


def frozen_package():
    data=json.loads((APP/'rules/registry/versions/20261014-v1/model_manifest_v1.json').read_text(encoding='utf-8'))
    for row in data['models']:
        row['jdm_json']=(APP/'rules/models'/row.pop('file')).read_text(encoding='utf-8')
    return ModelPackage.model_validate(data)


class CatalogRevisionTests(unittest.TestCase):
    def setUp(self):self.rules,self.legal,self.taxonomy=load_catalog()

    def family(self,identifier):return next(f for f in self.rules.families if f.rule_id==identifier)

    def test_archive_byte_pins_and_heads_equal_named_snapshots(self):
        path=APP/'rules/registry/versions/20261014-v1'
        pins=json.loads((path/'byte_pins.json').read_text())
        for name,pin in pins.items():self.assertEqual(hashlib.sha256((path/name).read_bytes()).hexdigest(),pin)
        for head,named in [('legal_registry_v1.json','legal_registry_20261016_v2.json'),
                           ('ruleset_v1.json','ruleset_20261016_v2.json'),('taxonomy_v1.json','taxonomy_20261016_v2.json')]:
            self.assertEqual((APP/'rules/registry'/head).read_bytes(),(APP/'rules/registry'/named).read_bytes())
        self.assertNotEqual(frozen_catalog()[0].version,self.rules.version)

    def test_model_alignment_draft_and_no_old_rule_ids_reused(self):
        package=load_package();models={(m.rule_id,m.rule_version):m for m in package.models}
        old={(m.rule_id,m.rule_version) for m in frozen_package().models}
        for family in self.rules.families:
            for rule in family.versions:
                model=models[(rule.rule_id,rule.version)]
                self.assertNotIn((rule.rule_id,rule.version),old)
                self.assertEqual((model.effective_from,model.effective_to,model.legal_basis),(rule.effective_from,rule.effective_to,rule.legal_basis))
                self.assertEqual(model.publication,'DRAFT');self.assertEqual(rule.publication,'DRAFT')
                validate_model(model)

    def test_source_fidelity_is_not_classification_approval(self):
        self.assertFalse(self.taxonomy.mappings)
        self.assertTrue(all(self.legal.verified(v.legal_basis) for f in self.rules.families for v in f.versions))
        self.assertTrue(all(not self.legal.verified(c.legal_basis) for c in self.taxonomy.categories))

    def test_content_transition_boundaries_no_latest_fallback(self):
        family=self.family('INV_CONTENT_001')
        for day,version in [('2022-07-01','content-2022-v2'),('2025-05-31','content-2022-v2'),
            ('2025-06-01','content-2025-v2'),('2026-06-30','content-2025-v2'),('2026-07-01','content-2026-v2'),
            ('2026-10-15','content-2026-v2'),('2026-10-16','content-2026-v2')]:
            with self.subTest(day=day):self.assertEqual(select(family,date.fromisoformat(day))[0].version,version)
        for day in (None,date(2022,6,30),date(2026,10,17)):
            self.assertIsNone(select(family,day)[0])

    def test_no_gap_or_overlap_at_any_supported_day(self):
        for family in self.rules.families:
            day=family.supported_from
            while day<family.supported_to:
                self.assertEqual(select(family,day)[1],'MATCH',(family.rule_id,day))
                day+=timedelta(days=1)

    def test_payment_not_split_at_359_and_changed_at_144(self):
        family=self.family('VAT_NON_CASH_PAYMENT_001')
        self.assertEqual(len(family.versions),2)
        self.assertEqual(select(family,date(2025,12,31))[0].version,select(family,date(2026,1,1))[0].version)
        before=select(family,date(2026,6,19))[0];after=select(family,date(2026,6,20))[0]
        self.assertNotEqual(before.version,after.version)
        self.assertNotIn('ND359_2025',{b.document_id for v in family.versions for b in v.legal_basis})
        self.assertIn('ND144_2026',{b.document_id for b in after.legal_basis})

    def test_vat_annex_year_split_and_direct_method_excluded(self):
        family=self.family('VAT_RATE_001')
        self.assertEqual(select(family,date(2025,12,31))[0].version,'vat-2025-v2')
        self.assertEqual(select(family,date(2026,1,1))[0].version,'vat-2026-v2')
        for rule in family.versions:
            self.assertTrue(any(p.requirement.path=='context.vat_method' and p.value=='DEDUCTION' for p in rule.predicates))
            self.assertTrue(any(p.requirement.path=='item.vat_category' and p.value=='REDUCTION_CANDIDATE' for p in rule.predicates))

    def test_statutory_expiry_separate_from_review_horizon(self):
        doc=next(d for d in self.legal.documents if d.document_id=='ND174_2025')
        self.assertEqual(doc.effective_to,date(2027,1,1))
        self.assertTrue(all(f.supported_to==date(2026,10,17) for f in self.rules.families))
        for ident in ('ND123_2020','ND70_2025','TT32_2025'):
            self.assertEqual(next(d for d in self.legal.documents if d.document_id==ident).effective_to,date(2026,7,1))

    def test_all_selected_bases_have_corpus_and_correct_dates(self):
        _,corpus=load_config()
        self.assertEqual(corpus.registry_version,self.legal.version)
        for family in self.rules.families:
            for rule in family.versions:
                for basis in rule.legal_basis:
                    doc=next(d for d in self.legal.documents if d.document_id==basis.document_id)
                    cite=LegalCitation(document_id=doc.document_id,locator=basis.locator,official_url=doc.official_url,sha256=doc.sha256,locator_reviewed=True)
                    self.assertTrue(retrieve(corpus,self.legal,(cite,),'',rule.effective_from),(rule.version,basis.locator))

    def test_annex_index_complete_and_not_product_mapping(self):
        data=json.loads((APP/'configs/explanation/legal_sources/ND174_appendices_source_index_v2.json').read_text(encoding='utf-8'))
        self.assertEqual([p['pdf_page'] for p in data['pages']],list(range(5,78)))
        self.assertFalse(data['table_semantics_approved']);self.assertFalse(data['product_mapping_approved'])
        for page in data['pages']:
            self.assertEqual(hashlib.sha256(page['text'].encode()).hexdigest(),page['text_sha256'])
            self.assertTrue(all(isinstance(w['text'],str) for w in page['words']))


class BusinessCaseTests(unittest.TestCase):
    """Approve in-memory copies ONLY to exercise MVP gates and native ZEN facts."""
    def setUp(self):
        self.rules,self.legal,self.taxonomy=load_catalog();self.package=load_package()
        self.rec,_,self.master,self.ctx,_,_,self.profile,_=pf.fixture()
        self.ctx=self.ctx.model_copy(update={'values':tuple(v.model_copy(update={'field':pf.human('VAT')})
            if v.path=='context.invoice_kind' else v for v in self.ctx.values)})

    def dated(self,on,amount=None):
        rec=self.rec.model_copy(update={'invoice':self.rec.invoice.model_copy(update={'issue_date':pf.human(date.fromisoformat(on))})})
        if amount is not None:rec=rec.model_copy(update={'totals':rec.totals.model_copy(update={'gross':pf.human(Decimal(amount))})})
        return rec

    def planned(self,ident,rec=None,ctx=None,promote=True,taxonomy=None):
        rec=rec or self.dated('2026-10-16');ctx=ctx or self.ctx
        family=next(f for f in self.rules.families if f.rule_id==ident)
        if promote:
            family=family.model_copy(update={'versions':tuple(v.model_copy(update={'publication':'APPROVED_TECHNICAL','review_reference':'SYNTHETIC_CASE_ONLY_NOT_LEGAL_APPROVAL'}) for v in family.versions)})
        rules=RuleSet(version='test-only-v2',families=(family,));q=pf.quality_for(rec);tax=taxonomy or self.taxonomy
        result=plan(rec,q,self.master,rules,self.legal,self.profile,tax,ctx,created_at=pf.STAMP['created_at'])
        inputs={name:obj.model_dump(mode='json') for name,obj in [('record',rec),('quality',q),('master',self.master),
            ('ruleset',rules),('legal',self.legal),('profile',self.profile),('taxonomy',tax),('context',ctx)]}
        return result,inputs

    def model(self,entry):
        return next(m for m in self.package.models if (m.rule_id,m.rule_version)==(entry.rule_id,entry.rule_version)).model_copy(update={
            'publication':'APPROVED_TECHNICAL','review_reference':'SYNTHETIC_CASE_ONLY_NOT_LEGAL_APPROVAL'})

    def test_actual_production_drafts_never_execute_or_pass(self):
        rec=self.dated('2026-10-16')
        p=plan(rec,pf.quality_for(rec),self.master,self.rules,self.legal,self.profile,self.taxonomy,self.ctx)
        self.assertTrue(all(e.eligibility!='ELIGIBLE' for e in p.entries))
        inputs={name:obj.model_dump(mode='json') for name,obj in [('record',rec),('quality',pf.quality_for(rec)),('master',self.master),
            ('ruleset',self.rules),('legal',self.legal),('profile',self.profile),('taxonomy',self.taxonomy),('context',self.ctx)]}
        def forbidden(*args):raise AssertionError('DRAFT must not reach engine')
        r=execute(p,inputs,self.package,runner=forbidden)
        self.assertEqual(r.aggregate.counts.evaluated,0)
        self.assertNotIn(r.aggregate.verdict,('PASS','PASS_WITHIN_SCOPE','FAIL'))

    def test_missing_date_does_not_select_latest(self):
        rec=self.rec.model_copy(update={'invoice':self.rec.invoice.model_copy(update={'issue_date':None})})
        p,_=self.planned('INV_CONTENT_001',rec)
        self.assertIsNone(p.entries[0].rule_version)
        self.assertEqual(p.entries[0].applicability,'UNKNOWN')

    def test_missing_seller_tax_id_without_absence_proof_needs_input(self):
        rec=self.dated('2026-10-16');rec=rec.model_copy(update={'parties':rec.parties.model_copy(update={'seller':rec.parties.seller.model_copy(update={'tax_id':None})})})
        p,_=self.planned('INV_CONTENT_001',rec)
        self.assertEqual(p.entries[0].eligibility,'NOT_EVALUATED_MISSING_INPUT')

    def content_case(self,present=True,method='COMPLETE_PARSE'):
        rec=self.dated('2026-10-16')
        if not present:rec=rec.model_copy(update={'parties':rec.parties.model_copy(update={'seller':rec.parties.seller.model_copy(update={'tax_id':None})})})
        self.profile=self.profile.model_copy(update={'absence_fidelity_policies':('complete-content-v1',)})
        observation=FieldObservation(observation_id='case-presence',field_path='parties.seller.tax_id',
            kind='PRESENT_VALUE' if present else 'CONFIRMED_ABSENT',fidelity_policy='complete-content-v1',validator_version='case',
            method=method,evidence_reference='synthetic-source',document_complete=True,verification_reference='synthetic-review',
            source_id=rec.source_id,source_record_id=rec.record_id,source_revision=rec.revision,profile_id=self.profile.profile_id,profile_version=self.profile.version)
        return self.planned('INV_CONTENT_001',rec,self.ctx.model_copy(update={'observations':(observation,)}))

    def test_native_zen_seller_presence_true_and_confirmed_absence_false(self):
        for present,expected in [(True,'PASS'),(False,'FAIL')]:
            p,inputs=self.content_case(present);e=p.entries[0]
            self.assertEqual(e.eligibility,'ELIGIBLE')
            model=self.model(e);context=build(p,e,model,inputs)
            self.assertEqual(rf.native(model,context,ExecutionPolicy())[0],expected)

    def test_ocr_empty_is_not_confirmed_absence(self):
        p,_=self.content_case(False,method='OCR')
        self.assertEqual(p.entries[0].eligibility,'REVIEW_REQUIRED')

    def test_non_vat_invoice_outside_scoped_check_not_legal_exemption(self):
        ctx=self.ctx.model_copy(update={'values':tuple(v.model_copy(update={'field':pf.human('SALE')})
            if v.path=='context.invoice_kind' else v for v in self.ctx.values)})
        p,_=self.planned('INV_CONTENT_001',ctx=ctx)
        self.assertEqual(p.entries[0].eligibility,'NOT_APPLICABLE')
        # This is applicability of the scoped MVP check, not a tax-compliant document verdict.

    def daily(self,rec,other='0',other_seller=False,other_day=False,complete=True):
        row=PurchaseEvidence(tenant_id=rec.tenant_id,taxpayer_id=rec.taxpayer_id,record_id=rec.record_id,revision=rec.revision,
            input_sha256=sha(rec.model_dump(mode='json')),issue_date=rec.invoice.issue_date.value,seller_tax_id=rec.parties.seller.tax_id.value,gross=rec.totals.gross.value)
        rows=(row,)
        if other!='0':rows+=(row.model_copy(update={'record_id':'other-case','gross':Decimal(other),
            'seller_tax_id':'1111111111' if other_seller else row.seller_tax_id,
            'issue_date':row.issue_date+timedelta(days=1) if other_day else row.issue_date}),)
        return DailyPurchases(version='case-ledger',complete=complete,verification_reference='SYNTHETIC_LEDGER_ONLY',purchases=rows)

    def test_payment_threshold_inclusive_and_daily_grouping(self):
        cases=[('4999999','0',False,False,'NO_MATCH'),('5000000','0',False,False,'MATCH'),
            ('5000001','0',False,False,'MATCH'),('3000000','2000000',False,False,'MATCH'),
            ('3000000','2000000',True,False,'NO_MATCH'),('3000000','2000000',False,True,'NO_MATCH')]
        for amount,other,other_seller,other_day,expected in cases:
            with self.subTest(amount=amount,other=other,other_seller=other_seller,other_day=other_day):
                rec=self.dated('2026-10-16',amount)
                ctx=self.ctx.model_copy(update={'daily':self.daily(rec,other,other_seller,other_day)})
                p,_=self.planned('VAT_NON_CASH_PAYMENT_001',rec,ctx)
                self.assertEqual(p.entries[0].applicability,expected)

    def test_below_threshold_incomplete_ledger_is_unknown(self):
        rec=self.dated('2026-10-16','4000000')
        for daily in (None,self.daily(rec,complete=False)):
            p,_=self.planned('VAT_NON_CASH_PAYMENT_001',rec,self.ctx.model_copy(update={'daily':daily}))
            self.assertEqual(p.entries[0].applicability,'UNKNOWN')

    def test_special_payment_foreign_currency_negative_amount_abstain(self):
        for mode in ('SPECIAL','USD','NEGATIVE'):
            rec=self.dated('2026-10-16','5000000');ctx=self.ctx
            if mode=='SPECIAL':ctx=ctx.model_copy(update={'values':tuple(v.model_copy(update={'field':pf.human('SPECIAL')}) if v.path=='context.payment_case' else v for v in ctx.values)})
            elif mode=='USD':rec=rec.model_copy(update={'currency':pf.human('USD')})
            else:rec=rec.model_copy(update={'totals':rec.totals.model_copy(update={'gross':pf.human(Decimal('-1'))})})
            p,_=self.planned('VAT_NON_CASH_PAYMENT_001',rec,ctx)
            self.assertEqual(p.entries[0].applicability,'UNKNOWN')

    def test_payment_proof_missing_or_wrong_scope_cannot_be_fabricated(self):
        rec=self.dated('2026-10-16','5000000');p,inputs=self.planned('VAT_NON_CASH_PAYMENT_001',rec)
        entry=p.entries[0];self.assertEqual(entry.eligibility,'ELIGIBLE')
        with self.assertRaises(ValueError):build(p,entry,self.model(entry),inputs,payment=None)

    def payment_proof(self,p,value):
        return PaymentProof(tenant_id=p.tenant_id,taxpayer_id=p.taxpayer_id,record_id=p.record_id,
            record_revision=p.record_revision,record_sha256=p.record_sha256,field=pf.human(value),
            quality=FieldQuality(field_path='payment.non_cash_evidence',field_status='PRESENT',
                validation='VALID',reliability='HUMAN_CONFIRMED',critical=False),verification_reference='SYNTHETIC_PROOF_ONLY')

    def test_native_payment_verified_boolean_and_scope_rejection(self):
        rec=self.dated('2026-10-16','5000000');p,inputs=self.planned('VAT_NON_CASH_PAYMENT_001',rec)
        entry=p.entries[0];model=self.model(entry)
        for value,expected in [(True,'PASS'),(False,'FAIL')]:
            proof=self.payment_proof(p,value)
            context=build(p,entry,model,inputs,payment=proof)
            self.assertEqual(rf.native(model,context,ExecutionPolicy())[0],expected)
            for update in ({'taxpayer_id':'other-payer'},{'record_revision':999},{'record_sha256':'0'*64}):
                with self.assertRaises(ValueError):build(p,entry,model,inputs,payment=proof.model_copy(update=update))

    def test_native_vat_rate_requires_test_only_independent_classification(self):
        family=next(f for f in self.rules.families if f.rule_id=='VAT_RATE_001')
        bases=family.versions[-1].legal_basis
        # Only this in-memory synthetic taxonomy is approved; published taxonomy stays blocked.
        tax=self.taxonomy.model_copy(update={'categories':tuple(c.model_copy(update={'legal_basis':bases}) for c in self.taxonomy.categories)})
        for rate,expected in [('0.08','PASS'),('0.10','FAIL')]:
            rec=self.dated('2026-10-16');item=rec.items[0].model_copy(update={'vat_rate':pf.human(Decimal(rate))})
            rec=rec.model_copy(update={'items':(item,)})
            assignment=ItemClassification(item_id=item.item_id,category=pf.human('REDUCTION_CANDIDATE'),
                quality=FieldQuality(field_path='items.'+item.item_id+'.vat_category',field_status='PRESENT',validation='VALID',
                    reliability='HUMAN_CONFIRMED',critical=False),evidence_kind='HUMAN_CLASSIFICATION',verification_reference='SYNTHETIC_ONLY')
            p,inputs=self.planned('VAT_RATE_001',rec,self.ctx.model_copy(update={'classifications':(assignment,)}),taxonomy=tax)
            entry=p.entries[0];self.assertEqual(entry.eligibility,'ELIGIBLE')
            model=self.model(entry);context=build(p,entry,model,inputs)
            self.assertEqual(rf.native(model,context,ExecutionPolicy())[0],expected)

    def test_stale_daily_ledger_unknown(self):
        rec=self.dated('2026-10-16','3000000');daily=self.daily(rec,'2000000')
        daily=daily.model_copy(update={'purchases':tuple(row.model_copy(update={'revision':999}) if row.record_id==rec.record_id else row for row in daily.purchases)})
        p,_=self.planned('VAT_NON_CASH_PAYMENT_001',rec,self.ctx.model_copy(update={'daily':daily}))
        self.assertEqual(p.entries[0].applicability,'UNKNOWN')

    def test_rate8_without_independent_category_is_unknown(self):
        p,_=self.planned('VAT_RATE_001')
        self.assertEqual(p.entries[0].applicability,'UNKNOWN')

    def test_kct_kkknt_and_direct_method_not_forced_into_8_percent(self):
        rec=self.dated('2026-10-16')
        for treatment in ('KCT','KKKNT'):
            item=rec.items[0].model_copy(update={'vat_treatment':pf.human(treatment),'vat_rate':None})
            p,_=self.planned('VAT_RATE_001',rec.model_copy(update={'items':(item,)}))
            self.assertEqual(p.entries[0].applicability,'NO_MATCH')
        ctx=self.ctx.model_copy(update={'values':tuple(v.model_copy(update={'field':pf.human('DIRECT')}) if v.path=='context.vat_method' else v for v in self.ctx.values)})
        p,_=self.planned('VAT_RATE_001',ctx=ctx);self.assertEqual(p.entries[0].applicability,'NO_MATCH')

    def test_unapproved_real_taxonomy_cannot_be_bypassed_by_human_label(self):
        item=self.rec.items[0]
        assignment=ItemClassification(item_id=item.item_id,category=pf.human('REDUCTION_CANDIDATE'),
            quality=FieldQuality(field_path='items.'+item.item_id+'.vat_category',field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=False),
            evidence_kind='HUMAN_CLASSIFICATION',verification_reference='SYNTHETIC_LABEL_ONLY')
        p,_=self.planned('VAT_RATE_001',ctx=self.ctx.model_copy(update={'classifications':(assignment,)}))
        self.assertEqual(p.entries[0].applicability,'UNKNOWN')

    def test_invalid_tax_id_and_stale_quality_rejected_before_rules(self):
        rec=self.dated('2026-10-16');data=rec.model_dump(mode='json');data['parties']['seller']['tax_id']['value']='ABC'
        with self.assertRaises(ValidationError):CanonicalFinancialRecord.model_validate(data)
        with self.assertRaises(ValueError):plan(rec,pf.quality_for(self.rec),self.master,self.rules,self.legal,self.profile,self.taxonomy,self.ctx)


class HistoricalReplayTests(unittest.TestCase):
    def test_v1_report_replays_after_current_catalog_is_v2(self):
        f=cf.ComplianceTests('test_default_catalog_no_false_tax_pass_and_capture_export_works');f.setUp()
        self.addCleanup(f.doCleanups)
        with patch('src.planning.repository.load_catalog',return_value=frozen_catalog()),patch('src.orchestration.workflow.load_package',return_value=frozen_package()):
            old=f.run_evaluation('old-catalog')
        original=f.workflow.artifact(f.ctx,f.payer,old.evaluation_id)
        current=f.run_evaluation('new-catalog')
        self.assertNotEqual(old.report.planning_evaluation_id,current.report.planning_evaluation_id)
        self.assertEqual(f.workflow.artifact(f.ctx,f.payer,old.evaluation_id),original)
        self.assertTrue(f.workflow.replay(f.ctx,f.payer,old.evaluation_id)['verified'])
        self.assertTrue(f.workflow.replay(f.ctx,f.payer,current.evaluation_id)['verified'])


if __name__=='__main__':unittest.main()
