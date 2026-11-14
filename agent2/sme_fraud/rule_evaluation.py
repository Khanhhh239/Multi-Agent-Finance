"""Per-rule results over scoped canonical source bindings, without partial sums."""
from copy import deepcopy
from pathlib import Path

from finance_input import AccessScope
from .import_files import canonical, digest, fail
from .noise_policy import name_key, name_similarity, assign_noise_points
from .rules import RULE_NAMES, WEIGHTS, DEFAULT_CONFIG
from .rule_sources import VERSION as INPUT_VERSION, REQUIREMENTS, ROLES, KINDS
from .snapshot_features import _ref, available, utc
from . import p1_evaluation
from . import vendor_identity_rules

VERSION='rule-results/1.0.0'
SUPPORTED=('E3','P1','B5','E4')


def _e3(sources):
    vendor=sources['vendor'][0]
    others=[v for v in sources['vendors'] if v['record_id']!=vendor['record_id']]
    insufficient=[v['record_id'] for v in [vendor,*others] if not name_key(v['name'])[0]]
    if insufficient:
        return dict(error=('name_content_insufficient','Tên NCC không đủ thông tin để so sánh; bổ sung tên nguồn có ý nghĩa, không kết luận không trùng.'),
                    details=dict(insufficient_vendor_ids=sorted(insufficient)))
    threshold=DEFAULT_CONFIG['fuzzy_similarity'];matches=[]
    for other in others:
        similarity=name_similarity(vendor['name'],other['name'])
        if similarity>threshold:matches.append((round(similarity,4),other['record_id']))
    evidence=dict(matched_vendor_count=len(matches),top_matches=[list(pair) for pair in sorted(matches,reverse=True)[:5]],
                  algorithm='difflib.SequenceMatcher',threshold=threshold)
    hits=[]
    if matches:
        hits=[dict(rule_id='E3',points=WEIGHTS['E3'],intrinsic_points=WEIGHTS['E3'],
                   scoring_role='master_quality',hard_trigger=0,evidence=evidence)]
        assign_noise_points(hits,DEFAULT_CONFIG['operational_score'])
    return dict(matched=bool(matches),score=hits[0]['points'] if hits else 0,
                intrinsic_points=WEIGHTS['E3'] if hits else 0,
                details=dict(evidence=evidence,hits=hits,scoring_role='master_quality',
                    observed_other_vendor_count=len(others),
                    score_reason=hits[0]['score_reason'] if hits else 'Không thấy cặp tên đủ ngưỡng trong các NCC nhìn thấy; không xác nhận đầy đủ master hoặc giao dịch hợp lệ.'))


