"""Business review packets bound to immutable run/bundle/source; no model labels."""
from copy import deepcopy
import csv
import io
import threading
import re
from finance_input.json_io import loads
from .import_files import canonical,digest
from .pipeline_release_store import ensure
from .review_store import ReviewStore
from .review_api import summarize
from .snapshot_features import utc

PACKET_VERSION='bundle-review-packet/1.0.0'
FAMILIES={
 'payment_invoice':('Khoản thanh toán có đúng nghĩa vụ hóa đơn không?','Đối chiếu hóa đơn, phân bổ và các khoản thanh toán trước đó.'),
 'split_obligation':('Các khoản chi có cùng nghĩa vụ và được phê duyệt đúng không?','Đối chiếu yêu cầu chi, đơn mua hàng, hợp đồng và các lần thanh toán.'),
 'payroll_entitlement':('Khoản lương có đúng người và đúng kỳ hưởng không?','Đối chiếu bảng lương, bảng công, nghỉ việc/tái tuyển dụng và chứng từ chuyển tiền.'),
 'approval_controls':('Khoản chi có được phê duyệt đúng thẩm quyền và thời điểm không?','Đối chiếu người lập, người duyệt, nhật ký và chứng từ phê duyệt.'),
 'vendor_bank_identity':('Đối tượng và tài khoản nhận tiền có đúng hồ sơ đã xác minh không?','Đối chiếu hồ sơ nhà cung cấp, người thụ hưởng và xác nhận tài khoản nhận tiền.'),
 'advance_lifecycle':('Khoản tạm ứng đã đến hạn và đủ hồ sơ quyết toán chưa?','Đối chiếu đề nghị tạm ứng, gia hạn, hoàn ứng và chứng từ quyết toán.'),
 'ml_anomaly':('Điểm khác thường của khoản này có lý do nghiệp vụ hợp lệ không?','Đối chiếu nội dung chi, đối tượng, kỳ và chứng từ nguồn; chưa đủ thì yêu cầu bổ sung.')}
FIELDS={
 'transactions':('transaction_id','revision','posted_at','observed_at','txn_type','amount_vnd','currency','vendor_id','employee_id','customer_id','creator_id','approver_id','recipient_account','invoice_number','invoice_issued_at','invoice_gross_vnd','payroll_period','business_purpose','advance_id','debit_account','credit_account'),
 'transaction_documents':('document_id','transaction_id','vendor_id','document_type','invoice_number','invoice_gross_vnd','issued_at','recorded_at','observed_at','status','revision'),
 'invoices':('invoice_id','record_id','revision','number','vendor_id','amount_vnd','gross_vnd','effective_at','observed_at','issued_at','status'),
 'payment_allocations':('allocation_id','record_id','revision','transaction_id','invoice_id','amount_vnd','effective_at','observed_at'),
 'vendors':('vendor_id','revision','name','bank_account','bank_code','recorded_at','observed_at'),
 'employees':('employee_id','revision','full_name','recorded_at','observed_at'),
 'approvals':('record_id','revision','transaction_ref','employee_ref','decision','effective_at','observed_at')}
IDS={'transactions':'transaction_id','transaction_documents':'document_id','invoices':'invoice_id','payment_allocations':'allocation_id','vendors':'vendor_id','employees':'employee_id','approvals':'record_id'}
MONEY=('obligation_gross_vnd','prior_evidence_allocated_vnd','candidate_amount_vnd','candidate_allocated_vnd','net_settled_vnd','related_amount_vnd','discrepancy_amount_vnd','confirmed_loss_vnd','recovered_amount_vnd')


class CompanyReviewStore(ReviewStore):
    """Separate DB/key namespace; membership grants shared company review visibility.
    Review revisions still record the actual current actor. Old personal HE reviews
    are never migrated or re-keyed into this store.
    """
    @staticmethod
    def owner(scope):
        ReviewStore.owner(scope)  # existing company-count and permission guard
        return digest(canonical(['bundle-company-review/1.0.0',scope.tenant_id,next(iter(scope.company_ids))]))


def _known(record,cutoff):
    clocks=[record.get(k) for k in ('observed_at','recorded_at','posted_at','effective_at') if record.get(k)]
    return bool(clocks) and all(utc(t)<=utc(cutoff) for t in clocks)


