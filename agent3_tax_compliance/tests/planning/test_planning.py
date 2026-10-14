"""Synthetic planning matrix; fixtures are not approved Vietnamese tax rules."""
import sys, unittest, json, sqlite3
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extraction_v1'))
import test_extraction as extraction_fixtures
from test_extraction import run,MASTER,STAMP,CTX
from src.domain.cfr import CanonicalFinancialRecord
from src.domain.field import FieldObject
from src.domain.evidence import Provenance
from src.quality.completeness import flatten
from src.quality.validators import validate_field
from src.quality.contracts import QualityAssessment,FieldQuality,Coverage,ConfidenceSummary
from src.canonicalization.derive import sha
from src.planning.contracts import *
from src.planning.service import plan
from src.planning.selector import select
from src.planning.units import discover
from src.planning.applicability import combine
from src.planning.eligibility import usable
from src.planning.catalog import load_catalog,load_capability
from src.planning.repository import PlanningRepository,replay
from src.legal_registry.registry import LegalRegistry,LegalDocument
from src.taxonomy.service import Taxonomy,CategoryDefinition,CategoryMapping
from src.app import create_app


def human(value):
    return FieldObject(value=value,status='PRESENT',source='fixture',confidence_basis='HUMAN_CONFIRMED',
        provenance=Provenance(method='fixture',adapter_version='fixture',review_event_id='fixture-review'))


def quality_for(record):
    fields=tuple(FieldQuality(field_path=p,field_status=f.status,validation=validate_field(p,f),
        reliability='HUMAN_CONFIRMED' if f.status=='PRESENT' else 'UNAVAILABLE',critical=False)
        for p,f in flatten(record).items())
    coverage=Coverage(expected=0,denominator=0,present=0,excluded_not_applicable=0,excluded_not_provided=0,ratio=None)
    return QualityAssessment(**STAMP,assessment_id='q-fixture',tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,
        extraction_artifact_id='extract-fixture',extraction_sha256='a'*64,record_id=record.record_id,
        record_revision=record.revision,input_sha256=sha(record.model_dump(mode='json')),implementation_sha256='b'*64,
        policy_version='fixture',policy_sha256='c'*64,profile_version='fixture',calibration_sha256='d'*64,
        completeness=coverage,critical_completeness=coverage,confidence=ConfidenceSummary(present_count=0,
            calibrated_count=0,calibrated_coverage=None,mean=None,minimum=None),fields=fields,issues=(),recommendations=(),disposition='REVIEW')


