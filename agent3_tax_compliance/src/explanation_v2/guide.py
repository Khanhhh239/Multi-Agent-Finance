"""Plain-language observations, derived only from the pinned CFR; no tax advice."""
from ..quality.completeness import flatten
from .contracts import UserGuide,GuideAction,Context,Fact

LABELS={'invoice.number':'số hóa đơn','invoice.series':'ký hiệu','invoice.issue_date':'ngày lập',
    'currency':'loại tiền','totals.net':'tổng trước thuế','totals.vat':'tổng thuế','totals.gross':'tổng thanh toán',
    **{'parties.'+p+'.'+f:label+' '+who for p,who in (('seller','người bán'),('buyer','người mua')) for f,label in (('name','tên'),('tax_id','MST'),('address','địa chỉ'))}}
ITEM_LABELS={'description':'tên hàng','quantity':'số lượng','unit_price':'đơn giá','net':'tiền trước thuế','vat_treatment':'nhóm thuế','vat_rate':'thuế suất'}


def label(record,path):
    if path.startswith('items.'):
        _,iid,field=path.split('.')
        item=next(i for i in record.items if i.item_id==iid)
        return f'dòng {item.line_number or 1}: '+ITEM_LABELS.get(field,field)
    return LABELS.get(path,path)


def build_guide(record):
    fields={p:f for p,f in flatten(record).items() if p in LABELS or (p.startswith('items.') and p.split('.')[-1] in ITEM_LABELS)}
    present=sum(f.status=='PRESENT' for f in fields.values());confirmed=sum(f.status=='PRESENT' and f.confidence_basis=='HUMAN_CONFIRMED' for f in fields.values())
    missing=[label(record,p) for p,f in fields.items() if f.status=='MISSING']
    ambiguous=[label(record,p) for p,f in fields.items() if f.status=='AMBIGUOUS']
    issues=[];actions=[];cards=[]
    unresolved=tuple(p for p,f in fields.items() if f.status in ('MISSING','AMBIGUOUS'))
    if unresolved:
        cards.append(GuideAction(title='Sửa các trường còn thiếu hoặc chưa rõ',
            reason='Những trường này chưa có một giá trị đủ căn cứ trong bản dữ liệu đã lưu.',
            steps=('Mở Xem nguồn để đối chiếu hóa đơn gốc.','Thử đọc lại vùng; nếu vẫn sai, nhập đúng nội dung trên chứng từ rồi lưu.'),
            target='data',field_paths=unresolved[:8]))
    if missing:issues.append('Chưa đọc được: '+', '.join(missing[:5])+(' và các trường khác.' if len(missing)>5 else '.'))
    if ambiguous:issues.append('Cần chọn lại sau đối chiếu: '+', '.join(ambiguous[:5])+'.')
    if not record.items:
        issues.append('Chưa trích được dòng hàng; chưa thể xem là hóa đơn không có hàng hóa/dịch vụ.')
        actions.append('Đối chiếu bảng hàng trên ảnh gốc; thử trích xuất lại. Nếu vẫn thiếu, chọn Bổ sung dòng hàng, đánh dấu vùng nguồn rồi lưu.')
        cards.append(GuideAction(title='Bổ sung bảng hàng bị bỏ sót',reason='Bản đã lưu chưa có dòng hàng; điều này không chứng minh hóa đơn không có hàng hóa/dịch vụ.',
            steps=('Đối chiếu toàn bộ bảng và các trang gốc.','Chọn Bổ sung dòng hàng, nhập phần được in và chọn vùng nguồn.','Chỉ xác nhận đủ dòng sau khi lưu và kiểm tra lại.'),target='data'))
    elif record.item_discovery_status!='COMPLETE':
        issues.append('Chưa xác nhận đã đọc đủ tất cả dòng hàng và trang.')
        actions.append('Xem tất cả các trang và đối chiếu đủ dòng hàng trước khi xác nhận hoàn tất.')
        cards.append(GuideAction(title='Xác nhận độ đầy đủ của bảng',reason='Số dòng đang hiển thị chưa được xác nhận bao phủ toàn bộ hóa đơn.',
            steps=('Xem từng trang và đối chiếu từng dòng.','Bổ sung dòng bị thiếu hoặc xóa dòng nhận nhầm.','Lưu xong rồi xác nhận đủ dòng/trang.'),target='data'))
    if missing or ambiguous:actions.append('Mở Xem nguồn ở các trường cần kiểm tra, sửa theo chứng từ gốc rồi lưu.')
    if present>confirmed:actions.append('Đối chiếu cả những ô đã được điền; có chữ không đồng nghĩa đã đúng.')
    if not actions:actions.append('Xem kết quả kiểm tra của đúng bản đã lưu và phần hồ sơ bổ sung còn yêu cầu.')
    if not cards:cards.append(GuideAction(title='Tiếp tục hồ sơ và kiểm tra bản đã lưu',reason='Không ghi nhận trường trống hoặc mơ hồ; vẫn cần căn cứ nghiệp vụ để kiểm tra thuế.',
        steps=('Bổ sung các tài liệu bạn thực sự đã đối chiếu.','Chạy Kiểm tra thuế trên bản đã lưu và xem các yêu cầu còn thiếu.'),target='business'))
    return UserGuide(read_summary=f'Đã trích được {present} trường và {len(record.items)} dòng hàng; {confirmed} trường đã được người dùng xác nhận.',
        missing_items=tuple(issues or ('Chưa ghi nhận trường trống hoặc mơ hồ trong dữ liệu đang xét.',)),
        next_steps=tuple(actions),actions=tuple(cards),warning='Đây là tình trạng dữ liệu đã lưu, chưa chứng minh hóa đơn hợp lệ hoặc đủ điều kiện khấu trừ thuế.')


def data_context(report,guide):
    ref='evaluation:'+report.evaluation_id
    texts=[('summary',guide.read_summary),('scope','Chỉ giải thích dữ liệu của bản đã lưu; chưa diễn giải kết quả thuế vì thiếu căn cứ phù hợp.'),
        ('coverage','Chất lượng được mô tả theo trường và dòng hàng; không phải độ chính xác OCR đã được đo trên tập độc lập.'),
        ('notice-data',' '.join(guide.missing_items)),('notice-scope',guide.warning),('action-data',' '.join(guide.next_steps))]
    return Context(evaluation_id=report.evaluation_id,record_revision=report.record_revision,record_sha256=report.record_sha256,
        excerpts=(),facts=tuple(Fact(fact_id=i,variants=(t,),refs=(ref,)) for i,t in texts))
