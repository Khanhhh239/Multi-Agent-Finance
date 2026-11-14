"""Enterprise-only execution of the retained 35-rule source profile.

This is a separately versioned native source bundle, not an extension of the
canonical snapshot 1.1.0 or a plaintext fallback for the encrypted Portal.
Coverage claims describe the supplied export, never prove external completeness.
"""
from copy import deepcopy
import math

from finance_input import AccessScope
from .import_files import canonical,digest,fail
from .rules import RULE_NAMES,DEFAULT_CONFIG,INPUT_TABLES,OPTIONAL_INPUT_TABLES,score_rules
from .exception_validation import validated_tables,_temporal
from .authority_policy import ApprovalAuthority
from .benford import monthly_diagnostics

VERSION='native-rule-source/1.0.0'
TABLES=tuple(dict.fromkeys((*INPUT_TABLES,*OPTIONAL_INPUT_TABLES)))
HISTORY_RULES=set('A1 A2 A3 A4 A5 B3 B6 D1 D2 D3 D4 D5 D6 P1 T1 T2'.split())
PAYMENT=('transactions','employees','vendors','payment_requests','procurement_links','transaction_documents','supplier_payment_agreements')
REQUIRED={
 'A1':PAYMENT,'A2':PAYMENT,'A3':(*PAYMENT,'entity_links'),
 'A4':(*PAYMENT,'recurring_payments'),'A5':('transactions','employees','journal_documents','journal_lines','recurring_payments'),
 'A6':('transactions','employees','transaction_documents'),
 'B1':('transactions','vendors','employees'),'B2':('transactions','vendors','employees','entity_links'),
 'B3':('transactions','vendors','employees','procurement_links','transaction_documents'),
 'B4':('transactions','vendors','vendor_status_history','tax_risk_history'),
 'B5':('transactions','vendors'),'B6':('transactions','vendors','vendor_payment_schedules'),
 'B7':('transactions','vendors','employees','bank_account_changes'),
 'C1':('transactions','employees','companies','calendar','operating_schedules'),
 'C2':('transactions','employees','approval_authorities','approval_authority_coverage'),
 'C3':('transactions','employees','approval_authorities','approval_authority_coverage'),
 'C4':('transactions','employees','leave_periods','system_actions','leave_activity_authorizations'),
 **{r:('transactions','employees') for r in ('D1','D2','D3','D4','D5','D6')},
 'E1':('transactions','employees','attendance','payroll_entitlements'),
 'E2':('transactions','employees','employment_events','payroll_settlements'),
 'E3':('transactions','vendors'),'E4':('transactions','vendors'),
 'F1':('transactions','employees','journal_audit_log','closing_periods','materiality_policies'),
 'F2':('transactions','employees','workflow_policies','override_events'),
 'F3':('transactions','employees','document_series','document_register','document_cancellations'),
 'F4':('transactions','employees','customers','receivable_invoices','receipt_allocations','receipt_coverage','receivable_explanations'),
 'P1':('transactions','vendors','transaction_documents'),'P2':('transactions','employees','transaction_documents'),
 'T1':('transactions','employees','advances','advance_events'),
 'T2':('transactions','employees','advances','advance_events','transaction_documents'),
}
assert set(REQUIRED)==set(RULE_NAMES)
CORE_FIELDS={
 'companies':('company_id','saturday_operations','recorded_at','accounting_framework'),
 'employees':('company_id','employee_id','recorded_at','full_name','role','approval_limit_vnd','self_approval_limit_vnd','bank_account','phone','address','contract_on_file'),
 'vendors':('company_id','vendor_id','recorded_at','name','registered_at','onboarded_at','bank_account','phone','address','related_party_disclosed_at'),
 'customers':('company_id','customer_id','recorded_at','name'),
 'calendar':('company_id','date','is_holiday'),
 'transactions':('company_id','transaction_id','posted_at','created_at','approved_at','amount_vnd','txn_type','currency','vendor_id','employee_id','customer_id','creator_id','approver_id','approval_limit_vnd','payment_channel','is_financial_entry','recipient_account','invoice_number','invoice_issued_at','invoice_gross_vnd','support_doc_count','goods_receipt_verified','payroll_period','advance_id','debit_account','credit_account'),
}
FORBIDDEN={'labels','splits','label','risk_label','fraud_type','fraud_family','is_fraud','expected','expected_signal','expected_outcome','expected_score','features'}