def fixture():
    record=run().record
    payload=record.model_dump(mode='json')
    def mark(obj):
        if isinstance(obj,dict):
            if 'status' in obj and 'provenance' in obj and obj['status']=='PRESENT':
                obj['confidence_basis']='HUMAN_CONFIRMED';obj['confidence']=None
                obj['provenance']['review_event_id']='fixture-review'
            for value in obj.values():mark(value)
        elif isinstance(obj,list):
            for value in obj:mark(value)
    mark(payload)
    payload['derived']['invoice_direction']['value']='INPUT'
    record=CanonicalFinancialRecord.model_validate(payload)
    master=MASTER.model_copy(update={'tax_code':'9876543210','effective_from':date(2022,1,1)})
    quality=quality_for(record)
    context=PlanningContext(tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,record_id=record.record_id,
        record_revision=record.revision,values=tuple(ContextValue(path=p,field=human(v),
            quality=FieldQuality(field_path=p,field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=False),
            verification_reference='synthetic-context-proof') for p,v in (
                ('context.invoice_kind','VAT'),('context.vat_method','DEDUCTION'),
                ('context.claim_input_vat',True),('context.payment_case','STANDARD'))))
    basis=LegalBasis(document_id='TEST_LAW',locator='synthetic-article')
    legal=LegalRegistry(version='fixture',checked_on=date(2026,10,14),documents=(LegalDocument(document_id='TEST_LAW',
        official_url='https://vanban.chinhphu.vn/',sha256='f'*64,effective_from=date(2020,1,1),source_status='PDF_REVIEWED',
        verified_locators=('synthetic-article',),transitional_policy='SYNTHETIC_TEST_ONLY'),))
    taxonomy=Taxonomy(version='fixture',effective_from=date(2022,1,1),effective_to=date(2027,1,1),
        categories=(CategoryDefinition(category_id='CAT',description='Synthetic legal classification',legal_basis=(basis,)),))
    profile=CapabilityProfile(profile_id='fixture',version='1',adapter_id='fixture',adapter_version='1',
        source_formats=('PDF',),supported_families=('INVOICE_CONTENT','VAT_RATE','PAYMENT_EVIDENCE'),absence_fidelity_policies=('complete-v1',))
    rule=RuleVersion(rule_id='TEST_RULE',version='v1',family='INVOICE_CONTENT',effective_from=date(2022,1,1),
        effective_to=date(2027,1,1),publication='APPROVED_TECHNICAL',review_reference='synthetic-test-review',
        legal_basis=(basis,),required_fields=(FieldRequirement(path='parties.seller.tax_id'),))
    return record,quality,master,context,legal,taxonomy,profile,rule


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.record,self.q,self.master,self.context,self.legal,self.taxonomy,self.profile,self.rule=fixture()

    def evaluate(self,rule=None,record=None,quality=None,context=None,profile='default',taxonomy=None,legal=None):
        rule=rule or self.rule;record=record or self.record
        family=RuleFamily(rule_id=rule.rule_id,supported_from=rule.effective_from,supported_to=rule.effective_to,versions=(rule,))
        return plan(record,quality or quality_for(record),self.master,RuleSet(version='fixture',families=(family,)),
            legal or self.legal,self.profile if profile=='default' else profile,taxonomy or self.taxonomy,
            context or self.context,created_at=STAMP['created_at'])

    def test_eligible_is_plan_only_with_all_pins_and_no_engine(self):
        result=self.evaluate()
        self.assertEqual(result.entries[0].eligibility,'ELIGIBLE')
        self.assertEqual(result.engine_calls,0)
        self.assertTrue(result.technical_only)
        self.assertEqual(len(result.pins),7)
        self.assertEqual(self.evaluate(),result)

    def test_predicate_numeric_metadata_and_type_mismatch_abstain(self):
        for value in ('NaN','Infinity','not-a-number',True):
            with self.assertRaises(ValidationError):
                Predicate(requirement=FieldRequirement(path='totals.gross'),operator='GTE',value=value)
        predicate=Predicate(requirement=FieldRequirement(path='currency'),operator='GTE',value='5')
        result=self.evaluate(rule=self.rule.model_copy(update={'predicates':(predicate,)}))
        self.assertEqual(result.entries[0].applicability,'UNKNOWN')
        self.assertIn('PREDICATE_TYPE_MISMATCH',result.entries[0].reasons)

    def test_date_boundaries_and_no_latest_fallback(self):
        first=self.rule.model_copy(update={'effective_to':date(2025,6,1)})
        second=self.rule.model_copy(update={'version':'v2','effective_from':date(2025,6,1)})
        family=RuleFamily(rule_id=self.rule.rule_id,supported_from=date(2022,1,1),supported_to=date(2027,1,1),versions=(first,second))
        for day,expected in [(date(2025,5,31),'v1'),(date(2025,6,1),'v2'),(date(2025,6,2),'v2')]:
            self.assertEqual(select(family,day)[0].version,expected)
        self.assertEqual(select(family,date(2021,1,1))[2],'DATE_OUTSIDE_SUPPORTED_HISTORY')

    def test_missing_and_ambiguous_date_keep_null_version(self):
        for status in ('MISSING','AMBIGUOUS'):
            record=self.record.model_copy(update={'invoice':self.record.invoice.model_copy(update={
                'issue_date':self.record.invoice.issue_date.model_copy(update={'status':status,'value':None})})})
            e=self.evaluate(record=record).entries[0]
            self.assertIsNone(e.rule_version)
            self.assertEqual(e.eligibility,'NOT_EVALUATED_UNKNOWN_APPLICABILITY')

    def test_gap_and_overlap_are_errors(self):
        for interval,reason in [(date(2026,1,1),'VERSION_GAP'),(date(2027,1,1),'VERSION_OVERLAP')]:
            a=self.rule.model_copy(update={'effective_to':interval})
            b=self.rule.model_copy(update={'version':'v2','effective_from':date(2026,1,1) if reason=='VERSION_OVERLAP' else date(2026,5,1)})
            family=RuleFamily(rule_id=a.rule_id,supported_from=date(2022,1,1),supported_to=date(2027,1,1),versions=(a,b))
            self.assertEqual(select(family,date(2026,4,3))[2],reason)

    def test_unknown_direction_not_not_applicable(self):
        record=self.record.model_copy(update={'derived':self.record.derived.model_copy(update={'invoice_direction':
            self.record.derived.invoice_direction.model_copy(update={'status':'AMBIGUOUS','value':None})})})
        rule=self.rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='derived.invoice_direction'),value='INPUT'),)})
        self.assertEqual(self.evaluate(rule,record).entries[0].eligibility,'NOT_EVALUATED_UNKNOWN_APPLICABILITY')

    def test_known_output_is_not_applicable(self):
        rule=self.rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='derived.invoice_direction'),value='OUTPUT'),)})
        self.assertEqual(self.evaluate(rule).entries[0].eligibility,'NOT_APPLICABLE')

    def test_unknown_applicability_with_unsupported_capability_stays_unknown(self):
        profile=self.profile.model_copy(update={'supported_families':(),'unsupported_families':('INVOICE_CONTENT',)})
        rule=self.rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='context.invoice_kind'),value='VAT'),)})
        context=self.context.model_copy(update={'values':()})
        e=self.evaluate(rule,context=context,profile=profile).entries[0]
        self.assertEqual((e.eligibility,e.capability,e.next_action),('NOT_EVALUATED_UNKNOWN_APPLICABILITY','UNSUPPORTED','COLLECT_OTHER_SOURCE'))
        self.assertFalse(e.review_required)

    def test_supported_missing_field_not_scope_exclusion(self):
        rule=self.rule.model_copy(update={'required_fields':(FieldRequirement(path='context.obligation_date'),)})
        self.assertEqual(self.evaluate(rule).entries[0].eligibility,'NOT_EVALUATED_MISSING_INPUT')

    def test_unknown_profile_is_planning_error(self):
        self.assertEqual(self.evaluate(profile=None).entries[0].eligibility,'NOT_EVALUATED_PLANNING_ERROR')

    def test_draft_or_unverified_basis_cannot_exclude(self):
        rule=self.rule.model_copy(update={'publication':'DRAFT','predicates':(Predicate(requirement=FieldRequirement(path='currency'),value='USD'),)})
        self.assertEqual(self.evaluate(rule).entries[0].eligibility,'NOT_EVALUATED_PLANNING_ERROR')
        legal=self.legal.model_copy(update={'documents':()})
        self.assertEqual(self.evaluate(legal=legal).entries[0].eligibility,'NOT_EVALUATED_PLANNING_ERROR')

    def cash(self,amount='4000000',profile='default',daily=None):
        record=self.record.model_copy(update={'totals':self.record.totals.model_copy(update={'gross':human(Decimal(amount))})})
        rule=self.rule.model_copy(update={'family':'PAYMENT_EVIDENCE','non_cash_policy':'non-cash-scope-v1','inclusive_threshold':Decimal('5000000'),
            'predicates':(Predicate(requirement=FieldRequirement(path='derived.invoice_direction'),value='INPUT'),)})
        context=self.context.model_copy(update={'daily':daily})
        return self.evaluate(rule,record,context=context,profile=profile),record

    def test_below_threshold_needs_complete_daily_ledger(self):
        e=self.cash()[0].entries[0]
        self.assertEqual(e.applicability,'UNKNOWN')
        self.assertIn('DAILY_PURCHASE_COMPLETENESS_UNKNOWN',e.reasons)

    def daily(self,amount='4000000',other=None):
        record=self.cash(amount)[1]
        purchase=PurchaseEvidence(tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,record_id=record.record_id,
            revision=record.revision,input_sha256=sha(record.model_dump(mode='json')),issue_date=record.invoice.issue_date.value,
            seller_tax_id=record.parties.seller.tax_id.value,gross=amount)
        purchases=(purchase,) if other is None else (purchase,purchase.model_copy(update={'record_id':'other','gross':Decimal(other)}))
        return DailyPurchases(version='ledger-v1',complete=True,verification_reference='synthetic-ledger',purchases=purchases)

    def test_complete_daily_below_threshold_can_no_match(self):
        self.assertEqual(self.cash(daily=self.daily())[0].entries[0].eligibility,'NOT_APPLICABLE')

    def test_same_supplier_same_day_sum_is_inclusive(self):
        self.assertEqual(self.cash(daily=self.daily(other='1000000'))[0].entries[0].applicability,'MATCH')
        self.assertEqual(self.cash('5000000')[0].entries[0].applicability,'MATCH')

    def test_daily_wrong_revision_unknown_and_duplicate_rejected(self):
        daily=self.daily();bad=daily.model_copy(update={'purchases':(daily.purchases[0].model_copy(update={'revision':2}),)})
        self.assertEqual(self.cash(daily=bad)[0].entries[0].applicability,'UNKNOWN')
        with self.assertRaises(ValidationError):DailyPurchases(version='x',complete=True,verification_reference='x',purchases=daily.purchases*2)

    def test_above_threshold_unsupported_source_is_scope_exclusion(self):
        profile=self.profile.model_copy(update={'supported_families':(),'unsupported_families':('PAYMENT_EVIDENCE',)})
        e=self.cash('5000000',profile=profile)[0].entries[0]
        self.assertEqual(e.eligibility,'OUT_OF_SCOPE_FOR_SOURCE')

    def test_low_confidence_and_unknown_validation_block(self):
        fields=tuple(f.model_copy(update={'reliability':'UNAVAILABLE'}) if f.field_path=='parties.seller.tax_id' else f for f in self.q.fields)
        self.assertEqual(self.evaluate(quality=self.q.model_copy(update={'fields':fields})).entries[0].eligibility,'NOT_EVALUATED_LOW_CONFIDENCE')
        fields=tuple(f.model_copy(update={'validation':'UNKNOWN'}) if f.field_path=='parties.seller.tax_id' else f for f in self.q.fields)
        self.assertEqual(self.evaluate(quality=self.q.model_copy(update={'fields':fields})).entries[0].eligibility,'REVIEW_REQUIRED')

    def test_stale_quality_or_context_and_master_scope_are_rejected(self):
        with self.assertRaises(ValueError):self.evaluate(quality=self.q.model_copy(update={'record_revision':2}))
        with self.assertRaises(ValueError):self.evaluate(context=self.context.model_copy(update={'tenant_id':'other'}))
        self.master=self.master.model_copy(update={'taxpayer_id':'other'})
        with self.assertRaises(ValueError):self.evaluate()

    def test_unit_identity_reorder_and_discovery_blocker(self):
        self.assertEqual(discover(self.record,'ITEM'),discover(self.record.model_copy(update={'items':tuple(reversed(self.record.items))}),'ITEM'))
        record=self.record.model_copy(update={'items':(),'item_discovery_status':'UNKNOWN'})
        rule=self.rule.model_copy(update={'unit_type':'ITEM'})
        e=self.evaluate(rule,record).entries[0]
        self.assertEqual(e.eligibility,'REVIEW_REQUIRED')
        self.assertEqual(e.unit.discovery,'UNKNOWN')

    def test_taxonomy_never_inferred_from_observed_rate(self):
        rule=self.rule.model_copy(update={'family':'VAT_RATE','unit_type':'ITEM','required_fields':(FieldRequirement(path='item.vat_category'),)})
        self.assertEqual(self.evaluate(rule).entries[0].eligibility,'NOT_EVALUATED_MISSING_INPUT')
        self.assertIsNone(self.taxonomy.resolve('8%',date(2026,1,1)))

    def test_confirmed_absence_requires_verified_complete_profile(self):
        rule=self.rule.model_copy(update={'required_fields':(),'required_observations':(ObservationRequirement(field_path='parties.seller.address',fidelity_policy='complete-v1'),)})
        obs=FieldObservation(observation_id='absent',field_path='parties.seller.address',kind='CONFIRMED_ABSENT',
            fidelity_policy='complete-v1',validator_version='fixture',method='COMPLETE_PARSE',evidence_reference='synthetic-full-document',
            document_complete=True,verification_reference='synthetic-proof',source_id=self.record.source_id,source_record_id=self.record.record_id,
            source_revision=self.record.revision,profile_id=self.profile.profile_id,profile_version=self.profile.version)
        context=self.context.model_copy(update={'observations':(obs,)})
        self.assertEqual(self.evaluate(rule,context=context).entries[0].eligibility,'ELIGIBLE')
        context=context.model_copy(update={'observations':(obs.model_copy(update={'method':'OCR'}),)})
        self.assertEqual(self.evaluate(rule,context=context).entries[0].eligibility,'REVIEW_REQUIRED')

    def test_unknown_field_blocks_only_its_rule(self):
        rule=self.rule.model_copy(update={'required_fields':(FieldRequirement(path='unregistered.field'),)})
        self.assertEqual(self.evaluate(rule).entries[0].eligibility,'NOT_EVALUATED_PLANNING_ERROR')

    def test_context_boolean_is_not_string_false(self):
        with self.assertRaises(ValidationError):ContextValue(path='context.claim_input_vat',field=human('false'),
            quality=FieldQuality(field_path='context.claim_input_vat',field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=False),verification_reference='x')

    def test_catalog_has_historical_versions_and_no_approved_production_rule(self):
        rules,legal,taxonomy=load_catalog()
        self.assertEqual(len(rules.families[0].versions),3)
        self.assertTrue(all(v.publication=='DRAFT' for f in rules.families for v in f.versions))
        self.assertFalse(taxonomy.mappings)
        self.assertIn('PAYMENT_EVIDENCE',load_capability('invoice_xml_v1').unsupported_families)

    def test_applicability_capability_field_matrix(self):
        rule=self.rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='currency'),value='VND'),)})
        count=0
        for app in ('MATCH','NO_MATCH','UNKNOWN'):
            for cap in ('SUPPORTED','UNSUPPORTED','UNKNOWN'):
                for missing in (False,True):
                    with self.subTest(app=app,cap=cap,missing=missing):
                        record=self.record.model_copy(update={'currency':human('VND' if app=='MATCH' else 'USD') if app!='UNKNOWN' else None})
                        if missing:record=record.model_copy(update={'parties':record.parties.model_copy(update={'seller':record.parties.seller.model_copy(update={'tax_id':None})})})
                        profile=self.profile if cap=='SUPPORTED' else None if cap=='UNKNOWN' else self.profile.model_copy(update={'supported_families':(),'unsupported_families':('INVOICE_CONTENT',)})
                        e=self.evaluate(rule,record,profile=profile).entries[0]
                        expected=('NOT_APPLICABLE' if app=='NO_MATCH' else 'NOT_EVALUATED_PLANNING_ERROR' if cap=='UNKNOWN' else
                            'NOT_EVALUATED_UNKNOWN_APPLICABILITY' if app=='UNKNOWN' else 'OUT_OF_SCOPE_FOR_SOURCE' if cap=='UNSUPPORTED' else
                            'NOT_EVALUATED_MISSING_INPUT' if missing else 'ELIGIBLE')
                        self.assertEqual(e.eligibility,expected)
                        count+=1
        self.assertEqual(count,18)

    def test_human_category_is_independent_and_expires(self):
        item=self.record.items[0]
        assignment=ItemClassification(item_id=item.item_id,category=human('CAT'),
            quality=FieldQuality(field_path='items.'+item.item_id+'.vat_category',field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=False),
            evidence_kind='HUMAN_CLASSIFICATION',verification_reference='synthetic-classification-proof')
        context=self.context.model_copy(update={'classifications':(assignment,)})
        rule=self.rule.model_copy(update={'family':'VAT_RATE','unit_type':'ITEM','required_fields':(FieldRequirement(path='item.vat_category'),)})
        self.assertEqual(self.evaluate(rule,context=context).entries[0].eligibility,'ELIGIBLE')
        expired=self.taxonomy.model_copy(update={'effective_to':date(2026,1,1)})
        self.assertEqual(self.evaluate(rule,context=context,taxonomy=expired).entries[0].eligibility,'REVIEW_REQUIRED')

    def test_mapping_version_and_item_code_are_required(self):
        item=self.record.items[0]
        mapping=CategoryMapping(mapping_id='map-v1',item_code='SKU',category_id='CAT',effective_from=date(2022,1,1),effective_to=date(2027,1,1),
            evidence_reference='catalogue',review_reference='review',evidence_kind='CATALOGUE')
        taxonomy=self.taxonomy.model_copy(update={'mappings':(mapping,)})
        assignment=ItemClassification(item_id=item.item_id,item_code='SKU',category=human('CAT'),mapping_id='map-v1',
            quality=FieldQuality(field_path='items.'+item.item_id+'.vat_category',field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=False),
            evidence_kind='CATALOGUE',verification_reference='proof')
        context=self.context.model_copy(update={'classifications':(assignment,)})
        rule=self.rule.model_copy(update={'unit_type':'ITEM','required_fields':(FieldRequirement(path='item.vat_category'),)})
        self.assertEqual(self.evaluate(rule,context=context,taxonomy=taxonomy).entries[0].eligibility,'ELIGIBLE')
        bad=assignment.model_copy(update={'mapping_id':'old-version'})
        self.assertEqual(self.evaluate(rule,context=context.model_copy(update={'classifications':(bad,)}),taxonomy=taxonomy).entries[0].eligibility,'REVIEW_REQUIRED')

    def test_group_partition_preserves_treatments_and_reorder_identity(self):
        item=self.record.items[0]
        items=(item,item.model_copy(update={'item_id':'kct-item','vat_treatment':human('KCT'),'vat_rate':None}),
               item.model_copy(update={'item_id':'kkknt-item','vat_treatment':human('KKKNT'),'vat_rate':None}),
               item.model_copy(update={'item_id':'zero-item','vat_rate':human(Decimal('0'))}))
        record=self.record.model_copy(update={'items':items})
        units=discover(record,'VAT_GROUP')
        self.assertEqual(len(units),4)
        self.assertEqual(set(r for u in units for r in u.item_refs),{i.item_id for i in items})
        self.assertEqual(units,discover(record.model_copy(update={'items':tuple(reversed(items))}),'VAT_GROUP'))

    def test_group_requirement_and_incomplete_discovery(self):
        rule=self.rule.model_copy(update={'unit_type':'VAT_GROUP','required_fields':(FieldRequirement(path='group.vat_rate'),)})
        self.assertEqual(self.evaluate(rule).entries[0].eligibility,'ELIGIBLE')
        record=self.record.model_copy(update={'item_discovery_status':'UNKNOWN'})
        entries=self.evaluate(rule,record).entries
        self.assertIn('ELIGIBLE',[e.eligibility for e in entries])
        self.assertIn('REVIEW_REQUIRED',[e.eligibility for e in entries])

    def test_calibrated_threshold_and_version_binding(self):
        field=self.record.parties.seller.tax_id
        calibrated=field.model_copy(update={'confidence_basis':'CALIBRATED','confidence':.98,
            'provenance':field.provenance.model_copy(update={'calibration_version':'cal-v1','review_event_id':None})})
        record=self.record.model_copy(update={'parties':self.record.parties.model_copy(update={'seller':self.record.parties.seller.model_copy(update={'tax_id':calibrated})})})
        q=quality_for(record)
        q=q.model_copy(update={'fields':tuple(f.model_copy(update={'reliability':'CALIBRATED','probability':.98}) if f.field_path=='parties.seller.tax_id' else f for f in q.fields),
                              'calibration_versions':('cal-v1',)})
        self.assertEqual(self.evaluate(record=record,quality=q).entries[0].eligibility,'NOT_EVALUATED_LOW_CONFIDENCE')
        rule=self.rule.model_copy(update={'required_fields':(FieldRequirement(path='parties.seller.tax_id',min_confidence=.95),)})
        self.assertEqual(self.evaluate(rule,record,q).entries[0].eligibility,'ELIGIBLE')
        self.assertEqual(self.evaluate(rule,record,q.model_copy(update={'calibration_versions':()})).entries[0].eligibility,'NOT_EVALUATED_LOW_CONFIDENCE')

    def test_cross_tenant_daily_evidence_and_stale_absence_are_rejected(self):
        daily=self.daily()
        bad=daily.model_copy(update={'purchases':(daily.purchases[0].model_copy(update={'tenant_id':'other'}),)})
        with self.assertRaises(ValidationError):PlanningContext.model_validate({**self.context.model_dump(mode='json'),'daily':bad.model_dump(mode='json')})

    def test_entry_contract_cannot_claim_eligible_without_version(self):
        entry=self.evaluate().entries[0].model_dump(mode='json');entry['rule_version']=None
        with self.assertRaises(ValidationError):RulePlanEntry.model_validate(entry)

    def test_gte_money_uses_decimal_without_float(self):
        rule=self.rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='totals.gross'),operator='GTE',value='108'),)})
        self.assertEqual(self.evaluate(rule).entries[0].applicability,'MATCH')
        with self.assertRaises(ValidationError):Predicate(requirement=FieldRequirement(path='totals.gross'),operator='GTE',value=108.0)

    def test_legacy_unknown_is_explicitly_migrated_before_predicate(self):
        from src.planning.migration import migrate_legacy_direction
        payload=self.record.model_dump(mode='json');payload['derived']['invoice_direction']['value']='UNKNOWN'
        migrated=migrate_legacy_direction(payload)
        self.assertEqual(payload['derived']['invoice_direction']['value'],'UNKNOWN')
        self.assertEqual(migrated['derived']['invoice_direction']['status'],'AMBIGUOUS')
        self.assertIsNone(migrated['derived']['invoice_direction']['value'])
        CanonicalFinancialRecord.model_validate(migrated)

    def test_special_payment_case_is_unknown_not_exempt(self):
        context=self.context.model_copy(update={'values':tuple(v.model_copy(update={'field':human('SPECIAL')}) if v.path=='context.payment_case' else v for v in self.context.values)})
        rule=self.rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='context.payment_case'),value='STANDARD'),)})
        self.assertEqual(self.evaluate(rule,context=context).entries[0].applicability,'UNKNOWN')


