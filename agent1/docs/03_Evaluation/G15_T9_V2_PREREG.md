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

## 6. Kết quả (22/10/2026; đăng ký trước commit `5f94cc8` lúc 10:01, tgt3 sinh sau đó; `outputs/t9/v2/`)

**Chọn trên nguồn** (`source_grid.csv`): 3/12 biến thể đủ điều kiện; chọn **`cap=2 | hazard=off | fifo=off`**
(P 0,979, R 0,722, F1 0,831, tự động 0,776; precision từng phương pháp: ML_subset 0,979, R1 0,963, R2 1,0, memo_partial 1,0).
Phân bổ FIFO bị loại ngay trên nguồn: precision của nó 0,19–0,26 (khách trả từng phần **không** theo thứ tự hạn).
Không dùng quy tắc dự phòng.

**Đo một lần** (`target_metrics.csv`), CI bootstrap theo công ty:

| Thế giới | Phiên bản | Precision [CI] | Recall | F1 [CI] | Tự động | MAE ngày |
|---|---|---|---|---|---|---|
| **tgt3 (chính)** | sprint3 | 0,899 [0,85; 0,93] | 0,603 | 0,722 [0,64; 0,80] | 0,717 | 2,53 |
| **tgt3 (chính)** | **v2** | **0,962 [0,94; 0,98]** | 0,557 | **0,706 [0,63; 0,78]** | 0,689 | **0,82** |
| tgt2 | sprint3 → v2 | 0,917 → **0,966** | 0,688 → 0,636 | 0,786 → 0,767 | 0,738 → 0,715 | 1,92 → 0,62 |
| hc_retention | sprint3 → v2 | 0,815 → 0,902 | 0,568 → 0,560 | 0,670 → 0,691 | 0,665 → 0,646 | 6,20 → 2,42 |
| hc_cod_realistic | sprint3 → v2 | 0,899 → 0,949 | 0,652 → 0,632 | 0,756 → 0,758 | 0,723 → 0,711 | 3,03 → 1,41 |
| tgt (đã nhìn) | sprint3 → v2 | 0,925 → 0,972 | 0,699 → 0,643 | 0,796 → 0,774 | 0,751 → 0,726 | 1,85 → 0,45 |

Quy tắc R1/R2 trên tgt3: F1 0,595 / 0,244 ⇒ v2 thắng quy tắc.

**Cổng `G15_tgt3`: TRƯỢT** — precision 0,962 ≥ 0,95 ✓, tự động 0,689 ✓, MAE 0,82 ✓, thắng quy tắc ✓, nhưng **F1 0,706 < 0,80** ✗.

**Đọc kết quả:**
- **Precision đã sửa được và chuyển miền tốt:** nguồn 0,979 → tgt3 0,962 (rơi 1,7 điểm, trong biên 2,5 đã đặt); đạt ≥ 0,95 ở tgt3, tgt2, tgt.
  Ngày trả ước lượng chính xác hơn 2–3 lần ở mọi thế giới (vì bỏ các tổ hợp đoán sai).
- **Recall là nút thắt:** đổi lấy precision, recall giảm 2–6 điểm. tgt3 khó hơn tgt (ngay cấu hình cũ chỉ F1 0,722).
  Để F1 ≥ 0,80 ở precision ~0,96 cần recall ≈ 0,69 — thiếu ~13 điểm trên tgt3.
- Phần recall còn thiếu nằm ở: thanh toán từng phần không có số HĐ (FIFO không giải được — đã đo), chuyển khoản gộp ≥ 3 HĐ (nay vào hàng chờ),
  DN ghi sổ theo tháng. Đây là bài toán thông tin, không phải tinh chỉnh: không có số HĐ trong nội dung CK thì nhiều liên kết không xác định được.
- **Khuyến nghị vận hành:** dùng v2 (liên kết tự động đáng tin hơn, ngày trả chính xác hơn), phần còn lại vào hàng chờ người duyệt (~31% giao dịch).
  Đòn bẩy recall lớn nhất nằm ngoài mô hình: khuyến khích khách ghi số HĐ khi chuyển khoản (R2 luôn đúng 100%).
