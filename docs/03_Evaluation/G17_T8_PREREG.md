# G17 — T8 lời hứa: thêm 6 đặc trưng quan sát được (đăng ký trước, 22/10/2026, agent1-Khanh)

> Commit **trước khi** chạy `scripts/sprint5/g17_promise_features.py`. Mục 1–4 không đổi sau khi xem kết quả.

## 1. Căn cứ
G17: mô hình CÓ lời hứa giảm MAE (trên hoá đơn có lời hứa) ≥ 10% so với mô hình KHÔNG có lời hứa, ở cả lời hứa sạch và nhiễu.
Hiện tại (`outputs/t1/EF_t8_t9*.csv`): sạch 11,24 vs 13,85 (**−18,8% ✓**); nhiễu 12,85 vs 13,90 (**−7,6% ✗**, thiếu 2,4 điểm).
Mô hình chỉ dùng 5 đặc trưng lời hứa (`has_promise`, `days_to_promised`, `promise_overdue`, `c_promise_rel`, `c_promise_n`).
Chế độ nhiễu (`world.py`, `promises_mode='noisy'`): ngày hứa lệch t(3)×7 ngày; 15% khách chỉ hứa miệng (không ghi); loại hứa exact/vague/partial;
30% lời hứa thất bại được hứa lại. Bảng lời hứa **đã chứa** `promised_date_lo/hi`, `promised_fraction`; mô hình hiện chưa dùng chúng, cũng chưa dùng lịch sử hứa lại.

## 2. Sáu đặc trưng (cố định trước, KHÔNG chọn lọc), tính "as-of" ngày cắt T từ dữ liệu có từ trước T
| Tên | Định nghĩa |
|---|---|
| `prom_width_days` | (`promised_date_hi` − `promised_date_lo`) của lời hứa gần nhất có `made_date` ≤ T (độ mơ hồ) |
| `prom_fraction` | `promised_fraction` của lời hứa gần nhất (hứa trả một phần) |
| `prom_n_inv` | số lời hứa đã ghi trên hoá đơn đó, `made_date` ≤ T |
| `prom_n_broken_inv` | số lời hứa trên hoá đơn đó đã tới hạn xác minh (`promised_date` + 3 ≤ T) mà `kept` = False |
| `prom_age_days` | T − `made_date` của lời hứa gần nhất |
| `c_prom_lag` | độ lệch trung bình (ngày trả thật − ngày hứa) của khách trên các lời hứa đã có ngày trả thật ≤ T, co về 0 với hệ số 6 (EB) |

## 3. Thiết kế đo (đúng `exp_EF`: huấn luyện cutoff < 2024-07-01, kiểm 26 tuần sau)
Ba mô hình DH-GBM trên mỗi thế giới `src` (sạch) và `src_noisy_promises` (nhiễu), cùng snapshot:
(B) không có lời hứa; (A) 5 đặc trưng hiện tại; (**C**) 5 hiện tại + 6 mới. Chỉ số: MAE_p50 trên hoá đơn có lời hứa. CI 95% bootstrap theo công ty cho tỉ lệ giảm so với B.

## 4. Tiêu chí
Dòng `G17_v2` đạt nếu **C** giảm ≥ 10% so với B ở **cả** sạch và nhiễu (điểm ước lượng), và C không tệ hơn A quá 1% ở sạch.
Không đổi bộ đặc trưng nếu kết quả không đạt (báo cáo như vậy).
**Giới hạn biết trước:** cửa sổ kiểm của `src`/`src_noisy_promises` đã bị nhìn ở lần chạy G17 trước; vì bộ đặc trưng cố định một lần (không chọn lọc), rủi ro chọn theo kết quả thấp,
nhưng đây không phải bộ niêm phong.

## 5. Kết quả
_Điền sau khi chạy._
