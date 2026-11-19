"""Transaction investigation uses the existing company auth and sealed review store."""
import re
from urllib.parse import urlsplit,unquote,parse_qs
from .auth import AuthError
from .import_files import ImportFailure,fail
from .validation_api import authorize_request,read_json,respond_failure
from .investigation import Investigation

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/pipeline-workspace/(?:runs/([A-Za-z0-9_.:-]{8,128})/)?investigation(?:/([A-Za-z0-9_.:-]{1,128})(?:/reviews/(rvw_[a-f0-9]{64}))?(?:/(start|heartbeat|save|attachments))?)?\Z')

def handle(handler,authorizer,service,method):
    url=urlsplit(handler.path);match=ROUTE.fullmatch(unquote(url.path))
    if not match:return False
    try:
        company,run,tid,review,action=match.groups();scope,recheck=authorize_request(handler,authorizer,company)
        if service is None:fail(503,'PIPELINE_NOT_CONFIGURED','Chưa có nguồn phân tích được cấu hình.','Bật Agent2 hoặc liên hệ người quản lý.')
        work=service.workspace;view=Investigation(work)
        if url.query:fail(400,'INVESTIGATION_QUERY','Không nhận tham số ngoài đường dẫn đã khóa.','Mở lại đúng giao dịch.')
        if method=='GET' and not action:
            if tid and not run:fail(400,'INVESTIGATION_RUN_REQUIRED','Cần chọn đúng lần phân tích.','Mở giao dịch từ hàng đợi.')
            value=view.detail(scope,run,tid,recheck,review) if tid else view.queue(scope,run,recheck)
        elif method=='POST' and run and tid and action:
            item=view.resolve(scope,run,tid,recheck,review);body=read_json(handler)
            if action=='start':
                if set(body)!={'request_id'} or not isinstance(body['request_id'],str) or not 8<=len(body['request_id'])<=128:fail(400,'INVESTIGATION_REQUEST','Thiếu mã yêu cầu.','Bấm bắt đầu lại.')
                value=work.action(scope,run,item['review_id'],'start',{},recheck)
                view.record(scope,item['review_id'],body['request_id'],'started',recheck)
            else:
                value=work.action(scope,run,item['review_id'],action,body,recheck)
                if action in ('save','attachments'):
                    key=body['request_id'] if action=='save' else value['attachment_id']
                    view.record(scope,item['review_id'],key,'saved' if action=='save' else 'attached',recheck)
        else:fail(405,'METHOD_NOT_ALLOWED','Thao tác không hợp lệ.','Dùng giao diện hàng đợi và điều tra.')
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Đăng nhập lại.')
        handler.respond(200,value)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    return True
