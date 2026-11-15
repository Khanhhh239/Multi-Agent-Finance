"""Review only completed HE results, using server-pinned evidence and run IDs."""
import re
import sqlite3
from urllib.parse import urlsplit
from finance_input.json_io import loads
from .auth import AuthError
from .import_files import ImportFailure,canonical,digest,fail
from .snapshot_features import build_from_snapshot,utc
from .validation_api import authorize_request,read_json,respond_failure

ROUTE=re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/he/jobs/(herun_[a-f0-9]{32})/reviews(?:/(rvw_[a-f0-9]{64})/(start|heartbeat|save|attachments)(?:/(att_[a-f0-9]{64}))?)?\Z')


def display_record(value):
    if isinstance(value,dict):return {k:str(v) if k.endswith('_vnd') and type(v) is int else display_record(v) for k,v in value.items()}
    if isinstance(value,list):return [display_record(v) for v in value]
    return value


def summarize(cases):
    reviews=[c['review'] for c in cases if c['review']['feedback'] is not None]
    feedback=[r['feedback'] for r in reviews]
    useful=[f for f in feedback if f['usefulness'] in {'yes','no'}]
    return dict(total_cases=len(cases),reviewed_cases=len(reviews),pending_cases=len(cases)-len(reviews),
        outcomes={key:sum(f['outcome']==key for f in feedback) for key in ('confirmed_risk','legitimate','inconclusive')},
        usefulness_assessed=len(useful),usefulness_yes=sum(f['usefulness']=='yes' for f in useful),
        declared_useful_fraction=sum(f['usefulness']=='yes' for f in useful)/len(useful) if useful else None,
        connected_review_seconds=round(sum(r['active_seconds'] for r in reviews),3) if reviews else None,
        accuracy=None,incremental_ml_benefit=None,training_eligible=False,
        limitation='Declared feedback on this run only; no verified labels or same-budget rules baseline.')


def _rule_snapshot_cases_for(store,scope,result,review_store,recheck):
    sid=result['snapshot_id'];manifest=store.get_snapshot(scope,sid,recheck);raw=store.get_snapshot(scope,sid,recheck,data=True)
    if digest(raw)!=manifest['data_checksum']:fail(503,'REVIEW_EVIDENCE_BINDING','Snapshot không khớp checksum đã khóa.','Kiểm tra kho snapshot.')
    data=loads(raw);source=data['source'];tables=source['tables'];as_of=source['as_of'];company=next(iter(scope.company_ids))
    id_fields={'transactions':'transaction_id','vendors':'vendor_id','employees':'employee_id','transaction_documents':'document_id','approval_authorities':'authority_id','approval_authority_coverage':'coverage_id'}
    by_key={}
    for tname,id_key in id_fields.items():
        for rec in tables.get(tname,[]):
            by_key[tname,rec[id_key],rec['observed_at']]=rec
    cases=[]
    for row in result['rows']:
        rid=row['record_id'];rev=int(row.get('revision',1));known=bool(row.get('known_at_cutoff',True))
        event_at=row.get('posted_at') or as_of;refs={}
        for branch in row.get('branches',{}).values():
            for ref in branch.get('evidence_refs',[]):
                rec=by_key.get((ref['table'],ref['record_id'],ref['observed_at']))
                if rec is None or rec.get('company_id')!=company:
                    fail(503,'REVIEW_EVIDENCE_BINDING','Căn cứ chưa khớp nguồn snapshot của lần chạy.','Kiểm tra bản nguồn và phiên bản phân tích; không thêm căn cứ từ ngoài snapshot.')
                eff=rec.get('posted_at') or rec.get('recorded_at') or rec['observed_at']
                if utc(rec['observed_at'])>utc(as_of) or utc(eff)>utc(event_at):
                    fail(503,'REVIEW_EVIDENCE_TIME','Căn cứ chưa khả dụng tại thời điểm giao dịch đang rà.','Đối chiếu thời điểm nguồn; không dùng chứng từ đến muộn để kết luận cho quá khứ.')
                refs[ref['table'],ref['record_id'],ref['observed_at']]=(id_fields[ref['table']],rec)
        items=[]
        for (table,rec_id,_),(id_key,rec) in sorted(refs.items()):
            view=display_record(rec);view.setdefault('record_id',rec[id_key]);view.setdefault('effective_at',rec.get('posted_at') or rec.get('recorded_at') or rec['observed_at'])
            items.append(dict(evidence_id='ev_'+digest(canonical(rec)),table=table,record=view,simulated=bool(rec.get('is_simulated')),original_verified=False))
        groups=row.get('groups',{});case_id=review_store.case_id(scope,result['run_id'],rid,rev)
        hit_notes=[g['explanation'] for g in groups.values() if g.get('available') and g.get('matched') and g.get('explanation')]
        unavail_notes=[g['explanation'] for g in groups.values() if not g.get('available') and g.get('status')!='not_applicable' and g.get('explanation')]
        if hit_notes:why=' '.join(hit_notes)+' Cần đối chiếu chứng từ gốc và phần còn thiếu trước khi kết luận.'
        elif not known:why='Giao dịch chưa được ghi nhận/hạch toán tại thời điểm cắt dữ liệu.'
        elif any(g.get('available') for g in groups.values()):why='Các nhóm luật đã bật HE (P1, C3, B1, B5/E4) đã chạy kiểm tra trên bản mã và chưa thấy tín hiệu sai lệch tại các nhóm khả dụng.'
        else:why='Chưa đủ nguồn hoặc vượt miền mạch HE cho các nhóm đang bật. Có thể bổ sung nguồn trước khi kết luận.'
        limits=[g['reason'] for g in groups.values() if not g.get('available') and g.get('reason')]
        if row.get('branches',{}).get('ml',{}).get('reason'):limits.append(row['branches']['ml']['reason'])
        cases.append(dict(case_id=case_id,record_id=rid,revision=rev,amount_vnd=str(row['amount_vnd'] if row.get('amount_vnd') is not None else 0),
            currency=row.get('currency','VND'),event_at=event_at,as_of=as_of,
            question='Khoản tiền này có đúng đối tượng, nghĩa vụ, phê duyệt và thời điểm được phép không?',
            why=why,next_step='Đối chiếu hóa đơn, phê duyệt, tài khoản nhận tiền và NCC dùng chung định danh; thiếu nguồn thì ghi rõ phần cần bổ sung.',
            evidence=items,analysis_limits=sorted(set(limits)),extra_notes=unavail_notes,review=review_store.get(scope,case_id)))
    return cases


