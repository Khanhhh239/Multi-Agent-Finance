"""Bound run/case adapter over the existing document and task lifecycle."""
import base64
import re
from .import_files import fail,digest
from .pipeline_release_store import ensure
from .remediation_store import _require_operator_scope,_require_verifier_scope,ROLE_LABELS_VI,compute_next_step_vi

DOC_TYPES={
 'invoice':'Hóa đơn', 'payment_allocation':'Bảng phân bổ thanh toán',
 'bank_transfer_receipt':'Ủy nhiệm chi / sao kê', 'purchase_order':'Đơn mua hàng',
 'contract':'Hợp đồng', 'payroll':'Bảng lương', 'attendance':'Bảng công',
 'employment_decision':'Quyết định nhân sự', 'approval_record':'Hồ sơ phê duyệt',
 'journal_record':'Chứng từ kế toán', 'advance_record':'Hồ sơ tạm ứng',
 'counterparty_reconciliation':'Đối chiếu công nợ', 'other':'Tài liệu khác'}


def binding_for(work,scope,run_id,review_id,recheck=None):
    observed,packet=work.packet(scope,run_id,recheck)
    item=next((c for c in packet['cases'] if c['review_id']==review_id),None)
    ensure(item is not None,'PIPELINE_REVIEW_NOT_FOUND','Phiếu không thuộc lượt chạy này.',404)
    ensure(work.remediation is not None,'PIPELINE_TASKS_UNAVAILABLE','Chưa cấu hình kho hồ sơ/công việc.',503)
    binding={k:packet[k] for k in ('snapshot_id','run_id','bundle_id','pin_id','as_of')}
    binding.update(review_id=review_id,case_id=item['case_id'])
    return binding,item


def _completion(task,documents):
    reasons=[];sub=task.get('submission');verification=task.get('verification')
    if task['status'] not in ('open','in_progress','waiting_external'):reasons.append('Công việc đã đóng; cần mở lại trước khi gửi kết quả mới.')
    if not sub:reasons.append('Người phụ trách chưa gửi kết quả thực hiện.')
    elif verification and verification['decision'] in ('request_rework','reopen') and sub['submitted_at']<=verification['confirmed_at']:
        reasons.append('Cần gửi kết quả mới sau khi được yêu cầu làm lại hoặc mở lại.')
    if task['require_evidence']:
        verified=[d for d in documents if d['verification_status']=='present']
        types={d['document_type'] for d in verified}
        required=task.get('required_document_types') or []
        missing=[DOC_TYPES.get(t,t) for t in required if t not in types]
        if missing:reasons.append('Thiếu chứng từ đã xác minh: '+', '.join(missing)+'.')
        elif not required and not verified:reasons.append('Chưa có chứng từ được xác minh trong hồ sơ của vụ này.')
    return reasons


def read(work,scope,run_id,review_id,recheck=None):
    binding,item=binding_for(work,scope,run_id,review_id,recheck)
    rem=work.remediation.get_case_remediation(scope,review_id,recheck=recheck)
    tasks=[t for t in rem['tasks'] if t.get('source_binding')==binding]
    can_edit='data.import' in scope.permissions;can_verify='evidence.verify' in scope.permissions
    for task in tasks:
        closed=task['status'] in ('completed','cancelled');reasons=_completion(task,rem['documents'])
        task['actions']=dict(can_assign=can_edit and not closed,can_submit=can_edit and not closed,
            can_verify=can_verify,can_complete=can_verify and not reasons,
            can_rework=can_verify and not closed,can_reopen=can_verify and closed,completion_blockers=reasons)
    types=dict(DOC_TYPES)
    for task in tasks:
        for name in task.get('required_document_types',[]):types.setdefault(name,name)
    refs=[]
    for doc in rem['documents']:
        for version in doc['versions']:
            refs.append(dict(evidence_id=doc['document_id']+':v'+str(version['version']),document_id=doc['document_id'],
                             version=version['version'],name=version['filename'],sha256=version['sha256'],
                             verification_status=version['verification_status']))
    return dict(version='bundle-case-remediation/1.0.0',**binding,documents=rem['documents'],tasks=tasks,
        checklist=rem['checklist'],next_step=compute_next_step_vi(rem['checklist'],tasks),
        assignees=[dict(key=k,label=v) for k,v in ROLE_LABELS_VI.items()],document_types=[dict(key=k,label=v) for k,v in types.items()],
        permissions=dict(can_upload=can_edit,can_assign=can_edit,can_submit=can_edit,can_verify=can_verify),
        evidence_refs=refs,identity_verified=False,
        separation_note='Hoàn tất công việc không tự đóng vụ, xác minh gian lận hoặc tạo nhãn ML; tài liệu mới không sửa snapshot cũ.')


