"""Company manager settings. Fit and activation also require model.fit."""
import re
from urllib.parse import urlsplit
from .auth import AuthError
from .import_files import ImportFailure,fail
from .validation_api import authorize_request,read_json,respond_failure
from .snapshot_api import _key

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/analysis-config(?:/(draft|fit|activate))?\Z')


def handle_config(handler,authorizer,manager,method):
    route=ROUTE.fullmatch(urlsplit(handler.path).path)
    if route is None:return False
    try:
        company,action=route.groups();scope,_=authorize_request(handler,authorizer,company)
        header=handler.headers.get_all('Authorization',[None])[0]
        if not hasattr(authorizer,'authorize_director'):fail(403,'MANAGER_REQUIRED','Cần quyền quản lý phân tích cho doanh nghiệp này.','Mở lại bằng tài khoản được cấp quyền.')
        recheck=lambda:authorizer.authorize_director(header,company)
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Tải lại từ Portal.')
        if manager is None:fail(503,'CONFIG_NOT_AVAILABLE','Chưa bật cấu hình bốn nhánh cho node này.','Người vận hành cần hoàn tất thiết lập backend.')
        if method=='GET' and action is None:value=manager.get(scope);status=200
        elif method=='POST' and action in ('draft','fit','activate'):
            from .method_store import require_fit
            require_fit(scope);key=_key(handler);body=read_json(handler)
            if not isinstance(body,dict):fail(400,'CONFIG_FIELDS','Yêu cầu không hợp lệ.','Dùng các ô trên màn hình.')
            if action=='draft':value=manager.draft(scope,body,key);status=200
            else:
                if set(body)!={'expected_revision'} or type(body['expected_revision']) is not int:fail(400,'CONFIG_REVISION','Thiếu phiên bản cấu hình.','Tải lại cấu hình hiện hành.')
                if action=='fit':value=manager.fit(scope,header,body['expected_revision'],key);status=202
                else:value=manager.activate(scope,header,body['expected_revision'],key);status=200
        else:fail(405,'METHOD_NOT_ALLOWED','Thao tác cấu hình không hợp lệ.','Dùng đúng thao tác trên màn hình.')
        if method=='POST':value=manager.get(scope)
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước khi trả kết quả.','Mở lại từ Portal.')
        handler.respond(status,value)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except Exception:respond_failure(handler,ImportFailure(503,'CONFIG_UNAVAILABLE','Chưa hoàn tất thao tác cấu hình.','Tải lại trạng thái trước khi thử lại; không tự đổi phiên bản đang chạy.'))
    return True