def cases_for(store,scope,result,review_store,recheck):
    if result.get('version')=='he-rule-snapshot-groups-result/1.0.0':
        return _rule_snapshot_cases_for(store,scope,result,review_store,recheck)
    sid=result['snapshot_id'];raw=loads(store.get_snapshot(scope,sid,recheck,data=True))
    frame=build_from_snapshot(store,scope,sid,result['as_of'],recheck)
    sources={(table,r['record_id'],r['revision']):r for table,rows in raw.items() if isinstance(rows,list) for r in rows}
    provenance={(r['record_id'],r['revision']):(r,e) for r,e in zip(frame['rows'],frame['evidence'])}
    cases=[]
    for scored in result['rows']:
        key=scored['record_id'],scored['revision'];meta,evidence=provenance[key]
        tx=sources['transactions',*key];items=[];refs={}
        # Feature provenance alone omits some rule-only dependencies, notably
        # coverage declarations and concurrent peer allocations. Retain the
        # evidence pinned in the completed result as well, never client refs.
        linked=list(evidence['records'])
        for branch in scored.get('branches',{}).values():linked.extend(branch.get('evidence_refs',[]))
        for ref in linked:
            identity=ref['table'],ref['record_id'],ref['revision']
            source=sources.get(identity)
            if source is None or (source['tenant_id'],source['company_id'])!=(scope.tenant_id,next(iter(scope.company_ids))):
                fail(503,'REVIEW_EVIDENCE_BINDING','Căn cứ chưa khớp nguồn snapshot của lần chạy.','Kiểm tra bản nguồn và phiên bản phân tích; không thêm căn cứ từ ngoài snapshot.')
            if utc(source['observed_at'])>utc(meta['as_of']) or utc(source['effective_at'])>utc(meta['event_at']):
                fail(503,'REVIEW_EVIDENCE_TIME','Căn cứ chưa khả dụng tại thời điểm giao dịch đang rà.','Đối chiếu thời điểm nguồn; không dùng chứng từ đến muộn để kết luận cho quá khứ.')
            if any(name in ref and ref[name]!=source[name] for name in ('observed_at','effective_at')):
                fail(503,'REVIEW_EVIDENCE_BINDING','Mốc thời gian căn cứ không khớp bản nguồn đã khóa.','Kiểm tra đúng lần chạy và snapshot; không tự sửa thời điểm nguồn.')
            refs[identity]=source
        for (table,_,_),source in sorted(refs.items()):
            items.append(dict(evidence_id='ev_'+digest(canonical(source)),table=table,record=display_record(source),
                simulated=bool(source['source']['is_simulated']),original_verified=bool(table=='supporting_documents' and source.get('source_kind')=='original' and not source['source']['is_simulated'] and source.get('verification_status')=='verified')))
        case_id=review_store.case_id(scope,result['run_id'],*key)
        branch=scored.get('branches',{}).get('rules',{});hit=next((r for r in branch.get('invoice_checks',[]) if r.get('matched')),None)
        why=('Nguồn cho thấy tổng thanh toán lũy kế '+str(hit['cumulative_paid_vnd'])+' VND so với nghĩa vụ '+str(hit['invoice_gross_vnd'])+' VND. Cần đối chiếu hóa đơn và các khoản trả liên quan trước khi kết luận.' if hit else
             'Các nhánh có đủ nguồn đã được phân tích. Cần đối chiếu căn cứ và phần còn thiếu; điểm không xác nhận sai phạm.' if any(b.get('available') for b in scored.get('branches',{}).values()) else
             'Model phát hiện mức bất thường tương đối; cần đối chiếu tài liệu trước khi kết luận.' if scored['available'] else
             'Chưa có điểm khả dụng. Có thể rà nguồn và yêu cầu bổ sung; không coi đây là một cảnh báo ML.')
        cases.append(dict(case_id=case_id,record_id=key[0],revision=key[1],amount_vnd=str(tx['amount_vnd']),currency=tx['currency'],event_at=meta['event_at'],as_of=meta['as_of'],
            question='Khoản tiền này có đúng đối tượng, nghĩa vụ, số tiền và thời điểm được phép không?',
            why=why,
            next_step='Đối chiếu hóa đơn, phê duyệt và chứng từ thanh toán; thiếu tài liệu thì chọn Chưa đủ căn cứ.',
            evidence=items,analysis_limits=evidence['missing_reasons'],review=review_store.get(scope,case_id)))
    return cases


