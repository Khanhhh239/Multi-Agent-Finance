"""Allowlisted business views over four existing adapters; no scoring thresholds."""
from collections import Counter
from .snapshot_features import utc

NAMES=dict(rules='Luật nghiệp vụ',statistics='So sánh thống kê',graph='Quan hệ đối tượng',ml='Phân tích bất thường')
REASONS={
    'transaction_not_visible_at_as_of':'Giao dịch chưa phát sinh hoặc chưa được biết tại mốc phân tích đã khóa.',
    'binding_missing':'Chưa chỉ định phiên bản đã fit cho doanh nghiệp này.',
    'binding_invalid':'Cấu hình phiên bản phân tích chưa hợp lệ; người quản lý cần kiểm tra.',
    'artifact_not_pinned':'Chưa chỉ định phiên bản đã fit cho nhánh phân tích này.',
    'artifact_missing':'Không tìm thấy phiên bản đã fit trong phạm vi doanh nghiệp.',
    'artifact_invalid':'Phiên bản lưu không còn nguyên vẹn; chưa thể sử dụng để chấm.',
    'artifact_incompatible':'Phiên bản đã fit không tương thích với bộ dữ liệu hoặc phiên bản xử lý hiện tại.',
    'artifact_from_future':'Dữ liệu đối chiếu của phiên bản chưa có trước giao dịch này.',
    'artifact_training_overlap':'Giao dịch từng thuộc dữ liệu huấn luyện hoặc đối chiếu; không trình bày như kết quả ngoài mẫu.',
    'before_evaluation_period':'Giao dịch nằm trước kỳ đánh giá của phiên bản đã fit.',
    'artifact_not_yet_created':'Phiên bản phân tích chưa được tạo tại thời điểm giao dịch.',
    'model_store_unconfigured':'Chưa cấu hình kho phiên bản đã fit để đọc kết quả.',
    'model_store_unavailable':'Kho phiên bản đã fit tạm thời chưa đọc được.',
    'features_missing':'Chưa đủ nguồn cho các đầu vào cần dùng; không tự điền số 0.',
    'features_all_missing':'Các đầu vào cần dùng đều chưa có nguồn khả dụng.',
    'scoring_failed':'Phiên bản phân tích chưa trả được kết quả hợp lệ.',
}
NODE_KINDS=dict(vendor='Nhà cung cấp',employee='Nhân viên',bank_account='Tài khoản ngân hàng',address='Địa chỉ',phone='Số điện thoại',tax_code='Mã số thuế',national_id='Giấy tờ định danh')
FINDING_NAMES=dict(vendors_shared_bank_account='Các nhà cung cấp cùng tài khoản ngân hàng',vendor_employee_shared_bank_account='Nhà cung cấp và nhân viên cùng tài khoản ngân hàng',vendor_employee_shared_phone='Nhà cung cấp và nhân viên cùng số điện thoại',vendors_shared_address='Các nhà cung cấp cùng địa chỉ — liên kết cần thêm bối cảnh')


def _method_view(method,label):
    reason=None if method['available'] else REASONS.get((method['reason'] or {}).get('code'),'Chưa đủ nguồn hoặc phiên bản phù hợp để thực hiện phân tích.')
    position=round(float(method['score'])*100,2) if method['available'] else None
    if position is not None and not 0<=position<=100:raise ValueError('Invalid relative position')
    missing=method.get('missing_features',[])
    sources=set()
    for field in missing:
        if 'invoice' in field or 'allocation' in field:sources.add('Hóa đơn hoặc phân bổ thanh toán')
        elif 'employee' in field or 'creator' in field or 'approval' in field:sources.add('Nhân viên hoặc phê duyệt')
        elif 'document' in field:sources.add('Chứng từ liên quan')
        elif 'prior' in field or 'history' in field:sources.add('Lịch sử giao dịch trước kỳ')
        elif 'journal' in field:sources.add('Bản ghi kế toán')
        else:sources.add('Nguồn cho một số đầu vào phân tích')
    return dict(label=label,status='available' if method['available'] else 'unavailable',available=method['available'],
        relative_position=position,reason=reason,missing_sources=sorted(sources),
        inputs_adjusted=bool(method.get('details',{}).get('imputed_features')),
        retrospective=method.get('details',{}).get('evaluation_mode')=='backtest' if method['available'] else None)


def quantitative_branch(kind,methods):
    results=[_method_view(method,('Đối chiếu lịch sử' if kind=='statistics' else 'Phương án doanh nghiệp '+str(i+1))) for i,method in enumerate(methods)]
    count=sum(r['available'] for r in results)
    status='available' if results and count==len(results) else 'partial' if count else 'unavailable'
    return dict(name=NAMES[kind],status=status,available=status=='available',
        message='Vị trí tương đối so với tập đối chiếu; không phải xác suất sai phạm và chưa tự tạo cảnh báo.' if count else (results[0]['reason'] if results else 'Chưa chỉ định phiên bản đã fit cho doanh nghiệp này.'),results=results)


