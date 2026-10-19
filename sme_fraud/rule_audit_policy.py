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
    'A3': 'Hiện chỉ chạy nhánh ≥3 khoản/30 ngày/tổng ≥hạn mức; chưa có nhánh ≥2 khoản/3 ngày/85% như A1. Chỉ gom liên kết mạnh TK/SĐT/đại diện; không gom địa chỉ đơn lẻ.',
    'A4': 'Mã dùng 30 ngày trượt, mô tả dùng tháng. Đếm cả khoản chi định kỳ/lương cận hạn mức; cần quyết định chính sách tháng lịch hay cửa sổ trượt.',
    'A5': 'Chỉ xét đuôi cao (>+2σ), không dùng độ lệch tuyệt đối. Nền được làm tròn VND rất thường xuyên; fallback công ty+loại có thể trộn các NCC khác quy mô.',
    'A6': 'Mã chỉ xét thanh toán cao hơn hóa đơn >1 VND, hóa đơn không chia hết 1.000; hẹp hơn mô tả làm tròn số lẻ. Cần nhãn hóa đơn/báo giá gốc và phí/khấu trừ hợp lệ.',
    'B1': 'Chỉ so TK thụ hưởng của vendor_payment với nhân viên, thiếu CCCD/mã ngân hàng và kiểm tra master trên các loại chi NCC khác. Bên liên quan công bố chỉ hạ điểm, không xóa hit.',
    'B2': 'Đường đi đồ thị có thể chỉ là TK trùng (chồng B1). Một đường đi đã được chấm 8 điểm; số trường trùng hiện đếm theo loại trường, chưa yêu cầu cùng một nhân viên.',
    'B3': 'Lịch sử “giao dịch đầu tiên” chỉ lưu vendor_payment; mua hàng ghi công nợ trước đó chưa được xét. Có giao nhận+hồ sơ đang được dùng làm ngoại lệ, chưa xác minh nội dung độc lập.',
    'B4': 'Dùng lịch sử trạng thái mô phỏng, không kết nối MST/ngành nghề. Phân biệt ngày phát hành và thời điểm công bố; thông tin công bố muộn không thể dùng để cảnh báo quá khứ.',
    'B5': 'Đối chiếu trực tiếp bank/phone/address, chưa gom người đại diện; cùng địa chỉ có 1 điểm. Logic hit và bằng chứng gần như E4, không phải hai chứng cứ độc lập.',
    'B6': 'Lịch sử tối thiểu 20 khoản chi, khoảng ngừng ≥180 ngày và khoản mới >P90; chưa xét hợp đồng mùa vụ/chi theo năm hoặc thông tin đổi tài khoản.',
    'B7': 'Giữ phiên bản đã quan sát kể cả đang chờ hiệu lực; chọn thay đổi có hiệu lực mới nhất, thống nhất với feature. Callback cần người duyệt độc lập cùng công ty đã biết. Chưa thêm điều kiện khoản chi lớn hoặc nguồn email BEC.',
    'C1': 'Xét giờ lập/duyệt, lễ minh họa và quyền vận hành thứ Bảy; chưa có lịch ca/ngày Chủ nhật riêng. Hit ngoài giờ không đồng nghĩa gian lận.',
    'C2': 'Có ngoại lệ trong quyền tự duyệt đã biết; phù hợp yêu cầu hard negatives, hẹp hơn mô tả chặn mọi tự duyệt. Chưa có ma trận SoD theo loại nghiệp vụ và ủy quyền có hiệu lực.',
    'C3': 'Dùng số tiền ≥50 triệu làm proxy cấp thẩm quyền cao; chưa xét vai trò, quyền duyệt thực tế hoặc tác vụ duyệt theo lô.',
    'C4': 'Chưa có implementation/nguồn lịch nghỉ theo ngày và log thao tác để đánh giá.',
    'D1': 'Chi-square chữ số đầu theo công ty/90 ngày, có lọc áp dụng và BH. Không có nhãn can thiệp phân phối cấp tập.',
    'D2': 'Dùng Chi-square chữ số thứ hai thay Z-statistic; ≥1.000 mẫu. Không có nhãn can thiệp phân phối cấp tập.',
    'D3': 'Kiểm tra hai chữ số đầu theo người lập và hạn mức đồng nhất, thêm BH; ít mẫu thường bị bỏ qua. Không được biến “có một dòng gian lận trong cửa sổ” thành nhãn cửa sổ gian lận.',
    'D4': 'So đuôi với baseline thực nghiệm quá khứ thay phân phối đều; hợp với nền VND tròn. Baseline bằng 0 đang không phát tín hiệu dù đuôi mới xuất hiện.',
    'D5': 'Dùng MAD chữ số đầu >0,015 sau lọc áp dụng; là chẩn đoán mô tả, không phải một kiểm định độc lập hay kết luận gian lận.',
    'D6': 'Hiện chỉ phân đoạn người lập, chưa có phòng ban/dự án. Các cửa sổ 90 ngày chồng nhau, không phải các thử nghiệm độc lập.',
    'E1': 'Có ngoại lệ từ xa, chấm công chưa quan sát và quyền chi nghỉ hưởng lương từ payroll_entitlements đã duyệt/as-of, đúng kỳ và số tiền. Tổng ngày nghỉ đơn lẻ không cấp ngoại lệ. Chưa hỗ trợ mọi khoản truy lĩnh/chi trả cuối cùng hoặc loại lao động.',
    'E2': 'Thiếu ngày nghỉ việc, kỳ công, loại khoản quyết toán cuối cùng; chưa có implementation đánh giá.',
    'E3': 'Dùng SequenceMatcher thay Levenshtein/Jaro-Winkler. Tên NCC giả lập chỉ khác số thứ tự có thể gây hit rộng; đây là rủi ro của bộ sinh, chưa chứng minh độ chính xác trên tên thật.',
    'E4': 'Cùng logic trùng bank/phone/address với B5. Nên đánh giá như kiểm tra chất lượng master, không tự coi mọi mã trùng là NCC ma.',
    'F1': 'txn_type=adjustment là proxy thủ công; mặc định trọng yếu=hạn mức người lập, chưa phải mức trọng yếu kế toán được duyệt. Xét ngày posted_at, chưa có lịch khóa sổ thực.',
    'F2': 'Chưa có log override/quyền đặc biệt/luồng phê duyệt chuẩn để đánh giá.',
    'F3': 'Không được dùng transaction_id ngẫu nhiên để tìm thiếu số chứng từ; thiếu sổ đăng ký số và nhật ký hủy.',
    'F4': 'Thiếu ghép thu tiền–hóa đơn, hạn thanh toán và giải trình công nợ; chưa thể quy chênh lệch thành doanh thu ảo.',
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
        return transaction['txn_type'] == 'adjustment'
    if rule == 'T1':
        return bool(transaction['advance_id'])
    if rule == 'T2':
        return transaction['txn_type'] == 'advance_writeoff'
    return False
