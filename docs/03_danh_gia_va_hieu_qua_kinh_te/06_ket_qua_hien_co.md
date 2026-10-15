# Kết quả đã có

**Tất cả là dữ liệu tổng hợp [M]; không phải bằng chứng về doanh nghiệp thật.** Ngân sách B3 (3 cảnh báo mỗi công ty mỗi tuần, khoảng 76 cảnh báo trên 1.000 dòng ở v4). Tệp thô: `results/`.

## 1. v3 (8 công ty; 5 seed; theo thời gian)

| Phương pháp | AP | Recall@B3 | Báo nhầm ca khó |
|---|---:|---:|---:|
| 31 luật tay của bạn bạn | 0,240 ± 0,019 | 31% | 2,9% |
| Isolation Forest, 190 đặc trưng | 0,021 ± 0,013 | 10% | 13,1% |
| ECOD / HBOS | 0,005 / 0,004 | 5% / 4% | 5% |
| Autoencoder | 0,065 ± 0,020 | 33% | 20,3% |
| EntityDeviation (nhãn không cần) | 0,012 ± 0,002 | 17% | 7,8% |
| Ensemble 80/20 của bạn bạn | 0,163 ± 0,023 | 34% | 7,7% |
| Luật học lại trọng số | 0,387 ± 0,019 | 48% | 3,7% |
| LightGBM 190 đặc trưng | 0,633 ± 0,046 | 75% | 11,9% |
| LightGBM + thực thể + luật | 0,817 ± 0,022 | 89% | 16,1% |

**Tập niêm phong v3** (3 họ mới, chạy đúng một lần; ngân sách B3): luật tay 29%; CES 2+1 recall 53% (họ mới 17,5%, báo nhầm 7,0%); LightGBM 2+1 recall 83% (họ mới 58,7%, báo nhầm 10,9%). Một phần phần thắng của LightGBM do bộ sinh chia sẻ cơ chế (lương luôn ngày 28).

## 2. v4: benchmark theo thời gian (3 thế giới 411 đến 413, 15 phương pháp)

| Phương pháp | AP | Recall@B3 | Vụ tìm thấy@B3 | Báo nhầm ca khó |
|---|---:|---:|---:|---:|
| Luật + đồ thị | 0,079 ± 0,022 | 27,0% | 42,7% | 16,5% |
| IF, 190 đặc trưng (đường cơ sở của bạn bạn) | 0,004 | 7,0% | 18,4% | 23,0% |
| Autoencoder | 0,096 ± 0,015 | 37,0% | 60,4% | 32,2% |
| EntityDeviation | 0,025 ± 0,006 | 34,5% | 52,6% | 13,4% |
| max(Luật, Entity) | 0,078 ± 0,043 | 39,4% | 59,8% | 15,6% |
| Ensemble 80/20 của bạn bạn | 0,026 ± 0,008 | 21,6% | 37,9% | 20,1% |
| Luật học lại trọng số | 0,116 ± 0,041 | 28,8% | 52,1% | 10,4% |
| LightGBM, 190 đặc trưng | 0,069 ± 0,071 | 42,1% | 61,6% | 14,0% |
| LightGBM + 46 đặc trưng thêm | 0,566 ± 0,053 | 76,9% | 85,8% | 18,8% |
| LightGBM + 46 đặc trưng + luật (L3) | **0,577 ± 0,058** | **77,5%** | 87,0% | 16,5% |
| max(L3, Luật, Entity) | 0,281 ± 0,056 | 76,0% | **90,5%** | 14,6% |

Chênh lệch chính: 15 dấu hiệu đỏ v4 nâng LightGBM từ AP 0,07 lên 0,57; **cùng tác giả viết bộ sinh và đặc trưng, nên đây là giới hạn trên**.

**Theo mức che giấu (Recall@B3):** luật 43 → 30 → 20; EntityDeviation 31 → 37 → 35; LightGBM 190 đặc trưng 55 → 41 → 36; L3 91 → 79 → 69 (L0 → L1 → L2).

**Kịch bản khó nhất với L3 (recall@B3):** payroll_padding 4%, vendor_burst 27%, price_creep 39%, expense_duplicate_claim 47%, kickback_overpricing 48%, personal_purchase 51%, off_cycle_payroll 52%, split_payments 55%. Với EntityDeviation: payroll_padding 79%, price_creep 86% (kênh không nhãn bổ sung cho mô hình có giám sát).

