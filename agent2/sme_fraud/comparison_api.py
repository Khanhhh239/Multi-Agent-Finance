"""Same-run P1 vs P1+ML trial with immutable company-scoped selections."""
import re
from urllib.parse import urlsplit
from .analysis_resources import AnalysisResources
from .auth import AuthError
from .import_files import ImportFailure,canonical,digest,fail
from .review_api import cases_for
from .rule35_comparison import make_rule35_plan,rule35_cases_for,rule35_report_for
from .selection_comparison import make_plan,report_for,POLICY,BUDGET
from .snapshot_analysis import analyze_snapshot,normalize_as_of
from .validation_api import authorize_request,read_json,respond_failure

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/workspace/runs/(herun_[a-f0-9]{32})/comparison\Z')
ANA_ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/analyses/(ana_[a-f0-9]{64})/comparison\Z')
SNAPSHOT_ID=re.compile(r'snp_[a-f0-9]{32}\Z')


def comparison_inputs(company,header,scope,recheck,snapshots,backend,reviews,stores,run):
    state=backend.node.jobs.status(company,header,run)
    if state['phase']!='completed':fail(409,'COMPARISON_RESULT_REQUIRED','Cần lượt phân tích đã hoàn tất để khóa phép so sánh.','Chờ hoàn tất hoặc mở kết quả đã lưu.')
    code,result=backend.node.jobs.result(company,header,run)
    if code!=200 or result.get('version')!='he-four-branch-result/1.0.0':fail(409,'COMPARISON_FOUR_BRANCH_REQUIRED','Lượt này chưa có đủ kết quả luật và ML để so sánh.','Chọn lượt bốn nhánh đã hoàn tất.')
    selected='current' if result.get('version')=='he-four-branch-result/1.0.0' else 'legacy'
    review_store=reviews[selected] if isinstance(reviews,dict) else reviews
    store=stores[selected] if isinstance(stores,dict) else stores
    cases=cases_for(snapshots,scope,result,review_store,recheck)
    manifest=snapshots.get_snapshot(scope,result['snapshot_id'],recheck)
    row,data=backend.node.jobs.store.get(scope,run)
    return result,cases,manifest,dict(artifact_id=data['request'].get('artifact_id'),plan_sha256=result.get('plan_sha256')),store


