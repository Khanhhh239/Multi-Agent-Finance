"""Technical synthetic rule fixtures, real ZEN runtime and adversarial contracts."""
import sys
import json
import unittest
import itertools
import random
import sqlite3
import importlib.metadata
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'planning'))
import test_planning as pf
from src.canonicalization.derive import sha
from src.persistence.repository import digest, RevisionConflict
from src.planning.contracts import RuleSet, RuleFamily, FieldRequirement, Predicate
from src.planning.service import plan as make_plan
from src.rules.contracts import *
from src.rules.models import jdm, validate_model, load_package
from src.rules.money_boundary import checked, add, product, rounded, equal
from src.rules.context import build,key_for
from src.rules.trace import parse_response
from src.rules.zen_adapter import evaluate,EngineFailure
from src.rules.executor import execute,run_id
from src.rules.outcomes import token,terminal_attempts
from src.rules.aggregator import aggregate
from src.rules.replay import verify
from src.rules.repository import ExecutionRepository
from src.app import create_app


def native(model,context,policy):
    import zen
    response=zen.ZenEngine().create_decision(model.jdm_json).evaluate({'facts':context.facts()},{'trace':True})
    return parse_response(json.dumps(response,ensure_ascii=False,allow_nan=False),model,context)


def model_for(rule,bindings=None,review=None,**changes):
    bindings=bindings or (Binding(condition_id='seller_nonempty',operation='NONEMPTY',path='parties.seller.tax_id'),)
    raw=json.dumps(jdm(bindings,review),ensure_ascii=False,separators=(',',':'))
    row=dict(model_id='model.'+rule.rule_id,version='synthetic-v1',rule_id=rule.rule_id,rule_version=rule.version,
        family=rule.family,unit_type=rule.unit_type,effective_from=rule.effective_from,effective_to=rule.effective_to,
        publication='APPROVED_TECHNICAL',review_reference='SYNTHETIC_TEST_ONLY',legal_basis=rule.legal_basis,
        bindings=bindings,review_condition_id=review,jdm_json=raw,jdm_sha256=digest(raw.encode()))
    return RuleModel(**{**row,**changes})


def setup(rules=None,models=None,record=None,context=None,taxonomy_override=None):
    rec,q,master,ctx,legal,taxonomy,profile,rule=pf.fixture()
    rec=record or rec;ctx=context or ctx;taxonomy=taxonomy_override or taxonomy
    if context is None:
        ctx=ctx.model_copy(update={'tenant_id':rec.tenant_id,'taxpayer_id':rec.taxpayer_id,'record_id':rec.record_id,'record_revision':rec.revision})
    q=pf.quality_for(rec)
    rules=rules or (rule,)
    ruleset=RuleSet(version='synthetic',families=tuple(RuleFamily(rule_id=r.rule_id,supported_from=r.effective_from,supported_to=r.effective_to,versions=(r,)) for r in rules))
    package=ModelPackage(package_id='synthetic',version='1',models=models or tuple(model_for(r) for r in rules))
    planned=make_plan(rec,q,master,ruleset,legal,profile,taxonomy,ctx,created_at=pf.STAMP['created_at'])
    inputs={name:obj.model_dump(mode='json') for name,obj in (
        ('record',rec),('quality',q),('master',master),('ruleset',ruleset),('legal',legal),
        ('profile',profile),('taxonomy',taxonomy),('context',ctx))}
    return planned,inputs,package