def handle_reviews(handler,authorizer,snapshots,backend,reviews,method):
    match=ROUTE.fullmatch(urlsplit(handler.path).path)
    if not match:return False
    # The base JSON/import backend keeps working without optional HE packages.
    ServiceError=type('DisabledHEError',(Exception,),{})
    try:
        company,job,case_id,action,attachment_id=match.groups();scope,recheck=authorize_request(handler,authorizer,company)
        if backend is None or reviews is None or snapshots is None:
            fail(503,'REVIEWS_NOT_CONFIGURED','Kho phiếu rà chưa được cấu hình.','Bật node doanh nghiệp có khóa lưu trữ được bảo vệ.')
        from experiments.he_inference.http_common import ServiceError
        header=handler.headers.get_all('Authorization',[None])[0]
        status,result=backend.node.jobs.result(company,header,job)
        if status!=200:fail(409,'REVIEW_RESULT_REQUIRED','Lần phân tích chưa có kết quả hoàn tất.','Chờ phân tích xong rồi mở phiếu rà.')
        if isinstance(reviews,dict):reviews=reviews['current' if result.get('version') in ('he-four-branch-result/1.0.0','he-rule-snapshot-groups-result/1.0.0') else 'legacy']
        cases=cases_for(snapshots,scope,result,reviews,recheck)
        if not case_id and method=='GET':
            value=dict(version='enterprise-review-packet/1.0.0',run_id=job,company_id=company,snapshot_id=result['snapshot_id'],as_of=result['as_of'],training_eligible=False,identity_basis='Portal workspace actor; not independently verified human',timing_basis='server_connected_active_time',summary=summarize(cases),cases=cases)
        else:
            case=next((c for c in cases if c['case_id']==case_id),None)
            if case is None:fail(404,'REVIEW_NOT_FOUND','Không có phiếu trong lần chạy này.','Mở đúng lần chạy và doanh nghiệp.')
            if method=='GET' and action=='attachments' and attachment_id:
                value=reviews.attachment(scope,case_id,attachment_id)
                if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
                handler.respond(200,value);return True
            if method!='POST' or not action or attachment_id:fail(405,'METHOD_NOT_ALLOWED','Thao tác phiếu không hợp lệ.','Dùng các nút trên phiếu rà.')
            body=read_json(handler)
            fields={'start':set(),'heartbeat':{'lease'},'save':{'lease','expected_revision','request_id','feedback'},'attachments':{'name','content'}}[action]
            if not isinstance(body,dict) or set(body)!=fields:fail(400,'REVIEW_REQUEST','Nội dung yêu cầu không hợp lệ.','Tải lại phiếu rồi thử lại.')
            if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
            if action=='start':value=reviews.start(scope,case_id)
            elif action=='heartbeat':value=reviews.heartbeat(scope,case_id,body['lease'])
            elif action=='attachments':value=dict(attachment_id=reviews.attach(scope,case_id,body['name'],body['content']),original_verified=False)
            else:value=reviews.save(scope,case_id,body['expected_revision'],body['feedback'],{e['evidence_id'] for e in case['evidence']},body['lease'],body['request_id'])
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
        handler.respond(200,value)
    except (AuthError,ImportFailure) as error:respond_failure(handler,error)
    except ServiceError as error:
        status=error.status if error.status in (400,401,403,404,409,413,422,429,503) else 503
        respond_failure(handler,ImportFailure(status,'REVIEW_RUN_UNAVAILABLE','Không có lần chạy khả dụng trong phạm vi được phép.','Mở đúng doanh nghiệp và lần phân tích đã hoàn tất.'))
    except (OSError,sqlite3.Error):respond_failure(handler,ImportFailure(503,'REVIEW_STORAGE','Kho phiếu rà tạm thời không sẵn sàng.','Giữ nội dung và gửi lại cùng mã yêu cầu.'))
    except Exception:respond_failure(handler,ImportFailure(503,'REVIEW_INTEGRITY','Chưa thể đọc phiếu hoặc kiểm tra căn cứ.','Kiểm tra snapshot, khóa và phiên bản dịch vụ; không ghi đè dữ liệu cũ.'))
    return True