def build_packet(scope,pin,result,manifest,data):
    ensure(pin['bundle_id']==result['pipeline']['bundle_id'] and result['snapshot']['snapshot_id']==manifest['snapshot_id'],
           'PIPELINE_REVIEW_BINDING','Kết quả không khớp bundle hoặc snapshot của phiếu.')
    pipe=result['pipeline'];admitted={d['case_id']:d for d in pipe['queue']['decisions'] if d['decision'] in ('selected','mandatory_route')}
    tables=data['source']['tables'];as_of=result['as_of'];simulated=bool(data['source']['is_simulated']);cases=[]
    cutoff_by_id={r['transaction_id']:min(utc(r['event_at']),utc(as_of)) for r in result['rows']}
    for case in pipe['cases']:
        if case['case_id'] not in admitted:continue
        packet_case_id=case['case_id'];rid='rvw_'+digest(canonical([scope.tenant_id,next(iter(scope.company_ids)),pin['pin_id'],packet_case_id]))
        refs={};gaps=[];cand=set(case['candidate_ids']);prior=set(case['evidence_tx_ids'])-cand
        def add(table,record,role,cutoff=as_of):
            if table not in FIELDS or not _known(record,cutoff):return False
            eid='pev_'+digest(canonical([manifest['checksum'],table,record]))
            visible={k:deepcopy(record[k]) for k in FIELDS[table] if k in record}
            # Keep signed VND exactly, including integers outside JS safe range.
            visible={k:str(v) if k.endswith('_vnd') and type(v) is int else v for k,v in visible.items()}
            if eid not in refs:refs[eid]=dict(evidence_id=eid,table=table,role=role,record=visible,source_sha256=digest(canonical(record)),
                source_kind='simulated' if simulated or record.get('is_simulated') else 'source_export',original_verified=False,
                verification='source_record_only',snapshot_id=manifest['snapshot_id'])
            return True
        txs={r['transaction_id']:r for r in tables['transactions']}
        for tid in sorted(cand|prior):
            tx=txs.get(tid)
            if tx is None or not add('transactions',tx,'candidate' if tid in cand else 'prior_payment_evidence'):
                gaps.append('Chưa có bản ghi giao dịch khả dụng trong snapshot: '+tid);continue
            # Master context must have been known by the transaction, not merely by
            # the global job cutoff. No latest-master lookup outside this snapshot.
            cutoff=cutoff_by_id.get(tid,utc(tx['posted_at']))
            for table,field in [('vendors','vendor_id'),('employees','creator_id'),('employees','approver_id'),('employees','employee_id')]:
                identity=tx.get(field)
                if not identity:continue
                candidates=[r for r in tables.get(table,[]) if r.get(IDS[table])==identity and _known(r,cutoff.isoformat())]
                if candidates:
                    latest=max(candidates,key=lambda r:utc(r.get('observed_at') or r.get('recorded_at')))
                    add(table,latest,'master_context',cutoff.isoformat())
        # Only explicit, unambiguous source refs from the frozen coalesced case.
        for ref in case['source_links']:
            table=ref['table']
            if table not in FIELDS or table=='transactions':continue
            identity=ref['record_id'];rows=[r for r in tables.get(table,[]) if
                (r.get(IDS[table])==identity or r.get('record_id')==identity or digest(canonical(r))==identity) and
                (ref.get('revision') is None or r.get('revision',1)==ref['revision']) and _known(r,as_of)]
            if len(rows)==1:add(table,rows[0],ref['role'])
            elif rows:gaps.append('Nguồn có nhiều phiên bản chưa xác định rõ: '+table+'/'+identity)
        question,next_step=FAMILIES.get(case['problem_family'],('Khoản này có căn cứ nghiệp vụ và chứng từ phù hợp không?','Đối chiếu chứng từ nguồn và ghi rõ phần cần bổ sung.'))
        why='Vụ này đã được chọn vào hàng đợi rà thử. Cần làm rõ '+question[0].lower()+question[1:]
        difference=case['financial_summary'].get('discrepancy_amount_vnd')
        if difference is not None and difference>0:
            why='Trong nguồn đã khóa có chênh lệch '+str(difference)+' VND cần đối chiếu với nghĩa vụ và các lần thanh toán; chưa phải tổn thất đã xác nhận.'
        elif not case['actionable_rule_ids']:
            why='Khoản này có thông tin khác thường so với nguồn tham chiếu đã khóa. Cần đối chiếu chứng từ để xác định lý do nghiệp vụ; chưa kết luận sai phạm.'
        finance={k:deepcopy(case['financial_summary'].get(k)) for k in MONEY}
        finance={k:str(v) if type(v) is int else v for k,v in finance.items()}
        cases.append(dict(review_id=rid,case_id=packet_case_id,question=question,why=why,next_step=next_step,
            candidate_ids=sorted(cand),evidence_transaction_ids=sorted(prior),evidence=list(refs.values()),
            source_limits=gaps+['Bản ghi nguồn không thay thế chứng từ gốc đã xác minh; thiếu tài liệu thì chọn Chưa đủ căn cứ.'],
            financial_summary=finance,source_kind='simulated' if simulated else 'source_export'))
    counts={k:sum(r.get('rule_coverage',{}).get('summary',{}).get(k,0) for r in result['rows'])
            for k in ('evaluated_hit','evaluated_no_hit','unavailable','not_applicable')}
    baseline=dict(catalogue_size=len(result.get('catalogue',[])) or (35 if 'retained_catalogue_35' in result.get('supported_checks',[]) else None),
                  row_checks=counts,limitation='Số luật trong phạm vi không đồng nghĩa tất cả đều đủ nguồn; kết quả thiếu nguồn vẫn chưa khả dụng.')
    return dict(version=PACKET_VERSION,tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),
        snapshot_id=manifest['snapshot_id'],snapshot_checksum=manifest['checksum'],data_checksum=manifest['data_checksum'],
        run_id=pin['run_id'],bundle_id=pin['bundle_id'],pin_id=pin['pin_id'],as_of=as_of,cases=cases,
        training_eligible=False,execution_location=pipe['execution_location'],he_execution=pipe['he_execution'],baseline=baseline)