class MoneyTests(unittest.TestCase):
    def test_no_loss_above_ieee_safe_range(self):
        self.assertEqual(add(('9007199254740992','1')),Decimal('9007199254740993'))
        self.assertFalse(equal('9007199254740992','9007199254740993'))

    def test_decimal_sum_and_product_ignore_global_precision(self):
        with localcontext() as context:
            context.prec=3
            self.assertEqual(add(('123456789012345678901234567890.12345678','0.00000001')),Decimal('123456789012345678901234567890.12345679'))
            self.assertEqual(product('12345678901234567890.25','0.08'),Decimal('987654312098765431.2200'))

    def test_unsupported_domain_and_floats_fail_closed(self):
        for value in (1.1,True,'NaN','Infinity','1e9','0.0000000000001','9'*61,Decimal('1E+100')):
            with self.subTest(value=value),self.assertRaises(ValueError):checked(value)
        with self.assertRaises(ValueError):product('0.000000000001','0.1')

    def test_explicit_rounding_half_up_half_even_and_negative(self):
        self.assertEqual(rounded('2.5',0,'HALF_UP'),Decimal('3'))
        self.assertEqual(rounded('2.5',0,'HALF_EVEN'),Decimal('2'))
        self.assertEqual(rounded('-2.5',0,'HALF_UP'),Decimal('-3'))
        with self.assertRaises(ValueError):rounded('2',0,'AUTO')

    def test_seeded_fraction_oracle_500_cases(self):
        rng=random.Random(20261015)
        with localcontext() as context:
            context.prec=5
            for _ in range(500):
                a=Decimal(str(rng.randrange(-10**20,10**20))+'.'+str(rng.randrange(10000)).zfill(4))
                b=Decimal(str(rng.randrange(-10**20,10**20))+'.'+str(rng.randrange(10000)).zfill(4))
                self.assertEqual(Fraction(add((a,b))),Fraction(a)+Fraction(b))
                self.assertEqual(Fraction(product(a,b)),Fraction(a)*Fraction(b))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.plan,self.inputs,self.package=setup()
        self.model=self.package.models[0]
        self.context=build(self.plan,self.plan.entries[0],self.model,self.inputs)
        self.policy=ExecutionPolicy()

    def test_pinned_real_engine_and_isolated_worker_pass(self):
        self.assertEqual(importlib.metadata.version('zen-engine'),'0.53.0')
        result,trace=evaluate(self.model,self.context,self.policy)
        self.assertEqual(result,'PASS')
        self.assertEqual(trace.matched_row_id,'pass-all')
        self.assertEqual(trace.conditions[0].origin,'ADAPTER')
        self.assertEqual(trace.row_origin,'ENGINE')

    def test_real_engine_exhaustive_boolean_table(self):
        bindings=tuple(Binding(condition_id='c'+str(i),operation='NONEMPTY',path='invoice.number') for i in range(4))
        rule=pf.fixture()[-1]
        model=model_for(rule,bindings,review='c3')
        for values in itertools.product((False,True),repeat=4):
            conditions=tuple(ConditionTrace(condition_id=b.condition_id,value=v,field_paths=('invoice.number',),evidence_refs=('synthetic',),observed_json=json.dumps(v),expected_json='true') for b,v in zip(bindings,values))
            ctx=self.context.model_copy(update={'model_sha256':model.jdm_sha256,'conditions':conditions})
            verdict,_=native(model,ctx,self.policy)
            self.assertEqual(verdict,'FAIL' if not all(values[:3]) else 'REVIEW' if values[3] else 'PASS')

    def test_raw_trace_is_unchanged_and_missing_conditions_not_claimed_engine(self):
        result,trace=native(self.model,self.context,self.policy)
        self.assertEqual(digest(trace.raw_response_json.encode()),trace.raw_sha256)
        raw=json.loads(trace.raw_response_json)
        self.assertNotIn('conditions',raw['trace']['table']['traceData'])
        self.assertTrue(all(c.origin=='ADAPTER' for c in trace.conditions))

    def test_no_hit_malformed_and_missing_trace_are_errors(self):
        _,trace=native(self.model,self.context,self.policy)
        raw=json.loads(trace.raw_response_json)
        for bad in ({'result':[],'trace':{}},{'result':{'result':'NOT_APPLICABLE'},'trace':{}},
                    {'result':{'result':'PASS'}},{**raw,'result':{'result':'PASS','extra':True}},
                    {**raw,'trace':{}},None):
            with self.subTest(bad=bad),self.assertRaises((ValueError,TypeError)):
                parse_response(json.dumps(bad),self.model,self.context)

    def test_forged_row_result_or_facts_are_rejected(self):
        _,trace=native(self.model,self.context,self.policy)
        for change in ('row','result','facts'):
            raw=json.loads(trace.raw_response_json)
            if change=='row':raw['trace']['table']['traceData']['rule']['_id']='fake'
            elif change=='result':raw['result']['result']='FAIL'
            else:raw['trace']['table']['input']['facts']['seller_nonempty']=False
            with self.assertRaises(ValueError):parse_response(json.dumps(raw),self.model,self.context)

    def test_model_tamper_and_unsafe_nodes_are_rejected(self):
        raw=json.loads(self.model.jdm_json);raw['nodes'][1]['content']['rules']=[]
        string=json.dumps(raw)
        with self.assertRaises(ValueError):validate_model(self.model.model_copy(update={'jdm_json':string,'jdm_sha256':digest(string.encode())}))
        with self.assertRaises(ValidationError):RuleModel.model_validate({**self.model.model_dump(mode='json'),'jdm_sha256':'a'*64})

    def test_numeric_boolean_and_row_index_in_raw_trace_are_rejected(self):
        _,trace=native(self.model,self.context,self.policy)
        for change in ('numeric','index'):
            raw=json.loads(trace.raw_response_json)
            if change=='numeric':raw['trace']['table']['input']['facts']['seller_nonempty']=1
            else:raw['trace']['table']['traceData']['index']=999
            with self.assertRaises(ValueError):parse_response(json.dumps(raw),self.model,self.context)

    def test_real_engine_no_hit_never_defaults_pass(self):
        import zen
        model=json.loads(self.model.jdm_json);model['nodes'][1]['content']['rules']=[]
        response=zen.ZenEngine().create_decision(json.dumps(model)).evaluate({'facts':self.context.facts()},{'trace':True})
        with self.assertRaises(ValueError):parse_response(json.dumps(response),self.model,self.context)

    def test_adapter_rejects_draft_model(self):
        with self.assertRaises(EngineFailure):evaluate(self.model.model_copy(update={'publication':'DRAFT'}),self.context,self.policy)

    def test_timeout_kills_worker_and_is_retryable(self):
        with self.assertRaises(EngineFailure) as caught:
            evaluate(self.model,self.context,ExecutionPolicy(timeout_seconds=.001))
        self.assertEqual(caught.exception.code,'ENGINE_TIMEOUT')
        self.assertTrue(caught.exception.retryable)

    def test_runtime_version_mismatch_is_error(self):
        with patch('src.rules.zen_adapter.importlib.metadata.version',return_value='0.54.0'):
            with self.assertRaises(EngineFailure):evaluate(self.model,self.context,self.policy)

    def test_missing_runtime_is_error(self):
        with patch('src.rules.zen_adapter.importlib.metadata.version',side_effect=importlib.metadata.PackageNotFoundError):
            with self.assertRaises(EngineFailure) as caught:evaluate(self.model,self.context,self.policy)
        self.assertEqual(caught.exception.code,'ENGINE_UNAVAILABLE')

    def test_crash_is_error_not_retryable(self):
        from src.ingestion.models import IngestionError
        with patch('src.rules.zen_adapter.run_bounded',side_effect=IngestionError('WORKER_RESOURCE_ERROR','crash')):
            with self.assertRaises(EngineFailure) as caught:evaluate(self.model,self.context,self.policy)
        self.assertFalse(caught.exception.retryable)

    def test_public_models_remain_draft_and_no_threshold_in_tables(self):
        package=load_package()
        self.assertEqual(len(package.models),7)
        self.assertTrue(all(m.publication=='DRAFT' for m in package.models))
        self.assertTrue(all('5000000' not in m.jdm_json for m in package.models))


