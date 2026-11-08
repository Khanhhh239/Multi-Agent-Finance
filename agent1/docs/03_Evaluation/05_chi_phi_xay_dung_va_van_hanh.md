# 5. Chi phí xây dựng và vận hành (phía nhà cung cấp sản phẩm)

> **Ước tính kế hoạch tại thời điểm lập, không phải hiện trạng triển khai.** Danh sách “phần còn lại” bên dưới đã cũ ở những mục như API/dashboard; xem [tiến độ hiện hành](../05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md) trước khi lập kế hoạch mới.

**Mọi đơn giá lương/hạ tầng dưới đây là giả định của người lập (mặt bằng VN 2026, cần thay bằng báo giá thật).**
Tính bằng triệu đồng (tr) trừ khi ghi khác. Công thức ở cuối file để tính lại khi đổi giả định.

## 5.1 Chi phí xây dựng

### Giai đoạn A — từ hiện trạng đến sẵn sàng pilot (6 tháng)

Hiện trạng đã có: máy phát dữ liệu, T0/T1/T4/T5/T7/T9 chạy được, bộ đánh giá, tài liệu (chi phí này đã nằm trong
công sức của dự án hiện tại và **không** tính lại ở đây). Phần còn lại: hoàn thiện T2/T3/T6/T8/T10, API, dashboard, kết nối
HĐĐT/sao kê, giám sát, bảo mật, pilot.

| Hạng mục | FTE | Đơn giá tr/tháng | 6 tháng |
|---|---|---|---|
| Kỹ sư ML (T1–T8, thích nghi miền, MLOps) | 1,0 | 60 | 360 |
| Kỹ sư dữ liệu (kết nối HĐĐT/sao kê, pipeline, chất lượng) | 1,0 | 45 | 270 |
| Full-stack (API, dashboard, Zalo OA) | 1,0 | 45 | 270 |
| Product/BA (yêu cầu, UAT, tiếp xúc pilot) | 0,5 | 40 | 120 |
| Kế toán/pháp lý tư vấn (T5, TT48, NĐ13) | 0,3 | 30 | 54 |
| QA/kiểm thử | 0,5 | 30 | 90 |
| **Nhân sự** | | | **1.164** |
| Hạ tầng dev/staging (5 tr/tháng) | | | 30 |
| LLM API cho diễn giải khi phát triển (3 tr/tháng) | | | 18 |
| Rà soát pháp lý bên ngoài (một lần) | | | 30 |
| Hỗ trợ đối tác pilot, đi lại | | | 40 |
| Dự phòng 15% | | | 192 |
| **Tổng giai đoạn A** | | | **≈ 1.474 (~1,5 tỷ)** |

### Giai đoạn B — pilot và hardening (6 tháng tiếp)

| Hạng mục | 6 tháng |
|---|---|
| Nhân sự: ML 0,8×60 + DE 0,5×45 + FS 1,0×45 + PM 0,5×40 + QA 0,5×30 + kế toán 0,3×30 = 159,5 tr/tháng | 957 |
| Hạ tầng + giám sát (10 tr/tháng) | 60 |
| Hỗ trợ khách pilot | 30 |
| Dự phòng 15% | 157 |
| **Tổng giai đoạn B** | **≈ 1.204 (~1,2 tỷ)** |

**Tổng đầu tư năm 1 ≈ 2.680 tr (~2,7 tỷ đồng).**

### Chi phí đã bỏ vào phần hiện có (để tham khảo, không cộng thêm)
Máy phát + 8 nguồn thật + mô hình T0/T1/T4/T5/T7/T9 + tài liệu: ước ~8–12 tuần người làm; mã ~5.000 dòng Python; tính toán CPU ~30 giờ máy.

## 5.2 Chi phí vận hành

### Biến đổi theo mỗi khách hàng (tr/tháng/khách)

| Hạng mục | Giả định | Chi phí |
|---|---|---|
| Tính toán batch đêm | ≤5 phút CPU/DN/đêm ≈ 2,5 giờ CPU/tháng; ~1.000đ/vCPU-giờ; ×4 vCPU | 0,010 |
| Lưu trữ | ~100 MB/DN | ~0 |
| LLM diễn giải (≈20 cảnh báo × 1.500 token) | ~30k token/tháng | 0,003 |
| Hỗ trợ khách | 1 CSKH (20 tr/tháng) / 150 khách | 0,133 |
| MLOps/giám sát | 0,5 FTE (30 tr) / 300 khách | 0,050 |
| **Tổng biến đổi** | | **≈ 0,196 (~0,2 tr)** |

### Cố định sau năm 1 (tr/tháng)
Đội 5 người (ML, DE, FS, PM, QA bán thời gian) ≈ 160 + hạ tầng nền 15 = **175 tr/tháng** (2,1 tỷ/năm).

## 5.3 Biên và điểm hoà vốn

Giá: Starter 0,75 tr/tháng, Growth 1,5 tr/tháng; hỗn hợp 50/50 → **1,125 tr/tháng**.

| Chỉ số | Giá trị |
|---|---|
| Biên gộp Starter | (0,75 − 0,196)/0,75 = **74%** |
| Biên gộp Growth | (1,5 − 0,196)/1,5 = **87%** |
| Đóng góp trên mỗi khách (hỗn hợp) | 1,125 − 0,196 = **0,929 tr/tháng** |
| Hoà vốn vận hành | 175 / 0,929 = **≈ 188 khách** |

Thời gian thu hồi đầu tư 2,68 tỷ sau khi đạt số khách ổn định:

| Số khách ổn định | Lãi vận hành/tháng (tr) | Thu hồi 2,68 tỷ |
|---|---|---|
| 188 | 0 | không bao giờ |
| 250 | 57 | ~47 tháng |
| 300 | 104 | ~26 tháng |
| 400 | 197 | ~14 tháng |
| 600 | 382 | ~7 tháng |

So với SOM 3 năm 1.500–3.000 DN (05_thi_truong): **kịch bản 300–400 khách trong 18–24 tháng đầu là khả thi nhưng
phải qua kênh đối tác** (phần mềm kế toán/ngân hàng/văn phòng kế toán); bán trực tiếp khó đạt.

## 5.4 Chi phí bên mua (để so với lợi ích)

| Hạng mục | Chi phí cho SME mẫu |
|---|---|
| Thuê bao Growth | 18 tr/năm |
| Onboard (kết nối HĐĐT/sao kê, 1 buổi + 2 giờ kế toán) | ~0,5 tr |
| Thời gian xem dự báo + hành động (0,5 giờ/tuần × 52 × 80k) | ~2,1 tr |
| **Tổng chi phí sở hữu năm 1** | **≈ 20,6 tr** |

## 5.5 Công thức (để thay giả định)

```
CAPEX_A = Σ(FTE × đơn giá × 6) + hạ tầng + pháp lý + hỗ trợ ; ×1,15
OPEX_cố_định/tháng = Σ(FTE × đơn giá) + hạ tầng nền
Đóng góp/khách = giá_bq − chi_phí_biến_đổi
Hoà vốn (khách) = OPEX_cố_định / đóng góp ;  Thu hồi (tháng) = CAPEX / (N·đóng góp − OPEX_cố_định)
```