def _scope(bundle,scope):
    if not isinstance(scope,AccessScope) or len(scope.company_ids)!=1 or 'data.import' not in scope.permissions or not scope.actor_id:
        fail(403,'ACCESS_DENIED','Không có quyền kiểm tra nguồn của một doanh nghiệp.','Dùng scope được backend xác thực.')
    if not isinstance(bundle,dict) or bundle.get('tenant_id')!=scope.tenant_id or bundle.get('company_id')!=next(iter(scope.company_ids)):
        fail(403,'ACCESS_DENIED','Gói nguồn ngoài phạm vi doanh nghiệp.','Chọn đúng tenant và doanh nghiệp.')
    for records in bundle.get('tables',{}).values() if isinstance(bundle.get('tables'),dict) else ():
        if isinstance(records,list) and any(not isinstance(r,dict) or r.get('company_id')!=bundle['company_id'] for r in records):
            fail(403,'ACCESS_DENIED','Nguồn có bản ghi ngoài phạm vi được cấp.','Tách gói nguồn theo doanh nghiệp.')


def validate_bundle(bundle,scope):
    _scope(bundle,scope);errors=[]
    def issue(path,message,action='Sửa bản nguồn, xuất lại manifest rồi kiểm tra lại.'):
        errors.append(dict(path=path,message=message,action=action))
    fields={'version','tenant_id','company_id','as_of','source_id','is_simulated','tables','coverage'}
    if set(bundle)!=fields or bundle.get('version')!=VERSION:
        issue('$','Gói nguồn cần đúng hợp đồng native-rule-source/1.0.0.');return dict(status='rejected',errors=errors)
    try:
        if len(canonical(bundle))>64*1024*1024:issue('$','Gói nguồn tối đa 64 MB trong bản kiểm chứng local.')
    except (ValueError,TypeError,RecursionError):
        issue('$','Gói nguồn phải là JSON hữu hạn, không có NaN/vô cực hoặc vòng lặp.');return dict(status='rejected',errors=errors)
    try:_temporal(bundle['as_of'],'timestamp')
    except (ValueError,TypeError):issue('as_of','Dùng ISO giây và múi giờ +07:00.');return dict(status='rejected',errors=errors)
    if type(bundle['is_simulated']) is not bool or not isinstance(bundle['source_id'],str) or not 1<=len(bundle['source_id'])<=128:issue('source_id','Cần định danh nguồn và cờ mô phỏng rõ ràng.')
    tables=bundle['tables'];coverage=bundle['coverage']
    if not isinstance(tables,dict) or not isinstance(coverage,dict):
        issue('tables','Cần các bảng và manifest nguồn.');return dict(status='rejected',errors=errors)
    def truth_keys(value,path):
        if isinstance(value,dict):
            for key,child in value.items():
                if key in FORBIDDEN:issue(path+'.'+key,'Nhãn/feature/kết quả kỳ vọng không thuộc nguồn tính luật.')
                else:truth_keys(child,path+'.'+key)
        elif isinstance(value,list):
            for i,child in enumerate(value):truth_keys(child,path+f'[{i+1}]')
    truth_keys(tables,'tables')
    if set(tables)-set(TABLES) or set(coverage)-set(TABLES):issue('tables','Có bảng ngoài allowlist; nhãn/feature/kết quả kỳ vọng phải để ngoài gói nguồn.')
    if sum(len(r) for r in tables.values() if isinstance(r,list))>30000:issue('tables','Tối đa 30.000 bản ghi nguồn trong bản kiểm chứng này.')
    identities={}
    for name,records in tables.items():
        if name not in TABLES:continue
        if not isinstance(records,list):issue(name,'Bảng phải là một danh sách bản ghi.');continue
        claim=coverage.get(name)
        if claim is not None:
            wanted={'status','observed_at','covered_from','covered_through','history_basis','record_count','records_sha256'}
            if not isinstance(claim,dict) or set(claim)!=wanted:issue('coverage.'+name,'Manifest thiếu trường hoặc thừa trường.');continue
            if claim['status'] not in ('complete','partial','unknown') or claim['history_basis'] not in ('since_inception','bounded_period','unknown'):issue('coverage.'+name,'Trạng thái/phạm vi lịch sử không hợp lệ.')
            valid_times=True
            for field in ('observed_at','covered_from','covered_through'):
                try:_temporal(claim[field],'timestamp')
                except (ValueError,TypeError):valid_times=False;issue('coverage.'+name+'.'+field,'Mốc nguồn cần ISO giây +07:00.')
            if valid_times and (claim['observed_at']>bundle['as_of'] or claim['covered_through']!=bundle['as_of'] or claim['covered_from']>claim['covered_through']):
                issue('coverage.'+name,'Khai báo phạm vi phải kết thúc tại as_of và đã được biết tại as_of.')
            if type(claim['record_count']) is not int or claim['record_count']!=len(records) or claim['records_sha256']!=digest(canonical(records)):
                issue('coverage.'+name,'Số dòng/checksum không khớp tệp hiện tại.','Không dùng manifest kiểm tra cũ cho nguồn đã sửa.')
        seen={}
        for i,row in enumerate(records):
            path=f'{name}[{i+1}]'
            if not isinstance(row,dict):issue(path,'Dòng phải là bản ghi.');continue
            if FORBIDDEN & set(row):issue(path,'Bản ghi chứa nhãn, feature hoặc kết quả kỳ vọng; không nhận vào tính luật.')
            required=(*CORE_FIELDS.get(name,()),'observed_at')
            for f in required:
                if f not in row:issue(path+'.'+f,'Thiếu trường nguồn bắt buộc.')
            try:_temporal(row.get('observed_at'),'timestamp')
            except (ValueError,TypeError):issue(path+'.observed_at','Thiếu thời điểm nguồn thực sự được biết.');continue
            for f,v in row.items():
                if f.endswith('_at') and v and isinstance(v,str) and len(v)>10:
                    try:_temporal(v,'timestamp')
                    except (ValueError,TypeError):issue(path+'.'+f,'Timestamp phải có giây và +07:00.')
                if f.endswith('_vnd') and v not in ('',None) and (type(v) is not int or abs(v)>999999999999999999):issue(path+'.'+f,'Tiền VND phải là số nguyên, tối đa 18 chữ số; không lấy trị tuyệt đối hoặc điền 0.')
                if isinstance(v,float) and not math.isfinite(v):issue(path+'.'+f,'Không nhận NaN hoặc vô cực.')
            if 'recorded_at' in row and row['recorded_at']!=row['observed_at']:issue(path+'.recorded_at','Profile native cần recorded_at khớp observed_at; không tự dời lịch sử master.')
            if name in ('transactions','journal_documents','journal_lines') and isinstance(row.get('posted_at'),str) and row['posted_at']<row['observed_at']:
                issue(path+'.observed_at','Nguồn ghi nhận sau ngày ghi sổ cần adapter bitemporal riêng; bản native này không được dùng nó để sửa quá khứ.')
            id_field={'transactions':'transaction_id','companies':'company_id','employees':'employee_id','vendors':'vendor_id','customers':'customer_id'}.get(name)
            if id_field and id_field in row:
                if not isinstance(row[id_field],str) or not row[id_field].strip():issue(path+'.'+id_field,'Mã nguồn phải là chuỗi không rỗng.');continue
                # Transactions have a single identity in this native profile;
                # the legacy engine does not resolve transaction revisions.
                revision=row.get('recorded_at','') if name!='transactions' else ''
                if not isinstance(revision,str):issue(path+'.recorded_at','Mốc phiên bản nguồn phải là chuỗi thời gian.');continue
                ident=(row[id_field],revision)
                if ident in seen:issue(path+'.'+id_field,'Trùng mã và mốc phiên bản nguồn.')
                seen[ident]=True
        identity_name={'employees':'employee_id','vendors':'vendor_id','customers':'customer_id','advances':'advance_id'}.get(name,'')
        identities[name]={r[identity_name] for r in records if isinstance(r,dict) and isinstance(r.get(identity_name),str)}
    transaction_rows=tables.get('transactions',[])
    for i,row in enumerate(transaction_rows if isinstance(transaction_rows,list) else []):
        if not isinstance(row,dict):continue
        for field,table in [('creator_id','employees'),('approver_id','employees'),('employee_id','employees'),('vendor_id','vendors'),('customer_id','customers'),('advance_id','advances')]:
            if field in row and row[field] is not None and not isinstance(row[field],str):
                issue(f'transactions[{i+1}].{field}','Mã tham chiếu phải là chuỗi.');continue
            if row.get(field) and table in tables and row[field] not in identities.get(table,set()):issue(f'transactions[{i+1}].{field}','Không tìm thấy mã nguồn trong cùng doanh nghiệp.')
        if row.get('txn_type')=='payroll' and (not row.get('employee_id') or not row.get('payroll_period')):
            issue(f'transactions[{i+1}].payroll_period','Khoản lương cần nhân viên và kỳ hưởng lương rõ ràng.')
        for field,table,identifier,at in [('creator_id','employees','employee_id',row.get('created_at')),('approver_id','employees','employee_id',row.get('approved_at')),('vendor_id','vendors','vendor_id',row.get('posted_at'))]:
            if row.get(field) and isinstance(at,str) and not any(r.get(identifier)==row[field] and isinstance(r.get('recorded_at'),str) and r['recorded_at']<=at for r in tables.get(table,[]) if isinstance(r,dict)):
                issue(f'transactions[{i+1}].{field}','Bản ghi tham chiếu chưa được biết tại thời điểm thao tác; cần lịch sử nguồn phù hợp.')
    if not errors:
        try:
            normalized=validated_tables(tables)
            ApprovalAuthority(normalized)
        except (ValueError,KeyError,TypeError) as error:issue('tables',str(error))
    return dict(status='rejected' if errors else 'accepted',errors=errors)


