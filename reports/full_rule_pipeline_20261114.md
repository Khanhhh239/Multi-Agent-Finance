# Trạng thái pipeline 35 luật — 14/11/2026

Đã nối đủ 35 luật giữ lại vào **nhập → kiểm tra → lưu snapshot → phân tích →
xem kết quả** qua profile nguồn `agent2-rule-snapshot/1.0.0` tại node doanh
nghiệp. Không cấu hình tỷ trọng 70–80%; luật là một thành phần của Agent2.

**Kiểm chứng:** 120 gói nguồn mô phỏng C001/C002, 140/140 ca trúng–đối chứng
khớp engine giữ lại; 255/255 kiểm thử hồi quy; 6/6 bước giao diện đạt. Đây là
kết quả kỹ thuật, chưa chứng minh độ chính xác gian lận trên doanh nghiệp thật.

Mỗi luật có mã trạng thái rõ: đánh giá được, chưa đủ nguồn hoặc không áp dụng.
Không tự tạo nguồn, điền số 0 hay coi thiếu dữ liệu là không vi phạm. D1–D6/F4
là chẩn đoán theo tập/nguồn; thông tin danh mục và ngữ cảnh không tự trở thành
điểm giao dịch. Không cộng hai lần B5/E4 hoặc tạo điểm tổng/xác suất.

**Cách thử:** [hướng dẫn](../agent2/docs/FULL_RULE_PIPELINE.md),
[mẫu JSON](../agent2/examples/full_rules/README.md),
[ZIP 120 tệp](../agent2/examples/full_rules/full_rule_inputs_C001_C002.zip).
Chọn doanh nghiệp đúng quyền rồi nhập một JSON. Mẫu dùng tenant `demo`, không
tự đổi nguồn thật sang tenant khác để vượt quyền.

**Giới hạn:** canonical ít cột vẫn có bốn adapter P1/E3/B5/E4; nguồn đầy đủ mới
là đường chạy 35 luật. Profile mới chưa bridge sang 33 feature/ML, chưa HE35
và chưa deploy Portal live. Native còn từ chối số âm và giao dịch/sổ cái biết
muộn ngoài miền hỗ trợ; P1 canonical có dấu không đổi.

[Bằng chứng và tái chạy](../Agent2_Spec_v2_1/evidence/R2/full_rule_pipeline_20261114/REPORT.md).

## Nguồn cần cho từng luật

Cột “đã nối” là có evaluator trong profile nguồn đầy đủ; **không có nghĩa nguồn
của mọi doanh nghiệp đã đủ**. P1 có một đường HE canonical giới hạn đã kiểm
chứng; không áp dụng nhãn HE đó cho profile nguồn đầy đủ mới.

