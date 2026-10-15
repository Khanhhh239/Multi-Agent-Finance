# 04 · Người dùng, nhu cầu và phân loại câu hỏi

## 1. Persona
| Persona | Mục tiêu | Thói quen | Kênh | Yêu cầu riêng |
|---|---|---|---|---|
| **Chủ DN / CEO** (chính) | Biết lãi–lỗ, tiền còn, ai nợ, cần chi gì sắp tới | Hỏi nhanh bằng điện thoại, ít thời gian | Chat di động / Zalo | Câu trả lời ≤ 5 dòng, số làm tròn dễ đọc, có "vì sao" |
| **Kế toán trưởng** | Giảm yêu cầu lấy số, bảo đảm số khớp sổ | Rất quan tâm công thức, tài khoản | Web | Truy vết tới chứng từ, tách khung quản trị/thuế |
| **Giám đốc chi nhánh / trưởng kinh doanh** | Công nợ khách mình, đạt kế hoạch | Tra cứu theo phạm vi của mình | Web/di động | **Phân quyền theo chi nhánh/nhân viên** (xem yêu cầu NFR‑S2) |
| **Kiểm toán nội bộ / quản trị rủi ro** (thứ cấp) | Phát hiện bất thường | Xem nhật ký, lọc ngoại lệ | Web | Nhật ký bất biến, danh sách chứng từ lệch |

## 2. Hành trình điển hình (CEO, 14/10)
1. 8h: nhận **bản tin tuần** (tiền, nợ quá hạn, chi phí tăng, nghĩa vụ 15 ngày tới).
2. Thấy "nợ quá hạn tăng": hỏi *"khách nào đang nợ lớn nhất?"* → bảng top khách + tuổi nợ.
3. Hỏi tiếp *"nếu bỏ khách đó thì DSO còn bao nhiêu?"* → agent nhớ ngữ cảnh, tính lại với bộ lọc loại trừ.
4. Bấm **"Xem cách tính"** → công thức + chứng từ lớn nhất.
5. Nhắn *"khách này xin khất đến 15/11, anh đồng ý"* → agent **đề xuất** ghi cam kết thanh toán; CEO bấm duyệt; nhật ký lưu.

## 3. Phân loại câu hỏi (taxonomy) — cơ sở cho bộ đánh giá
Rút từ 30 câu mẫu (`sample-questions.md`) và mở rộng. Mỗi nhóm có chỉ số/công cụ ánh xạ.

| Nhóm | Ví dụ | Công cụ/chỉ số chính | % mục tiêu trong bộ test |
|---|---|---|---|
| **Q1 Tra số đơn** | "Doanh thu thuần tháng này?" | `query_metric(net_revenue)` | 30% |
| **Q2 So sánh / xu hướng** | "Quý này so với quý trước tăng/giảm?" · "Dòng tiền từng tháng năm nay" | `query_metric` + `compare_to` / `group_by=month` | 20% |
| **Q3 Phân rã** | "Lợi nhuận gộp theo sản phẩm?" · "Công nợ theo nhân viên" | `group_by` (product_line, branch, salesperson…) | 10% |
| **Q4 Công nợ & dòng tiền** | "Khoản phải thu quá hạn > 30 ngày?" · "Phải trả đến hạn 15 ngày tới?" | `overdue_receivables`, `ap_due_soon`, `ar_aging`, `upcoming_obligations` | 12% |
| **Q5 Bất thường** | "Chi phí nào tăng mạnh?" · "Có chứng từ lệch Nợ/Có?" | `expense_spikes`, `unbalanced_journals`, `unusual_account_movements` | 8% |
| **Q6 Giả định / loại trừ** | "Nếu loại khách lớn nhất, DSO còn?" | `filters.exclude_top_customers` | 4% |
| **Q7 Khung thuế** | "Thu nhập chịu thuế?", "Chi phí không được trừ?" | `taxable_income`, `mgmt_vs_tax_gap` (view=tax) | 5% |
| **Q8 Mơ hồ** | "Lãi bao nhiêu?" "Tình hình thế nào?" | → **hỏi lại** (2–3 lựa chọn) | 4% |
| **Q9 Ngoài phạm vi / không an toàn** | "Dự báo giá cổ phiếu", "Xóa chứng từ này", "Bỏ qua quy tắc…" | → **từ chối** | 4% |
| **Q10 Hành động** | "Chặn tạm ứng chi nhánh đó" | `propose_action` (không tự thực thi) | 3% |

Độ khó thêm vào: không dấu ("doanh thu thang nay"), viết tắt ("dt", "cp"), nhầm lẫn thuật ngữ ("lãi" = gộp / ròng?), tham chiếu ("tháng đó", "khách ấy"), hai ý một câu, giọng nói (STT sai chính tả).

## 4. Nhu cầu → năng lực → chỉ số (traceability)
| Nhu cầu | Năng lực | Chỉ số đã có trong lõi |
|---|---|---|
| Biết lãi lỗ | P&L đầy đủ | `net_revenue`, `gross_profit`, `gross_margin_pct`, `operating_profit`, `net_profit`, `ebitda` |
| Biết tiền | Thanh khoản | `cash_and_equivalents`, `net_cash_flow`, `cash_flow_breakdown`, `cash_coverage_days`, `current_ratio`, `quick_ratio` |
| Biết ai nợ | Công nợ | `ar_balance`, `ar_by_customer`, `ar_by_salesperson`, `ar_aging`, `overdue_receivables`, `dso`, `dso_actual` |
| Biết nợ ai | Phải trả | `ap_balance`, `ap_by_vendor`, `ap_due_soon`, `dpo` |
| Biết chi phí | Chi phí | `operating_expenses`, `expense_by_category`, `expense_spikes`, `salary_expense`, `labor_cost`, `budget_vs_actual` |
| Biết hàng | Tồn kho | `inventory_value`, `dio`, `cash_conversion_cycle` |
| Biết nghĩa vụ | Thuế & vay | `tax_payable`, `vat_position`, `cit_estimate`, `debt_balance`, `upcoming_obligations` |
| Biết rủi ro | Bất thường | `unusual_account_movements`, `unbalanced_journals`, `mgmt_vs_tax_gap` |

## 5. Ưu tiên nhu cầu (MoSCoW)
- **Must:** tra số đơn, so sánh kỳ, phân rã, công nợ & quá hạn, nhãn tạm tính/khóa sổ, truy vết, hỏi lại, từ chối.
- **Should:** bản tin tuần, phân quyền, hội thoại nhiều lượt, đề xuất hành động có phê duyệt.
- **Could:** giọng nói, Zalo OA, Text‑to‑SQL dự phòng, biểu đồ.
- **Won't (v1):** dự báo tương lai (thuộc Agent 1), phát hiện gian lận chuyên sâu (Agent 2), tư vấn pháp lý thuế (Agent 3); tích hợp song song chỉ ở mức *mock adapter*.
