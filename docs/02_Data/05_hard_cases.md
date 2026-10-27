# 5. Hard case — tình huống khó của dữ liệu

Cột "Trạng thái": ✅ đã sinh trong máy phát · 🟡 có một phần · ⬜ chưa có (kế hoạch bổ sung ở 05_Coding_Agent_Plan).
Mỗi hard case cần: *cách sinh*, *nhãn đi kèm*, *cách đo*.

## 5.1 Hành vi khách hàng

| # | Hard case | Mô tả | Cách sinh | Nhãn | Cách đo | TT |
|---|---|---|---|---|---|---|
| H1 | Khách trả đúng theo lịch riêng | Ngày 10 & 25 hằng tháng, thứ Năm hằng tuần… | `payrun` 10 mẫu | `customers.payrun` | WAPE thu theo tuần, AUC biến "ngày chạy rơi vào tuần k" | ✅ |
| H2 | Khách mới, chưa có lịch sử (cold start) | <3 hoá đơn đã đóng | sự kiện `customer_acquired` theo tuần, có khách tạm rời và quay lại | `c_n_hist`, `events` | Phân tầng lỗi theo `c_n_hist` | ✅ (đo chưa tách tầng) |
| H3 | Điểm gãy riêng khách | Từ ngày D mọi HĐ chậm thêm 8–25 ngày | 10% khách | `events` | Tỷ lệ phát hiện / độ trễ / báo giả (T7) | ✅ |
| H4 | Suy giảm trước vỡ nợ | HĐ đáo hạn trước vỡ nợ chịu thanh khoản yếu và hazard trả theo tuần | tự động | `events` chứa mọi lần vỡ nợ; `customers.default_date` chỉ lần đầu | P(nợ xấu) tăng trước sự kiện | ✅ (chưa đo riêng theo lần lặp) |
| H5 | Vỡ nợ tương quan | Cụm khách vỡ nợ khi thị trường căng | hazard theo `S_t` và `F_t` | `events` | Phân bố số vỡ nợ/tuần (dispersion > Poisson) | ✅ |
| H6 | Trễ cực dài (>180 ngày) | Đuôi Pareto | `ultra_p`, `tail=coface` | `invoices.ultra_late` | Độ phủ P90; hiệu chỉnh đuôi | ✅ |
| H7 | Tranh chấp kéo dài + giảm trừ | +15–75 ngày, credit note | `dispute_p` | `invoices.dispute, credit_note` | AUC tranh chấp; sai số tiền kỳ vọng | ✅ |
| H8 | Trả một phần, trả thiếu | 30–70% rồi phần còn lại, có 15% thiếu 1–10% | `partial_p` | `payments.kind` | MAE tỷ lệ thu; WAPE theo tiền | ✅ |
| H9 | Khách gộp nhiều HĐ trong một lệnh chuyển | batch_pay | 55% khách | `payments.txn_id` chung | Độ chính xác liên kết T9 (một-nhiều) | ✅ |
| H10 | Khách gộp HĐ cuối tháng | 1 HĐ to/tháng | 12% khách | — | | ✅ |
| H11 | Dồn trả trước Tết / chậm sau Tết | | `tet_settle_p` | — | Sai số tuần quanh Tết (phân tầng) | ✅ |
| H12 | Khách một nhà mua >40% doanh thu | Tập trung | Pareto α=1,5 + tgt | — | Độ phủ khi khách lớn trễ | 🟡 (top-10 54–70%, chưa kiểm một khách >40%) |
| H13 | Ưu đãi chiết khấu thanh toán sớm (2/10 net 30) | Trả sớm có chủ đích | ⬜ | | | ⬜ |
| H14 | Khách là nhóm công ty trả chung một đầu mối | Trả hộ, tên người trả ≠ tên khách | ⬜ (T9 hard) | | Độ chính xác liên kết | ⬜ |
| H15 | Khách ngoại tệ, chênh lệch tỷ giá | USD/EUR | ⬜ | | | ⬜ |
| H16 | Khoản giữ lại bảo hành (xây dựng 5% sau 24 tháng) | Phần cuối rất muộn | ⬜ | | | ⬜ |

## 5.2 Nhiễu quan sát (dữ liệu bẩn kiểu SME VN)

