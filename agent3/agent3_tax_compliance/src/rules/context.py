"""Read facts only from pinned inputs or explicitly verified backend sidecars."""
import json
from decimal import Decimal
from ..canonicalization.derive import sha
from ..domain.cfr import CanonicalFinancialRecord
from ..planning.contracts import PlanningContext, FieldRequirement
from ..planning.eligibility import read_field, usable
from ..quality.contracts import QualityAssessment
from ..planning.contracts import EvaluationUnit
from ..canonicalization.normalize import exact_sum
from .contracts import EvaluationKey, EngineContext, ConditionTrace, PaymentProof
from .money_boundary import checked


def key_for(plan, entry):
    return EvaluationKey(evaluation_id=plan.evaluation_id, record_revision=plan.record_revision,
        rule_id=entry.rule_id, rule_version=entry.rule_version, unit_type=entry.unit.unit_type, unit_id=entry.unit.unit_id)


def bound_field(record,context,qualities,requirement,unit):
    path=requirement.path
    if path.startswith('group.'):
        if unit.unit_type!='VAT_GROUP' or not unit.item_refs:raise ValueError('Group members required')
        values=[];refs=[]
        for item_id in unit.item_refs:
            child=EvaluationUnit(unit_type='ITEM',unit_id=item_id,item_refs=(item_id,),discovery='COMPLETE')
            value,child_refs=bound_field(record,context,qualities,requirement.model_copy(update={'path':'item.'+path[6:]}),child)
            values.append(value);refs.extend(child_refs)
        if path=='group.net':return checked(exact_sum(values)),refs
        if len(set(values))!=1:raise ValueError('Group values conflict')
        return values[0],refs
    field,canonical=read_field(record,context,path,unit)
    refs=[]
    if path=='item.vat_category':
        classification=next((c for c in context.classifications if c.item_id==unit.unit_id),None)
        if classification is None:raise ValueError('Independent category classification required')
        field=classification.category;quality=classification.quality
        refs.append(classification.verification_reference)
    else:quality=qualities.get(canonical)
    value,reason=usable(field,quality,requirement)
    if reason:raise ValueError('Model input no longer usable: '+reason)
    refs.extend(('provenance:'+sha(field.provenance.model_dump(mode='json')),
                 'quality:'+sha(quality.model_dump(mode='json'))))
    return value,refs


def build(plan, entry, model, inputs, payment=None):
    if entry.eligibility != 'ELIGIBLE':
        raise ValueError('Only eligible contexts may execute')
    record = CanonicalFinancialRecord.model_validate(inputs['record'])
    quality = QualityAssessment.model_validate(inputs['quality'])
    context = PlanningContext.model_validate(inputs['context'])
    if (record.tenant_id, record.taxpayer_id, record.record_id, record.revision, sha(record.model_dump(mode='json'))) != (
            plan.tenant_id, plan.taxpayer_id, plan.record_id, plan.record_revision, plan.record_sha256):
        raise ValueError('Record/context differs from pinned plan')
    # The caller has already replayed planning. Model requirements must also be declared there.
    family = next(f for f in inputs['ruleset']['families'] if f['rule_id'] == entry.rule_id)
    rule = next(v for v in family['versions'] if v['version'] == entry.rule_version)
    requirements = {r['path']: FieldRequirement.model_validate(r) for r in rule['required_fields']}
    observations = {o.field_path: o for o in context.observations}
    q = {f.field_path: f for f in quality.fields}
    q.update({v.path: v.quality for v in context.values})
    traces = []
    for binding in model.bindings:
        refs = ['cfr:' + plan.record_sha256 + ':' + binding.path]
        if binding.operation == 'PAYMENT_NON_CASH':
            if payment is None:
                raise ValueError('Verified payment proof required; invoice payment label is insufficient')
            proof = PaymentProof.model_validate_json(payment.model_dump_json())
            if (proof.tenant_id, proof.taxpayer_id, proof.record_id, proof.record_revision, proof.record_sha256) != (
                    plan.tenant_id, plan.taxpayer_id, plan.record_id, plan.record_revision, plan.record_sha256):
                raise ValueError('Stale/cross-scope payment proof')
            if proof.quality.field_path != binding.path:
                raise ValueError('Payment proof field mismatch')
            observed, reason = usable(proof.field, proof.quality, FieldRequirement(path=binding.path))
            if reason:
                raise ValueError('Unusable payment proof: ' + reason)
            value = observed
            refs = [proof.verification_reference, proof.policy_version,
                    'payment-proof:' + sha(proof.model_dump(mode='json'))]
        elif binding.operation == 'OBSERVATION_PRESENT':
            if binding.path not in {r['field_path'] for r in rule['required_observations']}:
                raise ValueError('Observation not required by selected rule')
            observation = observations.get(binding.path)
            if observation is None or observation.kind == 'UNKNOWN':
                raise ValueError('Unverified observation')
            observed = observation.kind
            value = observation.kind == 'PRESENT_VALUE'
            refs += [observation.evidence_reference, observation.verification_reference]
        else:
            requirement = requirements.get(binding.path)
            if requirement is None:
                raise ValueError('Model field must be gated by selected rule requirements')
            observed,field_refs=bound_field(record,context,q,requirement,entry.unit)
            refs += field_refs
            if binding.operation == 'NONEMPTY':
                if not isinstance(observed, str):
                    raise ValueError('NONEMPTY requires text')
                value = bool(observed.strip())
            elif binding.value_type == 'DECIMAL':
                if not isinstance(observed, Decimal):
                    raise ValueError('Money field must be Decimal')
                value = checked(observed) == checked(binding.expected)
            elif binding.value_type == 'BOOL':
                if type(observed) is not bool:
                    raise ValueError('Boolean field required')
                value = observed == binding.expected
            else:
                if not isinstance(observed, str):
                    raise ValueError('Text field required')
                value = observed == binding.expected
        if type(value) is not bool:
            raise ValueError('Engine facts must be strict booleans')
        traces.append(ConditionTrace(condition_id=binding.condition_id, value=value, field_paths=(binding.path,),
            evidence_refs=tuple(r for r in refs if r), observed_json=json.dumps(str(observed) if isinstance(observed, Decimal) else observed, ensure_ascii=False),
            expected_json=json.dumps(binding.expected, ensure_ascii=False)))
    return EngineContext(planning_eligibility='ELIGIBLE',key=key_for(plan, entry), tenant_id=plan.tenant_id, taxpayer_id=plan.taxpayer_id,
        record_sha256=plan.record_sha256, plan_sha256=sha(plan.model_dump(mode='json')),
        model_sha256=model.jdm_sha256, conditions=tuple(traces))