class PersistencePlanningTests(unittest.TestCase):
    def setUp(self):
        self.fixture=extraction_fixtures.PersistenceTests(methodName='test_atomic_idempotent_roundtrip');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.repo=PlanningRepository(self.fixture.settings);self.ctx=CTX;self.payer='payer-a'
        self.artifact=self.repo.quality.extraction.work(self.ctx,self.payer,self.fixture.identifier,self.fixture.key)
        self.record=self.artifact.record
        self.repo.quality.work(self.ctx,self.payer,self.artifact.artifact_id)

    def test_persist_idempotent_replay_and_immutable(self):
        result=self.repo.work(self.ctx,self.payer,self.record.record_id,1)
        self.assertEqual(self.repo.work(self.ctx,self.payer,self.record.record_id,1),result)
        self.assertEqual(replay(self.repo.snapshot(self.ctx,self.payer,result.evaluation_id),result),result)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM rule_plans')

    def test_cross_tenant_denied_and_missing_revision_not_reused(self):
        result=self.repo.work(self.ctx,self.payer,self.record.record_id,1)
        other=self.ctx.model_copy(update={'tenant_id':'other'})
        with self.assertRaises(KeyError):self.repo.get(other,self.payer,result.evaluation_id)
        with self.assertRaises(KeyError):self.repo.work(self.ctx,self.payer,self.record.record_id,2)

    def test_api_auth_scope_and_zero_engine_calls(self):
        client=TestClient(create_app(self.fixture.settings))
        url='/v1/records/'+self.record.record_id+'/rule-plans?taxpayer_id=payer-a&revision=1'
        self.assertEqual(client.post(url).status_code,401)
        response=client.post(url,headers={'Authorization':'Bearer '+self.fixture.token})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['engine_calls'],0)
        self.assertEqual(client.post(url.replace('payer-a','payer-b'),headers={'Authorization':'Bearer '+self.fixture.token}).status_code,403)

    def test_audit_failure_rolls_back_plan(self):
        with patch.object(self.repo.base,'_audit',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):self.repo.work(self.ctx,self.payer,self.record.record_id,1)
        with self.repo.ingestion.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM rule_plans').fetchone()[0],0)


if __name__=='__main__':unittest.main()
