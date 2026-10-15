# 3. T2 · T3 · T8 — Những xác suất cấp hoá đơn khác

## 3.1 T2 — Không bao giờ trả (cure) và nợ xấu

**Khung:** mô hình chữa lành hỗn hợp (Tong, Mues & Thomas 2012): `S(t) = π + (1 − π)·S_u(t)` với `π` = xác suất *không bao giờ* trả
(nợ xấu) và `S_u` = phân phối thời gian trả của nhóm sẽ trả. Hiện thực:

- `CureGBM` (T2): LightGBM nhị phân `P(bad | còn mở tại T, đã quá hạn)`; huấn luyện chỉ trên hoá đơn đã biết kết cục (đã trả hoặc đã xoá sổ) ở
  `label_end` (tránh hoá đơn còn mở làm nhiễu). 400 vòng, lr 0,04, leaves 31, min_data 200, λ₂=10.
- `S_u` = hazard T1 (đã có); T6 lấy mẫu trạng thái "không trả" trước, rồi thời điểm.
- **Sàn quy tắc:** TT 48/2019 — quá hạn 6–12 tháng trích 30%, 1–2 năm 50%, 2–3 năm 70%, >3 năm 100%. Mô hình chỉ cảnh báo *sớm hơn* sàn.

**Kết quả đo** (HĐ đã quá hạn tại T, test 2024-07→2025-06, 03_Evaluation/04):

| Miền | Mô hình | PR-AUC | ROC-AUC | Brier | ECE | Tổn thất kỳ vọng/thực |
|---|---|---|---|---|---|---|
| src (nợ xấu 31,9% trong nhóm quá hạn) | quy tắc TT48 | 0,603 | 0,733 | 0,238 | 0,265 | 0,19 |
| | logistic | 0,812 | 0,910 | 0,105 | 0,022 | 1,03 |
| | **Cure-GBM** | **0,965** | **0,975** | **0,048** | 0,036 | 0,88 |
| tgt zero-shot (44,7%) | quy tắc TT48 | 0,682 | 0,729 | 0,334 | 0,373 | 0,18 |
| | logistic | 0,862 | 0,886 | 0,138 | 0,053 | 1,15 |
| | **Cure-GBM** | **0,976** | 0,974 | **0,053** | 0,033 | **0,95** |

Đọc: quy tắc tuổi nợ *thấp hơn thực tế 5×* (sàn dự phòng chậm — đúng ý nghĩa "cảnh báo sớm hơn sàn"); mô hình giữ chất lượng
khi chuyển sang `tgt` (không thích nghi). **Cảnh báo:** nhóm "đã quá hạn" trong máy phát có tín hiệu mạnh (suy giảm trước vỡ
nợ, `f_resid`); số trên dữ liệu thật sẽ thấp hơn.

**Dữ liệu thật SBA 7(a)** (nhãn xoá nợ ≤3 năm; train FY≤2016, test FY2018–22; n=223.259; tỷ lệ nền 1,36%):

| Mô hình | ROC-AUC | PR-AUC | Brier | ECE | Tổn thất kỳ vọng/thực |
|---|---|---|---|---|---|
| Tỷ lệ nền | 0,500 | 0,0136 | 0,0134 | 0,0031 | 4,78 |
| Logistic | 0,840 | 0,0572 | 0,0131 | 0,0034 | 1,99 |
| LightGBM | **0,955** | **0,2138** | **0,0122** | 0,0054 | 1,13 |
| LightGBM + isotonic (FY2017) | 0,954 | 0,2078 | 0,0126 | 0,0076 | 1,02 |

**Phải đọc kèm hai cảnh báo (đã điều tra):**
1. `TermInMonths` chiếm 56% gain; kỳ hạn >120 tháng (BĐS, 148k khoản) có tỷ lệ xoá nợ 0,03–0,13% — phần lớn AUC cao đến từ việc nhận diện *khoản BĐS dài hạn an toàn*.
2. **Nhãn bị che:** 144.908 khoản `LoanStatus = EXEMPT` (đang hoạt động, kết cục không công bố) luôn có y=0 → nhãn âm giả. Cần loại hoặc xử lý như kiểm duyệt (WP-2.2) trước khi tuyên bố AUC; PR-AUC 0,21 (15,7× nền) là con số nên dùng, cùng độ lệch hiệu chỉnh theo năm (FY2022: dự báo 0,92% vs thực 1,91%).

## 3.2 T3 — Tranh chấp và trả một phần

- Dự đoán **tại ngày lập** (không dùng thông tin sau): `c_disp_eb`, `c_part_eb` (tỷ lệ lịch sử khách, co về tiền nghiệm với 20 quan sát giả), `c_late_eb`, `log_amt_rel`, `term_days`, `c_n`.
- Đối chứng: tỷ lệ nền; tỷ lệ lịch sử khách (EB).
- Số tiền kỳ vọng thu: `E[paid/invoiced]` = 0,998 (2,6% HĐ thu <99,5%); T6 dùng nhân tử này và tách riêng nợ xấu.

Kết quả `tgt` (n=4.536 HĐ lập 2024-07→2025-06): 

| Nhãn | Mô hình | AUC | PR-AUC | Brier |
|---|---|---|---|---|
| Tranh chấp (2,3%) | tỷ lệ nền | 0,500 | 0,0227 | 0,0223 |
| | **lịch sử khách (EB)** | **0,668** | 0,050 | 0,0219 |
| | LightGBM | 0,541 | 0,0244 | 0,0224 |
| Trả một phần (9,6%) | tỷ lệ nền | 0,500 | 0,0957 | 0,0877 |
| | **lịch sử khách (EB)** | **0,718** | 0,194 | **0,0826** |
| | LightGBM | 0,694 | 0,189 | 0,0828 |

**Kết luận:** *LightGBM không thắng mốc "lịch sử khách" → không giữ.* Trong máy phát, tranh chấp là tính chất của khách (`dispute_p`),
nên EB đủ; LightGBM chỉ thêm nhiễu. Giữ mô hình EB cho T3 trừ khi dữ liệu thật cho thấy tương tác nhiều biến (cần kiểm thử).

## 3.3 T8 — Lời hứa trả (Promise-to-Pay)

- **Thực thể hạng nhất:** `payment_promises(invoice_id, promised_date, source, approved_by, created_at)`; có người duyệt + nhật ký.
- **Độ tin cậy theo khách:** Beta–Binomial `rel = (kept + 4)/(n + 6)` (tiền nghiệm Beta(4,2)); `kept` = |ngày trả thật − hứa| ≤ 3 ngày; chỉ tính lời hứa đã đến hạn ≤T (không rò rỉ).
- **Đưa vào mô hình:** `has_promise`, `days_to_promised`, `promise_overdue`, `c_promise_rel`, `c_promise_n` và biến tuần `promised_in_k`; GBM tự học
  "lời hứa của khách tin cậy dịch phân phối về tuần hứa".
- **Hiển thị:** nhãn nguồn số liệu ("theo cam kết của khách, độ tin cậy 0,82"), không ẩn mô hình.
- **Thí nghiệm E** (đang chạy): so DH-GBM có/không đặc trưng lời hứa trên `src` 2024-07→12; chỉ số MAE P50 trên HĐ có lời hứa.
- **Rủi ro:** dữ liệu lời hứa tổng hợp theo giả định `Beta(4,2)`; giá trị thật phải đo ở T13. Cần quy trình ghi lời hứa ít nhập liệu nhất (một tin nhắn → Agent 4 phân tích).
