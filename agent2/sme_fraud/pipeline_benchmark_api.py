"""Director-only technical benchmark; same live manager, no extra key/config DB."""
import re
from urllib.parse import urlsplit
from .auth import AuthError
from .import_files import ImportFailure, fail
from .pipeline_benchmark import benchmark_shadow_run
from .validation_api import authorize_request, read_json, respond_failure

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/pipeline-benchmarks\Z')


def handle_pipeline_benchmark(handler,authorizer,snapshots,manager,method,resources=None):
    match=ROUTE.fullmatch(urlsplit(handler.path).path)
    if not match:return False
    try:
        company=match.group(1);scope,_=authorize_request(handler,authorizer,company)
        if not hasattr(authorizer,'authorize_director'):
            fail(403,'TECHNICAL_VIEW_DENIED','Benchmark kỹ thuật chỉ mở cho quản lý.','Dùng tài khoản director đúng doanh nghiệp.')
        header=handler.headers.get_all('Authorization',[None])[0]
        recheck=lambda:authorizer.authorize_director(header,company)
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Đăng nhập lại.')
        if method!='POST':fail(405,'METHOD_NOT_ALLOWED','Benchmark nhận yêu cầu POST.','Chọn lần chạy shadow đã lưu.')
        if snapshots is None or manager is None:fail(503,'BENCHMARK_NOT_CONFIGURED','Kho snapshot hoặc shadow chưa được cấu hình.','Bật backend có kho dữ liệu và model đã duyệt.')
        body=read_json(handler)
        if not isinstance(body,dict) or 'shadow_run_id' not in body or set(body)-{'shadow_run_id','ml_method'}:
            fail(400,'BENCHMARK_FIELDS','Chỉ nhận mã shadow và phương pháp ML tùy chọn.','Không gửi feature, điểm hoặc nhãn từ trình duyệt.')
        result=benchmark_shadow_run(snapshots,manager,scope,body['shadow_run_id'],resources=resources,recheck=recheck,ml_method=body.get('ml_method'))
        handler.respond(200,result)
    except (AuthError,ImportFailure) as error:
        respond_failure(handler,error)
    return True
