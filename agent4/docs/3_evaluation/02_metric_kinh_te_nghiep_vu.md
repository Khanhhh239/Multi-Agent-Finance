# 02 · Metric đánh giá kinh tế & nghiệp vụ

> Khác với `01`: đây là các chỉ số chứng minh **sản phẩm làm doanh nghiệp tốt hơn**. Phần lớn chỉ đo được ở **pilot** (trước/sau); mục "Cách đo" nói rõ.

## 1. Cây giá trị
```
Giá trị Agent 4
 ├─ Tiết kiệm thời gian        (giờ kế toán/quản lý cho báo cáo & ad‑hoc)
 ├─ Quyết định nhanh hơn        (độ trễ thông tin ↓)
 │    ├─ Thu hồi nợ sớm hơn      → DSO ↓ → vốn lưu động giải phóng → lãi vay tiết kiệm
 │    ├─ Giảm nợ xấu             → tổn thất ↓
 │    └─ Quản lý thanh khoản     → ít lần vay khẩn cấp, ít phạt chậm nộp
 ├─ Chất lượng thông tin        (ít sai số, một nguồn sự thật)
 └─ Tuân thủ/kiểm toán         (truy vết, nhật ký)
```

## 2. Bộ chỉ số kinh tế (KPI)
| Nhóm | KPI | Định nghĩa | Baseline (DN mẫu, nguồn) | Cách đo trong pilot |
|---|---|---|---|---|
| **Thời gian** | Giờ xử lý yêu cầu ad‑hoc | Σ (số yêu cầu × thời gian xử lý) trên tháng | **Giả định** 108 giờ/tháng (60 yêu cầu/tuần × 25 phút) | Nhật ký yêu cầu 4 tuần trước/sau; bấm giờ mẫu |
| | Giờ làm gói báo cáo tháng/tuần | Thời gian tổng hợp báo cáo định kỳ | **Giả định** 48 + 35 giờ/tháng | Bảng chấm công công việc |
| | Time‑to‑answer | Từ lúc hỏi đến có số | Giả định 2–24 giờ (chờ kế toán) | Mốc thời gian hỏi–đáp |
| **Vốn lưu động** | **DSO** | Phải thu bình quân / doanh số bán chịu × ngày | 53 ngày (2025) → **62 ngày** (Q3/2026) — *dữ liệu mẫu* | Engine `dso` theo quý |
| | Tỷ lệ quá hạn > 30 ngày | Quá hạn > 30 ngày / phải thu | **19,3%** (9,17 / 47,63 tỷ) | `overdue_receivables` |
| | Phải thu quá hạn > 90 ngày | Dư nợ nhóm >90 ngày | **6,15 tỷ** | `ar_aging` |
| | Chu kỳ chuyển đổi tiền | DSO + DIO − DPO | 75 ngày (Q3/2026) | `cash_conversion_cycle` |
| **Rủi ro tín dụng** | Tổn thất nợ xấu / doanh số bán chịu | Xóa nợ + trích lập | **Giả định** 0,5%/năm (~0,97 tỷ) | Sổ xóa nợ, TK 2293, 6422 |
| | Thời gian từ vượt hạn mức đến can thiệp | Ngày giữa vi phạm và hành động | Hoàng Long (hạn mức 4 tỷ): dư nợ 3,1 tỷ (04/2026) → 6,2 tỷ (05/2026) → 8,1 tỷ (06/2026); vượt 120% hạn mức ngày 15/05/2026, không thu thêm được từ sau 09/09/2026 | Nhật ký cảnh báo & hành động |
| **Thanh khoản** | Số lần rút vốn khẩn cấp | Số lần giải ngân hạn mức do tiền < ngưỡng | 10 lần / 21 tháng | `cash_flow_breakdown` + `loan` |
| | Ngày tiền hiện có đủ chi | `cash_coverage_days` | 4,6 ngày (14/10) | Engine |
| | Phạt/chậm nộp thuế | Chi phí 811 liên quan | 4,2 triệu (2025) | Sổ 811 |
| **Chi phí tài chính** | Lãi vay | TK 635 | 764 triệu (2025); 1,11 tỷ (2026 đến 14/10) | Sổ 635 |
| **Chất lượng** | Tỷ lệ số liệu bị tranh cãi | Số lần kế toán sửa số đã gửi / tổng báo cáo | Chưa có baseline | Nhật ký chỉnh sửa |
| | Phát hiện bất thường sớm | Số ca A1–A10 nêu ra trong bản tin / số ca có | — | Bộ E10 + pilot |
| **Adoption** | WAU / MAU, câu hỏi/người/tuần | Mức sử dụng | — | Log |
| | CSAT / NPS | Hài lòng người dùng | — | Khảo sát 5 câu |
| | Tỷ lệ "Xem cách tính" được bấm | Mức quan tâm kiểm chứng | — | Log |

## 3. Thiết kế thí nghiệm trước/sau (pilot)
**Thiết kế:** nhóm đối chứng ghép cặp (matched) hoặc **bậc thang (stepped‑wedge)** nếu có ≥ 3 DN: mỗi DN đo 6 tuần *trước*, 6 tuần *sau*.
**Biến nhiễu cần kiểm soát:** mùa vụ (Tết, cuối năm), thay đổi chính sách tín dụng, nhân sự, dự án lớn.
**Phân tích:** chênh lệch trước–sau (difference‑in‑differences nếu có đối chứng); khoảng tin cậy bootstrap; báo cáo **hiệu ứng thực** chứ không phải kịch bản mô hình.
**Tiêu chí dừng:** nếu sau 6 tuần mức dùng < 3 câu/người/tuần thì sản phẩm chưa phù hợp quy trình → điều tra trước khi đo kinh tế.

## 4. Chỉ số "chi phí của sai sót" (đối trọng)
| Sai sót | Chi phí/ hậu quả | Giảm bằng |
|---|---|---|
| Số sai được tin | Quyết định sai (khó định lượng) → đặt mục tiêu **0** | Verifier |
| Nhầm khung thuế/quản trị | Kê khai/ dự toán sai | Validator khung |
| Từ chối nhầm câu hợp lệ | Giảm tin cậy, tăng quay lại kế toán | Đo over‑refusal |
| Hỏi lại quá nhiều | Mệt mỏi | Đo clarification rate ≤ 12% |

## 5. Báo cáo mẫu cho Ban điều hành (hàng quý)
```
Quý N: [mức dùng]  [giờ kế toán tiết kiệm]  [ΔDSO ngày → ΔVốn lưu động tỷ → Δlãi tiết kiệm]
       [nợ quá hạn >30 ngày: trước/sau]  [số cảnh báo sớm hành động được]  [số lỗi sản phẩm / số câu]
```
Tất cả số phải kèm **phương pháp đo + khoảng không chắc chắn**.