| # | Hard case | Cách sinh | Cách đo | TT |
|---|---|---|---|---|
| H20 | Ghi sổ theo lô (ngày sổ ≠ ngày tiền) | `posting_mode` ngày/tuần/tháng | MAE ngày sổ vs ngày thật (12,6 ngày ở tgt) | ✅ |
| H21 | Phân bổ FIFO sai | 50% khách ở chế độ không hằng ngày | Tác hại khi học từ nhãn sổ (thí nghiệm F) | ✅ |
| H22 | Nội dung chuyển khoản không ghi số HĐ | `memo_no_p` | % liên kết chỉ nhờ số tiền/tên | ✅ |
| H23 | Tên đối tác viết tắt/không dấu/cắt/trống | `counterparty_variant` | txn_customer_recall | ✅ |
| H24 | Số HĐ bỏ số 0 đầu, nhiều HĐ trong CK, lỗi gõ | `transfer_memo` | | ✅ |
| H25 | Phí chuyển tiền bị trừ, số tiền lệch vài chục nghìn | `fee_deducted` | dung sai TOL=25.000đ | ✅ |
| H26 | Giao dịch không phải trả hoá đơn (lãi, nộp tiền mặt, nội bộ, hoàn cọc, vay) | 6 loại nhiễu | tỷ lệ khớp nhầm giao dịch nhiễu (1,9%) | ✅ |
| H27 | Hoá đơn trùng, MST sai, ngày tương lai, tổng không cộng | `inject_errors` | recall/precision cổng chất lượng ≥95% | ✅ |
| H28 | Hoá đơn điều chỉnh/thay thế/huỷ (TT78) | ⬜ | | ⬜ |
| H29 | Thoả thuận miệng ngoài hệ thống (khất nợ không ghi) | ⬜ — hiện chỉ có lời hứa có ghi | | ⬜ |
| H30 | Dữ liệu thiếu cột (không có hạn thanh toán) | BPI/Customer Invoices tự nhiên có | | 🟡 |

## 5.3 Vĩ mô và cấu trúc

| # | Hard case | Cách sinh | Cách đo | TT |
|---|---|---|---|---|
| H40 | Sốc COVID theo OxCGRT VN | `covid_stress` thật | Độ phủ trong giai đoạn sốc | ✅ |
| H41 | Đóng băng tín dụng 2022–23 | `credit_crunch` | | ✅ |
| H42 | Mùa vụ + Tết theo ngành | 12 hệ số/ngành, hệ số Tết | WAPE theo tuần quanh Tết | ✅ |
| H43 | Thay đổi luật (giảm VAT 8%, bỏ môn bài, lương tối thiểu) | `calendar_vn` có hiệu lực theo ngày | 15 kiểm thử | ✅ |
| H44 | Thay đổi chế độ không thể dự báo (sốc ngoài mẫu) | `sens_*` đuôi khác | Giảm độ phủ có kiểm soát | 🟡 |
| H45 | Lạm phát/lãi suất vay biến động | WDI | | 🟡 |
| H46 | Thiên tai/đình trệ chuỗi cung ứng cục bộ | ⬜ | | ⬜ |

## 5.4 Hard case thiếu hụt tiền (ground truth cho T6)

| # | Tình huống | Sinh bằng | Đo |
|---|---|---|---|
| H50 | Thiếu hụt do sốc chung (nhiều khách cùng trễ) | cú sốc COVID/credit crunch | Cảnh báo trước ≥4 tuần, Brier |
| H51 | Thiếu hụt do một khách lớn trễ/vỡ nợ | điểm gãy + vỡ nợ khách lớn | Lead time, danh sách đòi nợ có chứa khách đó |
| H52 | Thiếu hụt do dồn nghĩa vụ (VAT quý + lương + BHXH cùng tuần) | lịch T5 | Dự báo đúng tuần |
| H53 | Thiếu hụt tuần sau Tết (chi lương + thưởng, thu chậm) | Tết | Dự báo đúng tuần |
| H54 | Không thiếu hụt nhưng dải rộng (báo giả) | | Tỷ lệ báo giả/DN-năm |

**Kết quả hiện có của tgt:** 12/14 công ty có ít nhất một ngày số dư âm (9,8% số ngày); src 26/40 (2,4% số ngày). Số
dư âm là *sự kiện có nhãn*, đo được lead-time.
