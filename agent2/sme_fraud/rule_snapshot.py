"""All 35 retained rules on immutable enterprise-owned source snapshots.

This explicit source profile accepts the retained tables. It does not invent
legacy fields from sparse canonical rows, change weights or route plaintext
to a cloud worker. Transaction findings and scope diagnostics stay separate.
"""
from copy import deepcopy
from pathlib import Path
from finance_input import AccessScope
from .import_files import canonical,digest,fail,ImportFailure
from .rules import RULE_NAMES
from .native_rule_node import validate_bundle,evaluate_bundle,REQUIRED,TABLES
from .snapshot_features import utc
from .rule_snapshot_visibility import visible, candidate_frame, unavailable_native, unavailable_scored_row, REASON as VISIBILITY_REASON, MESSAGE as VISIBILITY_MESSAGE

CONTRACT='agent2-rule-snapshot/1.0.0'
VERSION='snapshot-rule-analysis/1.0.0'
MAX_CANDIDATES=200
SCOPE_RULES=set(('D1','D2','D3','D4','D5','D6','F4'))
ROW_KINDS={**{k:('vendor_payment',) for k in ('A1','A2','A3','A6','B6','B7','P1')},'E1':('payroll',),'E2':('payroll',)}
LABELS={'A':'Khoản chi cần đối chiếu','B':'Thông tin nhà cung cấp cần đối chiếu',
 'C':'Phê duyệt và thao tác cần đối chiếu','D':'Phân bố số liệu cần đối chiếu',
 'E':'Nhân sự và danh mục cần đối chiếu','F':'Chứng từ và sổ sách cần đối chiếu',
 'P':'Thanh toán và hóa đơn cần đối chiếu','T':'Tạm ứng cần đối chiếu'}
PUBLIC_NAMES=dict(zip('A1 A2 A3 A4 A5 A6 B1 B2 B3 B4 B5 B6 B7 C1 C2 C3 C4 D1 D2 D3 D4 D5 D6 E1 E2 E3 E4 F1 F2 F3 F4 P1 P2 T1 T2'.split(),[
 'Các khoản chi cùng người nhận','Các khoản chi cùng người lập và người nhận','Các khoản chi qua đối tượng liên quan',
 'Khoản chi gần hạn mức','Số tiền khác lịch sử','Giá trị thanh toán làm tròn',
 'Tài khoản hoặc định danh NCC liên quan nhân viên','Liên hệ giữa NCC và nhân viên','Khoản chi cho NCC mới',
 'Trạng thái NCC và hóa đơn','NCC có thông tin dùng chung','Chi cho NCC sau thời gian ít hoạt động','Thay đổi tài khoản nhận tiền',
 'Thời điểm thao tác và lịch vận hành','Quyền tự duyệt khoản chi','Dấu vết phê duyệt','Thao tác trong thời gian nghỉ',
 'Phân bố chữ số đầu','Phân bố chữ số thứ hai','Phân bố hai chữ số đầu','Phân bố đuôi số','Độ lệch phân bố số liệu','Phân bố theo nhóm dữ liệu',
 'Căn cứ hưởng lương','Kỳ lương và thông tin nghỉ việc','Tên NCC tương tự','Định danh NCC dùng chung',
 'Nguồn bút toán và thời điểm khóa sổ','Thao tác ghi đè quy trình','Số chứng từ','Công nợ và lịch sử thu tiền',
 'Thanh toán và giá trị hóa đơn','Chi tiền mặt và hồ sơ thuế','Tạm ứng và ngày đến hạn','Căn cứ xóa nợ tạm ứng']))
assert set(PUBLIC_NAMES)==set(RULE_NAMES)


def catalogue():
    from .rule_evaluation import SUPPORTED
    return [dict(rule_id=k,name=v,implemented=True,profile=CONTRACT,required_tables=list(REQUIRED[k]),
        canonical_supported=k in SUPPORTED,he_supported=False,canonical_he_supported=k=='P1',
        scope='aggregate_or_source' if k in SCOPE_RULES else 'transaction_and_evidence') for k,v in RULE_NAMES.items()]