def evaluate_request(company,header,scope,recheck,snapshots,backend,reviews,stores,run,create=False):
    result,cases,manifest,pin,store=comparison_inputs(company,header,scope,recheck,snapshots,backend,reviews,stores,run)
    saved=store.get(scope,run)
    if saved is None:
        if not create:fail(404,'COMPARISON_NOT_CREATED','Lượt này chưa khóa phép so sánh.','Bấm So sánh luật và ML để tạo kế hoạch.')
        plan=make_plan(result,cases,manifest,pin)
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
        saved=store.put(scope,plan)
    plan=saved['plan']
    if plan['result_sha256']!=digest(canonical(result)) or plan['snapshot_checksum']!=manifest['checksum'] or plan['model_pin']!=pin:
        fail(409,'COMPARISON_SOURCE_CHANGED','Kết quả hoặc nguồn không còn khớp kế hoạch đã khóa.','Kiểm tra đúng run/snapshot/model; không thay lựa chọn trong kế hoạch cũ.')
    value=report_for(plan,cases);value.update(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    value.pop('report_sha256');value['report_sha256']=digest(canonical(value))
    return value


def evaluate_rule35_request(company,header,authorizer,scope,recheck,snapshots,reviews,stores,analysis_id,body=None,resources=None,create=False):
    if hasattr(authorizer,'authorize_director'):
        tech_check=lambda:authorizer.authorize_director(header,company)
        if tech_check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
    else:
        tech_check=recheck
    review_store=reviews['current'] if isinstance(reviews,dict) else reviews
    store=stores['current'] if isinstance(stores,dict) else stores
    saved=store.get(scope,analysis_id)
    if saved is None:
        if not create:fail(404,'COMPARISON_NOT_CREATED','Lượt phân tích 35 luật này chưa khóa phép so sánh.','Gửi snapshot_id và as_of để tạo kế hoạch.')
        if not isinstance(body,dict) or not SNAPSHOT_ID.fullmatch(str(body.get('snapshot_id') or '')):
            fail(400,'SNAPSHOT_ID','Thiếu hoặc sai mã snapshot cho phép so sánh 35 luật.','Chọn đúng snapshot_id đã lưu.')
        snapshot_id=body['snapshot_id']
        as_of=normalize_as_of(body.get('as_of'))
        ml_method=body.get('ml_method')
    else:
        snapshot_id=saved['plan']['snapshot_id']
        as_of=saved['plan']['as_of']
        ml_method=saved['plan'].get('ml_method')
    resources=resources or AnalysisResources()
    analysis=analyze_snapshot(snapshots,scope,snapshot_id,as_of,technical=True,recheck=tech_check,resources=resources)
    if analysis['analysis_id']!=analysis_id:
        fail(409,'COMPARISON_ANALYSIS_MISMATCH','Mã phân tích 35 luật không khớp nguồn và phiên bản hiện tại.','Kiểm tra snapshot_id, as_of và model binding.')
    manifest=snapshots.get_snapshot(scope,snapshot_id,recheck)
    raw_data=snapshots.get_snapshot(scope,snapshot_id,recheck,data=True)
    from finance_input.json_io import loads
    raw_obj=loads(raw_data)
    cases=rule35_cases_for(snapshots,scope,analysis,review_store,recheck,raw_data=raw_obj)
    if saved is None:
        plan=make_rule35_plan(analysis,cases,manifest,ml_method=ml_method,raw_data=raw_obj)
        if tech_check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
        saved=store.put(scope,plan)
    plan=saved['plan']
    expected_pin=analysis.get('bridge_provenance',{}).get('model_pins',{}).get(plan.get('ml_method')) if plan.get('ml_method') else None
    if plan['result_sha256']!=digest(canonical(analysis)) or plan['snapshot_checksum']!=manifest['checksum'] or plan.get('model_pin')!=expected_pin:
        fail(409,'COMPARISON_SOURCE_CHANGED','Kết quả 35 luật hoặc model không còn khớp kế hoạch đã khóa.','Kiểm tra đúng phân tích/snapshot/model; không thay lựa chọn trong kế hoạch cũ.')
    value=rule35_report_for(plan,cases,redaction='review')
    value.update(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    value.pop('report_sha256');value['report_sha256']=digest(canonical(value))
    return value


def handle_comparison(handler,authorizer,snapshots,backend,reviews,stores,method,analysis_resources=None):
    path=urlsplit(handler.path).path
    match=ROUTE.fullmatch(path)
    ana_match=None if match else ANA_ROUTE.fullmatch(path)
    if not match and not ana_match:return False
    try:
        if ana_match:
            company,analysis_id=ana_match.groups();scope,recheck=authorize_request(handler,authorizer,company)
            if stores is None or reviews is None or snapshots is None:fail(503,'COMPARISON_NOT_CONFIGURED','Bộ so sánh 35 luật chưa được cấu hình.','Bật kho snapshot, phiếu rà và kế hoạch so sánh.')
            if method not in ('GET','POST'):fail(405,'METHOD_NOT_ALLOWED','Thao tác chưa được hỗ trợ.','Dùng GET hoặc POST.')
            body=None
            if method=='POST':
                body=read_json(handler)
                allowed={'policy','budget','snapshot_id','as_of','ml_method'}
                required={'policy','budget','snapshot_id','as_of'}
                if not isinstance(body,dict) or not required.issubset(body) or set(body)-allowed or body['policy']!=POLICY or type(body['budget']) is not int or body['budget']!=BUDGET:
                    fail(400,'COMPARISON_POLICY','Phép thử 35 luật dùng luật trước, ML bù chỗ trống, tối đa 5 giao dịch.','Giữ chính sách thử đã chốt; chỉ gửi policy, budget, snapshot_id, as_of và ml_method tùy chọn.')
                if 'ml_method' in body and body['ml_method'] is not None and body['ml_method'] not in {'isolation_forest','autoencoder','ecod','lof'}:
                    fail(400,'COMPARISON_POLICY','Tên mô hình ML không hợp lệ.','Chọn mô hình thuộc bộ đã cấu hình (isolation_forest, ecod, autoencoder, lof).')
            header=handler.headers.get_all('Authorization',[None])[0]
            value=evaluate_rule35_request(company,header,authorizer,scope,recheck,snapshots,reviews,stores,analysis_id,body,analysis_resources,method=='POST')
            if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
            handler.respond(200,value)
            return True
        company,run=match.groups();scope,recheck=authorize_request(handler,authorizer,company)
        if backend is None or stores is None or reviews is None or snapshots is None:fail(503,'COMPARISON_NOT_CONFIGURED','Bộ so sánh chưa được cấu hình.','Bật Agent2 có kho kết quả và phiếu rà.')
        if method not in ('GET','POST'):fail(405,'METHOD_NOT_ALLOWED','Thao tác chưa được hỗ trợ.','Dùng nút trên màn hình.')
        if method=='POST':
            body=read_json(handler)
            if not isinstance(body,dict) or set(body)!={'policy','budget'} or body['policy']!=POLICY or type(body['budget']) is not int or body['budget']!=BUDGET:
                fail(400,'COMPARISON_POLICY','Phép thử dùng luật trước, ML bù chỗ trống, tối đa 5 giao dịch.','Giữ chính sách thử đã chốt; không gửi trọng số hoặc kết luận từ trình duyệt.')
        header=handler.headers.get_all('Authorization',[None])[0]
        value=evaluate_request(company,header,scope,recheck,snapshots,backend,reviews,stores,run,method=='POST')
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
        handler.respond(200,value)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except Exception as error:
        status=getattr(error,'status',503)
        if status not in (401,403,404,409,422,429,503):status=503
        respond_failure(handler,ImportFailure(status,'COMPARISON_UNAVAILABLE','Chưa đọc được phép so sánh trong phạm vi được cấp quyền.','Kiểm tra kết nối, doanh nghiệp và lần chạy; không tạo lại model hoặc khóa.'))
    return True
