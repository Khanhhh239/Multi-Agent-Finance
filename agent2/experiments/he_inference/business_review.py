"""Locked synthetic review packet; declared business feedback is not a label.

Offline rehearsal only. No Portal route, credential, approval, training export,
original-document verification or production timing authority is introduced.
"""
from copy import deepcopy
from datetime import datetime,timezone
import json
import math
from pathlib import Path

from finance_input import AccessScope
from sme_fraud.snapshot_features import build_from_snapshot,utc
from .protocol import canonical,read_json,sha
from .registry_export import ReadOnlySnapshots,_load_model

VERSION='he-business-review-demo/1.0.0'
FEEDBACK='he-business-review-feedback/1.0.0'
RESOLUTIONS={'confirmed_risk','legitimate','inconclusive'}
USEFULNESS={'yes','no','not_assessed'}


def packet_hash(packet):
    return sha(canonical({k:v for k,v in packet.items() if k!='packet_id'}))


def validate_packet(packet):
    if packet.get('version')!=VERSION or packet.get('data')!='synthetic_only' or packet.get('packet_id')!='brp_'+packet_hash(packet):
        raise ValueError('packet checksum/version mismatch')
    if packet.get('selected_features')!=['log_abs_amount','event_hour_sin'] or packet.get('training_eligible') is not False:
        raise ValueError('demo cannot expand features or become training data')
    cases=packet['cases'];ids=set()
    for case in cases:
        if case['case_id'] in ids:raise ValueError('duplicate case')
        ids.add(case['case_id']);evidence=case['evidence'];seen=set()
        for row in evidence:
            if row['origin']!='simulated_record' or row['original_verified'] is not False:
                raise ValueError('simulated evidence is not a verified original')
            if row['evidence_id'] in seen or row['evidence_id']!='ev_'+sha(canonical(row['source_record'])):
                raise ValueError('evidence checksum mismatch')
            seen.add(row['evidence_id'])
            source=row['source_record']
            if source['company_id']!=case['company_id'] or source['tenant_id']!=case['tenant_id']:
                raise ValueError('foreign evidence')
            if not source['source']['is_simulated'] or utc(source['observed_at'])>utc(case['knowledge_cutoff']) or utc(source['effective_at'])>utc(case['event_at']):
                raise ValueError('future or nonsimulated evidence')
    if len(ids)!=10 or {c['company_id'] for c in cases}!={'C001','C002'}:
        raise ValueError('requires ten C001/C002 demo cases')
    for company in ('C001','C002'):
        if sorted(c['priority_rank'] for c in cases if c['company_id']==company)!=[1,2,3,4,5]:
            raise ValueError('requires five distinct priority positions per company')
    return packet


