# T9 — G15 trượt ở đâu và vì sao (chẩn đoán, 22/10/2026, agent1-Khanh)

> Chẩn đoán trên tgt chỉ để hiểu lỗi, **không** dùng để chọn tham số. Mọi sửa đổi phải chọn lại trên nguồn.
> **Đính chính:** báo cáo miệng trước đó "T9 recall 0,47, F1 0,63" là số của **quy tắc R1**, không phải phương pháp triển khai.

## 1. Phương pháp triển khai trượt sát nút (`outputs/t9/sprint3/target_metrics.csv`)

| Thế giới | Phương pháp | Precision [CI] | Recall | F1 [CI] | Tự động | MAE ngày |
|---|---|---|---|---|---|---|
| src (công ty giữ lại) | chọn trên nguồn, τ = 0,5 | 0,955 | 0,727 | 0,826 | 0,749 | 0,80 |
| **tgt** | **Deployment source-selected** | **0,925 [0,88; 0,97]** | 0,699 | **0,796 [0,71; 0,87]** | 0,751 | 1,85 |
| tgt | Hybrid baseline τ = 0,9 | 0,940 | 0,661 | 0,776 | 0,710 | 1,26 |
| tgt | R1 (quy tắc số tiền duy nhất) | 0,965 | 0,472 | 0,634 | 0,583 | 0,58 |
| hc_retention | Deployment | 0,815 | 0,568 | 0,670 | — | — |
| hc_cod_realistic | Deployment | 0,899 | 0,652 | 0,756 | — | — |

Cổng G15: F1 ≥ 0,80 **(0,796, trượt 0,004)**, precision ≥ 0,95 **(0,925, trượt)**, tự động ≥ 0,6 (đạt), MAE ≤ 3 ngày (đạt).
⇒ Vấn đề chính trên tgt là **precision giảm 3 điểm** so với nguồn, không phải recall. Hard case `retention` khó nhất.

## 2. Phân rã lỗi theo nhóm (bộ ghép CŨ `ML_subset`)

Phân rã cũ từng dùng `outputs/t9/t9_links_tgt.parquet`, nhưng file này không
còn trong workspace ngày 27/10/2026. Phương pháp triển khai không lưu file liên
kết theo giao dịch cho tgt, nên phân rã dưới đây dùng bộ ghép cũ (recall 0,57)
và hiện không thể tái tính từ artifact đó.
Các mẫu hình nhiều khả năng vẫn đúng một phần với phương pháp mới, nhưng **cần đo lại** khi phương pháp triển khai xuất liên kết.

| Yếu tố | Nhóm | Recall (bộ cũ) | Số liên kết |
|---|---|---|---|
| Loại thanh toán | trả đủ | 0,683 | 6.537 |
| | từng phần / phần cuối / thu hồi | ≈ 0 | 1.315 (17%) |
| Ghi sổ | hằng ngày / tuần / **tháng** | 0,844 / 0,580 / **0,510** | 666 / 3.452 / 3.734 |
| HĐ / chuyển khoản | 1 / 2 / **≥ 3** | 0,711 / 0,603 / **0,214** | 4.809 / 1.028 / 2.015 |
| Nội dung CK có số HĐ | không / có | 0,538 / 0,588 | 3.000 / 4.852 |

Trên nguồn (phương pháp mới, `source_allocation_diagnostics.csv`): `partial_payment` 611 giao dịch, tp 21, fn 1.346 ⇒
thanh toán từng phần **gần như không ghép được ở cả phương pháp mới**; `wrong_customer` 124 giao dịch đều thành fp (nguồn của precision mất).

## 2b. Thí nghiệm lớp chặn bằng chứng (22/10/2026, `scripts/sprint5/t9_guard.py`, `outputs/t9/sprint5/`)

Giả thuyết: ghép sai do liên kết qua mô hình khách có độ tin cậy thấp ⇒ dưới ngưỡng g, đòi số HĐ trong nội dung CK hoặc tên khớp ≥ 90.
Lưới g ∈ {none, .7, .8, .9, .95} × τ ∈ {.5….9} trên DN nguồn giữ lại: **mọi cấu hình cho cùng kết quả** (P 0,951–0,952, F1 0,850–0,853)
⇒ quy tắc chọn đã đăng ký giữ τ = 0,5, không chặn. tgt tái lập đúng (P 0,925, F1 0,796). **Giả thuyết bị bác.**