def validate(data,scope,*,committed=False):
    def error(path,message,code='RULE_SOURCE_INVALID'):
        return dict(code=code,path=path,table=None,row=None,field=None,message=message,
            action='Bổ sung đúng nguồn theo profile, xuất lại checksum rồi kiểm tra; không điền giá trị giả.')
    result=dict(contract_version=CONTRACT,validator_version='rule-snapshot-validator/1.0.0',profile_version=CONTRACT,
        report_version='1.2.0',status='rejected',errors=[],warnings=[],counts={},capabilities={},analysis_limits={})
    if not isinstance(scope,AccessScope) or len(scope.company_ids)!=1 or 'data.import' not in scope.permissions or not scope.actor_id:
        result['errors']=[error('$','Không có quyền đọc/nhập nguồn doanh nghiệp.','ACCESS_DENIED')];return result
    company=next(iter(scope.company_ids))
    if not isinstance(data,dict) or data.get('tenant_id')!=scope.tenant_id or data.get('company_id')!=company:
        result['errors']=[error('$','Nguồn ngoài phạm vi doanh nghiệp.','ACCESS_DENIED')];return result
    if set(data)!={'contract_version','tenant_id','company_id','source','candidate_transaction_ids'} or data.get('contract_version')!=CONTRACT:
        result['errors']=[error('$','Tệp phải đúng profile agent2-rule-snapshot/1.0.0.')];return result
    from finance_input.validation import StrictValidator,FORMATS
    import json
    specification=json.loads(Path(__file__).with_name('rule_snapshot.schema.json').read_bytes())
    structural=list(StrictValidator(specification,format_checker=FORMATS).iter_errors(data))
    if structural:
        result['errors']=[error('.'.join(map(str,e.absolute_path)) or '$','Cấu trúc/kiểu dữ liệu không khớp schema profile nguồn luật.') for e in structural[:100]];return result
    ids=data['candidate_transaction_ids']
    if not isinstance(ids,list) or not 1<=len(ids)<=MAX_CANDIDATES or any(not isinstance(i,str) or not i for i in ids) or len(ids)!=len(set(ids)):
        result['errors']=[error('candidate_transaction_ids','Cần 1–200 mã giao dịch duy nhất để đánh giá; lịch sử để trong source.')];return result
    try:checked=validate_bundle(data['source'],scope)
    except Exception as e:
        from .import_files import ImportFailure
        if not isinstance(e,ImportFailure):raise
        result['errors']=[error('source','Nguồn ngoài quyền hoặc không hợp lệ.',e.code)];return result
    if checked['errors']:
        result['errors']=[error('source.'+e['path'],e['message']) for e in checked['errors']];return result
    source=data['source'];rows={r['transaction_id']:r for r in source['tables'].get('transactions',[])}
    if any(r.get('currency')!='VND' for r in rows.values()):
        result['errors']=[error('source.tables.transactions.currency','Profile này chỉ nhận số tiền VND; cần chuyển đổi có nguồn trước khi nhập.','RULE_CURRENCY_UNSUPPORTED')];return result
    if any(r.get('tenant_id',scope.tenant_id)!=scope.tenant_id for records in source['tables'].values() for r in records):
        result['errors']=[error('source','Nguồn có bản ghi ngoài tenant.','ACCESS_DENIED')];return result
    attested=any(r.get('status')=='verified' or r.get('callback_verified') in (1,True) for records in source['tables'].values() for r in records)
    if not committed and not source['is_simulated'] and attested and 'evidence.verify' not in scope.permissions:
        result['errors']=[error('source','Nhập nguồn thật có xác minh cần quyền evidence.verify; đọc snapshot đã lưu không xác minh mới.','VERIFICATION_PERMISSION')];return result
    for i,identity in enumerate(ids):
        if identity not in rows:result['errors'].append(error(f'candidate_transaction_ids[{i+1}]','Không tìm thấy giao dịch trong nguồn cùng doanh nghiệp.'))
    if result['errors']:return result
    for name in ('companies','employees','transactions'):
        if not source['tables'].get(name):result['errors'].append(error('source.tables.'+name,'Thiếu nguồn lõi để chạy engine; giữ dữ liệu chưa đủ trong luồng canonical hoặc bổ sung nguồn.'))
    if result['errors']:return result
    result['status']='accepted_with_warnings';result['required_as_of']=source['as_of'];result['counts']={'transactions':len(ids),'source_records':sum(len(r) for r in source['tables'].values())}
    result['capabilities']={company:dict(rule_catalogue=dict(implemented=35,execution='enterprise_local_only',he=False))}
    result['warnings']=[error('source','Profile chạy luật tại node doanh nghiệp; thiếu bảng/coverage làm luật tương ứng unavailable. Chưa có ML feature bridge hoặc full-catalog HE.','RULE_PROFILE_LIMITS')]
    result['analysis_limits']={company:[]};return result