class ExecutorTests(unittest.TestCase):
    def setUp(self):self.plan,self.inputs,self.package=setup()

    def execute(self,**kwargs):return execute(self.plan,self.inputs,self.package,runner=native,created_at=pf.STAMP['created_at'],**kwargs)

    def test_actual_execute_and_logical_replay(self):
        result=self.execute()
        self.assertEqual(result.aggregate.verdict,'PASS')
        self.assertEqual(result.aggregate.counts.evaluated,1)
        self.assertEqual(verify(result,self.plan,self.inputs,self.package,ExecutionPolicy()),result)

    def test_noneligible_never_calls_engine(self):
        rule=pf.fixture()[-1].model_copy(update={'publication':'DRAFT','review_reference':None})
        plan,inputs,package=setup(rules=(rule,))
        calls=[]
        result=execute(plan,inputs,package,runner=lambda *args:calls.append(args))
        self.assertFalse(calls)
        self.assertFalse(result.attempts)
        self.assertEqual(result.aggregate.verdict,'NO_VERDICT')
        self.assertEqual(result.aggregate.coverage,'NONE')

    def test_context_noneligible_rejected(self):
        entry=self.plan.entries[0].model_copy(update={'eligibility':'REVIEW_REQUIRED'})
        with self.assertRaises(ValueError):build(self.plan,entry,self.package.models[0],self.inputs)

    def test_stale_inputs_fail_before_engine(self):
        inputs=json.loads(json.dumps(self.inputs));inputs['record']['revision']=2
        with self.assertRaises(ValueError):execute(self.plan,inputs,self.package,runner=native)

    def test_missing_or_draft_model_never_pass(self):
        for package in (self.package.model_copy(update={'models':()}),
                self.package.model_copy(update={'models':(self.package.models[0].model_copy(update={'publication':'DRAFT'}),)})):
            result=execute(self.plan,self.inputs,package,runner=native)
            self.assertEqual(result.outcomes[0].execution_status,'ERROR')
            self.assertEqual(result.aggregate.verdict,'NO_VERDICT')

    def test_wrong_model_date_family_and_legal_basis(self):
        model=self.package.models[0]
        for update in ({'effective_from':date(2026,5,1)},{'effective_to':date(2026,4,3)},{'family':'VAT_RATE'},
                       {'legal_basis':(model.legal_basis[0].model_copy(update={'locator':'different'}),)}):
            package=self.package.model_copy(update={'models':(model.model_copy(update=update),)})
            self.assertEqual(execute(self.plan,self.inputs,package,runner=native).outcomes[0].execution_status,'ERROR')

    def test_model_undeclared_field_is_error(self):
        model=model_for(pf.fixture()[-1],(Binding(condition_id='number',operation='NONEMPTY',path='invoice.number'),))
        package=self.package.model_copy(update={'models':(model,)})
        self.assertEqual(execute(self.plan,self.inputs,package,runner=native).outcomes[0].execution_status,'ERROR')

    def test_retry_bounded_and_canonical_not_double_counted(self):
        calls=[]
        def retry(model,context,policy):
            calls.append(1)
            if len(calls)==1:raise EngineFailure('ENGINE_TIMEOUT',True)
            return native(model,context,policy)
        result=execute(self.plan,self.inputs,self.package,runner=retry)
        self.assertEqual(len(result.attempts),2)
        self.assertEqual(len(result.outcomes),1)
        self.assertEqual(result.aggregate.counts.evaluated,1)
        self.assertEqual(result.aggregate.counts.errors,0)
        self.assertEqual(result.attempts[0].error.code,'ENGINE_TIMEOUT')

    def test_timeout_budget_exhaustion_no_review_or_pass(self):
        result=execute(self.plan,self.inputs,self.package,runner=lambda *args:(_ for _ in ()).throw(EngineFailure('ENGINE_TIMEOUT',True)))
        self.assertEqual(len(result.attempts),2)
        self.assertEqual(result.aggregate.verdict,'NO_VERDICT')
        self.assertFalse(result.aggregate.review_required)
        self.assertEqual(result.aggregate.counts.evaluated,0)
        self.assertEqual(result.outcomes[0].error.next_action,'OPERATOR')

    def test_attempt_resume_does_not_repeat_completed_calls(self):
        result=self.execute()
        calls=[]
        resumed=execute(self.plan,self.inputs,self.package,runner=lambda *args:calls.append(args),initial_attempts=result.attempts)
        self.assertFalse(calls)
        self.assertEqual(resumed.outcomes,result.outcomes)

    def test_attempt_duplicate_gap_or_retry_after_success_rejected(self):
        outcome=self.execute().outcomes[0]
        for attempts in ((outcome,outcome),(outcome.model_copy(update={'attempt_number':2}),),
                (outcome,outcome.model_copy(update={'attempt_id':'other','attempt_number':2}))):
            with self.assertRaises(ValueError):terminal_attempts(attempts)

    def test_payment_proof_true_false_missing_and_stale(self):
        rule=pf.fixture()[-1].model_copy(update={'family':'PAYMENT_EVIDENCE','required_fields':()})
        model=model_for(rule,(Binding(condition_id='verified',operation='PAYMENT_NON_CASH',path='payment.non_cash_evidence',value_type='BOOL'),))
        plan,inputs,package=setup(rules=(rule,),models=(model,))
        for value in (True,False):
            proof=PaymentProof(tenant_id=plan.tenant_id,taxpayer_id=plan.taxpayer_id,record_id=plan.record_id,record_revision=plan.record_revision,
                record_sha256=plan.record_sha256,field=pf.human(value),quality=pf.FieldQuality(field_path='payment.non_cash_evidence',field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=True),verification_reference='SYNTHETIC_MATCHED_BANK_PROOF')
            result=execute(plan,inputs,package,payment=proof,runner=native)
            self.assertEqual(result.aggregate.verdict,'PASS' if value else 'FAIL')
            bad=proof.model_copy(update={'record_revision':2})
            self.assertEqual(execute(plan,inputs,package,payment=bad,runner=native).outcomes[0].execution_status,'ERROR')
        self.assertEqual(execute(plan,inputs,package,runner=native).outcomes[0].execution_status,'ERROR')

    def test_vat_rate_exact_boundary_and_independent_category(self):
        rec,q,master,ctx,legal,taxonomy,profile,base=pf.fixture()
        item=rec.items[0]
        classification=pf.ItemClassification(item_id=item.item_id,category=pf.human('CAT'),
            quality=pf.FieldQuality(field_path='items.'+item.item_id+'.vat_category',field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=True),
            evidence_kind='HUMAN_CLASSIFICATION',verification_reference='SYNTHETIC_CATEGORY_REVIEW')
        ctx=ctx.model_copy(update={'classifications':(classification,)})
        rule=base.model_copy(update={'family':'VAT_RATE','unit_type':'ITEM','required_fields':tuple(FieldRequirement(path=p) for p in ('item.vat_rate','item.vat_treatment','item.vat_category'))})
        bindings=(Binding(condition_id='rate',operation='EQUALS',path='item.vat_rate',value_type='DECIMAL',expected='0.08'),
            Binding(condition_id='treatment',operation='EQUALS',path='item.vat_treatment',expected='TAXABLE_RATE'),
            Binding(condition_id='category',operation='EQUALS',path='item.vat_category',expected='CAT'))
        model=model_for(rule,bindings)
        for value in ('0','0.079999999999','0.08','0.080000000001','0.1'):
            record=rec.model_copy(update={'items':(item.model_copy(update={'vat_rate':pf.human(Decimal(value))}),)})
            plan,inputs,package=setup(rules=(rule,),models=(model,),record=record,context=ctx)
            result=execute(plan,inputs,package,runner=native)
            self.assertEqual(result.aggregate.verdict,'PASS' if Decimal(value)==Decimal('.08') else 'FAIL')
        plan,inputs,package=setup(rules=(rule,),models=(model,),record=rec)
        calls=[];result=execute(plan,inputs,package,runner=lambda *a:calls.append(a))
        self.assertFalse(calls)
        self.assertNotEqual(result.aggregate.verdict,'PASS')

    def test_kct_kkknt_are_separate_from_zero_rate(self):
        rec,*_,base=pf.fixture();item=rec.items[0]
        for treatment in ('KCT','KKKNT'):
            record=rec.model_copy(update={'items':(item.model_copy(update={'vat_treatment':pf.human(treatment),'vat_rate':None}),)})
            rule=base.model_copy(update={'family':'VAT_RATE','unit_type':'ITEM','required_fields':(FieldRequirement(path='item.vat_treatment'),)})
            model=model_for(rule,(Binding(condition_id='treatment',operation='EQUALS',path='item.vat_treatment',expected=treatment),))
            plan,inputs,package=setup(rules=(rule,),models=(model,),record=record)
            self.assertEqual(execute(plan,inputs,package,runner=native).aggregate.verdict,'PASS')
            taxable=model_for(rule,(Binding(condition_id='treatment',operation='EQUALS',path='item.vat_treatment',expected='TAXABLE_RATE'),))
            package=package.model_copy(update={'models':(taxable,)})
            self.assertEqual(execute(plan,inputs,package,runner=native).aggregate.verdict,'FAIL')

    def test_confirmed_absence_fails_content_but_ocr_empty_does_not(self):
        rec,q,master,ctx,legal,taxonomy,profile,base=pf.fixture()
        field=rec.parties.seller.tax_id.model_copy(update={'value':None,'status':'MISSING','confidence_basis':'UNAVAILABLE'})
        rec=rec.model_copy(update={'parties':rec.parties.model_copy(update={'seller':rec.parties.seller.model_copy(update={'tax_id':field})})})
        obs=pf.FieldObservation(observation_id='synthetic-absence',field_path='parties.seller.tax_id',kind='CONFIRMED_ABSENT',fidelity_policy='complete-v1',validator_version='1',
            method='HUMAN_REVIEW',evidence_reference='synthetic-full-source',document_complete=True,source_id=rec.source_id,
            source_record_id=rec.record_id,source_revision=rec.revision,profile_id=profile.profile_id,profile_version=profile.version,verification_reference='synthetic-review')
        rule=base.model_copy(update={'required_fields':(),'required_observations':(pf.ObservationRequirement(field_path=obs.field_path,fidelity_policy='complete-v1'),)})
        model=model_for(rule,(Binding(condition_id='printed',operation='OBSERVATION_PRESENT',path=obs.field_path),))
        plan,inputs,package=setup(rules=(rule,),models=(model,),record=rec,context=ctx.model_copy(update={'observations':(obs,)}))
        self.assertEqual(execute(plan,inputs,package,runner=native).aggregate.verdict,'FAIL')
        ocr=obs.model_copy(update={'method':'OCR','kind':'UNKNOWN'})
        plan,inputs,package=setup(rules=(rule,),models=(model,),record=rec,context=ctx.model_copy(update={'observations':(ocr,)}))
        calls=[];result=execute(plan,inputs,package,runner=lambda *a:calls.append(a))
        self.assertFalse(calls)
        self.assertNotEqual(result.aggregate.verdict,'FAIL')

    def test_multiple_item_units_one_rule_and_discovery_blocker(self):
        rec,*_,base=pf.fixture();item=rec.items[0]
        rec=rec.model_copy(update={'items':tuple(item.model_copy(update={'item_id':'item-'+str(i)}) for i in range(3)),'item_discovery_status':'INCOMPLETE'})
        rule=base.model_copy(update={'family':'VAT_RATE','unit_type':'ITEM','required_fields':(FieldRequirement(path='item.vat_rate'),)})
        model=model_for(rule,(Binding(condition_id='rate',operation='EQUALS',path='item.vat_rate',value_type='DECIMAL',expected='0.08'),))
        plan,inputs,package=setup(rules=(rule,),models=(model,),record=rec)
        summary=execute(plan,inputs,package,runner=native).aggregate
        self.assertEqual(summary.counts.evaluated,3)
        self.assertEqual(summary.distinct_rules_evaluated,1)
        self.assertEqual(summary.verdict,'REVIEW')
        self.assertEqual(summary.coverage,'PARTIAL')

    def test_group_net_decimal_and_stable_membership(self):
        rec,*_,base=pf.fixture();item=rec.items[0]
        rec=rec.model_copy(update={'items':(item,item.model_copy(update={'item_id':'second','net':pf.human(Decimal('50'))}))})
        rule=base.model_copy(update={'family':'VAT_RATE','unit_type':'VAT_GROUP','required_fields':(FieldRequirement(path='group.net'),FieldRequirement(path='group.vat_rate'))})
        model=model_for(rule,(Binding(condition_id='net',operation='EQUALS',path='group.net',value_type='DECIMAL',expected='150'),
            Binding(condition_id='rate',operation='EQUALS',path='group.vat_rate',value_type='DECIMAL',expected='0.08')))
        plan,inputs,package=setup(rules=(rule,),models=(model,),record=rec)
        result=execute(plan,inputs,package,runner=native)
        self.assertEqual(result.aggregate.verdict,'PASS')
        self.assertEqual(result.aggregate.counts.evaluated,1)
        self.assertEqual(len(plan.entries[0].unit.item_refs),2)

    def test_malformed_runner_does_not_stop_other_eligible_units(self):
        base=pf.fixture()[-1]
        rules=(base.model_copy(update={'rule_id':'FIRST'}),base.model_copy(update={'rule_id':'SECOND'}))
        plan,inputs,package=setup(rules=rules)
        def malformed(model,context,policy):
            if model.rule_id=='FIRST':return 'INVALID',None
            return native(model,context,policy)
        result=execute(plan,inputs,package,runner=malformed)
        self.assertEqual(len(result.outcomes),2)
        self.assertEqual(result.aggregate.counts.evaluated,1)
        self.assertEqual(result.aggregate.counts.errors,1)
        self.assertEqual(result.aggregate.verdict,'NO_VERDICT')

    def test_unit_budget_stops_before_engine(self):
        base=pf.fixture()[-1]
        plan,inputs,package=setup(rules=(base,base.model_copy(update={'rule_id':'SECOND'})))
        calls=[]
        with self.assertRaises(ValueError):execute(plan,inputs,package,ExecutionPolicy(max_units=1),runner=lambda *a:calls.append(a))
        self.assertFalse(calls)

    def test_replay_detects_tampered_evidence_and_summary(self):
        result=self.execute()
        broken=result.model_copy(update={'aggregate':result.aggregate.model_copy(update={'verdict':'FAIL'})})
        with self.assertRaises(ValueError):verify(broken,self.plan,self.inputs,self.package,ExecutionPolicy())
        context=result.outcomes[0].context
        changed=context.model_copy(update={'conditions':tuple(c.model_copy(update={'evidence_refs':('forged',)}) for c in context.conditions)})
        outcome=result.outcomes[0].model_copy(update={'context':changed,'context_sha256':sha(changed.model_dump(mode='json')),
            'trace':result.outcomes[0].trace.model_copy(update={'conditions':changed.conditions})})
        broken=result.model_copy(update={'outcomes':(outcome,),'attempts':(outcome,)})
        with self.assertRaises(ValueError):verify(broken,self.plan,self.inputs,self.package,ExecutionPolicy())


