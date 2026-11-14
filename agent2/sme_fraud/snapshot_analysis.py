"""Read-only P1/E3 analysis and role-specific output over verified snapshots."""
from copy import deepcopy
from datetime import timezone
from pathlib import Path

from finance_input.json_io import loads
from finance_input.validation import stamp
from .import_files import canonical,digest,fail

VERSION='snapshot-analysis/1.1.0'
MAX_TRANSACTIONS=200
MAX_SOURCE_RECORDS=1000
CHECKS={'P1':('payment_invoice','Đối chiếu thanh toán hóa đơn'),
        'E3':('vendor_names','Đối chiếu danh mục nhà cung cấp')}
RECORD_TYPES={'transactions':('transaction','Giao dịch'),'invoices':('invoice','Hóa đơn'),
    'payment_allocations':('payment_allocation','Phân bổ thanh toán'),'vendors':('vendor','Nhà cung cấp'),
    'payment_history_coverage':('history_export','Phạm vi lịch sử thanh toán'),
    'employees':('employee','Nhân viên'),'approvals':('approval','Phê duyệt'),
    'supporting_documents':('document','Chứng từ'),'vendor_bank_history':('bank_history','Lịch sử tài khoản')}
CODE_FILES=('snapshot_analysis.py','snapshot_analysis.schema.json','rule_evaluation.py','rule_sources.py',
    'p1_evaluation.py','p1_inputs.py','rules.py','noise_policy.py','identity.py','snapshot_features.py','method_adapters.py',
    'analysis_branches.py','analysis_resources.py','ml_estimators.py','unsupervised_statistics.py','score_statistics.py','method_preprocess.py','vendor_identity_rules.py')
FACTS=('invoice_gross_vnd','prior_paid_vnd','current_allocated_vnd','cumulative_paid_vnd','excess_vnd')


def normalize_as_of(value):
    try:return stamp(value).astimezone(timezone.utc).isoformat()
    except (TypeError,ValueError,OverflowError):
        fail(400,'AS_OF_INVALID','Mốc as_of phải là thời gian ISO 8601 có múi giờ.',
            'Ví dụ 2026-10-10T11:00:00+07:00; không dùng thời gian không rõ múi giờ.')


