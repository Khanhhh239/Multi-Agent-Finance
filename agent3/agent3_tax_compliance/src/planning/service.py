"""Pure planner: scoped quality proofs -> pinned plan, with zero engine calls."""
from datetime import date
from pathlib import Path
from ..canonicalization.derive import sha
from ..domain.base import utcnow
from ..domain.taxpayer import identity_match
from .contracts import RulePlan,RulePlanEntry,VersionPin,FieldRequirement,EvaluationUnit
from .selector import select
from .capability import resolve
from .units import discover
from .eligibility import read_field,usable,decision,KNOWN_PATHS
from .applicability import evaluate


def implementation_sha():
    root=Path(__file__).resolve().parents[1]
    return sha({p.relative_to(root).as_posix():p.read_bytes().hex() for folder in ('planning','legal_registry','taxonomy')
                for p in sorted((root/folder).glob('*.py'))})


def plan(record,quality,master,ruleset,legal,profile,taxonomy,context,*,created_at=None):
    scope=(record.tenant_id,record.taxpayer_id,record.record_id,record.revision)
    if scope!=(quality.tenant_id,quality.taxpayer_id,quality.record_id,quality.record_revision):
        raise ValueError('quality/record scope or revision mismatch')
    if quality.input_sha256!=sha(record.model_dump(mode='json')):raise ValueError('quality is stale or forged')
    if scope!=(context.tenant_id,context.taxpayer_id,context.record_id,context.record_revision):raise ValueError('context scope mismatch')
    if (master.tenant_id,master.taxpayer_id,master.revision)!=(record.tenant_id,record.taxpayer_id,record.taxpayer_master_revision):
        raise ValueError('master scope mismatch')
    q={f.field_path:f for f in quality.fields}
    cq={v.path:v.quality for v in context.values}

    def get(requirement,unit=None):
        if requirement.path=='record_type':return record.record_type,None
        if requirement.path.startswith('group.'):
            if unit is None or unit.unit_type!='VAT_GROUP' or not unit.item_refs:return None,'MISSING_INPUT'
            values=[]
            for item_id in unit.item_refs:
                child=EvaluationUnit(unit_type='ITEM',unit_id=item_id,item_refs=(item_id,),discovery='COMPLETE')
                value,reason=get(requirement.model_copy(update={'path':'item.'+requirement.path[6:]}),child)
                if reason:return None,reason
                values.append(value)
            if requirement.path=='group.net':
                from ..canonicalization.normalize import exact_sum
                return exact_sum(values),None
            if len(set(values))!=1:return None,'AMBIGUOUS_INPUT'
            return values[0],None
        field,path=read_field(record,context,requirement.path,unit)
        if path=='derived.invoice_direction':
            deps={}
            for dep in ('parties.seller.tax_id','parties.buyer.tax_id','invoice.issue_date'):
                value,reason=get(FieldRequirement(path=dep,min_confidence=requirement.min_confidence))
                if reason:return None,reason
                deps[dep]=value
            seller=identity_match(deps['parties.seller.tax_id'],master,deps['invoice.issue_date'])
            buyer=identity_match(deps['parties.buyer.tax_id'],master,deps['invoice.issue_date'])
            expected='INPUT' if buyer=='MATCH' and seller=='NO_MATCH' else 'OUTPUT' if seller=='MATCH' and buyer=='NO_MATCH' else None
            if expected is None:return None,'AMBIGUOUS_INPUT'
            if field.status!='PRESENT' or field.value!=expected:return None,'AMBIGUOUS_INPUT'
            return expected,None
        if requirement.path=='item.vat_category':
            if unit is None or len(unit.item_refs)!=1:return None,'MISSING_INPUT'
            item_id=unit.item_refs[0]
            classification=next((c for c in context.classifications if c.item_id==item_id),None)
            if classification is None:return None,'MISSING_INPUT'
            on_date,reason=get(FieldRequirement(path='invoice.issue_date'))
            if reason:return None,reason
            if not taxonomy.effective_from<=on_date<taxonomy.effective_to:return None,'TAXONOMY_UNVERIFIED'
            category=next((c for c in taxonomy.categories if c.category_id==classification.category.value),None)
            if category is None or not legal.verified(category.legal_basis):return None,'TAXONOMY_UNVERIFIED'
            if classification.mapping_id:
                mapping=taxonomy.resolve(classification.item_code,on_date)
                if mapping is None or mapping.mapping_id!=classification.mapping_id or mapping.category_id!=category.category_id:
                    return None,'TAXONOMY_UNVERIFIED'
            elif classification.evidence_kind!='HUMAN_CLASSIFICATION' or classification.category.confidence_basis!='HUMAN_CONFIRMED':
                return None,'TAXONOMY_UNVERIFIED'
            if classification.quality.field_path!='items.'+item_id+'.vat_category':return None,'TAXONOMY_UNVERIFIED'
            return usable(classification.category,classification.quality,requirement)
        quality_field=cq.get(path) if path.startswith('context.') else q.get(path)
        if quality_field and quality_field.reliability=='CALIBRATED' and not path.startswith('context.'):
            if field is None or field.provenance.calibration_version not in quality.calibration_versions:
                return None,'LOW_CONFIDENCE'
        if quality_field and quality_field.validation=='INVALID_SOURCE_CONTENT':
            if not any(i.field_path==path and i.classification=='INVALID_SOURCE_CONTENT' and i.code in requirement.source_issue_codes
                       for i in quality.issues):return None,'VALIDATION_UNAVAILABLE'
        return usable(field,quality_field,requirement)

    entries=[]
    for family in ruleset.families:
        kind=family.versions[0].family
        capability=resolve(profile,kind,record.source_format)
        policies={v.date_field for v in family.versions}
        if len(policies)!=1:raise ValueError('date policy must be stable within a family')
        on_date,date_reason=get(FieldRequirement(path=next(iter(policies))))
        if isinstance(on_date,str):on_date=date.fromisoformat(on_date)
        rule,selection,select_reason=select(family,on_date)
        units=discover(record,rule.unit_type) if rule else (EvaluationUnit(unit_type='RECORD',unit_id=record.record_id,discovery='COMPLETE'),)
        for unit in units:
            reasons=[];traces=();app='UNKNOWN'
            status='NOT_EVALUATED_PLANNING_ERROR';action='OPERATOR';review=False
            if rule is None:
                reasons=[select_reason]+([date_reason] if date_reason else [])
                if select_reason=='DATE_UNAVAILABLE':
                    status='NOT_EVALUATED_UNKNOWN_APPLICABILITY'
                    action='COLLECT_OTHER_SOURCE' if capability=='UNSUPPORTED' else 'HUMAN_REVIEW'
                    review=capability!='UNSUPPORTED'
            else:
                paths=[r.path for r in rule.required_fields]+[p.requirement.path for p in rule.predicates]+[o.field_path for o in rule.required_observations]
                if any(p not in KNOWN_PATHS for p in paths):
                    reasons=['UNREGISTERED_FIELD_PATH']
                else:
                    app,traces=evaluate(rule,lambda req:get(req,unit),record,context)
                    if rule.publication!='APPROVED_TECHNICAL' or not legal.verified(rule.legal_basis):
                        reasons=['RULE_OR_LEGAL_BASIS_NOT_APPROVED']
                    elif app=='NO_MATCH':status='NOT_APPLICABLE';action='NONE';reasons=['APPLICABILITY_NO_MATCH']
                    elif capability=='UNKNOWN':reasons=['CAPABILITY_PROFILE_UNRESOLVED']
                    elif app=='UNKNOWN':
                        status='NOT_EVALUATED_UNKNOWN_APPLICABILITY'
                        action='COLLECT_OTHER_SOURCE' if capability=='UNSUPPORTED' else 'HUMAN_REVIEW'
                        review=capability!='UNSUPPORTED';reasons=[t.reason for t in traces if t.state=='UNKNOWN']
                    elif capability=='UNSUPPORTED':
                        status='OUT_OF_SCOPE_FOR_SOURCE';action='COLLECT_OTHER_SOURCE';reasons=['SOURCE_CANNOT_SUPPLY_EVIDENCE']
                    elif unit.discovery!='COMPLETE':
                        status='REVIEW_REQUIRED';action='HUMAN_REVIEW';review=True;reasons=['UNIT_DISCOVERY_'+unit.discovery]
                    else:
                        for req in rule.required_fields:
                            _,reason=get(req,unit)
                            if reason:reasons.append(reason)
                        observations={o.field_path:o for o in context.observations}
                        for req in rule.required_observations:
                            obs=observations.get(req.field_path)
                            if obs is None or obs.kind=='UNKNOWN':reasons.append('MISSING_INPUT');continue
                            if (obs.kind not in req.accepts or obs.fidelity_policy!=req.fidelity_policy
                                or obs.source_id!=record.source_id or obs.profile_id!=profile.profile_id or obs.profile_version!=profile.version
                                or not obs.verification_reference or obs.method=='OCR'
                                or not obs.document_complete or obs.fidelity_policy not in profile.absence_fidelity_policies):
                                reasons.append('OBSERVATION_UNVERIFIED');continue
                            observed,_=read_field(record,context,req.field_path,unit)
                            if obs.kind=='CONFIRMED_ABSENT' and observed and observed.status=='PRESENT':
                                reasons.append('OBSERVATION_UNVERIFIED')
                            if obs.kind=='PRESENT_VALUE' and (observed is None or observed.status!='PRESENT'):
                                reasons.append('OBSERVATION_UNVERIFIED')
                        status,action,review=decision(reasons)
                        if not reasons:reasons=['ALL_PLANNING_GATES_SATISFIED']
            entries.append(RulePlanEntry(rule_id=family.rule_id,rule_version=rule.version if rule else None,
                unit=unit,selection=selection,applicability=app,capability=capability,eligibility=status,
                reasons=tuple(dict.fromkeys(reasons)),next_action=action,review_required=review,traces=traces,
                legal_basis=rule.legal_basis if rule else ()))
    pins=tuple(VersionPin(name=name,version=version,sha256=sha(payload)) for name,version,payload in (
        ('ruleset',ruleset.version,ruleset.model_dump(mode='json')),
        ('legal',legal.version,legal.model_dump(mode='json')),
        ('capability',profile.version if profile else 'UNAVAILABLE',profile.model_dump(mode='json') if profile else None),
        ('taxonomy',taxonomy.version,taxonomy.model_dump(mode='json')),
        ('context',context.version,context.model_dump(mode='json')),
        ('quality',quality.policy_version,quality.model_dump(mode='json')),
        ('master',str(master.revision),master.model_dump(mode='json'))))
    code=implementation_sha();record_hash=sha(record.model_dump(mode='json'))
    evaluation_id='evaluation-'+sha([record_hash,[p.model_dump(mode='json') for p in pins],code])[:32]
    return RulePlan(config_version='rule-planning-v1',creator='rule-planner',stage='planning',
        created_at=created_at or utcnow(),evaluation_id=evaluation_id,tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,
        record_id=record.record_id,record_revision=record.revision,taxpayer_master_revision=record.taxpayer_master_revision,
        record_sha256=record_hash,implementation_sha256=code,pins=pins,entries=tuple(entries))
