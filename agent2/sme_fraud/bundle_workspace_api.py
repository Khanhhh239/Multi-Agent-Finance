"""Company membership business DTOs over completed immutable bundle observations."""
import re
from urllib.parse import urlsplit
from .auth import AuthError
from .import_files import ImportFailure,fail
from .validation_api import authorize_request,read_json,respond_failure
from .bundle_reviews import csv_report

RUN=r'([A-Za-z0-9_.:-]{8,128})'
ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/pipeline-workspace(?:/runs(?:/'+RUN+
    r'(?:/(report(?:\.csv)?|reviews/(rvw_[a-f0-9]{64})/(start|heartbeat|save|attachments|tasks)(?:/(att_[a-f0-9]{64}))?))?)?)?\Z')
REMEDIATION=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/pipeline-workspace/runs/'+RUN+
    r'/reviews/(rvw_[a-f0-9]{64})/remediation(?:/documents/(doc_[a-f0-9]{24})/versions/([1-9][0-9]{0,3}))?\Z')
BACKLOG=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/pipeline-workspace/backlog(?:/(reevaluate|active|shadow))?\Z')


def handle_bundle_workspace(handler,authorizer,service,method):
    path=urlsplit(handler.path).path
    bkl=BACKLOG.fullmatch(path)
    rem=REMEDIATION.fullmatch(path)
    route=ROUTE.fullmatch(path) or rem or bkl
    if route is None:return False
    try:
        run_id=None
        if bkl:
            company,bkl_action=bkl.groups()
        elif rem:
            company,run_id,review_id,document_id,version=rem.groups()
        else:company,run_id,tail,review_id,action,attachment_id=route.groups()
        scope,recheck=authorize_request(handler,authorizer,company)
        if service is None:fail(503,'PIPELINE_NOT_CONFIGURED','Chưa cấu hình luồng bundle.','Liên hệ người vận hành.')
        work=service.workspace;mime='application/json; charset=utf-8'
        if bkl:
            if method=='GET' and bkl_action in (None,'shadow','active'):
                value=work.backlog(scope,recheck,queue_mode=bkl_action or 'shadow')
            elif method=='POST' and bkl_action=='reevaluate':value=work.reevaluate_backlog(scope,read_json(handler),recheck)
            else:fail(405,'METHOD_NOT_ALLOWED','Thao tác backlog không hợp lệ.','Dùng màn hình vụ cần rà.')
        elif rem:
            from . import bundle_remediation
            if method=='GET' and document_id:value=bundle_remediation.content(work,scope,run_id,review_id,document_id,int(version),recheck)
            elif method=='GET':value=bundle_remediation.read(work,scope,run_id,review_id,recheck)
            elif method=='POST' and not document_id:value=bundle_remediation.command(work,scope,run_id,review_id,read_json(handler),recheck)
            else:fail(405,'METHOD_NOT_ALLOWED','Thao tác xử lý hồ sơ không hợp lệ.','Dùng màn hình vụ cần rà.')
        elif method=='GET' and not run_id:
            value=work.list_runs(scope,recheck);value['can_manage']=False
            try:
                authorizer.authorize_director(handler.headers.get('Authorization'),company)
                value['can_manage']=True
            except AuthError as error:
                if error.status!=403:raise
        elif method=='POST' and not run_id and urlsplit(handler.path).path.endswith('/runs'):
            value=work.submit(scope,read_json(handler),recheck,he_header=handler.headers.get('Authorization'))
        elif method=='GET' and (tail is None or tail in ('report','report.csv')):
            value=work.report(scope,run_id,recheck)
            if tail=='report.csv':value=csv_report(value);mime='text/csv; charset=utf-8'
        elif method=='GET' and action=='attachments' and attachment_id:
            item=work.case(scope,run_id,review_id,recheck);value=work.reviews.attachment(scope,item['review_id'],attachment_id)
        elif action=='tasks' and attachment_id is None and method in ('GET','POST'):
            value=work.tasks(scope,run_id,review_id,recheck,read_json(handler) if method=='POST' else None)
        elif method=='POST' and action and attachment_id is None:
            value=work.action(scope,run_id,review_id,action,read_json(handler),recheck)
        else:fail(405,'METHOD_NOT_ALLOWED','Thao tác hồ sơ không hợp lệ.','Dùng màn hình hồ sơ để thực hiện.')
        if isinstance(value,dict) and run_id:
            observed=work.observation(scope,run_id,recheck)
            value=dict(value,**{k:observed[k] for k in ('snapshot_id','run_id','bundle_id')})
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Đăng nhập lại trước khi tiếp tục.')
        handler.respond(200,value,mime)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except Exception:respond_failure(handler,ImportFailure(503,'PIPELINE_WORKSPACE_UNAVAILABLE','Chưa đọc hoặc lưu được hồ sơ lần chạy.','Giữ nguyên mã yêu cầu và tải lại; không tự tạo lượt khác.'))
    return True
