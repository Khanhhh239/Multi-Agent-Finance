"""Director-only release APIs. No caller supplied artifacts, metrics or pass flags."""
import re
from urllib.parse import urlsplit
from .auth import AuthError
from .import_files import ImportFailure,fail
from .validation_api import authorize_request,read_json,respond_failure
from .snapshot_api import _key

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/pipeline-releases(?:/(prepare|qualify|approve|switch|revoke|diff|runs|objects/(?:rbun|rgat|rapr|ract|rpin|robs)_[a-f0-9]{64}))?\Z')
FIELDS={
 'prepare':{'snapshot_id','name'},'qualify':{'bundle_id','lane'},
 'approve':{'bundle_id','gate_id','lane','reason'},
 'switch':{'bundle_id','gate_id','approval_id','lane','expected_revision','reason','action'},
 'revoke':{'id','reason'},'diff':{'left','right'},
 'runs':{'run_id','lane','snapshot_id','as_of'}}


def handle_releases(handler,authorizer,service,method):
    match=ROUTE.fullmatch(urlsplit(handler.path).path)
    if match is None:return False
    try:
        company,action=match.groups();scope,_=authorize_request(handler,authorizer,company)
        header=handler.headers.get_all('Authorization',[None])[0]
        if not hasattr(authorizer,'authorize_director'):fail(403,'MANAGER_REQUIRED','Cần quyền quản lý phân tích.','Mở bằng tài khoản được cấp quyền trong doanh nghiệp.')
        recheck=lambda:authorizer.authorize_director(header,company)
        if recheck()!=scope:fail(403,'MANAGER_REQUIRED','Cần quyền quản lý doanh nghiệp.','Tải lại quyền từ Portal.')
        if service is None:fail(503,'RELEASE_NOT_CONFIGURED','Chưa bật kho release được bảo vệ tại node doanh nghiệp.','Người vận hành cần cấu hình khóa và đường dẫn kho riêng.')
        if method=='GET' and action is None:value=service.overview(scope,recheck)
        elif method=='GET' and action and action.startswith('objects/'):
            oid=action.split('/')[1];value=dict(id=oid,value=service.store.get(scope,oid,recheck=recheck))
        elif method=='POST' and action in FIELDS:
            body=read_json(handler)
            allowed=FIELDS[action]|({'plan_id'} if action=='prepare' else {'execution_mode'} if action=='runs' else set())
            if not isinstance(body,dict) or not FIELDS[action]<=set(body) or set(body)-allowed:
                fail(400,'RELEASE_FIELDS','Nội dung thao tác không đúng schema.','Chỉ gửi các trường của thao tác; không gửi khóa, model, policy hoặc kết quả gate tự khai.')
            if any(not isinstance(v,str) or len(v)>1000 for k,v in body.items() if k!='expected_revision'):
                fail(400,'RELEASE_FIELDS','Các mã và lý do phải là chuỗi hợp lệ.','Dùng đúng mã trả về từ server.')
            if action=='prepare':value=service.prepare(scope,body['snapshot_id'],body['name'],_key(handler),recheck,plan_id=body.get('plan_id'))
            elif action=='qualify':value=service.qualify(scope,**body,recheck=recheck,key=_key(handler))
            elif action=='approve':value=service.approve(scope,**body,recheck=recheck,key=_key(handler))
            elif action=='switch':value=service.switch(scope,body,_key(handler),recheck)
            elif action=='revoke':value=service.store.revoke(scope,body['id'],body['reason'],recheck)
            elif action=='diff':value=service.diff(scope,**body,recheck=recheck)
            else:value=service.run(scope,**body,recheck=recheck)
        else:fail(405,'METHOD_NOT_ALLOWED','Thao tác release không hợp lệ.','Dùng GET xem trạng thái và POST cho thao tác có schema.')
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Đăng nhập lại trước khi tiếp tục.')
        handler.respond(200,value)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except Exception:respond_failure(handler,ImportFailure(503,'RELEASE_UNAVAILABLE','Chưa hoàn tất thao tác release.','Tải lại trạng thái trước khi thử lại; giữ nguyên mã yêu cầu, kho và khóa.'))
    return True