def build(packet_root,comparison_file,output):
    root=Path(packet_root).resolve();output=Path(output).resolve()
    if output==root or output.is_relative_to(root):raise ValueError('output must be outside source packet')
    prepared=read_json(root/'prepared.json');comparison=read_json(comparison_file)
    if prepared.get('data')!='synthetic_only' or not comparison.get('score_parity_passed') or comparison.get('data')!='synthetic_only':
        raise ValueError('requires a completed synthetic score comparison')
    for name,expected in prepared['source_sha256'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or sha(path.read_bytes())!=expected:raise ValueError('source packet integrity mismatch')
    config=read_json(root/'enterprise/node.json');store=ReadOnlySnapshots(config['snapshot_db']);cases=[]
    for measured in comparison['companies']:
        company=measured['company_id'];info=next(i for i in prepared['companies'] if i['company_id']==company)
        if measured['artifact_id']!=info['artifact_id'] or measured['snapshot_id']!=info['evaluation_snapshot_id'] or measured['snapshot_checksum']!=info['evaluation_checksum']:
            raise ValueError('comparison does not match pinned company model/snapshot')
        scope=AccessScope('demo',frozenset({company}),'business-demo-builder',frozenset({'data.import'}))
        _,model_manifest,_=_load_model(config['model_db'],scope,info['artifact_id'],lambda:scope,metadata_only=True)
        if model_manifest['selected_columns']!=['log_abs_amount','event_hour_sin']:raise ValueError('this rehearsal keeps the two existing features')
        if (measured['model_version']!=model_manifest['model_version']
                or measured['selected_columns']!=model_manifest['selected_columns']
                or measured['feature_contract_fingerprint']!=model_manifest['feature_contract_fingerprint']):
            raise ValueError('comparison model/feature metadata mismatch')
        manifest=store.get_snapshot(scope,info['evaluation_snapshot_id'])
        if manifest['checksum']!=measured['snapshot_checksum'] or manifest['created_at']!=measured['as_of']:raise ValueError('snapshot cutoff mismatch')
        with store._transaction(scope) as conn:
            _,source=store._read_snapshot(conn,scope,info['evaluation_snapshot_id'])
        if isinstance(source,bytes):source=json.loads(source)
        elif isinstance(source,str):source=json.loads(source)
        frame=build_from_snapshot(store,scope,info['evaluation_snapshot_id'],measured['as_of'])
        data_index={(table,r['record_id'],r['revision']):r for table,rows in source.items() if isinstance(rows,list) for r in rows}
        by_id={(r['record_id'],r['revision']):(r,e) for r,e in zip(frame['rows'],frame['evidence'])}
        metric=measured['trials'][0]['metrics'];scores={(r['record_id'],r['revision']):r for r in metric['rows']}
        from .comparison_metrics import compare_rows
        checked=compare_rows([dict(record_id=r['record_id'],revision=r['revision'],score=r['plaintext_score'],available=True) for r in metric['rows']],
                             [dict(record_id=r['record_id'],revision=r['revision'],score=r['encrypted_score'],available=True) for r in metric['rows']])
        if set(scores)!=set(by_id) or checked['encrypted_order']!=metric['encrypted_order'] or not checked['all_scores_within_tolerance']:
            raise ValueError('comparison rows/order mismatch')
        for rank,key in enumerate(metric['encrypted_order'],1):
            identity=tuple(key);row,evidence=by_id[identity];tx=data_index[('transactions',*identity)]
            selected=[]
            for ref in evidence['records']:
                raw=deepcopy(data_index[(ref['table'],ref['record_id'],ref['revision'])])
                # Money strings render exactly in JS; untouched source stays
                # locked separately and is never sent as a predictor.
                fields={k:str(raw[k]) for k in ('amount_vnd',) if k in raw}
                selected.append(dict(evidence_id='ev_'+sha(canonical(raw)),table=ref['table'],
                    record_id=ref['record_id'],revision=ref['revision'],source_record=raw,money_display=fields,
                    origin='simulated_record',original_verified=False))
            binding=dict(tenant_id='demo',company_id=company,snapshot_id=measured['snapshot_id'],
                         artifact_id=measured['artifact_id'],record_id=identity[0],revision=identity[1],as_of=measured['as_of'])
            cases.append(dict(**binding,case_id='brc_'+sha(canonical(binding)),priority_rank=rank,
                score=scores[identity]['encrypted_score'],model_version=measured['model_version'],
                event_at=row['event_at'],knowledge_cutoff=row['as_of'],amount_vnd=str(tx['amount_vnd']),currency=tx['currency'],
                description=tx.get('description',''),question='Khoản thanh toán này có đúng nhà cung cấp, nghĩa vụ, số tiền và thời điểm được phép không?',
                why='Giao dịch được xếp ưu tiên tương đối trong 5 mẫu của doanh nghiệp, từ model dùng số tiền và giờ phát sinh. Điểm không xác nhận sai phạm.',
                documents_to_request=['Hóa đơn gốc và hồ sơ nghĩa vụ/hợp đồng','Phê duyệt chi và chứng từ chuyển tiền','Lịch sử thanh toán đầy đủ để đối chiếu các khoản liên quan'],
                source_limits=['Các bản ghi bên dưới là mô phỏng, không phải chứng từ gốc đã xác minh.',
                    'Snapshot này không cung cấp bản ghi phê duyệt hoặc tài liệu đính kèm gốc.',
                    'Lịch sử chỉ nằm trong snapshot được cấp; không chứng minh sổ sách bên ngoài đã đầy đủ.'],evidence=selected))
    value=dict(version=VERSION,data='synthetic_only',created_at=datetime.now(timezone.utc).isoformat(),
        purpose='offline workflow rehearsal; no verified business benefit or label',
        comparison_sha256=sha(Path(comparison_file).read_bytes()),review_budget_per_company=5,
        selected_features=['log_abs_amount','event_hour_sin'],cases=cases,
        baseline_rules_comparison=None,training_eligible=False,timing_trust='unverified_browser_active_time')
    value['packet_id']='brp_'+packet_hash(value);validate_packet(value)
    output.mkdir(parents=True,exist_ok=False)
    (output/'packet.json').write_bytes(canonical(value))
    from .business_review_page import render
    render(value,output)
    (output/'summary.empty.json').write_bytes(canonical(summarize(value,dict(version=FEEDBACK,packet_id=value['packet_id'],reviews=[]))))
    return value


def validate_feedback(packet,feedback):
    validate_packet(packet)
    if not isinstance(feedback,dict) or set(feedback)!={'version','packet_id','reviews'} or feedback['version']!=FEEDBACK or feedback['packet_id']!=packet['packet_id']:
        raise ValueError('feedback does not belong to this packet')
    if not isinstance(feedback['reviews'],list) or len(feedback['reviews'])>500:raise ValueError('invalid review list')
    cases={c['case_id']:c for c in packet['cases']};versions={}
    fields={'case_id','revision','reviewer_name_declared','resolution','usefulness','explanation','action',
            'missing_materials','reviewed_evidence_ids','checks_completed','active_ms','timer_basis','submitted_at'}
    for r in feedback['reviews']:
        if not isinstance(r,dict) or set(r)!=fields or r['case_id'] not in cases:raise ValueError('unknown review fields or case')
        if type(r['revision']) is not int or not 1<=r['revision']<=500:raise ValueError('invalid revision')
        if r['resolution'] not in RESOLUTIONS or r['usefulness'] not in USEFULNESS:raise ValueError('invalid decision')
        for name in ('reviewer_name_declared','explanation','action','missing_materials'):
            if not isinstance(r[name],str) or len(r[name])>4000:raise ValueError('invalid text')
        if not r['reviewer_name_declared'].strip() or not r['explanation'].strip():raise ValueError('reviewer and explanation required')
        if r['usefulness']=='yes' and not r['action'].strip():raise ValueError('useful requires a concrete action')
        if type(r['checks_completed']) is not bool:raise ValueError('invalid checks acknowledgement')
        if r['resolution']=='inconclusive' and (not r['missing_materials'].strip() or not r['action'].strip()):
            raise ValueError('inconclusive requires missing material and next action')
        allowed={e['evidence_id'] for e in cases[r['case_id']]['evidence']};refs=r['reviewed_evidence_ids']
        if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs) or len(set(refs))!=len(refs) or not set(refs)<=allowed:
            raise ValueError('evidence outside locked case manifest')
        if r['resolution']!='inconclusive' and (not r['checks_completed'] or not refs):
            raise ValueError('a conclusion requires source references and completed checks declaration')
        if type(r['active_ms']) not in (int,float) or not math.isfinite(r['active_ms']) or not 1<=r['active_ms']<=2**53-1 or r['timer_basis']!='unverified_browser_active_time':
            raise ValueError('invalid or falsely verified timing')
        utc(r['submitted_at'])
        key=(r['case_id'],r['revision'])
        if key in versions and versions[key]!=r:raise ValueError('conflicting review revisions')
        versions[key]=deepcopy(r)  # exact duplicates never double-count
    per_case={}
    for (case_id,revision),r in versions.items():per_case.setdefault(case_id,{})[revision]=r
    for values in per_case.values():
        if sorted(values)!=list(range(1,len(values)+1)):raise ValueError('missing review revision history')
    return per_case


