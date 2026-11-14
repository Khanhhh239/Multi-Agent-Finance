"""Company work area and business reports over existing immutable HE runs.

No ranking, ensemble weights, new training labels, or implicit model fitting.
"""
import csv
import io
import re
from urllib.parse import urlsplit

from .auth import AuthError
from .import_files import ImportFailure,fail
from .validation_api import authorize_request,respond_failure
from .he_workbench import saved_runs
from .review_api import cases_for,summarize

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/workspace(?:/runs/(herun_[a-f0-9]{32})(?:/(report|report\.csv))?)?\Z')
NAMES={'rules':'Đối chiếu thanh toán','statistics':'So sánh với lịch sử','graph':'Liên kết đối tượng','ml':'Phân tích bất thường'}
PHASES={'queued':'Đã nhận yêu cầu','preparing':'Đang chuẩn bị dữ liệu','ready':'Đang chuẩn bị phép tính tiếp theo','sending':'Đang gửi và tính trên dữ liệu mã hóa','received':'Đang kiểm tra kết quả mã hóa','decrypting':'Đang giải mã tại doanh nghiệp','retryable':'Đang chờ kết nối lại','waiting_worker':'Đang chờ bộ xử lý','waiting_authorization':'Cần đăng nhập để tiếp tục','completed':'Đã phân tích xong','failed':'Lượt phân tích gặp lỗi','expired':'Yêu cầu đã hết hạn'}
REASONS={'rule_sources_unavailable':'Thiếu hóa đơn, liên kết thanh toán hoặc phạm vi lịch sử.','artifact_missing':'Chưa có phiên bản phân tích phù hợp.','artifact_not_pinned':'Chưa cấu hình phiên bản phân tích cho doanh nghiệp.','artifact_incompatible':'Phiên bản phân tích chưa tương thích với dữ liệu.','input_out_of_domain':'Giá trị nằm ngoài phạm vi đã kiểm chứng của phiên bản hiện tại.','features_missing':'Thiếu dữ liệu đầu vào cần thiết.','features_all_missing':'Chưa có đủ dữ liệu đầu vào.','he_graph_node_limit':'Số đối tượng vượt phạm vi phân tích liên kết hiện tại.','he_p1_source_limit':'Lịch sử liên quan vượt phạm vi tính hiện tại; cần người quản lý kiểm tra.','he_batch_limit':'Tệp vượt số giao dịch hỗ trợ trong một lượt chấm hiện tại.','artifact_training_overlap':'Giao dịch đã thuộc dữ liệu chuẩn bị phiên bản; cần dùng kỳ đánh giá riêng.','before_evaluation_period':'Giao dịch nằm trước kỳ đánh giá của phiên bản.','he_graph_sources_missing':'Chưa có đủ thuộc tính để đối chiếu liên kết.','he_statistics_out_of_domain':'Dữ liệu nằm ngoài phạm vi so sánh lịch sử đã kiểm chứng.'}
OUTCOMES={'confirmed_risk':'Có vấn đề cần xử lý','legitimate':'Không phát hiện vấn đề','inconclusive':'Chưa đủ căn cứ'}


def money(value):
    return f'{int(value):,}'.replace(',','.')+' đ'


def progress(jobs,scope,job,status):
    """Read only committed counts; never expose sealed feature/model inputs."""
    result=dict(phase=status['phase'],message=PHASES.get(status['phase'],'Đang xử lý'),completed_tasks=None,total_tasks=None)
    for store in (jobs.store,getattr(getattr(jobs,'legacy',None),'store',None)):
        if store is None:continue
        try:_,data=store.get(scope,job)
        except Exception as error:
            if getattr(error,'code',None)=='NODE_JOB_NOT_FOUND':continue
            raise
        pending=data.get('pending')
        if isinstance(pending,dict) and isinstance(pending.get('tasks'),list):
            result.update(completed_tasks=int(pending['cursor']),total_tasks=len(pending['tasks']))
        result.update(snapshot_id=data['request']['snapshot_id'],as_of=data['request']['as_of'])
        break
    return result