def _target(work,scope,binding,kind,identity,recheck):
    view=work.remediation.get_case_remediation(scope,binding['review_id'],recheck=recheck)
    rows=view['tasks'] if kind=='task' else view['documents']
    item=next((r for r in rows if r[kind+'_id']==identity),None)
    ensure(item is not None and (kind!='task' or item.get('source_binding')==binding),
           'PIPELINE_REMEDIATION_NOT_FOUND','Hồ sơ hoặc công việc không thuộc vụ/lần phân tích này.',404)
    return item


def command(work,scope,run_id,review_id,body,recheck=None):
    binding,_=binding_for(work,scope,run_id,review_id,recheck)
    ensure(isinstance(body,dict) and set(body)=={'action','request_id','payload'} and isinstance(body['action'],str)
           and isinstance(body['request_id'],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}',body['request_id'])
           and isinstance(body['payload'],dict),'PIPELINE_REMEDIATION_FIELDS','Yêu cầu xử lý hồ sơ không hợp lệ.',400)
    action=body['action'];p=body['payload'];store=work.remediation
    fields={
      'upload_document':({'document_type','filename','content_base64','note'},{'document_id'}),
      'import_attachment':({'attachment_id','document_type','note'},set()),
      'verify_document':({'document_id','version','decision','note'},set()),
      'assign_task':({'task_id','expected_revision','assignee_key','due_at','reason'},set()),
      'submit_task':({'task_id','expected_revision','result_summary','document_ids','waiting_external'},set()),
      'decide_task':({'task_id','expected_revision','decision','note'},set())}
    ensure(action in fields,'PIPELINE_REMEDIATION_ACTION','Thao tác xử lý chưa được hỗ trợ.',400)
    required,optional=fields[action]
    ensure(required<=set(p) and not set(p)-required-optional,'PIPELINE_REMEDIATION_FIELDS','Thiếu trường hoặc có nguồn/quyền tự khai.',400)
    if action in ('verify_document','decide_task'):_require_verifier_scope(scope,recheck)
    else:_require_operator_scope(scope,recheck)
    for key in ('document_id','task_id','attachment_id','document_type','filename','note','reason','result_summary','assignee_key','decision','due_at'):
        if key in p:ensure(isinstance(p[key],str) and len(p[key])<=4000,'PIPELINE_REMEDIATION_FIELDS','Nội dung hoặc mã hồ sơ không hợp lệ.',400)
    if 'expected_revision' in p:ensure(type(p['expected_revision']) is int and p['expected_revision']>=1,'PIPELINE_REMEDIATION_FIELDS','Cần phiên bản công việc đang xem.',400)
    if 'version' in p:ensure(type(p['version']) is int and p['version']>=1,'PIPELINE_REMEDIATION_FIELDS','Cần phiên bản chứng từ đang xem.',400)
    if 'waiting_external' in p:ensure(type(p['waiting_external']) is bool,'PIPELINE_REMEDIATION_FIELDS','Trạng thái chờ bổ sung không hợp lệ.',400)
    if 'document_ids' in p:ensure(isinstance(p['document_ids'],list) and len(p['document_ids'])<=100 and all(isinstance(i,str) for i in p['document_ids']) and len(set(p['document_ids']))==len(p['document_ids']),'PIPELINE_REMEDIATION_FIELDS','Danh sách chứng từ không hợp lệ.',400)

    def invoke():
        if 'task_id' in p:_target(work,scope,binding,'task',p['task_id'],recheck)
        if 'document_id' in p:_target(work,scope,binding,'document',p['document_id'],recheck)
        if action in ('upload_document','import_attachment'):
            if action=='import_attachment':
                original=work.reviews.attachment(scope,review_id,p['attachment_id'])
                content=original['content'];name=original['name']
            else:content=p['content_base64'];name=p['filename']
            ensure(0<len(name)<=160 and not any(c in name for c in '/\\\r\n\x00'),'PIPELINE_DOCUMENT_NAME','Tên tệp chứng từ không hợp lệ.',422)
            ensure(isinstance(content,str) and len(content)<3*1024*1024,'PIPELINE_DOCUMENT_CONTENT','Tệp chứng từ tối đa 2 MB.',413)
            try:raw=base64.b64decode(content,validate=True)
            except (ValueError,TypeError):fail(422,'PIPELINE_DOCUMENT_CONTENT','Không đọc được tệp chứng từ.','Chọn lại PDF/PNG/JPEG.')
            mime='application/pdf' if raw.startswith(b'%PDF-') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
            ensure(mime is not None,'PIPELINE_DOCUMENT_TYPE','Chỉ nhận PDF, PNG hoặc JPEG.',415)
            ensure(0<len(raw)<=2*1024*1024,'PIPELINE_DOCUMENT_CONTENT','Tệp chứng từ tối đa 2 MB.',413)
            ensure(p['document_type'] in {r['key'] for r in read(work,scope,run_id,review_id,recheck)['document_types']},'PIPELINE_DOCUMENT_TYPE','Chọn loại chứng từ trong danh sách.',422)
            if 'document_id' in p:
                current=_target(work,scope,binding,'document',p['document_id'],recheck)
                ensure(current['document_type']==p['document_type'],'PIPELINE_DOCUMENT_TYPE','Phiên bản mới phải giữ đúng loại chứng từ.',422)
            else:
                existing=store.get_case_remediation(scope,review_id,recheck=recheck)['documents']
                duplicate=next((d for d in existing if d['document_type']==p['document_type'] and d['versions'][0]['sha256']==digest(raw)),None)
                if duplicate is not None:return dict(document=duplicate,deduplicated_existing=True)
            value=store.upload_document(scope,case_id=review_id,obligation_id=review_id,document_type=p['document_type'],
                filename=name,mime=mime,content=raw,note=p['note'],document_id=p.get('document_id'),case_as_of=binding['as_of'],recheck=recheck)
            return value
        if action=='verify_document':
            return dict(document=store.verify_document(scope,document_id=p['document_id'],version=p['version'],decision=p['decision'],verification_note=p['note'],recheck=recheck))
        if action=='assign_task':
            ensure(p['assignee_key'] in ROLE_LABELS_VI,'PIPELINE_TASK_ASSIGNEE','Chọn bộ phận phụ trách trong danh sách.',422)
            return dict(task=store.assign_task(scope,task_id=p['task_id'],expected_revision=p['expected_revision'],assignee_kind='department_role',assignee_key=p['assignee_key'],due_at=p['due_at'],reason=p['reason'],recheck=recheck))
        if action=='submit_task':
            for identity in p['document_ids']:_target(work,scope,binding,'document',identity,recheck)
            return dict(task=store.submit_task(scope,task_id=p['task_id'],expected_revision=p['expected_revision'],result_summary=p['result_summary'],document_ids=p['document_ids'],waiting_external=p['waiting_external'],recheck=recheck))
        return dict(task=store.decide_task(scope,task_id=p['task_id'],expected_revision=p['expected_revision'],decision=p['decision'],note=p['note'],recheck=recheck))
    return store.bound_command(scope,operation='bundle-'+action,request_id=body['request_id'],binding=binding,payload=p,invoke=invoke,recheck=recheck)


def content(work,scope,run_id,review_id,document_id,version,recheck=None):
    binding,_=binding_for(work,scope,run_id,review_id,recheck)
    _target(work,scope,binding,'document',document_id,recheck)
    value=work.remediation.get_document(scope,document_id,version=version,include_bytes=True,recheck=recheck)
    return dict(name=value['filename'],mime=value['mime'],version=value['version'],sha256=value['sha256'],content=base64.b64encode(value['content']).decode())