**Bỏ-một-kịch bản (thế giới 411, 30 lần huấn luyện, trung bình recall@B3):** luật 30,4%; EntityDeviation 31,8%; LightGBM 190 đặc trưng 35,7%; max(Luật, Entity) 44,9%; L3 62,2%; max(L3, Luật, Entity) 70,2%. Không phương pháp nào bắt được `ghost_employee` khi chưa thấy (0%). Mỗi kịch bản chỉ có 1 đến 27 dòng dương ở kiểm thử: dùng để xếp hạng, không dùng để báo cáo độ chính xác.

## 3. v4: so sánh phương pháp lai (một phần; chưa đủ để chọn)

Các thế giới 411 (P1 và P2 xong) và 412 (P1 xong). Ngân sách B3. L4 thêm điểm của các bộ phát hiện không nhãn làm đặc trưng; "-FB" cân bằng trọng số theo họ; "C-" là mô hình hai tầng có trí nhớ 90 ngày theo thực thể; "2+1" là 2 khe mô hình chính và 1 khe kênh không nhãn.

| Cấu hình | P1 recall (411) | P1 recall (412) | Báo nhầm ca khó (411, 412) | P2 trung bình nhánh (411) |
|---|---:|---:|---|---:|
| Luật + đồ thị | 22,4% | 35,9% | 15,8%; 16,1% | 22,0% |
| Novelty max(R,E) | 34,5% | 52,6% | 14,9%; 15,6% | 38,8% |
| Novelty max(R,E,AE) | 39,9% | 53,8% | 23,6%; 24,7% (vượt 20%) | 52,9% |
| L3 | 74,4% | 78,6% | 18,0%; 17,4% | 52,3% |
| L3-FB | 71,7% | 77,8% | 19,0%; 15,0% | 63,3% |
| L4 | 77,6% | 80,3% | 18,4%; 16,5% | 66,6% |
| L4-FB | 78,5% | 80,8% | 19,1%; 16,7% | 63,4% |
| C-L4 | 77,1% | 77,8% | 17,2%; 13,7% | 55,4% |
| C-L4-FB | 76,7% | 79,5% | 17,2%; 13,1% | 56,5% |
| L3 2+1 Novelty max(R,E) | 75,3% | 79,1% | 17,1%; 16,8% | 63,7% |
| L4-FB 2+1 Novelty max(R,E) | 74,9% | 80,8% | 17,6%; 15,6% | 68,0% |
| max(L3, Novelty) | 74,9% | 79,9% | 15,4%; 14,7% | 64,5% |
| max(L4-FB, Novelty) | 76,2% | 79,9% | 16,4%; 13,9% | 69,6% |

**Đọc kết quả (thận trọng):**
1. Trong phân phối (P1), L4 hơn L3 khoảng 2 đến 4 điểm phần trăm: nằm trong sai số (khoảng 3 điểm với khoảng 200 dòng dương).
2. Khi ẩn một nhánh (P2, thế giới 411), các cấu hình có điểm không nhãn (L4, L4-FB, kết hợp với Novelty) cho trung bình nhánh cao hơn L3 (63 đến 70% so với 52%). Nhưng mỗi nhánh chỉ có 2 đến 57 dòng dương và mới có một thế giới: **chưa kết luận**.
3. Mô hình hai tầng (C-) **không cải thiện** AP (0,41 đến 0,50 so với 0,53 đến 0,55 của L3): giả thuyết "trí nhớ theo thực thể giúp" hiện bị bác bỏ ở mức P1.
4. Kênh Novelty có AE bị loại theo quy tắc chọn đã đăng ký vì báo nhầm vượt 20%.

## 4. Vòng phản hồi (52 tuần, 5 seed; số dòng gian lận tìm được)
Không học: 58. Nới ngưỡng: 58 → 52 → 48 khi nhiễu nhãn 0 → 15 → 30%. Học lại trọng số kiểu Active Anomaly Discovery: 83 → 79 → 54. Nghĩa là học từ phản hồi có ích, nhưng nhạy với nhãn sai.

## 5. Dữ liệu ngoài
ERP Fraud Data và DFKI: không phương pháp nào thắng ổn định; xem [dữ liệu 02](../02_du_lieu/02_nguon_cong_khai_dung_va_khong_dung.md).