def _evaluate(sources,inputs,scope,meta):
    """Internal snapshot consumer; never accepts a caller-supplied ready flag."""
    if not isinstance(scope,AccessScope) or len(scope.company_ids)!=1 or 'data.import' not in scope.permissions:
        fail(403,'ACCESS_DENIED','Không đủ quyền đánh giá nguồn luật.','Chọn đúng doanh nghiệp và quyền đọc.')
    company=next(iter(scope.company_ids));identity=(scope.tenant_id,company)
    if (meta['tenant_id'],meta['company_id'])!=identity:
        fail(403,'ACCESS_DENIED','Giao dịch ngoài phạm vi đánh giá luật.','Dùng snapshot đúng quyền.')
    cutoff,event=utc(meta['as_of']),utc(meta['event_at'])
    tx=sources['transactions']
    if len(tx)!=1 or (tx[0]['record_id'],tx[0]['revision'])!=(meta['record_id'],meta['revision']) or available(tx[0])!=cutoff or utc(tx[0]['effective_at'])!=event:
        raise ValueError('Rule evaluation transaction/cutoff mismatch')
    for role,records in sources.items():
        for record in records:
            if (record['tenant_id'],record['company_id'])!=identity:
                fail(403,'ACCESS_DENIED','Nguồn đánh giá luật khác doanh nghiệp.','Dùng snapshot đúng quyền.')
            if utc(record['observed_at'])>cutoff or utc(record['effective_at'])>event:
                raise ValueError('Rule evaluation source exceeds cutoff')
            if role=='transaction_history' and (record['record_id']==meta['record_id'] or available(record)>=cutoff or utc(record['effective_at'])>=event):
                raise ValueError('Rule history includes self or simultaneous/future data')
    plans=inputs['rules']
    if inputs['version']!=INPUT_VERSION or len(plans)!=len(RULE_NAMES) or {p['rule_id'] for p in plans}!=set(RULE_NAMES):
        raise ValueError('Rule source contract mismatch')
    implementation={name:digest(Path(__file__).with_name(name).read_bytes()) for name in
                    ('rule_evaluation.py','rule_sources.py','rules.py','noise_policy.py','p1_evaluation.py','p1_inputs.py','identity.py','vendor_identity_rules.py')}
    results=[]
    for plan in plans:
        code=plan['rule_id'];bound={role:sources.get(role,[]) for role in REQUIREMENTS[code]}
        applicable=not KINDS.get(code) or tx[0]['kind'] in KINDS[code]
        if applicable and digest(canonical(bound))!=plan['source_checksum']:
            raise ValueError('Rule source payload/checksum mismatch')
        actual_refs={(ROLES.get(role,role),r['record_id'],r['revision']):_ref(ROLES.get(role,role),r)
                     for role,records in bound.items() for r in records}
        expected_refs=[actual_refs[k] for k in sorted(actual_refs)] if applicable else []
        if expected_refs!=plan['evidence_refs']:
            raise ValueError('Rule evidence does not match source payload')
        result=dict(rule_id=code,name=RULE_NAMES[code],status='unavailable',available=False,matched=None,
            intrinsic_points=None,score=None,reason=None,gaps=deepcopy(plan['gaps']),
            evidence_refs=deepcopy(expected_refs),source_status=plan['source_status'],
            source_checksum=plan['source_checksum'],details={})
        if not applicable:
            result.update(status='not_applicable',reason=dict(code='rule_not_applicable',message='Loại giao dịch ngoài phạm vi luật; không phải kết quả không trúng luật.'))
        elif plan['source_status']!='ready' or plan['gaps']:
            result['reason']=dict(code='rule_sources_unavailable',message='Chưa đủ nguồn để đánh giá luật; xem bảng/trường hoặc phiên bản tham chiếu cần bổ sung trong gaps.')
        elif code not in SUPPORTED:
            result['reason']=dict(code='rule_source_profile_required',message='Luật đã có evaluator trong profile nguồn đầy đủ agent2-rule-snapshot/1.0.0; snapshot canonical này chưa có đường ánh xạ đủ nguồn. Không tự điền trường thiếu hoặc trả điểm 0.')
        else:
            if code=='E3':
                if len(bound['vendor'])!=1 or not bound['vendors']:
                    raise ValueError('Ready E3 lacks required source payload')
                evaluated=_e3(bound)
            elif code in ('B5','E4'):evaluated=vendor_identity_rules.evaluate(bound,meta)
            else:evaluated=p1_evaluation.evaluate(bound,meta)
            result['details']=evaluated['details']
            if 'error' in evaluated:
                result['reason']=dict(zip(('code','message'),evaluated['error']))
            else:
                result.update(status='evaluated_hit' if evaluated['matched'] else 'evaluated_no_hit',
                    available=True,matched=evaluated['matched'],intrinsic_points=evaluated['intrinsic_points'],
                    score=evaluated['score'])
        if code not in SUPPORTED:
            result['details'].update(evaluator_registered=True,required_input_profile='agent2-rule-snapshot/1.0.0')
        results.append(result)
    summary={status:sum(r['status']==status for r in results) for status in
             ('evaluated_hit','evaluated_no_hit','unavailable','not_applicable')}
    evaluated=summary['evaluated_hit']+summary['evaluated_no_hit']
    return dict(version=VERSION,coverage_status='partial' if evaluated else 'unavailable',
        rules=results,summary=summary,implementation=implementation,
        configuration=dict(fuzzy_similarity=DEFAULT_CONFIG['fuzzy_similarity'],noise_policy=DEFAULT_CONFIG['noise_policy']),
        coverage_basis='known_records_in_this_snapshot_only_not_complete_external_books',
        aggregate=dict(available=False,score=None,reason=dict(code='rules_incomplete',
            message='Chưa đánh giá đầy đủ bộ luật và tổng hợp canonical; không cộng điểm từng phần thành điểm tổng.')))
