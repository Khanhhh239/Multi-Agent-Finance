"""Single definition of what an enterprise provides. The web interface renders forms and guides from this; the code
validates against it. Instructions describe where the enterprise exports each file itself; nothing connects to a bank
or to the tax portal on its behalf.
"""

PROFILE_FIELDS = [
    dict(key='tax_code', label='Mã số thuế', type='tax_code', required=True, example='0109999982',
         help='Mã số thuế 10 số (hoặc 13 số với chi nhánh) đúng như trên giấy chứng nhận đăng ký thuế.'),
    dict(key='legal_name', label='Tên doanh nghiệp', type='text', required=True, example='Công ty TNHH Vật liệu Xây dựng Minh An',
         help='Ghi đúng tên trên giấy đăng ký; dùng để kiểm tra hóa đơn ghi đúng người mua.'),
    dict(key='registered_address', label='Địa chỉ đăng ký', type='text', required=False,
         help='Địa chỉ trên giấy đăng ký thuế; dùng để kiểm tra địa chỉ người mua trên hóa đơn.'),
    dict(key='vat_method', label='Phương pháp tính thuế giá trị gia tăng', type='choice', required=True,
         choices=[['DEDUCTION', 'Khấu trừ'], ['DIRECT', 'Trực tiếp']], help='Doanh nghiệp khấu trừ thì các cảnh báo về khấu trừ thuế đầu vào mới áp dụng.'),
    dict(key='filing_period', label='Kỳ khai thuế giá trị gia tăng', type='choice', required=True,
         choices=[['MONTH', 'Theo tháng'], ['QUARTER', 'Theo quý']], help='Quyết định lịch hạn nộp tờ khai.'),
    dict(key='industry', label='Ngành nghề đăng ký', type='list', required=False, example='4663 Bán buôn vật liệu xây dựng',
         help='Dùng để gợi ý hàng hóa không khớp ngành nghề (chỉ gợi ý, người duyệt quyết định).'),
]

FILES = [
    dict(key='purchase_xml', label='Hóa đơn mua vào (XML)', folder='invoices/purchase', accept=['.xml', '.zip'], required=True,
         how=['Đăng nhập cổng hóa đơn điện tử của cơ quan thuế bằng tài khoản doanh nghiệp.',
              'Vào Tra cứu, chọn Tra cứu hóa đơn, chọn tab Hóa đơn mua vào, chọn khoảng ngày.',
              'Với từng hóa đơn chọn Xuất XML; hoặc tải tệp XML gốc từ đường dẫn tra cứu của người bán.',
              'Có thể nén nhiều tệp XML thành một tệp .zip rồi tải lên một lần.'],
         pitfalls=['Không mở rồi lưu lại tệp XML bằng chương trình khác: chữ ký số sẽ hỏng.',
                   'Tệp PDF không thay được XML; PDF chỉ là bản hiển thị.']),
    dict(key='sales_xml', label='Hóa đơn bán ra (XML)', folder='invoices/sales', accept=['.xml', '.zip'], required=False,
         how=['Xuất từ phần mềm hóa đơn điện tử doanh nghiệp đang dùng, hoặc tab Hóa đơn bán ra trên cổng hóa đơn điện tử.'], pitfalls=[]),
    dict(key='bank', label='Sao kê ngân hàng', folder='bank', accept=['.xlsx', '.csv', '.sta', '.mt940', '.txt'], required=False,
         how=['Đăng nhập ngân hàng điện tử doanh nghiệp, mở Tài khoản, chọn Sao kê hoặc Lịch sử giao dịch, chọn kỳ, Xuất Excel.',
              'Một số ngân hàng cung cấp sao kê định dạng MT940 (chuẩn SWIFT) cho phần mềm kế toán; tệp này được đọc trực tiếp.',
              'Lần đầu, hệ thống đoán cột ngày, số tiền ghi nợ, ghi có, nội dung; người dùng xác nhận và lưu thành mẫu cho ngân hàng đó.'],
         pitfalls=['Cần đủ cả kỳ của hóa đơn và vài tuần sau đó (trả chậm).',
                   'Không có sao kê thì mọi hóa đơn từ 5 triệu đồng sẽ hiện "chưa có chứng từ chuyển khoản" cho tới khi người duyệt xác nhận.']),
    dict(key='portal_list', label='Bảng kê hóa đơn mua vào từ cổng thuế', folder='portal', accept=['.csv', '.xlsx'], required=False,
         how=['Trên cổng hóa đơn điện tử, tra cứu hóa đơn mua vào theo kỳ, chọn Xuất Excel.'],
         pitfalls=['Tên cột có thể khác giữa các phiên bản cổng; khai lại tên cột trong phần cài đặt nếu hệ thống không nhận ra.']),
    dict(key='risk_list', label='Danh sách doanh nghiệp rủi ro (tùy chọn)', folder='', accept=['.csv'], required=False,
         how=['Tệp CSV có cột mã số thuế, lấy từ công văn đã công bố của cơ quan thuế; ghi ngày của danh sách.'], pitfalls=[]),
]

# Header synonyms used to suggest the column mapping of an unknown bank statement (folded, lower case).
BANK_SYNONYMS = {
    'date': ['ngay giao dich', 'ngay gd', 'ngay hach toan', 'ngay', 'posting date', 'transaction date', 'value date', 'date', 'ngay hieu luc'],
    'debit': ['so tien ghi no', 'ghi no', 'phat sinh no', 'no', 'debit', 'withdrawal', 'so tien rut', 'chi', 'tien ra'],
    'credit': ['so tien ghi co', 'ghi co', 'phat sinh co', 'co', 'credit', 'deposit', 'so tien gui', 'thu', 'tien vao'],
    'description': ['noi dung', 'dien giai', 'mo ta', 'noi dung giao dich', 'remark', 'description', 'details', 'narrative', 'transaction details'],
    'counterparty_account': ['so tai khoan doi ung', 'tai khoan doi ung', 'so tk doi ung', 'tk doi ung', 'beneficiary account', 'account no',
                             'so tai khoan nguoi nhan', 'counterparty account', 'so tai khoan thu huong', 'tai khoan thu huong', 'tk thu huong'],
    'counterparty_name': ['ten don vi doi ung', 'ten doi ung', 'don vi doi ung', 'ten tai khoan doi ung', 'beneficiary name', 'counterparty name',
                          'ten nguoi nhan', 'nguoi huong', 'ten don vi thu huong', 'don vi thu huong', 'ten nguoi thu huong', 'thu huong',
                          'ten tai khoan thu huong', 'ten doi tac'],
}


def guide() -> dict:
    return dict(profile=PROFILE_FIELDS, files=FILES)