def rule_branch(results):
    counts=Counter(r['status'] for r in results['rules']);evaluated=counts['evaluated_hit']+counts['evaluated_no_hit']
    return dict(name=NAMES['rules'],status='partial' if evaluated else 'unavailable',available=False,
        evaluated_count=evaluated,unavailable_count=counts['unavailable'],not_applicable_count=counts['not_applicable'],total_count=len(results['rules']),
        message='Đã chạy các đối chiếu đủ nguồn. Những luật thiếu nguồn hoặc chưa có bộ đánh giá vẫn chưa khả dụng; chưa tính điểm tổng toàn bộ luật.')


def graph_branch(graph,public_ref):
    if not graph['available']:
        return dict(name=NAMES['graph'],status='unavailable',available=False,message='Chưa có đối tượng hoặc nguồn quan hệ khả dụng tại thời điểm giao dịch.',nodes=[],links=[],findings=[],missing_sources=[])
    nodes=[]
    for n in graph['nodes']:
        item=dict(id=n['id'],kind=NODE_KINDS.get(n['type'],'Đối tượng liên quan'),label=n['label'])
        if 'entity_id' in n:item['record_id']=n['entity_id']
        nodes.append(item)
    refs={(r['table'],r['record_id']):r for r in graph['evidence_refs']}
    links=[]
    for link in graph['links']:
        evidence=link['evidence'];ref=refs.get((evidence['source_table'],evidence['source_id']))
        if ref is None:raise ValueError('Graph edge without canonical source')
        links.append(dict(id=link['id'],source=link['source'],target=link['target'],relation=NODE_KINDS.get(link['relation'],'Quan hệ'),
            context_only=link['strength']!='identity_match',evidence=public_ref(ref['table'],ref)))
    ids={n['id'] for n in nodes};edge_ids={l['id'] for l in links}
    findings=[]
    for finding in graph['findings']:
        if not set(finding['entity_nodes'])<=ids or not set(finding['evidence_edge_ids'])<=edge_ids:raise ValueError('Incomplete graph finding')
        findings.append(dict(id=finding['id'],description=FINDING_NAMES.get(finding['type'],'Quan hệ cần đối chiếu thêm'),
            entity_nodes=finding['entity_nodes'],attribute_node=finding['attribute_node'],evidence_link_ids=finding['evidence_edge_ids'],
            context_only=True))
    gaps=[dict(source=NODE_KINDS.get(g.get('field'),'Nguồn liên quan'),record_id=g['entity_id'],action='Bổ sung định danh nguồn có thời điểm rõ ràng; không tự ghép các đối tượng khi thiếu căn cứ.') for g in graph['information_gaps']]
    return dict(name=NAMES['graph'],status='partial' if gaps else 'available',available=not gaps,
        message='Liên kết từ các bản ghi đã biết; không xác nhận sai phạm, không cộng thành điểm rủi ro.',nodes=nodes,links=links,findings=findings,missing_sources=gaps)


def project_branches(row,loaded,public_ref):
    rules=row['methods']['rules']['details']['rule_results']
    ml=[row['methods'][m] for m in sorted(loaded['selected']['ml_artifacts'])]
    result=dict(rules=rule_branch(rules),statistics=quantitative_branch('statistics',[row['methods']['robust_z']]),
        graph=graph_branch(row['graph'],public_ref),ml=quantitative_branch('ml',ml))
    if not ml and loaded['binding']['error']:result['ml']['message']=REASONS[loaded['binding']['error']]
    return result


def branch_summary(rows):
    return {key:dict(name=name,**{status:sum(r['branches'][key]['status']==status for r in rows) for status in ('available','partial','unavailable')}) for key,name in NAMES.items()}


def source_limits(data,company,as_of):
    """Disclosure only, using records visible at the selected global ceiling."""
    from .imports import analysis_limits
    known={k:([r for r in rows if r['company_id']==company and max(utc(r['effective_at']),utc(r['observed_at']))<=utc(as_of)] if isinstance(rows,list) else rows) for k,rows in data.items()}
    labels=dict(P1_INPUT_UNAVAILABLE='Thanh toán hóa đơn',DOCUMENT_BASIS_MISSING='Chứng từ gốc',BANK_HISTORY_MISSING='Lịch sử tài khoản nhà cung cấp',INVOICE_LINK_MISSING='Liên kết hóa đơn',APPROVAL_BASIS_MISSING='Phê duyệt khoản chi')
    result=[]
    for limit in analysis_limits(known,company):
        if limit['code']=='P1_INPUT_UNAVAILABLE':message='Chưa đủ kênh thanh toán, liên kết hoặc phạm vi lịch sử để đối chiếu một số giao dịch.';action='Bổ sung nguồn kênh thanh toán và phân bổ–hóa đơn, phạm vi lịch sử đã khai báo; không điền 0 cho lịch sử thiếu.'
        else:message=limit['message'];action=limit['action']
        result.append(dict(name=labels.get(limit['code'],'Nguồn liên quan'),message=message,action=action,affected_count=limit['affected_count']))
    return result