def analyze_snapshot(store,scope,snapshot_id,as_of,*,technical=False,recheck=None,resources=None):
    """Internal caller supplies trusted scope; HTTP adapter also gates director view."""
    as_of=normalize_as_of(as_of)
    manifest=store.get_snapshot(scope,snapshot_id,recheck)
    if manifest['contract_version']=='agent2-rule-snapshot/1.0.0':
        from .rule_snapshot import analyze
        return analyze(store,scope,snapshot_id,as_of,technical=technical,recheck=recheck,resources=resources)
    raw=store.get_snapshot(scope,snapshot_id,recheck,data=True)
    if digest(raw)!=manifest['data_checksum']:
        fail(500,'ARTIFACT_INTEGRITY','Checksum snapshot không khớp.','Đối chiếu kho snapshot trước khi phân tích.')
    data=loads(raw)
    if (len(data['transactions'])>MAX_TRANSACTIONS or
        sum(len(v) for v in data.values() if isinstance(v,list))>MAX_SOURCE_RECORDS):
        fail(413,'ANALYSIS_LIMIT','Snapshot vượt giới hạn phân tích đồng bộ của bản demo.',
            'Dùng snapshot thử tối đa 200 bản ghi giao dịch và 1.000 bản ghi nguồn, giữ đủ lịch sử/liên kết; không tự cắt lịch sử để chấm.')
    # Deliberately lazy: import-only/status requests never load or invoke models.
    from .method_adapters import score_snapshot,_versions
    from .analysis_resources import AnalysisResources
    from .analysis_branches import project_branches,branch_summary,source_limits
    resources=resources or AnalysisResources()
    loaded=resources.load(scope,recheck)
    scored=score_snapshot(store,scope,snapshot_id,as_of,methods=loaded['methods'],artifacts=loaded['artifacts'],recheck=recheck)
    binding={k:manifest[k] for k in ('snapshot_id','tenant_id','company_id','checksum','data_checksum','contract_version')}
    if scored['snapshot']!=binding:
        fail(500,'ARTIFACT_INTEGRITY','Snapshot đã đổi trong lúc phân tích.','Kiểm tra kho bất biến rồi chạy lại.')
    source={(table,r['record_id'],r['revision']):r for table,records in data.items() if isinstance(records,list) for r in records}
    implementation={name:digest(Path(__file__).with_name(name).read_bytes()) for name in CODE_FILES}
    analysis_id='ana_'+digest(canonical(dict(snapshot=binding,as_of=as_of,implementation=implementation,
        feature_contract=scored['feature_contract_fingerprint'],checks=list(CHECKS),resources=loaded['binding'],runtime=_versions())))

    def public_ref(table,ref):
        record=source.get((table,ref['record_id'],ref['revision']))
        if record is None:raise ValueError('Analysis evidence outside snapshot')
        kind,label=RECORD_TYPES[table]
        result=dict(record_type=kind,source=label,record_id=ref['record_id'],revision=ref['revision'],
            effective_at=record['effective_at'],observed_at=record['observed_at'],
            source_kind='simulated' if record['source']['is_simulated'] else 'source_export')
        if 'name' in record:result['display_name']=record['name']
        if table=='invoices':result['document_number']=record['number']
        return result

    def business_reason(rule):
        if rule['status']=='not_applicable':return 'Đối chiếu này không áp dụng cho loại giao dịch hiện tại.'
        if rule['available']:return None
        code=(rule['reason'] or {}).get('code','')
        if code=='name_content_insufficient':return 'Tên nhà cung cấp chưa đủ thông tin để đối chiếu; cần bổ sung tên nguồn.'
        if 'adjustment' in code:return 'Cần đối chiếu chứng từ và liên kết của khoản điều chỉnh.'
        if code=='p1_allocated_exceeds_payment':return 'Tổng phân bổ vượt tiền giao dịch; cần đối chiếu số tiền và liên kết.'
        if 'invoice_value' in code or 'cap_nonpositive' in code:return 'Giá trị nghĩa vụ hóa đơn chưa nhất quán; cần đối chiếu nguồn.'
        if 'revision' in code:return 'Liên kết chưa khớp phiên bản nguồn; cần bổ sung hoặc sửa tham chiếu.'
        return 'Chưa đủ nguồn hoặc căn cứ nhất quán để thực hiện đối chiếu này.'

    def business_check(code,rule,group_ids,group_signal):
        unavailable=rule['status']=='unavailable';applicable=rule['status']!='not_applicable'
        needed=(rule['matched'] or group_signal) if rule['available'] else None
        state='unavailable' if unavailable else 'not_applicable' if not applicable else 'needs_review' if needed else 'no_signal'
        evidence=[public_ref(r['table'],r) for r in rule['evidence_refs']]
        missing=[]
        for gap in rule['gaps']:
            item=dict(source=RECORD_TYPES.get(gap['table'],('related','Nguồn liên quan'))[1],
                action='Bổ sung hoặc đối chiếu nguồn có định danh và thời điểm rõ ràng; không tự điền dữ liệu còn thiếu.')
            if 'record_id' in gap:item['record_id']=gap['record_id']
            if 'revision' in gap:item['revision']=gap['revision']
            if item not in missing:missing.append(item)
        facts=[]
        if rule['available'] and code=='P1':
            for fact in rule['details']['invoice_checks']:
                facts.append(dict(**{k:fact[k] for k in FACTS},
                    invoice_refs=[public_ref('invoices',r) for r in fact['invoice_refs']]))
        if rule['available'] and code=='E3':
            peers={pair[1] for pair in rule['details']['evidence']['top_matches']}
            facts=[dict(vendor_ref=public_ref('vendors',r)) for r in rule['evidence_refs']
                   if r['table']=='vendors' and r['record_id'] in peers]
        return dict(name=CHECKS[code][1],status=state,available=rule['available'],needs_review=needed,
            reason=business_reason(rule),missing_sources=missing,evidence_refs=evidence,facts=facts,group_refs=group_ids)

    groups={};rows=[];unavailable=0;review_rows=0
    for row in scored['rows']:
        if (row['tenant_id'],row['company_id'])!=(scope.tenant_id,manifest['company_id']):
            raise ValueError('Analysis row outside caller scope')
        tx=source[('transactions',row['record_id'],row['revision'])]
        all_rules=row['methods']['rules']['details']['rule_results']['rules']
        selected={r['rule_id']:r for r in all_rules if r['rule_id'] in CHECKS}
        if set(selected)!=set(CHECKS):raise ValueError('Missing requested rule result')
        group_ids=[];group_signal=False
        p1=selected['P1']
        for group in p1['details'].get('simultaneous_checks',[]) if p1['available'] else []:
            group_id=group['group_id'] if technical else 'grp_'+digest(canonical(group['group_id']))[:24]
            group_ids.append(group_id);group_signal|=group['matched']
            if technical:item=deepcopy(group)
            else:
                item=dict(group_id=group_id,status='needs_review' if group['matched'] else 'no_signal',
                    needs_review=group['matched'],event_at=group['event_at'],knowledge_at=group['as_of'],
                    **{k:group[k] for k in ('prior_paid_vnd','group_allocated_vnd','cumulative_paid_vnd','invoice_gross_vnd','excess_vnd')},
                    transaction_refs=[public_ref('transactions',r) for r in group['transaction_refs']],
                    allocation_refs=[public_ref('payment_allocations',r) for r in group['allocation_refs']],
                    prior_allocation_refs=[public_ref('payment_allocations',r) for r in group['prior_allocation_refs']])
            if group_id in groups and groups[group_id]!=item:raise ValueError('Conflicting analysis group')
            groups[group_id]=item
        public_checks={CHECKS[code][0]:business_check(code,selected[code],group_ids if code=='P1' else [],group_signal if code=='P1' else False) for code in CHECKS}
        unavailable+=sum(r['status']=='unavailable' for r in selected.values())
        review_rows+=any(c['needs_review'] is True for c in public_checks.values())
        item=dict(transaction_id=row['record_id'],revision=row['revision'],event_at=row['event_at'],knowledge_at=row['as_of'],
            amount_vnd=tx['amount_vnd'],kind=tx['kind'],description=tx['description'],
            source_kind='simulated' if tx['source']['is_simulated'] else 'source_export')
        item['branches']=project_branches(row,loaded,public_ref)
        if technical:
            item['rules']=deepcopy(selected)
            item['rules']['P1']['details'].pop('simultaneous_checks',None)
            item['rules']['P1']['details']['simultaneous_group_refs']=group_ids
            item['methods']={k:v for k,v in row['methods'].items() if k!='rules'}
            item['graph_evidence']=row['graph']
            all_rules=row['methods']['rules']['details']['rule_results']
            item['rule_coverage']=dict(summary=all_rules['summary'],rules=[{k:deepcopy(r[k]) for k in
                ('rule_id','name','status','available','matched','score','intrinsic_points','reason','gaps','evidence_refs','details')} for r in all_rules['rules']])
        else:item['checks']=public_checks
        rows.append(item)
    if len(rows)!=scored['row_count']:raise ValueError('Analysis dropped rows')
    result=dict(version=VERSION,analysis_id=analysis_id,view='technical' if technical else 'review',as_of=as_of,
        analysis_context_id='actx_'+loaded['binding_hash'],
        snapshot={k:binding[k] for k in ('snapshot_id','company_id','checksum','data_checksum','contract_version')},
        supported_checks=[v[0] for v in CHECKS.values()],row_count=len(rows),rows=rows,
        groups=[groups[k] for k in sorted(groups)],
        branch_summary=branch_summary(rows),source_limits=source_limits(data,manifest['company_id'],as_of),
        summary=dict(transaction_count=len(rows),transactions_to_review=review_rows,unavailable_checks=unavailable,
            groups_to_review=sum(g.get('matched',g.get('needs_review',False)) for g in groups.values()),analysis_complete=False),
        coverage_message='Đã gọi bốn nhánh luật, thống kê, quan hệ và bất thường. Luật canonical có thanh toán hóa đơn, tên NCC và trùng thông tin NCC khi đủ nguồn; chưa đánh giá toàn bộ bộ quy tắc. Trùng thông tin là kiểm tra master, chưa tự tạo cảnh báo giao dịch. Nhánh thiếu nguồn hoặc phiên bản đã fit vẫn chưa khả dụng; chưa cộng thành điểm tổng.')
    if technical:
        result.update(implementation=implementation,feature_contract_fingerprint=scored['feature_contract_fingerprint'],
            inference_binding=dict(selection=loaded['selected'],resources=loaded['binding']['resources'],binding_error=loaded['binding']['error']),
            aggregate=dict(available=False,score=None,reason=dict(code='rules_incomplete',message='Chưa đánh giá đầy đủ toàn bộ luật; không cộng điểm từng phần thành tổng.')))
    resources.recheck(scope,loaded)
    if recheck is not None and recheck()!=scope:
        fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trong lúc phân tích.','Chạy lại theo quyền hiện hành.')
    return result
