# So sánh bộ luật, đồ thị quan hệ và Isolation Forest

Ba bộ dữ liệu tổng hợp v2, cùng seed. Mỗi bộ có 25.000 quan sát test; ngân sách xếp hạng 0,3% = 75 cảnh báo.
Điểm luật/ensemble không phải xác suất gian lận. Trọng số được đặt theo file luật trước khi đọc nhãn test.

| Tỷ lệ gian lận | Phương án | AP | Phát hiện | Precision@75 | Recall | Cảnh báo sai | Recall theo vụ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.1% | Rules | 0.5108 | 15 | 20.0% | 60.0% | 60 | 68.2% |
| 0.1% | IF | 0.0067 | 1 | 1.3% | 4.0% | 74 | 4.5% |
| 0.1% | Rules+Graph | 0.5166 | 15 | 20.0% | 60.0% | 60 | 68.2% |
| 0.1% | Rules+Graph+IF | 0.3120 | 9 | 12.0% | 36.0% | 66 | 40.9% |
| 0.3% | Rules | 0.6026 | 44 | 58.7% | 58.7% | 31 | 66.2% |
| 0.3% | IF | 0.0342 | 5 | 6.7% | 6.7% | 70 | 7.7% |
| 0.3% | Rules+Graph | 0.6136 | 44 | 58.7% | 58.7% | 31 | 66.2% |
| 0.3% | Rules+Graph+IF | 0.4528 | 30 | 40.0% | 40.0% | 45 | 46.2% |
| 0.5% | Rules | 0.6571 | 67 | 89.3% | 53.6% | 8 | 61.5% |
| 0.5% | IF | 0.0533 | 8 | 10.7% | 6.4% | 67 | 7.3% |
| 0.5% | Rules+Graph | 0.6700 | 67 | 89.3% | 53.6% | 8 | 61.5% |
| 0.5% | Rules+Graph+IF | 0.5004 | 45 | 60.0% | 36.0% | 30 | 41.3% |

## Diễn giải và phạm vi

- Sáu nhóm A–F có 31 rule. Năm rule C4/E2/F2/F3/F4 chưa đánh giá được vì thiếu nguồn dữ liệu cần thiết; không coi thiếu dữ liệu là không có vi phạm.
- B1/B4/B7/E3/F1 và A3/D3/D4 có phạm vi hoặc phương pháp thay thế được ghi trong rule_coverage.json.
- P1 (thanh toán vượt hóa đơn), T1 (tạm ứng quá hạn), T2 (xóa nợ thiếu hồ sơ) bổ sung phạm vi sáu kịch bản gian lận ban đầu.
- Rules dùng đối chiếu trực tiếp; Rules+Graph thêm chia nhỏ qua mạng lưới và quan hệ NCC–người đại diện–nhân viên.
- D1–D6 là chẩn đoán theo tập giao dịch tại từng thời điểm; không tăng điểm một giao dịch chỉ vì tập không theo Benford.
- Ngưỡng validation giữ mọi trường hợp bằng điểm nên có thể vượt ngân sách. Precision@75 so sánh cùng sức chứa, không phải ngưỡng vận hành.
- Hàng đợi case_queue.csv dùng ngưỡng nghiệp vụ mặc định; ưu tiên/SLA/chủ hồ sơ là gợi ý mô phỏng. Đã có UI rà soát cục bộ (xem ../review_ui.md), chưa gửi thông báo.
- File rule_hits.jsonl lưu dữ kiện, liên kết giao dịch, đường đi đồ thị và lý do ngoại lệ đã biết.
- Chỉ dùng dữ liệu tổng hợp, một seed và doanh nghiệp đã biết qua thời gian. Cần tập mới được giữ kín, nhiều seed và dữ liệu SME thật để nghiệm thu.
- Không chọn trọng số/đổi luật dựa trên nhãn test của báo cáo này; không cập nhật ngưỡng tự động theo phản hồi.

## Cảnh báo sai trên hard negatives ở cùng sức chứa