## 2c. Liên kết sai đến từ đâu (`scripts/sprint5/t9_method_breakdown.py`, `outputs/t9/sprint5/method_breakdown.csv`)

| Phương pháp tạo liên kết | Precision src / tgt | Số liên kết tgt | Tỷ trọng liên kết sai tgt | Độ tin cậy khách trung vị |
|---|---|---|---|---|
| `R2_memo` (số HĐ trong nội dung CK) | 1,000 / 1,000 | 1.636 | 0% | 1,0 |
| `memo_partial_residual` | 1,000 / 1,000 | 162 | 0% | 1,0 |
| `R1_unique_amount` | 0,963 / 0,953 | 2.676 | 28% | 1,0 |
| `ML_subset` | 0,872 / **0,813** | 1.284 | **54%** | 1,0 |
| `hazard_weighted_subset` | **0,542 / 0,500** | 158 | 18% | 1,0 |

**Đọc kết quả:**
- Mô hình gán khách **tự tin quá mức**: trung vị độ tin cậy 1,0 kể cả ở liên kết sai ⇒ mọi lớp chặn theo độ tin cậy đều vô tác dụng.
- `hazard_weighted_subset` đúng một nửa **ngay trên nguồn** (0,54) — không nên tự động.
- `ML_subset` dưới 0,95 trên nguồn (0,872) và tệ hơn trên tgt.
- Quy tắc dựa số HĐ không bao giờ sai ⇒ hướng đúng là tăng phần dựa số HĐ, giảm phần đoán tổ hợp.

**Vì sao KHÔNG sửa luôn rồi báo G15 đạt:** phân rã theo phương pháp ở trên đã nhìn tgt, nên tgt không còn sạch cho quyết định
"tắt phương pháp nào". Theo quy tắc chọn đã đăng ký (F1 tối đa với P ≥ 0,95 trên nguồn), cấu hình hiện tại vẫn được chọn
(bỏ `hazard_weighted_subset` cho P nguồn ≈ 0,959 nhưng F1 ≈ 0,850 < 0,853).

## 3. Đề xuất (chọn trên nguồn, đo một lần trên tgt)
| # | Việc | Cổng bị ảnh hưởng |
|---|---|---|
| 0 | **Đăng ký trước** luật "phương pháp có precision NGUỒN < 0,95 không được tự động (vào hàng chờ)" ⇒ tắt `hazard_weighted_subset` (0,54) và `ML_subset` (0,87); đo trên **bộ đích mới `tgt3`** (seed mới, có XML), vì tgt đã bị nhìn cho quyết định này | precision |
| 0b | Hiệu chỉnh lại xác suất gán khách (trung vị 1,0 kể cả khi sai) — isotonic theo khách mới/khách cũ | precision |
| 1 | ~~Xuất liên kết theo giao dịch~~ — xong (mục 2c) | chẩn đoán |
| 2 | **Giảm fp `wrong_customer`**: yêu cầu khớp tên người chuyển hoặc số HĐ khi khách khác khách dự đoán; đưa vào hàng chờ thay vì tự động | precision (cần +2,5 điểm) |
| 3 | **Phân bổ từng phần**: liên kết `partial` khi số tiền < số còn nợ và có số HĐ hoặc khách chỉ còn một HĐ mở | recall |
| 4 | Doanh nghiệp ghi sổ theo tháng: đặc trưng dựa ngày giá trị NH, không dựa ngày ghi sổ | recall |

## 4. Kết quả T9 v2 (đăng ký trước, đo một lần trên tgt3 sạch) — xem `G15_T9_V2_PREREG.md` mục 6
Giới hạn tổ hợp đoán ≤ 2 HĐ + tắt `hazard_weighted_subset`: precision tgt3 **0,962** (đạt), F1 **0,706** (trượt, recall 0,557).
Phân bổ FIFO cho thanh toán từng phần bị loại trên nguồn (precision 0,19–0,26).

G15 không chặn bậc 0 "bóng": ở bậc 0, T9 chỉ cung cấp nhãn, và E2E với nhãn T9 ước lượng đã đạt G12.