class BundleWorkspace:
    def __init__(self,release,review_store=None):
        self.release=release;self._reviews=review_store;self.lock=threading.RLock();self.remediation=None

    @property
    def reviews(self):
        with self.lock:
            if self._reviews is None:self._reviews=CompanyReviewStore(self.release.store.path.with_name(self.release.store.path.stem+'-reviews.sqlite3'),self.release.store.review_key)
            return self._reviews

    def observation(self,scope,run_id,recheck=None):
        with self.release.store.tx(scope,recheck,write=False) as c:
            row=c.execute('SELECT object_id FROM pins WHERE owner=? AND run_id=?',(self.release.store.owner(scope),run_id)).fetchone()
            ensure(row is not None,'PIPELINE_RUN_NOT_FOUND','Không có lượt này trong doanh nghiệp.',404)
            for obj in c.execute("SELECT id FROM objects WHERE owner=? AND kind='observation' ORDER BY rowid DESC",(self.release.store.owner(scope),)).fetchall():
                value=self.release.store.read(c,scope,obj['id'],'observation')
                if value['pin_id']==row['object_id']:return value
        ensure(False,'PIPELINE_RUN_PENDING','Lượt đang xử lý; giữ nguyên mã yêu cầu để tiếp tục.')

    def packet(self,scope,run_id,recheck=None):
        observed=self.observation(scope,run_id,recheck)
        packet_id=observed['result'].get('pipeline',{}).get('review_packet_id')
        ensure(packet_id is not None,'PIPELINE_NO_CASE_PACKET','Lượt này chưa có packet phiếu rà; không tự tạo lại bằng cấu hình mới.')
        packet=self.release.store.get(scope,packet_id,'review_packet',recheck)
        ensure(all(packet[k]==observed[k] for k in ('run_id','snapshot_id','bundle_id','pin_id')) and utc(packet['as_of'])==utc(observed['as_of']),
               'PIPELINE_REVIEW_BINDING','Packet không khớp lần chạy đã lưu.',503)
        return observed,packet

    def case(self,scope,run_id,review_id,recheck=None):
        _,packet=self.packet(scope,run_id,recheck)
        case=next((c for c in packet['cases'] if c['review_id']==review_id),None)
        ensure(case is not None,'PIPELINE_REVIEW_NOT_FOUND','Phiếu không thuộc lượt chạy này.',404)
        return case

    def report(self,scope,run_id,recheck=None):
        observed,packet=self.packet(scope,run_id,recheck);cases=[]
        for item in packet['cases']:
            state=self.reviews.get(scope,item['review_id'])
            for a in state['attachments']:a.update(source_kind='user_attachment',known_after_analysis=True)
            tasks=self.tasks(scope,run_id,item['review_id'],recheck)['tasks'] if self.remediation is not None else []
            cases.append(dict(item,review=state,tasks=tasks))
        stats=summarize(cases);outcomes=stats['outcomes'];resolved=outcomes['confirmed_risk']+outcomes['legitimate']
        closed_wait_sec=0.0;waiting_open_count=0
        for item in cases:
            for t in item.get('tasks') or []:
                wait_start=None
                for h in t.get('history') or []:
                    at_dt=utc(h['at'])
                    if h.get('to_status')=='waiting_external' and wait_start is None:wait_start=at_dt
                    elif h.get('to_status')!='waiting_external' and wait_start is not None:
                        closed_wait_sec+=max(0.0,(at_dt-wait_start).total_seconds());wait_start=None
                if wait_start is not None:waiting_open_count+=1
        stats.update(resolved_case_count=resolved,declared_issue_fraction=outcomes['confirmed_risk']/resolved if resolved else None,
                     resolution_coverage=resolved/len(cases) if cases else None,verified_fraud_precision=None,
                     waiting_evidence_seconds=round(closed_wait_sec,3),open_waiting_evidence_tasks=waiting_open_count,
                     inconclusive_excluded_count=outcomes['inconclusive'],
                     waiting_time_basis='action_task_waiting_external_history_separate_from_review_active_seconds',
                     limitation='Phản hồi khai báo của người rà, không phải nhãn gian lận đã xác minh hoặc độ chính xác model.')
        queue=observed['result']['pipeline']['queue']
        queue_summary={k:queue['counts'].get(k) for k in ('total_cases','queued_or_reserved','backlog_waiting','already_notified')}
        for key in ('unscorable','need_evidence','below_threshold','budget_deferred'):
            queue_summary[key]=sum(d['decision']==key for d in queue['decisions'])
        source_status=[]
        for branch,label in [('rules','Đối chiếu nghiệp vụ'),('statistics','So sánh lịch sử'),('graph','Liên kết đối tượng'),('ml','Phân tích bất thường')]:
            rows=observed['result']['rows'];counts={}
            for row in rows:
                status=row.get('branches',{}).get(branch,{}).get('status','unavailable');counts[status]=counts.get(status,0)+1
            source_status.append(dict(name=label,row_count=len(rows),statuses=counts))
        if recheck is not None:ensure(recheck()==scope,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.',403)
        value=dict(version='bundle-workspace-report/1.0.0',company_id=packet['company_id'],snapshot_id=packet['snapshot_id'],
            run_id=run_id,bundle_id=packet['bundle_id'],as_of=packet['as_of'],status='completed',cases=cases,summary=stats,
            queue_summary=queue_summary,source_status=source_status,
            execution_location=packet['execution_location'],he_execution=packet['he_execution'],training_eligible=False,
            baseline=packet.get('baseline'),tasks_available=self.remediation is not None,
            task_counts={k:sum(t['status']==k for c in cases for t in c['tasks']) for k in ('open','in_progress','waiting_external','completed','cancelled')},
            identity_basis='Server-authorized company actor; Portal may use a shared workspace identity')
        value['report_sha256']=digest(canonical(value))
        return value

    def tasks(self,scope,run_id,review_id,recheck=None,body=None):
        _,packet=self.packet(scope,run_id,recheck)
        item=next((c for c in packet['cases'] if c['review_id']==review_id),None)
        ensure(item is not None,'PIPELINE_REVIEW_NOT_FOUND','Phiếu không thuộc lượt chạy này.',404)
        ensure(self.remediation is not None,'PIPELINE_TASKS_UNAVAILABLE','Chưa cấu hình kho công việc.',503)
        from .remediation_store import ROLE_LABELS_VI
        binding={k:packet[k] for k in ('snapshot_id','run_id','bundle_id','pin_id','as_of')}
        binding.update(review_id=review_id,case_id=item['case_id'])
        if body is None:
            tasks=self.remediation.get_case_remediation(scope,review_id,recheck=recheck)['tasks']
            tasks=[t for t in tasks if t.get('source_binding')==binding]
            return dict(tasks=tasks,assignees=[dict(key=k,label=v) for k,v in ROLE_LABELS_VI.items()])
        fields={'task_type','title','what_to_do','reason','assignee_key','due_at','request_id'}
        ensure(isinstance(body,dict) and set(body)==fields and all(isinstance(v,str) and 0<len(v.strip())<=4000 for v in body.values()),
               'PIPELINE_TASK_FIELDS','Cần chọn loại việc, nội dung, lý do, bộ phận phụ trách và hạn xử lý; không nhận nguồn tự khai.',400)
        ensure(re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}',body['request_id']) is not None,'PIPELINE_TASK_FIELDS','Mã yêu cầu không hợp lệ.',400)
        ensure(body['assignee_key'] in ROLE_LABELS_VI,'PIPELINE_TASK_ASSIGNEE','Chọn bộ phận phụ trách trong danh sách.',422)
        issue={'request_documents':'missing_document','reconcile_payment':'payment_discrepancy','verify_control':'process_exception','remediate_issue':'unexplained_anomaly'}
        # Prefix the idempotency key with the immutable review, isolating tabs and
        # preventing a receipt from another run being accepted as this task.
        return self.remediation.create_task(scope,case_id=review_id,obligation_id=review_id,
            task_type=body['task_type'],issue_type=issue.get(body['task_type'],'unexplained_anomaly'),
            title=body['title'],what_to_do=body['what_to_do'],reason=body['reason'],
            assignee_kind='department_role',assignee_key=body['assignee_key'],due_at=body['due_at'],
            idempotency_key='bundle-'+digest(canonical([review_id,body['request_id']])),source_binding=binding,recheck=recheck)

    def list_runs(self,scope,recheck=None):
        runs=[];complete=set()
        for row in self.release.store.list(scope,'observation',recheck):
            o=row['value'];p=o['result'].get('pipeline',{})
            if not p.get('review_packet_id'):continue
            complete.add(o['pin_id']);runs.append(dict(status='completed',**{k:o[k] for k in ('run_id','snapshot_id','bundle_id','as_of','created_at')}))
        for row in self.release.store.list(scope,'pin',recheck):
            p=row['value']
            if row['id'] in complete or p['bundle']['profile']!='snapshot_case_shadow/1.0.0':continue
            runs.append(dict(run_id=p['run_id'],snapshot_id=p['request']['snapshot_id'],bundle_id=p['bundle_id'],as_of=p['request']['as_of'],created_at=p['at'],status='pending'))
        datasets=[]
        with self.release.snapshots._transaction(scope,recheck) as c:
            ids=[r[0] for r in c.execute('SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC LIMIT 100',(scope.tenant_id,next(iter(scope.company_ids))))]
            for sid in ids:
                m,raw=self.release.snapshots._read_snapshot(c,scope,sid);d=loads(raw)
                if 'source' not in d:
                    datasets.append(dict(snapshot_id=sid,created_at=m['created_at'],as_of=None,candidate_count=len(d.get('transactions',[])),
                        source_kind='source_export',can_analyze=False,reason='Bản dữ liệu chưa có bộ nguồn đầy đủ theo hợp đồng 35 luật. Bổ sung snapshot nguồn; không chuyển sang chấm P1 thay thế.'))
                    continue
                datasets.append(dict(snapshot_id=sid,created_at=m['created_at'],as_of=d['source']['as_of'],candidate_count=len(d['candidate_transaction_ids']),
                                     source_kind='simulated' if d['source']['is_simulated'] else 'source_export',can_analyze=True))
        current=self.release.store.current(scope,'staging',recheck);can_run=False
        if current.get('bundle_id'):
            from .import_files import ImportFailure
            try:
                with self.release.store.tx(scope,recheck,write=False) as c:
                    b,_=self.release._compatible(c,scope,current['bundle_id'],recheck)
                    can_run=b['profile']=='snapshot_case_shadow/1.0.0'
            except ImportFailure as error:
                if error.status in (401,403):raise
        return dict(company_id=next(iter(scope.company_ids)),runs=runs,datasets=datasets,can_run=can_run,
                    active_bundle_id=current.get('bundle_id'),execution_location='enterprise_local_only',
                    message='Sẵn sàng chạy shadow tại doanh nghiệp.' if can_run else 'Chưa có phiên bản phân tích tương thích đã được duyệt staging. Liên hệ người quản lý.')

    def submit(self,scope,body,recheck=None):
        ensure(isinstance(body,dict) and {'run_id','snapshot_id'}<=set(body) and not set(body)-{'run_id','snapshot_id','execution_mode'},
               'PIPELINE_RUN_FIELDS','Chỉ chọn snapshot và mã yêu cầu; không nhận điểm, model hoặc policy tự khai.',400)
        ensure(all(isinstance(v,str) for v in body.values()),'PIPELINE_RUN_FIELDS','Mã nguồn hoặc chế độ chạy không hợp lệ.',400)
        manifest,data=self.release._snapshot(scope,body['snapshot_id'],recheck)
        ensure('source' in data,'PIPELINE_CASE_PROFILE_REQUIRED','Luồng này cần snapshot nguồn đầy đủ.')
        result=self.release.run(scope,body['run_id'],'staging',body['snapshot_id'],data['source']['as_of'],recheck,
                                execution_mode=body.get('execution_mode','enterprise_local_only'),require_case_profile=True)
        return self.report(scope,result['run_id'],recheck)

    def action(self,scope,run_id,review_id,action,body,recheck=None):
        item=self.case(scope,run_id,review_id,recheck);store=self.reviews
        if recheck is not None:ensure(recheck()==scope,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.',403)
        ensure(isinstance(body,dict),'PIPELINE_REVIEW_FIELDS','Body không hợp lệ.',400)
        if action=='start' and not body:return store.start(scope,review_id)
        if action=='heartbeat' and set(body)=={'lease'}:return store.heartbeat(scope,review_id,body['lease'])
        if action=='attachments' and set(body)=={'name','content'}:
            identity=store.attach(scope,review_id,body['name'],body['content'],recheck=recheck)
            return dict(attachment_id=identity,original_verified=False)
        if action=='save' and set(body)=={'expected_revision','feedback','lease','request_id'}:
            return store.save(scope,review_id,body['expected_revision'],body['feedback'],[e['evidence_id'] for e in item['evidence']],body['lease'],body['request_id'],recheck=recheck)
        ensure(False,'PIPELINE_REVIEW_FIELDS','Thiếu trường hoặc có trường không được nhận.',400)


def csv_report(report):
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    fields=['snapshot_id','run_id','bundle_id','as_of','case_id','outcome','explanation','action','active_seconds','task_ids','task_statuses','task_assignees','task_due_at',*MONEY]
    writer.writerow(fields)
    def safe(value,field):
        value='' if value is None else str(value)
        if field in MONEY and re.fullmatch(r'-?\d+',value):return value
        return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
    for case in report['cases']:
        review=case['review'];feedback=review['feedback'] or {}
        row={k:report[k] for k in ('snapshot_id','run_id','bundle_id','as_of')}
        row.update(case_id=case['case_id'],outcome=feedback.get('outcome'),explanation=feedback.get('explanation'),action=feedback.get('action'),active_seconds=review['active_seconds'])
        tasks=case.get('tasks',[])
        row.update(task_ids='; '.join(t['task_id'] for t in tasks),task_statuses='; '.join(t['status'] for t in tasks),
            task_assignees='; '.join(t['assignee']['display_label'] for t in tasks),task_due_at='; '.join(t['due_at'] or '' for t in tasks))
        row.update(case['financial_summary'])
        writer.writerow([safe(row.get(k),k) for k in fields])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
