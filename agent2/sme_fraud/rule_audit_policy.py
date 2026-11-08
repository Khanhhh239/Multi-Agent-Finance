"""Declared audit scope and spec review; these annotations do not change rules."""

# Scenario coverage is a proxy from existing intent labels, NOT independent
# truth that a specific predicate/violation is present.
TARGETS = {
    'A1': ('split_payments', None), 'A2': ('split_payments', None),
    'A3': ('split_payments', {'multiple_recipients'}), 'A4': ('split_payments', None),
    'B1': ('ghost_vendor', {'employee_vendor_overlap'}),
    'B2': ('ghost_vendor', {'employee_vendor_overlap', 'new_shell_two_hop'}),
    'B3': ('ghost_vendor', {'new_shell_two_hop'}), 'B4': ('risky_invoice', None),
    'B5': ('split_payments', {'multiple_recipients'}),
    'C2': ('period_end_adjustment', None),
    'E1': ('ghost_vendor', {'ghost_employee_payroll'}),
    'E4': ('split_payments', {'multiple_recipients'}),
    'F1': ('period_end_adjustment', None),
    'P1': ('duplicate_payment', None), 'T1': ('long_outstanding_advance', None),
    'T2': ('long_outstanding_advance', {'opaque_writeoff'}),
}
NO_POSITIVE_TRUTH = {
    'A5': 'Chưa gán nhãn riêng cho số tiền tròn lệch baseline; sáu loại gian lận không phải nhãn của điều kiện này.',
    'A6': 'Chưa cài kịch bản nâng/làm tròn thanh toán vượt hóa đơn gốc.',
    'B6': 'Chưa cài NCC ngủ đông nhận khoản lớn; NCC nền hoạt động thường xuyên.',
    'B7': 'Có đổi TK hợp lệ, chưa có nhãn BEC/đổi TK trái phép.',
    'C1': 'Giờ muộn/cuối tuần là tín hiệu bối cảnh; không có nhãn riêng về vi phạm lịch làm việc.',
    'C3': 'Chưa cài nhãn phê duyệt siêu tốc trái quy trình.',
    'E3': 'Chưa cài nhãn cố ý lập mã NCC bằng tên biến thể; tên tổng hợp có chung tiền tố.',
}
SPEC_NOTES = {
    'A1': 'Cửa sổ 3 ngày, tổng ≥85% hạn mức hiện tại; chưa đối chiếu yêu cầu mua/đơn hàng/hợp đồng chung. Nhiều hóa đơn độc lập hợp lệ có thể bị gom.',
    'A2': 'Cửa sổ 30 ngày theo người lập+TK nhận. Ngoại lệ đối chiếu toàn cửa sổ A2, cùng hóa đơn/hợp đồng có bằng chứng và tổng toàn lịch sử không vượt trần. Hợp đồng cần supplier_payment_agreements đã duyệt/as-of; chưa tách mọi đơn mua hợp lệ độc lập.',
    'A3': 'Phase3 có nhánh ≥2 khoản/3 ngày/tổng ≥85% hạn mức và ≥3 khoản/30 ngày/tổng ≥hạn mức, qua ≥2 NCC. Chỉ gom TK có định danh ngân hàng/SĐT/đại diện, không gom địa chỉ đơn lẻ. Snapshot legacy thiếu nhánh ngắn.',
    'A4': 'Phase3 mặc định tháng lịch, theo người lập; rolling_30d là lựa chọn tường minh. Lương/chi định kỳ chỉ được loại khi có quyền chi tháng đã duyệt/as-of và chưa vượt tổng được duyệt; không loại theo nhãn mô phỏng.',
    'A5': 'Chỉ đuôi cao: mục tiêu khoản chi tăng bất thường; không xét trị tuyệt đối/đuôi thấp. Mặc định log/MAD theo cùng nghiệp vụ-thực thể, robust_z=3.5 đã chọn trên validation phase2; raw +2σ chỉ là cấu hình đối chiếu.',
    'A6': 'Mã chỉ xét thanh toán cao hơn hóa đơn >1 VND, hóa đơn không chia hết 1.000; hẹp hơn mô tả làm tròn số lẻ. Cần nhãn hóa đơn/báo giá gốc và phí/khấu trừ hợp lệ.',
    'B1': 'Phase3 tách đối chiếu toàn master đã biết khỏi chi NCC (Có 111/112, tiền/ngân hàng), gồm thuê/chi bán hàng. Có bank_code/recipient_bank_code/national_id thì dùng; số TK thực thiếu mã ngân hàng chỉ chẩn đoán. BANK_SYN có namespace riêng. Bên liên quan công bố hạ điểm, không xóa hit.',
    'B2': 'Đường đi đồ thị có thể chỉ là TK trùng (chồng B1). Một đường đi đã được chấm 8 điểm; số trường trùng hiện đếm theo loại trường, chưa yêu cầu cùng một nhân viên.',
    'B3': 'Phase3 dùng lần phát sinh nghiệp vụ tài chính gắn NCC đầu tiên trong lịch sử quan sát, gồm mua ghi công nợ trước khi trả tiền. Chưa có lịch sử trước đầu dataset. Ngoại lệ cần loại chứng từ và xác minh nội dung/as-of; số hồ sơ/giao nhận đơn lẻ không đủ.',
    'B4': 'Dùng lịch sử trạng thái mô phỏng, không kết nối MST/ngành nghề. Phân biệt ngày phát hành và thời điểm công bố; thông tin công bố muộn không thể dùng để cảnh báo quá khứ.',
    'B5': 'Đối chiếu trực tiếp bank/phone/address, chưa gom người đại diện; cùng địa chỉ có 1 điểm. Logic hit và bằng chứng gần như E4, không phải hai chứng cứ độc lập.',
    'B6': 'Lịch sử tối thiểu 20 khoản chi, khoảng ngừng ≥180 ngày và khoản mới >P90; chưa xét hợp đồng mùa vụ/chi theo năm hoặc thông tin đổi tài khoản.',
    'B7': 'Giữ phiên bản đã quan sát kể cả đang chờ hiệu lực; chọn thay đổi có hiệu lực mới nhất, thống nhất với feature. Callback cần người duyệt độc lập cùng công ty đã biết. Chưa thêm điều kiện khoản chi lớn hoặc nguồn email BEC.',
    'C1': 'Phase2/3 xét riêng giờ lập/duyệt theo operating_schedules đã duyệt/biết lúc thao tác, có lịch ca/cuối tuần. Thiếu nguồn thì dùng 08–19 và saturday_operations của công ty. Hit ngoài giờ là ngữ cảnh, cần bằng chứng độc lập để góp điểm.',
    'C2': 'Có ngoại lệ trong quyền tự duyệt đã biết; phù hợp yêu cầu hard negatives, hẹp hơn mô tả chặn mọi tự duyệt. Chưa có ma trận SoD theo loại nghiệp vụ và ủy quyền có hiệu lực.',
    'C3': 'Dùng số tiền ≥50 triệu làm proxy cấp thẩm quyền cao; chưa xét vai trò, quyền duyệt thực tế hoặc tác vụ duyệt theo lô.',
    'C4': 'Phase4 hỗ trợ leave_periods + system_actions và quyền làm việc có bằng chứng/as-of; chỉ maker/checker gắn giao dịch. Thiếu nguồn thực vẫn not_evaluable. Phê duyệt/actor đọc master đúng thời điểm, không dùng tổng ngày nghỉ tháng.',
    'D1': 'Chi-square chữ số đầu theo công ty/90 ngày, có lọc áp dụng và BH. Không có nhãn can thiệp phân phối cấp tập.',
    'D2': 'Dùng Chi-square chữ số thứ hai thay Z-statistic; ≥1.000 mẫu. Không có nhãn can thiệp phân phối cấp tập.',
    'D3': 'Definition phase4 thêm điều kiện số tiền thực cận hạn mức và BY cùng cutoff; legacy giữ BH/leading pairs. Có stress test đủ mẫu và nhãn can thiệp cửa sổ riêng. Không hạ min_rows hoặc dùng nhãn dòng làm nhãn cửa sổ.',
    'D4': 'So đuôi với baseline thực nghiệm quá khứ thay phân phối đều; hợp với nền VND tròn. Baseline bằng 0 đang không phát tín hiệu dù đuôi mới xuất hiện.',
    'D5': 'Dùng MAD chữ số đầu >0,015 sau lọc áp dụng; là chẩn đoán mô tả, không phải một kiểm định độc lập hay kết luận gian lận.',
    'D6': 'Definition phase4 có creator/department/project_id và BY, stress test đủ mẫu; legacy chỉ creator. Cửa sổ 90 ngày và phân đoạn chồng lặp có phụ thuộc; conformance không thay đánh giá SME thật.',
    'E1': 'Có ngoại lệ từ xa, chấm công chưa quan sát và quyền chi nghỉ hưởng lương từ payroll_entitlements đã duyệt/as-of, đúng kỳ và số tiền. Tổng ngày nghỉ đơn lẻ không cấp ngoại lệ. Chưa hỗ trợ mọi khoản truy lĩnh/chi trả cuối cùng hoặc loại lao động.',
    'E2': 'Phase4 có employment_events + payroll_settlements. Regular_salary cho kỳ bắt đầu sau ngày nghỉ, chưa rehire có hiệu lực: hard khi đủ nguồn. Final/backpay/severance/bonus đúng kỳ/số tiền được loại; thiếu nguồn/giao kỳ là information gap. Dataset SME gốc chưa có nguồn.',
    'E3': 'Dùng SequenceMatcher thay Levenshtein/Jaro-Winkler. Tên NCC giả lập chỉ khác số thứ tự có thể gây hit rộng; đây là rủi ro của bộ sinh, chưa chứng minh độ chính xác trên tên thật.',
    'E4': 'Cùng logic trùng bank/phone/address với B5. Nên đánh giá như kiểm tra chất lượng master, không tự coi mọi mã trùng là NCC ma.',
    'F1': 'Phase3 cần journal_audit_log (manual/entered_at), closing_periods đã duyệt và materiality_policies đã duyệt/as-of. Cửa sổ ≤5 ngày trước khóa thực, số tiền >trọng yếu. Proxy adjustment/cuối tháng/hạn mức chỉ chẩn đoán 0 điểm. Dataset gốc thiếu cả ba nguồn.',
    'F2': 'Phase4 đối chiếu override_events/workflow_policies theo control, role/hạn mức tại thao tác và phê duyệt lịch sử. Thiếu policy là information gap; ngoại lệ một control không miễn control khác. Chưa đủ ma trận duyệt chính sách thực tế.',
    'F3': 'Phase4 đọc series/register/cancellations: duplicate chứng từ thật là context; gap trên dải đóng có coverage hủy là source finding 0 điểm. Không dùng transaction_id. Thiếu nguồn thực không tính độ chính xác predicate.',
    'F4': 'Phase4 ghép invoice/customer/receipt thực/verified allocation/coverage/giải trình. >60 ngày từ due_at chưa giải trình là source finding thu hồi nợ, 0 điểm; thiếu/sai/overallocated nguồn là information gap. Không kết luận doanh thu giả.',
    'P1': 'Phụ lục ngoài 31: khóa công ty+NCC+số hóa đơn, có đối chiếu tổng trả; thiếu ký hiệu/mẫu/năm hóa đơn cho dữ liệu thực.',
    'T1': 'Phụ lục ngoài 31: dư nợ/hạn đã biết, không dùng quyết toán tương lai. Quá hạn có thể là chậm xử lý hợp lệ.',
    'T2': 'Phụ lục ngoài 31: thiếu evidence_on_file tại xóa nợ; chưa kiểm tra nội dung, thẩm quyền và chất lượng hồ sơ.',
}


