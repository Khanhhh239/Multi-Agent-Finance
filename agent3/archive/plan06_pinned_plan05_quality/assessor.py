"""Pure quality assessment. PRESENT, validity and reliability are distinct."""
from ..canonicalization.derive import sha
from .contracts import (QualityAssessment,FieldQuality,ConfidenceSummary,ReviewRecommendation,CalibrationScope,
    QualityPolicy,SourceCheck,CalibrationArtifact)
from .policy import profile_for,confidence_reason
from .completeness import flatten,completeness,coverage
from .validators import issue,validate_field,validate_raw,consistency
from .calibration import predict
from ..domain.cfr import CanonicalFinancialRecord
from ..extraction.contracts import ExtractionArtifact

def family(path):
    return 'items.*.'+path.split('.')[-1] if path.startswith('items.') else path

def assess(artifact,record,policy,scope,*,assessment_id,created_at,implementation_sha256,
           calibrations=(),raw_scores=None,source_checks=(),verified_fidelity_policies=(),verified_review_events=()):
    artifact=ExtractionArtifact.model_validate_json(artifact.model_dump_json())
    policy=QualityPolicy.model_validate_json(policy.model_dump_json())
    if scope.extractor_sha256!=artifact.extractor_sha256 or scope.document_family!=artifact.profile.version:
        raise ValueError('calibration context/extraction mismatch')
    calibrations=tuple(CalibrationArtifact.model_validate_json(c.model_dump_json()) for c in calibrations)
    if len({c.version for c in calibrations})!=len(calibrations): raise ValueError('duplicate calibration versions')
    raw_scores=raw_scores or {};issues=[];results=[];profile=None
    if (record is None)!=(artifact.record is None): raise ValueError('record/segmentation mismatch')
    if record:
        record=CanonicalFinancialRecord.model_validate_json(record.model_dump_json())
        for key in ('tenant_id','taxpayer_id','source_id','document_id','record_id','taxpayer_master_revision','source_format','record_type'):
            if getattr(record,key)!=getattr(artifact.record,key): raise ValueError('record/extraction identity mismatch: '+key)
        if record.revision<artifact.record.revision: raise ValueError('older revision than extraction')
        if record.revision==artifact.record.revision and record!=artifact.record: raise ValueError('same revision has different content')
        profile=profile_for(policy,record);fields=flatten(record)
        overall,critical,expected=completeness(record,profile,fields)
        paths=sorted(set(expected)|{p for p,f in fields.items() if f.status in ('PRESENT','AMBIGUOUS')})
        checks={}
        for check in source_checks:
            check=SourceCheck.model_validate_json(check.model_dump_json())
            if check.field_path not in paths: raise ValueError('source check does not address an assessed field')
            if check.field_path in checks: raise ValueError('duplicate source verification')
            if check.fidelity_policy_version not in policy.fidelity_policies or check.fidelity_policy_version not in verified_fidelity_policies:
                raise ValueError('source check requires verified fidelity policy')
            if any((e.source_id,e.document_id)!=(artifact.source_id,artifact.document_id) for e in check.evidence): raise ValueError('cross-source evidence')
            checks[check.field_path]=check
        for path in paths:
            field=fields.get(path);status=field.status.value if field else 'MISSING'
            validity=validate_field(path,field);reliability='UNAVAILABLE';probability=None
            if path in checks:
                validity,more=validate_raw(path,checks[path].raw_value,source_confirmed=True,evidence=checks[path].evidence);issues.extend(more)
            if status=='MISSING':
                issues.append(issue('MISSING_FIELD',path,'Expected field is not available; request the source or extract again.',field,action='REQUEST_DATA'))
            elif status=='AMBIGUOUS':
                issues.append(issue('AMBIGUOUS_CANDIDATES',path,'Competing values require source comparison.',field,action='SELECT_CANDIDATE'))
            elif status=='PRESENT':
                if field.confidence_basis=='DETERMINISTIC':
                    fidelity=field.provenance.deterministic_policy_version
                    if fidelity in policy.fidelity_policies and fidelity in verified_fidelity_policies: reliability='DETERMINISTIC_VERIFIED'
                    else: issues.append(issue('FIDELITY_UNVERIFIED',path,'Deterministic method has no verified fidelity proof in this run.',field,action='CONFIRM_VALUE'))
                elif field.confidence_basis=='HUMAN_CONFIRMED' and field.provenance.review_event_id in verified_review_events:
                    reliability='HUMAN_CONFIRMED'
                elif field.confidence_basis=='CALIBRATED':
                    target=scope.model_copy(update={'field_family':family(path)})
                    model=next((c for c in calibrations if c.version==field.provenance.calibration_version),None)
                    score=raw_scores.get(path)
                    value=predict(model,target,score) if model and score is not None else None
                    if value is not None and abs(value-field.confidence)<1e-12:
                        reliability='CALIBRATED';probability=value
                    else: issues.append(issue('CALIBRATION_SCOPE_UNAVAILABLE',path,'Calibration version, score, engine or preprocessing scope does not match.',field,action='CONFIRM_VALUE'))
                if reliability=='UNAVAILABLE':
                    issues.append(issue('CONFIDENCE_UNAVAILABLE',path,'No supported field correctness probability or verified fidelity proof; review required.',field,action='CONFIRM_VALUE'))
                elif reliability=='CALIBRATED':
                    risk='tax_id' if path.endswith('tax_id') else 'issue_date' if path.endswith('issue_date') else 'money' if path.startswith('totals.') or path.endswith('.net') else 'other'
                    reason=confidence_reason(probability,policy.thresholds.get(risk))
                    if reason: issues.append(issue(reason,path,'Field-specific acceptance threshold is missing or not met.',field,action='CONFIRM_VALUE'))
                if validity=='UNKNOWN': issues.append(issue('VALIDITY_UNKNOWN',path,'Format or source content could not be validated.',field,classification='UNKNOWN'))
            results.append(FieldQuality(field_path=path,field_status=status,validation=validity,reliability=reliability,
                probability=probability,critical=path in profile.critical_fields,
                eligible_within_policy=status=='PRESENT' and validity=='VALID' and reliability in ('DETERMINISTIC_VERIFIED','HUMAN_CONFIRMED')))
        issues.extend(consistency(record))
        if record.item_discovery_status!='COMPLETE' or not record.items:
            issues.append(issue('INCOMPLETE_ITEMS','items','Row/page completeness is not established; request pages or re-extract.',action='REQUEST_DATA'))
        if record.derived.invoice_direction.status=='AMBIGUOUS':
            issues.append(issue('UNKNOWN_DIRECTION','derived.invoice_direction','Taxpayer identity/direction remains unresolved.'))
    else:
        overall=critical=coverage((),{});issues.append(issue('REVIEW_SPLIT',None,'Document boundaries require confirmation before assessing fields.',action='REVIEW_SPLIT'))
    for extraction_issue in artifact.issues:
        if extraction_issue.code.startswith('UNPARSEABLE'):
            path=extraction_issue.field_path
            if path and path.startswith(('seller.','buyer.')): path='parties.'+path
            issues.append(issue('INVALID_EXTRACTION',path,'Extraction could not parse an observed region; source invalidity is unproven.',
                classification='INVALID_EXTRACTION',action='REEXTRACT',source_block_refs=extraction_issue.block_refs,
                evidence=tuple(e for c in artifact.candidates if c.semantic_field==extraction_issue.field_path for e in c.evidence_refs)))
    # Any field-level contradiction removes technical eligibility too.
    blocked={i.field_path for i in issues if i.severity=='ERROR'}
    results=[f.model_copy(update={'eligible_within_policy':False}) if f.field_path in blocked else f for f in results]
    present=sum(f.field_status=='PRESENT' for f in results)
    probabilities=[f.probability for f in results if f.field_status=='PRESENT' and f.validation=='VALID' and f.reliability=='CALIBRATED' and f.probability is not None]
    confidence=ConfidenceSummary(present_count=present,calibrated_count=len(probabilities),
        calibrated_coverage=len(probabilities)/present if present else None,
        mean=sum(probabilities)/len(probabilities) if probabilities else None,minimum=min(probabilities) if probabilities else None)
    issues.append(issue('AUTO_ACCEPT_DISABLED',None,'Thresholds and independent release evaluation are pending; all documents require review.',severity='INFO',action='CONFIRM_VALUE'))
    recommendations=tuple(ReviewRecommendation(recommendation_id='recommend-'+sha([i.code,i.field_path,i.action,n])[:32],
        reason=i.code,field_path=i.field_path,action=i.action,issue_refs=(n,)) for n,i in enumerate(issues))
    disposition='REVIEW_SPLIT' if not record else 'REQUEST_DATA' if any(i.action=='REQUEST_DATA' for i in issues) else 'REEXTRACT' if any(i.action=='REEXTRACT' for i in issues) else 'REVIEW'
    return QualityAssessment(config_version=policy.version,creator='quality-assessor',stage='quality',created_at=created_at,
        assessment_id=assessment_id,tenant_id=artifact.tenant_id,taxpayer_id=artifact.taxpayer_id,
        extraction_artifact_id=artifact.artifact_id,extraction_sha256=sha(artifact.model_dump(mode='json')),
        record_id=record.record_id if record else None,record_revision=record.revision if record else None,
        input_sha256=sha(record.model_dump(mode='json')) if record else sha(artifact.model_dump(mode='json')),
        implementation_sha256=implementation_sha256,policy_version=policy.version,policy_sha256=sha(policy.model_dump(mode='json')),
        profile_version=profile.version if profile else None,calibration_versions=tuple(c.version for c in calibrations),
        calibration_sha256=sha([c.model_dump(mode='json') for c in calibrations]),completeness=overall,critical_completeness=critical,
        confidence=confidence,fields=tuple(results),issues=tuple(issues),recommendations=recommendations,disposition=disposition)