| Luật | Nội dung | Bảng nguồn cần | Adapter nguồn đầy đủ | Adapter canonical | HE profile mới | Đối chiếu |
|---|---|---|---|---|---|---|
| A1 | Chia nhỏ cùng người nhận trong 3 ngày | `transactions`, `employees`, `vendors`, `payment_requests`, `procurement_links`, `transaction_documents`, `supplier_payment_agreements` | Có | Chưa | No | 4/4 |
| A2 | Chia nhỏ cùng người lập/người nhận trong 30 ngày | `transactions`, `employees`, `vendors`, `payment_requests`, `procurement_links`, `transaction_documents`, `supplier_payment_agreements` | Có | Chưa | No | 4/4 |
| A3 | Chia nhỏ qua cụm người nhận liên kết | `transactions`, `employees`, `vendors`, `payment_requests`, `procurement_links`, `transaction_documents`, `supplier_payment_agreements`, `entity_links` | Có | Chưa | No | 4/4 |
| A4 | Người lập có nhiều khoản cận hạn mức | `transactions`, `employees`, `vendors`, `payment_requests`, `procurement_links`, `transaction_documents`, `supplier_payment_agreements`, `recurring_payments` | Có | Chưa | No | 4/4 |
| A5 | Số tiền tròn lệch baseline lịch sử | `transactions`, `employees`, `journal_documents`, `journal_lines`, `recurring_payments` | Có | Chưa | No | 4/4 |
| A6 | Thanh toán làm tròn vượt hóa đơn gốc | `transactions`, `employees`, `transaction_documents` | Có | Chưa | No | 4/4 |
| B1 | Tài khoản hoặc căn cước NCC trùng nhân viên | `transactions`, `vendors`, `employees` | Có | Chưa | No | 4/4 |
| B2 | Thông tin hoặc người đại diện NCC liên kết nhân viên | `transactions`, `vendors`, `employees`, `entity_links` | Có | Chưa | No | 4/4 |
| B3 | NCC mới thành lập nhận giao dịch lớn đầu tiên | `transactions`, `vendors`, `employees`, `procurement_links`, `transaction_documents` | Có | Chưa | No | 4/4 |
| B4 | Trạng thái người phát hành hóa đơn rủi ro | `transactions`, `vendors`, `vendor_status_history`, `tax_risk_history` | Có | Chưa | No | 4/4 |
| B5 | Nhiều NCC chung thông tin định danh | `transactions`, `vendors` | Có | Yes | Chưa | 4/4 |
| B6 | NCC ngủ đông nhận khoản lớn | `transactions`, `vendors`, `vendor_payment_schedules` | Có | Chưa | No | 4/4 |
| B7 | Đổi tài khoản gần ngày thanh toán chưa xác minh | `transactions`, `vendors`, `employees`, `bank_account_changes` | Có | Chưa | No | 4/4 |
| C1 | Lập hoặc duyệt ngoài lịch vận hành | `transactions`, `employees`, `companies`, `calendar`, `operating_schedules` | Có | Chưa | No | 4/4 |
| C2 | Tự duyệt vượt quyền được cấp | `transactions`, `employees`, `approval_authorities`, `approval_authority_coverage` | Có | Chưa | No | 4/4 |
| C3 | Duyệt dưới 60 giây ở cấp thẩm quyền cao | `transactions`, `employees`, `approval_authorities`, `approval_authority_coverage` | Có | Chưa | No | 4/4 |
| C4 | Thao tác trong kỳ nghỉ phép chính thức | `transactions`, `employees`, `leave_periods`, `system_actions`, `leave_activity_authorizations` | Có | Chưa | No | 4/4 |
| D1 | Benford chữ số đầu | `transactions`, `employees` | Có | Chưa | No | 4/4 |
| D2 | Benford chữ số thứ hai | `transactions`, `employees` | Có | Chưa | No | 4/4 |
| D3 | Hai chữ số đầu sát hạn mức | `transactions`, `employees` | Có | Chưa | No | 4/4 |
| D4 | Đuôi số đặc biệt vượt baseline | `transactions`, `employees` | Có | Chưa | No | 4/4 |
| D5 | MAD chữ số đầu | `transactions`, `employees` | Có | Chưa | No | 4/4 |
| D6 | Benford theo phân đoạn | `transactions`, `employees` | Có | Chưa | No | 4/4 |
| E1 | Lương không có chấm công hoặc bằng chứng thay thế | `transactions`, `employees`, `attendance`, `payroll_entitlements` | Có | Chưa | No | 4/4 |
| E2 | Lương sau chấm dứt hợp đồng | `transactions`, `employees`, `employment_events`, `payroll_settlements` | Có | Chưa | No | 4/4 |
| E3 | Tên NCC tương tự | `transactions`, `vendors` | Có | Yes | Chưa | 4/4 |
| E4 | NCC trùng định danh | `transactions`, `vendors` | Có | Yes | Chưa | 4/4 |
| F1 | Điều chỉnh thủ công sát khóa sổ và trọng yếu | `transactions`, `employees`, `journal_audit_log`, `closing_periods`, `materiality_policies` | Có | Chưa | No | 4/4 |
| F2 | Quản lý ghi đè quy trình | `transactions`, `employees`, `workflow_policies`, `override_events` | Có | Chưa | No | 4/4 |
| F3 | Khoảng trống/trùng số chứng từ | `transactions`, `employees`, `document_series`, `document_register`, `document_cancellations` | Có | Chưa | No | 4/4 |
| F4 | Doanh thu/công nợ kéo dài chưa đối chiếu tiền | `transactions`, `employees`, `customers`, `receivable_invoices`, `receipt_allocations`, `receipt_coverage`, `receivable_explanations` | Có | Chưa | No | 4/4 |
| P1 | Thanh toán vượt tổng giá trị cùng hóa đơn | `transactions`, `vendors`, `transaction_documents` | Có | Yes | Chưa | 4/4 |
| P2 | Chi tiền mặt cần rà soát hạn mức và chứng từ VAT | `transactions`, `employees`, `transaction_documents` | Có | Chưa | No | 4/4 |
| T1 | Tạm ứng còn dư nợ quá hạn | `transactions`, `employees`, `advances`, `advance_events` | Có | Chưa | No | 4/4 |
| T2 | Xóa nợ tạm ứng thiếu hồ sơ | `transactions`, `employees`, `advances`, `advance_events`, `transaction_documents` | Có | Chưa | No | 4/4 |
