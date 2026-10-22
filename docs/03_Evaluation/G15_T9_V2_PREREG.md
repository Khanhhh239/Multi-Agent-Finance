# G15 — T9 v2: đăng ký trước (22/10/2026, agent1-Khanh)

> Viết và commit **trước khi** sinh `tgt3`. Không sửa mục 1–5 sau khi có số trên `tgt3`.

## 1. Căn cứ (chỉ từ nguồn; `outputs/t9/sprint5/source_strata.csv`)
Liên kết "đoán" trên DN nguồn giữ lại (2024H1), precision theo số HĐ trong tổ hợp:

| | 1 HĐ | 2 HĐ | ≥ 3 HĐ |
|---|---|---|---|
| `ML_subset` | 0,989 (274) | 0,973 (748) | **0,736** (793) |
| `hazard_weighted_subset` | 1,000 (6) | 0,958 (24) | **0,468** (173) |

Điểm tên người chuyển không phân biệt đúng/sai (hầu hết ≥ 90) ⇒ lỗi chủ yếu là **chọn sai tổ hợp HĐ**, không phải sai khách.
Thanh toán từng phần gần như không được ghép (nguồn: `partial_payment` tp 21 / fn 1.346).

## 2. Biến thể (τ = 0,5 cố định — đổi τ không có tác dụng, mục 2b của T9_RECALL_DIAGNOSIS)
`agent1/models/t9_fast.py::reconcile_arrays`, 12 biến thể = 3 × 2 × 2:
- `max_guess_subset` ∈ {không giới hạn, 2, 1}: liên kết đoán có nhiều HĐ hơn thì vào hàng chờ;
- `hazard_subsets` ∈ {bật, tắt};
- `fifo_allocation` ∈ {tắt, bật}: khách đã gán đủ tin cậy mà không tổ hợp nào khớp ⇒ phân bổ theo hạn sớm nhất, HĐ cuối trả một phần.

## 3. Quy tắc chọn (trên DN nguồn giữ lại, 2024H1)
1. **Đủ điều kiện:** precision tổng ≥ **0,975** (= 0,95 của cổng + biên chuyển miền 2,5 điểm, bằng mức rơi đã thấy của cấu hình hiện tại
   0,951 → 0,925), **và** mọi phương pháp tự động có ≥ 30 liên kết đạt precision nguồn ≥ 0,95, **và** tự động ≥ 0,6.
2. Trong các biến thể đủ điều kiện: F1 cao nhất; hoà thì tự động cao hơn.
3. Không biến thể nào đủ điều kiện ⇒ dùng quy tắc cũ (P ≥ 0,95, tự động ≥ 0,6, F1 cao nhất) và ghi `fallback_rule=True`.

## 4. Bộ đánh giá (đo **một lần**, không chỉnh sau khi xem)
- **`tgt3` (chính, cho dòng cổng `G15_tgt3`):** cấu hình y hệt `tgt` (`data/synthetic/tgt/config.json`), seed **7310**, **30 công ty**,
  sinh sau khi commit tài liệu này; niêm phong.
- Phụ (chỉ báo cáo): `tgt2` (chưa từng dùng cho T9), `hc_retention`, `hc_cod_realistic`, và `tgt` (đã bị nhìn — chỉ để nối số liệu).
- Cửa sổ: giao dịch 2024-07-01 → 2025-06-29 (giống sprint3).

## 5. Tiêu chí cổng (không đổi)
F1 ≥ 0,80; F1 > max(F1 của R1, R2) trên cùng thế giới; precision ≥ 0,95; tự động ≥ 0,6; MAE ngày trả ≤ 3.
Dòng `G15` cũ (tgt, cấu hình sprint3) giữ nguyên để kiểm toán.

## 6. Kết quả
_Điền sau khi chạy `scripts/sprint5/t9_v2.py`._