def _public_ref(table,row):
    ref=dict(record_type='transaction' if table=='transactions' else 'related',source={'transactions':'Giao dịch','employees':'Hồ sơ nhân viên','vendors':'Hồ sơ nhà cung cấp','entity_links':'Liên kết thực thể'}.get(table,'Nguồn liên quan'),
        record_id=str(row.get('record_id') or row.get('transaction_id') or row.get('evidence_id') or row.get('document_id') or row.get('vendor_id') or row.get('employee_id') or row.get('company_id')),
        revision=int(row.get('revision',1)),effective_at=row.get('effective_at',row.get('posted_at',row.get('observed_at'))),observed_at=row['observed_at'],source_kind='source_export')
    if row.get('full_name') or row.get('name'):ref['display_name']=row.get('full_name') or row.get('name')
    return ref


def source_guards(data,native):
    """An empty export is not an approved authority or known-zero attendance.

    Leave the retained engine unchanged; withhold unsupported findings and
    never turn its authority fallback into a confirmed canonical decision.
    """
    source=data['source'];tables=source['tables'];candidates=set(data['candidate_transaction_ids'])
    current=[t for t in tables.get('transactions',[]) if t['transaction_id'] in candidates and visible(t,source['as_of'])]
    from .authority_policy import ApprovalAuthority
    from .identity import normalize
    from .noise_policy import name_key
    authority=ApprovalAuthority(tables)
    for entry in native['rules']:
        code=entry['rule_id'];gaps=[]
        if code in ROW_KINDS and not any(t['txn_type'] in ROW_KINDS[code] and t['observed_at']<=source['as_of'] and t['posted_at']<=source['as_of'] for t in tables.get('transactions',[])):
            entry.update(available=False,status='not_applicable',matched=None,score=None,reason='rule_not_applicable_to_source_kinds',gaps=[],hits=[],groups=[]);continue
        if code in ('C2','C3'):
            for name in ('approval_authorities','approval_authority_coverage'):
                if not tables.get(name):gaps.append(dict(table=name,reason='approved_authority_source_missing'))
            for tx in current:
                if code=='C2' and tx['creator_id']!=tx['approver_id']:continue
                decision=authority.self_approval(tx) if code=='C2' else authority.checker_level(tx)
                if decision['mode']!='authority_matrix' or decision['status'] in ('ambiguous_coverage','ambiguous_authority','unknown_actor'):
                    gaps.append(dict(table='approval_authority_coverage',record_id=tx['transaction_id'],reason='authority_not_covered_or_ambiguous_at_action'))
                actor=tx['creator_id'] if code=='C2' else tx['approver_id'];staff=authority.employee_at(tx['company_id'],actor,tx['approved_at'])
                if decision['status']=='no_matching_authority' and (not staff or not isinstance(staff.get('role'),str) or normalize(staff['role']) in ('','UNKNOWN','NONE','NULL')):
                    gaps.append(dict(table='employees',record_id=actor,reason='actor_role_not_known_for_authority_scope'))
        if code in ('B2','B5','E4') and entry['matched'] is not True:
            fields=('phone','address') if code=='B2' else ('phone','address','bank_account','related_party_disclosed_at')
            names=('vendors','employees') if code=='B2' else ('vendors',)
            for name in names:
                for record in tables.get(name,[]):
                    for field in fields:
                        value=record.get(field)
                        if not isinstance(value,str) or field in ('phone','address') and value.strip() and not normalize(value,field):
                            gaps.append(dict(table=name,field=field,reason='identity_field_unknown'))
        if code=='E3' and entry['matched'] is not True:
            for record in tables.get('vendors',[]):
                if not name_key(record.get('name'))[0]:gaps.append(dict(table='vendors',field='name',reason='name_content_insufficient'))
        if code in ('P1','A6'):
            for tx in current:
                if tx['txn_type']=='vendor_payment' and (not isinstance(tx.get('invoice_number'),str) or not tx['invoice_number'].strip()):
                    gaps.append(dict(table='transactions',record_id=tx['transaction_id'],field='invoice_number',reason='invoice_identity_not_provided'))
        if code=='E1':
            for tx in current:
                if tx['txn_type']!='payroll':continue
                if not any(r.get('employee_id')==tx['employee_id'] and r.get('payroll_period')==tx['payroll_period'] and r['observed_at']<=tx['posted_at'] for r in tables.get('attendance',[])):
                    gaps.append(dict(table='attendance',record_id=tx['transaction_id'],reason='attendance_not_known_for_employee_period'))
        if code=='F3' and not tables.get('document_series'):gaps.append(dict(table='document_series',reason='numbering_scope_not_provided'))
        if gaps:entry.update(available=False,status='unavailable',matched=None,score=None,reason='source_or_scope_unavailable',gaps=entry['gaps']+gaps,hits=[],groups=[])
    return native


