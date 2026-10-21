# G13 — Chính sách cảnh báo thiếu hụt tiền (đăng ký trước 21/10/2026, agent1-Khanh)

> Viết **trước khi** chạy `scripts/sprint5/g13_policy.py`. Không sửa mục 1–3 sau khi xem kết quả tgt.

## 1. Vì sao G13 trượt (E2E `cash-e2e-estimated_T9-v1-fullweek`)
MC-copula-t, chi phí 5, 13 tuần: phát hiện ≥4 tuần 0,94, độ sớm trung vị 12 tuần, nhưng **báo động giả 2,58/công ty-năm** (cổng ≤1).
Nguyên nhân: ngưỡng chọn bằng chi phí **theo từng tuần** trên 144 điểm nguồn (16 công ty × 9 gốc), ra τ = 0,02.
Thước đo của cổng lại tính **theo đợt cảnh báo**. Hai đơn vị khác nhau, nên ngưỡng tối ưu theo tuần quá thấp với cổng theo đợt.

## 2. Chính sách (đăng ký trước)
| Thành phần | Lựa chọn |
|---|---|
| Dữ liệu chọn | Backtest T6 đầy đủ trên **src** (40 công ty, 52 tuần từ O = 2024-07-01, nhãn số dư thật src, 27 sự kiện), `scripts/sprint5/g13_source_backtest.py` |
| Hiệu chỉnh | `raw` và `isotonic`; isotonic ngoài-fold theo công ty (5 fold) khi chọn; khi áp lên tgt dùng isotonic học trên toàn bộ src |
| Tham số | τ ∈ {0,05; 0,10; …; 0,95} × xác nhận k ∈ {1, 2, 3} tuần liên tiếp |
| Tiêu chí chọn | Trong các chính sách có báo động giả trên src ≤ **0,8**/công ty-năm: tối đa tỷ lệ phát hiện ≥4 tuần, rồi độ sớm trung vị, rồi ít báo động giả nhất. Không có chính sách khả thi ⇒ chọn ít báo động giả nhất và ghi `feasible_on_source=False` |
| Thước đo | Không đổi: `agent1/eval/alerts.py::event_metrics` (sự kiện = ngày bắt đầu số dư âm; phát hiện nếu cảnh báo sớm ≥4 tuần trong cửa sổ 13 tuần; báo động giả = đợt cảnh báo mà 13 tuần sau không âm) |
| Mô hình cho cổng | MC-copula-t (T1+T4+T5), 13 tuần, **calibration = isotonic** (đăng ký trước); các mô hình/biến thể khác chỉ báo cáo |
| CI | Bootstrap theo công ty, 200 lần |

## 3. Tiêu chí cổng G13 (không đổi so với v1)
`n_events > 0`, phát hiện ≥4 tuần ≥ 0,70, độ sớm trung vị ≥ 4 tuần, báo động giả ≤ 1,0/công ty-năm, đo trên tgt E2E.
Dòng v1 giữ tên `G13_v1` để kiểm toán.

**Giới hạn biết trước:** tgt chỉ có 16 sự kiện / 7 công ty ⇒ CI phát hiện sẽ rộng; đạt điểm ước lượng không đủ để kết luận vững.

## 4. Kết quả (21/10/2026, `g13-isotonic-confirm-v1`, chính sách chọn trên backtest src rồi đóng băng)

Chính sách cho cổng: MC-copula-t, isotonic, **τ = 0,30, k = 1** (trên src: phát hiện 0,70, báo giả 0,75/công ty-năm).

| Bộ đánh giá | Sự kiện | Phát hiện ≥4 tuần [CI 95%] | Độ sớm trung vị | Báo giả/công ty-năm [CI] | Cổng |
|---|---|---|---|---|---|
| `tgt` E2E (nhãn T9 ước lượng, 14 công ty) | 16 | 0,94 [0,87; 1,00] | 11,6 tuần | **2,08** | **trượt** |
| **`tgt2` niêm phong** (nhãn oracle, 40 công ty) | 71 | **0,746 [0,59; 0,84]** | 7,0 tuần | **0,75 [0,43; 1,10]** | **đạt (điểm ước lượng)** |

**Đọc kết quả:**
- Hai bộ đích cho kết luận khác nhau. `tgt` có hành vi lệch mạnh hơn và nhãn T9 ước lượng (nhiễu hơn); `tgt2` dùng nhãn thật nên là **cận trên**.
- Trên `tgt2`, CI của phát hiện (0,59) và báo giả (1,10) đều chạm ngưỡng ⇒ đạt ở điểm ước lượng, **chưa vững**.
- So đối chứng trên `tgt2`: naive phát hiện 0,49; MC với ngày B1 0,52 ⇒ copula-t có giá trị thật so với mốc.
- **Kết luận vận hành:** cảnh báo dùng được làm **gợi ý có người duyệt** (bậc 2 trong GO_NO_GO), không tự động. Không chỉnh ngưỡng theo tgt/tgt2.