| Bộ | Phương án | Nhóm hợp lệ | Số mẫu | Cảnh báo sai | FPR |
| --- | --- | --- | ---: | ---: | ---: |
| 0.1% | Rules | approved_advance_extension | 96 | 0 | 0.00% |
| 0.1% | Rules | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.1% | Rules | declared_related_party | 96 | 0 | 0.00% |
| 0.1% | Rules | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.1% | Rules | legitimate_installments | 96 | 2 | 2.08% |
| 0.1% | Rules | legitimate_period_close | 96 | 0 | 0.00% |
| 0.1% | Rules | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.1% | Rules | long_approval_delay | 96 | 1 | 1.04% |
| 0.1% | Rules | new_legitimate_vendor | 96 | 1 | 1.04% |
| 0.1% | Rules | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.1% | Rules | round_recurring_payment | 96 | 0 | 0.00% |
| 0.1% | Rules | verified_bank_change | 97 | 0 | 0.00% |
| 0.1% | Rules | weekend_operations | 96 | 1 | 1.04% |
| 0.1% | IF | approved_advance_extension | 96 | 26 | 27.08% |
| 0.1% | IF | approved_advance_writeoff | 96 | 46 | 47.92% |
| 0.1% | IF | declared_related_party | 96 | 0 | 0.00% |
| 0.1% | IF | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.1% | IF | legitimate_installments | 96 | 0 | 0.00% |
| 0.1% | IF | legitimate_period_close | 96 | 0 | 0.00% |
| 0.1% | IF | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.1% | IF | long_approval_delay | 96 | 0 | 0.00% |
| 0.1% | IF | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.1% | IF | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.1% | IF | round_recurring_payment | 96 | 0 | 0.00% |
| 0.1% | IF | verified_bank_change | 97 | 0 | 0.00% |
| 0.1% | IF | weekend_operations | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | approved_advance_extension | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | declared_related_party | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | legitimate_installments | 96 | 2 | 2.08% |
| 0.1% | Rules+Graph | legitimate_period_close | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.1% | Rules+Graph | long_approval_delay | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | new_legitimate_vendor | 96 | 1 | 1.04% |
| 0.1% | Rules+Graph | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | round_recurring_payment | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph | verified_bank_change | 97 | 0 | 0.00% |
| 0.1% | Rules+Graph | weekend_operations | 96 | 1 | 1.04% |
| 0.1% | Rules+Graph+IF | approved_advance_extension | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | declared_related_party | 96 | 4 | 4.17% |
| 0.1% | Rules+Graph+IF | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | legitimate_installments | 96 | 4 | 4.17% |
| 0.1% | Rules+Graph+IF | legitimate_period_close | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | long_approval_delay | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | round_recurring_payment | 96 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | verified_bank_change | 97 | 0 | 0.00% |
| 0.1% | Rules+Graph+IF | weekend_operations | 96 | 0 | 0.00% |
| 0.3% | Rules | approved_advance_extension | 96 | 0 | 0.00% |
| 0.3% | Rules | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.3% | Rules | declared_related_party | 96 | 0 | 0.00% |
| 0.3% | Rules | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.3% | Rules | legitimate_installments | 96 | 3 | 3.12% |
| 0.3% | Rules | legitimate_period_close | 96 | 0 | 0.00% |
| 0.3% | Rules | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.3% | Rules | long_approval_delay | 96 | 0 | 0.00% |
| 0.3% | Rules | new_legitimate_vendor | 96 | 1 | 1.04% |
| 0.3% | Rules | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.3% | Rules | round_recurring_payment | 96 | 0 | 0.00% |
| 0.3% | Rules | verified_bank_change | 97 | 0 | 0.00% |
| 0.3% | Rules | weekend_operations | 96 | 0 | 0.00% |
| 0.3% | IF | approved_advance_extension | 96 | 17 | 17.71% |
| 0.3% | IF | approved_advance_writeoff | 96 | 44 | 45.83% |
| 0.3% | IF | declared_related_party | 96 | 0 | 0.00% |
| 0.3% | IF | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.3% | IF | legitimate_installments | 96 | 0 | 0.00% |
| 0.3% | IF | legitimate_period_close | 96 | 0 | 0.00% |
| 0.3% | IF | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.3% | IF | long_approval_delay | 96 | 0 | 0.00% |
| 0.3% | IF | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.3% | IF | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.3% | IF | round_recurring_payment | 96 | 0 | 0.00% |
| 0.3% | IF | verified_bank_change | 97 | 0 | 0.00% |
| 0.3% | IF | weekend_operations | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | approved_advance_extension | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | declared_related_party | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | legitimate_installments | 96 | 3 | 3.12% |
| 0.3% | Rules+Graph | legitimate_period_close | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.3% | Rules+Graph | long_approval_delay | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | new_legitimate_vendor | 96 | 1 | 1.04% |
| 0.3% | Rules+Graph | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | round_recurring_payment | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph | verified_bank_change | 97 | 0 | 0.00% |
| 0.3% | Rules+Graph | weekend_operations | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | approved_advance_extension | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | declared_related_party | 96 | 1 | 1.04% |
| 0.3% | Rules+Graph+IF | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | legitimate_installments | 96 | 5 | 5.21% |
| 0.3% | Rules+Graph+IF | legitimate_period_close | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | long_approval_delay | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | round_recurring_payment | 96 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | verified_bank_change | 97 | 0 | 0.00% |
| 0.3% | Rules+Graph+IF | weekend_operations | 96 | 0 | 0.00% |
| 0.5% | Rules | approved_advance_extension | 96 | 0 | 0.00% |
| 0.5% | Rules | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.5% | Rules | declared_related_party | 96 | 0 | 0.00% |
| 0.5% | Rules | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.5% | Rules | legitimate_installments | 96 | 0 | 0.00% |
| 0.5% | Rules | legitimate_period_close | 96 | 0 | 0.00% |
| 0.5% | Rules | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.5% | Rules | long_approval_delay | 96 | 0 | 0.00% |
| 0.5% | Rules | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.5% | Rules | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.5% | Rules | round_recurring_payment | 96 | 0 | 0.00% |
| 0.5% | Rules | verified_bank_change | 97 | 0 | 0.00% |
| 0.5% | Rules | weekend_operations | 96 | 0 | 0.00% |
| 0.5% | IF | approved_advance_extension | 96 | 11 | 11.46% |
| 0.5% | IF | approved_advance_writeoff | 96 | 48 | 50.00% |
| 0.5% | IF | declared_related_party | 96 | 0 | 0.00% |
| 0.5% | IF | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.5% | IF | legitimate_installments | 96 | 0 | 0.00% |
| 0.5% | IF | legitimate_period_close | 96 | 0 | 0.00% |
| 0.5% | IF | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.5% | IF | long_approval_delay | 96 | 0 | 0.00% |
| 0.5% | IF | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.5% | IF | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.5% | IF | round_recurring_payment | 96 | 0 | 0.00% |
| 0.5% | IF | verified_bank_change | 97 | 0 | 0.00% |
| 0.5% | IF | weekend_operations | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | approved_advance_extension | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | declared_related_party | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | legitimate_installments | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | legitimate_period_close | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.5% | Rules+Graph | long_approval_delay | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | round_recurring_payment | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph | verified_bank_change | 97 | 0 | 0.00% |
| 0.5% | Rules+Graph | weekend_operations | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | approved_advance_extension | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | approved_advance_writeoff | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | declared_related_party | 96 | 1 | 1.04% |
| 0.5% | Rules+Graph+IF | historical_valid_invoice | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | legitimate_installments | 96 | 4 | 4.17% |
| 0.5% | Rules+Graph+IF | legitimate_period_close | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | legitimate_self_approval | 97 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | long_approval_delay | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | new_legitimate_vendor | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | remote_employee_payroll | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | round_recurring_payment | 96 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | verified_bank_change | 97 | 0 | 0.00% |
| 0.5% | Rules+Graph+IF | weekend_operations | 96 | 0 | 0.00% |
