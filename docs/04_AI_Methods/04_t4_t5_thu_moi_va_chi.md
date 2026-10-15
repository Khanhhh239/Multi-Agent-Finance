# 4. T4 doanh thu mới · T5 lịch chi tất định

## 4.1 T4 — Doanh thu mới chưa lập hoá đơn

Vì sao cần: dự báo 13 tuần không thể chỉ nhìn công nợ đang có — hoá đơn lập trong 13 tuần tới (đặc biệt COD/kỳ hạn ngắn) đóng góp
phần lớn dòng thu các tuần xa; bỏ qua sẽ đánh giá thiếu hụt quá cao.

### Mô hình chính — `GlobalQuantileLGBM` (`agent1/models/t4_revenue.py`)
- **Toàn cục** (một mô hình cho mọi chuỗi), **trực tiếp đa chân trời** (`h` là đặc trưng), 3 mô hình alpha 0,1/0,5/0,9.
- **Chuẩn hoá quy mô:** mọi đặc trưng và mục tiêu chia cho `s = mean(13 tuần gần nhất) + 1e-9` → bất biến đơn vị VND/GBP, học chung nhiều công ty.
- Đặc trưng (27): 13 lag chuẩn hoá, `r4`, `r26` (xu hướng ngắn/dài), `zero_share`, `h`, giá trị cùng kỳ năm trước (lag 52, 53),
  tuần-trong-năm, tháng, cờ nghỉ Tết, `days_to_tet` (kẹp ±60), Giáng sinh, `log(s)`.
- Tham số: lr 0,04; leaves 31; min_data 50; ff 0,85; bagging 0,8; λ₂=1; 500 vòng.
- **CQR** trên cửa sổ hiệu chỉnh rời train/test (CAL_LO = 26 + 2H + 13 tuần): q̂ ở đơn vị chuẩn hoá.
- **Chronos-Bolt-small** zero-shot (ngữ cảnh ≤512 tuần, 13 bước, 3 phân vị) làm đối chứng và ensemble (trung bình phân vị).
- Mốc: naive mùa vụ 52 tuần + phần dư thực nghiệm; trung bình 13 tuần + phần dư thực nghiệm.

### Kết quả (SPL thấp tốt) — chi tiết 03_Evaluation/04
| Bối cảnh | LGBM | LGBM+CQR | Naive mùa vụ | TB 13 tuần | Chronos | Ensemble |
|---|---|---|---|---|---|---|
| `src` (trong miền) | 0,2596 | 0,2608 | 0,3271 | 0,2701 | 0,2628 | **0,2563** |
| `tgt` (zero-shot từ src) | 0,3483 | **0,3474** | 0,4249 | 0,3861 | 0,3667 | 0,3524 |
| Online Retail II — chỉ dữ liệu riêng | 0,2928 | 0,2875 | 0,3638 | 0,2823 | **0,2641** | 0,2685 |
| Online Retail II — tiền huấn luyện tổng hợp + riêng | 0,2818 | 0,2794 | — | — | — | 0,2684 |

cov80: LGBM không CQR 0,79 / 0,75 / 0,67; có CQR 0,84 / 0,80 / 0,83 → **CQR sửa đúng độ phủ thiếu**.

**Đọc:** (i) trên chuỗi tổng hợp LGBM + CQR thắng mọi mốc (−10% so với TB13 ở `tgt`); (ii) trên dữ liệu thật Online Retail II (nhà bán lẻ Anh)
LGBM chỉ thắng TB13 khi **tiền huấn luyện bằng chuỗi tổng hợp** (0,2794 vs 0,2823 — chênh nhỏ) và **Chronos zero-shot tốt nhất**;
(iii) ensemble LGBM+Chronos luôn nằm gần tốt nhất → là mặc định an toàn. Bài học: chuỗi thật có đặc tính (bán lẻ, Giáng sinh,
73 chuỗi) khác máy phát — cần thêm dữ liệu thật doanh thu SME VN (T13).

### Cải tiến đề xuất
1. Ràng buộc: tổng doanh thu mới phải nhất quán với công nợ mới → dùng đặc trưng "hoá đơn đã lập tuần này".
2. Kênh COD vs bán chịu tách riêng (COD → thu ngay).
3. Chronos tinh chỉnh nhẹ (LoRA) trên chuỗi tổng hợp nếu giấy phép cho phép (cần đọc điều khoản trước khi đưa vào sản phẩm).
4. Dự báo phân cấp (công ty → khách lớn) với hoà hợp (reconciliation).

## 4.2 T5 — Bộ máy quy tắc nghĩa vụ (tất định)

Mã: `agent1/calendar_vn.py`; kiểm thử: `tests/test_t0_t5.py` (15 ca, đạt).

**Thiết kế:** quy tắc có **ngày hiệu lực** (effective-dated) để chạy cả lịch sử 2019–2026; ngày nghỉ = python-holidays(VN) ∪ kỳ nghỉ Tết
chính thức (2018–2027); luôn "dịch về ngày làm việc kế tiếp" (VAT, TNDN, môn bài); BHXH lùi về ngày làm việc *trước* (giả định thận trọng).

| Nghĩa vụ | Quy tắc cài đặt | Căn cứ (thứ cấp) |
|---|---|---|
| VAT tháng | ngày 20 tháng sau | Luật QLT 38/2019 Đ.44 |
| VAT quý | ngày cuối tháng đầu quý sau | như trên |
| Ngưỡng kê khai tháng | doanh thu năm trước >50 tỷ | NĐ 126/2020 |
| TNDN tạm nộp quý | ngày 30 tháng đầu quý sau | NĐ 126/2020 |
| TNDN quyết toán | ngày cuối tháng thứ 3 sau năm tài chính | |
| BHXH | 32% (DN 21,5% + NLĐ 10,5%), hạn cuối tháng | QĐ 595 (cần đối chiếu) |
| Lương tối thiểu vùng I–IV | 5 mốc 2019→2026 | NĐ 90/2019 → 293/2025 |
| Môn bài | 30/01; bỏ từ 2026 | NQ 198/2025/QH15 |
| VAT 8% | các kỳ giảm 2022–2026; loại trừ ngành kim loại (đơn giản hoá) | NQ 43/2022 … 204/2025 |

**Ví dụ kiểm thử (đã đạt):** VAT tháng 9/2024 → 21/10/2024 (20/10 là Chủ nhật); VAT Q1/2025 sau nghỉ 30/4–1/5; TNDN tạm nộp quý 4/2024 → 03/02/2025
(30/01 trong nghỉ Tết Ất Tỵ); môn bài 2025 → 03/02/2025, 2026 → không còn; lương tối thiểu vùng I 01/2026 = 5.310.000đ.

**Mở rộng cần làm:** thuế TNCN (khấu trừ tại nguồn), thuế nhà thầu, tiền thuế GTGT hoàn lại, lệnh chi lương thưởng, thanh toán lãi vay theo lịch
hợp đồng thật, quy trình cập nhật khi có văn bản mới (WP-5.x).