def case_view(case,row):
    branch=row.get('branches',{}).get('rules',{})
    invoices=branch.get('invoice_checks',[]);groups=branch.get('simultaneous_checks',[])
    hit=next((c for c in invoices if c.get('matched')),None);group=next((c for c in groups if c.get('matched')),None)
    why=case['why']
    if hit:why='Tổng đã thanh toán '+money(hit['cumulative_paid_vnd'])+' so với nghĩa vụ hóa đơn '+money(hit['invoice_gross_vnd'])+'. Cần đối chiếu khoản trả thêm và chứng từ liên quan.'
    elif group:why='Các khoản thanh toán cùng thời điểm có tổng '+money(group['cumulative_paid_vnd'])+' so với nghĩa vụ '+money(group['invoice_gross_vnd'])+'. Cần đối chiếu cả nhóm thanh toán.'
    elif branch.get('status')=='not_applicable':why='Đây là loại giao dịch không thuộc phép đối chiếu thanh toán hiện tại. Kiểm tra liên kết khoản điều chỉnh và bản ghi gốc nếu có.'
    elif not branch.get('available',False):why='Chưa đủ nguồn để kết luận về thanh toán. Cần bổ sung hóa đơn, liên kết phân bổ hoặc phạm vi lịch sử còn thiếu.'
    checks=[]
    for kind,label in NAMES.items():
        item=row.get('branches',{}).get(kind)
        if item is None and kind=='ml':item=dict(available=row.get('available',False),status=row.get('status','unavailable'),reason=row.get('reason'))
        item=item or {}
        applicable=item.get('status')!='not_applicable';available=bool(item.get('available'))
        message=('Đã phân tích theo nguồn được cung cấp.' if available else REASONS.get(item.get('reason'),'Chưa đủ nguồn hoặc phiên bản phù hợp để phân tích.')) if applicable else 'Không áp dụng cho loại giao dịch này.'
        checks.append(dict(kind=kind,title=label,status='available' if available else 'unavailable' if applicable else 'not_applicable',message=message))
    fields=('case_id','record_id','revision','amount_vnd','currency','event_at','as_of','question','next_step','evidence','review')
    value={k:case[k] for k in fields}
    tx=next((e['record'] for e in case['evidence'] if e['table']=='transactions' and e['record']['record_id']==case['record_id']),{})
    if tx.get('kind') in ('salary','payroll'):
        value.update(question='Khoản lương có đúng người, kỳ hưởng và căn cứ phê duyệt không?',next_step='Đối chiếu bảng lương, bảng công, hồ sơ nhân sự và chứng từ chuyển tiền. Thiếu tài liệu thì ghi rõ phần cần bổ sung.')
    elif tx.get('kind')=='adjustment':
        value.update(question='Khoản điều chỉnh có đúng khoản gốc, số tiền và căn cứ cho phép không?',next_step='Đối chiếu bản ghi gốc, liên kết điều chỉnh, bút toán và hồ sơ phê duyệt liên quan.')
    graph=row.get('branches',{}).get('graph',{});entities=graph.get('entities',[]);links=[]
    records={(e['table'],e['record']['record_id'],e['record']['revision']):e['record'] for e in case['evidence']}
    labels=[]
    for entity in entities:
        record=records.get((entity['table'],entity['record_id'],entity['revision']),{})
        labels.append(record.get('name') or record.get('legal_name') or record.get('full_name') or entity['record_id'])
    matrix=graph.get('links_by_field',[])
    for i in range(len(entities)):
        for j in range(i+1,len(entities)):
            if not matrix:continue
            for k,label in enumerate(('Cùng tài khoản ngân hàng','Cùng số điện thoại','Cùng địa chỉ','Cùng mã số thuế')):
                if matrix[k][i][j]:links.append(dict(source=labels[i],target=labels[j],relation=label,context_only=k>=2))
    value.update(why=why,checks=checks,payment_signal=bool(hit or group),payment_unavailable=not branch.get('available',False) and branch.get('status')!='not_applicable',
        invoice_checks=[{k:c[k] for k in ('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd','matched') if k in c} for c in invoices],
        simultaneous_checks=[{k:c[k] for k in ('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd','matched') if k in c} for c in groups],graph_links=links)
    value['missing_sources']=[{k:g[k] for k in ('message','action') if k in g} for g in branch.get('gaps',[]) if g.get('message') or g.get('action')]
    return value


def csv_report(report):
    def text(value):
        value='' if value is None else str(value)
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['Doanh nghiệp','Lần phân tích','Bản dữ liệu','Mã giao dịch','Thời gian','Số tiền VND','Kết quả đã rà','Giải thích','Hành động','Tài liệu còn thiếu','Căn cứ đã xem','Giây rà đã lưu','Phiên bản kết quả','Nguồn mô phỏng'])
    for case in report['cases']:
        review=case['review'];feedback=review['feedback'] or {}
        # Only the validated money column is numeric. All user text is escaped
        # against spreadsheet formula execution, including IDs and notes.
        writer.writerow([text(report['company_id']),text(report['run_id']),text(report['snapshot_id']),text(case['record_id']),text(case['event_at']),str(int(case['amount_vnd'])),text(OUTCOMES.get(feedback.get('outcome'),'')),text(feedback.get('explanation')),text(feedback.get('action')),text(feedback.get('missing_materials')),text(', '.join(feedback.get('evidence_ids',[]))),review['active_seconds'],review['revision'],'Có' if any(e['simulated'] for e in case['evidence']) else 'Không'])
    return ('\ufeff'+output.getvalue()).encode('utf-8')


