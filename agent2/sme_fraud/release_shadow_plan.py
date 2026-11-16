"""Enterprise-only adapter from locked validation artifacts to shadow case policy.

Packages enter through the trusted enterprise Python/CLI boundary, never HTTP
model/metric uploads. Importing a study does not approve its quality or HE use.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from collections import Counter
from .import_files import canonical,digest
from .pipeline_release_store import ensure
from .case_queue_policy import validate_policy
from .validation_study import (validate_evaluation_plan,ValidationStudyError,extract_split_rows,
    _resolve_arm_ml_scores,apply_calibrator)

VERSION='release-shadow-plan/1.0.0'
PROFILE='snapshot_case_shadow/1.0.0'
SUPPORTED={'rules_35','robust_z','ecod','isolation_forest','lof','autoencoder'}
FIELDS={'version','scope','feature_contract_fingerprint','model_selection','evaluation_plan','study','references',
        'case_policy','ml_candidate_min_score','fallback_order','execution_location','source_runtime'}


def make_package(scope,*,model_selection,contract,plan,snapshot_manifests,model_artifacts,references,split_bundles,
                 case_policy,ml_candidate_min_score,fallback_order,label_packets=None):
    """Trusted validation producer hook; compute study, never approve or activate."""
    from .validation_study import run_validation_study
    from .pipeline_release import runtime_signature
    before=runtime_signature()
    report=run_validation_study(plan,snapshot_manifests=snapshot_manifests,model_artifacts=model_artifacts,
        reference_artifacts=references,split_bundles=split_bundles,label_packets=label_packets)
    ensure(before==runtime_signature(),'RELEASE_STUDY_RUNTIME','Code/runtime đổi trong lúc validation; cần chạy lại.')
    return dict(version=VERSION,scope=dict(tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids))),
        feature_contract_fingerprint=contract['fingerprint'],model_selection=deepcopy(model_selection),evaluation_plan=deepcopy(plan),study=report,
        references=deepcopy(references),case_policy=deepcopy(case_policy),ml_candidate_min_score=ml_candidate_min_score,
        fallback_order=list(fallback_order),execution_location='enterprise_local_only',source_runtime=before)


def without(value,*keys):return {k:v for k,v in value.items() if k not in keys}


def validate_package(package,scope,models,contract):
    ensure(isinstance(package,dict) and set(package)==FIELDS and package['version']==VERSION,
           'RELEASE_PLAN_CONTRACT','Gói validation/policy không đúng contract.')
    ensure(package['scope']==dict(tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids))),
           'RELEASE_SCOPE','Gói validation/policy ngoài doanh nghiệp.',403)
    ensure(package['execution_location']=='enterprise_local_only','RELEASE_PLAN_HE_UNSUPPORTED',
           'Gói local shadow không được khai báo thành executor HE/cloud.')
    from .pipeline_release import runtime_signature
    ensure(package['source_runtime']==runtime_signature(),'RELEASE_STUDY_RUNTIME','Study không được khóa cùng code/runtime hiện tại; cần chạy validation lại.')
    ensure(package['feature_contract_fingerprint']==contract['fingerprint'],'RELEASE_FEATURE_CHANGED','Feature contract của validation không khớp.')
    plan=package['evaluation_plan'];study=package['study']
    try:validate_evaluation_plan(plan)
    except ValidationStudyError as error:ensure(False,'RELEASE_PLAN_INVALID',str(error))
    ensure(plan['scope']==package['scope'] and study['scope']==package['scope'], 'RELEASE_SCOPE','Study/plan ngoài doanh nghiệp.',403)
    ensure(plan['versions']['feature_contract_version']==contract['version'],'RELEASE_FEATURE_CHANGED','Plan không khớp phiên bản feature đang chạy.')
    ensure(digest(canonical(without(study,'execution_costs','study_result_sha256')))==study['study_result_sha256'],
           'RELEASE_STUDY_INTEGRITY','Checksum study không khớp.')
    ensure(digest(canonical(plan))==study['plan_lock']['plan_sha256'] and
           study['plan_lock']['locked_before_test_inspection'] is True and study['plan_lock']['test_labels_inspected_at_lock'] is False,
           'RELEASE_STUDY_BINDING','Study không khớp EvaluationPlan đã khóa.')
    candidate=study['candidate_shadow_artifact'];selection=study['detector_validation']
    ensure(candidate['plan_sha256']==study['plan_lock']['plan_sha256'] and candidate['selected_arm']==selection['selected_arm'] and
           digest(canonical(without(candidate,'candidate_artifact_sha256')))==candidate['candidate_artifact_sha256'],
           'RELEASE_STUDY_BINDING','Candidate artifact không khớp study.')
    ensure(candidate['governance']['production_approved'] is False and candidate['governance']['candidate_shadow_only'] is True,
           'RELEASE_PRODUCTION_BLOCKED','Gói này chỉ dùng shadow, không nhận production approval tự khai.')
    arms={a['arm_id']:a for a in plan['candidates']}
    arm=selection['selected_arm'];ensure(arms.get(arm['arm_id'])==arm,'RELEASE_STUDY_BINDING','Phương án chọn không thuộc plan.')
    ensure(set(arm['branches'])<=SUPPORTED,'RELEASE_PLAN_BRANCH_UNSUPPORTED','Executor này chưa chấm supervised-shadow hoặc HE; không được giả điểm từ nhánh khác.')
    bindings={b['method_id']:b for b in plan['versions']['model_bindings']}
    for branch in set(arm['branches'])-{'rules_35'}:
        actual=models.get(branch);expected=bindings.get(branch)
        ensure(actual is not None and expected is not None and actual['artifact_id']==expected['artifact_id'] and
               actual['manifest_sha256']==expected['artifact_sha256'],'RELEASE_STUDY_MODEL_MISMATCH','Model được chọn không đúng artifact đã dùng trong validation.')
    refs=package['references']
    from .snapshot_features import utc
    for binding in plan['versions']['reference_bindings']:
        ref=refs.get(binding['reference_id'])
        ensure(ref is not None and ref['tenant_id']==scope.tenant_id and ref['company_id']==next(iter(scope.company_ids)) and
               ref['fitted_split']=='history_train' and digest(canonical(without(ref,'reference_id','reference_sha256')))==ref['reference_sha256'] and
               ref['reference_sha256']==binding['reference_sha256'] and ref['method_id']==binding['method_id'] and
               ref['reference_version']==binding['reference_version'] and ref['score_scale']==binding['score_scale'] and
               utc(ref['as_of'])<=utc(plan['splits']['history_train']['as_of']),
               'RELEASE_REFERENCE_INTEGRITY','Reference lịch sử thiếu hoặc không khớp checksum/scope/cutoff.')
    calibrator=study['calibration_validation']['calibrator']
    ensure(digest(canonical(without(calibrator,'calibrator_sha256')))==calibrator['calibrator_sha256'] and
           calibrator['calibrator_sha256']==candidate['calibrator_summary']['calibrator_sha256'],
           'RELEASE_CALIBRATOR_INTEGRITY','Calibrator không khớp artifact validation.')
    fb={f['fallback_config_id']:f for f in plan['fallback_specs']}
    order=package['fallback_order']
    ensure(isinstance(order,list) and len(order)==len(set(order)) and all(f in fb for f in order),
           'RELEASE_FALLBACK_CONTRACT','Thứ tự fallback phải chỉ định rõ các cấu hình trong plan.')
    policy=validate_policy(package['case_policy']);score=package['ml_candidate_min_score']
    ensure(policy['scoring']['calibrated_weight']==0 or calibrator['target_branch'] in arm['branches'],
           'RELEASE_CALIBRATOR_TARGET','Case policy không được lấy xác suất từ model ngoài phương án đã chọn.')
    ensure(type(score) in (int,float) and 0<=score<=1,'RELEASE_PLAN_THRESHOLD','Ngưỡng ứng viên ML thử phải là số 0–1 được khai báo rõ.')
    ensure(policy['budget']['period_kind'] in ('calendar_week_vn','calendar_month_vn'), 'RELEASE_PLAN_PERIOD','Không nhận kỳ tùy ý theo bundle/run để cấp lại quota.')
    return package


def compile_values(package):
    p=package['evaluation_plan'];s=package['study'];q=package['case_policy']
    return dict(validation_study=package,
        normalization=dict(references=package['references'],bindings=p['versions']['reference_bindings']),
        calibration=s['calibration_validation']['calibrator'],
        ensemble=dict(selected_arm=s['detector_validation']['selected_arm'],plan_sha256=s['plan_lock']['plan_sha256'],
                      case_scoring_contract='explicit_case_policy_over_rule_points_and_selected_ml; not benchmark transaction selection'),
        fallback=dict(specs=p['fallback_specs'],order=package['fallback_order']),
        grouping=dict(aggregation=q['scoring']['aggregation'],evidence_adds_score=False),
        thresholds=dict(min_case_score=q['scoring']['min_case_score'],ml_candidate_min_score=package['ml_candidate_min_score']),
        budget=q['budget'],mandatory_routing=dict(rules=q['scoring']['mandatory_rules']),backlog=q['backlog'])


def period_key(as_of,policy):
    at=datetime.fromisoformat(as_of).astimezone(timezone(timedelta(hours=7)))
    if policy['budget']['period_kind']=='calendar_month_vn':return at.strftime('%Y-%m')
    year,week,_=at.isocalendar();return f'{year}-W{week:02d}'


def score_and_coalesce(scope,analysis,manifest,data,package,bundle_id):
    from .case_coalescing import build_case_bundle_from_rule_analysis,coalesce_cases
    from .validation_study import _row_key
    plan=package['evaluation_plan'];study=package['study'];arm=study['detector_validation']['selected_arm']
    rows,_=extract_split_rows('release_shadow',scope,manifest,analysis,raw_data=data)
    bindings={r['reference_id']:r for r in plan['versions']['reference_bindings']}
    refs=package['references'];company=next(iter(scope.company_ids))
    from .snapshot_features import utc
    valid_after=max([utc(plan['splits'][s]['as_of']) for s in ('detector_validation','calibration_policy_validation')]+[utc(r['as_of']) for r in refs.values()])
    try:scored,_=_resolve_arm_ml_scores(rows,arm,refs,bindings,company)
    except ValidationStudyError as error:ensure(False,'RELEASE_SCORE_CONTRACT',str(error))
    fallbacks={f['fallback_config_id']:f for f in plan['fallback_specs']};chosen=[];extras={}
    for row in rows:
        key=_row_key(row);result=scored[key];fallback_id=None
        future_bound=utc(row['event_at'])<=valid_after
        if future_bound:result=dict(available=False,ml_available=False,ml_score=None,priority_score=None,reason=dict(code='release_artifact_from_future'))
        # Explicit subset fallback: all selected subset branches must be available,
        # and the declared missing branches must really be unavailable. No reweight.
        if not result['available'] and row['tx_visible'] and not future_bound:
            for fid in package['fallback_order']:
                f=fallbacks[fid];used=f['used_branches'];missing=f['missing_or_ineligible_branches']
                def actually_missing(branch):
                    if branch.startswith('rule_') and branch.endswith('_partial'):
                        return branch[5:-8] in row.get('unavailable_rule_ids',[])
                    return row['branches'].get(branch,{}).get('available') is not True
                if not used or not set(used)<=SUPPORTED or not all(actually_missing(b) for b in missing):continue
                if not all(row['branches'].get(b,{}).get('available') is True for b in used):continue
                if used==['rules_35']:
                    fbarm=dict(arm_id=fid,kind='rules_only',branches=used,weights=None,uses_percentile_reference=False,reference_ids=[])
                else:
                    ml=[b for b in used if b!='rules_35'];weights=f.get('weights')
                    if len(ml)>1 and not weights:continue
                    fbarm=dict(arm_id=fid,kind=('rules_plus_ml' if 'rules_35' in used else 'individual_detector') if len(ml)==1 else ('rules_plus_percentile_ensemble' if 'rules_35' in used else 'percentile_ensemble'),
                               branches=used,weights=weights,uses_percentile_reference=len(ml)>1,
                               reference_ids=[r['reference_id'] for r in bindings.values() if r['method_id'] in weights] if len(ml)>1 else [])
                candidate,_=_resolve_arm_ml_scores([row],fbarm,refs,bindings,company)
                if candidate[key]['available']:result=candidate[key];fallback_id=fid;break
        calibrator=study['calibration_validation']['calibrator'];target=calibrator['target_branch']
        target_row=row['branches'].get(target,{})
        probability=apply_calibrator(calibrator,target_row.get('score')) if target in arm['branches'] and target_row.get('available') is True and not future_bound else None
        extras[key[0]]=dict(ml_normalized_score=result['ml_score'] if result['available'] else None,
                           calibrated_fraud_probability=probability,calibration_status='experimental_calibrated' if probability is not None else 'unavailable')
        chosen.append(dict(record_id=key[0],revision=key[1],available=result['available'],priority_score=result['priority_score'] if result['available'] else None,
                           fallback_id=fallback_id,is_selected_arm_complete=fallback_id is None and result['available'],
                           is_full_ensemble=fallback_id is None and result['available'] and arm['kind'] in ('percentile_ensemble','rules_plus_percentile_ensemble'),reason=result.get('reason'),
                           experimental_calibrated_probability=probability,
                           calibration_status='experimental_only' if probability is not None else 'target_unavailable_or_calibrator_blocked'))
    # Case accounting and review evidence must obey the job's immutable cutoff as
    # well. The native snapshot may intentionally retain future/late-known rows;
    # never feed them to the prior-payment/invoice coalescer as known history.
    visible_data=deepcopy(data)
    for table,records in visible_data['source']['tables'].items():
        visible_data['source']['tables'][table]=[r for r in records if all(
            utc(r[field])<=utc(analysis['as_of']) for field in ('observed_at','recorded_at','posted_at','effective_at') if r.get(field))]
    case_bundle=build_case_bundle_from_rule_analysis(analysis,visible_data,scope=scope,ml_method=arm['arm_id'],extra_scores=extras,
                                                    ml_candidate_min_score=package['ml_candidate_min_score'])
    # The adapter's default branch/score fallback must not bypass the frozen plan.
    by_id={r['record_id']:r for r in chosen}
    for record in case_bundle['records']:
        selected=by_id[record['transaction_id']]
        record.update(ml_available=selected['available'] and extras[record['transaction_id']]['ml_normalized_score'] is not None,ml_raw_score=None)
        if not selected['available']:
            record.update(scorable=False,ml_available=False,ml_raw_score=None,ml_normalized_score=None)
        elif not record['actionable_hits'] and extras[record['transaction_id']]['ml_normalized_score'] is None:
            record.update(scorable=True,rules_evaluated_no_hit=True)
    case_bundle['snapshot_binding'].update(bundle_id=bundle_id)
    policy=package['case_policy'];cases=coalesce_cases(case_bundle,policy)
    return dict(version='release-shadow-execution/1.0.0',bundle_id=bundle_id,selected_arm_id=arm['arm_id'],
                plan_sha256=study['plan_lock']['plan_sha256'],study_result_sha256=study['study_result_sha256'],rows=chosen,
                case_bundle=case_bundle,cases=cases,case_policy=policy,period_key=period_key(analysis['as_of'],policy),
                he_execution=False,execution_location='enterprise_local_only',quality_approved=False,
                fallback_counts=dict(Counter(r['fallback_id'] for r in chosen if r['fallback_id'])),
                limitations=['Local enterprise shadow; no cloud upload or HE fallback',
                             'Case scoring/admission policy is an explicit experimental fixture; transaction budget comparison does not approve case policy'])