def _gaps(bundle,rule):
    gaps=[]
    for name in REQUIRED[rule]:
        claim=bundle['coverage'].get(name)
        if name not in bundle['tables']:gaps.append(dict(table=name,reason='source_not_supplied'))
        elif not claim:gaps.append(dict(table=name,reason='source_coverage_missing'))
        elif claim['status']!='complete':gaps.append(dict(table=name,reason='source_coverage_incomplete'))
        elif rule in HISTORY_RULES and name=='transactions' and claim['history_basis']!='since_inception':gaps.append(dict(table=name,reason='history_before_window_unknown'))
    for row in bundle['tables'].get('transactions',[]):
        if row.get('posted_at','')>bundle['as_of']:continue
        if rule in ('P1','A6') and row.get('txn_type')=='vendor_payment' and not row.get('invoice_gross_vnd'):
            gaps.append(dict(table='transactions',record_id=row['transaction_id'],reason='invoice_value_unavailable'))
        if rule in ('A1','A2','A3','B1') and row.get('txn_type')=='vendor_payment' and row.get('recipient_account') and not row.get('recipient_bank_code'):
            gaps.append(dict(table='transactions',record_id=row['transaction_id'],reason='recipient_bank_identity_incomplete'))
    return gaps


def evaluate_bundle(bundle,scope):
    checked=validate_bundle(bundle,scope)
    if checked['status']!='accepted':fail(422,'NATIVE_RULE_SOURCE_INVALID',json_message(checked['errors']),'Sửa dòng/trường được nêu rồi xuất lại nguồn và manifest.')
    tables={name:[deepcopy(r) for r in bundle['tables'].get(name,[]) if r['observed_at']<=bundle['as_of'] and (name!='transactions' or r['posted_at']<=bundle['as_of'])] for name in TABLES}
    if not tables['companies'] or not tables['employees'] or not tables['transactions']:
        fail(422,'NATIVE_RULE_CORE_MISSING','Cần doanh nghiệp, nhân viên và giao dịch nhìn thấy tại as_of.','Bổ sung nguồn lõi; không tạo người lập hoặc doanh nghiệp giả.')
    # Empty optional sources are only an engine transport detail. Every affected
    # rule is explicitly unavailable below, and no aggregate risk score is exposed.
    reference=score_rules(tables,config=deepcopy(DEFAULT_CONFIG))
    diagnostics=[r for r in monthly_diagnostics(tables,'phase4') if r['cutoff_at']<=bundle['as_of']]
    outputs=[]
    for rule,name in RULE_NAMES.items():
        gaps=_gaps(bundle,rule);hits=[dict(deepcopy(h),rule_id=rule,source_rule_id=h['rule_id']) for h in reference['hits'] if h['rule_id']==rule or rule in h.get('aliases',[])]
        findings=[deepcopy(f) for f in reference['evidence_findings'] if f['rule_id']==rule]
        statistical=[deepcopy(d) for d in diagnostics if d['rule_id']==rule]
        groups=[deepcopy(e) for e in reference['batch_events'] if e['rule_id']==rule]
        scope_kind='aggregate_diagnostic' if rule.startswith('D') else 'source_diagnostic' if rule=='F4' else 'transaction_and_source' if rule=='F3' else 'master_quality' if rule in ('B5','E3','E4') else 'transaction'
        information=[h for h in hits if h.get('evidence',{}).get('evidence_status') in ('information_gap','unconfirmed_proxy')]
        usable=[h for h in hits if h not in information]
        signal=any(not h.get('suppressed_reason') for h in usable) or any(f.get('signal') is True for f in findings) or any(e.get('signal') is True for e in groups)
        available=not gaps
        if rule.startswith('D'):
            good=[d for d in statistical if d['status']=='evaluated'];available=available and bool(good);signal=any(d.get('signal') is True for d in good)
            if not good:gaps.append(dict(table='transactions',reason='statistical_sample_not_evaluable',details=[d.get('skip_reasons') for d in statistical]))
        if rule=='F4' and not any(f['status']=='evaluated' for f in findings):available=False;gaps.append(dict(table='receivable_invoices',reason='no_evaluable_receivable_scope'))
        if information and not usable:available=False;gaps.append(dict(table='evidence',reason='unconfirmed_or_missing_business_evidence'))
        outputs.append(dict(rule_id=rule,name=name,scope=scope_kind,available=available,status='evaluated_hit' if available and signal else 'evaluated_no_hit' if available else 'unavailable',matched=bool(signal) if available else None,
            evaluated_subscopes=sum(d['status']=='evaluated' for d in statistical),unavailable_subscopes=sum(d['status']!='evaluated' for d in statistical),
            score=None,reason=None if available else 'source_or_scope_unavailable',gaps=gaps,hits=usable if available else [],groups=groups if available else [],findings=findings,statistics=statistical))
    return dict(version='native-rule-node-result/1.0.0',execution='plaintext_at_enterprise_node_only',he_execution=False,canonical_snapshot_adapter=False,tenant_id=scope.tenant_id,company_id=bundle['company_id'],as_of=bundle['as_of'],
        source_sha256=digest(canonical(bundle)),profile_config_sha256=digest(canonical(DEFAULT_CONFIG)),status='technical_only',is_simulated=bundle['is_simulated'],
        row_count=len(bundle['tables'].get('transactions',[])),processed_row_count=len(tables['transactions']),record_ids=[r['transaction_id'] for r in bundle['tables'].get('transactions',[])],
        unavailable_transactions=[dict(record_id=r['transaction_id'],reason='not_known_or_posted_after_as_of') for r in bundle['tables'].get('transactions',[]) if r['observed_at']>bundle['as_of'] or r['posted_at']>bundle['as_of']],rules=outputs,
        native_reference_sha256=digest(canonical(reference)),aggregate_available=False,aggregate_score=None,model_fit_performed=False,accuracy=None,
        limitations=['Source completeness is an export declaration, not external verification.','Separate native profile; does not activate missing rules in canonical snapshot/HE Portal.','Source/aggregate/master findings are not counts of fraud cases.','Late-posted native transaction/ledger rows require a separate bitemporal adapter; no retroactive zero fallback.'])


def json_message(errors):
    return '\n'.join(e['path']+': '+e['message'] for e in errors[:20])