def handle_workspace(handler,authorizer,snapshots,backend,reviews):
    parsed=urlsplit(handler.path);match=ROUTE.fullmatch(parsed.path)
    if not match:return False
    try:
        company,job,export=match.groups();scope,recheck=authorize_request(handler,authorizer,company)
        if parsed.query:fail(400,'QUERY_NOT_SUPPORTED','Đường dẫn không hợp lệ.','Mở lại từ màn hình làm việc.')
        if snapshots is None or backend is None:fail(503,'WORKSPACE_NOT_CONFIGURED','Phân tích chưa được cấu hình.','Bật Agent2 từ Portal hoặc liên hệ người quản lý.')
        header=handler.headers.get_all('Authorization',[None])[0]
        if not job:
            catalog=backend.datasets(scope,recheck);runs=saved_runs(backend.node.jobs,scope)['runs'][:100]
            training_snapshot=None
            selected=backend.selection(scope)
            if selected:
                from experiments.he_inference.registry_export import _load_model
                from experiments.he_inference.protocol import HEUnavailable
                try:
                    _,manifest,_=_load_model(backend.node.model_db,scope,selected,recheck,metadata_only=True)
                    training_snapshot=manifest.get('fit_context',{}).get('config',{}).get('snapshot_id')
                except (HEUnavailable,ImportFailure):pass
            datasets=[dict(d,is_training_source=d['snapshot_id']==training_snapshot) for d in catalog['datasets']]
            can_manage=False
            try:can_manage=hasattr(authorizer,'authorize_director') and authorizer.authorize_director(header,company)==scope
            except AuthError:pass
            value=dict(version='agent2-workspace/1.0.0',company_id=company,datasets=datasets,available=catalog['available'],message=catalog.get('message',''),can_manage=can_manage,
                runs=[{k:r.get(k) for k in ('job_id','snapshot_id','as_of','phase','created_at','row_count')} for r in runs],history_limit=100,
                summary=dict(datasets=len(catalog['datasets']),completed=sum(r['phase']=='completed' for r in runs),active=sum(r['phase'] not in ('completed','failed','expired') for r in runs),failed=sum(r['phase'] in ('failed','expired') for r in runs)))
        else:
            state=backend.node.jobs.status(company,header,job)
            value=dict(version='agent2-workspace-run/1.0.0',company_id=company,run_id=job,status=state['phase'],progress=progress(backend.node.jobs,scope,job,state),created_at=state['created_at'])
            value.update(snapshot_id=value['progress'].pop('snapshot_id',None),as_of=value['progress'].pop('as_of',None))
            if state['phase']=='completed':
                code,result=backend.node.jobs.result(company,header,job)
                if code!=200:fail(409,'RESULT_NOT_READY','Kết quả chưa sẵn sàng.','Chờ hoàn tất rồi tải lại.')
                review_store=reviews['current' if result.get('version')=='he-four-branch-result/1.0.0' else 'legacy'] if isinstance(reviews,dict) else reviews
                if review_store is None:fail(503,'REVIEWS_NOT_CONFIGURED','Kho phiếu rà chưa được cấu hình.','Liên hệ người quản lý.')
                cases=cases_for(snapshots,scope,result,review_store,recheck);rows={(r['record_id'],r['revision']):r for r in result['rows']}
                value.update(snapshot_id=result['snapshot_id'],as_of=result['as_of'],row_count=result['row_count'],summary=summarize(cases),
                    cases=[case_view(c,rows[c['record_id'],c['revision']]) for c in cases],training_eligible=False,identity_basis='Portal workspace actor',aggregation_available=False,
                    comparison_available=result.get('version')=='he-four-branch-result/1.0.0')
            elif export:fail(409,'RESULT_NOT_READY','Lượt phân tích chưa hoàn tất.','Mở lại lượt chạy để tiếp tục hoặc xem trạng thái.')
            if state['phase']=='failed':value.update(message='Lượt này gặp lỗi và được giữ trong lịch sử. Có thể tạo lượt kiểm thử mới sau khi khắc phục nguyên nhân.')
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền truy cập đã thay đổi.','Mở lại từ Portal.')
        handler.respond(200,csv_report(value) if export=='report.csv' else value,'text/csv; charset=utf-8' if export=='report.csv' else 'application/json; charset=utf-8')
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except Exception as error:
        status=getattr(error,'status',503)
        if status not in (401,403,404,409,410,422,429,503):status=503
        respond_failure(handler,ImportFailure(status,'WORKSPACE_UNAVAILABLE','Chưa đọc được dữ liệu làm việc trong phạm vi được cấp quyền.','Kiểm tra kết nối, doanh nghiệp và lượt phân tích rồi thử lại.'))
    return True
