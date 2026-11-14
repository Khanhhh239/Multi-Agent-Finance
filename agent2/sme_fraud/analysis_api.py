"""Authenticated synchronous snapshot analysis; no fit, persistence or queue."""
import re
import sqlite3
from urllib.parse import urlsplit

from .auth import AuthError
from .import_files import ImportFailure,canonical,fail
from .snapshot_analysis import analyze_snapshot,normalize_as_of
from .validation_api import authorize_request,read_json,respond_failure

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/snapshots/([A-Za-z0-9_.:-]{1,128})/analyze\Z')
SNAPSHOT_ID=re.compile(r'snp_[a-f0-9]{32}\Z')
MAX_OUTPUT_BYTES=5*1024*1024


def handle_analysis(handler,authorizer,store,method,resources=None):
    catalogue_route=re.fullmatch(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/rules/catalogue',urlsplit(handler.path).path)
    if catalogue_route:
        try:
            scope,recheck=authorize_request(handler,authorizer,catalogue_route[1])
            if method!='GET':fail(405,'METHOD_NOT_ALLOWED','Danh mục luật chỉ đọc bằng GET.','Không gửi thay đổi cấu hình qua endpoint này.')
            headers=handler.headers.get_all('Authorization',[]);authorization=headers[0] if len(headers)==1 else None
            if not hasattr(authorizer,'authorize_director'):fail(503,'ROLE_POLICY_UNAVAILABLE','Chưa có policy quản lý.','Cấu hình quyền phía server.')
            check=lambda:authorizer.authorize_director(authorization,catalogue_route[1])
            if check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Gửi lại theo quyền hiện hành.')
            from .rule_snapshot import catalogue,CONTRACT
            value=dict(version='rule-catalogue/1.0.0',company_id=catalogue_route[1],implemented_rule_count=35,input_profile=CONTRACT,rules=catalogue(),aggregate_weights_configured=False)
            if check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Gửi lại theo quyền hiện hành.')
            handler.respond(200,canonical(value))
        except (AuthError,ImportFailure) as error:respond_failure(handler,error)
        return True
    route=ROUTE.fullmatch(urlsplit(handler.path).path)
    if route is None:return False
    try:
        scope,recheck=authorize_request(handler,authorizer,route[1])
        if method!='POST':fail(405,'METHOD_NOT_ALLOWED','Phân tích snapshot dùng POST.','Gửi JSON gồm as_of và view tùy chọn.')
        if not SNAPSHOT_ID.fullmatch(route[2]):fail(400,'SNAPSHOT_ID','Mã snapshot không hợp lệ.','Dùng snapshot_id do bước xác nhận lưu trả về.')
        body=read_json(handler)
        if not isinstance(body,dict) or 'as_of' not in body or set(body)-{'as_of','view'}:
            fail(400,'ANALYSIS_REQUEST','Yêu cầu cần as_of và chỉ nhận thêm view tùy chọn.',
                'Không gửi vai trò, dữ liệu, điểm, model hoặc kết quả tự tạo; chọn snapshot trên URL.')
        view=body.get('view','review')
        if view not in ('review','technical'):fail(400,'ANALYSIS_VIEW','view không hợp lệ.','Chọn review hoặc technical; technical cần quyền quản lý.')
        as_of=normalize_as_of(body['as_of'])
        if view=='technical':
            headers=handler.headers.get_all('Authorization',[])
            authorization=headers[0] if len(headers)==1 else None
            # Never trust a client role or a hidden UI control; recheck on every read and before response.
            if not hasattr(authorizer,'authorize_director'):
                fail(503,'ROLE_POLICY_UNAVAILABLE','Chưa cấu hình kiểm quyền chi tiết kỹ thuật.','Dùng view review hoặc cấu hình policy backend.')
            recheck=lambda:authorizer.authorize_director(authorization,route[1])
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Gửi lại theo quyền hiện hành.')
        if store is None:fail(503,'SNAPSHOT_STORAGE_REQUIRED','Kho snapshot chưa được cấu hình.','Cấu hình kho snapshot mới riêng trước khi phân tích.')
        from .analysis_resources import AnalysisResources
        resources=resources or AnalysisResources()
        value=analyze_snapshot(store,scope,route[2],as_of,technical=view=='technical',recheck=recheck,resources=resources)
        packed=canonical(value)
        if len(packed)>MAX_OUTPUT_BYTES:
            fail(413,'ANALYSIS_OUTPUT_LIMIT','Kết quả vượt giới hạn trả đồng bộ của bản demo.',
                'Dùng snapshot thử nhỏ hơn có đủ nguồn liên quan; không tự cắt giao dịch hoặc lịch sử.')
        resources.recheck_id(scope,value['analysis_context_id'])
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước khi trả kết quả.','Gửi lại theo quyền hiện hành.')
        handler.respond(200,packed)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except (sqlite3.Error,OSError):
        respond_failure(handler,ImportFailure(503,'ANALYSIS_UNAVAILABLE','Kho hoặc nguồn phân tích tạm thời chưa sẵn sàng.','Kiểm tra dịch vụ rồi gửi lại; chưa có kết quả được xác nhận.'))
    except (ValueError,KeyError,TypeError,ArithmeticError,RecursionError):
        respond_failure(handler,ImportFailure(500,'ANALYSIS_FAILED','Không thể tạo kết quả phân tích nhất quán.','Kiểm tra snapshot và phiên bản xử lý; không dùng kết quả từng phần.'))
    return True