class AggregationTests(unittest.TestCase):
    def setUp(self):
        base=pf.fixture()[-1]
        rules=tuple(base.model_copy(update={'rule_id':'RULE_'+kind}) for kind in ('PASS','FAIL','REVIEW'))
        models=[]
        for rule,kind in zip(rules,('PASS','FAIL','REVIEW')):
            binding=Binding(condition_id='ok',operation='EQUALS',path='parties.seller.tax_id',expected='different' if kind=='FAIL' else pf.fixture()[0].parties.seller.tax_id.value)
            models.append(model_for(rule,(binding,),review='ok' if kind=='REVIEW' else None))
        self.plan,self.inputs,self.package=setup(rules=rules,models=tuple(models))
        self.result=execute(self.plan,self.inputs,self.package,runner=native)

    def scenario(self,kinds,extra=(),errors=(),missing=()):
        plan=self.plan.model_copy(update={'entries':tuple(e for e in self.plan.entries if e.rule_id[5:] in kinds)+extra})
        outcomes=[]
        for outcome in self.result.outcomes:
            kind=outcome.key.rule_id[5:]
            if kind not in kinds or kind in missing:continue
            context=outcome.context.model_copy(update={'plan_sha256':sha(plan.model_dump(mode='json'))})
            outcome=outcome.model_copy(update={'context':context,'context_sha256':sha(context.model_dump(mode='json'))})
            if kind in errors:
                outcome=outcome.model_copy(update={'execution_status':'ERROR','result':None,'trace':None,
                    'error':ExecutionError(code='ENGINE_TIMEOUT',message='synthetic timeout')})
            outcomes.append(outcome)
        return plan,tuple(outcomes)

    def blocker(self,**updates):
        return self.plan.entries[0].model_copy(update={'rule_id':'BLOCKER','unit':self.plan.entries[0].unit.model_copy(update={'unit_id':'blocker'}),
            'eligibility':'NOT_EVALUATED_MISSING_INPUT','review_required':False,'next_action':'REQUEST_DATA','reasons':('MISSING_INPUT',),**updates})

    def test_pass_and_distinct_rule_vs_unit_counts(self):
        plan,outcomes=self.scenario(('PASS',))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'PASS')
        self.assertEqual(summary.coverage,'FULL')
        self.assertEqual(summary.counts.in_scope,summary.counts.evaluated+summary.counts.blocked)

    def test_fail_preserves_operational_error_and_review_flag(self):
        blocker=self.blocker(review_required=True,eligibility='REVIEW_REQUIRED',next_action='HUMAN_REVIEW')
        plan,outcomes=self.scenario(('PASS','FAIL'),extra=(blocker,),errors=('PASS',))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'FAIL')
        self.assertEqual(summary.coverage,'PARTIAL')
        self.assertTrue(summary.review_required)
        self.assertEqual(summary.counts.errors,1)
        self.assertTrue(summary.operational_errors)

    def test_error_only_is_not_evaluated_and_not_tax_review(self):
        plan,outcomes=self.scenario(('PASS',),errors=('PASS',))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'NO_VERDICT')
        self.assertEqual(summary.coverage,'NONE')
        self.assertFalse(summary.review_required)
        self.assertEqual(summary.counts.evaluated,0)

    def test_pass_with_confirmed_exclusion_only(self):
        exclusion=self.blocker(eligibility='OUT_OF_SCOPE_FOR_SOURCE',capability='UNSUPPORTED',next_action='COLLECT_OTHER_SOURCE')
        plan,outcomes=self.scenario(('PASS',),extra=(exclusion,))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'PASS_WITHIN_SCOPE')
        self.assertEqual(summary.coverage,'FULL')
        self.assertEqual(summary.counts.out_of_scope,1)

    def test_all_outside_scope_is_no_verdict(self):
        exclusion=self.blocker(eligibility='OUT_OF_SCOPE_FOR_SOURCE',capability='UNSUPPORTED',next_action='COLLECT_OTHER_SOURCE')
        plan,outcomes=self.scenario((),extra=(exclusion,))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual((summary.verdict,summary.coverage),('NO_VERDICT','NONE'))
        self.assertIn('NO_IN_SCOPE_UNIT',summary.reasons)

    def test_all_not_applicable_and_empty_config_are_distinct(self):
        excluded=self.blocker(eligibility='NOT_APPLICABLE',applicability='NO_MATCH',next_action='NONE')
        plan,outcomes=self.scenario((),extra=(excluded,))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'NO_VERDICT')
        self.assertIn('NO_APPLICABLE_RULE',summary.reasons)
        plan,outcomes=self.scenario(())
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.processing_status,'ERROR')
        self.assertIsNone(summary.verdict)

    def test_unknown_outside_capability_never_counts_as_exclusion(self):
        unknown=self.blocker(eligibility='NOT_EVALUATED_UNKNOWN_APPLICABILITY',applicability='UNKNOWN',capability='UNSUPPORTED',next_action='COLLECT_OTHER_SOURCE')
        plan,outcomes=self.scenario(('PASS',),extra=(unknown,))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'NO_VERDICT')
        self.assertEqual(summary.coverage,'PARTIAL')
        self.assertEqual(summary.counts.out_of_scope,0)
        self.assertEqual(summary.counts.unknown_applicability,1)

    def test_unknown_intersection_not_double_counted(self):
        unknown=self.blocker(eligibility='NOT_EVALUATED_UNKNOWN_APPLICABILITY',applicability='UNKNOWN',capability='UNKNOWN')
        plan,outcomes=self.scenario(('PASS',),extra=(unknown,))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.counts.unresolved,1)
        self.assertEqual(summary.counts.unknown_applicability,1)
        self.assertEqual(summary.counts.unknown_capability,1)

    def test_incomplete_discovery_blocks_full_even_all_observed_pass(self):
        blocker=self.blocker(eligibility='REVIEW_REQUIRED',review_required=True,
            unit=self.plan.entries[0].unit.model_copy(update={'unit_id':'discovery','discovery':'INCOMPLETE'}))
        plan,outcomes=self.scenario(('PASS',),extra=(blocker,))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'REVIEW')
        self.assertEqual(summary.coverage,'PARTIAL')
        self.assertEqual(summary.counts.discovery_blockers,1)

    def test_missing_terminal_outcome_is_explicit_blocker(self):
        plan,outcomes=self.scenario(('PASS',),missing=('PASS',))
        summary=aggregate(plan,outcomes,self.package)
        self.assertEqual(summary.verdict,'NO_VERDICT')
        self.assertEqual(summary.operational_errors[0].code,'MISSING_TERMINAL_OUTCOME')

    def test_duplicate_stale_unexpected_and_noneligible_outcomes_fatal(self):
        plan,outcomes=self.scenario(('PASS',))
        outcome=outcomes[0]
        for bad in (outcomes+outcomes,(outcome.model_copy(update={'key':outcome.key.model_copy(update={'record_revision':2})}),),
                    (outcome.model_copy(update={'key':outcome.key.model_copy(update={'rule_id':'OTHER'})}),)):
            summary=aggregate(plan,bad,self.package)
            self.assertEqual(summary.processing_status,'ERROR')
            self.assertIsNone(summary.verdict)
            self.assertFalse(summary.counts.evaluated)
        noneligible=plan.model_copy(update={'entries':(self.blocker(),)})
        self.assertIsNone(aggregate(noneligible,outcomes,self.package).verdict)

    def test_cross_scope_version_trace_and_context_tampering_fatal(self):
        plan,outcomes=self.scenario(('PASS',));outcome=outcomes[0]
        for change in ({'tenant_id':'other'},{'package_sha256':'a'*64},{'model_sha256':'b'*64},
                       {'trace':None},{'result':'FAIL'},{'context_sha256':'c'*64}):
            summary=aggregate(plan,(outcome.model_copy(update=change),),self.package)
            self.assertIsNone(summary.verdict)
            self.assertTrue(summary.contract_errors)

    def test_outcome_error_cannot_carry_tax_verdict(self):
        outcome=self.result.outcomes[0]
        payload=outcome.model_dump(mode='json');payload.update(execution_status='ERROR',error={'code':'FAILED','message':'synthetic'})
        with self.assertRaises(ValidationError):RuleOutcome.model_validate(payload)

    def test_aggregate_pass_contract_rejects_blockers(self):
        plan,outcomes=self.scenario(('PASS',));summary=aggregate(plan,outcomes,self.package)
        payload=summary.model_dump(mode='json');payload['coverage']='PARTIAL'
        with self.assertRaises(ValidationError):Aggregate.model_validate(payload)

    def test_exhaustive_128_precedence_combinations_real_engine(self):
        base=pf.fixture()[-1];seller=pf.fixture()[0].parties.seller.tax_id.value
        for kinds in itertools.product(('PASS','FAIL','REVIEW','ERROR'),repeat=3):
            for needs_review in (False,True):
                rules=[];models=[];errors=set()
                for i,kind in enumerate(kinds):
                    rule=base.model_copy(update={'rule_id':'MATRIX_'+str(i)})
                    binding=Binding(condition_id='ok',operation='EQUALS',path='parties.seller.tax_id',expected='wrong' if kind=='FAIL' else seller)
                    rules.append(rule);models.append(model_for(rule,(binding,),review='ok' if kind=='REVIEW' else None))
                    if kind=='ERROR':errors.add(rule.rule_id)
                if needs_review:
                    rule=base.model_copy(update={'rule_id':'REVIEW_BLOCKER','predicates':(Predicate(requirement=FieldRequirement(path='context.obligation_date'),value='2026-04-03'),)})
                    rules.append(rule);models.append(model_for(rule))
                planned,inputs,package=setup(rules=tuple(rules),models=tuple(models))
                def runner(model,context,policy):
                    if model.rule_id in errors:raise EngineFailure('ENGINE_WORKER_ERROR')
                    return native(model,context,policy)
                summary=execute(planned,inputs,package,runner=runner).aggregate
                expected='FAIL' if 'FAIL' in kinds else 'REVIEW' if 'REVIEW' in kinds or needs_review else 'NO_VERDICT' if errors else 'PASS'
                with self.subTest(kinds=kinds,review=needs_review):
                    self.assertEqual(summary.verdict,expected)
                    self.assertEqual(summary.counts.evaluated,3-len(errors))
                    self.assertEqual(summary.counts.errors,len(errors))
                    self.assertEqual(summary.counts.in_scope,summary.counts.evaluated+summary.counts.blocked)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=pf.PersistencePlanningTests('test_persist_idempotent_replay_and_immutable')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.repo=ExecutionRepository(self.fixture.fixture.settings)
        self.ctx=self.fixture.ctx;self.payer=self.fixture.payer
        self.plan=self.repo.planning.work(self.ctx,self.payer,self.fixture.record.record_id,1)

    def approved_capture_plan(self):
        from src.review.correction_service import CorrectionService
        from src.review.contracts import CorrectionCommand,Change
        correction=CorrectionService(self.fixture.fixture.settings)
        correction.ensure_tasks(self.ctx,self.payer,self.fixture.record.record_id)
        task=correction.page(self.ctx,self.payer,'tasks',record_id=self.fixture.record.record_id)['items'][0]
        command=CorrectionCommand(record_id=self.fixture.record.record_id,expected_revision=1,task_id=task['task_id'],
            reason='Synthetic technical source comparison',changes=(Change(field_path='parties.seller.tax_id',new_value='1234567890'),
                Change(field_path='invoice.issue_date',new_value='2026-04-03')))
        correction.correct(self.ctx,self.payer,command,'plan08-technical-review')
        rec,q,master,ctx,legal,taxonomy,profile,rule=pf.fixture()
        ruleset=RuleSet(version='synthetic-approved-capture',families=(RuleFamily(rule_id=rule.rule_id,supported_from=rule.effective_from,supported_to=rule.effective_to,versions=(rule,)),))
        with patch('src.planning.repository.load_catalog',return_value=(ruleset,legal,taxonomy)):
            plan=self.repo.planning.work(self.ctx,self.payer,self.fixture.record.record_id,2)
        self.assertEqual(plan.entries[0].eligibility,'ELIGIBLE')
        package=ModelPackage(package_id='synthetic-approved',version='1',models=(model_for(rule),))
        return plan,package

    def test_capture_review_plan_real_worker_store_replay_end_to_end(self):
        plan,package=self.approved_capture_plan()
        result=self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package)
        self.assertEqual(result.aggregate.verdict,'PASS')
        self.assertEqual(result.record_revision,2)
        self.assertEqual(len(self.repo.attempts(self.ctx,self.payer,result.execution_id)),1)
        self.assertEqual(self.repo.replay(self.ctx,self.payer,result.execution_id),result)
        with self.repo.ingestion.db() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM rule_execution_attempts')
        with patch('src.rules.repository.execute',side_effect=AssertionError('Idempotent run must not evaluate again')):
            self.assertEqual(self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package),result)

    def test_retry_attempts_durable_and_counted_once(self):
        plan,package=self.approved_capture_plan()
        calls=[]
        def retry(model,context,policy):
            calls.append(1)
            if len(calls)==1:raise EngineFailure('ENGINE_TIMEOUT',True)
            return native(model,context,policy)
        result=self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=retry)
        self.assertEqual(len(self.repo.attempts(self.ctx,self.payer,result.execution_id)),2)
        self.assertEqual(result.aggregate.counts.evaluated,1)
        self.assertEqual(self.repo.replay(self.ctx,self.payer,result.execution_id),result)

    def test_process_interrupt_after_attempt_resumes_without_second_engine_call(self):
        plan,package=self.approved_capture_plan()
        from src.rules import repository as module
        original=module.execute
        def crash(*args,**kwargs):
            original_store=kwargs['on_attempt']
            def interrupted(attempt):
                original_store(attempt)
                raise KeyboardInterrupt('Simulated worker death after durable attempt')
            kwargs['on_attempt']=interrupted
            return original(*args,**kwargs)
        with patch('src.rules.repository.execute',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=native)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rule_execution_attempts').fetchone()[0],1)
            db.execute('UPDATE rule_execution_runs SET lease_until=0')
        calls=[]
        result=self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=lambda *a:calls.append(a))
        self.assertFalse(calls)
        self.assertEqual(result.aggregate.verdict,'PASS')

    def test_attempt_audit_failure_rolls_back_attempt_then_resumes(self):
        plan,package=self.approved_capture_plan()
        with patch.object(self.repo.base,'_audit',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=native)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rule_execution_attempts').fetchone()[0],0)
            db.execute('UPDATE rule_execution_runs SET lease_until=0')
        result=self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=native)
        self.assertEqual(result.aggregate.verdict,'PASS')

    def test_actual_concurrent_claims_only_one_engine_execution(self):
        plan,package=self.approved_capture_plan()
        entered=threading.Event();release=threading.Event();calls=[]
        def slow(model,context,policy):
            calls.append(1);entered.set()
            if not release.wait(10):raise RuntimeError('Test release timeout')
            return native(model,context,policy)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.repo.work,self.ctx,self.payer,plan.evaluation_id,package=package,runner=slow)
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(RevisionConflict):self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=slow)
            finally:release.set()
            result=future.result(timeout=10)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package),result)

    def test_superseded_worker_cannot_commit_attempt(self):
        plan,package=self.approved_capture_plan()
        def superseded(model,context,policy):
            response=native(model,context,policy)
            with self.repo.ingestion.db() as db:db.execute("UPDATE rule_execution_runs SET lease_token='replacement'")
            return response
        with self.assertRaises(RevisionConflict):self.repo.work(self.ctx,self.payer,plan.evaluation_id,package=package,runner=superseded)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rule_execution_attempts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM compliance_results').fetchone()[0],0)

    def test_real_public_catalog_blockers_persist_replay_and_idempotence(self):
        result=self.repo.work(self.ctx,self.payer,self.plan.evaluation_id)
        self.assertEqual(result.aggregate.verdict,'REVIEW')
        self.assertEqual(result.aggregate.counts.evaluated,0)
        self.assertEqual(self.repo.work(self.ctx,self.payer,self.plan.evaluation_id),result)
        self.assertEqual(self.repo.replay(self.ctx,self.payer,result.execution_id),result)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM compliance_results')

    def test_cross_tenant_and_taxpayer_isolation(self):
        result=self.repo.work(self.ctx,self.payer,self.plan.evaluation_id)
        other=self.ctx.model_copy(update={'tenant_id':'other'})
        with self.assertRaises(KeyError):self.repo.get(other,self.payer,result.execution_id)
        with self.assertRaises(KeyError):self.repo.attempts(other,self.payer,result.execution_id)
        with self.assertRaises(KeyError):self.repo.work(other,self.payer,self.plan.evaluation_id)

    def test_api_auth_result_and_attempt_pagination(self):
        client=TestClient(create_app(self.fixture.fixture.settings))
        headers={'Authorization':'Bearer '+self.fixture.fixture.token}
        url='/v1/rule-plans/'+self.plan.evaluation_id+'/executions?taxpayer_id='+self.payer
        self.assertEqual(client.post(url).status_code,401)
        response=client.post(url,headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        identifier=response.json()['execution_id']
        base='/v1/rule-executions/'+identifier
        self.assertEqual(client.get(base+'?taxpayer_id='+self.payer,headers=headers).status_code,200)
        page=client.get(base+'/attempts?taxpayer_id='+self.payer+'&limit=1&offset=0',headers=headers)
        self.assertEqual(page.json()['total'],0)
        self.assertEqual(client.get(base+'/attempts?taxpayer_id='+self.payer+'&limit=201',headers=headers).status_code,422)
        self.assertEqual(client.post(url.replace(self.payer,'payer-b'),headers=headers).status_code,403)

    def test_audit_failure_result_rollback_and_expired_lease_resume(self):
        with patch.object(self.repo.base,'_audit',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):self.repo.work(self.ctx,self.payer,self.plan.evaluation_id)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM compliance_results').fetchone()[0],0)
            db.execute('UPDATE rule_execution_runs SET lease_until=0')
        result=self.repo.work(self.ctx,self.payer,self.plan.evaluation_id)
        self.assertEqual(self.repo.replay(self.ctx,self.payer,result.execution_id),result)

    def test_concurrent_run_is_conflict_not_duplicate(self):
        with patch('src.rules.repository.execute',side_effect=RuntimeError('process stopped')):
            with self.assertRaises(RuntimeError):self.repo.work(self.ctx,self.payer,self.plan.evaluation_id)
        with self.assertRaises(RevisionConflict):self.repo.work(self.ctx,self.payer,self.plan.evaluation_id)


if __name__=='__main__':unittest.main()