def analyze(store,scope,snapshot_id,as_of,*,technical=False,recheck=None,resources=None):
    from finance_input.json_io import loads
    manifest=store.get_snapshot(scope,snapshot_id,recheck);raw=store.get_snapshot(scope,snapshot_id,recheck,data=True)
    if digest(raw)!=manifest['data_checksum']:fail(500,'ARTIFACT_INTEGRITY','Checksum snapshot không khớp.','Đối chiếu kho nguồn.')
    data=loads(raw);report=validate(data,scope,committed=True)
    if report['status']=='rejected':fail(422,'RULE_SNAPSHOT_INVALID','Snapshot nguồn luật không hợp lệ.','Xem báo cáo kiểm tra và xuất nguồn đúng phiên bản.')
    source=data['source']
    if utc(as_of)!=utc(source['as_of']):fail(422,'RULE_CUTOFF_MISMATCH','Mốc phân tích phải khớp phạm vi nguồn đã khóa.','Dùng đúng as_of trong nguồn hoặc tạo snapshot mới có coverage phù hợp.')
    if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Đăng nhập lại.')
    try:native=source_guards(data,evaluate_bundle(source,scope))
    except ImportFailure as error:
        if error.code!='NATIVE_RULE_CORE_MISSING':raise
        native=unavailable_native(source)
    from .analysis_resources import AnalysisResources
    from .analysis_branches import REASONS, branch_summary as compute_branch_summary, graph_branch, quantitative_branch
    from .method_adapters import score_batch, _method, _versions as method_versions
    from .rule_snapshot_features import build_rule_entity_graphs
    resources=resources or AnalysisResources();loaded=resources.load(scope,recheck);rows=[];
    frame=candidate_frame(data,scope,as_of,manifest)
    eligible_ids=[r['record_id'] for r in frame['rows']]
    graphs=build_rule_entity_graphs(data,scope,as_of,eligible_ids) if eligible_ids else {}
    scored=score_batch(frame,scope,artifacts=loaded['artifacts'],methods=loaded['methods'],graphs=graphs) if eligible_ids else dict(rows=[])
    scored_by_id={r['record_id']:r for r in scored['rows']}
    evidence_by_id={r['record_id']:e for r,e in zip(frame['rows'],frame['evidence'])}
    revision_by_id={r['record_id']:r['revision'] for r in frame['rows']}
    review_count=0;rule_summary={s:sum(r['status']==s for r in native['rules']) for s in ('evaluated_hit','evaluated_no_hit','unavailable','not_applicable')}
    by_id={r['transaction_id']:r for r in source['tables']['transactions']};raw_rules={r['rule_id']:r for r in native['rules']};scope_checks=[]
    known=lambda r:visible(r,source['as_of'])
    def check(entry,transaction=None):
        scope_rule=entry['rule_id'] in SCOPE_RULES
        hits=[h for h in entry['hits'] if transaction is None or h.get('transaction_id')==transaction['transaction_id']]
        matched=entry['matched'] if transaction is None else any(not h.get('suppressed_reason') for h in hits)
        row_known=transaction is None or known(transaction)
        applicable=entry['status']!='not_applicable' and (transaction is None or entry['rule_id'] not in ROW_KINDS or transaction['txn_type'] in ROW_KINDS[entry['rule_id']])
        ready=entry['available'] and row_known and applicable
        contextual=scope_rule or entry['scope']=='master_quality' or ready and matched and (all(h.get('scoring_role') in ('context','master_quality') for h in hits) or not any(h.get('points',0)>0 or h.get('hard_trigger') for h in hits))
        needed=bool(matched) and not contextual if ready else None
        state='unavailable' if not row_known else 'not_applicable' if not applicable else 'unavailable' if not ready else 'context_only' if matched and contextual else 'needs_review' if needed else 'no_signal'
        refs=[]
        if transaction is not None and row_known:
            ref=_public_ref('transactions',transaction);ref['source_kind']='simulated' if source['is_simulated'] else 'source_export';refs=[ref]
        for h in hits:
            for field,table,id_field in [('employee_ids','employees','employee_id'),('vendor_ids','vendors','vendor_id'),('transaction_ids','transactions','transaction_id')]:
                values=h.get('evidence',{}).get(field,[])
                if not isinstance(values,list):continue
                cutoff=transaction['posted_at'] if transaction is not None else source['as_of'];versions={}
                for record in source['tables'].get(table,[]):
                    if record.get(id_field) in values and record['observed_at']<=cutoff and record.get('posted_at',record['observed_at'])<=cutoff:
                        key=record.get(id_field)
                        if key not in versions or versions[key]['observed_at']<record['observed_at']:versions[key]=record
                for record in versions.values():
                        ref=_public_ref(table,record);ref['source_kind']='simulated' if source['is_simulated'] else 'source_export'
                        if ref not in refs:refs.append(ref)
        missing=[dict(source='Nguồn '+g.get('table','liên quan'),action='Bổ sung nguồn/coverage đúng thời điểm; không tự điền 0.') for g in entry['gaps']]
        if not applicable:missing=[]
        reason='Chưa đủ nguồn hoặc phạm vi lịch sử để kiểm tra.' if not ready else 'Dấu hiệu theo tập dữ liệu/danh mục; không phải điểm hay kết luận của riêng giao dịch.' if contextual and matched else 'Có căn cứ cần đối chiếu chứng từ gốc.' if needed else 'Không thấy tín hiệu trong phần nguồn đã cung cấp; không khẳng định giao dịch hợp lệ.'
        if not row_known:reason=VISIBILITY_MESSAGE;refs=[];missing=[dict(source='Giao dịch tại mốc phân tích',action='Dùng snapshot mới có nguồn phù hợp khi giao dịch đã phát sinh và được biết.')]
        elif not applicable:reason='Đối chiếu này không áp dụng cho loại giao dịch hiện tại; không phải kết quả không vi phạm.'
        if needed and entry['rule_id']=='B1':
            names=[r.get('display_name',r['record_id']) for r in refs if r['source']=='Hồ sơ nhân viên']
            reason='Tài khoản hoặc định danh NCC có thông tin trùng với nhân viên'+(': '+', '.join(names) if names else '')+'. Cần xác minh người thụ hưởng và hồ sơ liên quan.'
        elif needed and entry['rule_id']=='B2':reason='Có thông tin liên hệ hoặc liên kết giữa NCC và nhân viên cần làm rõ bằng hồ sơ gốc.'
        actions={'A':'Đối chiếu yêu cầu chi, PO/hợp đồng và lịch thanh toán.',
            'B':'Đối chiếu hồ sơ NCC, nhân sự liên quan và xác minh tài khoản nhận.',
            'C':'Đối chiếu nhật ký tạo/duyệt, ma trận thẩm quyền và lịch vận hành/nghỉ phép.',
            'D':'Đối chiếu tập số liệu gốc và cách ghi nhận nghiệp vụ trước khi chọn giao dịch rà.',
            'E':'Đối chiếu bảng công, bảng lương và hồ sơ nhân sự/NCC liên quan.',
            'F':'Đối chiếu chứng từ, log bút toán, lịch khóa sổ và hồ sơ công nợ.',
            'P':'Đối chiếu hóa đơn, phân bổ và lịch sử thanh toán có chứng từ.',
            'T':'Đối chiếu hồ sơ tạm ứng, gia hạn, hoàn ứng hoặc xóa nợ.'}
        if needed and transaction is not None and entry['rule_id'] in ('C2','C3','C4'):
            reason+=' Người lập: '+transaction['creator_id']+'; người duyệt: '+transaction['approver_id']+'.'
        return dict(name=entry['name'] if technical else PUBLIC_NAMES[entry['rule_id']],status=state,available=bool(ready),needs_review=needed,
            reason=reason,missing_sources=missing,evidence_refs=refs,facts=[],group_refs=[],next_action=actions[entry['rule_id'][0]])
    for code in RULE_NAMES:
        if code not in SCOPE_RULES:continue
        scope_checks.append(check(raw_rules[code]))
    for identity in data['candidate_transaction_ids']:
        tx=by_id[identity];checks={f'check_{i+1}':check(r,tx) for i,r in enumerate(native['rules']) if r['rule_id'] not in SCOPE_RULES}
        review_count+=any(c['needs_review'] for c in checks.values())
        if known(tx):scored_row=scored_by_id[identity];row_ev=evidence_by_id[identity];row_rev=revision_by_id[identity]
        else:
            scored_row,row_ev=unavailable_scored_row(tx,frame);row_rev=scored_row['revision']
            scored_row['methods']={m:_method(m,frame,row_ev,reason=(VISIBILITY_REASON,VISIBILITY_MESSAGE)) for m in ('rules',*loaded['methods'])}
        ml_items=[scored_row['methods'][m] for m in sorted(loaded['selected']['ml_artifacts'])]
        ml_branch=quantitative_branch('ml',ml_items)
        if not known(tx):ml_branch['message']=VISIBILITY_MESSAGE
        elif not ml_items and loaded['binding']['error']:ml_branch['message']=REASONS[loaded['binding']['error']]
        rule_branch_entry=dict(name='Luật nghiệp vụ',status='partial',available=False,evaluated_count=35-rule_summary['unavailable']-rule_summary['not_applicable'],unavailable_count=rule_summary['unavailable'],not_applicable_count=rule_summary['not_applicable'],total_count=35,message='Đã gọi đủ 35 evaluator; giữ riêng chẩn đoán nhóm và phần thiếu nguồn. Chưa có điểm tổng.')
        if not known(tx):rule_branch_entry.update(status='unavailable',evaluated_count=0,unavailable_count=35,not_applicable_count=0,message=VISIBILITY_MESSAGE)
        branches=dict(rules=rule_branch_entry,statistics=quantitative_branch('statistics',[scored_row['methods']['robust_z']]),graph=graph_branch(scored_row['graph'],_public_ref),ml=ml_branch)
        if not known(tx):branches['graph']['message']=VISIBILITY_MESSAGE
        item=dict(transaction_id=identity,revision=row_rev,event_at=tx['posted_at'],knowledge_at=tx['observed_at'],amount_vnd=tx['amount_vnd'],kind=tx['txn_type'],description=tx.get('business_purpose',''),source_kind='simulated' if source['is_simulated'] else 'source_export',branches=branches)
        if not known(tx):item['availability']=dict(available=False,reason=dict(code=VISIBILITY_REASON,message=VISIBILITY_MESSAGE))
        if technical:
            entries=[]
            for r in native['rules']:
                hits=[deepcopy(h) for h in r['hits'] if h.get('transaction_id')==identity];is_scope=r['rule_id'] in SCOPE_RULES;applicable=r['status']!='not_applicable' and (r['rule_id'] not in ROW_KINDS or tx['txn_type'] in ROW_KINDS[r['rule_id']]);ready=r['available'] and known(tx) and not is_scope and applicable
                matched=any(not h.get('suppressed_reason') for h in hits) if ready else None
                entries.append(dict(rule_id=r['rule_id'],name=r['name'],scope=r['scope'],status='unavailable' if not known(tx) else 'not_applicable' if is_scope or not applicable else 'unavailable' if not ready else 'evaluated_hit' if matched else 'evaluated_no_hit',available=ready,matched=matched,
                    score=max((h.get('points',0) for h in hits),default=0) if ready else None,
                    reason=VISIBILITY_REASON if not known(tx) else 'see_scope_result' if is_scope else 'rule_not_applicable' if not applicable else None if ready else 'source_or_scope_unavailable',gaps=[dict(table='transactions',reason=VISIBILITY_REASON)] if not known(tx) else deepcopy(r['gaps']),hits=hits if known(tx) else [],scope_result_ref=r['rule_id'] if is_scope and known(tx) else None))
            item['rule_coverage']=dict(summary={s:sum(e['status']==s for e in entries) for s in ('evaluated_hit','evaluated_no_hit','unavailable','not_applicable')},source_scope_summary=rule_summary,rules=entries)
            item['methods']=deepcopy(scored_row['methods'])
            item['feature_missing_reasons']=dict(row_ev['missing_reasons'])
            item['feature_evidence']=dict(records=deepcopy(row_ev['records']),signed_amount_vnd=row_ev['signed_amount_vnd'],history_group=row_ev['history_group'],history_type_record_count=row_ev['history_type_record_count'])
            item['graph']=deepcopy(scored_row['graph'])
        else:item['checks']=checks
        rows.append(item)
    implementation={n:digest(Path(__file__).with_name(n).read_bytes()) for n in ('rule_snapshot.py','rule_snapshot_visibility.py','native_rule_node.py','rules.py','benford.py','noise_policy.py','rule_snapshot_features.py')}
    binding={k:manifest[k] for k in ('snapshot_id','company_id','checksum','data_checksum','contract_version')}
    versions=method_versions()
    model_pins={m:getattr(loaded['artifacts'].get(m),'artifact_id',None) for m in loaded['methods']}
    analysis_seed=dict(snapshot=binding,as_of=source['as_of'],candidates=data['candidate_transaction_ids'],implementation=implementation,feature_contract_fingerprint=frame['contract']['fingerprint'],bridge_sha256=frame['contract']['bridge_sha256'],method_versions=versions,model_pins=model_pins,context=loaded['binding_hash'])
    result=dict(version=VERSION,analysis_id='ana_'+digest(canonical(analysis_seed)),
        analysis_context_id='actx_'+loaded['binding_hash'],view='technical' if technical else 'review',snapshot=binding,as_of=source['as_of'],supported_checks=['retained_catalogue_35'],row_count=len(rows),rows=rows,groups=[],scope_checks=scope_checks,
        summary=dict(transaction_count=len(rows),transactions_to_review=review_count,unavailable_checks=rule_summary['unavailable'],unavailable_transactions=sum(not known(by_id[i]) for i in data['candidate_transaction_ids']),groups_to_review=sum(c['status']=='context_only' for c in scope_checks),analysis_complete=False),
        branch_summary=compute_branch_summary(rows),source_limits=[],
        coverage_message='Đã nối đủ 35 luật và bridge 33 feature point-in-time vào profile nguồn đầy đủ tại node doanh nghiệp. Thiếu nguồn hoặc model không tương thích giữ unavailable; D/F4 đánh giá theo tập/nguồn, không gán điểm gian lận cho mỗi giao dịch. Chưa mở rộng HE cho bridge này hoặc cố định tỷ trọng luật/ML.')
    if technical:
        scoped=[];candidates=set(data['candidate_transaction_ids'])
        for entry in native['rules']:
            item=deepcopy(entry);item['evaluation_unit']='source_scope';item['source_hit_count']=len(entry['hits']);item['hits']=[h for h in item['hits'] if h.get('transaction_id') in candidates];scoped.append(item)
        result.update(catalogue=catalogue(),catalogue_results=scoped,scope_results=[r for r in scoped if r['rule_id'] in SCOPE_RULES],native_reference_sha256=native['native_reference_sha256'],native_source_sha256=native['source_sha256'],implementation=implementation,feature_contract=frame['contract'],bridge_provenance=dict(frame['manifest'],method_versions=versions,model_pins=model_pins),aggregate=dict(available=False,score=None),he_execution=False)
    resources.recheck(scope,loaded)
    if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trong lúc chấm.','Chạy lại theo quyền hiện hành.')
    return result