def merge_feedback(packet,files):
    all_rows=[]
    for feedback in files:
        validate_feedback(packet,feedback);all_rows.extend(feedback['reviews'])
    merged=dict(version=FEEDBACK,packet_id=packet['packet_id'],reviews=all_rows)
    values=validate_feedback(packet,merged)
    merged['reviews']=[values[k][rev] for k in sorted(values) for rev in sorted(values[k])]
    return merged


def summarize(packet,feedback):
    history=validate_feedback(packet,feedback);latest={k:v[max(v)] for k,v in history.items()};groups=[]
    for company in ('C001','C002'):
        ids={c['case_id'] for c in packet['cases'] if c['company_id']==company}
        reviews=[v for k,v in latest.items() if k in ids]
        yes=sum(r['usefulness']=='yes' for r in reviews);no=sum(r['usefulness']=='no' for r in reviews)
        ms=sum(r['active_ms'] for k,versions in history.items() if k in ids for r in versions.values())
        groups.append(dict(company_id=company,selected=len(ids),reviewed=len(reviews),unreviewed=len(ids)-len(reviews),
            declared_useful=yes,declared_not_useful=no,usefulness_not_assessed=sum(r['usefulness']=='not_assessed' for r in reviews),
            declared_useful_fraction=yes/(yes+no) if yes+no else None,
            inconclusive=sum(r['resolution']=='inconclusive' for r in reviews),
            browser_active_minutes=ms/60000 if reviews else None,timing_verified=False,
            declared_useful_per_browser_active_minute=yes/(ms/60000) if yes+no and ms>0 else None))
    return dict(version='he-business-review-summary/1.0.0',packet_id=packet['packet_id'],data='synthetic_only',
        status='awaiting_human_review' if not latest else 'demo_declarations_only',companies=groups,
        review_revisions=sum(len(v) for v in history.values()),reviewer_identity_verified=False,
        business_effectiveness_verified=False,incremental_benefit_vs_rules=None,training_eligible=False,
        feature_expansion_recommended=False,remaining_technical_issue='HE-AC-01: native worker crash before commit not recoverable')