def target_match(rule, label):
    if rule not in TARGETS or not int(label['is_fraud']):
        return False
    family, variants = TARGETS[rule]
    return label['fraud_type'] == family and (variants is None or label['variant'] in variants)


def eligible(rule, transaction):
    if rule in {'A1', 'A2', 'A3', 'A6', 'B6', 'B7', 'P1'}:
        return transaction['txn_type'] == 'vendor_payment'
    if rule == 'A4':
        return (int(transaction['is_financial_entry']) and transaction['payment_channel'] in {'bank', 'cash'}
                and transaction['txn_type'] != 'customer_receipt')
    if rule == 'A5':
        return bool(int(transaction['is_financial_entry']))
    if rule in {'B1', 'B2', 'B3', 'B4', 'B5', 'E3', 'E4'}:
        return bool(transaction['vendor_id'])
    if rule in {'C1', 'C2', 'C3'}:
        return bool(transaction['creator_id'] and transaction['approver_id'])
    if rule == 'E1':
        return transaction['txn_type'] == 'payroll'
    if rule == 'F1':
        return bool(int(transaction['is_financial_entry']))
    if rule == 'T1':
        return bool(transaction['advance_id'])
    if rule == 'T2':
        return transaction['txn_type'] == 'advance_writeoff'
    return False
