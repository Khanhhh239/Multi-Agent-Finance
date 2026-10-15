# 7. Bộ dữ liệu đánh giá — từng năng lực và đánh giá chung

Nguyên tắc: (i) mỗi năng lực có **bộ kiểm tra riêng** để lỗi một khối không bị che bởi khối khác; (ii) có **bộ đánh giá
chung** (đầu-cuối) cho kết quả người dùng thấy; (iii) mọi bộ kiểm tra tách theo **thời gian** (và theo **công ty** khi đo
chuyển miền) với nhãn bị kiểm duyệt đúng tại ngày cắt.

## 7.1 Đánh giá riêng từng năng lực (unit benchmarks)

| Mã | Năng lực | Bộ dữ liệu | Quy tắc chia | Nhãn | Mốc bắt buộc | Chỉ số chính |
|---|---|---|---|---|---|---|
| E-T0 | Lược đồ, chất lượng | XML từ `tgt` (200 file) + `inject_errors` (5–30%) | — | lỗi đã chèn | không có | recall/precision cổng ≥95% |
| E-T1a | Thời điểm trả — trong miền | `src` snapshot hằng tuần | rolling-origin 2023-07, 2024-07; train<O, cal=63 ngày liền trước (cách 120 ngày), test 26 tuần | `remaining` bị kiểm duyệt | B0 đúng hạn, B1 trung vị khách, B1d phân vị khách | pinball, MAE P50, cov80, IBS, ECE@4w, C-index, WAPE thu 1–4/5–13 tuần |
| E-T1b | Thời điểm trả — chuyển miền | `tgt` onboard 2024-07, lịch sử nhìn thấy M ∈ {0,3,6,12,24} tháng | train nguồn đến 2024-07 + M tháng đích; test 52 tuần | như trên | + zero-shot, TGT-only, POOLED, FINE-TUNE, IW-POOLED | như trên theo M |
| E-T1c | Thời điểm trả — thật | Customer Invoices, BPI 2019 | train<2019-12 / 2018-09; test sau | ngày ghi sổ ERP / clear | như trên | như trên |
| E-T1d | Chịu nhiễu đuôi | `sens_uk`, `sens_coface` | mô hình huấn luyện ở `src`; test không thích nghi | | | độ suy giảm so với `src` |
| E-T2a | Nợ xấu — tổng hợp | `src`, `tgt` HĐ đã quá hạn tại T | train<O, test 52 tuần | `is_bad_debt` | quy tắc tuổi nợ TT48, logistic, tỷ lệ nền | PR-AUC, ROC-AUC, Brier, ECE, tổn thất kỳ vọng/thực |
| E-T2b | Nợ xấu — thật | SBA 7(a) | train FY≤2016, cal FY2017, test FY2018–22 | xoá nợ ≤3 năm | tỷ lệ nền, logistic | như trên + hiệu chỉnh theo FY |
| E-T3 | Tranh chấp, trả một phần | `src`→`tgt`, đặc trưng as-of ngày lập | | `dispute`, `partial` | tỷ lệ nền, lịch sử khách | AUC, Brier |
| E-T4 | Doanh thu mới | `src`, `tgt`, Online Retail II | rolling-origin mỗi 4 tuần, 26 tuần cuối | doanh thu tuần | naive mùa vụ, TB 13 tuần, Chronos | SPL (pinball chuẩn hoá), cov80, WAPE |
| E-T5 | Lịch nghĩa vụ | ví dụ văn bản luật | — | ngày đúng luật | — | 100% đúng (15 kiểm thử) |
| E-T6a | Khoảng số dư — tổng hợp | `tgt` 14 công ty × 52 điểm cắt × 13 tuần | O=2024-07 | `daily_cash.balance` | MC độc lập, MC ngày điểm B1, LGBM-Q trực tiếp, naive | cov80, interval score, pinball, CRPS |
| E-T6b | Xác suất thiếu hụt | như trên | | số dư <0 trong 4/13 tuần | | Brier, AUC, lead time |
| E-T6c | Khoảng trên dữ liệu thật | Berka tài khoản-tuần | train 1993–96, test 1997–98 | số dư thật | naive | cov80 (kỳ vọng ngoài phạm vi cấu trúc hoá đơn) |
| E-T7 | Điểm gãy | `tgt`+`sens_uk`+`sens_coface` (giữ lại) | ngưỡng chọn ở `src` | `events` | CUSUM-MAD, trung bình trượt | detection@180d, lag, báo giả/khách-năm |
| E-T8 | Lời hứa | `src` 2024-07→2024-12 | | ngày trả thật | DH-GBM không lời hứa | MAE P50 trên HĐ có lời hứa |
| E-T9 | Khớp sao kê | `tgt` 2024 (toàn bộ) | mô hình học ở 12 công ty `src` 2023 | `payments.txn_id` | R1 đúng số tiền, R2 regex số HĐ | link precision/recall/F1, MAE ngày trả |
| E-T10 | Giải thích | `tgt` điểm cắt có thiếu hụt | | tình huống thiếu hụt | xếp hạng theo số tiền | độ ổn định xếp hạng; mô phỏng chính sách "đòi K khoản đầu" |

## 7.2 Đánh giá chung (end-to-end)

| Mã | Bộ | Kịch bản | Điểm đo |
|---|---|---|---|
| E2E-1 | `tgt` 14 công ty × 52 tuần | Chạy toàn bộ pipeline như sản phẩm: T9 → T1 (fine-tune 12 tháng) → T4 → T5 → T6 + ACI → T10 | cov80 số dư, P(thiếu hụt) Brier/AUC, lead-time, ước lượng giá trị kinh tế (03_Evaluation/06) |
| E2E-2 | Sốc COVID (2021-07→10) và đóng băng tín dụng (2022-10→2023-06) | Cùng pipeline, theo giai đoạn | độ phủ theo chế độ; T7 chuyển chế độ kịp? |
| E2E-3 | `sens_coface` | Không thích nghi | mức xuống cấp có kiểm soát; vẫn đạt cov ≥70% |
| E2E-4 | Mô phỏng chính sách | "Đòi K=5 khoản đầu mỗi tuần" vs "đòi khoản to nhất" vs "không làm gì" | số ngày phải thu giảm, số sự kiện thiếu hụt giảm (mô phỏng, không phải nhân quả) |

## 7.3 Bộ "hard-case chuyên biệt" (đề xuất; chưa sinh)

Mỗi bộ ≈ 12 công ty × 7 năm, bật *đúng một* hard case để cô lập năng lực: `hc_lumpy_customer` (1 khách >40%),
`hc_group_payer` (người trả ≠ khách), `hc_discount_early` (2/10 net 30), `hc_retention` (giữ lại bảo hành),
`hc_fx` (USD), `hc_credit_note` (điều chỉnh/thay thế), `hc_verbal` (thoả thuận miệng không ghi).
Cách bật: thêm cờ vào `WorldConfig` (xem 05_Coding_Agent_Plan/WP-D2).

## 7.4 Quy tắc niêm phong và tái lập

1. `tgt` và các `hc_*`: chỉ dùng ở bước báo cáo cuối; siêu tham số chọn trên `src` (cửa sổ hiệu chỉnh).
2. Mọi bảng kết quả ghi `seed`, hash cấu hình (`config.json`), phiên bản mã (git SHA) vào CSV đầu ra.
3. Tái lập bit-by-bit không bắt buộc (đa luồng LightGBM), nhưng sai khác chỉ số giữa các lần chạy phải <0,5% — kiểm tra bằng 3 seed.
